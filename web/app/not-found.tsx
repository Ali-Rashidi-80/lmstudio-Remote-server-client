import Link from "next/link";

export default function NotFound() {
  return (
    <main className="auth-wrap">
      <div className="card-form">
        <div className="brand-lockup">
          <img src="/logo.png" alt="AI Workspace" width={40} height={40} />
          <div className="brand">AI Workspace</div>
        </div>
        <h1>صفحه یافت نشد (۴۰۴)</h1>
        <p className="muted" style={{ margin: 0 }}>
          مسیر درخواستی در سامانه موجود نیست.
        </p>
        <Link className="btn primary" href="/chat">
          بازگشت به گفتگو
        </Link>
      </div>
    </main>
  );
}
