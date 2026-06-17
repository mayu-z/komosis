/* ──────────────────────────────────────────────────────────
 * DashboardPage — the live run dashboard with all 5 sections
 * ────────────────────────────────────────────────────────── */
import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useRunContext } from "@/context/RunContext";
import { useSocket } from "@/hooks/useSocket";
import { usePolling } from "@/hooks/usePolling";
import Layout from "@/components/Layout";
import Card from "@/components/Card";
import ThoughtStream from "@/components/ThoughtStream";
import RunSummaryCard from "@/sections/RunSummaryCard";
import ScoreBreakdownPanel from "@/sections/ScoreBreakdownPanel";
import FixesAppliedTable from "@/sections/FixesAppliedTable";
import CiTimelinePanel from "@/sections/CiTimelinePanel";

export default function DashboardPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { state, initRun } = useRunContext();

  // If context doesn't have this runId yet, initialize
  useEffect(() => {
    if (runId && state.runId !== runId) {
      initRun(runId, `/run/${runId}`);
    }
  }, [runId, state.runId, initRun]);

  // Subscribe to Socket.io events
  useSocket(runId ?? null);

  // Poll for status + results
  usePolling(runId ?? null);

  if (!runId) {
    navigate("/");
    return null;
  }

  return (
    <Layout>
      <div className="space-y-6">
        {/* ─── Row 1: Summary + Score ──────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <RunSummaryCard />
          <ScoreBreakdownPanel />
        </div>

        {/* ─── Row 2: Agent Thoughts (real-time) ───────── */}
        <Card
          title="Agent Thoughts"
          subtitle="Real-time reasoning stream"
        >
          <ThoughtStream thoughts={state.thoughts} maxHeight="400px" />
        </Card>

        {/* ─── Row 3: Fixes + CI ──────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <FixesAppliedTable />
          <CiTimelinePanel />
        </div>
      </div>
    </Layout>
  );
}
