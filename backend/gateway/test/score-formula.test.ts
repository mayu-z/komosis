/* ──────────────────────────────────────────────────────────
 * ACCEPTANCE TEST: Score Formula (SOURCE_OF_TRUTH §12)
 *
 * base: 100
 * speed_bonus: +10 if total_time_secs < 300
 * efficiency_penalty: -2 × max(0, commits - 20)
 * total: base + speed_bonus - efficiency_penalty (clamped >= 0)
 * ────────────────────────────────────────────────────────── */
import { describe, expect, it } from "vitest";
import { schemaValidators } from "../src/validators.js";

/* Score formula pure implementation (mirrors agent scorer.py) */
function computeScore(totalTimeSecs: number, totalCommits: number) {
  const base = 100;
  const speed_bonus = totalTimeSecs < 300 ? 10 : 0;
  const efficiency_penalty = 2 * Math.max(0, totalCommits - 20);
  const total = Math.max(0, base + speed_bonus - efficiency_penalty);
  return { base, speed_bonus, efficiency_penalty, total };
}

/* Helper: build a minimal results.json for schema validation */
function buildResults(totalTimeSecs: number, totalCommits: number, overrides: Record<string, unknown> = {}) {
  const score = computeScore(totalTimeSecs, totalCommits);
  return {
    run_id: "run_score_test",
    repo_url: "https://github.com/org/repo",
    team_name: "RIFT ORGANISERS",
    leader_name: "Saiyam Kumar",
    branch_name: "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
    final_status: "PASSED",
    total_failures: 1,
    total_fixes: 1,
    total_time_secs: totalTimeSecs,
    score,
    fixes: [
      {
        file: "src/app.py",
        bug_type: "SYNTAX",
        line_number: 10,
        commit_message: "[AI-AGENT] fix syntax error",
        status: "FIXED",
      },
    ],
    ci_log: [
      {
        iteration: 1,
        status: "passed",
        timestamp: "2026-02-19T10:05:12Z",
        regression: false,
      },
    ],
    ...overrides,
  };
}

describe("§12 score formula", () => {
  // ── Speed bonus ────────────────────────────────────────
  it("awards +10 speed bonus when runtime < 300s", () => {
    const score = computeScore(200, 5);
    expect(score.speed_bonus).toBe(10);
    expect(score.total).toBe(110);
  });

  it("awards +10 speed bonus at 299s", () => {
    const score = computeScore(299, 0);
    expect(score.speed_bonus).toBe(10);
    expect(score.total).toBe(110);
  });

  it("does NOT award speed bonus at exactly 300s", () => {
    const score = computeScore(300, 0);
    expect(score.speed_bonus).toBe(0);
    expect(score.total).toBe(100);
  });

  it("does NOT award speed bonus when runtime > 300s", () => {
    const score = computeScore(600, 0);
    expect(score.speed_bonus).toBe(0);
    expect(score.total).toBe(100);
  });

  // ── Efficiency penalty ─────────────────────────────────
  it("applies no penalty for <= 20 commits", () => {
    const score = computeScore(200, 20);
    expect(score.efficiency_penalty).toBe(0);
    expect(score.total).toBe(110);
  });

  it("applies -2 per excess commit above 20", () => {
    const score = computeScore(200, 25);
    expect(score.efficiency_penalty).toBe(10);
    expect(score.total).toBe(100); // 100 + 10 - 10
  });

  it("applies -2 per excess commit for 21 commits (1 extra)", () => {
    const score = computeScore(400, 21);
    expect(score.efficiency_penalty).toBe(2);
    expect(score.total).toBe(98); // 100 + 0 - 2
  });

  it("applies correct penalty for 30 commits", () => {
    const score = computeScore(400, 30);
    expect(score.efficiency_penalty).toBe(20);
    expect(score.total).toBe(80);
  });

  // ── Floor at zero ──────────────────────────────────────
  it("clamps total score to 0 (never negative)", () => {
    const score = computeScore(600, 100);
    // penalty = 2 * (100 - 20) = 160, total = 100 + 0 - 160 = -60 → 0
    expect(score.efficiency_penalty).toBe(160);
    expect(score.total).toBe(0);
  });

  // ── Combined ───────────────────────────────────────────
  it("combines speed bonus with penalty correctly", () => {
    const score = computeScore(150, 22);
    // base 100, speed +10, penalty 2*2=4, total=106
    expect(score.total).toBe(106);
  });

  it("zero commits, fast run = 110", () => {
    const score = computeScore(10, 0);
    expect(score.total).toBe(110);
  });

  // ── Schema validation on resulting payload ─────────────
  it("produces valid results.json with speed bonus", () => {
    const results = buildResults(200, 5);
    expect(schemaValidators.results(results)).toBe(true);
    expect(results.score.total).toBe(110);
  });

  it("produces valid results.json with high commit penalty", () => {
    const results = buildResults(400, 50);
    expect(schemaValidators.results(results)).toBe(true);
    expect(results.score.total).toBe(40); // 100 + 0 - 60
  });
});

describe("§9 performance thresholds", () => {
  it("runtime under 5 minutes yields speed bonus", () => {
    const score = computeScore(299, 10);
    expect(score.speed_bonus).toBe(10);
  });

  it("commit count over 20 applies penalty exactly as specified", () => {
    const score = computeScore(400, 25);
    // exactly -2 * max(0, 25-20) = -10
    expect(score.efficiency_penalty).toBe(10);
  });
});
