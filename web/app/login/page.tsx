"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await api.login(username, password);
      if (res.user.role === "admin") {
        // stay flexible; chat is primary
      }
      router.replace("/chat");
    } catch (err: any) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-wrap">
      <form className="card-form" onSubmit={onSubmit}>
        <div className="brand">AI Workspace</div>
        <h1>ورود</h1>
        <p className="muted">دسترسی فقط با دعوت یا حساب ساخته‌شده توسط ادمین.</p>
        <input
          placeholder="نام کاربری"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="رمز عبور (حداقل ۱۰ کاراکتر)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          minLength={10}
          required
        />
        {error ? <div style={{ color: "var(--danger)" }}>{error}</div> : null}
        <button className="btn primary" disabled={loading} type="submit">
          {loading ? "…" : "ورود"}
        </button>
      </form>
    </main>
  );
}
