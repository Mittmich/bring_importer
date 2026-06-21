---
name: calendar-server-sync
status: active
---

# Server-side Google Calendar Sync

Replace the browser-side GIS token flow with a one-time server-side OAuth connection, and
sync the weekly planner to Google Calendar.

## Decisions (confirmed with user)

- **Server-side OAuth (authorization code flow)** with a stored per-user **refresh token**. One-time
  connect. Implemented with **httpx** (no Google SDKs) to keep the image lean.
- **Conflict resolution: planner wins.** The weekly planner is the source of truth.
- **Write trigger: manual "Sync now"** button. No automatic pushes on every edit.
- **On load (connected):** read-only check of the visible week's synced events → surface which meals are
  out-of-sync. No writes on load.
- **Sync now:** for the visible week, create events for unsynced meals and **recreate** events that were
  deleted in Google; store/update the event id per entry.
- **Deleting a meal in the app** deletes its Google event immediately (cleanup; we still hold the id).
- **Events:** all-day, titled with the recipe name, description contains a **link to the recipe**
  (`{app_origin}/recipes/{uuid}` — a non-public/owner link is fine).
- **Client secret** lives as a **GitHub secret**, written into `.env` by the deploy workflow.

## Backend

### config.py
Add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`. Derive `app_origin` (for the
post-connect redirect and recipe links) from `GOOGLE_REDIRECT_URI`, so there's a single source.

### db.py
- New table `google_integrations(user_id PK, refresh_token TEXT, calendar_id TEXT, updated_at)`.
- Guarded migration: `ALTER TABLE meal_plan_entries ADD COLUMN google_event_id TEXT`.

### api/google_calendar.py (httpx)
- `build_auth_url(state)` — consent URL, `access_type=offline&prompt=consent`,
  scope `https://www.googleapis.com/auth/calendar`.
- `exchange_code(code) -> {refresh_token, access_token}`.
- `refresh_access_token(refresh_token) -> access_token`.
- `list_calendars(access_token)`, `insert_event(...) -> event_id`, `delete_event(...)`,
  `event_exists(access_token, calendar_id, event_id) -> bool`.

### api/routers/integrations.py  (prefix `/integrations/google`)
- `GET /connect` (auth) → `{url}` with a short-lived signed `state` (JWT, SECRET_KEY) carrying the user.
- `GET /callback?code=&state=` (no auth) → validate state, exchange code, store refresh token + default
  `calendar_id='primary'`, redirect to `{app_origin}/plan?google=connected`.
- `GET /status` (auth) → `{connected, calendar_id}`.
- `GET /calendars` (auth) → list; `PUT /calendar` (auth) → set `calendar_id`.
- `DELETE /connect` (auth) → disconnect.

### api/routers/meal_plan.py
- Helper `get_access_token(user_id)` → load refresh token, refresh, return access token (or None).
- `DELETE /meal-plan/{id}` → also delete the Google event if `google_event_id` set + connected (best effort).
- `POST /meal-plan/sync` (DateRange) → planner-wins push for the week: ensure each entry has a live event
  (create if no id; recreate if id missing in Google); update ids. Returns counts + fresh status.
- `POST /meal-plan/sync-status` (DateRange) → read-only: classify each entry `synced | missing | unsynced`.
  Used on load. (404/not-connected → all `unsynced`.)

## Frontend

- Remove the GIS browser flow (`useGoogleCalendar` token client). Calendar is now backend-driven.
- `lib/api.ts`: `googleStatus`, `googleConnectUrl`, `googleCalendars`, `setGoogleCalendar`,
  `googleDisconnect`, `syncWeek`, `weekSyncStatus`.
- `WeeklyPlanPage`:
  - If not connected → "Connect Google Calendar" → `window.location = connectUrl`.
  - If connected → show calendar selector + "Sync now"; on mount/week-change call `weekSyncStatus` and
    badge out-of-sync meals; "Sync now" → `syncWeek` then refresh status.
  - On `?google=connected` return → refetch status, clear the query param.

## Deployment

- `deploy-lightsail.yml` "Write .env" step: add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (from GitHub
  secrets) and `GOOGLE_REDIRECT_URI=https://bring.vimi.run/api/integrations/google/callback`.
- Compose `backend` already uses `env_file: .env`, so the vars reach the backend. (No nginx change needed;
  the frontend no longer needs the client id.)
- **User prerequisites:** on the existing OAuth client add Authorized redirect URI
  `https://bring.vimi.run/api/integrations/google/callback`; add `GOOGLE_CLIENT_ID` /
  `GOOGLE_CLIENT_SECRET` as GitHub repo secrets.

## Tests
Mock `api.routers.*` Google helpers (like the `merge_ingredients` pattern). Cover: connect URL, callback
stores token, status, sync creates/recreates, sync-status classification, delete cleanup. Keep ≥80%.

## Outcome

Implemented. `/ci` green locally: ruff/black/isort/ty clean, **114 backend tests pass, 85.05% coverage**,
frontend `tsc + vite build` clean.

- Backend (httpx, no Google SDK): `config.py` (GOOGLE_* + `app_origin`), `db.py`
  (`google_integrations` table + `meal_plan_entries.google_event_id`), `api/google_calendar.py`,
  `api/routers/integrations.py`, and meal-plan `POST /sync`, `POST /sync-status`, plus delete-time event
  cleanup. `tests/test_calendar_sync.py` (12 tests).
- Frontend: removed the GIS browser hook; `WeeklyPlanPage` now connects via the backend, shows a
  **Sync now** button, per-meal sync dots, a calendar-settings dialog (pick calendar / disconnect), and a
  read-only sync-status check on load/week-change.
- Deployment: `deploy-lightsail.yml` writes `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` (from GitHub
  secrets) + literal `GOOGLE_REDIRECT_URI`; backend already loads them via `env_file: .env`.

### User prerequisites (one-time)
1. Add GitHub repo secrets **`GOOGLE_CLIENT_ID`** and **`GOOGLE_CLIENT_SECRET`**.
2. In the Google Cloud OAuth client, add **Authorized redirect URI**
   `https://bring.vimi.run/api/integrations/google/callback`.

### Notes / follow-ups
- Refresh token stored plaintext in SQLite (same trust model as other secrets here).
- The old frontend `GOOGLE_CLIENT_ID` plumbing (env-config.js / nginx sub_filter / `config.googleClientId`)
  is now unused but left in place; safe to remove later.
- `google_calendar.py` is only ~35% covered (network layer is mocked); overall coverage stays ≥80%.
