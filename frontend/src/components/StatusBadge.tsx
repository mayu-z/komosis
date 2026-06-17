/* ──────────────────────────────────────────────────────────
 * StatusBadge — colored pill for run/ci status
 * ────────────────────────────────────────────────────────── */
import { cn } from "@/lib/utils";

const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
  queued:       { bg: "bg-amber-100 border border-amber-300", text: "text-amber-700", label: "Queued" },
  running:      { bg: "bg-zinc-100 border border-zinc-300",   text: "text-zinc-700",   label: "Running" },
  passed:       { bg: "bg-emerald-100 border border-emerald-300",  text: "text-emerald-700",  label: "Passed" },
  failed:       { bg: "bg-red-100 border border-red-300",    text: "text-red-700",    label: "Failed" },
  quarantined:  { bg: "bg-orange-100 border border-orange-300", text: "text-orange-700", label: "Quarantined" },
  pending:      { bg: "bg-zinc-100 border border-zinc-300",   text: "text-zinc-700",   label: "Pending" },
  applied:      { bg: "bg-emerald-100 border border-emerald-300",  text: "text-emerald-700",  label: "Applied" },
  rolled_back:  { bg: "bg-orange-100 border border-orange-300", text: "text-orange-700", label: "Rolled Back" },
  skipped:      { bg: "bg-zinc-100 border border-zinc-300",   text: "text-zinc-700",   label: "Skipped" },
  FIXED:        { bg: "bg-emerald-100 border border-emerald-300",  text: "text-emerald-700",  label: "Fixed" },
  FAILED:       { bg: "bg-red-100 border border-red-300",    text: "text-red-700",    label: "Failed" },
  PASSED:       { bg: "bg-emerald-100 border border-emerald-300",  text: "text-emerald-700",  label: "Passed" },
  QUARANTINED:  { bg: "bg-orange-100 border border-orange-300", text: "text-orange-700", label: "Quarantined" },
};

interface StatusBadgeProps {
  status: string;
  className?: string;
  pulse?: boolean;
}

export default function StatusBadge({ status, className, pulse }: StatusBadgeProps) {
  const cfg = statusConfig[status] ?? {
    bg: "bg-zinc-100 border border-zinc-300",
    text: "text-zinc-700",
    label: status,
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 text-xs font-medium",
        cfg.bg,
        cfg.text,
        className,
      )}
    >
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-35" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-current" />
        </span>
      )}
      {cfg.label}
    </span>
  );
}
