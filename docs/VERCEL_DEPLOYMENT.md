# Vercel Deployment Guide

This repo can be deployed to Vercel as a **frontend-only** app.
The backend services (`gateway`, `agent`, `worker`, Postgres, Redis) should stay on Railway/Docker.

## 1. Import Project in Vercel

1. In Vercel, import this GitHub repo.
2. Keep project root as repository root.
3. Vercel uses `vercel.json` in this repo to build `frontend/dist`.

## 2. Required Vercel Environment Variables

Set these in Vercel Project Settings -> Environment Variables:

- `VITE_API_BASE_URL=https://<your-gateway-public-url>`
- `VITE_SOCKET_URL=https://<your-gateway-public-url>`
- `VITE_SOCKET_PATH=/socket.io`

Optional:

- `VITE_FRONTEND_PORT=5173` (local dev only)
- `VITE_PREVIEW_PORT=4173` (local preview only)

## 3. Notes

- Vercel does not require binding a custom runtime port for static Vite apps.
- Frontend port env vars are used for local development (`vite dev` / `vite preview`).
- If API and Socket run on the same host, keep both `VITE_API_BASE_URL` and `VITE_SOCKET_URL` pointing to that host.
