import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const frontendPort = Number(process.env.VITE_FRONTEND_PORT ?? 5173);
const gatewayProxyTarget = process.env.VITE_DEV_PROXY_TARGET ?? "http://localhost:3000";
const previewPort = Number(process.env.VITE_PREVIEW_PORT ?? 4173);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: frontendPort,
    proxy: {
      "/api": {
        target: gatewayProxyTarget,
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
      "/socket.io": {
        target: gatewayProxyTarget,
        ws: true,
      },
    },
  },
  preview: {
    port: previewPort,
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
