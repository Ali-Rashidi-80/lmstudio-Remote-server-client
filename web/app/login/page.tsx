"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useThemeSync } from "@/components/AppShell";

export default function LoginPage() {
  const router = useRouter();
  const [theme, toggleTheme] = useThemeSync();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api.login(username.trim(), password);
      router.replace("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "خطا در ورود");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-wrap">
      <button
        type="button"
        className="btn btn-sm auth-theme-corner"
        onClick={toggleTheme}
      >
        {theme === "dark" ? "تم روشن" : "تم تاریک"}
      </button>

      <form className="card-form" onSubmit={onSubmit}>
        <div className="brand-lockup brand-lockup--lg">
          <img src="/logo.png" alt="AI Workspace" width={56} height={56} />
          <div>
            <div className="brand">AI Workspace</div>
            <div className="muted">دروازه امن مدل‌های محلی LM Studio</div>
          </div>
        </div>
        <h1>ورود به حساب</h1>
        <p className="muted" style={{ margin: 0 }}>
          دسترسی فقط با دعوت‌نامه یا حساب ساخته‌شده توسط ادمین.
        </p>

        <label className="field-label">
          <span>نام کاربری</span>
          <input
            className="input"
            placeholder="مثال: admin"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </label>

        <label className="field-label">
          <span>رمز عبور</span>
          <div className="pw-wrap">
            <input
              className="input"
              type={showPw ? "text" : "password"}
              placeholder="حداقل ۱۰ کاراکتر"
              autoComplete="current-password"
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

        <button className="btn primary" disabled={loading} type="submit">
          {loading ? "در حال ورود…" : "ورود"}
        </button>

        <div className="muted" style={{ textAlign: "center" }}>
          لینک دعوت دارید؟ <Link href="/accept-invite">پذیرش دعوت‌نامه</Link>
        </div>
      </form>
    </main>
  );
}
