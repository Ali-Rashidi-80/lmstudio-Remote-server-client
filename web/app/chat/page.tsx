"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ChatItem, RagSource, User, wsUrl } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { ConfirmDialog, ModalDialog } from "@/components/ConfirmDialog";
import { MarkdownContent } from "@/components/MarkdownContent";
import { useToast } from "@/components/Toast";

type LocalMsg = {
  id?: string;
  role: string;
  content: string;
  sources?: RagSource[];
  imagePreview?: string;
};

const MAX_IMAGE_BYTES = 2 * 1024 * 1024;
const STARTER_PROMPTS = [
  "یک چک‌لیست کوتاه برای بررسی امنیت API بنویس.",
  "معماری پایگاه داده و جریان کار این سامانه را خلاصه کن.",
  "یک تابع پایتون تمیز با تایپ‌هینت برای اعتبارسنجی ورودی بنویس.",
];

export default function ChatPage() {
  const router = useRouter();
  const toast = useToast();

  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<ChatItem[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [messages, setMessages] = useState<LocalMsg[]>([]);
  const [loadingMsgs, setLoadingMsgs] = useState(false);

  const [text, setText] = useState("");
  const [useRag, setUseRag] = useState(false);
  const [useTools, setUseTools] = useState(false);
  const [selectedModel, setSelectedModel] = useState("");
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [imageB64, setImageB64] = useState<string | null>(null);

  const [workerOnline, setWorkerOnline] = useState(false);
  const [workerStatus, setWorkerStatus] = useState("در حال اتصال…");
  const [streaming, setStreaming] = useState("");
  const [generating, setGenerating] = useState(false);
  const [livePhase, setLivePhase] = useState("");
  const [chatQuery, setChatQuery] = useState("");

  const [renameTarget, setRenameTarget] = useState<ChatItem | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ChatItem | null>(null);
  const [modalBusy, setModalBusy] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const streamingRef = useRef("");
  const pendingSourcesRef = useRef<RagSource[] | undefined>(undefined);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const prevSearchRef = useRef("");

  const refreshChats = useCallback(async (q?: string, signal?: AbortSignal) => {
    const list = q?.trim() ? await api.chatsSearch(q.trim(), signal) : await api.chats(signal);
    setChats(list);
    setActiveId((prev) => {
      if (prev && list.some((c) => c.id === prev)) return prev;
      return list[0]?.id || "";
    });
  }, []);

  // Debounced chat search (only fires when user changes search text)
  useEffect(() => {
    if (!user) return undefined;
    if (prevSearchRef.current === chatQuery) return undefined;
    prevSearchRef.current = chatQuery;
    const ctrl = new AbortController();
    const timer = window.setTimeout(() => {
      refreshChats(chatQuery, ctrl.signal).catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        toast.error(err instanceof Error ? err.message : "خطا در جستجوی گفتگوها");
      });
    }, 220);
    return () => {
      ctrl.abort();
      window.clearTimeout(timer);
    };
  }, [chatQuery, user, refreshChats, toast]);

  // Initial auth, models, localStorage migration, and resilient WebSocket connection
  useEffect(() => {
    let disposed = false;

    const connectWs = async () => {
      if (disposed) return;
      try {
        const { ticket } = await api.wsTicket();
        if (disposed) return;
        const ws = new WebSocket(wsUrl(ticket));
        wsRef.current = ws;

        ws.onopen = () => {
          reconnectAttemptsRef.current = 0;
        };

        ws.onmessage = (ev) => {
          let data: Record<string, unknown>;
          try {
            data = JSON.parse(ev.data) as Record<string, unknown>;
          } catch {
            return;
          }
          const type = String(data.type || "");
          const payload = (data.payload as Record<string, unknown> | undefined) || {};

          if (type === "sys_status") {
            const online = Boolean(payload.online);
            const hw = String(payload.hw || "CPU");
            setWorkerOnline(online);
            setWorkerStatus(online ? `${hw} (آنلاین)` : "آفلاین");
          } else if (type === "models_list") {
            const list = Array.isArray(payload.models) ? payload.models : [];
            const ids = list
              .map((m) => (typeof m === "object" && m && "id" in m ? String(m.id) : String(m)))
              .filter((id) => id && !id.toLowerCase().includes("embed") && !id.toLowerCase().includes("mmproj"));
            if (ids.length) {
              setAvailableModels((prev) => Array.from(new Set([...ids, ...prev])));
            }
          } else if (type === "status") {
            const st = String(payload.content || "");
            setLivePhase(st === "thinking" ? "در حال تولید پاسخ…" : st);
          } else if (type === "queue" || type === "tool_event") {
            setLivePhase(String(payload.content || ""));
          } else if (type === "rag_sources") {
            const srcs = Array.isArray(payload.sources) ? (payload.sources as RagSource[]) : undefined;
            pendingSourcesRef.current = srcs;
          } else if (type === "chunk" || type === "delta") {
            const piece = String(payload.content ?? data.content ?? "");
            streamingRef.current += piece;
            setStreaming(streamingRef.current);
            setLivePhase("");
          } else if (type === "full" || type === "done") {
            const finalText = String(
              payload.content ?? data.content ?? streamingRef.current ?? ""
            );
            const attachedSources = pendingSourcesRef.current;
            pendingSourcesRef.current = undefined;
            if (finalText.trim()) {
              setMessages((prev) => [
                ...prev,
                { role: "assistant", content: finalText, sources: attachedSources },
              ]);
            }
            streamingRef.current = "";
            setStreaming("");
            setGenerating(false);
            setLivePhase("");
            void refreshChats();
          } else if (type === "error") {
            const msg = String(payload.content || "خطا در پردازش");
            pendingSourcesRef.current = undefined;
            setMessages((prev) => [...prev, { role: "assistant", content: `⚠️ ${msg}` }]);
            streamingRef.current = "";
            setStreaming("");
            setGenerating(false);
            setLivePhase("");
            toast.error(msg);
          }
        };

        ws.onclose = () => {
          setWorkerOnline(false);
          setWorkerStatus("قطع اتصال — تلاش مجدد…");
          setGenerating(false);
          if (!disposed) {
            const delay = Math.min(15000, 1000 * 2 ** reconnectAttemptsRef.current);
            reconnectAttemptsRef.current += 1;
            reconnectTimerRef.current = window.setTimeout(() => {
              void connectWs();
            }, delay);
          }
        };
      } catch {
        if (!disposed) {
          const delay = Math.min(15000, 1500 * 2 ** reconnectAttemptsRef.current);
          reconnectAttemptsRef.current += 1;
          reconnectTimerRef.current = window.setTimeout(() => {
            void connectWs();
          }, delay);
        }
      }
    };

    api
      .me()
      .then(async (u) => {
        if (disposed) return;
        setUser(u);
        const [modelsRes] = await Promise.all([
          api.chatModels().catch(() => null),
          refreshChats(),
        ]);
        if (modelsRes) {
          setAvailableModels(modelsRes.available_models);
          setSelectedModel((prev) => prev || modelsRes.default_chat_model);
          setWorkerOnline(modelsRes.worker.worker_online);
          setWorkerStatus(
            modelsRes.worker.worker_online ? `${modelsRes.worker.hw} (آنلاین)` : "آفلاین"
          );
        }

        const flag = localStorage.getItem("aiws_imported");
        const raw = localStorage.getItem("ai_sessions");
        if (!flag && raw) {
          try {
            const parsed = JSON.parse(raw) as Record<
              string,
              { title?: string; history?: unknown[] }
            >;
            const sessions = Object.values(parsed).map((s) => ({
              title: s.title || "Imported",
              history: s.history || [],
            }));
            if (sessions.length) {
              await api.importLocal(sessions);
              localStorage.setItem("aiws_imported", "1");
              await refreshChats();
            }
          } catch {
            /* ignore corrupt local dump */
          }
        }
        await connectWs();
      })
      .catch(() => router.replace("/login"));

    return () => {
      disposed = true;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      wsRef.current?.close();
    };
  }, [router, refreshChats, toast]);

  // Sync active chat settings & load history
  const activeChat = useMemo(
    () => chats.find((c) => c.id === activeId) || null,
    [chats, activeId]
  );

  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return undefined;
    }
    const ctrl = new AbortController();
    setLoadingMsgs(true);
    api
      .messages(activeId, ctrl.signal)
      .then((rows) => {
        setMessages(
          rows.map((r) => ({
            id: r.id,
            role: r.role,
            content: r.content,
            sources: r.meta?.sources,
          }))
        );
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        toast.error(err instanceof Error ? err.message : "خطا در دریافت پیام‌ها");
      })
      .finally(() => setLoadingMsgs(false));
    return () => ctrl.abort();
  }, [activeId, toast]);

  useEffect(() => {
    if (activeChat) {
      setUseRag(activeChat.use_rag);
      if (activeChat.model) {
        setSelectedModel(activeChat.model);
      }
    }
  }, [activeChat]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  async function newChat() {
    try {
      const c = await api.createChat("گفتگوی جدید", useRag, selectedModel || null);
      setChats((prev) => [c, ...prev.filter((item) => item.id !== c.id)]);
      setActiveId(c.id);
      setMessages([]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در ساخت گفتگو");
    }
  }

  async function submitSend() {
    const trimmed = text.trim();
    if ((!trimmed && !imageB64) || generating) return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      toast.error("اتصال WebSocket برقرار نیست. چند لحظه صبر کنید.");
      return;
    }

    let chatId = activeId;
    if (!chatId) {
      try {
        const c = await api.createChat(
          (trimmed || "گفتگوی تصویری").slice(0, 48),
          useRag,
          selectedModel || null
        );
        chatId = c.id;
        setActiveId(chatId);
        await refreshChats(chatQuery);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "خطا در ایجاد گفتگو");
        return;
      }
    }

    const historyPayload = messages
      .filter((x) => x.role === "user" || x.role === "assistant")
      .map((x) => ({ role: x.role, content: x.content }));

    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: trimmed || "[تصویر]",
        imagePreview: imageB64 || undefined,
      },
    ]);

    streamingRef.current = "";
    pendingSourcesRef.current = undefined;
    setStreaming("");
    setGenerating(true);
    setLivePhase("در حال ارسال…");

    wsRef.current.send(
      JSON.stringify({
        v: 1,
        type: "chat",
        payload: {
          chat_id: chatId,
          content: trimmed,
          use_rag: useRag,
          use_tools: useTools,
          model: selectedModel || undefined,
          image: imageB64 || undefined,
          history: historyPayload,
        },
      })
    );

    setText("");
    setImageB64(null);
  }

  function onSend(e: FormEvent) {
    e.preventDefault();
    void submitSend();
  }

  function onTextareaKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submitSend();
    }
  }

  function onStopGeneration() {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ v: 1, type: "sys_cancel", payload: {} }));
    if (streamingRef.current.trim()) {
      const partial = streamingRef.current;
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `${partial}\n\n_(متوقف شد)_` },
      ]);
    }
    streamingRef.current = "";
    setStreaming("");
    setGenerating(false);
    setLivePhase("");
  }

  function onSelectImage(file: File | null) {
    if (!file) return;
    if (file.size > MAX_IMAGE_BYTES) {
      toast.error("حجم تصویر نباید بیشتر از ۲ مگابایت باشد.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setImageB64(reader.result);
      }
    };
    reader.readAsDataURL(file);
  }

  async function onToggleRag(checked: boolean) {
    setUseRag(checked);
    if (activeId) {
      try {
        await api.updateChat(activeId, { use_rag: checked });
        setChats((prev) =>
          prev.map((c) => (c.id === activeId ? { ...c, use_rag: checked } : c))
        );
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "خطا در ذخیره تنظیم RAG");
      }
    }
  }

  async function onModelChange(model: string) {
    setSelectedModel(model);
    if (activeId) {
      try {
        await api.updateChat(activeId, { model: model || null });
        setChats((prev) =>
          prev.map((c) => (c.id === activeId ? { ...c, model: model || null } : c))
        );
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "خطا در تغییر مدل گفتگو");
      }
    }
  }

  async function onConfirmRename(e: FormEvent) {
    e.preventDefault();
    if (!renameTarget || !renameTitle.trim()) return;
    setModalBusy(true);
    try {
      const updated = await api.updateChat(renameTarget.id, { title: renameTitle.trim() });
      setChats((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      setRenameTarget(null);
      toast.success("عنوان گفتگو بروزرسانی شد.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در تغییر نام");
    } finally {
      setModalBusy(false);
    }
  }

  async function onConfirmDelete() {
    if (!deleteTarget) return;
    setModalBusy(true);
    try {
      await api.deleteChat(deleteTarget.id);
      const remaining = chats.filter((c) => c.id !== deleteTarget.id);
      setChats(remaining);
      if (activeId === deleteTarget.id) {
        setActiveId(remaining[0]?.id || "");
        setMessages([]);
      }
      setDeleteTarget(null);
      toast.success("گفتگو حذف شد.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "خطا در حذف گفتگو");
    } finally {
      setModalBusy(false);
    }
  }

  async function copyMessage(content: string) {
    try {
      await navigator.clipboard.writeText(content);
      toast.info("متن کپی شد.");
    } catch {
      toast.error("کپی در کلیپ‌بورد ناموفق بود.");
    }
  }

  if (!user) return <main className="auth-wrap muted">در حال بارگذاری…</main>;

  const sidebarExtra = (
    <>
      <button type="button" className="btn primary" onClick={newChat}>
        + گفتگوی جدید
      </button>
      <input
        className="input"
        placeholder="جستجوی عنوان گفتگو…"
        value={chatQuery}
        onChange={(e) => setChatQuery(e.target.value)}
      />
      <div className="chat-list">
        {chats.length === 0 ? (
          <div className="muted" style={{ fontSize: "0.84rem", padding: "0.4rem" }}>
            گفتگویی یافت نشد.
          </div>
        ) : (
          chats.map((c) => (
            <div key={c.id} className={`chat-item ${c.id === activeId ? "is-active" : ""}`}>
              <button
                type="button"
                className="chat-item-btn"
                title={c.title}
                onClick={() => setActiveId(c.id)}
              >
                {c.title}
              </button>
              <div className="chat-item-actions">
                <button
                  type="button"
                  className="btn btn-xs"
                  title="تغییر نام"
                  onClick={() => {
                    setRenameTarget(c);
                    setRenameTitle(c.title);
                  }}
                >
                  ویرایش
                </button>
                <button
                  type="button"
                  className="btn btn-xs danger"
                  title="حذف"
                  onClick={() => setDeleteTarget(c)}
                >
                  حذف
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </>
  );

  const headerActions = activeChat ? (
    <>
      <button
        type="button"
        className="btn btn-sm"
        onClick={() => {
          setRenameTarget(activeChat);
          setRenameTitle(activeChat.title);
        }}
      >
        تغییر نام
      </button>
      <a
        className="btn btn-sm"
        href={api.exportChatUrl(activeChat.id, "md")}
        download={`chat-${activeChat.id}.md`}
      >
        خروجی MD
      </a>
      <a
        className="btn btn-sm"
        href={api.exportChatUrl(activeChat.id, "json")}
        download={`chat-${activeChat.id}.json`}
      >
        خروجی JSON
      </a>
    </>
  ) : null;

  return (
    <AppShell
      user={user}
      workerStatus={workerStatus}
      workerOnline={workerOnline}
      sidebarExtra={sidebarExtra}
      headerActions={headerActions}
      pageTitle={activeChat?.title || "گفتگوی جدید"}
    >
      <div className="chat-panel">
        <div className="messages">
          {loadingMsgs ? (
            <div className="card" style={{ display: "grid", gap: "0.6rem" }}>
              <div className="skeleton" style={{ width: "45%" }} />
              <div className="skeleton" style={{ width: "85%" }} />
              <div className="skeleton" style={{ width: "65%" }} />
            </div>
          ) : null}

          {!loadingMsgs && messages.length === 0 && !streaming ? (
            <div className="empty-state">
              <img src="/logo.png" alt="AI Workspace" width={48} height={48} />
              <h2 style={{ margin: 0, fontSize: "1.15rem" }}>گفتگو را شروع کنید</h2>
              <p className="muted" style={{ margin: 0, maxWidth: 460 }}>
                پیام‌های شما از طریق Bridge امن و رمزنگاری‌شده به مدل محلی LM Studio روی کامپیوتر شما ارسال می‌شوند.
              </p>
              <div className="prompt-chips">
                {STARTER_PROMPTS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    className="btn btn-sm"
                    onClick={() => setText(p)}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {messages.map((m, i) => (
            <article key={m.id || `m-${i}`} className={`bubble ${m.role === "user" ? "user" : "assistant"}`}>
              <div className="bubble-head">
                <span>{m.role === "user" ? user.username : "دستیار هوش مصنوعی"}</span>
                {m.role !== "user" ? (
                  <button
                    type="button"
                    className="btn btn-xs"
                    onClick={() => void copyMessage(m.content)}
                  >
                    کپی پاسخ
                  </button>
                ) : null}
              </div>
              {m.imagePreview ? (
                <div style={{ marginBottom: "0.5rem" }}>
                  <img
                    src={m.imagePreview}
                    alt="پیوست کاربر"
                    style={{ maxWidth: 260, borderRadius: 10 }}
                  />
                </div>
              ) : null}
              {m.role === "user" ? (
                <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
              ) : (
                <MarkdownContent content={m.content} />
              )}
              {m.sources?.length ? (
                <div className="sources">
                  <strong>منابع بازیابی‌شده (RAG):</strong>
                  {m.sources.map((s, idx) => (
                    <div key={s.chunk_id || idx}>
                      [{s.doc_title}] {s.snippet?.slice(0, 180)}…
                    </div>
                  ))}
                </div>
              ) : null}
            </article>
          ))}

          {streaming ? (
            <article className="bubble assistant">
              <div className="bubble-head">
                <span>دستیار هوش مصنوعی</span>
                <span className="badge badge--ok">در حال نوشتن…</span>
              </div>
              <MarkdownContent content={streaming} streaming />
            </article>
          ) : null}

          {livePhase && !streaming ? (
            <div className="muted" style={{ fontSize: "0.86rem" }}>
              {livePhase}
            </div>
          ) : null}
          <div ref={messagesEndRef} />
        </div>

        <form className="composer-box" onSubmit={onSend}>
          <div className="composer-toolbar">
            <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.86rem" }}>
              <input
                type="checkbox"
                checked={useRag}
                onChange={(e) => void onToggleRag(e.target.checked)}
              />
              <span>جستجو در پایگاه دانش (RAG)</span>
            </label>

            <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.86rem" }}>
              <input
                type="checkbox"
                checked={useTools}
                onChange={(e) => setUseTools(e.target.checked)}
              />
              <span>ابزار محاسبه‌گر</span>
            </label>

            <select
              className="select"
              style={{ width: "auto", minWidth: 210, padding: "0.35rem 0.65rem" }}
              value={selectedModel}
              onChange={(e) => void onModelChange(e.target.value)}
              aria-label="انتخاب مدل"
            >
              {availableModels.length === 0 ? (
                <option value="">مدل پیش‌فرض سرور</option>
              ) : (
                availableModels.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))
              )}
            </select>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => onSelectImage(e.target.files?.[0] || null)}
            />
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => fileInputRef.current?.click()}
            >
              پیوست تصویر
            </button>
          </div>

          {imageB64 ? (
            <div className="img-preview">
              <img src={imageB64} alt="پیش‌نمایش" />
              <span className="muted">تصویر آماده ارسال</span>
              <button
                type="button"
                className="btn btn-xs danger"
                onClick={() => setImageB64(null)}
              >
                حذف
              </button>
            </div>
          ) : null}

          <div className="composer">
            <textarea
              className="textarea"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={onTextareaKeyDown}
              placeholder="پیام خود را بنویسید… (Enter ارسال / Shift+Enter خط جدید)"
            />
            <div className="composer-actions">
              {generating ? (
                <button type="button" className="btn danger" onClick={onStopGeneration}>
                  توقف
                </button>
              ) : (
                <button className="btn primary" type="submit" disabled={!text.trim() && !imageB64}>
                  ارسال
                </button>
              )}
            </div>
          </div>
        </form>
      </div>

      <ModalDialog
        open={Boolean(renameTarget)}
        title="تغییر نام گفتگو"
        onClose={() => setRenameTarget(null)}
      >
        <form onSubmit={onConfirmRename} className="stack-form">
          <label className="field-label">
            <span>عنوان جدید</span>
            <input
              className="input"
              value={renameTitle}
              onChange={(e) => setRenameTitle(e.target.value)}
              maxLength={255}
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
        title="حذف گفتگو"
        message={`آیا از حذف گفتگوی «${deleteTarget?.title || ""}» مطمئن هستید؟ تمامی پیام‌های آن پاک خواهند شد.`}
        confirmLabel="حذف گفتگو"
        danger
        busy={modalBusy}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => void onConfirmDelete()}
      />
    </AppShell>
  );
}
