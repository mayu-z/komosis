/* ──────────────────────────────────────────────────────────
 * usePolling — polls run status until terminal state
 * ────────────────────────────────────────────────────────── */
import { useEffect, useRef } from "react";
import { getRunStatus, getResults } from "@/lib/api";
import { useRunContext } from "@/context/RunContext";

const TERMINAL_STATES = new Set(["passed", "failed", "quarantined"]);
const POLL_INTERVAL = 3_000;

export function usePolling(runId: string | null): void {
  const { state, dispatch } = useRunContext();
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!runId) return;

    const poll = async () => {
      try {
        const status = await getRunStatus(runId);
        dispatch({ type: "SET_STATUS", payload: status });

        if (TERMINAL_STATES.has(status.status)) {
          // Fetch full results
          try {
            const results = await getResults(runId);
            dispatch({ type: "SET_RESULTS", payload: results });
          } catch {
            // results.json may not be ready yet — ignore
          }

          // Stop polling
          if (timer.current) {
            clearInterval(timer.current);
            timer.current = null;
          }
        }
      } catch (err) {
        console.error("[polling] error:", err);
      }
    };

    // Initial poll
    void poll();

    // Set interval
    timer.current = setInterval(() => void poll(), POLL_INTERVAL);

    return () => {
      if (timer.current) {
        clearInterval(timer.current);
        timer.current = null;
      }
    };
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps
}
