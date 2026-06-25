"""
finalizer node — handles healthy repos (tests pass + CI exists).

Sets a human-readable summary and routes to scorer so the run is recorded
with the correct "passed" status and score.
"""
from __future__ import annotations

import logging

from ...db import insert_trace
from ...events import emit_thought
from ..state import AgentState

logger = logging.getLogger("komosis.node.finalizer")


async def finalizer(state: AgentState) -> AgentState:
    """
    Terminal node for healthy repositories.

    Called when decision_node determines that:
      - Tests exist and are passing
      - A CI pipeline already exists

    Sets a summary message and passes state to the scorer.
    """
    run_id = state["run_id"]
    iteration = state.get("iteration", 1)
    step = iteration * 10 + 12

    repo_url = state.get("repo_url", "unknown")
    language = state.get("language", "unknown")
    framework = state.get("framework", "unknown")
    test_count = len(state.get("test_files", []))
    ci_file = state.get("ci_file_path") or "CI pipeline detected"

    summary = (
        f"Repository is healthy — {test_count} {framework} test file(s) "
        f"found and passing, CI pipeline exists ({ci_file}). "
        f"No agent intervention required."
    )

    logger.info("finalizer run=%s — %s", run_id, summary)

    await emit_thought(
        run_id,
        "finalizer",
        f"✅ {summary}",
        step,
    )

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="finalizer",
        action_type="health_check",
        action_label="Repository is healthy — no intervention needed",
        payload={
            "repo_url": repo_url,
            "language": language,
            "framework": framework,
            "test_files": state.get("test_files", []),
            "ci_file_path": state.get("ci_file_path"),
        },
    )

    return {
        "summary": summary,
        # Force a "passed" outcome so scorer gives full score
        "test_exit_code": 0,
        "current_node": "finalizer",
    }
