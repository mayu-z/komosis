/* ──────────────────────────────────────────────────────────
 * useSocket — subscribe to Socket.io events for a run
 * ────────────────────────────────────────────────────────── */
import { useEffect, useRef } from "react";
import { getSocket, joinRoom, leaveRoom } from "@/lib/socket";
import { useRunContext } from "@/context/RunContext";
import type {
  CiUpdateEvent,
  FixAppliedEvent,
  RunCompleteEvent,
  TelemetryTickEvent,
  ThoughtEvent,
} from "@/types";

export function useSocket(runId: string | null): void {
  const { dispatch } = useRunContext();
  const activeRoom = useRef<string | null>(null);

  useEffect(() => {
    if (!runId) return;

    const socket = getSocket();

    // Join the room
    joinRoom(runId);
    activeRoom.current = runId;

    const onThought = (ev: ThoughtEvent) => dispatch({ type: "ADD_THOUGHT", payload: ev });
    const onFix = (ev: FixAppliedEvent) => dispatch({ type: "ADD_FIX", payload: ev });
    const onCi = (ev: CiUpdateEvent) => dispatch({ type: "ADD_CI_EVENT", payload: ev });
    const onTelemetry = (ev: TelemetryTickEvent) => dispatch({ type: "ADD_TELEMETRY", payload: ev });
    const onComplete = (ev: RunCompleteEvent) => dispatch({ type: "SET_COMPLETE", payload: ev });

    socket.on("thought_event", onThought);
    socket.on("fix_applied", onFix);
    socket.on("ci_update", onCi);
    socket.on("telemetry_tick", onTelemetry);
    socket.on("run_complete", onComplete);

    return () => {
      socket.off("thought_event", onThought);
      socket.off("fix_applied", onFix);
      socket.off("ci_update", onCi);
      socket.off("telemetry_tick", onTelemetry);
      socket.off("run_complete", onComplete);

      if (activeRoom.current) {
        leaveRoom(activeRoom.current);
        activeRoom.current = null;
      }
    };
  }, [runId, dispatch]);
}
