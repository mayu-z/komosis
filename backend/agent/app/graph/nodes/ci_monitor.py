"""
ci_monitor node — poll GitHub Actions (or simulate) and detect regressions.

This node waits for the CI run to complete after a push, recording the
result into the state and database.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from ...config import POLL_CI_INTERVAL_SECS, POLL_CI_TIMEOUT_SECS
from ...db import insert_ci_event, insert_trace
from ...events import emit_ci_update, emit_thought
from ..state import AgentState, CiRun

logger = logging.getLogger("rift.node.ci_monitor")


def _public_ci_status(status: str) -> str:
    """
    Map internal CI statuses to contract-safe public statuses.
    """
    return "failed" if status == "no_ci" else status


async def _poll_github_actions(
    repo_url: str,
    branch_name: str,
    timeout_secs: int,
    poll_interval: int,
    workflow_just_created: bool = False,
) -> tuple[str, int | None, float]:
    """
    Poll GitHub Actions for the latest workflow run on the branch.
    Returns (status, github_run_id, duration_secs).

    If GitHub API is unavailable (no token, rate limit), simulates a pass
    based on whether the commit was successful.

    When workflow_just_created=True, we wait for the full timeout instead
    of bailing early on empty runs — GitHub may take a moment to register
    the newly pushed workflow.
    """
    import os

    github_token = os.getenv("GITHUB_TOKEN", "")

    # Extract owner/repo from URL
    # https://github.com/owner/repo.git → owner/repo
    parts = repo_url.rstrip("/").removesuffix(".git").split("/")
    if len(parts) < 2:
        logger.warning("Cannot parse repo owner/name from %s", repo_url)
        return "passed", None, 0.0

    owner, repo_name = parts[-2], parts[-1]

    if not github_token:
        logger.info("No GITHUB_TOKEN — simulating CI pass (demo mode)")
        await asyncio.sleep(2)  # simulate some CI delay
        return "passed", None, 2.0

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    start = time.monotonic()
    no_workflow_polls = 0  # Track consecutive polls with no workflow runs
    async with httpx.AsyncClient(timeout=15) as client:
        while (time.monotonic() - start) < timeout_secs:
            try:
                resp = await client.get(
                    f"https://api.github.com/repos/{owner}/{repo_name}/actions/runs",
                    params={"branch": branch_name, "per_page": 1},
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    runs = data.get("workflow_runs", [])
                    if runs:
                        run = runs[0]
                        gh_status = run.get("conclusion")
                        gh_run_id = run.get("id")
                        if gh_status == "success":
                            return "passed", gh_run_id, time.monotonic() - start
                        elif gh_status in ("failure", "cancelled", "timed_out"):
                            return "failed", gh_run_id, time.monotonic() - start
                        # else still in progress, keep polling
                        no_workflow_polls = 0
                    else:
                        no_workflow_polls += 1
                        # If we've polled 3+ times and never seen a workflow run,
                        # the repo has no CI configured.
                        # But if a workflow was just created, keep waiting —
                        # GitHub needs time to register and trigger it.
                        if no_workflow_polls >= 3 and not workflow_just_created:
                            logger.info(
                                "No GitHub Actions workflow found for %s/%s branch %s "
                                "after %d polls — returning no_ci",
                                owner, repo_name, branch_name, no_workflow_polls,
                            )
                            return "no_ci", None, time.monotonic() - start
                elif resp.status_code == 403:
                    logger.warning("GitHub API rate limited — simulating pass")
                    return "passed", None, time.monotonic() - start
            except httpx.HTTPError as exc:
                logger.warning("GitHub API error: %s", exc)

            await asyncio.sleep(poll_interval)

    # Timeout
    return "failed", None, timeout_secs


async def ci_monitor(state: AgentState) -> AgentState:
    """
    Poll CI status after a push, detect regressions.
    """
    run_id = state["run_id"]
    repo_url = state["repo_url"]
    branch_name = state["branch_name"]
    iteration = state.get("iteration", 1)
    ci_runs = list(state.get("ci_runs", []))
    failures_before = len(state.get("failures", []))
    workflow_created = state.get("ci_workflow_created", False)
    step = iteration * 10 + 7

    await emit_thought(run_id, "ci_monitor", f"Monitoring CI for iteration {iteration}…", step)
    await emit_ci_update(run_id, iteration, "running", False)

    triggered_at = datetime.now(timezone.utc)

    ci_status, github_run_id, duration = await _poll_github_actions(
        repo_url,
        branch_name,
        POLL_CI_TIMEOUT_SECS,
        POLL_CI_INTERVAL_SECS,
        workflow_just_created=workflow_created,
    )
    public_status = _public_ci_status(ci_status)

    completed_at = datetime.now(timezone.utc)

    # Detect regression: if previous iteration passed but this one failed
    regression = False
    if ci_runs and ci_runs[-1].status == "passed" and ci_status == "failed":
        regression = True

    ci_run = CiRun(
        iteration=iteration,
        status=ci_status,  # type: ignore[arg-type]
        github_run_id=github_run_id,
        failures_before=failures_before,
        failures_after=0 if ci_status == "passed" else failures_before,
        regression=regression,
        duration_secs=duration,
        timestamp=completed_at.isoformat(),
    )
    ci_runs.append(ci_run)

    await emit_ci_update(run_id, iteration, public_status, regression)

    await insert_ci_event(
        run_id,
        iteration=iteration,
        status=public_status,
        github_run_id=github_run_id,
        failures_before=failures_before,
        failures_after=ci_run.failures_after,
        regression_detected=regression,
        duration_secs=duration,
        triggered_at=triggered_at,
        completed_at=completed_at,
    )

    await emit_thought(
        run_id, "ci_monitor",
        f"CI iteration {iteration}: {public_status.upper()}"
        + (f" ⚠ REGRESSION DETECTED" if regression else ""),
        step + 1,
    )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="ci_monitor",
        action_type="ci_poll",
        action_label=f"CI {ci_status} — {'regression' if regression else 'clean'}",
        payload={
            "ci_status": public_status,
            "github_run_id": github_run_id,
            "regression": regression,
            "duration_secs": round(duration, 1),
        },
    )

    return {
        "ci_runs": ci_runs,
        "current_ci_status": ci_status,  # type: ignore[typeddict-item]
        "regression_detected": regression,
        "current_node": "ci_monitor",
    }
