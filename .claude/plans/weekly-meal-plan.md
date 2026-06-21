---
name: weekly-meal-plan
status: done
---

# Weekly Meal Plan: Interactive Planner + Bring Shopping List + Google Calendar

## Goal

A weekly meal planner where the user assigns recipes to days interactively, then:
1. **Shopping list → Bring**: aggregate every ingredient across the week's recipes, run an LLM
   merge/dedupe/sum pass, and push the consolidated list to Bring.
2. **Google Calendar export**: import each meal as an all-day event into a user-selected calendar.

## Decisions (confirmed with user)

- **Meal structure**: multiple recipes per day (ordered list, no fixed breakfast/lunch/dinner slots).
- **Bring**: deeplink + a generated public schema.org HTML page (same mechanism
  [RecipeDetail.tsx](frontend-react/src/components/RecipeDetail.tsx) already uses for `Add to Bring`).
  No Bring account/credentials.
- **Calendar**: all-day events, one per recipe per day, titled with the recipe name.
  - **The Google OAuth consent flow starts on demand when the user clicks "Export to calendar"** — it
    requests calendar read/write, then the user picks a calendar and the events are created.
  - Entirely **frontend / browser-side** via Google Identity Services (GIS): the browser gets a
    short-lived access token and calls the Calendar API directly. **No backend Google code, no token
    storage, no env vars.** The OAuth *Client ID* (a public, non-secret value) lives in frontend config;
    the user creates it once in Google Cloud. App login stays email/password — Google is only for export.

## Architecture notes (current state)

- Backend: FastAPI, SQLite via [api/db.py](backend/api/db.py) (`CREATE TABLE IF NOT EXISTS` + guarded
  migrations in `init_db`). Recipes are JSON blobs in `recipes.recipe_json`.
- Auth: JWT; `get_current_user` / `get_user_id(email)` in [api/auth.py](backend/api/auth.py).
- LLM: OpenAI structured output via `_get_client().beta.chat.completions.parse` in
  [api/recipe_extraction.py](backend/api/recipe_extraction.py) (lazy singleton, key from config).
- Bring: `GET /recipes/{uuid}.html` serves public JSON-LD; frontend opens a
  `api.getbring.com/rest/bringrecipes/deeplink?url=<that html>&...` link. **Bring fetches the URL from its
  own servers**, so the HTML endpoint must be publicly reachable (works in prod, not localhost).
- Frontend: React + Vite, react-query, nav in [Sidebar.tsx](frontend-react/src/components/Sidebar.tsx)
  and [BottomNav.tsx](frontend-react/src/components/BottomNav.tsx); API client in
  [lib/api.ts](frontend-react/src/lib/api.ts); runtime config in [lib/config.ts](frontend-react/src/lib/config.ts).

---

## Phase 1 — Data model & meal-plan CRUD (backend)

### Step 1.1 — Schema

In [api/db.py](backend/api/db.py) `init_db`, add two `CREATE TABLE IF NOT EXISTS`:

- `meal_plan_entries(id INTEGER PK AUTOINCREMENT, user_id INTEGER, date TEXT /* YYYY-MM-DD */,
  recipe_uuid TEXT, position INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)`.
- `shopping_lists(token TEXT PK, user_id INTEGER, items_json TEXT, created_at TIMESTAMP DEFAULT
  CURRENT_TIMESTAMP)` — caches the merged ingredient list so the public Bring HTML endpoint serves it
  without auth.

(No Google-related tables — calendar export is entirely client-side.)

### Step 1.2 — Models

In [api/models.py](backend/api/models.py): `MealPlanEntryCreate {date, recipe_uuid}`,
`MealPlanEntry {id, date, recipe_uuid, recipe_title, position}`, `DateRange {start, end}` (ISO dates).

### Step 1.3 — Router `api/routers/meal_plan.py` (prefix `/meal-plan`, auth required)

- `GET /meal-plan?start=&end=` → entries in `[start, end]` for the user, joined to `recipes.title`,
  ordered by `date, position`. Tolerate entries whose recipe was deleted (skip or mark missing).
- `POST /meal-plan` (body `MealPlanEntryCreate`) → validate the recipe belongs to the user; append with
  `position = max(position)+1` for that day; return the created `MealPlanEntry`.
- `DELETE /meal-plan/{entry_id}` → 204; 404 if not owned.
- `PATCH /meal-plan/{entry_id}` (body `{date?, position?}`) → move/reorder (enables drag-and-drop later;
  deferrable if time-boxed).

Wire the router in [api/main.py](backend/api/main.py).

---

## Phase 2 — Shopping list → Bring (backend + LLM)

### Step 2.1 — LLM merge

New `api/shopping_list.py` with `merge_ingredients(items: list[Ingredient]) -> list[Ingredient]`:
- Uses `_get_client().beta.chat.completions.parse` with a structured-output schema (the `Ingredient`
  model wrapped in a `MergedList` BaseModel).
- Prompt rules: combine identical ingredients; **sum** quantities when units are compatible
  (`2 cups` + `1 cup` → `3 cups`); keep separate line items when units are incompatible or non-numeric
  (`to taste`); normalize names (singular, lowercase) but keep them readable; never invent items.
- Guard: empty `items` → return `[]` (no LLM call). Wrap defensively; on failure fall back to the
  un-merged concatenation so the feature degrades gracefully.

### Step 2.2 — Endpoints (in the meal-plan router)

- `POST /meal-plan/shopping-list` (body `DateRange`, auth) →
  1. Load all entries in range → their recipes → flatten `ingredients`.
  2. `merge_ingredients(...)`.
  3. Persist `{token=uuid4, user_id, items_json}` in `shopping_lists`.
  4. Return `{token, items, bring_url}` where `bring_url` =
     `https://api.getbring.com/rest/bringrecipes/deeplink?url=<api>/meal-plan/shopping-list/{token}.html&source=web`.
     (Return `items` so the frontend can preview/confirm.)
- `GET /meal-plan/shopping-list/{token}.html` (**public, no auth**) → schema.org/Recipe HTML with
  `recipeIngredient: string[]` from the stored merged items — mirrors `get_recipe_html` in
  [api/routers/recipes.py](backend/api/routers/recipes.py). Token is an unguessable uuid4.

---

## Phase 3 — Google Calendar export (frontend only, on-demand OAuth)

No backend changes. The OAuth consent fires when the user clicks **Export to calendar**.

### Step 3.1 — Config

- Add a public OAuth **Client ID** to frontend config — extend
  [lib/config.ts](frontend-react/src/lib/config.ts) with `googleClientId` (read from the existing
  `window.ENV` runtime-config object, falling back to a constant). It is not a secret.
- One-time user setup (documented in plan/README): Google Cloud project → enable **Google Calendar API**
  → create **OAuth Client ID → Web application** → add the app origin to *Authorized JavaScript origins*.
  No client secret, no redirect URI (GIS token flow is popup-based).

### Step 3.2 — GIS token client + hook

- Load the GIS script (`https://accounts.google.com/gsi/client`) — in `index.html` or injected on demand.
- New `hooks/useGoogleCalendar.ts`:
  - `requestAccess()` → `google.accounts.oauth2.initTokenClient({ client_id, scope:
    'https://www.googleapis.com/auth/calendar', callback })` then `requestAccessToken()`. This is what
    triggers Google's consent popup. Resolve with the in-memory access token (short-lived ~1h).
  - `listCalendars(token)` → `GET https://www.googleapis.com/calendar/v3/users/me/calendarList`.
  - `insertEvent(token, calendarId, { summary, date })` → `POST .../calendars/{calendarId}/events` with an
    all-day event (`start.date` = day, `end.date` = day+1 per Google's exclusive-end rule).

### Step 3.3 — Export flow (in the plan page)

Single **"Export to calendar"** button drives the whole sequence:
1. Click → `requestAccess()` → Google consent popup (read/write calendar).
2. On grant → `listCalendars()` → show a calendar picker (default `primary`).
3. User confirms a calendar → `insertEvent` for each entry in the visible week, sequentially; show
   progress and a success toast (`created N events`). Re-export creates duplicates (v1 limitation — note
   it in the confirm step).

---

## Phase 4 — Frontend planner UI

### Step 4.1 — API client

Extend [lib/api.ts](frontend-react/src/lib/api.ts) with: `getMealPlan(start,end)`, `addMealPlanEntry`,
`deleteMealPlanEntry`, `buildShoppingList(start,end)` + matching TS interfaces. (No Google methods —
those go through `useGoogleCalendar`.)

### Step 4.2 — Weekly plan page

- New `pages/WeeklyPlanPage.tsx` at route `/plan` (add to [App.tsx](frontend-react/src/App.tsx) inside
  the authed `AppShell`). Add a "Plan" nav item (calendar icon) to
  [Sidebar.tsx](frontend-react/src/components/Sidebar.tsx) and
  [BottomNav.tsx](frontend-react/src/components/BottomNav.tsx).
- Week view: compute Mon–Sun of the current week; prev/next-week navigation. Desktop: 7-column grid;
  mobile: vertical day cards (reuse the `100svh` + `flex-1 overflow-y-auto` scroll pattern).
- Each day: recipe chips with a remove (×); an "+ Add recipe" button opening a picker modal listing
  `api.listRecipes()` (searchable) → `addMealPlanEntry`. react-query invalidation on mutate.
- (Optional, deferrable) drag-and-drop between days via `PATCH`.

### Step 4.3 — Action bar

- **"Shopping list → Bring"**: `buildShoppingList(weekStart, weekEnd)`, show merged items in a confirm
  sheet, then open `bring_url` (anchor `target=_blank`). Empty week → disabled.
- **"Export to calendar"**: the on-demand OAuth + picker + insert flow from Phase 3.3.

---

## Phase 5 — Tests & verification

- Backend (`backend/tests/`, keep coverage ≥80% per CI):
  - Meal-plan CRUD: add/list/delete, ownership 404s, cross-user isolation, position ordering.
  - Shopping list: mock `merge_ingredients` (like the existing `CANONICAL_RECIPE` mocks in
    [conftest.py](backend/tests/conftest.py)); assert merged items persist and the public `.html`
    endpoint renders JSON-LD and needs no auth.
- Frontend: `npm run build` (tsc) clean; lint clean for new files. The GIS/Calendar path is browser-only
  and verified manually (real Google account); keep that logic thin and isolated in the hook.
- Run `/ci` before finishing.

## Risks / notes

- **Bring reachability**: the shopping-list `.html` must be public for Bring's servers to fetch it — works
  in prod, not on localhost (pre-existing constraint).
- **Google setup** is a one-time user task (OAuth Client ID + Calendar API + authorized origin). The
  "Export to calendar" button should be hidden/disabled when `googleClientId` is unset.
- **Access-token-only flow**: no refresh token; consent is requested each export (or while a cached
  in-memory token is still valid). Nothing Google-related is stored — not in our DB, not sent to our
  backend.
- **Popup blockers**: `requestAccessToken()` must be called directly in the button's click handler so the
  consent popup isn't blocked.
- **Duplicate calendar events** on re-export — v1 limitation; later, tag events to upsert.

## Suggested sequencing

Phase 1 → 2 (planner + Bring list; self-contained, high-value) → Phase 4 UI for those → Phase 3 (frontend
Google export) → Phase 5 throughout.

## Outcome

All phases implemented. `/ci` green: ruff/black/isort/ty clean, 102 backend tests pass (was 90), 86.62%
coverage, frontend `tsc + vite build` clean.

Backend:
- `api/db.py` — added `meal_plan_entries` + `shopping_lists` tables.
- `api/models.py` — `MealPlanEntryCreate/Update`, `MealPlanEntry`, `DateRange`.
- `api/shopping_list.py` — `merge_ingredients()` LLM pass (mirrors recipe_extraction; degrades to
  un-merged on empty/failure).
- `api/routers/meal_plan.py` — GET/POST/PATCH/DELETE `/meal-plan`, `POST /meal-plan/shopping-list`
  (returns `{token, items}`), public `GET /meal-plan/shopping-list/{token}.html`. Wired in `main.py`.
- `tests/test_meal_plan.py` (12 tests) + conftest now binds the new router's db connection.

Frontend:
- `lib/api.ts` — meal-plan CRUD + `buildShoppingList`; `lib/config.ts` — `googleClientId`.
- `hooks/useGoogleCalendar.ts` — on-demand GIS token flow + direct Calendar API (list/insert).
- `pages/WeeklyPlanPage.tsx` — Mon–Sun grid, recipe picker dialog, "Shopping list → Bring" (frontend
  builds the deeplink from the token), "Export to calendar" (consent → calendar picker → all-day events).
- Route `/plan` in `App.tsx`; "Plan" nav item in Sidebar + BottomNav.

Notes for the user:
- **Bring** only works where the `…/shopping-list/{token}.html` page is publicly reachable (prod, not
  localhost) — same constraint as recipe import.
- **Google Calendar** export button is hidden until `GOOGLE_CLIENT_ID` is set (window.ENV or localStorage).
  One-time setup: Google Cloud project → enable Calendar API → OAuth Client ID (Web) → add the app origin
  to Authorized JavaScript origins.
- `merge_ingredients` is covered only via a mock in tests (real LLM path untested); the function guards
  empty input and catches exceptions, falling back to the raw list.

Deferred (optional, noted in plan): drag-and-drop between days (PATCH endpoint exists and is tested,
but no DnD UI yet); de-duplicating calendar events on re-export.
