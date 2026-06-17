import path from "node:path";

export const workerConfig = {
  redisUrl: process.env.REDIS_URL ?? "redis://localhost:6379",
  agentBaseUrl: process.env.AGENT_BASE_URL ?? "http://localhost:8001",
  gatewayBaseUrl: process.env.GATEWAY_BASE_URL ?? "http://localhost:3000",
  pollIntervalMs: Number(process.env.POLL_INTERVAL_MS ?? 3000),
  maxPollAttempts: Number(process.env.MAX_POLL_ATTEMPTS ?? 200),
  outputsDir: process.env.OUTPUTS_DIR ?? path.resolve(process.cwd(), "outputs"),
  concurrency: Number(process.env.WORKER_CONCURRENCY ?? 2),
};
