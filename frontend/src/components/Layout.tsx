/* ──────────────────────────────────────────────────────────
 * Layout — persistent chrome around pages
 * ────────────────────────────────────────────────────────── */
import type { ReactNode } from "react";
import Header from "./Header";

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-transparent text-[var(--color-text)] flex flex-col relative">
      <Header />
      <main className="flex-1 w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>
      <footer className="border-t border-black/10 py-4 text-center text-xs text-[var(--color-text-muted)] bg-white/75 backdrop-blur-md">
        komosis 2026 · Autonomous CI/CD Healing Agent
      </footer>
    </div>
  );
}
