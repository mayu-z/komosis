"""
cicd_generator node — LLM-powered GitHub Actions CI/CD pipeline generator.

Called by decision_node when:
  (a) tests exist and are passing but no CI pipeline is present, OR
  (b) test_generator has just created a test file and wants a CI pipeline too.

Pipeline content:
  CI section  — always complete: install → lint → test → build.
  CD section  — platform-specific when detected; commented placeholder otherwise.

The workflow file is committed and pushed to the healing branch using the
same auth pattern as commit_push.py (GITHUB_TOKEN injected into the remote
URL, then restored immediately after push so no token is persisted on disk).
"""
from __future__ import annotations

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
from ...utils.platform_detector import detect_platform, PlatformHints
from ...prompts.cicd_prompts import (
    CICD_SYSTEM,
    CI_ONLY_PROMPT,
    CI_WITH_CD_PROMPT,
    CI_PLACEHOLDER_PROMPT,
    get_test_command,
    get_platform_guidance,
)

logger = logging.getLogger("komosis.node.cicd_generator")

_WORKFLOWS_DIR = ".github/workflows"
_OUTPUT_FILENAME = "ci.yml"


# ── YAML fence stripping ──────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """
    Remove markdown code fences that the LLM may include despite instructions.
    Handles ``` and ```yaml and ```yml opening tags.
    """
    text = text.strip()
    # More robust than a manual loop: strip leading and trailing fence lines.
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


# ── LLM prompt selection ──────────────────────────────────────────────────────

def _build_prompt(
    language: str,
    framework: str,
    hints: PlatformHints,
) -> tuple[str, str]:
    """
    Return (system_prompt, user_prompt) based on detected platform.

    Three cases:
      1. Platform detected → full CI + CD
      2. No platform, has Dockerfile → CI only (Docker build step included)
      3. No platform, no Docker  → CI + commented CD placeholder
    """
    test_cmd = get_test_command(language, framework)
    base = {
        "language":       language,
        "framework":      framework,
        "test_command":   test_cmd,
        "has_dockerfile": hints.has_dockerfile,
    }

    if hints.platform:
        user = CI_WITH_CD_PROMPT.format(
            **base,
            platform=hints.platform,
            platform_hints=str(hints.deploy_hints) or "none",
            platform_guidance=get_platform_guidance(hints.platform),
        )
    elif hints.has_dockerfile:
        # Only CI; the Dockerfile already handles the CD surface.
        user = CI_ONLY_PROMPT.format(**base)
    else:
        user = CI_PLACEHOLDER_PROMPT.format(**base)

    return CICD_SYSTEM, user


# ── Git helpers ───────────────────────────────────────────────────────────────

def _auth_remote_url(url: str) -> str:
    """Inject GITHUB_TOKEN into an HTTPS remote URL for authentication."""
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        return url
    if "@" in url.split("//", 1)[-1]:
        return url          # already has credentials embedded
    m = re.match(r"https://(.+)", url)
    if m:
        return f"https://x-access-token:{token}@{m.group(1)}"
    return url


def _write_and_commit(
    repo_dir: str,
    branch_name: str,
    yaml_content: str,
    language: str,
    platform: str | None,
) -> str:
    """
    Write .github/workflows/ci.yml, commit, push. Returns the short commit SHA.

    Runs synchronously; wrap with asyncio.to_thread at the call site.
    """
    repo = GitRepo(repo_dir)

    # Git identity (required for committing)
    with repo.config_writer("repository") as cw:
        cw.set_value("user", "name",  "Komosis Agent")
        cw.set_value("user", "email", "komosis-agent@noreply.github.com")

    # Checkout the healing branch
    if repo.active_branch.name != branch_name:
        repo.heads[branch_name].checkout()  # type: ignore[union-attr]

    # Write the workflow file
    workflow_dir = Path(repo_dir) / _WORKFLOWS_DIR
    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_file = workflow_dir / _OUTPUT_FILENAME
    workflow_file.write_text(yaml_content + "\n", encoding="utf-8")

    # Stage all changes (the new ci.yml and any parent dirs)
    repo.git.add(A=True)

    platform_label = platform or "no platform detected"
    commit_msg = (
        f"[AI-AGENT] Add CI/CD pipeline for {language} ({platform_label})"
    )
    repo.index.commit(commit_msg)
    commit_sha = repo.head.commit.hexsha[:7]

    # Push with token auth; always restore original URL afterwards
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

async def cicd_generator(state: AgentState) -> AgentState:
    """
    Generate a CI/CD pipeline and commit it to the healing branch.

    Steps:
      1. Detect deployment platform from repo files.
      2. Select the appropriate prompt template.
      3. Call LLM to produce YAML.
      4. Strip any markdown fences.
      5. Write .github/workflows/ci.yml.
      6. Commit + push via asyncio.to_thread (blocks on I/O).
      7. Update state with commit details and summary.
    """
    run_id      = state["run_id"]
    repo_dir    = state.get("repo_dir", "")
    branch_name = state["branch_name"]
    language    = state.get("language", "unknown")
    framework   = state.get("framework", "unknown")
    iteration   = state.get("iteration", 1)
    total_commits = state.get("total_commits", 0)
    step        = iteration * 10 + 11

    await emit_thought(
        run_id, "cicd_generator",
        f"Generating CI/CD pipeline for {language}/{framework}…",
        step,
    )

    # ── 1. Guard: no LLM keys ────────────────────────────────────────────────
    if not has_llm_keys():
        msg = "No LLM keys configured — cannot generate CI/CD pipeline"
        logger.error("cicd_generator run=%s: %s", run_id, msg)
        await emit_thought(run_id, "cicd_generator", f"⚠ {msg}", step + 1)
        return {
            "summary": msg,
            "current_node": "cicd_generator",
        }

    # ── 2. Detect platform ───────────────────────────────────────────────────
    hints = await asyncio.to_thread(detect_platform, repo_dir)
    platform_label = hints.platform or "none detected"

    await emit_thought(
        run_id, "cicd_generator",
        f"Platform: {platform_label} | Dockerfile: {hints.has_dockerfile}",
        step + 1,
    )
    logger.info(
        "cicd_generator run=%s lang=%s framework=%s platform=%s",
        run_id, language, framework, hints.platform,
    )

    # ── 3. Build prompt and call LLM ─────────────────────────────────────────
    system_prompt, user_prompt = _build_prompt(language, framework, hints)
    llm = get_llm(temperature=0.0)   # deterministic — YAML must be valid

    try:
        resp = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        yaml_content = _strip_fences(str(resp.content))
    except Exception as exc:
        err = f"LLM call failed: {exc}"
        logger.exception("cicd_generator run=%s: %s", run_id, err)
        await emit_thought(run_id, "cicd_generator", f"⚠ {err}", step + 2)
        return {
            "summary": f"CI/CD generation failed: {err}",
            "current_node": "cicd_generator",
        }

    if not yaml_content or not yaml_content.startswith("name:"):
        # LLM returned something that doesn't look like valid YAML — log and bail.
        err = f"LLM returned invalid YAML (first 100 chars: {yaml_content[:100]!r})"
        logger.error("cicd_generator run=%s: %s", run_id, err)
        await emit_thought(run_id, "cicd_generator", f"⚠ {err}", step + 2)
        return {
            "summary": f"CI/CD generation produced invalid YAML: {err}",
            "current_node": "cicd_generator",
        }

    await emit_thought(
        run_id, "cicd_generator",
        f"Generated {len(yaml_content.splitlines())} lines of YAML",
        step + 2,
    )

    # ── 4. Write + commit + push ──────────────────────────────────────────────
    try:
        commit_sha = await asyncio.to_thread(
            _write_and_commit,
            repo_dir, branch_name, yaml_content, language, hints.platform,
        )
    except Exception as exc:
        err = f"Git commit/push failed: {exc}"
        logger.exception("cicd_generator run=%s: %s", run_id, err)
        await emit_thought(run_id, "cicd_generator", f"⚠ {err}", step + 3)
        return {
            "summary": f"CI/CD pipeline generated but push failed: {err}",
            "current_node": "cicd_generator",
        }

    workflow_rel = f"{_WORKFLOWS_DIR}/{_OUTPUT_FILENAME}"
    platform_str = hints.platform or "placeholder"

    # ── 5. Persist fix record ─────────────────────────────────────────────────
    fix_id = await insert_fix(
        run_id,
        file_path=workflow_rel,
        bug_type="SYNTAX",      # closest canonical type for a missing pipeline
        line_number=1,
        description="No CI/CD pipeline present in repository",
        fix_description=(
            f"Generated GitHub Actions CI/CD pipeline "
            f"(platform: {platform_str})"
        ),
        original_code="",
        fixed_code=yaml_content[:2000],
        status="applied",
        commit_sha=commit_sha,
        commit_message=(
            f"[AI-AGENT] Add CI/CD pipeline for {language} ({platform_str})"
        ),
        confidence_score=0.9,
        model_used="llm",
    )

    await emit_thought(
        run_id, "cicd_generator",
        f"✅ Committed {workflow_rel} → {commit_sha} (platform: {platform_str})",
        step + 3,
    )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="cicd_generator",
        action_type="cicd_generation",
        action_label=f"Generated CI/CD pipeline ({platform_str})",
        payload={
            "language":       language,
            "framework":      framework,
            "platform":       hints.platform,
            "has_dockerfile": hints.has_dockerfile,
            "yaml_lines":     len(yaml_content.splitlines()),
            "commit_sha":     commit_sha,
            "workflow_file":  workflow_rel,
            "fix_id":         fix_id,
        },
    )

    summary = (
        f"Generated GitHub Actions CI/CD pipeline for {language}/{framework}. "
        f"Platform: {platform_str}. "
        f"Committed {workflow_rel} at {commit_sha}."
    )

    return {
        "summary":          summary,
        "ci_workflow_created": True,
        "has_ci_pipeline":  True,
        "ci_file_path":     workflow_rel,
        "total_commits":    total_commits + 1,
        "test_exit_code":   0,   # reaching here means tests passed (or gen succeeded)
        "current_node":     "cicd_generator",
    }
