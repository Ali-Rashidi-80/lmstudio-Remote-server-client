const envApi = (process.env.NEXT_PUBLIC_API_URL || "").trim().replace(/\/+$/, "");

export function getApiUrl(): string {
  if (typeof window !== "undefined") {
    const pageHost = window.location.hostname;
    if (envApi) {
      try {
        const parsed = new URL(envApi);
        const loopback = new Set(["localhost", "127.0.0.1"]);
        if (loopback.has(parsed.hostname) && loopback.has(pageHost) && parsed.hostname !== pageHost) {
          parsed.hostname = pageHost;
          return parsed.toString().replace(/\/+$/, "");
        }
      } catch {
        /* use envApi as-is */
      }
      return envApi;
    }
    return `${window.location.protocol}//${pageHost}:8010`;
  }
  return envApi || "http://127.0.0.1:8010";
}

export const API_URL = getApiUrl();

export type User = {
  id: string;
  username: string;
  email: string | null;
  role: string;
  is_active: boolean;
};

export type ChatItem = {
  id: string;
  title: string;
  model: string | null;
  use_rag: boolean;
  created_at: string;
  updated_at: string;
};

export type RagSource = {
  chunk_id?: string;
  doc_id?: string;
  doc_title: string;
  snippet: string;
  score?: number;
};

export type MessageItem = {
  id: string;
  role: string;
  content: string;
  meta?: { sources?: RagSource[]; [key: string]: unknown } | null;
  created_at: string;
};

export type ChatModelsInfo = {
  default_chat_model: string;
  default_embed_model: string;
  available_models: string[];
  worker: {
    worker_online: boolean;
    hw: string;
  };
};

export type KnowledgeDocItem = {
  id: string;
  title: string;
  filename: string;
  content_type?: string;
  status: string;
  size_bytes: number;
  is_shared: boolean;
  is_owner?: boolean;
  last_error?: string | null;
  created_at: string;
};

export type RagJobItem = {
  id: string;
  doc_id: string;
  status: string;
  error: string | null;
  finished_at?: string | null;
};

export type InviteItem = {
  id: string;
  email: string | null;
  role: string;
  expires_at: string;
  used_at: string | null;
  created_at?: string;
  token: string | null;
};

export type AdminStats = {
  app_version?: string;
  users: number;
  docs: number;
  chunks?: number;
  audit_logs?: number;
  active_rag_jobs: number;
  worker: {
    worker_online: boolean;
    hw: string;
    connected_users?: number;
  };
};

export type AdminSettings = {
  default_chat_model: string;
  default_embed_model: string;
  embed_dim: number;
};

export type AdminModelsInfo = {
  default_chat_model: string;
  default_embed_model: string;
  available_models: Array<{ id?: string } | string>;
  worker: AdminStats["worker"];
  note?: string;
};

export type AuditLogItem = {
  id: string;
  actor_id: string | null;
  action: string;
  detail: Record<string, unknown>;
  created_at: string;
};

export type AuditLogsPage = {
  total: number;
  items: AuditLogItem[];
};

export type ReindexResult = {
  ok: number;
  failed: number;
  total: number;
};

export type PruneResult = {
  refresh_tokens: number;
  audit_logs: number;
  rag_jobs: number;
};

export type UploadDocResult = {
  id: string;
  status: string;
  job_id: string;
  ingest_mode: string;
};

function makeIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `k-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function parseErrorDetail(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return JSON.stringify(item);
      })
      .join(" | ");
  }
  return fallback;
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = fetch(`${getApiUrl()}/api/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

type RequestOptions = RequestInit & {
  idempotent?: boolean;
  skipRefresh?: boolean;
};

async function request<T>(path: string, opts: RequestOptions = {}, retried = false): Promise<T> {
  const { idempotent, skipRefresh, ...init } = opts;
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  const headers = new Headers(init.headers || undefined);
  if (!isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (idempotent && !headers.has("Idempotency-Key")) {
    headers.set("Idempotency-Key", makeIdempotencyKey());
  }

  const res = await fetch(`${getApiUrl()}${path}`, {
    ...init,
    credentials: "include",
    headers,
  });

  if (
    res.status === 401 &&
    !retried &&
    !skipRefresh &&
    !path.startsWith("/api/auth/login") &&
    !path.startsWith("/api/auth/refresh") &&
    !path.startsWith("/api/auth/accept-invite")
  ) {
    const ok = await refreshSession();
    if (ok) {
      return request<T>(path, opts, true);
    }
  }

  if (!res.ok) {
    const errBody = await res.json().catch(() => null);
    throw new Error(parseErrorDetail(errBody, res.statusText || `HTTP ${res.status}`));
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string; user: User }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
      skipRefresh: true,
    }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  logoutAll: () => request<{ ok: boolean }>("/api/auth/logout-all", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    request<{ ok: boolean }>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),
  me: (signal?: AbortSignal) => request<User>("/api/auth/me", { signal }),
  wsTicket: () => request<{ ticket: string }>("/api/auth/ws-ticket", { method: "POST" }),
  acceptInvite: (body: {
    token: string;
    username: string;
    password: string;
    email?: string;
  }) =>
    request<{ access_token: string; user: User }>("/api/auth/accept-invite", {
      method: "POST",
      body: JSON.stringify(body),
      skipRefresh: true,
    }),
  chats: (signal?: AbortSignal) => request<ChatItem[]>("/api/chats", { signal }),
  chatsSearch: (q: string, signal?: AbortSignal) =>
    request<ChatItem[]>(`/api/chats?q=${encodeURIComponent(q)}`, { signal }),
  chatModels: (signal?: AbortSignal) =>
    request<ChatModelsInfo>("/api/chats/models", { signal }),
  createChat: (title = "گفتگوی جدید", use_rag = false, model?: string | null) =>
    request<ChatItem>("/api/chats", {
      method: "POST",
      body: JSON.stringify({ title, use_rag, model: model || null }),
      idempotent: true,
    }),
  updateChat: (
    chatId: string,
    body: { title?: string; model?: string | null; use_rag?: boolean }
  ) =>
    request<ChatItem>(`/api/chats/${chatId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  messages: (chatId: string, signal?: AbortSignal) =>
    request<MessageItem[]>(`/api/chats/${chatId}/messages`, { signal }),
  deleteChat: (chatId: string) =>
    request<{ ok: boolean }>(`/api/chats/${chatId}`, { method: "DELETE" }),
  importLocal: (sessions: Array<{ title: string; history: unknown[] }>) =>
    request<{ imported: number }>("/api/chats/import-local", {
      method: "POST",
      body: JSON.stringify({ sessions }),
    }),
  users: (signal?: AbortSignal) => request<User[]>("/api/users", { signal }),
  createUser: (body: {
    username: string;
    password: string;
    role?: string;
    email?: string;
  }) =>
    request<User>("/api/users", {
      method: "POST",
      body: JSON.stringify(body),
      idempotent: true,
    }),
  updateUser: (id: string, body: { role?: string; is_active?: boolean }) =>
    request<User>(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  createInvite: (email?: string, role = "user") =>
    request<{
      id: string;
      token: string;
      role: string;
      email: string | null;
      expires_at: string;
      accept_path: string;
    }>("/api/users/invites", {
      method: "POST",
      body: JSON.stringify({ email: email || undefined, role }),
      idempotent: true,
    }),
  listInvites: (signal?: AbortSignal) =>
    request<InviteItem[]>("/api/users/invites", { signal }),
  revokeInvite: (inviteId: string) =>
    request<{ ok: boolean }>(`/api/users/invites/${inviteId}`, { method: "DELETE" }),
  docs: (params?: { q?: string; status?: string }, signal?: AbortSignal) => {
    const sp = new URLSearchParams();
    if (params?.q?.trim()) sp.set("q", params.q.trim());
    if (params?.status?.trim()) sp.set("status", params.status.trim());
    const qs = sp.toString();
    return request<KnowledgeDocItem[]>(`/api/knowledge/docs${qs ? `?${qs}` : ""}`, { signal });
  },
  uploadDoc: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<UploadDocResult>("/api/knowledge/docs", {
      method: "POST",
      body: form,
      idempotent: true,
    });
  },
  jobStatus: (jobId: string, signal?: AbortSignal) =>
    request<RagJobItem>(`/api/knowledge/jobs/${jobId}`, { signal }),
  patchDoc: (id: string, body: { title?: string; is_shared?: boolean }) =>
    request<{ id: string; title: string; is_shared: boolean }>(`/api/knowledge/docs/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteDoc: (id: string) =>
    request<{ ok: boolean }>(`/api/knowledge/docs/${id}`, { method: "DELETE" }),
  searchKnowledge: (q: string, top_k = 5) =>
    request<{ sources: RagSource[] }>("/api/knowledge/search", {
      method: "POST",
      body: JSON.stringify({ q, top_k }),
    }),
  adminStats: (signal?: AbortSignal) =>
    request<AdminStats>("/api/admin/stats", { signal }),
  adminSettings: (signal?: AbortSignal) =>
    request<AdminSettings>("/api/admin/settings", { signal }),
  adminModels: (signal?: AbortSignal) =>
    request<AdminModelsInfo>("/api/admin/models", { signal }),
  putAdminSettings: (body: {
    default_chat_model?: string;
    default_embed_model?: string;
  }) =>
    request<AdminSettings>("/api/admin/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  adminReindex: () =>
    request<ReindexResult>("/api/admin/reindex", {
      method: "POST",
      idempotent: true,
    }),
  adminUnload: () =>
    request<{ ok: boolean }>("/api/admin/unload-models", { method: "POST" }),
  adminAuditLogs: (
    params?: { action?: string; limit?: number; offset?: number },
    signal?: AbortSignal
  ) => {
    const sp = new URLSearchParams();
    if (params?.action?.trim()) sp.set("action", params.action.trim());
    if (params?.limit) sp.set("limit", String(params.limit));
    if (params?.offset) sp.set("offset", String(params.offset));
    const qs = sp.toString();
    return request<AuditLogsPage>(`/api/admin/audit-logs${qs ? `?${qs}` : ""}`, { signal });
  },
  adminPrune: () =>
    request<PruneResult>("/api/admin/maintenance/prune", { method: "POST" }),
  ready: () => request<{ ready: boolean; worker: AdminStats["worker"] }>("/api/ready"),
  exportChatUrl: (chatId: string, format: "md" | "json" = "md") =>
    `${getApiUrl()}/api/chats/${chatId}/export?format=${format}`,
  apiUrl: API_URL,
};

export function wsUrl(ticket: string): string {
  const base = getApiUrl().replace(/^http/, "ws");
  return `${base}/ws/client?ticket=${encodeURIComponent(ticket)}`;
}

const faNumber = new Intl.NumberFormat("fa-IR");
const faDateTime = new Intl.DateTimeFormat("fa-IR", {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatNumber(n: number): string {
  return faNumber.format(n);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return faDateTime.format(d);
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "۰ بایت";
  if (bytes < 1024) return `${faNumber.format(bytes)} بایت`;
  if (bytes < 1024 * 1024) return `${faNumber.format(Math.round((bytes / 1024) * 10) / 10)} کیلوبایت`;
  return `${faNumber.format(Math.round((bytes / (1024 * 1024)) * 100) / 100)} مگابایت`;
}
