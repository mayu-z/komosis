/* ──────────────────────────────────────────────────────────
 * Frontend type definitions — mirrors @rift/contracts
 * ────────────────────────────────────────────────────────── */

export type RunStatus = "queued" | "running" | "passed" | "failed" | "quarantined";

export type BugType = "LINTING" | "SYNTAX" | "LOGIC" | "TYPE_ERROR" | "IMPORT" | "INDENTATION";

export type FinalStatus = "PASSED" | "FAILED" | "QUARANTINED";

export type CiStatus = "passed" | "failed" | "running" | "pending";

export type FixEventStatus = "applied" | "failed" | "rolled_back" | "skipped";

// ── Request / Response ──────────────────────────────────────

export interface RunAgentRequest {
  repo_url: string;
  team_name: string;
  leader_name: string;
  requested_ref?: string;
}

export interface RunAgentResponse {
  run_id: string;
  branch_name: string;
  status: "queued";
  socket_room: string;
  fingerprint: string;
}

export interface RunAgentDuplicateResponse {
  run_id: string;
  status: "queued" | "running";
  message: string;
}

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

// ── Score ────────────────────────────────────────────────────

export interface ScoreBreakdown {
  base: number;
  speed_bonus: number;
  efficiency_penalty: number;
  total: number;
}

// ── Results ─────────────────────────────────────────────────

export interface ResultFixRow {
  file: string;
  bug_type: BugType;
  line_number: number;
  commit_message: string;
  status: "FIXED" | "FAILED";
}

export interface ResultCiRow {
  iteration: number;
  status: CiStatus;
  timestamp: string;
  regression: boolean;
}

export interface ResultsJson {
  run_id: string;
  repo_url: string;
  team_name: string;
  leader_name: string;
  branch_name: string;
  final_status: FinalStatus;
  total_failures: number;
  total_fixes: number;
  total_time_secs: number;
  score: ScoreBreakdown;
  fixes: ResultFixRow[];
  ci_log: ResultCiRow[];
}

// ── Socket Events ───────────────────────────────────────────

export interface ThoughtEvent {
  run_id: string;
  node: string;
  message: string;
  step_index: number;
  timestamp: string;
}

export interface FixAppliedEvent {
  run_id: string;
  file: string;
  bug_type: BugType;
  line: number;
  status: FixEventStatus;
  confidence: number;
  commit_sha?: string;
}

export interface CiUpdateEvent {
  run_id: string;
  iteration: number;
  status: CiStatus;
  regression: boolean;
  timestamp: string;
}

export interface TelemetryTickEvent {
  run_id: string;
  container_id: string;
  cpu_pct: number;
  mem_mb: number;
  timestamp: string;
}

export interface RunCompleteEvent {
  run_id: string;
  final_status: FinalStatus;
  score: ScoreBreakdown;
  total_time_secs: number;
  pdf_url: string;
}

// ── Status endpoint ─────────────────────────────────────────

export interface RunStatusResponse {
  run_id: string;
  status: RunStatus | string;
  current_node: string;
  iteration: number;
  max_iterations: number;
  progress_pct: number;
}

// ── Replay ──────────────────────────────────────────────────

export interface ReplayEvent {
  step_index: number;
  agent_node: string;
  action_type: string;
  action_label: string;
  payload: Record<string, unknown>;
  emitted_at: string;
}

export interface ReplayResponse {
  run_id: string;
  events: ReplayEvent[];
}
