import { Queue } from "bullmq";
import { config } from "./config.js";

export const AGENT_RUNS_QUEUE = "agent-runs";

let _queue: Queue | null = null;

/**
 * Parse Redis URL into host/port/auth for BullMQ connection.
 */
function parseRedisUrl(url: string): { host: string; port: number; username?: string; password?: string; family?: number } {
  const parsed = new URL(url);
  const opts: { host: string; port: number; username?: string; password?: string; family?: number } = {
    host: parsed.hostname || "localhost",
    port: Number(parsed.port) || 6379,
    family: 0,
  };
  if (parsed.username) opts.username = decodeURIComponent(parsed.username);
  if (parsed.password) opts.password = decodeURIComponent(parsed.password);
  return opts;
}

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
 * Returns the shared BullMQ producer queue for agent runs.
 */
export function getQueue(): Queue<AgentRunJobData> {
  if (!_queue) {
    const redisOpts = parseRedisUrl(config.redisUrl);
    _queue = new Queue<AgentRunJobData>(AGENT_RUNS_QUEUE, {
      connection: redisOpts,
      defaultJobOptions: {
        attempts: 3,
        backoff: { type: "exponential", delay: 2000 },
        removeOnComplete: { count: 500 },
        removeOnFail: { count: 200 },
      },
    });
  }
  return _queue as Queue<AgentRunJobData>;
}

/**
 * Enqueue an agent run job.
 */
export async function enqueueAgentRun(data: AgentRunJobData): Promise<string> {
  const queue = getQueue();
  const job = await queue.add("process-run", data, {
    jobId: data.run_id, // idempotent: same run_id = same job
  });
  return job.id ?? data.run_id;
}

/**
 * Graceful shutdown helper.
 */
export async function closeQueue(): Promise<void> {
  if (_queue) {
    await _queue.close();
    _queue = null;
  }
}
