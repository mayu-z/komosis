# Komosis

> Autonomous CI/CD healing agent — give it a broken GitHub repo, it fixes it.

Komosis takes a GitHub repository URL, clones it, runs the test suite, diagnoses failures, generates fixes, and commits them back to a new branch — without any human intervention. A real-time React dashboard shows every decision the agent makes as it happens.

---

## What It Does

1. You submit a GitHub repo URL
2. Komosis clones it and runs the existing test suite in a sandboxed Docker container
3. The LangGraph agent classifies every failure — syntax error, import issue, logic bug, type error, linting, indentation
4. It generates a fix for each failure, validates it, and commits it with an `[AI-AGENT]` prefix
5. It monitors CI, retries if needed, and rolls back if a fix causes a regression
6. The dashboard updates in real time via WebSocket — you watch the agent think, fix, and commit

---

## Stack

| Layer | Technology |
|---|---|
| Agent | Python, FastAPI, LangGraph, Groq (primary), OpenAI (fallback) |
| Queue | BullMQ + Redis |
| Gateway | Node.js, Express, Socket.io |
| Frontend | React, Vite, TypeScript |
| Sandbox | Docker (per-language containers) |
| Database | PostgreSQL, Redis |
| Monorepo | pnpm workspaces |
| Deploy | Vercel (frontend), Railway (backend) |

---

## Architecture

```
[ React Dashboard ]
       │  WebSocket (Socket.io)
       ▼
[ Express Gateway ]  ──►  [ BullMQ Queue ]  ──►  [ FastAPI Agent ]
       │                                                  │
       │                                          [ LangGraph Graph ]
       │                                                  │
       │                              ┌───────────────────┤
       │                              ▼                   ▼
       │                      [ repo_scanner ]    [ test_runner ]
       │                              │                   │
       │                              ▼                   ▼
       │                      [ decision_node ]   [ fix_generator ]
       │                              │                   │
       │                              ▼                   ▼
       │                      [ cicd_generator ]  [ ci_monitor ]
       │                              │                   │
       └──────────────────────────────┴───► [ finalizer ]
                                                  │
                                         ┌────────┴────────┐
                                         ▼                 ▼
                                  [ PostgreSQL ]     [ results.json ]
```

---

## Agent Decision Flow

The LangGraph agent is not a simple pipeline. After scanning the repo it makes decisions:

```
repo_scanner
     │
     ▼
decision_node
     │
     ├── tests exist + failing   →  test_runner → fix_generator → ci_monitor
     │
     ├── tests exist + passing   →  cicd_generator
     │
     ├── no tests found          →  test_generator → cicd_generator
     │
     └── healthy (tests pass, CI exists)  →  finalizer (nothing to do)
```

This means Komosis works on any repository — not just ones with failing tests.

---

## Fix Classification

Every failure is classified before a fix is generated:

| Bug Type | Example |
|---|---|
| `SYNTAX` | Missing colon, unclosed bracket |
| `IMPORT` | Module not found, wrong import path |
| `TYPE_ERROR` | Wrong type passed to function |
| `LOGIC` | Incorrect condition, wrong return value |
| `LINTING` | Unused variable, line too long |
| `INDENTATION` | Mixed tabs/spaces, wrong indent level |

Rule-based parsing runs first for deterministic classification. The LLM is only used as a fallback for failures that don't match known patterns.

---

## Running Locally

### Prerequisites

- Node.js 20+
- Python 3.11+
- Docker
- pnpm

### Start infrastructure

```bash
docker run -d --name komosis-redis -p 6379:6379 redis:alpine

docker run -d --name komosis-postgres \
  -e POSTGRES_USER=komosis \
  -e POSTGRES_PASSWORD=komosis \
  -e POSTGRES_DB=komosis \
  -p 5432:5432 postgres:15
```

### Environment setup

```bash
cp .env.example .env
```

Minimum required variables:

```env
# Agent
GROQ_API_KEYS=your_groq_key
GITHUB_PAT=ghp_xxxxxxxxxxxx
DATABASE_URL=postgresql://komosis:komosis@localhost:5432/komosis
REDIS_URL=redis://localhost:6379

# Gateway
PORT=3000
FASTAPI_URL=http://localhost:8001
FRONTEND_URL=http://localhost:5173

# Frontend
VITE_API_URL=http://localhost:3000
VITE_SOCKET_URL=http://localhost:3000
```

Get a free Groq API key at [console.groq.com](https://console.groq.com).
Get a GitHub PAT at Settings → Developer settings → Personal access tokens → with `repo` and `workflow` scopes.

### Start all services

**Terminal 1 — Agent**
```bash
cd backend/agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

**Terminal 2 — Gateway**
```bash
cd backend/gateway
pnpm install
pnpm dev
```

**Terminal 3 — Worker**
```bash
cd backend/gateway
pnpm worker
```

**Terminal 4 — Frontend**
```bash
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:5173`.

### Or use Docker Compose

```bash
docker compose up --build
```

---

## API Reference

### POST /run-agent

Start an autonomous healing run.

```json
{
  "repo_url": "https://github.com/org/repo",
  "team_name": "your team",
  "leader_name": "your name"
}
```

Response:

```json
{
  "run_id": "run_abc123",
  "branch_name": "YOUR_TEAM_YOUR_NAME_AI_Fix",
  "status": "queued",
  "socket_room": "/run/run_abc123"
}
```

### GET /results/:runId

Returns the full run output including fixes applied, CI status, and score.

### GET /report/:runId

Returns a generated PDF incident report for the run.

### GET /replay/:runId

Returns the full execution trace for replay mode in the dashboard.

### GET /agent/status/:runId

Returns current LangGraph node, iteration count, and progress.

### POST /agent/query

Post-run natural language Q&A grounded in the run trace.

```json
{ "run_id": "run_abc123", "question": "Why did the import fix fail on retry?" }
```

### GET /health

Health check. Returns `{ "status": "ok" }`.

---

## WebSocket Events

Connect to `/run/:runId` to receive real-time agent updates.

| Event | Description |
|---|---|
| `thought_event` | Agent reasoning step |
| `fix_applied` | A fix was committed |
| `ci_update` | CI pipeline status changed |
| `telemetry_tick` | Iteration progress update |
| `run_complete` | Run finished, results ready |

---

## Project Structure

```
komosis/
├── backend/
│   ├── agent/              # FastAPI + LangGraph agent
│   │   ├── app/
│   │   │   ├── nodes/      # LangGraph nodes
│   │   │   ├── prompts/    # LLM prompt templates
│   │   │   ├── utils/      # File analysis, diff building, platform detection
│   │   │   └── llm.py      # Groq/OpenAI factory with round-robin key rotation
│   │   └── main.py
│   └── gateway/            # Express + BullMQ
│       ├── src/
│       │   ├── routes/
│       │   └── workers/
│       └── index.ts
├── frontend/               # React + Vite dashboard
│   └── src/
│       ├── components/
│       └── pages/
├── packages/
│   └── contracts/          # Shared TypeScript types
├── migrations/             # PostgreSQL migrations
├── services/               # Shared service utilities
├── docker-compose.yml
└── pnpm-workspace.yaml
```

---

## Known Limitations

- LLM-generated fixes are non-deterministic on edge cases. Rule-based parsing runs first to minimize this.
- Large monorepos with complex dependency graphs may require increased worker memory.
- Multi-language repos (e.g. Python + Go in the same repo) are not yet fully supported.
- Third-party API latency (Groq, GitHub) can affect run duration.

---

## License

MIT
