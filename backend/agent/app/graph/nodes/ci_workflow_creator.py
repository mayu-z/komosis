"""
ci_workflow_creator node — LLM-powered GitHub Actions CI workflow generator.

When ci_monitor detects that a repo has NO GitHub Actions workflow,
this node:
  1. Reads the repo's directory structure, package files, and test config.
  2. Asks the LLM to generate a suitable .github/workflows/ci.yml.
  3. Commits and pushes the workflow to the healing branch.
  4. Sets state so ci_monitor can poll for the real CI run.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path

from git import Repo as GitRepo  # type: ignore[import-untyped]
from langchain_core.messages import HumanMessage, SystemMessage

from ...db import insert_trace
from ...events import emit_thought
from ...llm import get_llm, has_llm_keys
from ..state import AgentState

logger = logging.getLogger("rift.node.ci_workflow_creator")


# ── Helpers ─────────────────────────────────────────────────

def _tree_summary(repo_dir: str, max_depth: int = 3) -> str:
    """Return a compact directory tree string (ignoring node_modules, .git, etc.)."""
    ignored = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
    }
    root = Path(repo_dir)
    lines: list[str] = []

    def _walk(p: Path, depth: int) -> None:
        if depth > max_depth:
            return
        indent = "  " * depth
        for child in sorted(p.iterdir()):
            if child.name in ignored:
                continue
            if child.is_dir():
                lines.append(f"{indent}{child.name}/")
                _walk(child, depth + 1)
            else:
                lines.append(f"{indent}{child.name}")

    try:
        _walk(root, 0)
    except Exception:
        pass
    return "\n".join(lines[:200])  # cap to avoid huge prompts


def _read_file_safe(path: Path, max_chars: int = 3000) -> str:
    """Read a file, returning empty string on error."""
    try:
        return path.read_text(errors="replace")[:max_chars]
    except Exception:
        return ""


def _gather_repo_context(repo_dir: str) -> str:
    """Collect relevant files that help the LLM understand the project."""
    root = Path(repo_dir)
    parts: list[str] = []

    # Directory tree
    parts.append("## Directory Structure\n```")
    parts.append(_tree_summary(repo_dir))
    parts.append("```\n")

    # Key config files
    candidates = [
        "package.json", "pyproject.toml", "setup.py", "setup.cfg",
        "requirements.txt", "Makefile", "tsconfig.json", "vite.config.ts",
        "jest.config.js", "jest.config.ts", "vitest.config.ts",
        "pytest.ini", "tox.ini", ".eslintrc.json", "Cargo.toml",
        "go.mod", "pom.xml", "build.gradle",
    ]
    for name in candidates:
        fp = root / name
        if fp.exists():
            content = _read_file_safe(fp)
            if content:
                parts.append(f"## {name}\n```\n{content}\n```\n")

    return "\n".join(parts)


def _auth_remote_url(url: str) -> str:
    """Inject GITHUB_TOKEN into an HTTPS git remote URL for authentication."""
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        return url
    if "@" in url.split("//", 1)[-1]:
        return url
    m = re.match(r"https://(.+)", url)
    if m:
        return f"https://x-access-token:{token}@{m.group(1)}"
    return url


# ── LLM workflow generation ─────────────────────────────────

async def _generate_workflow_yaml(
    language: str,
    framework: str,
    repo_context: str,
) -> str:
    """Ask the LLM to produce a GitHub Actions CI workflow YAML."""
    llm = get_llm(temperature=0.1)

    system_prompt = (
        "You are a senior DevOps engineer. Generate a GitHub Actions CI workflow YAML file "
        "that runs the project's tests on every push and pull request.\n\n"
        "Rules:\n"
        "- The workflow file goes in `.github/workflows/ci.yml`.\n"
        "- Use a recent, stable runner (ubuntu-latest).\n"
        "- Install dependencies and run the test suite.\n"
        "- Keep it minimal but correct — only what's needed to run tests.\n"
        "- For Node.js projects, detect the package manager (npm/yarn/pnpm) from lock files.\n"
        "- For Python projects, use pip install.\n"
        "- Return ONLY the raw YAML content. No markdown fences. No explanation.\n"
    )

    user_prompt = f"""Generate a CI workflow for this project.

**Language**: {language}
**Test framework**: {framework}

{repo_context}

Return ONLY the YAML content for `.github/workflows/ci.yml`. No markdown, no explanation."""

    resp = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    yaml_content = str(resp.content).strip()

    # Strip markdown fences if the LLM added them despite instructions
    if yaml_content.startswith("```"):
        lines = yaml_content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        yaml_content = "\n".join(lines)

    return yaml_content


# ── Git commit + push ──────────────────────────────────────

def _commit_and_push_workflow(
    repo_dir: str,
    branch_name: str,
    yaml_content: str,
) -> str:
    """Write .github/workflows/ci.yml, commit and push. Returns commit SHA."""
    repo = GitRepo(repo_dir)

    # Configure git user
    with repo.config_writer("repository") as cw:
        cw.set_value("user", "name", "RIFT AI Agent")
        cw.set_value("user", "email", "rift-agent@noreply.github.com")

    # Ensure we're on the right branch
    if repo.active_branch.name != branch_name:
        repo.heads[branch_name].checkout()

    # Write the workflow file
    workflow_dir = Path(repo_dir) / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_file = workflow_dir / "ci.yml"
    workflow_file.write_text(yaml_content + "\n")

    # Stage, commit, push
    repo.git.add(A=True)
    repo.index.commit("[AI-AGENT] Add CI workflow for automated testing")
    commit_sha = repo.head.commit.hexsha[:7]

    # Push with auth
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


# ── Node entry point ───────────────────────────────────────

async def ci_workflow_creator(state: AgentState) -> AgentState:
    """
    Generate and push a GitHub Actions CI workflow when the repo has none.
    """
    run_id = state["run_id"]
    repo_dir = state.get("repo_dir", "")
    repo_url = state["repo_url"]
    branch_name = state["branch_name"]
    language = state.get("language", "unknown")
    framework = state.get("framework", "unknown")
    iteration = state.get("iteration", 1)
    total_commits = state.get("total_commits", 0)
    step = iteration * 10 + 8  # unique step after ci_monitor's step+1

    await emit_thought(
        run_id, "ci_workflow_creator",
        "No CI workflow detected — generating GitHub Actions workflow with LLM…",
        step,
    )

    # Guard: need LLM keys
    if not has_llm_keys():
        logger.warning("No LLM keys — cannot generate CI workflow")
        await emit_thought(
            run_id, "ci_workflow_creator",
            "Skipping workflow generation — no LLM keys available",
            step + 1,
        )
        return {
            "ci_workflow_created": True,  # prevent infinite loop
            "current_ci_status": "passed",  # fall through gracefully
            "current_node": "ci_workflow_creator",
        }

    # Check if workflow already exists (shouldn't get here, but safety)
    workflow_path = Path(repo_dir) / ".github" / "workflows"
    if workflow_path.exists() and any(workflow_path.glob("*.yml")):
        logger.info("CI workflow already exists — skipping generation")
        await emit_thought(
            run_id, "ci_workflow_creator",
            "CI workflow already exists — skipping",
            step + 1,
        )
        return {
            "ci_workflow_created": True,
            "current_node": "ci_workflow_creator",
        }

    # Gather repo context for the LLM
    repo_context = await asyncio.to_thread(_gather_repo_context, repo_dir)

    # Generate the workflow YAML
    try:
        yaml_content = await _generate_workflow_yaml(language, framework, repo_context)
    except Exception as exc:
        logger.exception("LLM workflow generation failed: %s", exc)
        await emit_thought(
            run_id, "ci_workflow_creator",
            f"Failed to generate CI workflow: {exc}",
            step + 1,
        )
        return {
            "ci_workflow_created": True,
            "current_ci_status": "passed",
            "current_node": "ci_workflow_creator",
        }

    if not yaml_content or len(yaml_content) < 20:
        logger.warning("LLM returned empty/invalid workflow YAML")
        await emit_thought(
            run_id, "ci_workflow_creator",
            "LLM returned invalid workflow — skipping CI",
            step + 1,
        )
        return {
            "ci_workflow_created": True,
            "current_ci_status": "passed",
            "current_node": "ci_workflow_creator",
        }

    # Commit and push
    try:
        commit_sha = await asyncio.to_thread(
            _commit_and_push_workflow, repo_dir, branch_name, yaml_content,
        )
    except Exception as exc:
        logger.exception("Failed to push CI workflow: %s", exc)
        await emit_thought(
            run_id, "ci_workflow_creator",
            f"Failed to push workflow: {exc}",
            step + 1,
        )
        return {
            "ci_workflow_created": True,
            "current_ci_status": "passed",
            "current_node": "ci_workflow_creator",
        }

    await emit_thought(
        run_id, "ci_workflow_creator",
        f"✅ Pushed CI workflow (commit {commit_sha}) — will now monitor real CI",
        step + 1,
    )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="ci_workflow_creator",
        action_type="workflow_push",
        action_label=f"Generated and pushed .github/workflows/ci.yml",
        payload={
            "commit_sha": commit_sha,
            "branch": branch_name,
            "language": language,
            "framework": framework,
            "yaml_length": len(yaml_content),
        },
    )

    return {
        "ci_workflow_created": True,
        "total_commits": total_commits + 1,
        "current_node": "ci_workflow_creator",
    }
