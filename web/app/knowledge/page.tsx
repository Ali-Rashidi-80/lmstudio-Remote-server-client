"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  formatBytes,
  formatDateTime,
  formatNumber,
  KnowledgeDocItem,
  RagSource,
  User,
} from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { ConfirmDialog, ModalDialog } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";

const MAX_DOC_BYTES = 10 * 1024 * 1024;
const ALLOWED_EXT = [".pdf", ".txt", ".md", ".docx"];

function statusLabel(status: string): { label: string; cls: string } {
  if (status === "ready") return { label: "آماده", cls: "badge--ok" };
  if (status === "failed") return { label: "خطا", cls: "badge--danger" };
  if (status === "running") return { label: "در حال پردازش", cls: "badge--warn" };
  return { label: "در صف", cls: "badge--warn" };
}

export default function KnowledgePage() {
  const router = useRouter();
  const toast = useToast();

  const [user, setUser] = useState<User | null>(null);
  const [docs, setDocs] = useState<KnowledgeDocItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const [searchDoc, setSearchDoc] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const [ragQuery, setRagQuery] = useState("");
  const [ragTopK, setRagTopK] = useState(5);
  const [ragSearching, setRagSearching] = useState(false);
  const [ragResults, setRagResults] = useState<RagSource[]>([]);

  const [renameTarget, setRenameTarget] = useState<KnowledgeDocItem | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeDocItem | null>(null);
  const [modalBusy, setModalBusy] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const pollTimerRef = useRef<number | null>(null);

  const loadDocs = useCallback(
    async (signal?: AbortSignal) => {
      const list = await api.docs({ q: searchDoc, status: statusFilter }, signal);
      setDocs(list);
    },
    [searchDoc, statusFilter]
  );

  useEffect(() => {
    api
      .me()
      .then(async (u) => {
        setUser(u);
      })
      .catch(() => router.replace("/login"));
    return () => {
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current);
      }
    };
  }, [router]);

  useEffect(() => {
    if (!user) return undefined;
    const ctrl = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      loadDocs(ctrl.signal)
        .catch((err) => {
          if (err instanceof DOMException && err.name === "AbortError") return;
          toast.error(err instanceof Error ? err.message : "خطا در بارگذاری اسناد");
        })
        .finally(() => setLoading(false));
    }, 200);
    return () => {
      ctrl.abort();
      window.clearTimeout(timer);
    };
  }, [user, loadDocs, toast]);

  function pollJob(jobId: string, tries = 0) {
    if (tries > 60) return;
    pollTimerRef.current = window.setTimeout(async () => {
      try {
        const job = await api.jobStatus(jobId);
        if (job.status === "completed") {
          toast.success("ایندکس سند با موفقیت کامل شد.");
          await loadDocs();
          return;
        }
        if (job.status === "failed") {
          toast.error(job.error || "پردازش سند با خطا مواجه شد.");
          await loadDocs();
          return;
        }
        pollJob(jobId, tries + 1);
      } catch {
        /* stop polling quietly if user navigated or job removed */
      }
    }, 1200);
  }

  async function onUpload(file: File | null) {
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (!ALLOWED_EXT.some((ext) => lower.endsWith(ext))) {
      toast.error("فرمت مجاز: PDF، TXT، MD یا DOCX");
      return;
    }
    if (file.size > MAX_DOC_BYTES) {
      toast.error("حداکثر حجم مجاز فایل ۱۰ مگابایت است.");
      return;
    }

    setBusy(true);
    try {
      const res = await api.uploadDoc(file);
      toast.info("فایل آپلود شد و در صف پردازش قرار گرفت.");
      await loadDocs();
      if (res.job_id) {
        pollJob(res.job_id);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در آپلود فایل");
    } finally {
      setBusy(false);
    }
  }

  async function onVectorSearch(e: FormEvent) {
    e.preventDefault();
    if (!ragQuery.trim()) return;
    setRagSearching(true);
    try {
      const res = await api.searchKnowledge(ragQuery.trim(), ragTopK);
      setRagResults(res.sources);
      if (res.sources.length === 0) {
        toast.info("قطعه‌ای مرتبط با عبارت شما پیدا نشد.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در جستجوی برداری");
    } finally {
      setRagSearching(false);
    }
  }

  async function onConfirmRename(e: FormEvent) {
    e.preventDefault();
    if (!renameTarget || !renameTitle.trim()) return;
    setModalBusy(true);
    try {
      await api.patchDoc(renameTarget.id, { title: renameTitle.trim() });
      setRenameTarget(null);
      await loadDocs();
      toast.success("عنوان سند تغییر یافت.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در تغییر عنوان سند");
    } finally {
      setModalBusy(false);
    }
  }

  async function onConfirmDelete() {
    if (!deleteTarget) return;
    setModalBusy(true);
    try {
      await api.deleteDoc(deleteTarget.id);
      setDeleteTarget(null);
      await loadDocs();
      toast.success("سند و بردارهای آن حذف شدند.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در حذف سند");
    } finally {
      setModalBusy(false);
    }
  }

  if (!user) return <main className="auth-wrap muted">در حال بارگذاری…</main>;

  return (
    <AppShell user={user} pageTitle="پایگاه دانش (RAG)">
      <div style={{ display: "grid", gap: "1rem" }}>
        <section className="card" style={{ display: "grid", gap: "0.75rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
            <div>
              <h2 className="card-title" style={{ marginBottom: "0.2rem" }}>
                بارگذاری سند جدید
              </h2>
              <p className="muted" style={{ margin: 0 }}>
                فرمت‌های مجاز: PDF, TXT, MD, DOCX — حداکثر ۱۰ مگابایت
              </p>
            </div>
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
            >
              {busy ? "در حال آپلود…" : "انتخاب فایل"}
            </button>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt,.md,.docx"
            disabled={busy}
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              e.target.value = "";
              void onUpload(f);
            }}
          />

          <div
            className={`dropzone ${dragOver ? "is-dragover" : ""}`}
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              const f = e.dataTransfer.files?.[0] || null;
              void onUpload(f);
            }}
          >
            فایل را اینجا رها کنید یا برای انتخاب کلیک کنید
          </div>
        </section>

        <section className="card" style={{ display: "grid", gap: "0.75rem" }}>
          <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
            <h2 className="card-title" style={{ margin: 0, marginInlineEnd: "auto" }}>
              فهرست اسناد ({formatNumber(docs.length)})
            </h2>
            <input
              className="input"
              style={{ maxWidth: 240 }}
              placeholder="فیلتر بر اساس عنوان…"
              value={searchDoc}
              onChange={(e) => setSearchDoc(e.target.value)}
            />
            <select
              className="select"
              style={{ maxWidth: 160 }}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">همه وضعیت‌ها</option>
              <option value="ready">آماده</option>
              <option value="queued">در صف</option>
              <option value="running">در حال پردازش</option>
              <option value="failed">خطا</option>
            </select>
          </div>

          {loading ? (
            <div style={{ display: "grid", gap: "0.5rem" }}>
              <div className="skeleton" style={{ width: "100%" }} />
              <div className="skeleton" style={{ width: "85%" }} />
            </div>
          ) : docs.length === 0 ? (
            <div className="empty-state">
              <p className="muted" style={{ margin: 0 }}>
                هنوز سندی در پایگاه دانش وجود ندارد.
              </p>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>عنوان</th>
                    <th>وضعیت</th>
                    <th>دسترسی</th>
                    <th>حجم</th>
                    <th>تاریخ ثبت</th>
                    <th>عملیات</th>
                  </tr>
                </thead>
                <tbody>
                  {docs.map((d) => {
                    const st = statusLabel(d.status);
                    const owner = d.is_owner !== false;
                    return (
                      <tr key={d.id}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{d.title}</div>
                          {!owner ? (
                            <span className="badge" style={{ marginTop: "0.2rem" }}>
                              اشتراکی از سایرین
                            </span>
                          ) : null}
                          {d.status === "failed" && d.last_error ? (
                            <div className="muted" style={{ color: "var(--danger)", fontSize: "0.8rem" }}>
                              {d.last_error}
                            </div>
                          ) : null}
                        </td>
                        <td>
                          <span className={`badge ${st.cls}`}>{st.label}</span>
                        </td>
                        <td>{d.is_shared ? "اشتراکی" : "خصوصی"}</td>
                        <td>{formatBytes(d.size_bytes)}</td>
                        <td>{formatDateTime(d.created_at)}</td>
                        <td>
                          {owner ? (
                            <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
                              <button
                                type="button"
                                className="btn btn-xs"
                                onClick={() => {
                                  setRenameTarget(d);
                                  setRenameTitle(d.title);
                                }}
                              >
                                تغییر نام
                              </button>
                              <button
                                type="button"
                                className="btn btn-xs"
                                onClick={async () => {
                                  try {
                                    await api.patchDoc(d.id, { is_shared: !d.is_shared });
                                    await loadDocs();
                                  } catch (err) {
                                    toast.error(err instanceof Error ? err.message : "خطا");
                                  }
                                }}
                              >
                                {d.is_shared ? "خصوصی کن" : "اشتراک‌گذاری"}
                              </button>
                              <button
                                type="button"
                                className="btn btn-xs danger"
                                onClick={() => setDeleteTarget(d)}
                              >
                                حذف
                              </button>
                            </div>
                          ) : (
                            <span className="muted">فقط خواندنی</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="card" style={{ display: "grid", gap: "0.75rem" }}>
          <h2 className="card-title" style={{ margin: 0 }}>
            پیش‌نمایش جستجوی برداری (RAG Test)
          </h2>
          <form
            onSubmit={onVectorSearch}
            style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}
          >
            <input
              className="input"
              style={{ flex: "1 1 260px" }}
              placeholder="پرسش یا عبارت کلیدی برای بازیابی از اسناد…"
              value={ragQuery}
              onChange={(e) => setRagQuery(e.target.value)}
            />
            <select
              className="select"
              style={{ width: 120 }}
              value={ragTopK}
              onChange={(e) => setRagTopK(Number(e.target.value))}
            >
              <option value={3}>۳ نتیجه</option>
              <option value={5}>۵ نتیجه</option>
              <option value={10}>۱۰ نتیجه</option>
            </select>
            <button type="submit" className="btn primary" disabled={ragSearching}>
              {ragSearching ? "در حال جستجو…" : "جستجوی معنایی"}
            </button>
          </form>

          {ragResults.length > 0 ? (
            <div style={{ display: "grid", gap: "0.5rem" }}>
              {ragResults.map((r, idx) => (
                <div key={r.chunk_id || idx} className="sources" style={{ marginTop: 0 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                    <strong>{r.doc_title}</strong>
                    {typeof r.score === "number" ? (
                      <span className="badge badge--ok">
                        شباهت: {formatNumber(Math.round(r.score * 100))}%
                      </span>
                    ) : null}
                  </div>
                  <div>{r.snippet}</div>
                </div>
              ))}
            </div>
          ) : null}
        </section>
      </div>

      <ModalDialog
        open={Boolean(renameTarget)}
        title="تغییر عنوان سند"
        onClose={() => setRenameTarget(null)}
      >
        <form onSubmit={onConfirmRename} className="stack-form">
          <label className="field-label">
            <span>عنوان جدید</span>
            <input
              className="input"
              value={renameTitle}
              onChange={(e) => setRenameTitle(e.target.value)}
              maxLength={512}
              required
            />
          </label>
          <div className="dialog-foot" style={{ padding: 0 }}>
            <button type="button" className="btn" onClick={() => setRenameTarget(null)}>
              انصراف
            </button>
            <button type="submit" className="btn primary" disabled={modalBusy}>
              {modalBusy ? "در حال ذخیره…" : "ذخیره"}
            </button>
          </div>
        </form>
      </ModalDialog>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="حذف سند"
        message={`آیا از حذف سند «${deleteTarget?.title || ""}» مطمئن هستید؟`}
        confirmLabel="حذف سند"
        danger
        busy={modalBusy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void onConfirmDelete()}
      />
    </AppShell>
  );
}
