/* ──────────────────────────────────────────────────────────
 * API client — wraps all Gateway REST endpoints
 * ────────────────────────────────────────────────────────── */
import type {
  ErrorEnvelope,
  ReplayResponse,
  ResultsJson,
  RunAgentDuplicateResponse,
  RunAgentRequest,
  RunAgentResponse,
  RunStatusResponse,
} from "@/types";

function normalizeApiBase(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "/api";

  const withoutTrailingSlash = trimmed.replace(/\/+$/, "");
  if (/^https?:\/\//i.test(withoutTrailingSlash)) return withoutTrailingSlash;
  if (withoutTrailingSlash.startsWith("/")) return withoutTrailingSlash;
  return `/${withoutTrailingSlash}`;
}

const BASE = normalizeApiBase(import.meta.env.VITE_API_BASE_URL ?? "/api");

// ── Helpers ─────────────────────────────────────────────────

class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.ok) return res.json() as Promise<T>;

  let envelope: ErrorEnvelope | null = null;
  try {
    envelope = (await res.json()) as ErrorEnvelope;
  } catch {
    // not JSON
  }

  throw new ApiError(
    res.status,
    envelope?.error.code ?? "UNKNOWN",
    envelope?.error.message ?? res.statusText,
    envelope?.error.details,
  );
}

// ── Public API ──────────────────────────────────────────────

export async function startRun(
  payload: RunAgentRequest,
): Promise<RunAgentResponse | RunAgentDuplicateResponse> {
  const res = await fetch(`${BASE}/run-agent`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (res.status === 409) {
    return res.json() as Promise<RunAgentDuplicateResponse>;
  }

  return handleResponse<RunAgentResponse>(res);
}

export async function getRunStatus(runId: string): Promise<RunStatusResponse> {
  const res = await fetch(`${BASE}/agent/status/${encodeURIComponent(runId)}`);
  return handleResponse<RunStatusResponse>(res);
}

export async function getResults(runId: string): Promise<ResultsJson> {
  const res = await fetch(`${BASE}/results/${encodeURIComponent(runId)}`);
  return handleResponse<ResultsJson>(res);
}

export async function getReplay(runId: string): Promise<ReplayResponse> {
  const res = await fetch(`${BASE}/replay/${encodeURIComponent(runId)}`);
  return handleResponse<ReplayResponse>(res);
}

export function getReportUrl(runId: string): string {
  return `${BASE}/report/${encodeURIComponent(runId)}`;
}

export async function askAgent(
  runId: string,
  question: string,
): Promise<{ answer: string }> {
  const res = await fetch(`${BASE}/agent/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, question }),
  });
  return handleResponse<{ answer: string }>(res);
}

export { ApiError };
