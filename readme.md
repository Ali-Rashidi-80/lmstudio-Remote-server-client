✦ AI Workspace Enterprise (v17.2 Final)

A Secure, Autonomous, and End-to-End Encrypted AI Bridge Architecture

سیستم AI Workspace یک معماری پیشرفته‌ی کلاینت-سرور برای ارتباط امن و از راه دور با مدل‌های زبانی محلی (اجرا شده توسط LM Studio) است. این پروژه با استفاده از معماری Bridge-Worker طراحی شده است تا به کاربران اجازه دهد بدون نیاز به افشای IP مستقیم سرور پردازشی خود، از طریق یک رابط کاربری مدرن (Web/GUI) با هوش مصنوعی ارتباط برقرار کنند.

🏛 Architecture Topology (معماری سیستم)

این سیستم از ۴ جزء اصلی تشکیل شده است:

Bridge Server (FastAPI):
یک سرور واسط و سبک (Relay) که در محیط ابری (Cloud) مستقر می‌شود. وظیفه آن مدیریت اتصالات WebSocket، مسیریابی پیام‌ها و مدیریت وضعیت (Presence) است. بریج هیچ درکی از محتوای پیام‌ها ندارد زیرا تمامی داده‌ها رمزنگاری شده‌اند (Zero-Knowledge Architecture).

PC Worker Node (Python/LM Studio):
یک پردازشگر محلی که در کنار سخت‌افزار اصلی (دارای GPU/CPU قدرتمند) اجرا می‌شود. این نود از یک سو به Bridge متصل است و از سوی دیگر درخواست‌ها را به سرور محلی LM Studio پاس می‌دهد.

Web UI Client (HTML/JS/CSS):
رابط کاربری تحت وب با طراحی مدرن (Glassmorphism)، پشتیبانی از تم تاریک/روشن، چندزبانگی (En/Fa) و قابلیت رندر پیشرفته Markdown و کد.

Desktop GUI Client (PySide6):
نسخه بومی دسکتاپ برای سیستم‌عامل‌های ویندوز/لینوکس/مک که تمامی قابلیت‌های نسخه وب را در یک پنجره مستقل با پرفورمنس بالا ارائه می‌دهد.

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

به صورت همزمان، PC Worker هر ۱۵ ثانیه یک سیگنال ping به Bridge ارسال می‌کند. اگر Bridge به مدت ۴۵ ثانیه پینگی دریافت نکند، وضعیت PC را آفلاین در نظر می‌گیرد (جلوگیری از Race Condition).

2. سناریوی چت و استریم (Streaming Chat Flow)

کاربر پیامی تایپ می‌کند (متن + تصویر انتخابی).

کلاینت پیام را در قالب JSON بسته بندی کرده و با کلید AES رمزنگاری می‌کند.

Bridge بسته رمزنگاری شده را به PC Node می‌فرستد.

سرور PC بسته را رمزگشایی کرده، تاریخچه چت کاربر را بروزرسانی می‌کند (با مدیریت سقف تاریخچه) و درخواست را به LM Studio می‌فرستد.

پاسخ LM Studio به صورت تکه‌تکه (Chunk) دریافت می‌شود.

PC هر Chunk را رمزنگاری کرده و از طریق Bridge به کاربر برمی‌گرداند. کلاینت پیام را رمزگشایی کرده و با انیمیشن روان به کاربر نمایش می‌دهد.

3. سناریوی ابزارهای خودمختار (Autonomous Agents / Tool Calling)

اگر دکمه "ابزارها" فعال باشد، پرامپت سیستمی تغییر کرده و لیست ابزارها (مانند ماشین‌حساب امن SafeMathEvaluator) به مدل ارسال می‌شود.

اگر مدل تشخیص دهد نیاز به محاسبه دارد، یک tool_call برمی‌گرداند.

Worker ابزار را به صورت امن (جلوگیری از DoS و اعداد غول‌پیکر در محاسبات توانی) اجرا می‌کند.

نتیجه ابزار به تاریخچه چت اضافه شده و مجدداً به مدل ارسال می‌شود تا پاسخ نهایی به کاربر داده شود. (این فرآیند در بک‌گراند رخ می‌دهد و کاربر وضعیت "در حال اجرای ابزار" را می‌بیند).

4. سناریوی مدیریت حافظه (Memory Management)

کاربر دکمه "تخلیه RAM" را می‌فشارد.

پیام unload_models به PC ارسال می‌شود.

سرور PC ابتدا لیست مدل‌های لود شده را می‌گیرد و سپس به مسیر دقیق /api/v1/models/unload در LM Studio دستور تخلیه می‌فرستد تا VRAM آزاد شود.

🛠 Features & Capabilities (قابلیت‌های کلیدی)

Strict PEP8 Compliance: کدها بدون هیچ ارور Flake8 یا Pylint نوشته شده‌اند.

Multilingual UI: معماری داینامیک پشتیبانی از RTL/LTR برای زبان‌های فارسی و انگلیسی.

Smart Hardware Monitor: تشخیص خودکار گرافیک (NVIDIA / Apple Silicon) و سوئیچ حالت پردازش.

Auto-Pruning History: مدیریت هوشمند حافظه‌ی کانتکست (Context Window) با حذف پیام‌های قدیمی و حفظ System Prompt.

Resilient Reconnection: الگوریتم Exponential Backoff برای اتصال مجدد ویندوز کلاینت در صورت قطعی شبکه.

🚀 Setup Requirements (نیازمندی‌ها)

Python 3.10+ (For Bridge, PC Node, GUI Client)

PySide6 (For Desktop App)

FastAPI & Uvicorn (For Bridge Server)

PyCryptodome (For AES Encryption)

LM Studio (Running locally on the PC Node with API server enabled on port 1234)

“Perfection is achieved, not when there is nothing more to add, but when there is nothing left to take away.”