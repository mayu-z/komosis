/* ──────────────────────────────────────────────────────────
 * DiffViewer — collapsible per-file diff accordion
 *
 * Each file entry is shown as a clickable header that expands
 * to reveal a syntax-coloured unified diff block:
 *   + additions  → green
 *   - deletions  → red
 *   @@ hunks     → blue
 *   context      → muted grey
 * ────────────────────────────────────────────────────────── */
import { useState } from "react";
import { useRunContext } from "@/context/RunContext";
import Card from "@/components/Card";
import type { DiffEntry } from "@/types";

// ── Diff line coloriser ──────────────────────────────────────

function diffLineColor(line: string): string {
  if (line.startsWith("+") && !line.startsWith("+++")) return "#4ade80"; // green-400
  if (line.startsWith("-") && !line.startsWith("---")) return "#f87171"; // red-400
  if (line.startsWith("@@"))                            return "#60a5fa"; // blue-400
  if (line.startsWith("diff ") || line.startsWith("index ") ||
      line.startsWith("---")   || line.startsWith("+++"))  return "#a1a1aa"; // zinc-400
  return "#d4d4d8"; // zinc-300 — context lines
}

// ── Single file diff block ───────────────────────────────────

function DiffBlock({ diff }: { diff: string }) {
  const lines = diff.split("\n");
  return (
    <pre
      className="text-[11px] font-mono leading-5 overflow-x-auto p-4 rounded-b
        bg-[#0a0a0a] border border-t-0 border-black/20"
      style={{ maxHeight: "420px", overflowY: "auto" }}
    >
      {lines.map((line, i) => (
        <span
          key={i}
          className="block whitespace-pre"
          style={{ color: diffLineColor(line) }}
        >
          {line || " "}
        </span>
      ))}
    </pre>
  );
}

// ── File stat badge ──────────────────────────────────────────

function FileStat({ diff }: { diff: string }) {
  let additions = 0;
  let deletions = 0;
  for (const line of diff.split("\n")) {
    if (line.startsWith("+") && !line.startsWith("+++")) additions++;
    if (line.startsWith("-") && !line.startsWith("---")) deletions++;
  }
  return (
    <span className="flex items-center gap-2 text-[10px] font-mono">
      {additions > 0 && (
        <span className="text-emerald-600">+{additions}</span>
      )}
      {deletions > 0 && (
        <span className="text-red-500">−{deletions}</span>
      )}
    </span>
  );
}

// ── File accordion row ───────────────────────────────────────

function FileRow({ entry, isOpen, onToggle }: {
  entry: DiffEntry;
  isOpen: boolean;
  onToggle: () => void;
}) {
  // Extract a short filename for the label, keep full path in tooltip
  const parts = entry.file.replace(/\\/g, "/").split("/");
  const shortName = parts[parts.length - 1];
  const dirPart   = parts.slice(0, -1).join("/");

  return (
    <div className="rounded border border-black/10 overflow-hidden">
      {/* Header row */}
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between gap-3
          px-3 py-2.5 bg-[var(--color-surface-2)]
          hover:bg-zinc-100 transition-colors text-left"
        title={entry.file}
      >
        <div className="flex items-center gap-2 min-w-0">
          {/* Folder icon */}
          <svg
            className="w-3.5 h-3.5 flex-shrink-0 text-zinc-400"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"
            />
          </svg>
          <div className="min-w-0">
            {dirPart && (
              <span className="text-[10px] text-[var(--color-text-muted)] block truncate">
                {dirPart}/
              </span>
            )}
            <span className="text-xs font-mono font-medium text-[var(--color-text)]">
              {shortName}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <FileStat diff={entry.diff} />
          <span className="text-[10px] text-[var(--color-text-muted)]">
            {isOpen ? "▲" : "▼"}
          </span>
        </div>
      </button>

      {/* Diff content */}
      {isOpen && <DiffBlock diff={entry.diff} />}
    </div>
  );
}

// ── Component ────────────────────────────────────────────────

export default function DiffViewer() {
  const { state } = useRunContext();
  const { diffs } = state;

  // Open the first file by default
  const [openFile, setOpenFile] = useState<string | null>(
    diffs[0]?.file ?? null,
  );

  if (!diffs.length) return null;

  const toggle = (file: string) =>
    setOpenFile((prev) => (prev === file ? null : file));

  return (
    <Card
      title="Changes Made"
      subtitle={`${diffs.length} file${diffs.length === 1 ? "" : "s"} modified on this branch`}
    >
      <div className="space-y-2">
        {diffs.map((entry) => (
          <FileRow
            key={entry.file}
            entry={entry}
            isOpen={openFile === entry.file}
            onToggle={() => toggle(entry.file)}
          />
        ))}
      </div>
    </Card>
  );
}
