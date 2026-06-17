/* ──────────────────────────────────────────────────────────
 * §11.4 — Fixes Applied Table
 * file, bug_type, line, commit_message, status
 * ────────────────────────────────────────────────────────── */
import { useRunContext } from "@/context/RunContext";
import Card from "@/components/Card";
import StatusBadge from "@/components/StatusBadge";
import type { FixAppliedEvent, ResultFixRow } from "@/types";

export default function FixesAppliedTable() {
  const { state } = useRunContext();

  // Merge real-time socket fixes with final results
  const resultFixes: ResultFixRow[] = state.results?.fixes ?? [];
  const liveFixes: FixAppliedEvent[] = state.fixes;

  const hasData = resultFixes.length > 0 || liveFixes.length > 0;

  return (
    <Card title="Fixes Applied">
      {!hasData ? (
        <div className="flex items-center justify-center h-32 text-sm text-[var(--color-text-muted)]">
          No fixes applied yet.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-text-muted)]">
                <th className="pb-2 pr-3 font-medium">File</th>
                <th className="pb-2 pr-3 font-medium">Bug Type</th>
                <th className="pb-2 pr-3 font-medium text-right">Line</th>
                <th className="pb-2 pr-3 font-medium">Message</th>
                <th className="pb-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]/50">
              {/* Results fixes (from results.json) */}
              {resultFixes.map((fix, i) => (
                <tr key={`r-${i}`} className="hover:bg-[var(--color-surface-2)] transition-colors">
                  <td className="py-2 pr-3">
                    <span className="font-mono text-xs truncate max-w-[200px] inline-block">{fix.file}</span>
                  </td>
                  <td className="py-2 pr-3">
                    <span className="bg-[var(--color-surface-2)] border border-black/10 px-1.5 py-0.5 text-xs font-mono">
                      {fix.bug_type}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-xs">{fix.line_number}</td>
                  <td className="py-2 pr-3 text-xs truncate max-w-[250px]">{fix.commit_message}</td>
                  <td className="py-2">
                    <StatusBadge status={fix.status} />
                  </td>
                </tr>
              ))}

              {/* Live fixes (from socket events, only if no results yet) */}
              {resultFixes.length === 0 &&
                liveFixes.map((fix, i) => (
                  <tr key={`l-${i}`} className="hover:bg-[var(--color-surface-2)] transition-colors">
                    <td className="py-2 pr-3">
                      <span className="font-mono text-xs truncate max-w-[200px] inline-block">{fix.file}</span>
                    </td>
                    <td className="py-2 pr-3">
                      <span className="bg-[var(--color-surface-2)] border border-black/10 px-1.5 py-0.5 text-xs font-mono">
                        {fix.bug_type}
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-right font-mono text-xs">{fix.line}</td>
                    <td className="py-2 pr-3 text-xs">
                      {fix.commit_sha ? (
                        <span className="font-mono">{fix.commit_sha.slice(0, 8)}</span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2">
                      <StatusBadge status={fix.status} />
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>

          {/* Summary footer */}
          {resultFixes.length > 0 && (
            <div className="mt-3 pt-3 border-t border-[var(--color-border)] flex items-center gap-4 text-xs text-[var(--color-text-muted)]">
              <span>
                Total: <strong className="text-[var(--color-text)]">{resultFixes.length}</strong>
              </span>
              <span>
                Fixed:{" "}
                <strong className="text-emerald-700">
                  {resultFixes.filter((f) => f.status === "FIXED").length}
                </strong>
              </span>
              <span>
                Failed:{" "}
                <strong className="text-red-700">
                  {resultFixes.filter((f) => f.status === "FAILED").length}
                </strong>
              </span>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
