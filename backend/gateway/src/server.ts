import http from "node:http";
import { Server as SocketIOServer } from "socket.io";
import { createApp } from "./app.js";
import { config } from "./config.js";
import { ContractSafeBroadcaster } from "./socket-broadcaster.js";
import { RedisBridge } from "./redis-bridge.js";
import { closeRedis } from "./redis.js";
import { closePool } from "./db.js";
import { closeQueue } from "./queue.js";

const app = createApp();
const httpServer = http.createServer(app);

// ── Socket.io ──────────────────────────────────────────────
const io = new SocketIOServer(httpServer, {
  cors: { origin: "*", methods: ["GET", "POST"] },
  path: "/socket.io",
  transports: ["websocket", "polling"],
});

io.on("connection", (socket) => {
  // Clients join a room by run_id: e.g. "/run/run_abc123"
  socket.on("join_run", (runId: string) => {
    const room = `/run/${runId}`;
    void socket.join(room);
    // eslint-disable-next-line no-console
    console.log(`Socket ${socket.id} joined room ${room}`);
  });

  socket.on("leave_run", (runId: string) => {
    const room = `/run/${runId}`;
    void socket.leave(room);
  });
});

// Export for use by worker bridge / routes
export const broadcaster = new ContractSafeBroadcaster(io);
export const redisBridge = new RedisBridge(broadcaster);
export { io };

// ── Start ──────────────────────────────────────────────────
httpServer.listen(config.port, () => {
  // eslint-disable-next-line no-console
  console.log(`Gateway listening on http://localhost:${config.port}`);
  // eslint-disable-next-line no-console
  console.log(`Socket.io attached on /socket.io`);

  // Start Redis → Socket.io bridge (non-blocking; logs errors internally)
  redisBridge.start().catch((err) => {
    // eslint-disable-next-line no-console
    console.error("[Gateway] Redis bridge failed to start:", err);
  });
});

// ── Graceful shutdown ──────────────────────────────────────
async function shutdown(signal: string): Promise<void> {
  // eslint-disable-next-line no-console
  console.log(`\n${signal} received — shutting down gracefully…`);
  await redisBridge.close();
  io.close();
  httpServer.close();
  await closeQueue();
  await closeRedis();
  await closePool();
  process.exit(0);
}

process.on("SIGTERM", () => void shutdown("SIGTERM"));
process.on("SIGINT", () => void shutdown("SIGINT"));
