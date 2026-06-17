/* ──────────────────────────────────────────────────────────
 * ACCEPTANCE TEST: Compliance Rules
 *
 * Covers ACCEPTANCE_TESTS.md §1-§2:
 *   1.1 Branch name format
 *   1.2 Commit prefix [AI-AGENT]
 *   1.3 Protected branch block
 *   2.  Required bug type mapping
 * ────────────────────────────────────────────────────────── */
import { describe, expect, it } from "vitest";
import { formatBranchName } from "../src/branch.js";
import {
  assertNonProtectedTargetBranch,
  ensureCommitPrefix,
  normalizeBugType,
} from "../src/compliance.js";

// ── §1.1 Branch name format ─────────────────────────────────

describe("§1.1 branch name format", () => {
  it("formats canonical sample: RIFT ORGANISERS + Saiyam Kumar", () => {
    expect(formatBranchName("RIFT ORGANISERS", "Saiyam Kumar")).toBe(
      "RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix",
    );
  });

  it("normalizes to uppercase", () => {
    expect(formatBranchName("team alpha", "jane doe")).toBe(
      "TEAM_ALPHA_JANE_DOE_AI_Fix",
    );
  });

  it("replaces spaces with underscores", () => {
    expect(formatBranchName("Code Warriors", "John Smith")).toBe(
      "CODE_WARRIORS_JOHN_SMITH_AI_Fix",
    );
  });

  it("strips non-alphanumeric characters except underscore", () => {
    expect(formatBranchName("RIFT@2026!", "Leader#1")).toBe(
      "RIFT2026_LEADER1_AI_Fix",
    );
  });

  it("handles multiple consecutive spaces", () => {
    expect(formatBranchName("Team   Name", "Lead   Name")).toBe(
      "TEAM_NAME_LEAD_NAME_AI_Fix",
    );
  });

  it("always ends with _AI_Fix suffix (exact case)", () => {
    const branch = formatBranchName("ANY TEAM", "ANY LEADER");
    expect(branch.endsWith("_AI_Fix")).toBe(true);
  });

  it("throws on empty normalized inputs", () => {
    expect(() => formatBranchName("***", "$$$")).toThrow();
    expect(() => formatBranchName("", "")).toThrow();
  });
});

// ── §1.2 Commit prefix ─────────────────────────────────────

describe("§1.2 commit message prefix", () => {
  it("accepts message starting with [AI-AGENT]", () => {
    expect(ensureCommitPrefix("[AI-AGENT] fix missing colon")).toBe(
      "[AI-AGENT] fix missing colon",
    );
  });

  it("accepts [AI-AGENT] with no space after", () => {
    expect(ensureCommitPrefix("[AI-AGENT]fix")).toBe("[AI-AGENT]fix");
  });

  it("rejects message without prefix", () => {
    expect(() => ensureCommitPrefix("fix parser")).toThrow();
  });

  it("rejects empty message", () => {
    expect(() => ensureCommitPrefix("")).toThrow();
  });

  it("rejects whitespace-only message", () => {
    expect(() => ensureCommitPrefix("   ")).toThrow();
  });

  it("is case-sensitive (must be exactly [AI-AGENT])", () => {
    expect(() => ensureCommitPrefix("[ai-agent] fix")).toThrow();
  });
});

// ── §1.3 Protected branch block ────────────────────────────

describe("§1.3 protected branch block", () => {
  it("blocks push to main", () => {
    expect(() => assertNonProtectedTargetBranch("main")).toThrow();
  });

  it("blocks push to master", () => {
    expect(() => assertNonProtectedTargetBranch("master")).toThrow();
  });

  it("blocks push to Main (case insensitive)", () => {
    expect(() => assertNonProtectedTargetBranch("Main")).toThrow();
  });

  it("blocks push to MASTER (case insensitive)", () => {
    expect(() => assertNonProtectedTargetBranch("MASTER")).toThrow();
  });

  it("allows push to feature branch", () => {
    expect(() =>
      assertNonProtectedTargetBranch("RIFT_ORGANISERS_SAIYAM_KUMAR_AI_Fix"),
    ).not.toThrow();
  });

  it("allows push to any non-protected branch", () => {
    expect(() => assertNonProtectedTargetBranch("feature/ai-fix")).not.toThrow();
    expect(() => assertNonProtectedTargetBranch("dev")).not.toThrow();
  });
});

// ── §2 Required bug type mapping ────────────────────────────

describe("§2 required bug type normalization", () => {
  it("normalizes all 6 required types to uppercase canonical form", () => {
    expect(normalizeBugType("linting")).toBe("LINTING");
    expect(normalizeBugType("syntax")).toBe("SYNTAX");
    expect(normalizeBugType("logic")).toBe("LOGIC");
    expect(normalizeBugType("type_error")).toBe("TYPE_ERROR");
    expect(normalizeBugType("import")).toBe("IMPORT");
    expect(normalizeBugType("indentation")).toBe("INDENTATION");
  });

  it("accepts already-uppercase canonical forms", () => {
    expect(normalizeBugType("LINTING")).toBe("LINTING");
    expect(normalizeBugType("SYNTAX")).toBe("SYNTAX");
    expect(normalizeBugType("LOGIC")).toBe("LOGIC");
    expect(normalizeBugType("TYPE_ERROR")).toBe("TYPE_ERROR");
    expect(normalizeBugType("IMPORT")).toBe("IMPORT");
    expect(normalizeBugType("INDENTATION")).toBe("INDENTATION");
  });

  it("resolves common aliases to canonical types", () => {
    expect(normalizeBugType("lint")).toBe("LINTING");
    expect(normalizeBugType("style")).toBe("LINTING");
    expect(normalizeBugType("format")).toBe("LINTING");
    expect(normalizeBugType("parse")).toBe("SYNTAX");
    expect(normalizeBugType("compilation")).toBe("SYNTAX");
    expect(normalizeBugType("runtime")).toBe("LOGIC");
    expect(normalizeBugType("semantic")).toBe("LOGIC");
    expect(normalizeBugType("type")).toBe("TYPE_ERROR");
    expect(normalizeBugType("types")).toBe("TYPE_ERROR");
    expect(normalizeBugType("typing")).toBe("TYPE_ERROR");
    expect(normalizeBugType("module")).toBe("IMPORT");
    expect(normalizeBugType("dependency")).toBe("IMPORT");
    expect(normalizeBugType("whitespace")).toBe("INDENTATION");
    expect(normalizeBugType("indent")).toBe("INDENTATION");
  });

  it("returns null for unknown/unsupported types", () => {
    expect(normalizeBugType("security")).toBeNull();
    expect(normalizeBugType("performance")).toBeNull();
    expect(normalizeBugType("")).toBeNull();
  });
});
