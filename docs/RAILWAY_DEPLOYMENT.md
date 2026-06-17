# Railway Deployment Guide

This repo is structured as a multi-service app. Deploy all services in one Railway project:

1. `gateway` (public)
2. `frontend` (public)
3. `agent` (private)
4. `worker` (private)
5. Railway Postgres plugin
6. Railway Redis plugin

## 1. Create Services From This Repo

Create each service from the same GitHub repo and set:

- Root directory: `/`
- Dockerfile path:
  - `backend/gateway/Dockerfile`
  - `frontend/Dockerfile`
  - `backend/agent/Dockerfile`
  - `backend/worker/Dockerfile`

## 2. Network + Port Expectations

- `gateway` listens on `PORT` (already supported)
- `frontend` listens on `PORT` (runtime nginx template)
- `agent` listens on `PORT` (uvicorn now uses `PORT`)
- `worker` has no public port

## 3. Required Environment Variables

Use `railway.env.example` as the base reference. Set per service:

### `gateway`

- `PORT=3000`
- `DATABASE_URL=<Railway Postgres URL>`
- `REDIS_URL=<Railway Redis URL>`
- `AGENT_BASE_URL=http://agent:8001`
- `OUTPUTS_DIR=/app/outputs`
- `MAX_ITERATIONS=5`

### `agent`

- `PORT=8001`
- `DATABASE_URL=<Railway Postgres URL>`
- `REDIS_URL=<Railway Redis URL>`
- `GATEWAY_BASE_URL=http://gateway:3000`
- `REPOS_DIR=/tmp/repos`
- `OUTPUTS_DIR=/app/outputs`
- `MAX_ITERATIONS=5`
- `GITHUB_TOKEN=<required for push>`
- `GROQ_API_KEYS=<optional, comma-separated>`
- `OPENAI_API_KEY=<optional fallback>`

### `worker`

- `REDIS_URL=<Railway Redis URL>`
- `AGENT_BASE_URL=http://agent:8001`
- `GATEWAY_BASE_URL=http://gateway:3000`
- `OUTPUTS_DIR=/app/outputs`
- `POLL_INTERVAL_MS=3000`
- `MAX_POLL_ATTEMPTS=200`
- `WORKER_CONCURRENCY=2`

### `frontend`

- `PORT=8080` (or leave Railway default)
- `GATEWAY_UPSTREAM=http://gateway:3000`

## 4. Public Routing

- Expose `frontend` publicly.
- Expose `gateway` publicly if you want direct API access.
- Keep `agent` and `worker` private.

If frontend is the only public app, requests to `/api/*` and `/socket.io/*` are proxied internally to `gateway`.

## 5. Deploy Order

1. Provision Postgres + Redis.
2. Deploy `agent`.
3. Deploy `gateway`.
4. Deploy `worker`.
5. Deploy `frontend`.

## 6. Health Checks

- `gateway`: `GET /health`
- `agent`: `GET /health`
- `frontend`: `GET /` (serves SPA)
