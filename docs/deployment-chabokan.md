# Deploy Bridge on Chabokan (or similar)

**English** · [فارسی](fa/deployment-chabokan.md)

1. Create app/service for Bridge (Python) and attach managed Postgres + Redis if available.
2. Set env from `.env.example` (real secrets via panel, not git).
3. Terminate HTTPS at the reverse proxy; set `COOKIE_SECURE=true` and `CORS_ORIGINS=https://your-frontend`.
4. Ensure WebSocket upgrade is enabled for `/ws/client` and `/ws/pc`.
5. Persist volume for `storage/uploads`.
6. Run PC Worker at home/office with `BRIDGE_WS_URL=wss://your-bridge` and matching `WORKER_TOKEN`.
7. Backup: `scripts/backup-postgres.sh` / schedule `pg_dump`.

Host/lab Bridge port note: local default publish is **8010** (`BRIDGE_HOST_PORT`). Public deploy usually terminates TLS on 443 and proxies to the container port.

Iran package/container mirrors: [mirrors-iran.md](mirrors-iran.md).
