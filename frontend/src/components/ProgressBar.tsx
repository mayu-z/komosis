/* ──────────────────────────────────────────────────────────
 * ProgressBar — animated progress indicator
 * ────────────────────────────────────────────────────────── */
import { cn } from "@/lib/utils";

interface ProgressBarProps {
  value: number;       // 0–100
  className?: string;
  showLabel?: boolean;
}

export default function ProgressBar({ value, className, showLabel = true }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value));

  return (
    <div className={cn("w-full", className)}>
      {showLabel && (
        <div className="flex justify-between text-xs text-[var(--color-text-muted)] mb-1">
          <span>Progress</span>
          <span>{Math.round(clamped)}%</span>
        </div>
      )}
      <div className="h-2 bg-[var(--color-surface-2)] overflow-hidden border border-black/10">
        <div
          className="h-full bg-gradient-to-r from-slate-900 to-slate-700 transition-all duration-500 ease-out"
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
