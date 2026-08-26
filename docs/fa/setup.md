# راه‌اندازی

[English](../setup.md) · **فارسی**

## پیش‌نیازها

- Python 3.11+
- Node.js 20+
- Docker (برای Postgres/Redis)
- LM Studio با API روی `127.0.0.1:1234`

## محیط

کپی `.env.example` → `.env` و `pc_client/.env.example` → `pc_client/.env`.

متغیرهای ضروری Bridge: `DATABASE_URL`، `REDIS_URL`، `JWT_SECRET`، `WORKER_TOKEN`، `ADMIN_BOOTSTRAP_PASSWORD` (≥۱۰ کاراکتر)، `CORS_ORIGINS`.

متغیرهای ضروری Worker: `BRIDGE_WS_URL` (مثلاً `ws://127.0.0.1:8010`)، `WORKER_TOKEN` (همان Bridge)، `LMSTUDIO_HOST=127.0.0.1:1234`.

پورت میزبان Bridge پیش‌فرض **۸۰۱۰** است تا با `:8000` تداخل نکند.

## میرور ایران

[mirrors-iran.md](mirrors-iran.md). ترجیحاً `scripts/install-deps.ps1` / `.sh`.

## ادمین bootstrap

در اولین استارت با جدول `users` خالی، Bridge ادمین را از env می‌سازد. استارت‌های بعدی دوباره نمی‌سازند.

## بالا آوردن محلی (پیشنهادی)

1. `docker compose up -d postgres redis`
2. `cd backend && alembic upgrade head`
3. `powershell -File scripts/start-bridge.ps1`
4. `powershell -File scripts/run-rag-worker.ps1`
5. `cd pc_client && python main.py`
6. `cd web && npm install && npm run dev` با `NEXT_PUBLIC_API_URL=http://localhost:8010`

Compose کامل (اختیاری): `docker compose up -d` شامل `bridge`، `rag-worker` و `web`.

## GUI دسکتاپ

`pc_client/gui_client.py` legacy است. UI محصول Next.js است.
