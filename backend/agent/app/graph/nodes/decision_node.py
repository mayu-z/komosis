"""
decision_node — reads repo_scanner output and routes the graph.

Routing logic:
  - has_tests = False                          → test_generator
  - has_tests = True, tests_passing = False    → test_runner  (existing fix flow)
  - has_tests = True, tests_passing = True,
    has_ci_pipeline = False                    → cicd_generator
  - has_tests = True, tests_passing = True,
    has_ci_pipeline = True                     → finalizer   (nothing to do)
"""
from __future__ import annotations

import logging

from ...db import insert_trace
from ...events import emit_thought
from ..state import AgentState

logger = logging.getLogger("komosis.node.decision_node")


async def decision_node(state: AgentState) -> AgentState:
    """
    Inspect repo health and set ``next_node`` for conditional routing.

    This node runs immediately after ``repo_scanner`` and determines the
    most useful action for this repository without running the test suite
    itself — that is delegated to the appropriate downstream node.
    """
    run_id = state["run_id"]
    iteration = state.get("iteration", 1)
    step = iteration * 10 + 2   # sits between repo_scanner (step+1) and test_runner (step+3)

    has_tests: bool = state.get("has_tests", False)
    has_ci_pipeline: bool = state.get("has_ci_pipeline", False)
    tests_passing: bool = state.get("tests_passing", False)

    logger.info(
        "decision_node run=%s has_tests=%s tests_passing=%s has_ci=%s",
        run_id, has_tests, tests_passing, has_ci_pipeline,
    )

    await emit_thought(
        run_id,
        "decision_node",
        (
            f"Repo health: has_tests={has_tests}, "
            f"tests_passing={tests_passing}, "
            f"has_ci_pipeline={has_ci_pipeline}"
        ),
        step,
    )

    # ── Routing decision ─────────────────────────────────────────────────────

    if not has_tests:
        # No tests at all — generate them first, then optionally add CI
        next_node = "test_generator"
        reason = "No tests found → routing to test_generator"

    elif has_tests and not tests_passing:
        # Tests exist but are failing — run the existing fix flow
        next_node = "test_runner"
        reason = "Tests failing → routing to test_runner (fix flow)"

    elif has_tests and tests_passing and not has_ci_pipeline:
        # Tests pass but there's no CI — add a pipeline
        next_node = "cicd_generator"
        reason = "Tests passing, no CI pipeline → routing to cicd_generator"

    else:
        # Tests pass AND CI exists — repo is healthy, nothing to do
        next_node = "finalizer"
        reason = "Tests passing and CI exists → routing to finalizer (healthy repo)"

    logger.info("decision_node run=%s → %s (%s)", run_id, next_node, reason)

    await emit_thought(run_id, "decision_node", reason, step + 1)

    await insert_trace(
        run_id,
        step_index=step,
        agent_node="decision_node",
        action_type="routing",
        action_label=reason,
        payload={
            "has_tests": has_tests,
            "has_ci_pipeline": has_ci_pipeline,
            "tests_passing": tests_passing,
            "next_node": next_node,
        },
    )

    return {
        "next_node": next_node,
        "current_node": "decision_node",
    }
