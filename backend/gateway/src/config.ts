import path from "node:path";

export const config = {
  port: Number(process.env.PORT ?? 3000),
  outputsDir: process.env.OUTPUTS_DIR ?? path.resolve(process.cwd(), "outputs"),
  maxIterations: Number(process.env.MAX_ITERATIONS ?? 5),

  // Database
  databaseUrl:
    process.env.DATABASE_URL ??
    "postgres://rift:rift_secret@localhost:5432/rift",

  // Redis
  redisUrl: process.env.REDIS_URL ?? "redis://localhost:6379",

  // Agent service
  agentBaseUrl: process.env.AGENT_BASE_URL ?? "http://localhost:8001",
};
