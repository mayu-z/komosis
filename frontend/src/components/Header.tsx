/* ──────────────────────────────────────────────────────────
 * Header — top navigation bar
 * ────────────────────────────────────────────────────────── */
import { Link } from "react-router-dom";

export default function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-black/10 bg-white/80 backdrop-blur-md">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-14">
        <Link to="/" className="flex items-center gap-2 group">
          <span className="font-mono text-xs tracking-wide px-2 py-1 border border-black/15 bg-black text-white">
            komosis
          </span>
          <span className="font-semibold text-sm tracking-tight text-[var(--color-text)]">
            Agent
          </span>
        </Link>

        <nav className="flex items-center gap-4 text-sm text-[var(--color-text-muted)]">
          <Link to="/app" className="hover:text-[var(--color-text)] transition-colors px-1">
            New Run
          </Link>
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center border border-black/15 px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-black hover:text-white transition-colors"
          >
            Docs
          </a>
        </nav>
      </div>
    </header>
  );
}
