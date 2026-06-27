/* ──────────────────────────────────────────────────────────
 * RepoIntelligenceCard — what the agent found & decided
 *
 * Two-column layout:
 *   Left  — language / framework / platform (scanner output)
 *   Right — repo health dots + agent actions taken
 * Bottom — decision path trace in monospace
 * ────────────────────────────────────────────────────────── */
import { useRunContext } from "@/context/RunContext";
import Card from "@/components/Card";

// ── Language colour mapping ──────────────────────────────────

const LANG_COLORS: Record<string, { bg: string; text: string }> = {
  python:     { bg: "#dbeafe", text: "#1d4ed8" },
  typescript: { bg: "#ede9fe", text: "#6d28d9" },
  javascript: { bg: "#fef9c3", text: "#a16207" },
  go:         { bg: "#ccfbf1", text: "#0d9488" },
  java:       { bg: "#ffedd5", text: "#c2410c" },
  rust:       { bg: "#fee2e2", text: "#b91c1c" },
  ruby:       { bg: "#fce7f3", text: "#be185d" },
  csharp:     { bg: "#f0fdf4", text: "#15803d" },
  php:        { bg: "#eff6ff", text: "#2563eb" },
  kotlin:     { bg: "#fdf4ff", text: "#9333ea" },
};

function LanguageBadge({ lang }: { lang: string | null }) {
  const key = (lang ?? "").toLowerCase();
  const colors = LANG_COLORS[key] ?? { bg: "#f4f4f5", text: "#3f3f46" };
  return (
    <span
      className="inline-block text-xs font-semibold px-2.5 py-1 rounded-full"
      style={{ backgroundColor: colors.bg, color: colors.text }}
    >
      {lang ?? "unknown"}
    </span>
  );
}

// ── Health dot ───────────────────────────────────────────────

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full mr-2 flex-shrink-0 mt-0.5"
      style={{ backgroundColor: ok ? "var(--color-success)" : "var(--color-danger)" }}
    />
  );
}

// ── Action chip ──────────────────────────────────────────────

function ActionChip({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium
      px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
      <span>✓</span>
      {label}
    </span>
  );
}

// ── Component ────────────────────────────────────────────────

export default function RepoIntelligenceCard() {
  const { state } = useRunContext();
  const { intelligence } = state;

  if (!intelligence) return null;

  const {
    language, framework, platform,
    has_tests, has_ci, decision_path,
    cicd_generated, tests_generated,
  } = intelligence;

  const noActions = !cicd_generated && !tests_generated;

  return (
    <Card
      title="Repository Intelligence"
      subtitle="What the agent found and decided"
    >
      <div className="grid grid-cols-2 gap-6">

        {/* ── Left: scanner output ─────────────────── */}
        <div className="space-y-4">
          <div>
            <p className="text-[10px] uppercase font-mono tracking-wider
              text-[var(--color-text-muted)] mb-1.5">
              Language
            </p>
            <LanguageBadge lang={language} />
          </div>

          <div>
            <p className="text-[10px] uppercase font-mono tracking-wider
              text-[var(--color-text-muted)] mb-1">
              Test Framework
            </p>
            <span className="text-sm font-medium text-[var(--color-text)]">
              {framework ?? "none detected"}
            </span>
          </div>

          <div>
            <p className="text-[10px] uppercase font-mono tracking-wider
              text-[var(--color-text-muted)] mb-1">
              Deploy Platform
            </p>
            <span className="text-sm font-medium text-[var(--color-text)]">
              {platform ?? "not detected"}
            </span>
          </div>
        </div>

        {/* ── Right: health + actions ───────────────── */}
        <div className="space-y-4">
          <div>
            <p className="text-[10px] uppercase font-mono tracking-wider
              text-[var(--color-text-muted)] mb-2">
              Repo Health
            </p>
            <div className="space-y-1.5">
              <div className="flex items-start text-xs text-[var(--color-text)]">
                <Dot ok={has_tests} />
                Tests {has_tests ? "found" : "not found"}
              </div>
              <div className="flex items-start text-xs text-[var(--color-text)]">
                <Dot ok={has_ci} />
                CI/CD {has_ci ? "exists" : "not found"}
              </div>
            </div>
          </div>

          <div>
            <p className="text-[10px] uppercase font-mono tracking-wider
              text-[var(--color-text-muted)] mb-2">
              Agent Actions
            </p>
            <div className="flex flex-wrap gap-1.5">
              {tests_generated && <ActionChip label="Tests generated" />}
              {cicd_generated  && <ActionChip label="CI/CD generated" />}
              {noActions && (
                <span className="text-xs text-[var(--color-text-muted)]">
                  No generation needed
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Decision path trace ──────────────────────────────── */}
      {decision_path && (
        <div className="mt-5 pt-4 border-t border-black/8">
          <p className="text-[10px] uppercase font-mono tracking-wider
            text-[var(--color-text-muted)] mb-2">
            Decision Path
          </p>
          <div className="flex flex-wrap items-center gap-1 font-mono text-xs
            bg-[var(--color-surface-2)] px-3 py-2.5 rounded border border-black/6">
            {decision_path.split("→").map((segment, i, arr) => (
              <span key={i} className="flex items-center gap-1">
                <span className="text-[var(--color-text)]">{segment.trim()}</span>
                {i < arr.length - 1 && (
                  <span className="text-[var(--color-text-muted)] select-none">→</span>
                )}
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
