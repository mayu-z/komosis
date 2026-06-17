/* ──────────────────────────────────────────────────────────
 * §11.5 — CI/CD Status Timeline
 * iteration, status, timestamp, regression indicators
 * ────────────────────────────────────────────────────────── */
import { useRunContext } from "@/context/RunContext";
import Card from "@/components/Card";
import StatusBadge from "@/components/StatusBadge";
import type { CiUpdateEvent, ResultCiRow } from "@/types";

function ciStatusLabel(status: string) {
  switch (status) {
    case "passed":
      return "PASS";
    case "failed":
      return "FAIL";
    case "running":
      return "RUN";
    default:
      return "PEND";
  }
}

export default function CiTimelinePanel() {
  const { state } = useRunContext();

  // Merge final results with live events
  const resultCi: ResultCiRow[] = state.results?.ci_log ?? [];
  const liveCi: CiUpdateEvent[] = state.ciEvents;

  const items = resultCi.length > 0 ? resultCi : liveCi;

  return (
    <Card title="CI/CD Timeline">
      {items.length === 0 ? (
        <div className="flex items-center justify-center h-32 text-sm text-[var(--color-text-muted)]">
          No CI events yet.
        </div>
      ) : (
        <div className="space-y-0">
          {items.map((item, i) => {
            const isLast = i === items.length - 1;
            const regression = "regression" in item ? item.regression : false;
            const ts = "timestamp" in item ? item.timestamp : "";

            return (
              <div key={`ci-${item.iteration}-${i}`} className="flex items-stretch gap-3">
                {/* Timeline connector */}
                <div className="flex flex-col items-center w-6">
                  <div className="flex-shrink-0 text-[9px] font-mono text-[var(--color-text-muted)] border border-black/10 px-1 py-0.5 bg-white">
                    {ciStatusLabel(item.status)}
                  </div>
                  {!isLast && (
                    <div className="flex-1 w-px bg-[var(--color-border)] my-1" />
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 pb-4">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">Iteration {item.iteration}</span>
                    <StatusBadge status={item.status} />
                    {regression && (
                      <span className="inline-flex items-center gap-1 border border-orange-300 bg-orange-100 px-2 py-0.5 text-[10px] font-medium text-orange-700">
                        Regression
                      </span>
                    )}
                  </div>
                  {ts && (
                    <time className="text-[10px] text-[var(--color-text-muted)] mt-0.5 block">
                      {new Date(ts).toLocaleString()}
                    </time>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
