import { createRequire } from "node:module";
import { config } from "./config.js";

const require = createRequire(import.meta.url);
const IORedis = require("ioredis") as typeof import("ioredis").default;
type RedisClient = InstanceType<typeof IORedis>;

let _redis: RedisClient | null = null;

/**
 * Returns a shared IORedis instance.
 * Lazily created on first call so tests can import the module
 * without connecting to a real Redis.
 */
export function getRedis(): RedisClient {
  if (!_redis) {
    _redis = new IORedis(config.redisUrl, {
      maxRetriesPerRequest: null, // required by BullMQ
      enableReadyCheck: true,
      family: 0, // allow both IPv4 and IPv6 (Railway uses IPv6 private networking)
      retryStrategy(times: number) {
        return Math.min(times * 200, 5000);
      },
    });
  }
  return _redis;
}

/**
 * Returns a *new* IORedis connection suitable for BullMQ
 * (BullMQ requires its own dedicated connections).
 */
export function createRedisConnection(): RedisClient {
  return new IORedis(config.redisUrl, {
    maxRetriesPerRequest: null,
    enableReadyCheck: true,
    family: 0,
    retryStrategy(times: number) {
      return Math.min(times * 200, 5000);
    },
  });
}

/**
 * Graceful shutdown helper.
 */
export async function closeRedis(): Promise<void> {
  if (_redis) {
    await _redis.quit();
    _redis = null;
  }
}
