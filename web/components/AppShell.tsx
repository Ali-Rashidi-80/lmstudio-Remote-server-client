"use client";

import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api, User } from "@/lib/api";
import { ModalDialog } from "@/components/ConfirmDialog";
import { useToast } from "@/components/Toast";

type ThemeMode = "dark" | "light";

export function useThemeSync(): [ThemeMode, () => void] {
  const [theme, setTheme] = useState<ThemeMode>("dark");
  const channelRef = useRef<BroadcastChannel | null>(null);

  useEffect(() => {
    const current =
      document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    setTheme(current);

    if (typeof BroadcastChannel !== "undefined") {
      const ch = new BroadcastChannel("aiws_sync");
      channelRef.current = ch;
      ch.onmessage = (ev) => {
        if (ev.data?.type === "theme" && (ev.data.theme === "dark" || ev.data.theme === "light")) {
          document.documentElement.setAttribute("data-theme", ev.data.theme);
          localStorage.setItem("aiws_theme", ev.data.theme);
          setTheme(ev.data.theme);
        }
      };
      return () => {
        ch.close();
        channelRef.current = null;
      };
    }
    return undefined;
  }, []);

  const toggle = () => {
    const next: ThemeMode = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("aiws_theme", next);
    setTheme(next);
    channelRef.current?.postMessage({ type: "theme", theme: next });
  };

  return [theme, toggle];
}

type AppShellProps = {
  user: User;
  workerStatus?: string;
  workerOnline?: boolean;
  sidebarExtra?: ReactNode;
  headerActions?: ReactNode;
  pageTitle: string;
  children: ReactNode;
};

export function AppShell({
  user,
  workerStatus,
  workerOnline = false,
  sidebarExtra,
  headerActions,
  pageTitle,
  children,
}: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const toast = useToast();
  const [theme, toggleTheme] = useThemeSync();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const [curPw, setCurPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [pwBusy, setPwBusy] = useState(false);
  const [pwErr, setPwErr] = useState("");

  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return undefined;
    const ch = new BroadcastChannel("aiws_sync");
    ch.onmessage = (ev) => {
      if (ev.data?.type === "logout") {
        router.replace("/login");
      }
    };
    return () => ch.close();
  }, [router]);

  async function onChangePassword(e: FormEvent) {
    e.preventDefault();
    setPwErr("");
    setPwBusy(true);
    try {
      await api.changePassword(curPw, newPw);
      setCurPw("");
      setNewPw("");
      setPwOpen(false);
      toast.success("رمز عبور با موفقیت تغییر یافت.");
    } catch (err) {
      setPwErr(err instanceof Error ? err.message : "خطا در تغییر رمز عبور");
    } finally {
      setPwBusy(false);
    }
  }

  async function onLogout(allDevices = false) {
    try {
      if (allDevices) {
        await api.logoutAll();
      } else {
        await api.logout();
      }
    } catch {
      /* proceed to login even if cookie already cleared */
    }
    if (typeof BroadcastChannel !== "undefined") {
      const ch = new BroadcastChannel("aiws_sync");
      ch.postMessage({ type: "logout" });
      ch.close();
    }
    router.replace("/login");
  }

  return (
    <div className="shell">
      {drawerOpen ? (
        <div
          className="drawer-backdrop"
          onClick={() => setDrawerOpen(false)}
          aria-hidden="true"
        />
      ) : null}

      <aside className={`sidebar ${drawerOpen ? "sidebar--open" : ""}`}>
        <div className="sidebar-top">
          <div className="brand-lockup">
            <img src="/logo.png" alt="AI Workspace" width={40} height={40} />
            <div>
              <div className="brand">AI Workspace</div>
              <div className="muted" style={{ fontSize: "0.78rem" }}>
                فضای کاری امن هوش مصنوعی
              </div>
            </div>
          </div>
          <button
            type="button"
            className="icon-btn mobile-only"
            onClick={() => setDrawerOpen(false)}
            aria-label="بستن منو"
          >
            ×
          </button>
        </div>

        <nav className="nav-pills" aria-label="ناوبری اصلی">
          <Link
            href="/chat"
            className={`nav-link ${pathname === "/chat" ? "is-active" : ""}`}
            aria-current={pathname === "/chat" ? "page" : undefined}
            onClick={() => setDrawerOpen(false)}
          >
            گفتگو
          </Link>
          <Link
            href="/knowledge"
            className={`nav-link ${pathname === "/knowledge" ? "is-active" : ""}`}
            aria-current={pathname === "/knowledge" ? "page" : undefined}
            onClick={() => setDrawerOpen(false)}
          >
            پایگاه دانش
          </Link>
          {user.role === "admin" ? (
            <Link
              href="/admin"
              className={`nav-link ${pathname === "/admin" ? "is-active" : ""}`}
              aria-current={pathname === "/admin" ? "page" : undefined}
              onClick={() => setDrawerOpen(false)}
            >
              مدیریت
            </Link>
          ) : null}
        </nav>

        {workerStatus !== undefined ? (
          <div className={`status-pill ${workerOnline ? "is-online" : "is-offline"}`}>
            <span className="status-dot" />
            <span>Worker: {workerStatus}</span>
          </div>
        ) : null}

        {sidebarExtra ? <div className="sidebar-extra">{sidebarExtra}</div> : null}

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <span>{user.username}</span>
            <span className="badge">{user.role === "admin" ? "ادمین" : "کاربر"}</span>
          </div>
          <div className="sidebar-actions">
            <button
              type="button"
              className="btn btn-sm"
              onClick={toggleTheme}
              title="تغییر پوسته"
            >
              {theme === "dark" ? "تم روشن" : "تم تاریک"}
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => setPwOpen(true)}
            >
              تغییر رمز
            </button>
          </div>
          <div className="sidebar-actions">
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => void onLogout(false)}
            >
              خروج
            </button>
            <button
              type="button"
              className="btn btn-sm danger"
              onClick={() => void onLogout(true)}
            >
              خروج همه‌جا
            </button>
          </div>
        </div>
      </aside>

      <main className="workspace-main">
        <header className="topbar">
          <div className="topbar-start">
            <button
              type="button"
              className="btn btn-sm mobile-only"
              onClick={() => setDrawerOpen(true)}
              aria-label="منو"
            >
              ☰ منو
            </button>
            <h1 className="topbar-title">{pageTitle}</h1>
          </div>
          <div className="topbar-actions">{headerActions}</div>
        </header>
        <div className="workspace-body">{children}</div>
      </main>

      <ModalDialog open={pwOpen} title="تغییر رمز عبور" onClose={() => setPwOpen(false)}>
        <form onSubmit={onChangePassword} className="stack-form">
          <label className="field-label">
            <span>رمز عبور فعلی</span>
            <input
              type="password"
              className="input"
              value={curPw}
              onChange={(e) => setCurPw(e.target.value)}
              required
            />
          </label>
          <label className="field-label">
            <span>رمز عبور جدید (حداقل ۱۰ کاراکتر)</span>
            <input
              type="password"
              className="input"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              minLength={10}
              required
            />
          </label>
          {pwErr ? <div className="form-error">{pwErr}</div> : null}
          <div className="dialog-foot" style={{ padding: 0, marginTop: "0.4rem" }}>
            <button type="button" className="btn" onClick={() => setPwOpen(false)}>
              انصراف
            </button>
            <button type="submit" className="btn primary" disabled={pwBusy}>
              {pwBusy ? "در حال ذخیره…" : "بروزرسانی رمز"}
            </button>
          </div>
        </form>
      </ModalDialog>
    </div>
  );
}
