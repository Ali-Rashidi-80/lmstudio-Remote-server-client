# عیب‌یابی

[English](../troubleshooting.md) · **فارسی**

## Bridge بالا نمی‌آید

- وجود `.env` را از روی `.env.example` تأیید کنید.
- `ADMIN_BOOTSTRAP_PASSWORD` باید ≥ ۱۰ کاراکتر باشد.
- پورت اشغال: از **۸۰۱۰** استفاده کنید.
- `DATABASE_URL` باید `postgresql+asyncpg://` باشد و به Postgres سالم برسد.

## `/api/ready` ناموفق است

1. سلامت Postgres و Redis در `docker compose ps`  
2. اجرای PC Worker با `WORKER_TOKEN` یکسان  
3. تطابق `REDIS_URL` / `DATABASE_URL` با پورت‌های میزبان یا شبکهٔ compose  

```bash
curl -s http://127.0.0.1:8010/api/health
curl -s http://127.0.0.1:8010/api/ready
```

## Worker وصل نمی‌شود

- `BRIDGE_WS_URL` باید با Bridge یکی باشد (`ws://127.0.0.1:8010` محلی، `wss://…` prod).
- `WORKER_TOKEN` در دو طرف یکسان.
- در production: `TLS_VERIFY=true`.
- پروکسی باید upgrade وب‌سوکت برای `/ws/pc` را اجازه دهد.

## آپلود RAG گیر می‌کند

- با `RAG_INGEST_MODE=arq` باید `rag-worker` در حال اجرا باشد.
- در prod امبدینگ از Worker؛ `EMBED_DIRECT_URL` فقط لاب.
- LM Studio باید EmbeddingGemma با **dim 768** سرو کند.
- پس از تعویض مدل امبد: **reindex** ادمین.

## ورود / CORS / کوکی

- `CORS_ORIGINS` باید دقیقاً مبدأ وب را شامل شود.
- پشت HTTPS: `COOKIE_SECURE=true`.
- ثبت‌نام باز غیرفعال است؛ از دعوت استفاده کنید.

## وب به API نمی‌رسد

- `NEXT_PUBLIC_API_URL=http://localhost:8010` (یا URL عمومی Bridge).
- بعد از تغییر env، Next را ری‌استارت کنید.

## اسکیما / Alembic

- دیتابیس تازه: `cd backend && alembic upgrade head`
- جداول از قبل با `create_all`: `alembic stamp 0001`

## مشکلات شبکه ایران

میرور چابکان — [mirrors-iran.md](mirrors-iran.md) و `scripts/install-deps.ps1`.
