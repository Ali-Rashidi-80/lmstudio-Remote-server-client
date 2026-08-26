# API overview

**English** · [فارسی](fa/api.md)

## REST

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/api/health` | no | liveness |
| GET | `/api/ready` | no | DB + Redis + worker status |
| POST | `/api/auth/login` | no | sets httpOnly cookies |
| POST | `/api/auth/logout` | user | |
| POST | `/api/auth/logout-all` | user | |
| POST | `/api/auth/refresh` | cookie | |
| GET | `/api/auth/me` | user | |
| POST | `/api/auth/ws-ticket` | user | 60s WS ticket |
| POST | `/api/auth/accept-invite` | no | invite-only signup |
| POST | `/api/auth/change-password` | user | |
| POST | `/api/auth/register` | — | always 403 |
| GET/POST | `/api/users` | admin | |
| PATCH | `/api/users/{user_id}` | admin | |
| POST/GET | `/api/users/invites` | admin | |
| GET/POST | `/api/chats` | user | ownership enforced |
| GET | `/api/chats/{chat_id}` | user | |
| GET | `/api/chats/{chat_id}/messages` | user | |
| DELETE | `/api/chats/{chat_id}` | user | |
| POST | `/api/chats/import-local` | user | migrate browser sessions |
| GET/POST | `/api/knowledge/docs` | user | RAG documents |
| PATCH/DELETE | `/api/knowledge/docs/{doc_id}` | user | |
| GET | `/api/knowledge/jobs/{job_id}` | user | ingest status |
| POST | `/api/knowledge/search` | user | vector search |
| GET | `/api/admin/stats` | admin | |
| GET/PUT | `/api/admin/settings` | admin | |
| POST | `/api/admin/reindex` | admin | |
| POST | `/api/admin/unload-models` | admin | |
| GET | `/api/admin/models` | admin | |

## WebSocket protocol `v:1`

Client: `WS /ws/client?ticket=...`  
Worker: `WS /ws/pc?token=WORKER_TOKEN`

Envelope:

```json
{ "v": 1, "type": "chat", "payload": { "content": "...", "chat_id": "...", "use_rag": true } }
```

Worker messages include `client_id` when routing replies.

Default local Bridge base URL: `http://127.0.0.1:8010`.
