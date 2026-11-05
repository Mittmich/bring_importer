---
name: admin-control-plane
status: done
updated: 2026-11-05
---

# Admin control plane

## Goal

An in-app admin area where an admin can:

- see all users with usage stats
- create sign-up (invite) links
- issue one-time password-reset links
- disable / re-enable users
- log a user out everywhere
- delete users (with their data)

## Decisions (user, 2026-11-05)

- **Admin role:** `users.is_admin` flag. The first admin is granted via `manage_users.py admin <email>`,
  run on the server by a new `grant-admin.yml` gh workflow. After that, admins promote or demote
  others in the UI. Nobody can demote or disable themselves, and the last admin can't be removed.
- **Password resets:** a one-time reset link valid for 24 h. The admin copies it to the user
  (the app sends no email), so the admin never sees the password.
- **Scope:** all extras (disable, delete, usage stats, log out everywhere).

## Design

### Sessions become revocable

JWTs currently live about 21 days and can't be revoked. To fix that:

- Add `users.token_version` (default 0) and put it in the JWT as `ver`.
- `get_current_user` rejects tokens whose `ver` doesn't match, and rejects disabled users.
  Tokens without `ver` count as version 0, so existing sessions keep working after deploy.
- Bumping the version logs a user out everywhere. Reset and disable both bump it.
- `/token` refuses disabled users and records `last_login_at`.

### Schema (guarded `ALTER TABLE` in `init_db`, like the existing migrations)

- `users`: `is_admin`, `disabled`, `token_version`, `created_at` (NULL for existing users),
  `last_login_at`, `invited_by`.
- New `auth_links` table: `id`, `kind` (`signup` | `reset`), `token_hash` (only a SHA-256 of
  the token is stored, so a DB leak exposes no usable links), `email` (an invite can be locked
  to an address), `user_id` (target of a reset), `note`, `created_by`, `created_at`,
  `expires_at`, `used_at`, `used_by`, `revoked_at`.

### Admin API (`api/routers/admin.py`, `require_admin` dependency → 403 for non-admins)

- `GET /admin/users`: id, email, display name, admin, disabled, created, last login,
  invited by, recipe count.
- `PATCH /admin/users/{id}` `{is_admin?, disabled?}`. Disabling bumps `token_version`.
  Self and last-admin rules apply.
- `POST /admin/users/{id}/logout` bumps `token_version`.
- `POST /admin/users/{id}/reset-link` returns `{token, expires_at}` (24 h). It revokes earlier
  unused reset links for that user.
- `DELETE /admin/users/{id}?confirm=<email>` deletes the user and their data in one transaction:
  - recipes and their images
  - tags and recipe_tags
  - other users' cookbook and meal-plan rows pointing at those recipes
  - meal plan and shopping lists
  - friendships
  - owned cookbooks (with members and entries)
  - cookbook memberships
  - Google integration
  - auth links

  Admins can't delete themselves.
- `GET /admin/invites` lists sign-up links with status (active / used / expired / revoked).
  `POST /admin/invites` `{email?, note?, expires_in_days=7}` returns `{token, …}`.
  `DELETE /admin/invites/{id}` revokes a link.
- The link token is returned only at creation time. The client builds
  `${origin}/signup/<token>` and `${origin}/reset/<token>`.

### Public endpoints (`api/routers/auth.py`)

- `GET /auth/links/{token}` returns `{kind, email?}` for a usable link, otherwise 404.
- `POST /auth/signup` `{token, email, password, display_name?}`: email must match a locked
  invite and must not already exist; password min 8 characters. It creates the user
  (`invited_by`), marks the link used, and returns an access token.
- `POST /auth/reset` `{token, password}`: sets the password, bumps `token_version`, marks the
  link used, and returns an access token.
- Login, signup and reset only ever say "invalid or expired link", never which part failed.

### Frontend (`frontend-react`)

- The profile response gains `is_admin`. Account shows an "Admin" entry for admins only.
- `/admin` page (admin-only; others are redirected):
  - **Users tab:** searchable list with stats and badges (admin, disabled), and a per-user
    menu: Reset password link, Log out everywhere, Disable/Enable, Make/Remove admin, Delete
    (typed-email confirmation).
  - **Sign-up links tab:** create (optional email, note, validity), copy/share the link once,
    list with status, revoke.
  - Generated links are shown in a dialog with Copy and, on phones, the share sheet.
- Public pages `/signup/:token` and `/reset/:token` (outside the app shell, styled like
  `LoginPage`). They validate the link first, then show the form, then log the user in and
  go to `/`.
- All strings in en and de.

### Ops / docs

- `manage_users.py admin <email> [--revoke]` and `.github/workflows/grant-admin.yml`.
- Update AGENTS.md: "no self-registration" becomes "sign-up only via admin invite links".
  README section on admin.

## Steps

- [x] 1. Schema migrations + revocable sessions (`ver` in JWT, disabled check, last login)
- [x] 2. `auth_links` helpers (create/hash/validate/consume) + public link/signup/reset endpoints
- [x] 3. Admin router: users list/patch/logout/reset-link/delete, invites CRUD
- [x] 4. Backend tests (sessions, guards, links lifecycle, cascade delete, access control)
- [x] 5. CLI `admin` command + `grant-admin.yml` workflow
- [x] 6. Frontend: API client, `/admin` page (users + links tabs), link dialog, Account entry
- [x] 7. Frontend: `/signup/:token` and `/reset/:token` pages
- [x] 8. i18n, typecheck/lint/build, end-to-end check against a throwaway server, docs

## Outcome

- **Backend:**
  - `users` gains `is_admin`, `disabled`, `token_version`, `created_at`, `last_login_at` and
    `invited_by`.
  - New `auth_links` table (SHA-256 hashes only).
  - JWTs carry `ver`, and `get_current_user` rejects revoked or disabled sessions. Old tokens
    count as version 0, so nobody is logged out by the deploy.
  - `/token` refuses disabled accounts (403 only after a correct password) and records the
    last login.
  - `api/auth_links.py`; public `GET /auth/links/{token}`, `POST /auth/signup` and
    `POST /auth/reset`.
  - `api/routers/admin.py` covers users list/patch/logout/reset-link/delete (one transaction,
    images removed after commit) and invites list/create/revoke, with self and last-admin
    guards.
  - `manage_users.py admin <email> [--revoke]` and `.github/workflows/grant-admin.yml`, with
    inputs passed via env, not interpolated into scripts.
  - 320 tests pass (13 new in `tests/test_admin.py`).
- **Frontend:**
  - Account → Admin entry for admins.
  - `/admin` with Users (search, stats, badges, ⋯ actions, typed-email delete) and Sign-up
    links (create, status list, revoke) tabs.
  - `LinkDialog` shows a link once, with copy and share.
  - Public `/signup/:token` and `/reset/:token` (`pages/LinkPages.tsx`).
  - en and de strings.
  - tsc and build pass; eslint stays at the 18-error baseline.
- **Verified** end to end over HTTP against a throwaway server: CLI grant, invite, signup,
  reset (old session → 401), disable (login 403), stats, invite status, delete.
- **Not verified:** a visual check in a browser.
