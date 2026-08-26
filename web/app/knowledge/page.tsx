"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function KnowledgePage() {
  const router = useRouter();
  const [docs, setDocs] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function load() {
    setDocs(await api.docs());
  }

  useEffect(() => {
    api.me().then(load).catch(() => router.replace("/login"));
  }, [router]);

  async function onUpload(file: File | null) {
    if (!file) return;
    setBusy(true);
    setMsg("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${api.apiUrl}/api/knowledge/docs`, {
        method: "POST",
        credentials: "include",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Upload failed");
      }
      setMsg("آپلود و ایندکس انجام شد (یا در صف قرار گرفت).");
      await load();
    } catch (e: any) {
      setMsg(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="panel" style={{ maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <div>
          <div className="brand-lockup">
            <img src="/logo.png" alt="AI Workspace" width={40} height={40} />
            <div className="brand">پایگاه دانش</div>
          </div>
          <p className="muted">PDF / TXT / MD / DOCX — امبدینگ از LM Studio EmbeddingGemma</p>
        </div>
        <Link className="btn" href="/chat">
          بازگشت
        </Link>
      </div>
      <input
        type="file"
        accept=".pdf,.txt,.md,.docx"
        disabled={busy}
        onChange={(e) => onUpload(e.target.files?.[0] || null)}
      />
      {msg ? <p className="muted">{msg}</p> : null}
      <table className="table">
        <thead>
          <tr>
            <th>عنوان</th>
            <th>وضعیت</th>
            <th>اشتراک</th>
            <th>حجم</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {docs.map((d) => (
            <tr key={d.id}>
              <td>{d.title}</td>
              <td>{d.status}</td>
              <td>{d.is_shared ? "اشتراکی" : "خصوصی"}</td>
              <td>{d.size_bytes}</td>
              <td style={{ display: "flex", gap: "0.35rem" }}>
                <button
                  className="btn"
                  onClick={async () => {
                    await api.patchDoc(d.id, !d.is_shared);
                    await load();
                  }}
                >
                  {d.is_shared ? "خصوصی کن" : "اشتراک"}
                </button>
                <button
                  className="btn danger"
                  onClick={async () => {
                    await api.deleteDoc(d.id);
                    await load();
                  }}
                >
                  حذف
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
