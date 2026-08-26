"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";

function AcceptForm() {
  const params = useSearchParams();
  const router = useRouter();
  const [token, setToken] = useState(params.get("token") || "");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.acceptInvite({ token, username, password });
      router.replace("/chat");
    } catch (err: any) {
      setError(String(err.message || err));
    }
  }

  return (
    <form className="card-form" onSubmit={onSubmit}>
      <div className="brand-lockup brand-lockup--lg">
        <img src="/logo.png" alt="AI Workspace" width={56} height={56} />
        <div className="brand">AI Workspace</div>
      </div>
      <h1>پذیرش دعوت</h1>
      <input
        placeholder="توکن دعوت"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        required
      />
      <input
        placeholder="نام کاربری"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        required
      />
      <input
        type="password"
        placeholder="رمز عبور (حداقل ۱۰)"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        minLength={10}
        required
      />
      {error ? <div style={{ color: "var(--danger)" }}>{error}</div> : null}
      <button className="btn primary" type="submit">
        ساخت حساب
      </button>
    </form>
  );
}

export default function AcceptInvitePage() {
  return (
    <main className="auth-wrap">
      <Suspense>
        <AcceptForm />
      </Suspense>
    </main>
  );
}
