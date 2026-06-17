/**
 * Redis → Socket.io Bridge
 *
 * Subscribes to Redis pub/sub channels published by the Worker and Agent,
 * then forwards each event to the correct Socket.io room via the
 * ContractSafeBroadcaster.  Also syncs the in-memory runStore so the
 * status endpoint stays accurate.
 *
 * Channels consumed:
 *   run:event:thought_event   → broadcaster.emitThought
 *   run:event:fix_applied     → broadcaster.emitFixApplied
 *   run:event:ci_update       → broadcaster.emitCiUpdate
 *   run:event:telemetry_tick  → broadcaster.emitTelemetryTick
 *   run:event:run_complete    → broadcaster.emitRunComplete  +  runStore.markComplete
 *   run:status                → runStore.markRunning / markComplete
 *
 * Design notes:
 * - Uses a DEDICATED Redis connection because Redis requires a separate
 *   connection for pub/sub (the subscribed client can't do normal commands).
 * - Pattern-subscribe (`psubscribe("run:event:*")`) is used for the five
 *   event channels, plus a regular `subscribe("run:status")` for lifecycle.
 * - Every handler is wrapped in try/catch so a single malformed message
 *   never crashes the bridge.
 */
import { createRequire } from "node:module";
import type { ContractSafeBroadcaster } from "./socket-broadcaster.js";
import { runStore } from "./run-store.js";
import { config } from "./config.js";

const require = createRequire(import.meta.url);
const IORedis = require("ioredis") as typeof import("ioredis").default;
type RedisClient = InstanceType<typeof IORedis>;

// ── Channel constants ──────────────────────────────────────

const EVENT_PATTERN = "run:event:*";
const STATUS_CHANNEL = "run:status";

/**
 * Map the last segment of a Redis channel name to the broadcaster method.
 *
 *   "run:event:thought_event"  → "thought_event"
 *   "run:event:fix_applied"    → "fix_applied"
 *   etc.
 */
type EventType =
  | "thought_event"
  | "fix_applied"
  | "ci_update"
  | "telemetry_tick"
  | "run_complete";

function extractEventType(channel: string): EventType | null {
  const last = channel.split(":").pop() ?? "";
  const allowed: EventType[] = [
    "thought_event",
    "fix_applied",
    "ci_update",
    "telemetry_tick",
    "run_complete",
  ];
  return allowed.includes(last as EventType) ? (last as EventType) : null;
}

// ── Bridge class ───────────────────────────────────────────

export class RedisBridge {
  private subscriber: RedisClient | null = null;
  private running = false;

  constructor(private readonly broadcaster: ContractSafeBroadcaster) {}

  /**
   * Create a dedicated Redis subscriber connection, subscribe to all
   * required channels, and start forwarding messages.
   */
  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;

    this.subscriber = new IORedis(config.redisUrl, {
      maxRetriesPerRequest: null,
      enableReadyCheck: true,
      lazyConnect: true,
      family: 0,
      retryStrategy(times: number) {
        return Math.min(times * 200, 5000);
      },
    });

    // Connect
    await this.subscriber.connect();

    // ── Pattern subscribe: run:event:* ────────────────────
    this.subscriber.on("pmessage", (pattern: string, channel: string, message: string) => {
      this.handleEventMessage(channel, message);
    });

    // ── Regular subscribe: run:status ─────────────────────
    this.subscriber.on("message", (channel: string, message: string) => {
      if (channel === STATUS_CHANNEL) {
        this.handleStatusMessage(message);
      }
    });

    await this.subscriber.psubscribe(EVENT_PATTERN);
    await this.subscriber.subscribe(STATUS_CHANNEL);

    // eslint-disable-next-line no-console
    console.log(
      `[RedisBridge] Subscribed to pattern "${EVENT_PATTERN}" and channel "${STATUS_CHANNEL}"`
    );
  }

  /**
   * Graceful shutdown — unsubscribe and disconnect.
   */
  async close(): Promise<void> {
    if (!this.subscriber) return;
    this.running = false;

    try {
      await this.subscriber.punsubscribe(EVENT_PATTERN);
      await this.subscriber.unsubscribe(STATUS_CHANNEL);
    } catch {
      /* best effort */
    }

    try {
      await this.subscriber.quit();
    } catch {
      this.subscriber.disconnect();
    }

    this.subscriber = null;
    // eslint-disable-next-line no-console
    console.log("[RedisBridge] Closed");
  }

  // ── Private handlers ────────────────────────────────────

  /**
   * Forward a run:event:* message to the correct Socket.io room.
   */
  private handleEventMessage(channel: string, raw: string): void {
    try {
      const eventType = extractEventType(channel);
      if (!eventType) return;

      const payload = JSON.parse(raw);
      const runId: string | undefined = payload?.run_id;
      if (!runId) {
        // eslint-disable-next-line no-console
        console.warn(`[RedisBridge] Missing run_id in ${channel}`);
        return;
      }

      const room = `/run/${runId}`;

      switch (eventType) {
        case "thought_event":
          this.broadcaster.emitThought(room, payload);
          break;
        case "fix_applied":
          this.broadcaster.emitFixApplied(room, payload);
          break;
        case "ci_update":
          this.broadcaster.emitCiUpdate(room, payload);
          break;
        case "telemetry_tick":
          this.broadcaster.emitTelemetryTick(room, payload);
          break;
        case "run_complete":
          this.broadcaster.emitRunComplete(room, payload);
          // Also sync runStore
          runStore.markComplete(runId);
          break;
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(
        `[RedisBridge] Error handling event on ${channel}:`,
        err instanceof Error ? err.message : err
      );
    }
  }

  /**
   * Handle run:status messages to keep the in-memory run store in sync.
   *
   * Payload shape (from worker):
   *   { run_id, status, current_node, iteration }
   */
  private handleStatusMessage(raw: string): void {
    try {
      const data = JSON.parse(raw) as {
        run_id: string;
        status: string;
        current_node?: string;
        iteration?: number;
      };

      if (!data.run_id || !data.status) return;

      const terminalStates = ["passed", "failed", "quarantined"];

      if (data.status === "running") {
        runStore.markRunning(data.run_id);
      } else if (terminalStates.includes(data.status)) {
        runStore.markComplete(data.run_id);
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error(
        "[RedisBridge] Error handling status message:",
        err instanceof Error ? err.message : err
      );
    }
  }
}
