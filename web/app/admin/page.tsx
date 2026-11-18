"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AdminModelsInfo,
  AdminStats,
  api,
  AuditLogItem,
  formatDateTime,
  formatNumber,
  InviteItem,
  User,
} from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";

export default function AdminPage() {
  const router = useRouter();
  const toast = useToast();

  const [user, setUser] = useState<User | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [invites, setInvites] = useState<InviteItem[]>([]);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [modelsInfo, setModelsInfo] = useState<AdminModelsInfo | null>(null);

  const [userFilter, setUserFilter] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("user");
  const [latestInviteLink, setLatestInviteLink] = useState("");

  const [username, setUsername] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newRole, setNewRole] = useState("user");
  const [createErr, setCreateErr] = useState("");

  const [chatModel, setChatModel] = useState("");
  const [embedModel, setEmbedModel] = useState("");
  const [opsBusy, setOpsBusy] = useState(false);

  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditActionFilter, setAuditActionFilter] = useState("");
  const [auditPage, setAuditPage] = useState(0);

  const [confirmKind, setConfirmKind] = useState<
    | null
    | { type: "unload" }
    | { type: "reindex" }
    | { type: "deactivate"; target: User }
    | { type: "revoke_invite"; invite: InviteItem }
  >(null);

  const AUDIT_LIMIT = 20;

  const loadAudits = useCallback(
    async (page = auditPage, action = auditActionFilter, signal?: AbortSignal) => {
      const res = await api.adminAuditLogs(
        { action, limit: AUDIT_LIMIT, offset: page * AUDIT_LIMIT },
        signal
      );
      setAuditLogs(res.items);
      setAuditTotal(res.total);
    },
    [auditPage, auditActionFilter]
  );

  const loadAll = useCallback(async () => {
    const u = await api.me();
    if (u.role !== "admin") {
      router.replace("/chat");
      return;
    }
    const [list, invList, st, settings, mdl] = await Promise.all([
      api.users(),
      api.listInvites(),
      api.adminStats(),
      api.adminSettings(),
      api.adminModels().catch(() => null),
    ]);
    setUser(u);
    setUsers(list);
    setInvites(invList);
    setStats(st);
    setModelsInfo(mdl);
    setChatModel(settings.default_chat_model || "");
    setEmbedModel(settings.default_embed_model || "");
    await loadAudits(0, "");
  }, [router, loadAudits]);

  useEffect(() => {
    loadAll().catch(() => router.replace("/login"));
  }, [loadAll, router]);

  useEffect(() => {
    if (!user) return undefined;
    const ctrl = new AbortController();
    loadAudits(auditPage, auditActionFilter, ctrl.signal).catch((err) => {
      if (err instanceof DOMException && err.name === "AbortError") return;
      toast.error(err instanceof Error ? err.message : "خطا در بارگذاری لاگ‌ها");
    });
    return () => ctrl.abort();
  }, [user, auditPage, auditActionFilter, loadAudits, toast]);

  const filteredUsers = useMemo(() => {
    const q = userFilter.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        u.username.toLowerCase().includes(q) ||
        (u.email || "").toLowerCase().includes(q) ||
        u.role.toLowerCase().includes(q)
    );
  }, [users, userFilter]);

  const liveModelIds = useMemo(() => {
    const raw = modelsInfo?.available_models || [];
    return raw.map((m) => (typeof m === "string" ? m : String(m.id || ""))).filter(Boolean);
  }, [modelsInfo]);

  async function onCreateInvite(e: FormEvent) {
    e.preventDefault();
    try {
      const res = await api.createInvite(inviteEmail.trim() || undefined, inviteRole);
      const fullUrl = `${window.location.origin}${res.accept_path}`;
      setLatestInviteLink(fullUrl);
      setInviteEmail("");
      setInvites(await api.listInvites());
      toast.success("لینک دعوت ایجاد شد.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در ساخت دعوت‌نامه");
    }
  }

  async function onCreateUser(e: FormEvent) {
    e.preventDefault();
    setCreateErr("");
    try {
      await api.createUser({
        username: username.trim(),
        password,
        email: newEmail.trim() || undefined,
        role: newRole,
      });
      setUsername("");
      setNewEmail("");
      setPassword("");
      setUsers(await api.users());
      toast.success("کاربر جدید ایجاد شد.");
    } catch (err) {
      setCreateErr(err instanceof Error ? err.message : "خطا در ایجاد کاربر");
    }
  }

  async function copyText(val: string) {
    try {
      await navigator.clipboard.writeText(val);
      toast.info("در کلیپ‌بورد کپی شد.");
    } catch {
      toast.error("کپی انجام نشد.");
    }
  }

  function downloadAuditJson() {
    const blob = new Blob([JSON.stringify(auditLogs, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit-logs-page-${auditPage + 1}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function runConfirmedAction() {
    if (!confirmKind) return;
    setOpsBusy(true);
    try {
      if (confirmKind.type === "unload") {
        await api.adminUnload();
        toast.success("درخواست تخلیه مدل‌ها به Worker ارسال شد.");
      } else if (confirmKind.type === "reindex") {
        const r = await api.adminReindex();
        toast.success(`بازنمایه کامل شد: موفق=${r.ok} خطا=${r.failed} کل=${r.total}`);
      } else if (confirmKind.type === "deactivate") {
        await api.updateUser(confirmKind.target.id, { is_active: !confirmKind.target.is_active });
        setUsers(await api.users());
        toast.success("وضعیت کاربر تغییر یافت.");
      } else if (confirmKind.type === "revoke_invite") {
        await api.revokeInvite(confirmKind.invite.id);
        setInvites(await api.listInvites());
        toast.success("دعوت‌نامه باطل شد.");
      }
      setConfirmKind(null);
      await loadAudits(auditPage, auditActionFilter);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در اجرای عملیات");
    } finally {
      setOpsBusy(false);
    }
  }

  if (!user) return <main className="auth-wrap muted">در حال بارگذاری…</main>;

  return (
    <AppShell
      user={user}
      workerOnline={Boolean(stats?.worker?.worker_online)}
      workerStatus={
        stats?.worker?.worker_online ? `${stats.worker.hw} (آنلاین)` : "آفلاین"
      }
      pageTitle={`مدیریت سامانه${stats?.app_version ? ` · v${stats.app_version}` : ""}`}
    >
      <div style={{ display: "grid", gap: "1rem" }}>
        {stats ? (
          <section className="kpi-grid">
            <div className="kpi-card">
              <span className="muted">کاربران</span>
              <span className="kpi-value">{formatNumber(stats.users)}</span>
            </div>
            <div className="kpi-card">
              <span className="muted">اسناد دانش</span>
              <span className="kpi-value">{formatNumber(stats.docs)}</span>
            </div>
            <div className="kpi-card">
              <span className="muted">بردارهای ذخیره</span>
              <span className="kpi-value">{formatNumber(stats.chunks || 0)}</span>
            </div>
            <div className="kpi-card">
              <span className="muted">کارهای فعال RAG</span>
              <span className="kpi-value">{formatNumber(stats.active_rag_jobs)}</span>
            </div>
            <div className="kpi-card">
              <span className="muted">وضعیت Worker</span>
              <span className="kpi-value" style={{ fontSize: "1.05rem" }}>
                {stats.worker?.worker_online ? `آنلاین (${stats.worker.hw})` : "آفلاین"}
              </span>
            </div>
          </section>
        ) : null}

        <div className="split-grid">
          <section className="card" style={{ display: "grid", gap: "0.75rem" }}>
            <h2 className="card-title" style={{ margin: 0 }}>
              ساخت لینک دعوت
            </h2>
            <form onSubmit={onCreateInvite} className="stack-form">
              <label className="field-label">
                <span>ایمیل دعوت‌شونده (اختیاری)</span>
                <input
                  className="input"
                  type="email"
                  placeholder="user@example.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                />
              </label>
              <label className="field-label">
                <span>نقش</span>
                <select
                  className="select"
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value)}
                >
                  <option value="user">کاربر عادی</option>
                  <option value="admin">ادمین</option>
                </select>
              </label>
              <button className="btn primary" type="submit">
                ایجاد دعوت‌نامه
              </button>
            </form>
            {latestInviteLink ? (
              <div className="sources" style={{ marginTop: 0 }}>
                <div style={{ wordBreak: "break-all" }}>{latestInviteLink}</div>
                <button
                  type="button"
                  className="btn btn-xs"
                  onClick={() => void copyText(latestInviteLink)}
                >
                  کپی لینک
                </button>
              </div>
            ) : null}
          </section>

          <section className="card" style={{ display: "grid", gap: "0.75rem" }}>
            <h2 className="card-title" style={{ margin: 0 }}>
              ایجاد مستقیم کاربر
            </h2>
            <form onSubmit={onCreateUser} className="stack-form">
              <label className="field-label">
                <span>نام کاربری</span>
                <input
                  className="input"
                  placeholder="حداقل ۳ کاراکتر"
                  minLength={3}
                  maxLength={64}
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
                  placeholder="user@example.com"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                />
              </label>
              <label className="field-label">
                <span>نقش</span>
                <select
                  className="select"
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                >
                  <option value="user">کاربر عادی</option>
                  <option value="admin">ادمین</option>
                </select>
              </label>
              <label className="field-label">
                <span>رمز عبور (حداقل ۱۰ کاراکتر)</span>
                <input
                  className="input"
                  type="password"
                  minLength={10}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>
              {createErr ? <div className="form-error">{createErr}</div> : null}
              <button className="btn primary" type="submit">
                ساخت کاربر
              </button>
            </form>
          </section>
        </div>

        <section className="card" style={{ display: "grid", gap: "0.75rem" }}>
          <h2 className="card-title" style={{ margin: 0 }}>
            تنظیمات مدل و عملیات نگهداری
          </h2>
          <div className="split-grid">
            <label className="field-label">
              <span>مدل پیش‌فرض چت</span>
              <input
                className="input"
                list="live-models-list"
                value={chatModel}
                onChange={(e) => setChatModel(e.target.value)}
              />
            </label>
            <label className="field-label">
              <span>مدل پیش‌فرض امبدینگ (تغییر آن نیاز به Reindex دارد)</span>
              <input
                className="input"
                list="live-models-list"
                value={embedModel}
                onChange={(e) => setEmbedModel(e.target.value)}
              />
            </label>
          </div>
          <datalist id="live-models-list">
            {liveModelIds.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn primary"
              onClick={async () => {
                try {
                  await api.putAdminSettings({
                    default_chat_model: chatModel,
                    default_embed_model: embedModel,
                  });
                  toast.success("تنظیمات ذخیره شد.");
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "خطا در ذخیره تنظیمات");
                }
              }}
            >
              ذخیره تنظیمات
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setConfirmKind({ type: "reindex" })}
            >
              Reindex همه اسناد
            </button>
            <button
              type="button"
              className="btn danger"
              onClick={() => setConfirmKind({ type: "unload" })}
            >
              تخلیه مدل‌های حافظه
            </button>
            <button
              type="button"
              className="btn"
              onClick={async () => {
                try {
                  const res = await api.adminPrune();
                  toast.success(
                    `پاکسازی انجام شد: توکن=${res.refresh_tokens} لاگ=${res.audit_logs} کار=${res.rag_jobs}`
                  );
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : "خطا در پاکسازی");
                }
              }}
            >
              پاکسازی لاگ و توکن‌های قدیمی
            </button>
          </div>
        </section>

        <section className="card" style={{ display: "grid", gap: "0.75rem" }}>
          <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
            <h2 className="card-title" style={{ margin: 0, marginInlineEnd: "auto" }}>
              مدیریت کاربران ({formatNumber(filteredUsers.length)})
            </h2>
            <input
              className="input"
              style={{ maxWidth: 240 }}
              placeholder="جستجوی کاربر یا ایمیل…"
              value={userFilter}
              onChange={(e) => setUserFilter(e.target.value)}
            />
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>نام کاربری</th>
                  <th>ایمیل</th>
                  <th>نقش</th>
                  <th>وضعیت</th>
                  <th>عملیات</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((u) => {
                  const isSelf = u.id === user.id;
                  return (
                    <tr key={u.id}>
                      <td>
                        <strong>{u.username}</strong> {isSelf ? <span className="badge">شما</span> : null}
                      </td>
                      <td>{u.email || "—"}</td>
                      <td>
                        <select
                          className="select"
                          style={{ width: 120, padding: "0.3rem 0.5rem" }}
                          value={u.role}
                          disabled={isSelf}
                          onChange={async (e) => {
                            try {
                              await api.updateUser(u.id, { role: e.target.value });
                              setUsers(await api.users());
                              toast.success("نقش کاربر تغییر یافت.");
                            } catch (err) {
                              toast.error(err instanceof Error ? err.message : "خطا");
                            }
                          }}
                        >
                          <option value="user">user</option>
                          <option value="admin">admin</option>
                        </select>
                      </td>
                      <td>
                        <span className={`badge ${u.is_active ? "badge--ok" : "badge--danger"}`}>
                          {u.is_active ? "فعال" : "غیرفعال"}
                        </span>
                      </td>
                      <td>
                        <button
                          type="button"
                          className={`btn btn-xs ${u.is_active ? "danger" : ""}`}
                          disabled={isSelf}
                          onClick={() => setConfirmKind({ type: "deactivate", target: u })}
                        >
                          {u.is_active ? "غیرفعال‌سازی" : "فعال‌سازی"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card" style={{ display: "grid", gap: "0.75rem" }}>
          <h2 className="card-title" style={{ margin: 0 }}>
            دعوت‌نامه‌ها ({formatNumber(invites.length)})
          </h2>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>ایمیل</th>
                  <th>نقش</th>
                  <th>وضعیت</th>
                  <th>انقضا</th>
                  <th>عملیات</th>
                </tr>
              </thead>
              <tbody>
                {invites.map((inv) => {
                  const used = Boolean(inv.used_at);
                  const expired = !used && new Date(inv.expires_at).getTime() < Date.now();
                  return (
                    <tr key={inv.id}>
                      <td>{inv.email || "عمومی"}</td>
                      <td>{inv.role}</td>
                      <td>
                        {used ? (
                          <span className="badge badge--ok">استفاده‌شده</span>
                        ) : expired ? (
                          <span className="badge badge--danger">منقضی</span>
                        ) : (
                          <span className="badge badge--warn">در انتظار</span>
                        )}
                      </td>
                      <td>{formatDateTime(inv.expires_at)}</td>
                      <td>
                        <div style={{ display: "flex", gap: "0.35rem" }}>
                          {inv.token && !used && !expired ? (
                            <button
                              type="button"
                              className="btn btn-xs"
                              onClick={() =>
                                void copyText(
                                  `${window.location.origin}/accept-invite?token=${inv.token}`
                                )
                              }
                            >
                              کپی لینک
                            </button>
                          ) : null}
                          {!used ? (
                            <button
                              type="button"
                              className="btn btn-xs danger"
                              onClick={() => setConfirmKind({ type: "revoke_invite", invite: inv })}
                            >
                              لغو
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="card" style={{ display: "grid", gap: "0.75rem" }}>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
            <h2 className="card-title" style={{ margin: 0, marginInlineEnd: "auto" }}>
              لاگ ممیزی رویدادها ({formatNumber(auditTotal)})
            </h2>
            <input
              className="input"
              style={{ maxWidth: 220 }}
              placeholder="فیلتر اکشن (مثال: login)"
              value={auditActionFilter}
              onChange={(e) => {
                setAuditPage(0);
                setAuditActionFilter(e.target.value);
              }}
            />
            <button type="button" className="btn btn-sm" onClick={downloadAuditJson}>
              خروجی JSON
            </button>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>زمان</th>
                  <th>عملیات</th>
                  <th>شناسه کاربر</th>
                  <th>جزئیات</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.map((log) => (
                  <tr key={log.id}>
                    <td>{formatDateTime(log.created_at)}</td>
                    <td>
                      <span className="badge">{log.action}</span>
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem" }}>
                      {log.actor_id ? log.actor_id.slice(0, 8) : "system"}
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem" }}>
                      {JSON.stringify(log.detail)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <button
              type="button"
              className="btn btn-sm"
              disabled={auditPage === 0}
              onClick={() => setAuditPage((p) => Math.max(0, p - 1))}
            >
              صفحه قبل
            </button>
            <span className="muted">صفحه {formatNumber(auditPage + 1)}</span>
            <button
              type="button"
              className="btn btn-sm"
              disabled={(auditPage + 1) * AUDIT_LIMIT >= auditTotal}
              onClick={() => setAuditPage((p) => p + 1)}
            >
              صفحه بعد
            </button>
          </div>
        </section>
      </div>

      <ConfirmDialog
        open={Boolean(confirmKind)}
        title={
          confirmKind?.type === "unload"
            ? "تخلیه مدل‌ها"
            : confirmKind?.type === "reindex"
              ? "بازنمایه کامل اسناد"
              : confirmKind?.type === "revoke_invite"
                ? "لغو دعوت‌نامه"
                : "تغییر وضعیت کاربر"
        }
        message={
          confirmKind?.type === "unload"
            ? "آیا از ارسال دستور تخلیه همه مدل‌های بارگذاری‌شده در LM Studio مطمئن هستید؟"
            : confirmKind?.type === "reindex"
              ? "همه اسناد دانش با مدل امبدینگ فعلی دوباره پردازش و بردارسازی می‌شوند. ادامه می‌دهید؟"
              : confirmKind?.type === "revoke_invite"
                ? "این لینک دعوت باطل شده و دیگر قابل استفاده نخواهد بود."
                : `آیا از ${confirmKind?.target.is_active ? "غیرفعال‌سازی" : "فعال‌سازی"} حساب «${confirmKind?.target.username || ""}» مطمئن هستید؟`
        }
        danger={confirmKind?.type === "unload" || confirmKind?.type === "revoke_invite" || Boolean(confirmKind?.type === "deactivate" && confirmKind.target.is_active)}
        busy={opsBusy}
        onCancel={() => setConfirmKind(null)}
        onConfirm={() => void runConfirmedAction()}
      />
    </AppShell>
  );
}
