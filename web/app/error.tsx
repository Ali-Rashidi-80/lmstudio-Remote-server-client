"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="auth-wrap">
      <div className="card-form">
        <div className="brand-lockup">
          <img src="/logo.png" alt="AI Workspace" width={40} height={40} />
          <div className="brand">AI Workspace</div>
        </div>
        <h1>خطای غیرمنتظره در رابط کاربری</h1>
        <p className="muted" style={{ margin: 0 }}>
          {error.message || "امکان نمایش این صفحه وجود ندارد."}
        </p>
        <button type="button" className="btn primary" onClick={() => reset()}>
          تلاش مجدد
        </button>
      </div>
    </main>
  );
}
