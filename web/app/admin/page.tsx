"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, User } from "@/lib/api";

export default function AdminPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [invite, setInvite] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [chatModel, setChatModel] = useState("");
  const [embedModel, setEmbedModel] = useState("");
  const [opsMsg, setOpsMsg] = useState("");

  async function load() {
    const [u, list, st, settings] = await Promise.all([
      api.me(),
      api.users(),
      api.adminStats(),
      api.adminSettings(),
    ]);
    if (u.role !== "admin") {
      router.replace("/chat");
      return;
    }
    setUser(u);
    setUsers(list);
    setStats(st);
    setChatModel(settings.default_chat_model || "");
    setEmbedModel(settings.default_embed_model || "");
  }

  useEffect(() => {
    load().catch(() => router.replace("/login"));
  }, [router]);

  async function createInvite() {
    const res = await api.createInvite();
    setInvite(`${window.location.origin}${res.accept_path}`);
  }

  async function createUser(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.createUser({ username, password, role: "user" });
      setUsername("");
      setPassword("");
      await load();
    } catch (err: any) {
      setError(String(err.message || err));
    }
  }

  if (!user) return <main className="auth-wrap muted">…</main>;

  return (
    <main className="panel" style={{ maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem" }}>
        <div>
          <div className="brand-lockup">
            <img src="/logo.png" alt="AI Workspace" width={40} height={40} />
            <div className="brand">داشبورد ادمین</div>
          </div>
          <p className="muted">AI Workspace v20.0.0</p>
        </div>
        <Link className="btn" href="/chat">
          بازگشت به چت
        </Link>
      </div>

      {stats ? (
        <section style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "0.8rem" }}>
          <div className="btn">کاربران: {stats.users}</div>
          <div className="btn">اسناد: {stats.docs}</div>
          <div className="btn">Job فعال: {stats.active_rag_jobs}</div>
          <div className="btn">
            Worker: {stats.worker?.worker_online ? `online/${stats.worker.hw}` : "offline"}
          </div>
        </section>
      ) : null}

      <section style={{ marginTop: "1.2rem" }}>
        <h3>دعوت کاربر</h3>
        <button className="btn primary" onClick={createInvite}>
          ساخت لینک دعوت
        </button>
        {invite ? <p className="muted" style={{ wordBreak: "break-all" }}>{invite}</p> : null}
      </section>

      <section style={{ marginTop: "1.2rem" }}>
        <h3>ایجاد مستقیم کاربر</h3>
        <form onSubmit={createUser} style={{ display: "grid", gap: "0.5rem", maxWidth: 420 }}>
          <input className="btn" placeholder="username" value={username} onChange={(e) => setUsername(e.target.value)} />
          <input
            className="btn"
            type="password"
            placeholder="password min 10"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error ? <div style={{ color: "var(--danger)" }}>{error}</div> : null}
          <button className="btn primary" type="submit">
            ایجاد
          </button>
        </form>
      </section>

      <section style={{ marginTop: "1.2rem" }}>
        <h3>تنظیمات مدل / عملیات</h3>
        <div style={{ display: "grid", gap: "0.5rem", maxWidth: 560 }}>
          <input
            className="btn"
            placeholder="default chat model"
            value={chatModel}
            onChange={(e) => setChatModel(e.target.value)}
          />
          <input
            className="btn"
            placeholder="default embed model"
            value={embedModel}
            onChange={(e) => setEmbedModel(e.target.value)}
          />
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button
              className="btn primary"
              type="button"
              onClick={async () => {
                setOpsMsg("");
                await api.putAdminSettings({
                  default_chat_model: chatModel,
                  default_embed_model: embedModel,
                });
                setOpsMsg("تنظیمات ذخیره شد. اگر embed عوض شد، Reindex لازم است.");
              }}
            >
              ذخیره تنظیمات
            </button>
            <button
              className="btn"
              type="button"
              onClick={async () => {
                setOpsMsg("در حال reindex…");
                const r = await api.adminReindex();
                setOpsMsg(`Reindex: ok=${r.ok} failed=${r.failed} total=${r.total}`);
              }}
            >
              Reindex همه اسناد
            </button>
            <button
              className="btn"
              type="button"
              onClick={async () => {
                try {
                  await api.adminUnload();
                  setOpsMsg("Unload models ارسال شد.");
                } catch (e: any) {
                  setOpsMsg(String(e.message || e));
                }
              }}
            >
              Unload models
            </button>
          </div>
          {opsMsg ? <p className="muted">{opsMsg}</p> : null}
        </div>
      </section>

      <section style={{ marginTop: "1.2rem" }}>
        <h3>کاربران</h3>
        <table className="table">
          <thead>
            <tr>
              <th>نام</th>
              <th>نقش</th>
              <th>فعال</th>
              <th>عملیات</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.username}</td>
                <td>{u.role}</td>
                <td>{u.is_active ? "بله" : "خیر"}</td>
                <td>
                  <button
                    className="btn"
                    onClick={async () => {
                      await api.updateUser(u.id, { is_active: !u.is_active });
                      await load();
                    }}
                  >
                    {u.is_active ? "غیرفعال" : "فعال"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
