---
name: security-audit
status: done
updated: 2026-11-05
---

# Security audit + fixes

## Goal

The user asked on 2026-11-05 for a security audit of the codebase with fixes, paying
attention to the eMudhra certificate problem.

## Findings

| # | Severity | Finding |
|---|----------|---------|
| 1 | High | **eMudhra / certifi (PYSEC-2026-4320):** certifi 2025.4.26 still trusts `emSign ECC Root CA - G3`, whose intermediates have compromised keys. The backend uses that bundle for every outbound TLS call (OpenAI, Google OAuth/Calendar, recipe-URL fetches), so an on-path attacker could forge certificates for those hosts. |
| 2 | High | **Stored XSS:** `GET /recipes/{uuid}.html` and `GET /meal-plan/shopping-list/{token}.html` put the recipe name unescaped in `<title>` and `<h1>`, and `json.dumps` inside `<script>` allows `</script>` breakout. The pages are served from the app's origin, so the script can read the JWT in localStorage. |
| 3 | High | **SSRF:** `POST /recipes/import-url` fetches any URL, including loopback, private, link-local and instance-metadata addresses, follows redirects unchecked, and reads the whole body before the 5 MB check. |
| 4 | High | **Token confusion:** the Google OAuth `state` JWT (`sub` = email, same key) passes as a login token. It appears in the consent URL. |
| 5 | High | **Vulnerable dependencies:** starlette, python-multipart, pyjwt, urllib3, requests, cryptography, idna, anyio, python-dotenv, soupsieve, dnspython; react-router (GHSA-qwww-vcr4-c8h2). |
| 6 | Medium | **Unused `python-jose`:** forgery CVE with no fix; it also pulls in `ecdsa` (Minerva, no fix). Nothing imports it. |
| 7 | Medium | **Fallback `SECRET_KEY`:** a missing env var silently falls back to a public string, which makes tokens forgeable. |
| 8 | Medium | **No brute-force protection:** none on login or on the link endpoints. |
| 9 | Medium | **Password change keeps old sessions alive** (against the AGENTS.md rule). |
| 10 | Medium | **Email enumeration:** login timing reveals which emails exist, because bcrypt runs only for known users. |
| 11 | Medium | **CORS:** `*` with credentials. |
| 12 | Medium | **No security headers:** no HSTS, nosniff, frame-ancestors or Referrer-Policy. Without a Referrer-Policy, `/signup/<token>` and `/reset/<token>` can leak in the Referer. |
| 13 | Low | **OAuth callback:** reflects Google's `error` into the redirect without URL-encoding. |

## Noted, not changed

- **Cloudflare → origin TLS:** the origin uses a self-signed certificate. Cloudflare can verify
  the origin only if it gets a Cloudflare Origin CA certificate and the SSL mode is set to
  "Full (strict)". That is a Cloudflare dashboard step.
- **`/recipes/{uuid}.html` stays unauthenticated:** Bring fetches it server-side. The random
  uuid4 is the only protection.
- **`ssh-keyscan` in deploy workflows** trusts the host on first use. Pinning the host key in a
  secret would be stricter.
- **Friend requests:** they confirm whether an email has an account, but only to logged-in
  users of an invite-only app.

## Steps

- [x] 1. Dependencies: bump certifi ≥ 2026.10.18 and the vulnerable libraries, drop python-jose, migrate `on_event` → lifespan (Starlette 1.x); `npm audit fix`; Docker build pulls a fresh base so system CAs are current
- [x] 2. Safe HTML for the Bring pages (escape + `<`-safe JSON-LD + CSP/nosniff headers), shared helper
- [x] 3. SSRF guard for import-url (http/https only, public IPs only, checked per redirect hop, streamed size cap)
- [x] 4. Auth hardening: reject `purpose` tokens as sessions; random per-process key + loud warning when SECRET_KEY is unset or the old default; dummy bcrypt for unknown users; password change bumps the version and returns a fresh token (frontend stores it); rate limits on /token and /auth/*
- [x] 5. CORS allow-list from env; OAuth error URL-encoded
- [x] 6. nginx security headers (HSTS, nosniff, Referrer-Policy, frame-ancestors, server_tokens off)
- [x] 7. Tests for each fix; lint/type/test/build; pip-audit + npm audit clean; docs

## Outcome

- **eMudhra / certifi:**
  - certifi is now 2026.10.23 (floor `>=2026.10.18` in `pyproject.toml`), and
    `emSign ECC Root CA - G3` is gone from the bundle.
  - The deploy runs `docker compose build --pull`, so the base image's system CAs stay current too.
- **Dependencies:**
  - Targeted upgrades: starlette 1.10, fastapi 0.162, python-multipart, pyjwt 2.15, urllib3 2.8,
    requests, idna, anyio, python-dotenv, soupsieve, dnspython.
  - Removed: `python-jose` (along with ecdsa, rsa, pyasn1 and cryptography).
  - react-router is 7.18.5.
  - `pip-audit` and `npm audit --omit=dev` both report 0. Moderate advisories remain in
    frontend build-only tools.
  - Startup moved to a lifespan handler, and `requires-python` is now >=3.10.
- **XSS:** `api/bring_page.py` renders both Bring pages: escaped text, `<`-safe JSON-LD,
  CSP `default-src 'none'`, nosniff and no-referrer.
- **SSRF:** `api/safe_fetch.py` allows only http(s), only public addresses (checked on every
  resolved IP and again on the connected peer), re-checks redirects itself (max 5) and caps the
  streamed body.
  Checked live: example.com fetched; localhost, 127.0.0.1, 169.254.169.254 and
  ::ffff:10.0.0.1 refused; an expired certificate rejected.
- **Auth:**
  - Tokens carrying `purpose` are refused as sessions.
  - A missing or placeholder `SECRET_KEY` means a random per-process key plus a warning.
  - Unknown emails cost one bcrypt check, so timing doesn't reveal accounts.
  - A password change bumps the token version and returns a fresh token, which the frontend
    stores.
  - Rate limits (15-minute window): 10 failed logins per account, 30 per address, 30 invalid
    links per address. A blocked request gets 429 with Retry-After.
- **CORS:** the `CORS_ORIGINS` allow-list (default: the Vite dev server), no credentials.
  OAuth error reasons are URL-encoded.
- **nginx:** HSTS, nosniff, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
  Permissions-Policy and `server_tokens off`. Cache-busting uses `expires epoch`, so the
  headers aren't dropped per location.
- **Checks:** 361 backend tests pass (new: `tests/test_security.py`, `tests/test_safe_fetch.py`).
  ruff, black and isort are clean; ty is at 7 diagnostics, below the baseline of 8; tsc and
  build pass; eslint is at its baseline.
- **Not verified locally:** `nginx -t`, because Docker isn't installed here. CI's Docker build
  and the deploy cover it.
