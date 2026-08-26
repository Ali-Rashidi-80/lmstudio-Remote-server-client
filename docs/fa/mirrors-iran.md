# میرورهای ایرانی (چابکان)

[English](../mirrors-iran.md) · **فارسی**

وقتی دسترسی بین‌المللی محدود است، میرور محلی را ترجیح دهید.

## PyPI

```
pip install -r backend/requirements.txt \
  -i https://mirror2.chabokan.net/pypi/simple/ \
  --trusted-host mirror2.chabokan.net
```

یا `pip.conf.example` را در پیکربندی pip کپی کنید.

## npm

`web/.npmrc`:

```
registry=https://mirror2.chabokan.net/npm/
```

## Docker

Daemon:

```json
{ "registry-mirrors": ["https://mirror2.chabokan.net"] }
```

یا pull با پیشوند:

```
docker pull mirror2.chabokan.net/redis:7-alpine
```

`pgvector/pgvector:pg16` اگر در کش نباشد ممکن است از upstream بیاید؛ اسکریپت‌ها خودکار fallback می‌کنند.

کمک‌کننده‌ها: `scripts/install-deps.ps1` / `scripts/install-deps.sh`.

منبع: https://iran.chabokan.net/
