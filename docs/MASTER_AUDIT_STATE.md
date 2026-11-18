# Master Adversarial Audit & Remediation State (`AI Workspace` v20.0.0)

> **Target Repo:** `d:\0\lmstudio-Remote-server-client`  
> **Reference Repo:** None  
> **Execution Mode:** Full-Stack Adversarial Audit + Production-Ready Remediation (No Git Commits)  
> **Last Updated:** 2026-11-18  

---

## Phase 1: Stack Discovery, Gap Analysis & Cross-Stack Wiring Audit

### 1.1 Architecture & Manifest Inventory
| Layer | Manifest / Entrypoint | Technology | Key Files Audited |
|---|---|---|---|
| **Backend Bridge API** | `backend/requirements.txt`, `backend/pyproject.toml`, `backend/alembic.ini` | FastAPI 0.115, SQLAlchemy 2.0 Async (`asyncpg`), Alembic 1.15, pgvector 0.4.1, Redis 5.2, ARQ 0.26.1, PyJWT, argon2-cffi, pycryptodome | `backend/app/main.py`, `backend/app/core/*`, `backend/app/db/*`, `backend/app/models/entities.py`, `backend/app/schemas/*`, `backend/app/api/deps.py`, `backend/app/api/routes/*`, `backend/app/services/*`, `backend/app/workers/rag.py`, `backend/app/ws/manager.py`, `backend/alembic/versions/0001_initial.py` |
| **Frontend Web UI** | `web/package.json`, `web/tsconfig.json`, `web/next.config.ts` | Next.js 15.2.4 (App Router, standalone), React 19, TypeScript 5.8 | `web/lib/api.ts`, `web/app/layout.tsx`, `web/app/globals.css`, `web/app/page.tsx`, `web/app/login/page.tsx`, `web/app/accept-invite/page.tsx`, `web/app/chat/page.tsx`, `web/app/knowledge/page.tsx`, `web/app/admin/page.tsx` |
| **PC GPU Worker** | `pc_client/requirements.txt`, `pc_client/app_config.json` | Python `httpx`, `websockets` 15.0.1, `pycryptodome`, `python-dotenv` | `pc_client/main.py`, `pc_client/cipher_utils.py`, `cipher_utils.py` |
| **Infra & CI/QA** | `docker-compose.yml`, `backend/Dockerfile`, `web/Dockerfile`, `.github/workflows/ci.yml` | Postgres 16 (`pgvector`), Redis 7, Docker Compose, GitHub Actions, PowerShell QA | `docker-compose.yml`, `backend/Dockerfile`, `web/Dockerfile`, `.env.example`, `pc_client/.env.example`, `.gitignore`, `scripts/qa.ps1`, `scripts/live_smoke.py` |
| **Test Suite** | `backend/pytest.ini`, `backend/tests/*` | pytest + pytest-asyncio against real Postgres + Redis | `backend/tests/conftest.py`, `test_api_gaps.py`, `test_ownership.py`, `test_security.py`, `test_stream_persist.py`, `test_rag_live.py`, `test_lmstudio_live.py` |

### 1.2 Adversarial Findings & Cross-Stack Defect Register

| ID | Severity | Area / File & Lines | Defect Description & Impact | Planned Fix Phase |
|---|---|---|---|---|
| **F-01** | **P0** | `backend/app/workers/rag.py:37`, `backend/app/services/rag.py:88-96` | **Cross-process RAG failure:** ARQ `rag-worker` runs in a separate OS process where `ws.manager.pc_client` is always `None`. In production (`EMBED_DIRECT_URL=""`), every background RAG ingest fails with `PC Worker offline for embeddings`. | Phase 2 |
| **F-02** | **P0** | `pc_client/main.py:561-626`, `web/app/chat/page.tsx:121-135` | **Multi-turn context & current message drop:** `pc_client` checks `m.get("role") == "ai"` (dropping Web `assistant` turns), AND when `req_history` is non-empty (`if req_history:` vs `else:`), it skips appending the new `user_text` / `image_b64` entirely! | Phase 2 |
| **F-03** | **P1** | `pc_client/main.py:375-390`, `backend/app/api/routes/ws.py:88-90` | **Hardware status mismatch:** Worker sends `{"type": "hw_info", "content": status}`, Bridge reads `payload.hw`/`data.hw`, causing UI & `/api/ready` to always display `"CPU"`. | Phase 2 |
| **F-04** | **P1** | `backend/app/services/bootstrap.py:26`, `backend/alembic/versions/0001_initial.py:146` | **Duplicate HNSW index:** Creates both `idx_rag_chunks_embedding_hnsw` and `ix_rag_chunks_embedding_hnsw` on `rag_chunks.embedding`, doubling vector index memory & insert cost. | Phase 2 |
| **F-05** | **P1** | `backend/app/services/rag.py:167-174` | **PostgreSQL transaction poisoning:** `SELECT set_config('hnsw.ef_search', ...)` catches `Exception: pass` without a `SAVEPOINT` (`begin_nested()`), which aborts the entire outer transaction if unsupported. | Phase 2 |
| **F-06** | **P1** | `backend/app/api/routes/auth.py:129-188` | **Concurrency race conditions & missing idempotency:** `accept_invite` and `refresh` lack `SELECT ... FOR UPDATE` row locks; `POST` mutations (`chats`, `knowledge/docs`, `users`, `invites`, `reindex`) lack `Idempotency-Key` support. | Phase 2 |
| **F-07** | **P1** | `backend/app/api/routes/auth.py:87-125,191-198` | **Silent error swallowing & incomplete logout:** `logout`/`logout_all` use `except Exception: pass`, `logout_all` fails to blacklist current access `jti` or read `Bearer` header, and `change_password` leaves existing refresh tokens active. | Phase 2 |
| **F-08** | **P1** | `backend/app/api/routes/ws.py:79,127,162-212` | **WS security & persistence gaps:** WS ticket is not single-use (replayable for 60s), `WORKER_TOKEN` uses `!=` instead of `secrets.compare_digest`, invalid `chat_id` UUID crashes WS loop, `image` payload size is unchecked, and chat `updated_at` / auto-title never update on WS message. | Phase 2 |
| **F-09** | **P1** | `backend/app/api/routes/admin.py:123`, `users.py:71-112` | **RBAC & user management flaws:** `GET /api/admin/models` uses `CurrentUser` instead of `AdminUser`; admins can deactivate/demote themselves (`PATCH /api/users/{id}`); deactivating a user does not revoke refresh tokens; no `DELETE /api/users/invites/{id}`; no `GET /api/admin/audit-logs` or maintenance prune endpoint; no `EmailStr` validation. | Phase 2 |
| **F-10** | **P1** | `backend/app/api/routes/knowledge.py:61-196` | **Unbounded RAM upload & missing doc/search UX endpoints:** `await file.read()` buffers arbitrary sizes before `MAX_DOC_BYTES` check; no magic/structure validation (fake PDF/DOCX/null bytes); no doc rename (`PATCH`), no filter/pagination, no `is_owner` flag in list, and `delete_doc` ignores `is_owner` only implicitly via 404. | Phase 2 |
| **F-11** | **P1** | `backend/app/api/routes/chats.py:45-99` | **Missing Chat CRUD:** No `PATCH /api/chats/{id}` (rename, model, `use_rag`), no `GET /api/chats/{id}/export`, no pagination (`limit`/`offset`), no `GET /api/chats/models`, and unvalidated string UUIDs cause raw `500 ValueError` instead of `422`. | Phase 2 |
| **F-12** | **P1** | `backend/app/core/config.py`, `backend/app/core/logging.py`, `.env.example`, `pc_client/main.py` | **Hardcodes & log hygiene:** Hardcoded chunk/context/rate-limit constants, `JWT_SECRET` test/example < 32 bytes, `pc_client` default WS port `8000` instead of `8010`, no rotating file log handler, and no retention pruning for `audit_logs`/`refresh_tokens`/`rag_jobs`. | Phase 2 |
| **F-13** | **P0** | `web/app/layout.tsx:18`, `web/Dockerfile` | **External CDN dependency & broken Docker assets:** `layout.tsx` loads Google Fonts (`fonts.googleapis.com`), violating 100% self-contained local asset mandate; `web/Dockerfile` omits `COPY --from=builder /app/public ./public`, causing 404 on `/logo.png` and local fonts. | Phase 3 & 4 |
| **F-14** | **P1** | `web/lib/api.ts:1` | **Broken API fallback & missing auth refresh/types:** Falls back to `http://localhost:8000` instead of `:8010`; uses `any` everywhere; no automatic `401 -> /api/auth/refresh` retry; no `AbortSignal` or `Idempotency-Key`; no `Intl` formatters. | Phase 3 |
| **F-15** | **P1** | `web/app/globals.css`, `web/app/chat/page.tsx`, `knowledge/page.tsx`, `admin/page.tsx`, `login/page.tsx`, `accept-invite/page.tsx` | **AI Slop & Incomplete UI Wiring:** Single dark theme only (no Light mode); missing `error.tsx`/`not-found.tsx`/`loading.tsx`; no Markdown/code block rendering or copy button; no Stop Generation (`sys_cancel`), Rename/Delete/Export Chat, Model Selector, Tool Toggle, Image Upload, WS reconnect, Change Password, Logout-All, Knowledge Job polling, Vector Search Preview, Admin Invite revoke, User Role edit, Audit Logs table, or `<dialog>` confirmations; hardcoded `v20.0.0` in `admin/page.tsx:71`. | Phase 3 |
| **F-16** | **P1** | `backend/app/main.py`, `web/next.config.ts`, `cipher_utils.py`, `pc_client/cipher_utils.py`, `backend/Dockerfile`, `docker-compose.yml` | **Security & Infra Hardening Gaps:** Unvalidated `X-Request-ID` reflection; missing Security Headers (CSP, X-Frame-Options, nosniff, Referrer-Policy, HSTS) & CSRF Origin check on cookie mutations; unauthenticated `AES-CBC` with null-padded key in `cipher_utils`; Dockerfiles running as `root`; Compose binds DB/Redis to `0.0.0.0`, hardcodes Postgres password, and has `WEB_HOST_PORT` colliding with `:3000`. | Phase 4 |
| **F-17** | **P1** | `backend/pyproject.toml`, `scripts/qa.ps1`, `.github/workflows/ci.yml`, `web/package.json` | **QA & CI Gaps:** Missing `pylint` + `compileall` in `qa.ps1` and CI; missing `web` CI job (`tsc`, `eslint`, `next build`); `web/package.json` lacks ESLint setup for non-interactive `npm run lint`; missing concurrency, idempotency, WS replay, BOLA, and `pc_client` unit tests. | Phase 5 |

### 1.3 Live Environment Reconnaissance
- **Python available:** Python 3.11.9, Python 3.12.13 (uv), Python 3.14, `uv 0.12.2`
- **Node/npm available:** Node `v24.20.0`, npm `11.19.0`, `web/node_modules` present
- **Docker host ports currently occupied by unrelated services:** `127.0.0.1:3000`, `:8000`, `:5432`, `:5433`, `:6379`, `:6380`, `:8001`, `:8082`, `:8103`.
- **Safe project ports:** Postgres `127.0.0.1:55432`, Redis `127.0.0.1:26379`, Bridge `127.0.0.1:8010`, Web E2E `127.0.0.1:3010`.

---

## Phase 2: Backend De-Hardcoding, ACID Concurrency, Cross-Process Relay & Log/DB Hygiene (COMPLETED)

### Files Created / Modified
- `.env.example` & `.env`: Added `APP_ENV`, `WEB_HOST_PORT`, `BRIDGE_INTERNAL_URL`, `RAG_*`, rate limit, retention, and `LOG_FILE` rotation config; expanded `JWT_SECRET` placeholder to >= 32 bytes; added `http://localhost:3010` to dev `CORS_ORIGINS`.
- `backend/app/core/config.py`: Parameterized RAG, rate-limit, retention, and logging settings; added `validate_production_secrets()` fail-fast guard for `APP_ENV=production` / `COOKIE_SECURE=true`.
- `backend/app/core/logging.py`: Added optional `RotatingFileHandler` alongside JSON stdout formatter.
- `backend/app/db/redis.py`: Added atomic `consume_ws_ticket` (`SET NX EX`), `set_worker_state` / `get_worker_state` Redis presence + model list cache, and logged Redis ping errors.
- `backend/app/services/rate_limit.py`: Added generic `check_rate_limit(scope, key_id, limit, window)` with self-healing TTL check and parameterized `check_login_rate`.
- `backend/app/services/idempotency.py`: Created Redis-backed `Idempotency-Key` guard (`begin_idempotency`, `complete_idempotency`, `abort_idempotency`) returning `409` on payload mismatch or concurrent in-flight duplicate.
- `backend/app/services/maintenance.py`: Created `prune_stale_records()` deleting expired/revoked refresh tokens and aged audit/RAG job records per `AUDIT_RETENTION_DAYS`.
- `backend/app/models/entities.py` & `backend/app/services/bootstrap.py` & `backend/alembic/versions/0002_hardening_indexes_cascades.py`: Added `ON DELETE CASCADE` on child user/chat FKs, `ix_audit_logs_created_at`, and dropped duplicate `idx_rag_chunks_embedding_hnsw` in favor of single `ix_rag_chunks_embedding_hnsw`.
- `backend/app/ws/manager.py`: Added Redis presence sync, `available_models` tracking + `get_models` probe on PC connect, `merged_status()`, fail-fast embed waiter cleanup on PC disconnect, and structured send error handling.
- `backend/app/api/routes/internal.py`: Created `POST /api/internal/embeddings` protected by constant-time `X-Worker-Token`.
- `backend/app/services/rag.py`: Added exponential-backoff retries, cross-process fallback to `/api/internal/embeddings` when ARQ worker runs out-of-process, `SAVEPOINT` (`db.begin_nested()`) around `hnsw.ef_search`, shared-doc stale check, and `top_k` clamping.
- `backend/app/api/routes/auth.py`: Added `SELECT ... FOR UPDATE` locks on `accept_invite` & `refresh`, rate limits, email uniqueness check, structured error logging in `logout`/`logout_all` (no bare `except: pass`), and refresh token revocation + cookie rotation on `change_password`.
- `backend/app/api/routes/users.py`: Added `Idempotency-Key`, `EmailStr` validation, self-deactivation/self-demotion prevention, token revocation on deactivation, and `DELETE /api/users/invites/{invite_id}`.
- `backend/app/api/routes/chats.py`: Added `GET /api/chats/models`, `PATCH /api/chats/{chat_id}`, `GET /api/chats/{chat_id}/export` (Markdown/JSON), `Idempotency-Key` on `POST`, UUID path validation, and pagination.
- `backend/app/api/routes/knowledge.py`: Added bounded streaming upload (`413` over 10MB), PDF/DOCX/text content signature & zip-bomb checks, upload rate limiting, `Idempotency-Key`, search/status filtering, `is_owner` flag, `PATCH` title/share support, and UUID path typing.
- `backend/app/api/routes/admin.py` & `health.py`: Fixed `GET /api/admin/models` RBAC (`AdminUser`), added `GET /api/admin/audit-logs`, `POST /api/admin/maintenance/prune`, `Idempotency-Key` on reindex, `app_version`/counts in stats, and Redis-merged worker status in `/api/ready`.
- `backend/app/api/routes/ws.py`: Enforced single-use WS ticket consumption (`consume_ws_ticket`), constant-time `WORKER_TOKEN` verification, `hw_info` & `models_list` handling, image size limit, chat ownership + UUID validation, DB history fallback, and auto-titling.
- `backend/app/main.py`: Wired `internal.router`, `validate_production_secrets()`, `prune_stale_records()`, log rotation, validated `X-Request-ID`, HTTP security headers, and CSRF Origin check.
- `pc_client/main.py`: Extracted `build_chat_messages()` fixing multi-turn `assistant` role mapping and dropped current user messages when `req_history` is present; fixed `hw_info` payload, default port `:8010`, initial `models_list` push, env-configurable intervals, rotating file logging, and removed silent `except: pass`.

---

## Phase 3: Anti-Slop UI/UX Surgery, 100% Local Assets & Complete Client Wiring (COMPLETED)

### Files Created / Modified
- `web/public/fonts/*`: Bundled local `Vazirmatn-Regular.woff2`, `Vazirmatn-Medium.woff2`, `Vazirmatn-Bold.woff2`, `JetBrainsMono-Regular.woff2`, `JetBrainsMono-SemiBold.woff2` (100% self-contained, zero Google Fonts CDN).
- `web/app/layout.tsx`: Removed external Google Fonts `<link>`, added pre-hydration theme script (`data-theme`), and wrapped children in `ToastProvider`.
- `web/app/globals.css`: Rebuilt cohesive Dark + Light theme design system (`[data-theme="dark"]`, `[data-theme="light"]`), local `@font-face` rules, RTL chat layout, native `<dialog>` styling, toast stack, skeleton loaders, responsive mobile drawer, and WCAG-verified contrast tokens.
- `web/lib/api.ts`: Fixed API fallback to `:8010`, added strict TypeScript types (zero `any`), single-flight `401 -> /api/auth/refresh` retry, `Idempotency-Key` headers on mutating `POST`s, `AbortSignal` support, and `Intl` (`fa-IR`) date/number/byte formatters.
- `web/components/Toast.tsx`, `ConfirmDialog.tsx`, `MarkdownContent.tsx`, `AppShell.tsx`: Implemented accessible toast notifications, native `<dialog>` modals/confirmations, XSS-safe Markdown + fenced code block renderer with copy buttons, and unified `AppShell` with Dark/Light `BroadcastChannel` sync, Change Password modal, and Logout-All-Devices.
- `web/app/error.tsx`, `not-found.tsx`, `loading.tsx`: Added global error boundary, 404 screen, and loading skeleton.
- `web/app/login/page.tsx` & `accept-invite/page.tsx`: Added accessible labeled fields, password visibility toggle, theme toggle, email support on invite acceptance, and cross-links.
- `web/app/chat/page.tsx`: Wired full chat CRUD (create, debounced search with `AbortController`, rename `<dialog>`, delete `<ConfirmDialog>`, Markdown/JSON export), model selector, RAG & calculator toggles, `<= 2MB` image attachment preview, Stop Generation (`sys_cancel`), auto-reconnect WS with exponential backoff, copy-message, skeleton loader, and starter-prompt empty state.
- `web/app/knowledge/page.tsx`: Wired drag-and-drop + picker upload (`<= 10MB`), live job status polling, search + status filter, rename `<dialog>`, ownership-aware share/delete controls, formatted sizes/dates, and interactive RAG Vector Search Preview.
- `web/app/admin/page.tsx`: Replaced hardcoded version with dynamic `stats.app_version`, added KPI cards, invite create/list/copy/revoke, user create/search/role/active controls (self-lockout guarded), model settings + confirm-gated Reindex / Unload / Prune ops, and paginated/filterable Audit Logs viewer + JSON export.

---

## Phase 4: Red/Blue Security Hardening & Container/Infra Tightening (COMPLETED)

### Files Created / Modified
- `backend/app/main.py`: Added `REQUEST_ID_RE` validation (`^[a-zA-Z0-9._-]{1,64}$`), HTTP security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy`, conditional `Strict-Transport-Security`), and CSRF Origin verification on cookie-authenticated mutations (`POST`/`PUT`/`PATCH`/`DELETE`).
- `web/next.config.ts`: Added security headers including strict self-contained `Content-Security-Policy` (`font-src 'self'`, `script-src 'self' 'unsafe-inline'`, `frame-ancestors 'none'`).
- `cipher_utils.py` & `pc_client/cipher_utils.py`: Upgraded relay encryption from unauthenticated AES-CBC to **AES-256-GCM** (`v2:` prefix, SHA-256 32-byte key derivation, 96-bit random nonce, 128-bit auth tag, strict base64 validation, payload cap).
- `backend/Dockerfile`: Multi-stage build running as non-root `aiws` (`UID 10001`) with `HEALTHCHECK`.
- `web/Dockerfile`: Fixed missing `public/` copy (`COPY --from=builder /app/public ./public`), runs as non-root `node` with `HEALTHCHECK`.
- `docker-compose.yml`: Bound Postgres/Redis to `127.0.0.1` only, parameterized `POSTGRES_PASSWORD` & `WEB_HOST_PORT` (default `3010`), wired `BRIDGE_INTERNAL_URL=http://bridge:8000` on `rag-worker`, added `no-new-privileges:true`, log rotation (`10m` x 3), and healthchecks across all 5 services.

---

## Phase 5: Automated QA, CI Gate & Browser E2E Verification (COMPLETED)

### Files Created / Modified
- `backend/pyproject.toml`: Configured `[tool.pylint]` gates cleanly matching codebase standards.
- `scripts/qa.ps1`: Added `pylint app` and `compileall` checks alongside `ruff`, `black --check`, `isort --check-only`, `flake8`, `mypy`, and `pytest`.
- `.github/workflows/ci.yml`: Added `pylint` & `compileall` to backend CI and added full `web` CI job (`tsc --noEmit`, `eslint`, `next build`).
- `web/.eslintrc.json`, `web/package.json`: Configured non-interactive ESLint (`next lint`) and `@playwright/test` (`test:e2e` script).
- `web/playwright.config.ts`, `web/e2e/workspace.spec.ts`: Added 5 real-Chrome E2E tests against live Next.js standalone (`127.0.0.1:3010`) + FastAPI Bridge (`127.0.0.1:8010`) + Postgres + Redis.
- `backend/tests/test_adversarial_audit.py`: Added tests covering `build_chat_messages`, `AES-256-GCM` roundtrip & tamper rejection, `Idempotency-Key` replay & `409` conflict, single-use WS ticket & `hw_info`, `/api/internal/embeddings` auth/RPC, admin RBAC/self-lockout/invites/audit/prune, security headers/CSRF, and `.env.example` hygiene.

### Verified Execution Results (Latest Final Gate Run)
- **Alembic Migrations:** `alembic current` -> `0002 (head)`; `alembic upgrade head` -> exit `0`.
- **Backend & PC Worker Gate (`scripts/qa.ps1`):** Exit `0` (`QA OK`):
  - `ruff check`: `All checks passed!`
  - `black --check`: `49 files would be left unchanged.`
  - `isort --check-only`: exit `0`
  - `flake8`: exit `0`
  - `mypy`: `Success: no issues found in 41 source files`
  - `pylint app`: `10.00/10`
  - `compileall`: exit `0`
  - `pytest`: `24 passed, 10 skipped, 1 warning in 94.29s (0:01:34)` *(10 live integration tests in `test_lmstudio_live.py` & `test_rag_live.py` skipped because local LM Studio on `:1234` was unreachable)*.
- **Web TypeScript & ESLint:** `npx tsc --noEmit` -> exit `0`; `npm run lint` (`next lint`) -> exit `0` (`✔ No ESLint warnings or errors`).
- **Web Production Build:** `npm run build` (`next build`) -> exit `0` (`✓ Compiled successfully`, `✓ Generating static pages (9/9)`).
- **Live Backend Smoke (`scripts/live_smoke.py`, `REQUIRE_WORKER=0` against `http://127.0.0.1:8010`):** Exit `0` (`SMOKE OK`; verified `/api/health`, `/api/ready`, `/api/auth/login`, `/api/auth/me`, `/api/admin/stats`, `/api/admin/settings`, `/api/auth/ws-ticket`; optional local LM Studio `:1234` reported `ConnectError`).
- **Real Chrome E2E (`npm run test:e2e`, `channel: "chrome"`):** Exit `0`, **`5 passed (14.5s)`** across:
  1. `/login` local fonts/logo, zero external CDN requests, zero console/page errors, RTL & Dark/Light theme toggle
  2. `/chat` create, native rename dialog, MD/JSON export HTTP 200, native delete dialog
  3. `/knowledge` upload zone, filters & RAG search UI
  4. `/admin` KPIs, dynamic `app_version`, invite create/revoke, self-lockout guard, audit filter & maintenance prune
  5. `390x844` mobile RTL drawer without horizontal overflow
  *(Note: Chrome DevTools MCP `browser` subagent could not attach because no user Chrome remote-debugging `DevToolsActivePort` session was open; real headless Chrome was executed directly via Playwright.)*

---

## Phase 6: Workspace Hygiene & Non-Commit Delivery Gate (COMPLETED)

- Stopped both temporary verification daemons (`uvicorn` `:8010` and `next standalone` `:3010`); verified zero running background tasks.
- Cleaned temporary test/upload artifacts (`backend/storage/uploads/*`, `web/playwright-report`, `web/test-results`).
- Updated `.gitignore` to ignore `.cursor/`, `backups/`, `.eslintcache`, `*.tsbuildinfo`, `web/playwright-report/`, and `web/test-results/`.
- **Non-Commit Mandate Honored:** Zero `git commit`s or pushes performed (`git log -n 1` preserved at `e97f56d`).
