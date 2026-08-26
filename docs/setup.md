# Setup

**English** · [فارسی](fa/setup.md)

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker (for Postgres/Redis)
- LM Studio with API on `127.0.0.1:1234`

## Environment

Copy `.env.example` → `.env` and `pc_client/.env.example` → `pc_client/.env`.

Required Bridge vars: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `WORKER_TOKEN`, `ADMIN_BOOTSTRAP_PASSWORD` (≥10 chars), `CORS_ORIGINS`.

Required Worker vars: `BRIDGE_WS_URL` (e.g. `ws://127.0.0.1:8010`), `WORKER_TOKEN` (same as Bridge), `LMSTUDIO_HOST=127.0.0.1:1234`.

Host Bridge port defaults to **8010** (`BRIDGE_HOST_PORT` / `scripts/start-bridge.ps1`) to avoid clashing with other apps on `:8000`.

## Iran mirrors

See [mirrors-iran.md](mirrors-iran.md). Prefer `scripts/install-deps.ps1` / `.sh`.

## Bootstrap admin

On first start with an empty `users` table, Bridge creates the admin from env. Subsequent starts do not recreate it.

## Local bring-up (recommended)

1. `docker compose up -d postgres redis`
2. `cd backend && alembic upgrade head` (fresh database)
3. `powershell -File scripts/start-bridge.ps1`
4. `powershell -File scripts/run-rag-worker.ps1`
5. `cd pc_client && python main.py`
6. `cd web && npm install && npm run dev` with `NEXT_PUBLIC_API_URL=http://localhost:8010`

Full Compose (optional): `docker compose up -d` also starts `bridge`, `rag-worker`, and `web`.

## Desktop GUI

`pc_client/gui_client.py` is legacy. Product UI is Next.js.

See also: [architecture.md](architecture.md), [troubleshooting.md](troubleshooting.md), [../readme.md](../readme.md).
