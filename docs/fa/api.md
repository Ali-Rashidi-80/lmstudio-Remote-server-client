# مرور API

[English](../api.md) · **فارسی**

## REST

| متد | مسیر | Auth | یادداشت |
|-----|------|------|---------|
| GET | `/api/health` | خیر | زنده‌بودن |
| GET | `/api/ready` | خیر | DB + Redis + worker |
| POST | `/api/auth/login` | خیر | کوکی httpOnly |
| POST | `/api/auth/logout` | کاربر | |
| POST | `/api/auth/logout-all` | کاربر | |
| POST | `/api/auth/refresh` | کوکی | |
| GET | `/api/auth/me` | کاربر | |
| POST | `/api/auth/ws-ticket` | کاربر | بلیت ۶۰ثانیه |
| POST | `/api/auth/accept-invite` | خیر | ثبت‌نام دعوت‌محور |
| POST | `/api/auth/change-password` | کاربر | |
| POST | `/api/auth/register` | — | همیشه 403 |
| GET/POST | `/api/users` | ادمین | |
| PATCH | `/api/users/{user_id}` | ادمین | |
| POST/GET | `/api/users/invites` | ادمین | |
| GET/POST | `/api/chats` | کاربر | مالکیت اجباری |
| GET | `/api/chats/{chat_id}` | کاربر | |
| GET | `/api/chats/{chat_id}/messages` | کاربر | |
| DELETE | `/api/chats/{chat_id}` | کاربر | |
| POST | `/api/chats/import-local` | کاربر | مهاجرت نشست مرورگر |
| GET/POST | `/api/knowledge/docs` | کاربر | اسناد RAG |
| PATCH/DELETE | `/api/knowledge/docs/{doc_id}` | کاربر | |
| GET | `/api/knowledge/jobs/{job_id}` | کاربر | وضعیت ingest |
| POST | `/api/knowledge/search` | کاربر | جستجوی برداری |
| GET | `/api/admin/stats` | ادمین | |
| GET/PUT | `/api/admin/settings` | ادمین | |
| POST | `/api/admin/reindex` | ادمین | |
| POST | `/api/admin/unload-models` | ادمین | |
| GET | `/api/admin/models` | ادمین | |

## پروتکل WebSocket `v:1`

کلاینت: `WS /ws/client?ticket=...`  
Worker: `WS /ws/pc?token=WORKER_TOKEN`

پوشش:

```json
{ "v": 1, "type": "chat", "payload": { "content": "...", "chat_id": "...", "use_rag": true } }
```

پیام‌های Worker هنگام مسیریابی پاسخ شامل `client_id` هستند.

آدرس پایه محلی پیش‌فرض Bridge: `http://127.0.0.1:8010`.
