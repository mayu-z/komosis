import { randomUUID } from "node:crypto";
import { Router, type Router as RouterType } from "express";
import type { RunAgentDuplicateResponse, RunAgentRequest, RunAgentResponse } from "@rift/contracts";
import { formatBranchName } from "../branch.js";
import { submissionFingerprint } from "../fingerprint.js";
import { schemaValidators, validateBody } from "../validators.js";
import { buildErrorEnvelope } from "../error-envelope.js";
import { runStore } from "../run-store.js";
import { enqueueAgentRun } from "../queue.js";
import { getPool } from "../db.js";
import { config } from "../config.js";

export const runAgentRouter: RouterType = Router();

runAgentRouter.post("/run-agent", validateBody("runAgentRequest"), async (req, res) => {
  const payload = req.body as RunAgentRequest;
  const fingerprint = submissionFingerprint(payload);
  const existing = runStore.getActiveByFingerprint(fingerprint);

  if (existing) {
    const duplicateResponse: RunAgentDuplicateResponse = runStore.toDuplicateResponse(existing);
    if (!schemaValidators.runAgentDuplicateResponse(duplicateResponse)) {
      return res
        .status(500)
        .json(buildErrorEnvelope("INTERNAL_CONTRACT_ERROR", "Generated duplicate response violates contract"));
    }

    return res.status(409).json(duplicateResponse);
  }

  let branchName: string;
  try {
    branchName = formatBranchName(payload.team_name, payload.leader_name);
  } catch {
    return res
      .status(400)
      .json(buildErrorEnvelope("INVALID_INPUT", "Unable to compute valid branch name"));
  }

  const runId = `run_${randomUUID().replace(/-/g, "").slice(0, 12)}`;
  const response: RunAgentResponse = {
    run_id: runId,
    branch_name: branchName,
    status: "queued",
    socket_room: `/run/${runId}`,
    fingerprint
  };

  if (!schemaValidators.runAgentResponse(response)) {
    return res
      .status(500)
      .json(buildErrorEnvelope("INTERNAL_CONTRACT_ERROR", "Generated response violates contract"));
  }

  // ── Persist to PostgreSQL ────────────────────────────────
  try {
    const pool = getPool();
    await pool.query(
      `INSERT INTO runs (
        run_id, fingerprint, repo_url, team_name, leader_name,
        branch_name, status, start_time
      ) VALUES (
        $1, $2, $3, $4, $5, $6, 'queued', now()
      )
      ON CONFLICT DO NOTHING`,
      [runId, fingerprint, payload.repo_url, payload.team_name, payload.leader_name, branchName]
    );
  } catch (err) {
    // Log but don't fail — in-memory store is fallback
    // eslint-disable-next-line no-console
    console.error("Failed to persist run to PostgreSQL:", err);
  }

  // ── Register in-memory + enqueue to BullMQ ───────────────
  runStore.registerQueuedRun(response);

  try {
    await enqueueAgentRun({
      run_id: runId,
      repo_url: payload.repo_url,
      team_name: payload.team_name,
      leader_name: payload.leader_name,
      branch_name: branchName,
      max_iterations: config.maxIterations,
      feature_flags: {
        ENABLE_KB_LOOKUP: true,
        ENABLE_SPECULATIVE_BRANCHES: false,
        ENABLE_ADVERSARIAL_TESTS: true,
        ENABLE_CAUSAL_GRAPH: true,
        ENABLE_PROVENANCE_PASS: true,
      },
    });
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("Failed to enqueue agent run:", err);
    // Still return 202 — run is registered and can be picked up on retry
  }

  return res.status(202).json(response);
});
