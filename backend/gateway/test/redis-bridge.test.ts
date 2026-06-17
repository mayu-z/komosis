/* ──────────────────────────────────────────────────────────
 * TESTS: Redis → Socket.io Bridge
 *
 * Tests the RedisBridge class that subscribes to Redis pub/sub
 * and forwards events to Socket.io rooms via ContractSafeBroadcaster.
 *
 * Since we can't spin up a real Redis in the unit-test container,
 * we mock the IORedis subscriber and test:
 *   1. Event routing (each of the 5 event types)
 *   2. Run store lifecycle sync (status channel)
 *   3. Malformed message resilience
 *   4. Graceful start/close
 * ────────────────────────────────────────────────────────── */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── Mock IORedis before any imports that use createRequire ──
// The RedisBridge creates an IORedis instance internally, so we
// intercept the dynamic require("ioredis") call.

type Listener = (...args: string[]) => void;

class MockRedisSubscriber {
  private listeners = new Map<string, Listener[]>();
  connected = false;

  async connect(): Promise<void> {
    this.connected = true;
  }
  async psubscribe(_pattern: string): Promise<void> {}
  async subscribe(_channel: string): Promise<void> {}
  async punsubscribe(_pattern: string): Promise<void> {}
  async unsubscribe(_channel: string): Promise<void> {}
  async quit(): Promise<void> {
    this.connected = false;
  }
  disconnect(): void {
    this.connected = false;
  }

  on(event: string, listener: Listener): this {
    const existing = this.listeners.get(event) ?? [];
    existing.push(listener);
    this.listeners.set(event, existing);
    return this;
  }

  /** Simulate receiving a pattern message (pmessage) */
  simulatePMessage(pattern: string, channel: string, message: string): void {
    for (const listener of this.listeners.get("pmessage") ?? []) {
      listener(pattern, channel, message);
    }
  }

  /** Simulate receiving a regular message */
  simulateMessage(channel: string, message: string): void {
    for (const listener of this.listeners.get("message") ?? []) {
      listener(channel, message);
    }
  }
}

// We need to mock the `createRequire` to intercept the ioredis require
let mockSubscriber: MockRedisSubscriber;

vi.mock("node:module", () => ({
  createRequire: () => {
    return (mod: string) => {
      if (mod === "ioredis") {
        return function MockIORedis() {
          return mockSubscriber;
        };
      }
      throw new Error(`Unexpected require("${mod}") in test`);
    };
  },
}));

// ── Now import the module under test ───────────────────────
import { RedisBridge } from "../src/redis-bridge.js";
import { runStore } from "../src/run-store.js";
import type { ContractSafeBroadcaster } from "../src/socket-broadcaster.js";

// ── Helpers ────────────────────────────────────────────────

function createMockBroadcaster() {
  return {
    emitThought: vi.fn(),
    emitFixApplied: vi.fn(),
    emitCiUpdate: vi.fn(),
    emitTelemetryTick: vi.fn(),
    emitRunComplete: vi.fn(),
  } as unknown as ContractSafeBroadcaster & {
    emitThought: ReturnType<typeof vi.fn>;
    emitFixApplied: ReturnType<typeof vi.fn>;
    emitCiUpdate: ReturnType<typeof vi.fn>;
    emitTelemetryTick: ReturnType<typeof vi.fn>;
    emitRunComplete: ReturnType<typeof vi.fn>;
  };
}

function validThought(runId = "run_abc123") {
  return {
    run_id: runId,
    node: "repo_scanner",
    message: "Scanning repository for test failures…",
    step_index: 1,
    timestamp: "2026-02-20T10:00:00Z",
  };
}

function validFixApplied(runId = "run_abc123") {
  return {
    run_id: runId,
    file: "src/main.py",
    bug_type: "SYNTAX",
    line: 42,
    status: "applied",
    confidence: 0.92,
    commit_sha: "abc1234",
  };
}

function validCiUpdate(runId = "run_abc123") {
  return {
    run_id: runId,
    iteration: 1,
    status: "failed",
    regression: false,
    timestamp: "2026-02-20T10:01:00Z",
  };
}

function validTelemetryTick(runId = "run_abc123") {
  return {
    run_id: runId,
    container_id: "ctr_001",
    cpu_pct: 45.2,
    mem_mb: 256.5,
    timestamp: "2026-02-20T10:01:30Z",
  };
}

function validRunComplete(runId = "run_abc123") {
  return {
    run_id: runId,
    final_status: "PASSED",
    score: { base: 100, speed_bonus: 10, efficiency_penalty: 0, total: 110 },
    total_time_secs: 180,
    pdf_url: `/report/${runId}`,
  };
}

// ── Test suites ────────────────────────────────────────────

describe("RedisBridge", () => {
  let bridge: RedisBridge;
  let broadcaster: ReturnType<typeof createMockBroadcaster>;

  beforeEach(() => {
    mockSubscriber = new MockRedisSubscriber();
    broadcaster = createMockBroadcaster();
    bridge = new RedisBridge(broadcaster as unknown as ContractSafeBroadcaster);
  });

  afterEach(async () => {
    await bridge.close();
  });

  // ── Startup & shutdown ────────────────────────────────

  describe("lifecycle", () => {
    it("connects and subscribes on start", async () => {
      const psubSpy = vi.spyOn(mockSubscriber, "psubscribe");
      const subSpy = vi.spyOn(mockSubscriber, "subscribe");

      await bridge.start();

      expect(mockSubscriber.connected).toBe(true);
      expect(psubSpy).toHaveBeenCalledWith("run:event:*");
      expect(subSpy).toHaveBeenCalledWith("run:status");
    });

    it("disconnects on close", async () => {
      await bridge.start();
      await bridge.close();

      expect(mockSubscriber.connected).toBe(false);
    });

    it("is idempotent — double start does not throw", async () => {
      await bridge.start();
      await bridge.start(); // second call should be no-op
      expect(mockSubscriber.connected).toBe(true);
    });

    it("close without start does not throw", async () => {
      await bridge.close(); // should not throw
    });
  });

  // ── Event routing: thought_event ──────────────────────

  describe("thought_event forwarding", () => {
    it("forwards valid thought_event to broadcaster", async () => {
      await bridge.start();
      const payload = validThought();

      mockSubscriber.simulatePMessage("run:event:*", "run:event:thought_event", JSON.stringify(payload));

      expect(broadcaster.emitThought).toHaveBeenCalledOnce();
      expect(broadcaster.emitThought).toHaveBeenCalledWith("/run/run_abc123", payload);
    });
  });

  // ── Event routing: fix_applied ────────────────────────

  describe("fix_applied forwarding", () => {
    it("forwards valid fix_applied to broadcaster", async () => {
      await bridge.start();
      const payload = validFixApplied();

      mockSubscriber.simulatePMessage("run:event:*", "run:event:fix_applied", JSON.stringify(payload));

      expect(broadcaster.emitFixApplied).toHaveBeenCalledOnce();
      expect(broadcaster.emitFixApplied).toHaveBeenCalledWith("/run/run_abc123", payload);
    });
  });

  // ── Event routing: ci_update ──────────────────────────

  describe("ci_update forwarding", () => {
    it("forwards valid ci_update to broadcaster", async () => {
      await bridge.start();
      const payload = validCiUpdate();

      mockSubscriber.simulatePMessage("run:event:*", "run:event:ci_update", JSON.stringify(payload));

      expect(broadcaster.emitCiUpdate).toHaveBeenCalledOnce();
      expect(broadcaster.emitCiUpdate).toHaveBeenCalledWith("/run/run_abc123", payload);
    });
  });

  // ── Event routing: telemetry_tick ─────────────────────

  describe("telemetry_tick forwarding", () => {
    it("forwards valid telemetry_tick to broadcaster", async () => {
      await bridge.start();
      const payload = validTelemetryTick();

      mockSubscriber.simulatePMessage("run:event:*", "run:event:telemetry_tick", JSON.stringify(payload));

      expect(broadcaster.emitTelemetryTick).toHaveBeenCalledOnce();
      expect(broadcaster.emitTelemetryTick).toHaveBeenCalledWith("/run/run_abc123", payload);
    });
  });

  // ── Event routing: run_complete ───────────────────────

  describe("run_complete forwarding", () => {
    it("forwards valid run_complete to broadcaster and marks runStore complete", async () => {
      await bridge.start();

      // First register a run so markComplete has something to clean up
      runStore.registerQueuedRun({
        run_id: "run_abc123",
        status: "queued",
        branch_name: "TEST_TEAM_LEADER_AI_Fix",
        socket_room: "/run/run_abc123",
        fingerprint: "a".repeat(64),
      });
      runStore.markRunning("run_abc123");
      expect(runStore.getActiveByRunId("run_abc123")).toBeDefined();

      const payload = validRunComplete();
      mockSubscriber.simulatePMessage("run:event:*", "run:event:run_complete", JSON.stringify(payload));

      expect(broadcaster.emitRunComplete).toHaveBeenCalledOnce();
      expect(broadcaster.emitRunComplete).toHaveBeenCalledWith("/run/run_abc123", payload);
      // Should also have removed from runStore
      expect(runStore.getActiveByRunId("run_abc123")).toBeUndefined();
    });
  });

  // ── Status channel ────────────────────────────────────

  describe("run:status lifecycle sync", () => {
    it("marks run as running on status=running", async () => {
      await bridge.start();

      runStore.registerQueuedRun({
        run_id: "run_status_01",
        status: "queued",
        branch_name: "TEST_TEAM_LEADER_AI_Fix",
        socket_room: "/run/run_status_01",
        fingerprint: "b".repeat(64),
      });

      expect(runStore.getActiveByRunId("run_status_01")?.status).toBe("queued");

      mockSubscriber.simulateMessage(
        "run:status",
        JSON.stringify({ run_id: "run_status_01", status: "running", current_node: "ci_runner", iteration: 1 })
      );

      expect(runStore.getActiveByRunId("run_status_01")?.status).toBe("running");
    });

    it("marks run as complete on status=passed", async () => {
      await bridge.start();

      runStore.registerQueuedRun({
        run_id: "run_status_02",
        status: "queued",
        branch_name: "TEST_TEAM_LEADER_AI_Fix",
        socket_room: "/run/run_status_02",
        fingerprint: "c".repeat(64),
      });
      runStore.markRunning("run_status_02");

      mockSubscriber.simulateMessage(
        "run:status",
        JSON.stringify({ run_id: "run_status_02", status: "passed", current_node: "scorer", iteration: 3 })
      );

      expect(runStore.getActiveByRunId("run_status_02")).toBeUndefined();
    });

    it("marks run as complete on status=failed", async () => {
      await bridge.start();

      runStore.registerQueuedRun({
        run_id: "run_status_03",
        status: "queued",
        branch_name: "TEST_TEAM_LEADER_AI_Fix",
        socket_room: "/run/run_status_03",
        fingerprint: "d".repeat(64),
      });

      mockSubscriber.simulateMessage(
        "run:status",
        JSON.stringify({ run_id: "run_status_03", status: "failed", current_node: "error_handler", iteration: 0 })
      );

      expect(runStore.getActiveByRunId("run_status_03")).toBeUndefined();
    });

    it("marks run as complete on status=quarantined", async () => {
      await bridge.start();

      runStore.registerQueuedRun({
        run_id: "run_status_04",
        status: "queued",
        branch_name: "TEST_TEAM_LEADER_AI_Fix",
        socket_room: "/run/run_status_04",
        fingerprint: "e".repeat(64),
      });

      mockSubscriber.simulateMessage(
        "run:status",
        JSON.stringify({ run_id: "run_status_04", status: "quarantined", current_node: "scorer", iteration: 5 })
      );

      expect(runStore.getActiveByRunId("run_status_04")).toBeUndefined();
    });
  });

  // ── Resilience / edge cases ───────────────────────────

  describe("error resilience", () => {
    it("ignores unknown event types", async () => {
      await bridge.start();

      mockSubscriber.simulatePMessage(
        "run:event:*",
        "run:event:unknown_thing",
        JSON.stringify({ run_id: "run_x", data: "irrelevant" })
      );

      expect(broadcaster.emitThought).not.toHaveBeenCalled();
      expect(broadcaster.emitFixApplied).not.toHaveBeenCalled();
      expect(broadcaster.emitCiUpdate).not.toHaveBeenCalled();
      expect(broadcaster.emitTelemetryTick).not.toHaveBeenCalled();
      expect(broadcaster.emitRunComplete).not.toHaveBeenCalled();
    });

    it("handles malformed JSON gracefully (no crash)", async () => {
      await bridge.start();

      // Should not throw
      mockSubscriber.simulatePMessage("run:event:*", "run:event:thought_event", "not valid json{{{");

      expect(broadcaster.emitThought).not.toHaveBeenCalled();
    });

    it("handles missing run_id gracefully", async () => {
      await bridge.start();

      mockSubscriber.simulatePMessage(
        "run:event:*",
        "run:event:thought_event",
        JSON.stringify({ node: "scanner", message: "no run_id" })
      );

      expect(broadcaster.emitThought).not.toHaveBeenCalled();
    });

    it("handles malformed status JSON gracefully", async () => {
      await bridge.start();

      mockSubscriber.simulateMessage("run:status", "totally not json");

      // Should not crash, no broadcaster calls
      expect(broadcaster.emitThought).not.toHaveBeenCalled();
    });

    it("handles status message with missing fields gracefully", async () => {
      await bridge.start();

      mockSubscriber.simulateMessage("run:status", JSON.stringify({ garbage: true }));

      // Should be silently ignored
    });

    it("handles broadcaster throwing without crashing", async () => {
      await bridge.start();

      broadcaster.emitThought.mockImplementation(() => {
        throw new Error("Schema validation failed");
      });

      // Should not crash the bridge
      mockSubscriber.simulatePMessage(
        "run:event:*",
        "run:event:thought_event",
        JSON.stringify(validThought())
      );

      expect(broadcaster.emitThought).toHaveBeenCalledOnce();
      // Bridge is still alive — send another event
      mockSubscriber.simulatePMessage(
        "run:event:*",
        "run:event:ci_update",
        JSON.stringify(validCiUpdate())
      );
      expect(broadcaster.emitCiUpdate).toHaveBeenCalledOnce();
    });
  });

  // ── Multi-run isolation ───────────────────────────────

  describe("multi-run isolation", () => {
    it("routes events to correct Socket.io rooms by run_id", async () => {
      await bridge.start();

      const thought1 = validThought("run_AAA");
      const thought2 = validThought("run_BBB");

      mockSubscriber.simulatePMessage("run:event:*", "run:event:thought_event", JSON.stringify(thought1));
      mockSubscriber.simulatePMessage("run:event:*", "run:event:thought_event", JSON.stringify(thought2));

      expect(broadcaster.emitThought).toHaveBeenCalledTimes(2);
      expect(broadcaster.emitThought).toHaveBeenCalledWith("/run/run_AAA", thought1);
      expect(broadcaster.emitThought).toHaveBeenCalledWith("/run/run_BBB", thought2);
    });
  });
});
