# Troubleshooting

**English** · [فارسی](fa/troubleshooting.md)

## Bridge will not start

- Confirm `.env` exists (copied from `.env.example`).
- `ADMIN_BOOTSTRAP_PASSWORD` must be ≥ 10 characters.
- Port busy: use **8010** (`scripts/start-bridge.ps1` or `BRIDGE_HOST_PORT`).
- DB URL must use `postgresql+asyncpg://` and reach a healthy Postgres.

## `/api/ready` fails

Checklist:

1. `docker compose ps` — Postgres and Redis healthy  
2. PC Worker running with matching `WORKER_TOKEN`  
3. `REDIS_URL` / `DATABASE_URL` match the compose network or host ports  

```bash
curl -s http://127.0.0.1:8010/api/health
curl -s http://127.0.0.1:8010/api/ready
```

## Worker cannot connect

- `BRIDGE_WS_URL` must match Bridge (`ws://127.0.0.1:8010` local, `wss://…` prod).
- `WORKER_TOKEN` identical on both sides.
- Production: `TLS_VERIFY=true`; only disable verify in disposable labs.
- Firewall / reverse proxy must allow WebSocket upgrade on `/ws/pc`.

## RAG upload stuck / no embeddings

- `RAG_INGEST_MODE=arq` requires `scripts/run-rag-worker.ps1` (or compose `rag-worker`).
- Prefer Worker embeddings in prod; `EMBED_DIRECT_URL` is lab-only.
- LM Studio must serve embedding model `text-embedding-embeddinggemma-300m` with **dim 768**.
- After changing embed model: admin **reindex** (chunks store `embed_model_id` / `embed_dim`).

## Login / CORS / cookies

- `CORS_ORIGINS` must include the exact web origin (e.g. `http://localhost:3000`).
- Behind HTTPS set `COOKIE_SECURE=true`.
- Open registration is disabled (`POST /api/auth/register` → 403); use invites.

## Web cannot reach API

- `NEXT_PUBLIC_API_URL=http://localhost:8010` (or your public Bridge URL).
- Rebuild/restart Next after changing env.

## Schema / Alembic

- Fresh DB: `cd backend && alembic upgrade head`
- Tables already created via `create_all`: `alembic stamp 0001` then continue with newer revisions

## QA / CI local failures

```powershell
powershell -File scripts/qa.ps1
```

Ensure test Postgres/Redis env vars match [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) when running outside compose.

## Iran network issues

Use Chabokan mirrors — [mirrors-iran.md](mirrors-iran.md) and `scripts/install-deps.ps1`.
