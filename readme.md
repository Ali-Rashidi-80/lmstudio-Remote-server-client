✦ AI Workspace Enterprise (v17.6 Final)

A Secure, Autonomous, and End-to-End Encrypted AI Bridge Architecture

سیستم AI Workspace یک معماری پیشرفته‌ی کلاینت-سرور برای ارتباط امن و از راه دور با مدل‌های زبانی محلی (اجرا شده توسط LM Studio) است. این پروژه با استفاده از معماری Bridge-Worker طراحی شده است تا به کاربران اجازه دهد بدون نیاز به افشای IP مستقیم سرور پردازشی خود، از طریق یک رابط کاربری مدرن (Web/GUI) با هوش مصنوعی ارتباط برقرار کنند.

🏛 Architecture Topology (معماری سیستم)

این سیستم از ۴ جزء اصلی تشکیل شده است:

Bridge Server (FastAPI):
یک سرور واسط و سبک (Relay) که در محیط ابری (Cloud) مستقر می‌شود. وظیفه آن مدیریت اتصالات WebSocket، مسیریابی پیام‌ها و مدیریت وضعیت (Presence) است. بریج هیچ درکی از محتوای پیام‌ها ندارد زیرا تمامی داده‌ها رمزنگاری شده‌اند (Zero-Knowledge Architecture).

PC Worker Node (Python/LM Studio):
یک پردازشگر محلی که در کنار سخت‌افزار اصلی (دارای GPU/CPU قدرتمند) اجرا می‌شود. این نود از یک سو به Bridge متصل است و از سوی دیگر درخواست‌ها را به سرور محلی LM Studio پاس می‌دهد.

Web UI Client (HTML/JS/CSS):
رابط کاربری تحت وب با طراحی مدرن (Glassmorphism)، مدیریت پویای کانتکست‌ها با سایدبار، محافظت در برابر پر شدن حافظه (Storage Quota Protection)، پشتیبانی از تم تاریک/روشن و چندزبانگی.

Desktop GUI Client (PySide6):
نسخه بومی دسکتاپ برای سیستم‌عامل‌های ویندوز/لینوکس/مک که تمامی قابلیت‌های نسخه وب شامل همگام‌سازی تاریخچه (Context Sync) و پاکسازی حافظه را در یک پنجره مستقل با پرفورمنس بالا ارائه می‌دهد.

🔒 Security & Encryption (امنیت و رمزنگاری)

امنیت در این سیستم بر پایه اصل End-to-End Encryption (E2E) بنا شده است:

الگوریتم: سیستم از الگوریتم AES-CBC با کلید ۲۵۶-بیتی (۳۲ بایتی) استفاده می‌کند.

تولید IV داینامیک: برای هر پیام یک Initialization Vector (IV) تصادفی ۱۶ بایتی تولید می‌شود تا حملات Replay Attack خنثی شوند.

پروتکل ارتباطی: واسط (Bridge Server) تنها پیام‌های رمزنگاری شده (payload) را دریافت و به مقصد فوروارد می‌کند. کلید رمزنگاری (ENCRYPTION_KEY) تنها در کلاینت کاربر (Web/GUI) و سرور پردازشی (PC Worker) وجود دارد.

Proxy Kill-Switch: در سرور PC، تمامی متغیرهای محیطی مرتبط با پروکسی مسدود شده‌اند تا از نشت داده‌ها (Data Leak) به تونل‌های ناخواسته جلوگیری شود.

⚙️ Data Flows & Scenarios (سناریوها و جریان کاری)

1. سناریوی اتصال و کشف (Discovery Scenario)

کاربر به Bridge متصل می‌شود.

Bridge یک شناسه یکتا (client_id) به کاربر اختصاص می‌دهد.

Bridge بررسی می‌کند که آیا PC Node متصل است یا خیر. وضعیت (آنلاین/آفلاین) به همراه نوع سخت‌افزار (CPU/GPU) به کاربر ارسال می‌شود.

به صورت همزمان، PC Worker هر ۱۵ ثانیه یک سیگنال ping به Bridge ارسال می‌کند. سیستم از قابلیت Self-Healing کتابخانه Asyncio استفاده کرده و از افتادن در لوپ‌های بی‌نهایت جلوگیری می‌کند.

2. سناریوی کانتکست و استریم (Context Sync & Streaming)

کاربر پیامی تایپ می‌کند (متن + تصویر انتخابی) یا یک چت قدیمی را باز می‌کند.

کل تاریخچه‌ی چت به همراه پیام جدید درون پکیج رمزنگاری شده قرار گرفته و به سمت PC Node می‌رود.

سرور PC بسته را رمزگشایی کرده، Context کامل مدل را از نو می‌سازد (جلوگیری از فراموشی یا Amnesia).

پاسخ LM Studio به صورت تکه‌تکه (Chunk) دریافت و رمزنگاری می‌شود.

رابط کاربری بدون فریز شدن و با استفاده از Throttling، متن را با انیمیشن روان به کاربر نمایش داده و به صورت زمان‌بندی‌شده در حافظه ذخیره می‌کند.

3. مدیریت حافظه (Memory Management & Quota Defense)

در وب: اگر کاربر عکس‌های متعددی ارسال کند و سقف ۵ مگابایتی LocalStorage پر شود، سیستم بدون کرش کردن، اخطار پر شدن فضا (Quota Exceeded) را نمایش می‌دهد و کاربر با زدن دکمه ✖ در کنار چت‌های قدیمی در سایدبار می‌تواند فضا را آزاد کند.

در دسکتاپ: دکمه‌ی اختصاصی 🗑 (Clear Chat) به هدر اضافه شده است تا با یک کلیک، حافظه لوکال و سرور همزمان ریست شوند و نیازی به راه‌اندازی مجدد برنامه نباشد.

در سرور پردازشی: پیام unload_models و clear_history مستقیماً کانتکست و VRAM سیستم کاربر را کاملاً تخلیه می‌کند.

🛠 Features & Capabilities (قابلیت‌های کلیدی)

Strict PEP8 Compliance: کدها بدون هیچ ارور Flake8 یا Pylint نوشته شده‌اند.

Storage Bomb Defense: جلوگیری از کرش جاوااسکریپت در زمان پر شدن حافظه به دلیل تصاویر Base64.

Smart Hardware Monitor: تشخیص خودکار گرافیک (NVIDIA / Apple Silicon) و سوئیچ حالت پردازش.

Grace Period Disconnection: ۳۰ ثانیه زمان طلایی در سرور Bridge برای حفظ اتصال کلاینت در زمان قطعی‌های کوتاه اینترنت.

Resilient Reconnection: الگوریتم Exponential Backoff برای اتصال مجدد در صورت قطعی شبکه.

🚀 Setup Requirements (نیازمندی‌ها)

Python 3.10+ (For Bridge, PC Node, GUI Client)

PySide6 (For Desktop App)

FastAPI & Uvicorn (For Bridge Server)

PyCryptodome (For AES Encryption)

LM Studio (Running locally on the PC Node with API server enabled on port 1234)

“Perfection is achieved, not when there is nothing more to add, but when there is nothing left to take away.”