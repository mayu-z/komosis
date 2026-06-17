/* ──────────────────────────────────────────────────────────
 * §11.3 — Score Breakdown Panel
 * base, speed_bonus, efficiency_penalty, total (visual)
 * ────────────────────────────────────────────────────────── */
import { useRunContext } from "@/context/RunContext";
import Card from "@/components/Card";
import ScoreGauge from "@/components/ScoreGauge";

export default function ScoreBreakdownPanel() {
  const { state } = useRunContext();
  const score = state.results?.score ?? state.completionEvent?.score ?? null;

  if (!score) {
    return (
      <Card title="Score Breakdown">
        <div className="flex items-center justify-center h-40 text-sm text-[var(--color-text-muted)]">
          Score will appear when the run completes.
        </div>
      </Card>
    );
  }

  const rows = [
    {
      label: "Base Score",
      value: score.base,
      tone: "text-zinc-700 bg-zinc-100 border-zinc-300",
    },
    {
      label: "Speed Bonus",
      value: score.speed_bonus,
      tone: "text-emerald-700 bg-emerald-100 border-emerald-300",
      prefix: "+",
    },
    {
      label: "Efficiency Penalty",
      value: score.efficiency_penalty,
      tone: "text-red-700 bg-red-100 border-red-300",
      prefix: score.efficiency_penalty <= 0 ? "" : "-",
    },
  ];

  return (
    <Card title="Score Breakdown">
      <div className="flex items-center gap-6">
        {/* Gauge */}
        <ScoreGauge total={score.total} />

        {/* Breakdown table */}
        <div className="flex-1 space-y-3">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-mono uppercase px-1.5 py-0.5 border ${r.tone}`}>
                  {r.label}
                </span>
              </div>
              <span className="font-mono font-semibold">
                {r.prefix ?? ""}
                {r.value.toFixed(1)}
              </span>
            </div>
          ))}

          <div className="border-t border-[var(--color-border)] pt-2 flex items-center justify-between text-sm">
            <span className="font-semibold">Total</span>
            <span className="font-mono font-bold text-lg">{score.total.toFixed(1)}</span>
          </div>
        </div>
      </div>
    </Card>
  );
}
