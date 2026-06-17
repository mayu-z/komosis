import { createRequire } from "node:module";
import { config } from "./config.js";

const require = createRequire(import.meta.url);
const pg = require("pg") as typeof import("pg");
const { Pool } = pg;

type PgPool = InstanceType<typeof Pool>;

let _pool: PgPool | null = null;

/**
 * Returns a shared pg Pool.
 * Lazily created so tests can import without connecting.
 */
export function getPool(): PgPool {
  if (!_pool) {
    _pool = new Pool({
      connectionString: config.databaseUrl,
      max: 10,
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 5_000,
    });
  }
  return _pool;
}

/**
 * Graceful shutdown helper.
 */
export async function closePool(): Promise<void> {
  if (_pool) {
    await _pool.end();
    _pool = null;
  }
}
