#!/usr/bin/env python3
"""Honest live smoke against Bridge (+ optional PC Worker / LM Studio)."""

from __future__ import annotations

import os
import sys
import time

import httpx

API = os.environ.get("API_URL", "http://127.0.0.1:8010").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_BOOTSTRAP_USERNAME", "admin")
ADMIN_PASS = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "adminpass12")
REQUIRE_WORKER = os.environ.get("REQUIRE_WORKER", "1").strip().lower() in {
    "1",
    "true",
    "yes",
}
WORKER_WAIT_SEC = int(os.environ.get("WORKER_WAIT_SEC", "45"))


def main() -> int:
    failures: list[str] = []
    with httpx.Client(base_url=API, timeout=30.0, trust_env=False) as c:
        r = c.get("/api/health")
        print("health", r.status_code, r.json())
        if r.status_code != 200 or r.json().get("status") != "ok":
            failures.append("health")

        r = c.get("/api/ready")
        body = r.json()
        print("ready", r.status_code, body)
        if r.status_code != 200 or not body.get("database") or not body.get("redis"):
            failures.append("ready")

        # Wait for PC Worker if required
        online = bool((body.get("worker") or {}).get("worker_online"))
        if REQUIRE_WORKER and not online:
            deadline = time.time() + WORKER_WAIT_SEC
            while time.time() < deadline:
                time.sleep(2)
                body = c.get("/api/ready").json()
                online = bool((body.get("worker") or {}).get("worker_online"))
                print("waiting worker...", online)
                if online:
                    break
        print("worker_online", online)
        if REQUIRE_WORKER and not online:
            failures.append("worker_online")

        r = c.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
        print("login", r.status_code)
        if r.status_code != 200:
            failures.append("login")
            print("SMOKE FAIL", failures)
            return 1

        r = c.get("/api/auth/me")
        me = r.json()
        print("me", r.status_code, me.get("username"), me.get("role"))
        if r.status_code != 200 or me.get("role") != "admin":
            failures.append("me")

        r = c.get("/api/admin/stats")
        print("admin/stats", r.status_code, r.json())
        if r.status_code != 200:
            failures.append("admin/stats")

        r = c.get("/api/admin/settings")
        settings = r.json()
        print("admin/settings", r.status_code, settings)
        if r.status_code != 200 or "default_embed_model" not in settings:
            failures.append("admin/settings")

        r = c.post("/api/auth/ws-ticket")
        print("ws-ticket", r.status_code, "ticket" in r.json())
        if r.status_code != 200 or not r.json().get("ticket"):
            failures.append("ws-ticket")

    try:
        with httpx.Client(timeout=3.0, trust_env=False) as c:
            r = c.get("http://127.0.0.1:1234/v1/models")
            print("lmstudio", r.status_code)
    except Exception as exc:
        print("lmstudio unreachable (optional):", type(exc).__name__)

    if failures:
        print("SMOKE FAIL:", failures)
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
