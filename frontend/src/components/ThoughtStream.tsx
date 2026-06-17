/* ──────────────────────────────────────────────────────────
 * ThoughtStream — scrollable list of thought events
 * ────────────────────────────────────────────────────────── */
import { useEffect, useRef } from "react";
import type { ThoughtEvent } from "@/types";

const nodeTone: Record<string, string> = {
  repo_scanner: "bg-zinc-100 text-zinc-700 border-zinc-300",
  test_runner: "bg-amber-100 text-amber-700 border-amber-300",
  ast_analyzer: "bg-zinc-100 text-zinc-700 border-zinc-300",
  fix_generator: "bg-orange-100 text-orange-700 border-orange-300",
  commit_push: "bg-emerald-100 text-emerald-700 border-emerald-300",
  ci_monitor: "bg-zinc-100 text-zinc-700 border-zinc-300",
  scorer: "bg-zinc-100 text-zinc-700 border-zinc-300",
};

interface ThoughtStreamProps {
  thoughts: ThoughtEvent[];
  maxHeight?: string;
}

export default function ThoughtStream({ thoughts, maxHeight = "320px" }: ThoughtStreamProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [thoughts.length]);

  if (thoughts.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-[var(--color-text-muted)]">
        Waiting for agent thoughts…
      </div>
    );
  }

  return (
    <div className="thought-stream overflow-y-auto space-y-1 pr-1" style={{ maxHeight }}>
      {thoughts.map((t, i) => (
        <div
          key={`${t.step_index}-${i}`}
          className="border border-black/10 px-3 py-2 bg-white hover:bg-[var(--color-surface-2)] transition-colors"
        >
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-center gap-2 text-[10px] text-[var(--color-text-muted)] flex-wrap">
              <span
                className={`font-mono uppercase px-1.5 py-0.5 border ${nodeTone[t.node] ?? "bg-zinc-100 text-zinc-700 border-zinc-300"}`}
              >
                {t.node}
              </span>
              <span>·</span>
              <span>step {t.step_index}</span>
              <span>·</span>
              <time>{new Date(t.timestamp).toLocaleTimeString()}</time>
            </div>
            <p className="text-sm leading-snug text-[var(--color-text)]">{t.message}</p>
          </div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
