"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  useEffect(() => {
    api
      .me()
      .then(() => router.replace("/chat"))
      .catch(() => router.replace("/login"));
  }, [router]);
  return <main className="auth-wrap muted">در حال هدایت…</main>;
}
