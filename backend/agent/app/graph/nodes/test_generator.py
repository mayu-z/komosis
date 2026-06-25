"""
test_generator node — LLM-powered test suite generator.

Called by decision_node when ``has_tests = False`` (the repo has no test
files at all). Produces one focused test file for the most important source
file in the repo, then passes control to cicd_generator so the branch ends
up with both tests and a CI pipeline in the same run.

Design constraints:
  - Generate tests for ONE file only — better to have a small, passing test
    suite than a large broken one.
  - Use asyncio.to_thread for all blocking file/git I/O.
  - Validate the generated file parses before committing (Python: ast.parse;
    TypeScript/JS: rough fence check; others: skip validation).
  - If generation or push fails, degrade gracefully and still route to
    cicd_generator so the CI pipeline is at least attempted.
"""
from __future__ import annotations

import ast
import asyncio
import logging
import os
import re
from pathlib import Path

from git import Repo as GitRepo  # type: ignore[import-untyped]
from langchain_core.messages import HumanMessage, SystemMessage

from ...db import insert_fix, insert_trace
from ...events import emit_thought
from ...llm import get_llm, has_llm_keys
from ..state import AgentState
from ...utils.file_analyzer import find_best_file_to_test
from ...prompts.cicd_prompts import (
    TEST_GENERATION_SYSTEM,
    TEST_GENERATION_PROMPT,
    get_test_file_path,
    default_framework,
)

logger = logging.getLogger("komosis.node.test_generator")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove markdown code fences that the LLM may include."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _validate_python(content: str) -> bool:
    """Return True if the content is valid Python syntax."""
    try:
        ast.parse(content)
        return True
    except SyntaxError as exc:
        logger.warning("Generated Python test file has syntax error: %s", exc)
        return False


def _validate_generated(content: str, language: str) -> bool:
    """
    Basic validation of generated test content.

    For Python, use the AST. For other languages, just check that the content
    is non-empty and doesn't still have fence markers (LLM sometimes ignores
    the instruction even after stripping).
    """
    if not content or len(content.strip()) < 20:
        return False
    if "```" in content:
        return False   # fence stripping missed something

    if language == "python":
        return _validate_python(content)

    return True     # other languages: trust the LLM output


def _auth_remote_url(url: str) -> str:
    """Inject GITHUB_TOKEN into HTTPS remote URL for auth."""
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        return url
    if "@" in url.split("//", 1)[-1]:
        return url
    m = re.match(r"https://(.+)", url)
    if m:
        return f"https://x-access-token:{token}@{m.group(1)}"
    return url


def _write_and_commit(
    repo_dir: str,
    branch_name: str,
    test_file_rel: str,
    test_content: str,
    source_basename: str,
    framework: str,
) -> str:
    """
    Write the generated test file, commit, and push. Returns short commit SHA.
    Runs synchronously — wrap with asyncio.to_thread at the call site.
    """
    repo = GitRepo(repo_dir)

    with repo.config_writer("repository") as cw:
        cw.set_value("user", "name",  "Komosis Agent")
        cw.set_value("user", "email", "komosis-agent@noreply.github.com")

    if repo.active_branch.name != branch_name:
        repo.heads[branch_name].checkout()  # type: ignore[union-attr]

    # Write test file (create parent dirs as needed)
    full_path = Path(repo_dir) / test_file_rel
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(test_content + "\n", encoding="utf-8")

    repo.git.add(A=True)

    commit_msg = f"[AI-AGENT] Add {framework} tests for {source_basename}"
    repo.index.commit(commit_msg)
    commit_sha = repo.head.commit.hexsha[:7]

    origin = repo.remotes.origin
    original_url = origin.url
    auth_url = _auth_remote_url(original_url)
    if auth_url != original_url:
        origin.set_url(auth_url)
    try:
        origin.push(branch_name)
    finally:
        if auth_url != original_url:
            origin.set_url(original_url)

    return commit_sha


# ── Node entry point ──────────────────────────────────────────────────────────

async def test_generator(state: AgentState) -> AgentState:
    """
    Generate a test file for the repository's most important source file.

    Steps:
      1. Identify the best file to test (file_analyzer utility).
      2. Determine the test framework (from state or language default).
      3. Call LLM to produce test file content.
      4. Validate syntax / strip fences.
      5. Write file, commit, push.
      6. Update state with test_files list and route to cicd_generator.
    """
    run_id      = state["run_id"]
    repo_dir    = state.get("repo_dir", "")
    branch_name = state["branch_name"]
    language    = state.get("language", "unknown")
    framework   = state.get("framework") or default_framework(language)
    iteration   = state.get("iteration", 1)
    total_commits = state.get("total_commits", 0)
    step        = iteration * 10 + 10

    await emit_thought(
        run_id, "test_generator",
        f"Scanning repo for best file to test ({language}/{framework})…",
        step,
    )

    # ── 1. Guard: no LLM keys ────────────────────────────────────────────────
    if not has_llm_keys():
        msg = "No LLM keys configured — cannot generate tests"
        logger.error("test_generator run=%s: %s", run_id, msg)
        await emit_thought(run_id, "test_generator", f"⚠ {msg}", step + 1)
        await insert_trace(
            run_id,
            step_index=step,
            agent_node="test_generator",
            action_type="test_generation",
            action_label="Skipped — no LLM keys",
            payload={"language": language, "framework": framework},
        )
        return {
            "summary": msg,
            "current_node": "test_generator",
        }

    # ── 2. Find best source file ──────────────────────────────────────────────
    result = await asyncio.to_thread(
        find_best_file_to_test, repo_dir, language
    )

    if result is None:
        # No suitable file found — try with a relaxed size limit before giving up.
        result = await asyncio.to_thread(
            find_best_file_to_test, repo_dir, language,
            max_lines=350,
        )

    if result is None:
        msg = (
            f"No suitable {language} source file found for test generation. "
            f"Skipping test generation, proceeding to CI/CD pipeline."
        )
        logger.warning("test_generator run=%s: %s", run_id, msg)
        await emit_thought(run_id, "test_generator", f"⚠ {msg}", step + 1)
        await insert_trace(
            run_id,
            step_index=step,
            agent_node="test_generator",
            action_type="test_generation",
            action_label="Skipped — no suitable source file",
            payload={"language": language, "framework": framework},
        )
        return {
            "summary": msg,
            "current_node": "test_generator",
        }

    source_rel, source_content = result
    source_basename = os.path.basename(source_rel)

    await emit_thought(
        run_id, "test_generator",
        f"Generating {framework} tests for {source_rel}…",
        step + 1,
    )
    logger.info(
        "test_generator run=%s source=%s framework=%s",
        run_id, source_rel, framework,
    )

    # ── 3. Generate test content via LLM ────────────────────────────────────
    user_prompt = TEST_GENERATION_PROMPT.format(
        language=language,
        framework=framework,
        file_path=source_rel,
        source_code=source_content[:4000],  # cap to keep prompt under token limit
    )
    llm = get_llm(temperature=0.1)   # slight variance encourages diverse test cases

    try:
        resp = await llm.ainvoke([
            SystemMessage(content=TEST_GENERATION_SYSTEM),
            HumanMessage(content=user_prompt),
        ])
        test_content = _strip_fences(str(resp.content))
    except Exception as exc:
        err = f"LLM call failed: {exc}"
        logger.exception("test_generator run=%s: %s", run_id, err)
        await emit_thought(run_id, "test_generator", f"⚠ {err}", step + 2)
        return {
            "summary": f"Test generation failed: {err}. Proceeding to CI/CD generation.",
            "current_node": "test_generator",
        }

    # ── 4. Validate generated content ────────────────────────────────────────
    if not _validate_generated(test_content, language):
        msg = "Generated test file failed validation — skipping commit"
        logger.warning("test_generator run=%s: %s (content preview: %r)", run_id, msg, test_content[:100])
        await emit_thought(run_id, "test_generator", f"⚠ {msg}", step + 2)
        return {
            "summary": f"{msg}. Proceeding to CI/CD generation.",
            "current_node": "test_generator",
        }

    # ── 5. Determine test file path ───────────────────────────────────────────
    test_file_rel = get_test_file_path(source_rel, language)

    await emit_thought(
        run_id, "test_generator",
        f"Writing test file: {test_file_rel}",
        step + 2,
    )

    # ── 6. Write + commit + push ─────────────────────────────────────────────
    try:
        commit_sha = await asyncio.to_thread(
            _write_and_commit,
            repo_dir, branch_name,
            test_file_rel, test_content,
            source_basename, framework,
        )
    except Exception as exc:
        err = f"Git commit/push failed: {exc}"
        logger.exception("test_generator run=%s: %s", run_id, err)
        await emit_thought(run_id, "test_generator", f"⚠ {err}", step + 3)
        return {
            "summary": f"Tests generated but push failed: {err}. Proceeding to CI/CD.",
            "current_node": "test_generator",
        }

    # ── 7. Persist fix record ─────────────────────────────────────────────────
    fix_id = await insert_fix(
        run_id,
        file_path=test_file_rel,
        bug_type="LOGIC",       # missing tests = logic gap
        line_number=1,
        description="No test suite present in repository",
        fix_description=f"Generated {framework} tests for {source_rel}",
        original_code="",
        fixed_code=test_content[:2000],
        status="applied",
        commit_sha=commit_sha,
        commit_message=f"[AI-AGENT] Add {framework} tests for {source_basename}",
        confidence_score=0.8,
        model_used="llm",
    )

    await emit_thought(
        run_id, "test_generator",
        f"✅ Committed {test_file_rel} → {commit_sha}",
        step + 3,
    )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="test_generator",
        action_type="test_generation",
        action_label=f"Generated {framework} tests for {source_basename}",
        payload={
            "language":     language,
            "framework":    framework,
            "source_file":  source_rel,
            "test_file":    test_file_rel,
            "test_lines":   len(test_content.splitlines()),
            "commit_sha":   commit_sha,
            "fix_id":       fix_id,
        },
    )

    summary = (
        f"Generated {framework} tests for {source_basename}. "
        f"Test file: {test_file_rel}. "
        f"Committed at {commit_sha}. "
        f"Proceeding to CI/CD pipeline generation."
    )

    # Update test_files and has_tests so scorer and DB records are accurate
    existing_test_files = list(state.get("test_files", []))
    existing_test_files.append(test_file_rel)

    return {
        "summary":       summary,
        "test_files":    existing_test_files,
        "has_tests":     True,
        "framework":     framework,
        "total_commits": total_commits + 1,
        "current_node":  "test_generator",
    }
