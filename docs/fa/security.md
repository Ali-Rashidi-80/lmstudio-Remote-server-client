# امنیت

[English](../security.md) · **فارسی**

## مدل تهدید (فاز ۱)

- TLS/WSS + کاربران احرازشده (کوکی) و توکن Worker
- بدون تزریق کلید رمزنگاری مشترک به HTML
- ثبت‌نام دعوت‌محور؛ `/api/auth/register` باز غیرفعال
- ردیف‌های چت و RAG محدود به `user_id`
- `unload_models` فقط ادمین
- محدودیت نرخ ورود با Redis

## بهداشت رازها

- هرگز فایل `.env` را commit نکنید
- هر کلیدی که قبلاً در تاریخچه git بوده را بچرخانید
- اگر مخزن عمومی با راز بوده، `git filter-repo` / BFG را ترجیح دهید

## کوکی‌ها

`access_token` / `refresh_token`: `HttpOnly`، `SameSite=Lax`، و `Secure` وقتی `COOKIE_SECURE=true`.

## TLS مربوط به Worker

در production مقدار `TLS_VERIFY=true`. فقط در لاب غیرفعال کنید.

## مرتبط

- سیاست ریشه: [../../SECURITY.fa.md](../../SECURITY.fa.md)
- مرزهای اعتماد: [architecture.md](architecture.md)
