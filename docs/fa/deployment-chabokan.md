# استقرار Bridge روی چابکان (یا مشابه)

[English](../deployment-chabokan.md) · **فارسی**

1. سرویس/اپ Bridge (پایتون) بسازید و در صورت امکان Postgres + Redis مدیریت‌شده وصل کنید.
2. env را از `.env.example` بگیرید (راز واقعی از پنل، نه git).
3. HTTPS را در reverse proxy خاتمه دهید؛ `COOKIE_SECURE=true` و `CORS_ORIGINS=https://your-frontend`.
4. upgrade وب‌سوکت برای `/ws/client` و `/ws/pc` را فعال کنید.
5. volume پایدار برای `storage/uploads`.
6. PC Worker را در خانه/اداره با `BRIDGE_WS_URL=wss://your-bridge` و همان `WORKER_TOKEN` اجرا کنید.
7. بکاپ: `scripts/backup-postgres.sh` / زمان‌بندی `pg_dump`.

یادداشت پورت لاب محلی: انتشار پیش‌فرض **۸۰۱۰** (`BRIDGE_HOST_PORT`). استقرار عمومی معمولاً TLS روی ۴۴۳ را به پورت کانتینر پروکسی می‌کند.

میرور بسته/کانتینر ایران: [mirrors-iran.md](mirrors-iran.md).
