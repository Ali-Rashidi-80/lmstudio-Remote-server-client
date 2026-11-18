"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useThemeSync } from "@/components/AppShell";

function AcceptForm() {
  const params = useSearchParams();
  const router = useRouter();
  const [token, setToken] = useState(params.get("token") || "");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.acceptInvite({
        token: token.trim(),
        username: username.trim(),
        password,
        email: email.trim() || undefined,
      });
      router.replace("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در فعال‌سازی دعوت");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="card-form" onSubmit={onSubmit}>
      <div className="brand-lockup brand-lockup--lg">
        <img src="/logo.png" alt="AI Workspace" width={56} height={56} />
        <div>
          <div className="brand">AI Workspace</div>
          <div className="muted">ساخت حساب با دعوت‌نامه</div>
        </div>
      </div>
      <h1>پذیرش دعوت</h1>

      <label className="field-label">
        <span>توکن دعوت</span>
        <input
          className="input"
          placeholder="توکن دعوت"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          required
        />
      </label>

      <label className="field-label">
        <span>نام کاربری</span>
        <input
          className="input"
          placeholder="حداقل ۳ کاراکتر"
          minLength={3}
          maxLength={64}
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
      </label>

      <label className="field-label">
        <span>ایمیل (اختیاری)</span>
        <input
          className="input"
          type="email"
          placeholder="name@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </label>

      <label className="field-label">
        <span>رمز عبور</span>
        <div className="pw-wrap">
          <input
            className="input"
            type={showPw ? "text" : "password"}
            placeholder="حداقل ۱۰ کاراکتر"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={10}
            required
          />
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => setShowPw((v) => !v)}
          >
            {showPw ? "مخفی" : "نمایش"}
          </button>
        </div>
      </label>

      {error ? <div className="form-error">{error}</div> : null}

      <button className="btn primary" type="submit" disabled={loading}>
        {loading ? "در حال ساخت حساب…" : "ساخت حساب"}
      </button>

      <div className="muted" style={{ textAlign: "center" }}>
        قبلاً حساب دارید؟ <Link href="/login">ورود</Link>
      </div>
    </form>
  );
}

export default function AcceptInvitePage() {
  const [theme, toggleTheme] = useThemeSync();

  return (
    <main className="auth-wrap">
      <button
        type="button"
        className="btn btn-sm auth-theme-corner"
        onClick={toggleTheme}
      >
        {theme === "dark" ? "تم روشن" : "تم تاریک"}
      </button>
      <Suspense fallback={<div className="card-form muted">در حال بارگذاری…</div>}>
        <AcceptForm />
      </Suspense>
    </main>
  );
}
