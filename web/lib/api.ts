const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type User = {
  id: string;
  username: string;
  email: string | null;
  role: string;
  is_active: boolean;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string; user: User }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  me: () => request<User>("/api/auth/me"),
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
    }),
  chats: () => request<any[]>("/api/chats"),
  createChat: (title = "New chat", use_rag = false) =>
    request<any>("/api/chats", {
      method: "POST",
      body: JSON.stringify({ title, use_rag }),
    }),
  messages: (chatId: string) => request<any[]>(`/api/chats/${chatId}/messages`),
  deleteChat: (chatId: string) =>
    request(`/api/chats/${chatId}`, { method: "DELETE" }),
  importLocal: (sessions: any[]) =>
    request("/api/chats/import-local", {
      method: "POST",
      body: JSON.stringify({ sessions }),
    }),
  users: () => request<User[]>("/api/users"),
  createUser: (body: { username: string; password: string; role?: string }) =>
    request<User>("/api/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (id: string, body: { role?: string; is_active?: boolean }) =>
    request<User>(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  createInvite: (email?: string) =>
    request<{ token: string; accept_path: string }>("/api/users/invites", {
      method: "POST",
      body: JSON.stringify({ email, role: "user" }),
    }),
  listInvites: () => request<any[]>("/api/users/invites"),
  docs: () => request<any[]>("/api/knowledge/docs"),
  deleteDoc: (id: string) =>
    request(`/api/knowledge/docs/${id}`, { method: "DELETE" }),
  adminStats: () => request<any>("/api/admin/stats"),
  adminSettings: () => request<any>("/api/admin/settings"),
  putAdminSettings: (body: {
    default_chat_model?: string;
    default_embed_model?: string;
  }) =>
    request<any>("/api/admin/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  adminReindex: () =>
    request<{ ok: number; failed: number; total: number }>("/api/admin/reindex", {
      method: "POST",
    }),
  adminUnload: () =>
    request<{ ok: boolean }>("/api/admin/unload-models", { method: "POST" }),
  patchDoc: (id: string, is_shared: boolean) =>
    request<{ id: string; is_shared: boolean }>(
      `/api/knowledge/docs/${id}?is_shared=${is_shared}`,
      { method: "PATCH" }
    ),
  chatsSearch: (q: string) =>
    request<any[]>(`/api/chats?q=${encodeURIComponent(q)}`),
  ready: () => request<any>("/api/ready"),
  apiUrl: API_URL,
};

export function wsUrl(ticket: string): string {
  const base = API_URL.replace(/^http/, "ws");
  return `${base}/ws/client?ticket=${encodeURIComponent(ticket)}`;
}
