import { Link } from "react-router-dom";

function GridBackground() {
  const cells = 180;
  return (
    <div className="fixed -inset-[64px] z-0 overflow-hidden pointer-events-none flex flex-wrap content-start">
      {Array.from({ length: cells }).map((_, i) => (
        <div
          key={i}
          className="w-[64px] h-[64px] border-r border-b border-black/[0.06]"
        />
      ))}
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white text-black relative overflow-hidden">
      <GridBackground />

      <div className="relative z-10 flex flex-col min-h-screen">
        <header className="border-b border-black/10 bg-white/80 backdrop-blur-md">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs tracking-wide px-2 py-1 border border-black/15 bg-black text-white">
                komosis
              </span>
              <span className="font-semibold text-sm tracking-tight">Agent</span>
            </div>
            <Link
              to="/app"
              className="inline-flex items-center border border-black/15 px-3 py-1.5 text-xs font-medium hover:bg-black hover:text-white transition-colors"
            >
              Launch
            </Link>
          </div>
        </header>

        <main className="flex-1 flex items-center justify-center p-6">
          <div className="w-full max-w-4xl border border-black/10 bg-white/95 shadow-[0_14px_35px_rgba(10,10,10,0.06)]">
            <div className="h-12 border-b border-black/10 bg-zinc-50 flex items-center px-4 gap-4">
              <div className="flex gap-2">
                <div className="w-3 h-3 rounded-full bg-[#ff5f56]" />
                <div className="w-3 h-3 rounded-full bg-[#ffbd2e]" />
                <div className="w-3 h-3 rounded-full bg-[#27c93f]" />
              </div>
              <div className="flex-1 flex justify-center">
                <div className="bg-white text-zinc-500 text-xs px-4 py-1.5 border border-black/10 w-64 text-center font-mono">
                  komosis.ai
                </div>
              </div>
              <div className="w-12" />
            </div>

            <div className="px-8 py-20 md:py-24 text-center">
              <h1 className="text-4xl md:text-6xl font-bold tracking-tight mb-6">
                Autonomous CI/CD Healing
              </h1>
              <p className="text-zinc-600 text-lg md:text-xl max-w-2xl mx-auto mb-10">
                Detect, fix, and verify repository issues automatically with a structured iteration loop.
              </p>
              <div className="flex items-center justify-center gap-3">
                <Link
                  to="/app"
                  className="bg-black text-white px-6 py-3 text-sm font-medium hover:bg-zinc-800 transition-colors"
                >
                  Start New Run
                </Link>
                <a
                  href="https://github.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="border border-black/15 px-6 py-3 text-sm font-medium hover:bg-zinc-100 transition-colors"
                >
                  GitHub
                </a>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
