/* ──────────────────────────────────────────────────────────
 * Card — reusable surface card
 * ────────────────────────────────────────────────────────── */
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface CardProps {
  title?: string;
  subtitle?: string;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  glow?: "running" | "passed" | "failed" | null;
}

export default function Card({ title, subtitle, icon, children, className, glow }: CardProps) {
  const glowCls =
    glow === "running"
      ? "status-glow-running"
      : glow === "passed"
        ? "status-glow-passed"
        : glow === "failed"
          ? "status-glow-failed"
          : "";

  return (
    <div
      className={cn(
        "border border-black/10 bg-white/95 p-5 shadow-[0_12px_30px_rgba(10,10,10,0.06)]",
        glowCls,
        className,
      )}
    >
      {(title || icon) && (
        <div className="flex items-center gap-2 mb-4 border-b border-black/10 pb-3">
          {icon}
          <div>
            {title && <h3 className="text-sm font-semibold tracking-tight">{title}</h3>}
            {subtitle && (
              <p className="text-xs text-[var(--color-text-muted)]">{subtitle}</p>
            )}
          </div>
        </div>
      )}
      {children}
    </div>
  );
}
