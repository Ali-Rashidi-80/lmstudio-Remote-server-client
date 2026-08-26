"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, User, wsUrl } from "@/lib/api";

type Msg = { role: string; content: string; sources?: any[] };

export default function ChatPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<any[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [useRag, setUseRag] = useState(false);
  const [status, setStatus] = useState("offline");
  const [streaming, setStreaming] = useState("");
  const [chatQuery, setChatQuery] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const streamingRef = useRef("");

  async function refreshChats(q?: string) {
    const list = q?.trim() ? await api.chatsSearch(q.trim()) : await api.chats();
    setChats(list);
    if (!activeId && list[0]) setActiveId(list[0].id);
  }

  useEffect(() => {
    api
      .me()
      .then(async (u) => {
        setUser(u);
        await refreshChats();
        // one-time localStorage import
        const flag = localStorage.getItem("aiws_imported");
        const raw = localStorage.getItem("ai_sessions");
        if (!flag && raw) {
          try {
            const parsed = JSON.parse(raw);
            const sessions = Object.values(parsed).map((s: any) => ({
              title: s.title || "Imported",
              history: s.history || [],
            }));
            if (sessions.length) {
              await api.importLocal(sessions);
              localStorage.setItem("aiws_imported", "1");
              await refreshChats();
            }
          } catch {
            /* ignore */
          }
        }
        const { ticket } = await api.wsTicket();
        const ws = new WebSocket(wsUrl(ticket));
        wsRef.current = ws;
        ws.onmessage = (ev) => {
          const data = JSON.parse(ev.data);
          const type = data.type;
          const payload = data.payload || {};
          if (type === "sys_status") {
            setStatus(payload.online ? `online (${payload.hw || "CPU"})` : "offline");
          } else if (type === "rag_sources") {
            setMessages((m) => [
              ...m,
              { role: "system", content: "منابع بازیابی‌شده", sources: payload.sources },
            ]);
          } else if (type === "chunk" || type === "delta") {
            const piece = payload.content || data.content || "";
            streamingRef.current += piece;
            setStreaming(streamingRef.current);
          } else if (type === "full" || type === "done") {
            const finalText =
              payload.content || data.content || streamingRef.current || "";
            if (finalText.trim()) {
              setMessages((m) => [...m, { role: "assistant", content: finalText }]);
            }
            streamingRef.current = "";
            setStreaming("");
          } else if (type === "error") {
            setMessages((m) => [
              ...m,
              { role: "assistant", content: payload.content || "خطا" },
            ]);
            streamingRef.current = "";
            setStreaming("");
          }
        };
        ws.onclose = () => setStatus("disconnected");
      })
      .catch(() => router.replace("/login"));
    return () => wsRef.current?.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  useEffect(() => {
    if (!activeId) return;
    api.messages(activeId).then((rows) =>
      setMessages(rows.map((r) => ({ role: r.role, content: r.content, sources: r.meta?.sources })))
    );
  }, [activeId]);

  async function newChat() {
    const c = await api.createChat("گفتگوی جدید", useRag);
    await refreshChats();
    setActiveId(c.id);
    setMessages([]);
  }

  async function onSend(e: FormEvent) {
    e.preventDefault();
    if (!text.trim() || !wsRef.current || wsRef.current.readyState !== 1) return;
    let chatId = activeId;
    if (!chatId) {
      const c = await api.createChat(text.slice(0, 40), useRag);
      chatId = c.id;
      setActiveId(chatId);
      await refreshChats();
    }
    setMessages((m) => [...m, { role: "user", content: text }]);
    wsRef.current.send(
      JSON.stringify({
        v: 1,
        type: "chat",
        payload: {
          chat_id: chatId,
          content: text,
          use_rag: useRag,
          history: messages
            .filter((x) => x.role === "user" || x.role === "assistant")
            .map((x) => ({ role: x.role, content: x.content })),
        },
      })
    );
    setText("");
  }

  const title = useMemo(
    () => chats.find((c) => c.id === activeId)?.title || "چت",
    [chats, activeId]
  );

  if (!user) return <main className="auth-wrap muted">در حال بارگذاری…</main>;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">AI Workspace</div>
        <div className="muted">Worker: {status}</div>
        <button className="btn primary" onClick={newChat}>
          گفتگوی جدید
        </button>
        <input
          className="btn"
          placeholder="جستجوی عنوان چت"
          value={chatQuery}
          onChange={(e) => {
            const v = e.target.value;
            setChatQuery(v);
            void refreshChats(v);
          }}
        />
        <label className="muted">
          <input
            type="checkbox"
            checked={useRag}
            onChange={(e) => setUseRag(e.target.checked)}
          />{" "}
          استفاده از دانش (RAG)
        </label>
        <div className="list">
          {chats.map((c) => (
            <button
              key={c.id}
              className="btn"
              onClick={() => setActiveId(c.id)}
              style={{
                outline: c.id === activeId ? "1px solid var(--accent)" : undefined,
              }}
            >
              {c.title}
            </button>
          ))}
        </div>
        <div style={{ marginTop: "auto", display: "grid", gap: "0.4rem" }}>
          <Link href="/knowledge">دانش</Link>
          {user.role === "admin" ? <Link href="/admin">داشبورد ادمین</Link> : null}
          <button
            className="btn danger"
            onClick={async () => {
              await api.logout();
              router.replace("/login");
            }}
          >
            خروج ({user.username})
          </button>
        </div>
      </aside>
      <section className="panel">
        <h2 style={{ marginTop: 0 }}>{title}</h2>
        <div className="messages">
          {messages.map((m, i) => (
            <div key={i} className={`bubble ${m.role === "user" ? "user" : "assistant"}`}>
              {m.content}
              {m.sources?.length ? (
                <div className="sources">
                  {m.sources.map((s: any, idx: number) => (
                    <div key={idx}>
                      [{s.doc_title}] {s.snippet?.slice(0, 160)}…
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
          {streaming ? <div className="bubble assistant">{streaming}</div> : null}
        </div>
        <form className="composer" onSubmit={onSend}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="پیام خود را بنویسید…"
          />
          <button className="btn primary" type="submit">
            ارسال
          </button>
        </form>
      </section>
    </div>
  );
}
