/* ──────────────────────────────────────────────────────────
 * ACCEPTANCE TEST: End-to-End Run Lifecycle
 *
 * Covers ACCEPTANCE_TESTS.md §4, §8, §10:
 *   Full lifecycle: POST /run-agent → GET /agent/status (queued)
 *     → markRunning → GET /agent/status (running)
 *     → markComplete + results.json → GET /results → GET /agent/status (passed)
 *     → duplicate 409 before completion → error envelope for unknown run
 * ────────────────────────────────────────────────────────── */
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import request from "supertest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ResultsJson } from "@rift/contracts";
import { writeResultsArtifact } from "../src/artifacts.js";

let outputsDir = "";
let createApp: (typeof import("../src/app.js"))["createApp"];
let runStore: (typeof import("../src/run-store.js"))["runStore"];

const VALID_PAYLOAD = {
  repo_url: "https://github.com/e2e-org/e2e-repo",
  team_name: "E2E Warriors",
  leader_name: "Test Lead",
};

function validResults(runId: string): ResultsJson {
  return {
    run_id: runId,
    repo_url: "https://github.com/e2e-org/e2e-repo",
    team_name: "E2E Warriors",
    leader_name: "Test Lead",
    branch_name: "E2E_WARRIORS_TEST_LEAD_AI_Fix",
    final_status: "PASSED",
    total_failures: 2,
    total_fixes: 2,
    total_time_secs: 200,
    score: {
      base: 100,
      speed_bonus: 10,
      efficiency_penalty: 0,
      total: 110,
    },
    fixes: [
      {
        file: "src/main.py",
        bug_type: "SYNTAX",
        line_number: 12,
        commit_message: "[AI-AGENT] fix missing colon",
        status: "FIXED",
      },
      {
        file: "src/utils.py",
        bug_type: "LINTING",
        line_number: 34,
        commit_message: "[AI-AGENT] fix trailing whitespace",
        status: "FIXED",
      },
    ],
    ci_log: [
      {
        iteration: 1,
        status: "failed",
        timestamp: "2026-02-19T10:01:00Z",
        regression: false,
      },
      {
        iteration: 2,
        status: "passed",
        timestamp: "2026-02-19T10:03:00Z",
        regression: false,
      },
    ],
  };
}

beforeEach(async () => {
  outputsDir = await mkdtemp(path.join(os.tmpdir(), "rift-e2e-"));
  process.env.OUTPUTS_DIR = outputsDir;
  vi.resetModules();
  ({ createApp } = await import("../src/app.js"));
  ({ runStore } = await import("../src/run-store.js"));
});

afterEach(async () => {
  delete process.env.OUTPUTS_DIR;
  await rm(outputsDir, { recursive: true, force: true });
});

// ── Full lifecycle ──────────────────────────────────────────

describe("E2E run lifecycle", () => {
  it("complete lifecycle: submit → queued → running → complete → results", async () => {
    const app = createApp();

    // ① Submit new run
    const submitRes = await request(app).post("/run-agent").send(VALID_PAYLOAD);
    expect(submitRes.status).toBe(202);
    expect(submitRes.body.status).toBe("queued");
    expect(submitRes.body.run_id).toMatch(/^run_/);
    expect(submitRes.body.branch_name).toBe("E2E_WARRIORS_TEST_LEAD_AI_Fix");
    expect(submitRes.body.socket_room).toMatch(/^\/run\//);
    expect(submitRes.body.fingerprint).toMatch(/^[a-f0-9]{64}$/);

    const runId: string = submitRes.body.run_id;

    // ② Status is queued
    const queuedStatus = await request(app).get(`/agent/status/${runId}`);
    expect(queuedStatus.status).toBe(200);
    expect(queuedStatus.body.run_id).toBe(runId);
    expect(queuedStatus.body.status).toBe("queued");
    expect(queuedStatus.body.progress_pct).toBe(0);

    // ③ Mark running
    runStore.markRunning(runId);
    const runningStatus = await request(app).get(`/agent/status/${runId}`);
    expect(runningStatus.status).toBe(200);
    expect(runningStatus.body.status).toBe("running");

    // ④ Mark complete + write results artifact
    runStore.markComplete(runId);
    await writeResultsArtifact(outputsDir, runId, validResults(runId));

    // ⑤ Status resolves from artifact
    const completeStatus = await request(app).get(`/agent/status/${runId}`);
    expect(completeStatus.status).toBe(200);
    expect(completeStatus.body.status).toBe("passed");
    expect(completeStatus.body.progress_pct).toBe(100);

    // ⑥ Results endpoint returns full artifact
    const resultsRes = await request(app).get(`/results/${runId}`);
    expect(resultsRes.status).toBe(200);
    expect(resultsRes.body.run_id).toBe(runId);
    expect(resultsRes.body.final_status).toBe("PASSED");
    expect(resultsRes.body.fixes).toHaveLength(2);
    expect(resultsRes.body.ci_log).toHaveLength(2);
    expect(resultsRes.body.score.total).toBe(110);
  });
});

// ── Duplicate submission (409) ──────────────────────────────

describe("duplicate submission handling", () => {
  it("returns 409 with duplicate response while run is active", async () => {
    const app = createApp();

    const first = await request(app).post("/run-agent").send(VALID_PAYLOAD);
    expect(first.status).toBe(202);

    const second = await request(app).post("/run-agent").send(VALID_PAYLOAD);
    expect(second.status).toBe(409);
    expect(second.body.run_id).toBe(first.body.run_id);
    expect(second.body.status).toBe("queued");
    expect(second.body.message).toContain("fingerprint");

    // Cleanup
    runStore.markComplete(first.body.run_id);
  });

  it("allows resubmission after previous run completes", async () => {
    const app = createApp();

    const first = await request(app).post("/run-agent").send(VALID_PAYLOAD);
    expect(first.status).toBe(202);
    runStore.markComplete(first.body.run_id);

    const second = await request(app).post("/run-agent").send(VALID_PAYLOAD);
    expect(second.status).toBe(202);
    expect(second.body.run_id).not.toBe(first.body.run_id);

    // Cleanup
    runStore.markComplete(second.body.run_id);
  });
});

// ── Error envelope conformance ──────────────────────────────

describe("error envelope conformance", () => {
  it("returns error envelope for unknown run_id on /agent/status", async () => {
    const app = createApp();
    const res = await request(app).get("/agent/status/run_nonexistent999");
    expect(res.status).toBe(404);
    expect(res.body.error).toBeDefined();
    expect(res.body.error.code).toBe("NOT_FOUND");
    expect(typeof res.body.error.message).toBe("string");
  });

  it("returns error envelope for missing results.json on /results", async () => {
    const app = createApp();
    const res = await request(app).get("/results/run_missing_01");
    expect(res.status).toBe(404);
    expect(res.body.error).toBeDefined();
    expect(res.body.error.code).toBe("NOT_FOUND");
  });

  it("returns error envelope for missing report.pdf on /report", async () => {
    const app = createApp();
    const res = await request(app).get("/report/run_missing_02");
    expect(res.status).toBe(404);
    expect(res.body.error).toBeDefined();
    expect(res.body.error.code).toBe("NOT_FOUND");
  });

  it("returns error envelope for non-existent endpoint", async () => {
    const app = createApp();
    const res = await request(app).get("/nonexistent");
    expect(res.status).toBe(404);
    expect(res.body.error).toBeDefined();
    expect(res.body.error.code).toBe("NOT_FOUND");
    expect(res.body.error.message).toBe("Endpoint not found");
  });

  it("returns error envelope for invalid run_id format", async () => {
    const app = createApp();
    const res = await request(app).get("/agent/status/../etc/passwd");
    // Express normalizes path, but the pattern check should catch it
    expect(res.status === 400 || res.status === 404).toBe(true);
    expect(res.body.error).toBeDefined();
  });

  it("error envelope has no extra top-level keys", async () => {
    const app = createApp();
    const res = await request(app).get("/results/run_ghost_01");
    expect(res.status).toBe(404);
    // Only "error" key at top level per ErrorEnvelope schema
    expect(Object.keys(res.body)).toEqual(["error"]);
    expect(Object.keys(res.body.error)).toContain("code");
    expect(Object.keys(res.body.error)).toContain("message");
  });
});

// ── POST /run-agent validation ──────────────────────────────

describe("POST /run-agent input validation", () => {
  it("rejects empty body", async () => {
    const app = createApp();
    const res = await request(app).post("/run-agent").send({});
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe("INVALID_INPUT");
  });

  it("rejects missing repo_url", async () => {
    const app = createApp();
    const res = await request(app).post("/run-agent").send({
      team_name: "Team",
      leader_name: "Leader",
    });
    expect(res.status).toBe(400);
  });

  it("rejects missing team_name", async () => {
    const app = createApp();
    const res = await request(app).post("/run-agent").send({
      repo_url: "https://github.com/org/repo",
      leader_name: "Leader",
    });
    expect(res.status).toBe(400);
  });

  it("rejects missing leader_name", async () => {
    const app = createApp();
    const res = await request(app).post("/run-agent").send({
      repo_url: "https://github.com/org/repo",
      team_name: "Team",
    });
    expect(res.status).toBe(400);
  });

  it("rejects non-URL repo_url", async () => {
    const app = createApp();
    const res = await request(app).post("/run-agent").send({
      repo_url: "not-a-url",
      team_name: "Team",
      leader_name: "Leader",
    });
    expect(res.status).toBe(400);
  });

  it("rejects additional unexpected properties (strict mode)", async () => {
    const app = createApp();
    const res = await request(app).post("/run-agent").send({
      repo_url: "https://github.com/org/repo",
      team_name: "Team",
      leader_name: "Leader",
      hacker_payload: "drop table",
    });
    // Schema uses additionalProperties:false, should reject
    expect(res.status).toBe(400);
  });
});

// ── Artifact integrity ──────────────────────────────────────

describe("artifact integrity", () => {
  it("written results.json is schema-valid when read back", async () => {
    const runId = "run_integrity_01";
    const results = validResults(runId);
    await writeResultsArtifact(outputsDir, runId, results);

    const app = createApp();
    const res = await request(app).get(`/results/${runId}`);
    expect(res.status).toBe(200);

    // Verify all required fields present
    const body = res.body as ResultsJson;
    expect(body.run_id).toBe(runId);
    expect(body.repo_url).toBeDefined();
    expect(body.team_name).toBeDefined();
    expect(body.leader_name).toBeDefined();
    expect(body.branch_name).toBeDefined();
    expect(body.final_status).toBeDefined();
    expect(typeof body.total_failures).toBe("number");
    expect(typeof body.total_fixes).toBe("number");
    expect(typeof body.total_time_secs).toBe("number");
    expect(body.score).toBeDefined();
    expect(body.fixes).toBeInstanceOf(Array);
    expect(body.ci_log).toBeInstanceOf(Array);
  });

  it("results.json fixes all have [AI-AGENT] commit prefix", async () => {
    const runId = "run_prefix_01";
    const results = validResults(runId);
    await writeResultsArtifact(outputsDir, runId, results);

    const app = createApp();
    const res = await request(app).get(`/results/${runId}`);
    expect(res.status).toBe(200);

    for (const fix of res.body.fixes) {
      expect(fix.commit_message).toMatch(/^\[AI-AGENT\]/);
    }
  });

  it("results.json fixes all have valid bug_type from required set", async () => {
    const runId = "run_bugtype_01";
    const results = validResults(runId);
    await writeResultsArtifact(outputsDir, runId, results);

    const app = createApp();
    const res = await request(app).get(`/results/${runId}`);
    expect(res.status).toBe(200);

    const validTypes = new Set([
      "LINTING",
      "SYNTAX",
      "LOGIC",
      "TYPE_ERROR",
      "IMPORT",
      "INDENTATION",
    ]);
    for (const fix of res.body.fixes) {
      expect(validTypes.has(fix.bug_type)).toBe(true);
    }
  });

  it("results.json ci_log entries have valid statuses", async () => {
    const runId = "run_cilog_01";
    const results = validResults(runId);
    await writeResultsArtifact(outputsDir, runId, results);

    const app = createApp();
    const res = await request(app).get(`/results/${runId}`);
    expect(res.status).toBe(200);

    const validStatuses = new Set(["passed", "failed", "error"]);
    for (const entry of res.body.ci_log) {
      expect(validStatuses.has(entry.status)).toBe(true);
      expect(typeof entry.iteration).toBe("number");
      expect(typeof entry.timestamp).toBe("string");
      expect(typeof entry.regression).toBe("boolean");
    }
  });

  it("report.pdf endpoint returns PDF content-type", async () => {
    const runId = "run_report_e2e";
    const runDir = path.join(outputsDir, runId);
    await mkdir(runDir, { recursive: true });
    await writeFile(path.join(runDir, "report.pdf"), "%PDF-1.4 test", "utf8");

    const app = createApp();
    const res = await request(app).get(`/report/${runId}`);
    expect(res.status).toBe(200);
    expect(res.headers["content-type"]).toMatch(/application\/pdf/);
    expect(res.headers["content-disposition"]).toContain(runId);
  });
});
