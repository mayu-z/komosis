"""
diff_builder — build a per-file diff summary for the healing branch.

Runs two git commands against the cloned repo:
  1. git diff main..HEAD --name-only   → list of changed files
  2. git diff main..HEAD -- <file>     → unified diff for each file

The result is a list of dicts suitable for JSON serialisation and storage
in the ``diff_summary`` JSONB column, and for display in the frontend
DiffViewer panel.

Design notes:
  - Uses subprocess so there is no gitpython dependency here; the git
    binary is already required by the agent container.
  - Diff content is capped at 3000 chars per file to keep the DB row
    and the socket payload sensible.
  - All failures are handled gracefully — any error returns an empty
    list rather than crashing the finaliser node.
  - Tries ``main`` first, falls back to ``master`` if the base branch
    is named differently.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Any

logger = logging.getLogger("komosis.utils.diff_builder")

_MAX_DIFF_CHARS = 3_000
_BASE_BRANCHES = ("main", "master")


def _run_git(args: list[str], cwd: str) -> str:
    """Run a git command and return stdout. Returns '' on any error."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout
    except Exception as exc:
        logger.debug("git command %s failed: %s", args, exc)
        return ""


def _detect_base_branch(workspace_dir: str) -> str:
    """Return 'main' or 'master' depending on which exists remotely."""
    for branch in _BASE_BRANCHES:
        out = _run_git(
            ["rev-parse", "--verify", f"origin/{branch}"],
            workspace_dir,
        )
        if out.strip():
            return branch
    # Fallback — just use main and let git handle the error gracefully
    return "main"


def build_diff_summary(
    workspace_dir: str,
    branch_name: str,
) -> list[dict[str, Any]]:
    """
    Return a list of ``{"file": str, "diff": str}`` dicts for every file
    changed on ``branch_name`` relative to the repo's default branch.

    Parameters
    ----------
    workspace_dir:
        Absolute path to the cloned repository root.
    branch_name:
        The healing branch name (e.g. ``"komosis/run_abc123"``).

    Returns
    -------
    list[dict]
        Each entry has ``"file"`` (relative path) and ``"diff"`` (unified
        diff string, capped at 3000 chars).  Empty list on any failure.
    """
    try:
        base = _detect_base_branch(workspace_dir)
        ref = f"{base}..HEAD"

        # 1. Get list of changed file paths
        names_out = _run_git(["diff", ref, "--name-only"], workspace_dir)
        changed_files = [f.strip() for f in names_out.splitlines() if f.strip()]

        if not changed_files:
            logger.info(
                "diff_builder: no changed files on branch %s vs %s",
                branch_name, base,
            )
            return []

        # 2. Get per-file diffs
        diffs: list[dict[str, Any]] = []
        for file_path in changed_files:
            diff_out = _run_git(
                ["diff", ref, "--", file_path],
                workspace_dir,
            )
            diffs.append({
                "file": file_path,
                "diff": diff_out[:_MAX_DIFF_CHARS],
            })

        logger.info(
            "diff_builder: %d changed file(s) on branch %s",
            len(diffs), branch_name,
        )
        return diffs

    except Exception as exc:
        logger.error("diff_builder failed: %s", exc, exc_info=True)
        return []
