"""
Redis-backed event emitter.

Publishes SSE-compatible events to Redis pub/sub channels so the
Worker → Gateway → Socket.io pipeline can forward them to the frontend.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from .config import REDIS_URL

logger = logging.getLogger("rift.events")

_pool: aioredis.ConnectionPool | None = None


async def _get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(REDIS_URL, decode_responses=True)
    return aioredis.Redis(connection_pool=_pool)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def emit_thought(
    run_id: str,
    node: str,
    message: str,
    step_index: int,
) -> None:
    """Publish a thought_event to Redis."""
    payload = {
        "run_id": run_id,
        "node": node,
        "message": message,
        "step_index": step_index,
        "timestamp": _now_iso(),
    }
    r = await _get_redis()
    await r.publish("run:event:thought_event", json.dumps(payload))
    logger.debug("thought_event run=%s node=%s step=%d", run_id, node, step_index)


async def emit_fix_applied(
    run_id: str,
    file: str,
    bug_type: str,
    line: int,
    status: str,
    confidence: float,
    commit_sha: str | None = None,
) -> None:
    """Publish a fix_applied event to Redis."""
    payload = {
        "run_id": run_id,
        "file": file,
        "bug_type": bug_type,
        "line": line,
        "status": status,
        "confidence": confidence,
    }
    # Optional field must be omitted when absent to satisfy strict schema.
    if commit_sha:
        payload["commit_sha"] = commit_sha
    r = await _get_redis()
    await r.publish("run:event:fix_applied", json.dumps(payload))
    logger.debug("fix_applied run=%s file=%s", run_id, file)


async def emit_ci_update(
    run_id: str,
    iteration: int,
    status: str,
    regression: bool,
) -> None:
    """Publish a ci_update event to Redis."""
    # Keep socket payload contract-safe even if callers pass internal statuses.
    if status == "no_ci":
        status = "failed"
    if status not in {"pending", "running", "passed", "failed"}:
        status = "failed"

    payload = {
        "run_id": run_id,
        "iteration": iteration,
        "status": status,
        "regression": regression,
        "timestamp": _now_iso(),
    }
    r = await _get_redis()
    await r.publish("run:event:ci_update", json.dumps(payload))
    logger.debug("ci_update run=%s iter=%d status=%s", run_id, iteration, status)


async def emit_telemetry_tick(
    run_id: str,
    container_id: str,
    cpu_pct: float,
    mem_mb: float,
) -> None:
    """Publish a telemetry_tick event to Redis."""
    payload = {
        "run_id": run_id,
        "container_id": container_id,
        "cpu_pct": cpu_pct,
        "mem_mb": mem_mb,
        "timestamp": _now_iso(),
    }
    r = await _get_redis()
    await r.publish("run:event:telemetry_tick", json.dumps(payload))


async def emit_run_complete(
    run_id: str,
    final_status: str,
    score: dict[str, float],
    total_time_secs: float,
    pdf_url: str,
) -> None:
    """Publish a run_complete event to Redis."""
    payload = {
        "run_id": run_id,
        "final_status": final_status,
        "score": score,
        "total_time_secs": total_time_secs,
        "pdf_url": pdf_url,
    }
    r = await _get_redis()
    await r.publish("run:event:run_complete", json.dumps(payload))
    logger.info("run_complete run=%s status=%s score=%s", run_id, final_status, score.get("total"))


async def emit_status_update(
    run_id: str,
    status: str,
    current_node: str,
    iteration: int,
) -> None:
    """Publish a status update (consumed by Worker polling)."""
    payload = {
        "run_id": run_id,
        "status": status,
        "current_node": current_node,
        "iteration": iteration,
    }
    r = await _get_redis()
    await r.publish("run:status", json.dumps(payload))


async def close_event_pool() -> None:
    """Drain the Redis connection pool at shutdown."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
