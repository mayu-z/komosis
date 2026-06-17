import { createRequire } from "node:module";
import { Worker, Job } from "bullmq";
import { workerConfig } from "./config.js";

const require = createRequire(import.meta.url);
const IORedis = require("ioredis") as typeof import("ioredis").default;
type RedisClient = InstanceType<typeof IORedis>;

const AGENT_RUNS_QUEUE = "agent-runs";

export interface AgentRunJobData {
  run_id: string;
  repo_url: string;
  team_name: string;
  leader_name: string;
  branch_name: string;
  max_iterations: number;
  feature_flags: {
    ENABLE_KB_LOOKUP: boolean;
    ENABLE_SPECULATIVE_BRANCHES: boolean;
    ENABLE_ADVERSARIAL_TESTS: boolean;
    ENABLE_CAUSAL_GRAPH: boolean;
    ENABLE_PROVENANCE_PASS: boolean;
  };
}

/**
 * Sleep helper.
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Notify the gateway that a run's status has changed.
 * Uses Redis pub/sub key that gateway can subscribe to.
 */
async function publishStatusUpdate(
  redis: RedisClient,
  runId: string,
  status: string,
  currentNode: string,
  iteration: number
): Promise<void> {
  const payload = JSON.stringify({ run_id: runId, status, current_node: currentNode, iteration });
  await redis.publish("run:status", payload);
}

/**
 * Process a single agent run job:
 * 1. POST /agent/start to kick off the agent
 * 2. Poll GET /agent/status until terminal state
 * 3. Bridge SSE thought events to Redis pub/sub
 */
async function processAgentRun(job: Job<AgentRunJobData>): Promise<void> {
  const { run_id, repo_url, team_name, leader_name, branch_name, max_iterations, feature_flags } = job.data;
  const redis = new IORedis(workerConfig.redisUrl, { maxRetriesPerRequest: null });

  // eslint-disable-next-line no-console
  console.log(`[Worker] Processing run ${run_id} for ${team_name}/${leader_name}`);

  try {
    // ── Step 1: Start the agent ────────────────────────────
    await publishStatusUpdate(redis, run_id, "running", "repo_scanner", 0);

    const startResp = await fetch(`${workerConfig.agentBaseUrl}/agent/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id,
        repo_url,
        team_name,
        leader_name,
        branch_name,
        max_iterations,
        feature_flags,
      }),
      signal: AbortSignal.timeout(30_000),
    });

    if (!startResp.ok) {
      const text = await startResp.text();
      throw new Error(`Agent /agent/start returned ${startResp.status}: ${text}`);
    }

    const startData = (await startResp.json()) as { accepted: boolean; run_id: string };
    if (!startData.accepted) {
      throw new Error(`Agent rejected run ${run_id}`);
    }

    // eslint-disable-next-line no-console
    console.log(`[Worker] Agent accepted run ${run_id}`);

    // ── Step 2: Poll agent status until terminal ────────────
    // Events are published directly by the agent to Redis pub/sub,
    // and the gateway's RedisBridge subscribes to those channels.
    // No SSE bridge needed — avoids duplicate event delivery.
    let attempts = 0;
    let terminal = false;

    while (attempts < workerConfig.maxPollAttempts && !terminal) {
      await sleep(workerConfig.pollIntervalMs);
      attempts++;

      try {
        const statusResp = await fetch(
          `${workerConfig.agentBaseUrl}/agent/status?run_id=${run_id}`,
          { signal: AbortSignal.timeout(10_000) }
        );

        if (!statusResp.ok) continue;

        const statusData = (await statusResp.json()) as {
          run_id: string;
          status: string;
          current_node: string;
          iteration: number;
        };

        await publishStatusUpdate(redis, run_id, statusData.status, statusData.current_node, statusData.iteration);
        await job.updateProgress(Math.min(100, Math.round((statusData.iteration / max_iterations) * 100)));

        if (["passed", "failed", "quarantined"].includes(statusData.status)) {
          terminal = true;
          // eslint-disable-next-line no-console
          console.log(`[Worker] Run ${run_id} reached terminal state: ${statusData.status}`);
        }
      } catch {
        // eslint-disable-next-line no-console
        console.warn(`[Worker] Poll attempt ${attempts} failed for ${run_id}`);
      }
    }

    if (!terminal) {
      // eslint-disable-next-line no-console
      console.warn(`[Worker] Run ${run_id} timed out after ${attempts} poll attempts`);
      await publishStatusUpdate(redis, run_id, "failed", "timeout", 0);
    }

    // eslint-disable-next-line no-console
    console.log(`[Worker] Finished processing run ${run_id}`);
  } finally {
    await redis.quit();
  }
}

// ── Parse Redis URL for BullMQ connection ──────────────────
function parseRedisUrl(url: string): { host: string; port: number; username?: string; password?: string; family?: number } {
  const parsed = new URL(url);
  const opts: { host: string; port: number; username?: string; password?: string; family?: number } = {
    host: parsed.hostname || "localhost",
    port: Number(parsed.port) || 6379,
    family: 0, // allow both IPv4 and IPv6 (Railway private networking uses IPv6)
  };
  if (parsed.username) opts.username = decodeURIComponent(parsed.username);
  if (parsed.password) opts.password = decodeURIComponent(parsed.password);
  return opts;
}

// ── Create and start the BullMQ worker ─────────────────────
const redisOpts = parseRedisUrl(workerConfig.redisUrl);

const worker = new Worker<AgentRunJobData>(
  AGENT_RUNS_QUEUE,
  processAgentRun,
  {
    connection: redisOpts,
    concurrency: workerConfig.concurrency,
    removeOnComplete: { count: 500 },
    removeOnFail: { count: 200 },
  }
);

worker.on("completed", (job) => {
  // eslint-disable-next-line no-console
  console.log(`[Worker] Job ${job.id} completed for run ${job.data.run_id}`);
});

worker.on("failed", (job, err) => {
  // eslint-disable-next-line no-console
  console.error(`[Worker] Job ${job?.id} failed:`, err.message);
});

worker.on("error", (err) => {
  // eslint-disable-next-line no-console
  console.error("[Worker] Worker error:", err);
});

// eslint-disable-next-line no-console
console.log(`[Worker] Started — consuming queue "${AGENT_RUNS_QUEUE}" with concurrency ${workerConfig.concurrency}`);

// ── Graceful shutdown ──────────────────────────────────────
async function shutdown(signal: string): Promise<void> {
  // eslint-disable-next-line no-console
  console.log(`\n[Worker] ${signal} received — shutting down…`);
  await worker.close();
  process.exit(0);
}

process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("SIGINT", () => void shutdown("SIGINT"));
