"""
RIFT Agent Service — FastAPI application.

Phase C: Fully wired to LangGraph agent with real SSE streaming,
Redis-backed events, asyncpg persistence, and conversational query.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .config import DATABASE_URL, REDIS_URL
from .db import close_pool, get_pool
from .errors import install_error_handlers
from .events import close_event_pool
from .graph.builder import run_agent_graph
from .models import AgentStartRequest, AgentStartResponse, AgentStatusResponse
from .state import RunState, run_state_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger("rift.agent")


# ── Lifespan (startup / shutdown) ───────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup: warm DB pool.  Shutdown: drain connections."""
    logger.info("Agent starting — warming DB + Redis pools…")
    try:
        pool = await get_pool()
        logger.info("DB pool ready (%s)", DATABASE_URL[:40] + "…")
    except Exception as exc:
        logger.warning("DB pool warmup failed (non-fatal): %s", exc)

    yield  # app runs

    logger.info("Agent shutting down — draining pools…")
    await close_pool()
    await close_event_pool()


app = FastAPI(
    title="RIFT Agent Service",
    version="0.2.0",
    lifespan=lifespan,
)
install_error_handlers(app)

# Active graph tasks keyed by run_id
_active_tasks: dict[str, asyncio.Task[None]] = {}


# ── Health ──────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    db_ok = "ok"
    try:
        pool = await get_pool()
        await pool.fetchval("SELECT 1")
    except Exception:
        db_ok = "unavailable"

    return {"agent": "ok", "version": "0.2.0", "database": db_ok}


# ── POST /agent/start ──────────────────────────────────────

@app.post("/agent/start", response_model=AgentStartResponse)
async def agent_start(payload: AgentStartRequest) -> AgentStartResponse:
    """
    Accept a run request and launch the LangGraph agent in background.
    Returns immediately so the worker can poll status.
    """
    run_id = payload.run_id

    # Prevent duplicate launches
    if run_id in _active_tasks and not _active_tasks[run_id].done():
        return AgentStartResponse(accepted=True, run_id=run_id)

    # Update in-memory state
    run_state_store.upsert(
        RunState(run_id=run_id, status="running", current_node="repo_scanner", iteration=0)
    )

    # Launch graph in background
    async def _run() -> None:
        try:
            final = await run_agent_graph(
                run_id=run_id,
                repo_url=payload.repo_url,
                team_name=payload.team_name,
                leader_name=payload.leader_name,
                branch_name=payload.branch_name,
                max_iterations=payload.max_iterations,
                feature_flags=payload.feature_flags.model_dump(),
            )
            run_state_store.upsert(
                RunState(
                    run_id=run_id,
                    status=final.get("status", "failed"),
                    current_node=final.get("current_node", "done"),
                    iteration=final.get("iteration", 0),
                )
            )
        except Exception:
            logger.exception("Agent graph task failed for run %s", run_id)
            run_state_store.upsert(
                RunState(run_id=run_id, status="failed", current_node="error", iteration=0)
            )

    task = asyncio.create_task(_run())
    _active_tasks[run_id] = task

    return AgentStartResponse(accepted=True, run_id=run_id)


# ── GET /agent/status ──────────────────────────────────────

@app.get("/agent/status", response_model=AgentStatusResponse)
async def agent_status(run_id: str) -> AgentStatusResponse:
    state = run_state_store.get(run_id)
    if state is None:
        return AgentStatusResponse(
            run_id=run_id,
            status="queued",
            current_node="queued",
            iteration=0,
        )
    return AgentStatusResponse(
        run_id=state.run_id,
        status=state.status,
        current_node=state.current_node,
        iteration=state.iteration,
    )


# ── GET /agent/stream — real SSE from Redis pub/sub ─────────

@app.get("/agent/stream")
async def agent_stream(run_id: str) -> StreamingResponse:
    """
    Stream thought events for a run via SSE.
    Subscribes to Redis pub/sub and relays events.
    """

    async def event_generator() -> AsyncIterator[str]:
        import redis.asyncio as aioredis

        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()

        channels = [
            "run:event:thought_event",
            "run:event:fix_applied",
            "run:event:ci_update",
            "run:event:telemetry_tick",
            "run:event:run_complete",
            "run:status",
        ]
        await pubsub.subscribe(*channels)

        try:
            # Send initial connection event
            yield (
                "event: thought_event\n"
                f'data: {{"run_id":"{run_id}","node":"stream","message":"SSE connected","step_index":0,"timestamp":""}}\n\n'
            )

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                data = message.get("data", "")
                if not data:
                    continue

                # Filter: only send events for this run_id
                try:
                    parsed = json.loads(data)
                    if parsed.get("run_id") != run_id:
                        continue
                except (json.JSONDecodeError, TypeError):
                    continue

                channel: str = message["channel"]
                event_type = channel.split(":")[-1] if ":" in channel else "status"

                yield f"event: {event_type}\ndata: {data}\n\n"

                # Stop on run_complete
                if event_type == "run_complete":
                    break
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.aclose()
            await r.aclose()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── POST /agent/query — conversational query about a run ────

class AgentQueryRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=2000)


class EvidenceItem(BaseModel):
    step_index: int
    agent_node: str


class AgentQueryResponse(BaseModel):
    run_id: str
    answer: str
    evidence: list[EvidenceItem]


@app.post("/agent/query", response_model=AgentQueryResponse)
async def agent_query(payload: AgentQueryRequest) -> AgentQueryResponse:
    """
    Answer questions about a specific run using execution traces.
    Uses LLM if available, otherwise returns structured summary.
    """
    from .config import OPENAI_API_KEY, OPENAI_MODEL
    from .db import get_fixes_for_run, get_run, get_traces_for_run
    from .llm import get_llm, has_llm_keys

    run_id = payload.run_id

    # Gather context from DB
    run_row = await get_run(run_id)
    traces = await get_traces_for_run(run_id)
    fixes = await get_fixes_for_run(run_id)

    if not run_row:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Build context summary
    trace_summary = "\n".join(
        f"  Step {t['step_index']}: [{t['agent_node']}] {t['action_label']}"
        for t in traces[:50]
    )
    fix_summary = "\n".join(
        f"  {f['file_path']}:{f['line_number']} ({f['bug_type']}) → {f['status']}"
        for f in fixes[:30]
    )
    context = (
        f"Run: {run_id}\n"
        f"Status: {run_row.get('status')}\n"
        f"Repo: {run_row.get('repo_url')}\n"
        f"Branch: {run_row.get('branch_name')}\n"
        f"Execution trace:\n{trace_summary}\n"
        f"Fixes:\n{fix_summary}\n"
    )

    # If we have LLM keys, use it for a better answer
    if has_llm_keys():
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = get_llm(temperature=0.3)
            resp = await llm.ainvoke([
                SystemMessage(
                    content=(
                        "You are an AI assistant explaining CI/CD healing agent activity. "
                        "Answer based on the execution context provided. Be concise and specific."
                    )
                ),
                HumanMessage(content=f"Context:\n{context}\n\nQuestion: {payload.question}"),
            ])
            answer = str(resp.content)
        except Exception:
            logger.exception("LLM query failed — falling back to structured answer")
            answer = (
                f"Run {run_id} status: {run_row.get('status')}. "
                f"{len(traces)} trace steps, {len(fixes)} fixes recorded."
            )
    else:
        answer = (
            f"Run {run_id} status: {run_row.get('status')}. "
            f"{len(traces)} trace steps, {len(fixes)} fixes recorded. "
            f"(LLM unavailable — set GROQ_API_KEYS for detailed answers)"
        )

    evidence = [
        EvidenceItem(step_index=t["step_index"], agent_node=t["agent_node"])
        for t in traces[:10]
    ]

    return AgentQueryResponse(
        run_id=run_id,
        answer=answer,
        evidence=evidence,
    )
