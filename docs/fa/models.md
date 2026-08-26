# مدل‌ها

[English](../models.md) · **فارسی**

پیش‌فرض‌های قفل‌شده این استقرار:

- **چت:** `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q6_k`
- **امبدینگ:** `text-embedding-embeddinggemma-300m` (`EMBED_DIM=768`)

جایگزین‌ها:

- کیفیت چت: `@q8_0` / توان عملیاتی: `@q4_k_m` / سبک: `google/gemma-4-e4b`
- امبد جایگزین: `text-embedding-nomic-embed-text-v2`

تغییر مدل امبدینگ نیازمند reindex کامل chunkهای RAG است (`embed_model_id` روی هر chunk ذخیره می‌شود).

پیکربندی از env Bridge / تنظیمات ادمین؛ Worker باید شناسه‌های مطابق LM Studio را بارگذاری کند.
