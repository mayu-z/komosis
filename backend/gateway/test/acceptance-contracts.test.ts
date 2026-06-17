/* ──────────────────────────────────────────────────────────
 * ACCEPTANCE TEST: Comprehensive Contract Validation
 *
 * Covers ACCEPTANCE_TESTS.md §4 (API contracts) & §5 (event
 * contracts) — exhaustive accept/reject for all 10 schemas.
 * ────────────────────────────────────────────────────────── */
import { describe, expect, it } from "vitest";
import { schemaValidators } from "../src/validators.js";

// ── Helper: canonical payloads ──────────────────────────────

const CANONICAL_THOUGHT: Record<string, unknown> = {
  run_id: "run_abc123",
  node: "fix_generator",
  message: "Rule path failed, switching to model route",
  step_index: 92,
  timestamp: "2026-02-19T10:03:02Z",
};

const CANONICAL_FIX_APPLIED: Record<string, unknown> = {
  run_id: "run_abc123",
  file: "src/validator.py",
  bug_type: "SYNTAX",
  line: 8,
  status: "applied",
  confidence: 0.91,
  commit_sha: "abc123def",
};

const CANONICAL_CI_UPDATE: Record<string, unknown> = {
  run_id: "run_abc123",
  iteration: 2,
  status: "failed",
  regression: true,
  timestamp: "2026-02-19T10:05:12Z",
};

const CANONICAL_TELEMETRY: Record<string, unknown> = {
  run_id: "run_abc123",
  container_id: "c1",
  cpu_pct: 42.3,
  mem_mb: 312,
  timestamp: "2026-02-19T10:05:13Z",
};

const CANONICAL_RUN_COMPLETE: Record<string, unknown> = {
  run_id: "run_abc123",
  final_status: "PASSED",
  score: { base: 100, speed_bonus: 10, efficiency_penalty: 0, total: 110 },
  total_time_secs: 244,
  pdf_url: "/report/run_abc123",
};

const CANONICAL_RESULTS: Record<string, unknown> = {
  run_id: "run_abc123",
  repo_url: "https://github.com/org/repo",
  team_name: "RIFT ORGANISERS",
  leader_name: "Saiyam Kumar",
  branch_name: "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
  final_status: "PASSED",
  total_failures: 2,
  total_fixes: 2,
  total_time_secs: 244,
  score: { base: 100, speed_bonus: 10, efficiency_penalty: 0, total: 110 },
  fixes: [
    {
      file: "src/validator.py",
      bug_type: "SYNTAX",
      line_number: 8,
      commit_message: "[AI-AGENT] fix missing colon",
      status: "FIXED",
    },
  ],
  ci_log: [
    { iteration: 1, status: "passed", timestamp: "2026-02-19T10:05:12Z", regression: false },
  ],
};

const CANONICAL_RUN_AGENT_REQUEST: Record<string, unknown> = {
  repo_url: "https://github.com/org/repo",
  team_name: "RIFT ORGANISERS",
  leader_name: "Saiyam Kumar",
};

const CANONICAL_RUN_AGENT_RESPONSE: Record<string, unknown> = {
  run_id: "run_abc123",
  branch_name: "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
  status: "queued",
  socket_room: "/run/run_abc123",
  fingerprint: "3dc49b0aa7a4648ceee63780f2d0b1477f0f5b8cd86d5914fa66f4ec9baf1910",
};

const CANONICAL_DUPLICATE_RESPONSE: Record<string, unknown> = {
  run_id: "run_abc123",
  status: "running",
  message: "Active run already exists for this submission fingerprint",
};

// ── Tests ───────────────────────────────────────────────────

describe("§4 API contract schema validation", () => {
  describe("run-agent-request schema", () => {
    it("accepts valid request with all required fields", () => {
      expect(schemaValidators.runAgentRequest(CANONICAL_RUN_AGENT_REQUEST)).toBe(true);
    });

    it("accepts request with optional requested_ref", () => {
      expect(
        schemaValidators.runAgentRequest({
          ...CANONICAL_RUN_AGENT_REQUEST,
          requested_ref: "feature/fix-login",
        }),
      ).toBe(true);
    });

    it("rejects request missing repo_url", () => {
      const { repo_url, ...rest } = CANONICAL_RUN_AGENT_REQUEST;
      expect(schemaValidators.runAgentRequest(rest)).toBe(false);
    });

    it("rejects request missing team_name", () => {
      const { team_name, ...rest } = CANONICAL_RUN_AGENT_REQUEST;
      expect(schemaValidators.runAgentRequest(rest)).toBe(false);
    });

    it("rejects request missing leader_name", () => {
      const { leader_name, ...rest } = CANONICAL_RUN_AGENT_REQUEST;
      expect(schemaValidators.runAgentRequest(rest)).toBe(false);
    });

    it("rejects request with invalid repo_url format", () => {
      expect(
        schemaValidators.runAgentRequest({ ...CANONICAL_RUN_AGENT_REQUEST, repo_url: "not-a-url" }),
      ).toBe(false);
    });
  });

  describe("run-agent-response schema", () => {
    it("accepts valid response", () => {
      expect(schemaValidators.runAgentResponse(CANONICAL_RUN_AGENT_RESPONSE)).toBe(true);
    });

    it("rejects response with non-queued status", () => {
      expect(
        schemaValidators.runAgentResponse({ ...CANONICAL_RUN_AGENT_RESPONSE, status: "running" }),
      ).toBe(false);
    });

    it("rejects response missing fingerprint", () => {
      const { fingerprint, ...rest } = CANONICAL_RUN_AGENT_RESPONSE;
      expect(schemaValidators.runAgentResponse(rest)).toBe(false);
    });
  });

  describe("run-agent-duplicate-response schema", () => {
    it("accepts valid duplicate response", () => {
      expect(schemaValidators.runAgentDuplicateResponse(CANONICAL_DUPLICATE_RESPONSE)).toBe(true);
    });

    it("accepts queued status for duplicate", () => {
      expect(
        schemaValidators.runAgentDuplicateResponse({ ...CANONICAL_DUPLICATE_RESPONSE, status: "queued" }),
      ).toBe(true);
    });

    it("rejects duplicate with status = passed", () => {
      expect(
        schemaValidators.runAgentDuplicateResponse({ ...CANONICAL_DUPLICATE_RESPONSE, status: "passed" }),
      ).toBe(false);
    });
  });

  describe("results.json schema", () => {
    it("accepts canonical results", () => {
      expect(schemaValidators.results(CANONICAL_RESULTS)).toBe(true);
    });

    it("accepts all final_status values", () => {
      for (const status of ["PASSED", "FAILED", "QUARANTINED"]) {
        expect(
          schemaValidators.results({ ...CANONICAL_RESULTS, final_status: status }),
        ).toBe(true);
      }
    });

    it("rejects results with lowercase final_status", () => {
      expect(
        schemaValidators.results({ ...CANONICAL_RESULTS, final_status: "passed" }),
      ).toBe(false);
    });

    it("rejects results missing score", () => {
      const { score, ...rest } = CANONICAL_RESULTS;
      expect(schemaValidators.results(rest)).toBe(false);
    });

    it("rejects results missing fixes array", () => {
      const { fixes, ...rest } = CANONICAL_RESULTS;
      expect(schemaValidators.results(rest)).toBe(false);
    });

    it("rejects results missing ci_log array", () => {
      const { ci_log, ...rest } = CANONICAL_RESULTS;
      expect(schemaValidators.results(rest)).toBe(false);
    });

    it("accepts all 6 required bug types in fixes", () => {
      const bugTypes = ["LINTING", "SYNTAX", "LOGIC", "TYPE_ERROR", "IMPORT", "INDENTATION"];
      for (const bt of bugTypes) {
        const results = {
          ...CANONICAL_RESULTS,
          fixes: [
            {
              file: "src/app.py",
              bug_type: bt,
              line_number: 1,
              commit_message: "[AI-AGENT] fix issue",
              status: "FIXED",
            },
          ],
        };
        expect(schemaValidators.results(results)).toBe(true);
      }
    });

    it("rejects fix with invalid bug type", () => {
      const results = {
        ...CANONICAL_RESULTS,
        fixes: [
          {
            file: "src/app.py",
            bug_type: "SECURITY",
            line_number: 1,
            commit_message: "[AI-AGENT] fix issue",
            status: "FIXED",
          },
        ],
      };
      expect(schemaValidators.results(results)).toBe(false);
    });

    it("rejects fix with commit message missing [AI-AGENT] prefix", () => {
      const results = {
        ...CANONICAL_RESULTS,
        fixes: [
          {
            file: "src/app.py",
            bug_type: "SYNTAX",
            line_number: 1,
            commit_message: "fix issue without prefix",
            status: "FIXED",
          },
        ],
      };
      expect(schemaValidators.results(results)).toBe(false);
    });

    it("accepts all ci_log status values", () => {
      for (const st of ["passed", "failed", "running", "pending"]) {
        const results = {
          ...CANONICAL_RESULTS,
          ci_log: [
            { iteration: 1, status: st, timestamp: "2026-02-19T10:00:00Z", regression: false },
          ],
        };
        expect(schemaValidators.results(results)).toBe(true);
      }
    });
  });
});

describe("§5 event contract schema validation", () => {
  describe("thought_event", () => {
    it("accepts canonical payload", () => {
      expect(schemaValidators.thoughtEvent(CANONICAL_THOUGHT)).toBe(true);
    });

    it("rejects missing node", () => {
      const { node, ...rest } = CANONICAL_THOUGHT;
      expect(schemaValidators.thoughtEvent(rest)).toBe(false);
    });

    it("rejects missing step_index", () => {
      const { step_index, ...rest } = CANONICAL_THOUGHT;
      expect(schemaValidators.thoughtEvent(rest)).toBe(false);
    });
  });

  describe("fix_applied", () => {
    it("accepts canonical payload", () => {
      expect(schemaValidators.fixAppliedEvent(CANONICAL_FIX_APPLIED)).toBe(true);
    });

    it("accepts all fix status values", () => {
      for (const s of ["applied", "failed", "rolled_back", "skipped"]) {
        expect(
          schemaValidators.fixAppliedEvent({ ...CANONICAL_FIX_APPLIED, status: s }),
        ).toBe(true);
      }
    });

    it("rejects confidence > 1.0", () => {
      expect(
        schemaValidators.fixAppliedEvent({ ...CANONICAL_FIX_APPLIED, confidence: 1.2 }),
      ).toBe(false);
    });

    it("rejects confidence < 0.0", () => {
      expect(
        schemaValidators.fixAppliedEvent({ ...CANONICAL_FIX_APPLIED, confidence: -0.1 }),
      ).toBe(false);
    });

    it("accepts without optional commit_sha", () => {
      const { commit_sha, ...rest } = CANONICAL_FIX_APPLIED;
      expect(schemaValidators.fixAppliedEvent(rest)).toBe(true);
    });

    it("accepts all 6 required bug types", () => {
      for (const bt of ["LINTING", "SYNTAX", "LOGIC", "TYPE_ERROR", "IMPORT", "INDENTATION"]) {
        expect(
          schemaValidators.fixAppliedEvent({ ...CANONICAL_FIX_APPLIED, bug_type: bt }),
        ).toBe(true);
      }
    });

    it("rejects unknown bug type", () => {
      expect(
        schemaValidators.fixAppliedEvent({ ...CANONICAL_FIX_APPLIED, bug_type: "UNKNOWN" }),
      ).toBe(false);
    });
  });

  describe("ci_update", () => {
    it("accepts canonical payload", () => {
      expect(schemaValidators.ciUpdateEvent(CANONICAL_CI_UPDATE)).toBe(true);
    });

    it("accepts all ci status values", () => {
      for (const s of ["passed", "failed", "running", "pending"]) {
        expect(
          schemaValidators.ciUpdateEvent({ ...CANONICAL_CI_UPDATE, status: s }),
        ).toBe(true);
      }
    });

    it("rejects invalid status", () => {
      expect(
        schemaValidators.ciUpdateEvent({ ...CANONICAL_CI_UPDATE, status: "cancelled" }),
      ).toBe(false);
    });

    it("requires regression boolean", () => {
      const { regression, ...rest } = CANONICAL_CI_UPDATE;
      expect(schemaValidators.ciUpdateEvent(rest)).toBe(false);
    });
  });

  describe("telemetry_tick", () => {
    it("accepts canonical payload", () => {
      expect(schemaValidators.telemetryTickEvent(CANONICAL_TELEMETRY)).toBe(true);
    });

    it("rejects missing container_id", () => {
      const { container_id, ...rest } = CANONICAL_TELEMETRY;
      expect(schemaValidators.telemetryTickEvent(rest)).toBe(false);
    });
  });

  describe("run_complete", () => {
    it("accepts canonical payload", () => {
      expect(schemaValidators.runCompleteEvent(CANONICAL_RUN_COMPLETE)).toBe(true);
    });

    it("accepts all final_status values", () => {
      for (const s of ["PASSED", "FAILED", "QUARANTINED"]) {
        expect(
          schemaValidators.runCompleteEvent({ ...CANONICAL_RUN_COMPLETE, final_status: s }),
        ).toBe(true);
      }
    });

    it("rejects lowercase final_status", () => {
      expect(
        schemaValidators.runCompleteEvent({ ...CANONICAL_RUN_COMPLETE, final_status: "passed" }),
      ).toBe(false);
    });

    it("rejects missing score", () => {
      const { score, ...rest } = CANONICAL_RUN_COMPLETE;
      expect(schemaValidators.runCompleteEvent(rest)).toBe(false);
    });

    it("requires all 4 score fields", () => {
      expect(
        schemaValidators.runCompleteEvent({
          ...CANONICAL_RUN_COMPLETE,
          score: { base: 100 }, // missing speed_bonus, efficiency_penalty, total
        }),
      ).toBe(false);
    });
  });
});
