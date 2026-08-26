# Security

**English** · [فارسی](fa/security.md)

## Threat model (phase 1)

- TLS/WSS + authenticated users (cookies) and worker token
- No shared encryption key injected into HTML
- Invite-only registration; open `/api/auth/register` disabled
- Chat and RAG rows scoped by `user_id`
- `unload_models` is admin-only
- Login rate-limited via Redis

## Secrets hygiene

- Never commit `.env` files
- Rotate any key that was previously committed to git history
- Prefer `git filter-repo` / BFG if the repository was public with secrets

## Cookies

`access_token` / `refresh_token`: `HttpOnly`, `SameSite=Lax`, `Secure` when `COOKIE_SECURE=true`.

## Worker TLS

Set `TLS_VERIFY=true` in production. Only disable for lab environments.

## Related

- Root policy: [../SECURITY.md](../SECURITY.md)
- Architecture trust boundaries: [architecture.md](architecture.md)
