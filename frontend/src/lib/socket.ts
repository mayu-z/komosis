/* ──────────────────────────────────────────────────────────
 * Socket.io client singleton & connection management
 * ────────────────────────────────────────────────────────── */
import { io, type Socket } from "socket.io-client";

let socket: Socket | null = null;
const SOCKET_URL = import.meta.env.VITE_SOCKET_URL ?? window.location.origin;
const SOCKET_PATH = import.meta.env.VITE_SOCKET_PATH ?? "/socket.io";

export function getSocket(): Socket {
  if (!socket) {
    socket = io(SOCKET_URL, {
      path: SOCKET_PATH,
      // Prefer polling first for proxy compatibility, then upgrade to websocket.
      transports: ["polling", "websocket"],
      autoConnect: true,
      reconnection: true,
      reconnectionAttempts: 20,
      reconnectionDelay: 1_000,
      reconnectionDelayMax: 10_000,
    });

    socket.on("connect", () => {
      console.log("[socket] connected:", socket?.id);
    });

    socket.on("disconnect", (reason) => {
      console.log("[socket] disconnected:", reason);
    });

    socket.on("connect_error", (err) => {
      console.warn("[socket] connection error:", err.message);
    });
  }

  return socket;
}

export function joinRoom(runId: string): void {
  getSocket().emit("join_run", runId);
}

export function leaveRoom(runId: string): void {
  getSocket().emit("leave_run", runId);
}

export function disconnectSocket(): void {
  if (socket) {
    socket.disconnect();
    socket = null;
  }
}
