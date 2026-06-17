/* ──────────────────────────────────────────────────────────
 * RunContext — global state for the active run
 * ────────────────────────────────────────────────────────── */
import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type Dispatch,
  type ReactNode,
} from "react";
import type {
  CiUpdateEvent,
  FixAppliedEvent,
  ResultsJson,
  RunCompleteEvent,
  RunStatus,
  RunStatusResponse,
  TelemetryTickEvent,
  ThoughtEvent,
} from "@/types";

// ── State shape ─────────────────────────────────────────────

export interface RunState {
  runId: string | null;
  socketRoom: string | null;
  status: RunStatus;
  currentNode: string;
  iteration: number;
  maxIterations: number;
  progressPct: number;
  thoughts: ThoughtEvent[];
  fixes: FixAppliedEvent[];
  ciEvents: CiUpdateEvent[];
  telemetry: TelemetryTickEvent[];
  results: ResultsJson | null;
  completionEvent: RunCompleteEvent | null;
  error: string | null;
}

const initialState: RunState = {
  runId: null,
  socketRoom: null,
  status: "queued",
  currentNode: "",
  iteration: 0,
  maxIterations: 10,
  progressPct: 0,
  thoughts: [],
  fixes: [],
  ciEvents: [],
  telemetry: [],
  results: null,
  completionEvent: null,
  error: null,
};

// ── Actions ─────────────────────────────────────────────────

type Action =
  | { type: "SET_RUN"; runId: string; socketRoom: string }
  | { type: "SET_STATUS"; payload: RunStatusResponse }
  | { type: "ADD_THOUGHT"; payload: ThoughtEvent }
  | { type: "ADD_FIX"; payload: FixAppliedEvent }
  | { type: "ADD_CI_EVENT"; payload: CiUpdateEvent }
  | { type: "ADD_TELEMETRY"; payload: TelemetryTickEvent }
  | { type: "SET_RESULTS"; payload: ResultsJson }
  | { type: "SET_COMPLETE"; payload: RunCompleteEvent }
  | { type: "SET_ERROR"; error: string }
  | { type: "RESET" };

// ── Dedup helpers (prevent duplicate events from Socket.io re-delivery) ──

function thoughtKey(t: ThoughtEvent): string {
  return `${t.run_id}|${t.node}|${t.step_index}|${t.message}`;
}

function fixKey(f: FixAppliedEvent): string {
  return `${f.run_id}|${f.file}|${f.line}|${f.bug_type}|${f.status}`;
}

function ciKey(c: CiUpdateEvent): string {
  return `${c.run_id}|${c.iteration}|${c.status}|${c.regression}`;
}

function reducer(state: RunState, action: Action): RunState {
  switch (action.type) {
    case "SET_RUN":
      return {
        ...initialState,
        runId: action.runId,
        socketRoom: action.socketRoom,
        status: "queued",
      };

    case "SET_STATUS":
      return {
        ...state,
        status: action.payload.status as RunStatus,
        currentNode: action.payload.current_node,
        iteration: action.payload.iteration,
        maxIterations: action.payload.max_iterations,
        progressPct: action.payload.progress_pct,
      };

    case "ADD_THOUGHT": {
      const key = thoughtKey(action.payload);
      if (state.thoughts.some((t) => thoughtKey(t) === key)) return state;
      return {
        ...state,
        thoughts: [...state.thoughts, action.payload],
        currentNode: action.payload.node,
        status: "running",
      };
    }

    case "ADD_FIX": {
      const key = fixKey(action.payload);
      if (state.fixes.some((f) => fixKey(f) === key)) return state;
      return {
        ...state,
        fixes: [...state.fixes, action.payload],
      };
    }

    case "ADD_CI_EVENT": {
      const key = ciKey(action.payload);
      if (state.ciEvents.some((c) => ciKey(c) === key)) return state;
      return {
        ...state,
        ciEvents: [...state.ciEvents, action.payload],
        iteration: action.payload.iteration,
      };
    }

    case "ADD_TELEMETRY":
      return {
        ...state,
        telemetry: [...state.telemetry, action.payload],
      };

    case "SET_RESULTS":
      return {
        ...state,
        results: action.payload,
        status: action.payload.final_status.toLowerCase() as RunStatus,
        progressPct: 100,
      };

    case "SET_COMPLETE":
      return {
        ...state,
        completionEvent: action.payload,
        status: action.payload.final_status.toLowerCase() as RunStatus,
        progressPct: 100,
      };

    case "SET_ERROR":
      return { ...state, error: action.error, status: "failed" };

    case "RESET":
      return initialState;

    default:
      return state;
  }
}

// ── Context ─────────────────────────────────────────────────

interface RunContextValue {
  state: RunState;
  dispatch: Dispatch<Action>;
  initRun: (runId: string, socketRoom: string) => void;
  reset: () => void;
}

const RunContext = createContext<RunContextValue | null>(null);

export function RunProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const initRun = useCallback(
    (runId: string, socketRoom: string) => {
      dispatch({ type: "SET_RUN", runId, socketRoom });
    },
    [dispatch],
  );

  const reset = useCallback(() => dispatch({ type: "RESET" }), [dispatch]);

  const value = useMemo(
    () => ({ state, dispatch, initRun, reset }),
    [state, dispatch, initRun, reset],
  );

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRunContext(): RunContextValue {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useRunContext must be used within <RunProvider>");
  return ctx;
}
