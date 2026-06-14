---
title: Comprehensive recipe management with URL + image import + frontend tests
status: draft
created: 2026-06-14
updated: 2026-06-14
scope: fullstack
---

# Plan: Comprehensive recipe management with URL + image import

## Context

The app is currently structured as a "Recipe to Bring Importer": the home page (`index.html`) is a photo-upload form, parsing a photo with OpenAI's vision model is the only entry point, and the next obvious step after a successful parse is to push the result to a Bring shopping list. There is no notion of a personal recipe library — the `/recipes` listing was added later but is read-only, has no edit/delete, and (a small bug) returns every user's recipes to anyone who hits it.

**Related plan:** `.pi/plans/2026-06-14-add-backend-tests-precommit-ci.md` (draft) is building the test scaffolding, pre-commit hooks, and CI pipeline. This plan assumes that scaffolding is in place — new tests added here land in the same `backend/tests/` tree, and we don't re-do the `_extract_recipe_from_html` refactor that plan covers.

The user wants the framing flipped: this is a **recipe management** tool, of which importing is one feature. Importing must accept both **photos** (already works) and **webpage URLs** (new — feasibility to confirm during the first step). After import, the recipe is saved to the user's library and the recipe detail page offers **"Add to Bring"** as one of several actions (alongside Edit, Delete, View raw HTML, etc.).

## Goals

- A logged-in user has a personal **recipe library** (list + detail) that is the primary surface of the app.
- Recipes can be created by **importing from an image** (existing) or by **importing from a webpage URL** (new).
- "**Add to Bring**" is a per-recipe action on the detail page, not the implicit next step after import.
- Full **CRUD** on recipes: Create (import), Read (list + detail), Update (edit form), Delete (with confirmation).
- `/recipes` is **scoped to the current user**; cross-user leak is fixed.
- A short, optional **note** the user can attach to a saved recipe (small text field) is in scope as the only non-import metadata. No tags, no categories, no sharing, no favourites.
- **Automated frontend tests** covering the critical user flows, runnable locally and in CI:
  - **Unit tests** for the pure helpers in the frontend (recipe→HTML rendering, ingredient-line parsing, URL validation, etc.).
  - **End-to-end tests** that drive the actual pages in a real browser, mocking OpenAI and external fetches, and verifying: login → import (photo + URL) → library list → detail page → edit → delete → "Add to Bring" widget load.
  - Frontend test jobs are wired into CI alongside the backend test job.

## Non-goals

- Tags, categories, favourites, collections, or any other organisation primitive.
- Notes with rich text or per-ingredient notes (just a single free-form text field per recipe).
- Sharing recipes between users or generating public links beyond the existing `/recipes/{uuid}.html` Bring endpoint.
- Adjusting serving sizes with automatic ingredient rescaling.
- Re-importing / re-parsing a recipe in place (delete + re-import is acceptable for v1).
- Storing uploaded images; the recipe's source image is whatever HTML the import produced.
- Mobile-app shell changes (PWA install flow stays as-is).
- Frontend **visual regression** testing, **Lighthouse** audits, **a11y** audits beyond what Bootstrap gives us, **i18n**, or **performance** budgets.
- Testing the third-party Bring widget itself (it's an opaque `<script>` from `platform.getbring.com`; we only assert that we *invoke* it correctly with the right URL).
- Cross-browser E2E coverage: Playwright supports it, but we only target **Chromium** for v1 to keep install size and CI time down. Firefox/WebKit are follow-ups.
- Migrating the frontend to a bundler/build tool (Webpack/Vite/Rollup). Tests use Vitest's built-in dev server; the app itself stays as plain script tags.

## Feasibility check (must be done first)

The user asked us to "check which is possible" for webpage import. Before committing to the design, the executor must do a small spike and record findings. Three strategies are realistic, with very different tradeoffs:

1. **schema.org JSON-LD in the page.** Most major recipe sites (NYT Cooking, Bon Appétit, Serious Eats, Allrecipes, Food Network, King Arthur, BBC Good Food, etc.) embed a `<script type="application/ld+json">` block whose `@type` is `Recipe`. Fetching the URL, parsing HTML, and extracting this block is straightforward with `beautifulsoup4` (already a dep) and gives clean, structured data with no LLM cost. **Expected coverage: very high for mainstream sites, low for personal blogs.**
2. **`recipe-scrapers` Python library** (https://github.com/hhhonzik/recipe-scrapers). Knows ~330 site-specific scrapers. Useful as a fallback for sites that don't expose clean JSON-LD. Adds a dep but is MIT-licensed and widely used.
3. **OpenAI text extraction.** Fetch the HTML, strip to a reasonable size, send to `gpt-4o-mini` (cheap) with the same schema.org/Recipe prompt we already use. Works on **any** page, including personal blogs, but costs money per import and adds 2–10 s latency.

**Recommended approach for v1:** try (1), and if it fails, fall back to (3) automatically. (2) is a future optimisation if/when JSON-LD coverage proves insufficient. Skip (4) (render-to-image) entirely — too expensive and slow.

The first step below formalises this spike; if it surfaces something that breaks the recommendation (e.g. JSON-LD is unexpectedly rare in the user's real-world use), the executor should pause and re-plan.

## Steps

1. [ ] **Refactor: split `backend/api.py` into a `backend/api/` package with focused modules.**
   - `api.py` is currently 419 lines with 32 top-level definitions and is about to grow further (steps 2–4 add three new endpoints, auth tightening, and schema migration). Split it into a package **without changing any HTTP behavior or any symbol name the existing tests touch**:
     ```
     backend/api/
     ├── __init__.py        # re-exports `app` for `run.py` + back-compat re-exports of names the existing tests import/monkeypatch
     ├── main.py            # FastAPI() instance, CORS middleware, startup event, include_router calls
     ├── config.py          # env loading (load_dotenv), OPENAI_API_KEY, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
     ├── db.py              # get_db_connection(), init_db() (schema migration arrives in step 3)
     ├── models.py          # Pydantic: Token, TokenData, User, UserInDB, Recipe, RecipeCreate, RecipeResponse
     ├── auth.py            # pwd_context, get_password_hash, verify_password, authenticate_user, get_user, get_user_id, create_access_token, get_current_user
     ├── recipe_extraction.py # parse_recipe_with_openai, _extract_recipe_from_html (the tests/CI plan's step 4 refactor lands here automatically)
     └── routers/
         ├── __init__.py
         ├── auth.py        # APIRouter → POST /token
         ├── recipes.py     # APIRouter → POST /recipes/parse, GET /recipes, GET /recipes/{uuid}.json, GET /recipes/{uuid}.html  (PUT, DELETE, /import-url added in steps 3–5)
         └── health.py      # APIRouter → GET /health
     ```
   - `api/__init__.py` re-exports:
     - `app` (so `from api import app` in `run.py` and the tests/CI plan's `conftest.py` keeps working);
     - the names the existing 64 tests use or monkeypatch: `get_db_connection`, `init_db`, `get_password_hash`, `verify_password`, `get_user`, `get_user_id`, `authenticate_user`, `get_current_user`, `create_access_token`. A short comment documents these as "back-compat re-exports for existing tests; new code imports from the focused modules directly."
   - `api/main.py` does `app.include_router(auth_router)`, `app.include_router(recipes_router)`, `app.include_router(health_router)`. The HTTP surface is byte-for-byte identical to today (same paths, same methods, same request/response shapes, same status codes).
   - `pyproject.toml` `[tool.setuptools]` changes from `py-modules = ["api", "run", "manage_users", "generate_password"]` to `py-modules = ["run", "manage_users", "generate_password"]` and adds `packages = ["api", "api.routers"]`. The `manage_users` / `run` / `generate_password` flat modules stay as-is to keep this step small.
   - Delete the old `backend/api.py` file once the package is in place (the package takes its place; nothing else references the file by path).
   - **Explicitly out of scope for this step** (called out so they don't sneak in):
     - Replacing `@app.on_event("startup")` with a lifespan context manager. Tracked separately; the existing deprecation warning stays.
     - Replacing `datetime.utcnow()` in `create_access_token` (also a pre-existing deprecation warning).
     - The schema migration in step 3; this step only moves the **existing** `init_db` and `get_db_connection` into `db.py` unchanged.
     - The new endpoints in steps 3–5; this step only moves the **existing** routes into the routers unchanged.
   - Verify:
     - `cd backend && source .venv/bin/activate && python -c "import api; print(api.app)"` → prints the FastAPI app.
     - `cd backend && source .venv/bin/activate && python -c "from api.routers import auth, recipes, health"` → no `ImportError`.
     - `cd backend && source .venv/bin/activate && ruff check api/ && black --check api/ && isort --check-only api/` → no new drift.
     - `cd backend && source .venv/bin/activate && pytest -q` → all 64 existing tests from the tests/CI plan still pass; the back-compat re-exports cover every monkeypatch target.
     - Manual: `cd backend && source .venv/bin/activate && python run.py & sleep 2 && curl -s http://localhost:8001/health && kill %1` → `{"status": "healthy", ...}` and clean exit.

2. [ ] **Feasibility spike for URL import.**
   - In a scratch script (`backend/_spike_url_import.py`, gitignored), write a function that takes a URL, fetches the HTML with a realistic `User-Agent`, and tries JSON-LD extraction.
   - Test against ~5 representative URLs spanning mainstream recipe sites and a personal blog (e.g. one NYT, one Allrecipes, one personal `wordpress.com` blog). Record hit/miss and parse quality in a short `## Spike results` section appended to this plan file.
   - If JSON-LD coverage is acceptable (≥3/5 clean hits), proceed with strategy 1+3. Otherwise, add `recipe-scrapers` to `pyproject.toml` dependencies and revise step 5 to include it.

3. [ ] **Backend: scope `/recipes` to the current user and require auth on mutating endpoints.**
   - The current `GET /recipes` returns rows for every user; require `Depends(get_current_user)` and filter by `user_id`.
   - Verify `GET /recipes/{uuid}.json` and `GET /recipes/{uuid}.html` keep working without auth (Bring needs them to be publicly fetchable).
   - Add `created_at` and `updated_at` to the `recipes` table; store the user's note in a new nullable `note TEXT` column. Schema-migration in `init_db()` (use `ALTER TABLE … ADD COLUMN` guarded by a `pragma_table_info` check; SQLite has no `IF NOT EXISTS` for columns). The `init_db` to extend is now the one in `api/db.py`.
   - Extend the in-DB `recipe_json` shape with `source: { kind: "image" | "url", value: <base64-truncated-or-url> }` so the detail page can show "Imported from photo" / "Imported from https://…". Don't break existing rows — backfill with `{"kind": "unknown"}` on read.
   - Drop the back-compat re-export of any name that *only* existed to support the tests, if the tests no longer need it. Keep the `app` and the test-mutated names re-exported.

4. [ ] **Backend: add `PUT /recipes/{uuid}` and `DELETE /recipes/{uuid}`.**
   - Both require auth; the recipe's `user_id` must match `current_user`.
   - `PUT` accepts a `RecipeUpdate` body: `title`, `recipeIngredient`, `recipeYield`, `description`, `note`, plus the full `html_content` (the editor will preserve the original markup). Returns the updated recipe.
   - `DELETE` returns 204; the public JSON/HTML endpoints will then 404, which is fine for Bring.
   - Both return 404 (not 403) on foreign-recipe access to avoid leaking which UUIDs exist.
   - Routes go in `api/routers/recipes.py`; Pydantic models go in `api/models.py` (extend, don't replace).

5. [ ] **Backend: add `POST /recipes/import-url` and align the image endpoint response shape.**
   - Body: `{"url": "https://…", "note": optional}`. Auth required.
   - Fetch the page server-side using `httpx` (10 s timeout, max 5 MB, real `User-Agent`). Return 422 on fetch failure with a clear error.
   - Run the JSON-LD extractor (lives in `api/recipe_extraction.py`); if it finds a `Recipe`, normalise into our `Recipe` shape. Otherwise, fall back to OpenAI text extraction with a prompt equivalent to the image one (drop the image, pass the cleaned HTML body up to ~30 K chars).
   - Store with `source = {"kind": "url", "value": url}`. Generate a new `uuid` (re-using the existing flow). Return the same `RecipeResponse` shape the image endpoint uses.
   - **Image endpoint alignment**: the image endpoint already saves; just make its response identical to the URL one (uuid + url). This is a one-line change in `api/routers/recipes.py` since both endpoints now call the same `RecipeResponse` model.
   - The shared "save + return `RecipeResponse`" helper goes in `api/recipe_extraction.py` (or a new `api/services/recipes.py` if the executor prefers a `services/` layer — either is fine; the plan doesn't dictate the helper's exact home as long as both routes use it).

6. [ ] **Backend: add the new tests for the URL import and CRUD paths.**
   - Tests (live in `backend/tests/test_recipes.py`, which the tests/CI plan already provisions via `conftest.py`, `mocked_openai`, `auth_headers`, etc.):
     - one happy-path test for JSON-LD extraction in the URL import path
     - one happy-path test for the OpenAI-text fallback when JSON-LD is missing
     - one test for `PUT /recipes/{uuid}` round-trip
     - one test for `DELETE /recipes/{uuid}` and the resulting 404 on the public endpoints
     - one test for the auth-scoping bug fixed in step 3 (user A must not see user B's recipes)
   - These tests import from the new module locations (`api.db.init_db`, `api.auth.create_access_token`, `api.routers.recipes`, etc.) — the back-compat re-exports in `__init__.py` are no longer needed by new code.

7. [ ] **Frontend: reframe the home page as a recipe library, with import as one of two actions.**
   - Rename `index.html` semantics to "My Recipes" while keeping the file name (avoid breaking the deep links) and `Recipe to Bring` in the title is replaced with the user's library framing.
   - The page body becomes: heading "My Recipes", a row of action buttons "Import from photo" and "Import from URL", then a list of recent recipes (≤10, with a "See all" link to the existing `recipes.html`).
   - "Import from photo" opens a modal with the current photo-upload + preview + Parse flow. After parse: "Save to library" (primary) and "Add to Bring" (secondary). Saving returns to the home and toasts "Saved". "Add to Bring" saves then navigates to `recipe-data.html?id=…`.
   - "Import from URL" opens a modal with a URL input and optional note. Submit → loading state → preview → "Save to library" / "Add to Bring" (same as photo flow).
   - On error, the modal stays open with a human-readable message and a "Try again" button.

8. [ ] **Frontend: add an Edit Recipe page (`edit-recipe.html?id=…`).**
   - Fetches the recipe, prefills a Bootstrap form (title, yield, description, note, ingredients as a textarea with one per line).
   - "Save" calls `PUT /recipes/{uuid}`; on success, navigate back to the detail page.
   - "Cancel" navigates back without saving.
   - Keep the `html_content` as a hidden field on the form and PUT it back unchanged — the editor only touches the structured fields for v1.

9. [ ] **Frontend: surface the per-recipe actions on `recipe-data.html`.**
   - Add a button group near the title: **"Add to Bring"** (primary), **"Edit"**, **"Delete"** (danger), plus the existing **"View HTML Source"** and **"Open Raw HTML"** in a secondary group.
   - "Add to Bring" scrolls to / reveals the existing `bringImportCard` and re-invokes `showBringWidget(uuid)`.
   - "Delete" shows a Bootstrap confirm modal ("Delete *{title}*? This cannot be undone."), then calls `DELETE /recipes/{uuid}` and navigates to `index.html` on success.
   - "Edit" navigates to `edit-recipe.html?id=…`.

10. [ ] **Frontend: enforce auth and ownership on the listing.**
    - `recipes.html` already calls `/recipes`; with the backend now requiring a token, add the `Authorization: Bearer …` header.
    - If a user navigates to `recipe-data.html?id=…` for a recipe they don't own (only possible by typing a UUID), the detail page should show a friendly "Recipe not found" rather than the current generic 404.

11. [ ] **Docs and housekeeping.**
    - Update the top-level `README.md`: reframe the "Features" and "How to Use" sections around the library, mention URL import, mention edit/delete, and remove the now-misleading "Recipe to Bring Importer" framing (or keep the name and adjust the description).
    - Add a short "Privacy & external requests" note: imported URLs are fetched server-side and the raw HTML is sent to OpenAI for parsing when JSON-LD is not present.
    - No DB-format change is breaking for existing users, but add a one-line note in `manage_users.py --help` output pointing at the new `note` column.

12. [ ] **Frontend: set up test infrastructure.**
    - The frontend currently has no Node project. Create `frontend/package.json` with `"private": true`, `"type": "module"`, and these devDependencies: `vitest@^2`, `jsdom@^25`, `@vitest/coverage-v8@^2`, `@playwright/test@^1.47`, `http-server@^14`. No `dependencies` block — the app itself doesn't ship any npm packages.
    - Add `package.json` scripts:
      - `test` → `vitest run`
      - `test:watch` → `vitest`
      - `test:coverage` → `vitest run --coverage`
      - `test:e2e` → `playwright test`
      - `test:e2e:headed` → `playwright test --headed`
    - Create `frontend/vitest.config.js` with `environment: 'jsdom'`, `test/include: ['tests/unit/**/*.test.{js,ts}']`, `test/coverage/reporter: ['text', 'html']`, and a `setupFiles: ['tests/unit/setup.js']` that stubs the small set of browser APIs the helpers need (`Image`, `FileReader` are already present in jsdom, but `crypto.subtle` and `matchMedia` may not be).
    - Create `frontend/playwright.config.js` with:
      - `testDir: 'tests/e2e'`
      - `use.baseURL: 'http://localhost:8000'` (the static frontend)
      - `webServer`: an array with two entries: the FastAPI backend (`uvicorn api.main:app --port 8001`, working dir `../backend`, reusing the existing `.venv`) and `npx http-server . -p 8000 -s` for the frontend
      - `use.actionTimeout: 10000` and `expect.timeout: 10000` (the OpenAI path can be slow when not mocked)
      - A single `projects: [{ name: 'chromium', use: devices['Desktop Chrome'] }]` block
    - Add `frontend/.gitignore` entries: `node_modules/`, `test-results/`, `playwright-report/`, `coverage/`, `playwright/.cache/`.
    - Add a one-line `frontend/README.md` (or section in the top-level README) explaining `npm install && npm test` and `npm run test:e2e`.
    - Verify locally: `cd frontend && npm install && npm test` runs zero tests green, and `npx playwright install --with-deps chromium` succeeds. This step is green-on-empty before the next step adds real tests.

13. [ ] **Frontend: extract testable pure helpers and add Vitest unit tests.**
    - Refactor `app.js`: pull `createSimpleRecipeHtml` (and any other pure data→DOM or data→string functions written in steps 7–9) out into a new `frontend/js/lib/recipe-html.js` that attaches to `globalThis.recipeLib` (or `window.recipeLib`) using a tiny UMD-ish shim:
      ```js
      (function (root) {
        function createSimpleRecipeHtml(data) { /* ... */ }
        function parseIngredientsTextarea(text) { /* returns string[] */ }
        function isLikelyRecipeUrl(url) { /* returns boolean */ }
        root.recipeLib = { createSimpleRecipeHtml, parseIngredientsTextarea, isLikelyRecipeUrl };
      })(typeof window !== 'undefined' ? window : globalThis);
      ```
    - `app.js`, `edit-recipe.html`, and any other consumer loads the file with `<script src="js/lib/recipe-html.js"></script>` *before* the page script.
    - Add `frontend/tests/unit/recipe-html.test.js` with cases for:
      - `createSimpleRecipeHtml` with full data, missing fields, special characters (e.g. `&`, `<`, emoji)
      - `parseIngredientsTextarea` with one-per-line input, blank lines, leading/trailing whitespace
      - `isLikelyRecipeUrl` accepts `https://example.com/cookies`, rejects `not-a-url`, `javascript:`, `file:///`, empty string
    - Add a coverage threshold: `test/coverage/thresholds: { lines: 80, functions: 80, statements: 80, branches: 70 }` on the `js/lib/**` glob. Helper files are small and well-suited to a high bar.
    - Verify: `cd frontend && npm test` and `cd frontend && npm run test:coverage` both pass; the coverage report shows ≥80% on `js/lib/**`.

14. [ ] **Frontend: add Playwright E2E tests for the full user flow.**
    - `frontend/tests/e2e/fixtures.js` (or `playwright.config.js`'s `use.extraHTTPHeaders`) mocks:
      - `POST **/v1/chat/completions` (OpenAI) → returns a canned schema.org/Recipe HTML response so the image and URL flows complete without hitting OpenAI.
      - `GET **://platform.getbring.com/**` → returns a stub script that exposes a fake `window.bringwidgets.import.setUrl` which records the last URL (so the test can assert on it). Avoids a real third-party dependency in CI.
      - `GET https://example-recipes.test/allrecipes/cookies` and a few more (recorded in `frontend/tests/e2e/mocks/`) → returns saved HTML fixtures used by the URL import path. The URL import backend route hits the *server*, not the browser, so these mocks go on the backend's outbound fetches via `httpx` monkeypatching in a `conftest.py` (already plumbed by the tests/CI plan's `mocked_openai` fixture pattern — extend that file with `mocked_url_fetch`).
    - Specs (one file per area, all under `frontend/tests/e2e/`):
      - `auth.spec.js` — login page renders, wrong password shows the error, correct password (from a fixture user seeded in the backend) lands on `index.html`. The session is saved to `storageState` for reuse.
      - `home.spec.js` — empty state shows "No recipes yet" (or whatever step 7 lands on); "Import from photo" and "Import from URL" buttons open the right modals; the modal close button works.
      - `import-photo.spec.js` — happy path: pick a small test image, the mock OpenAI response is parsed, the preview shows, "Save to library" closes the modal and the recipe appears on the home page and `/recipes`. Error path: image too large / parse failure → modal stays open with a human-readable error.
      - `import-url.spec.js` — happy path with the mock URL returning a JSON-LD recipe; happy path with the mock URL returning plain HTML (forcing the OpenAI fallback); error path with a 404.
      - `library.spec.js` — list shows the imported recipes in reverse-chronological order; clicking a row navigates to the detail page.
      - `detail.spec.js` — Add to Bring button shows the bringImportCard and the mocked widget received the correct `${frontendUrl}/api/recipes/{uuid}.html` URL; Edit and Delete buttons are present and visible.
      - `edit.spec.js` — change a field, save, detail page reflects the change, backend `GET /recipes/{uuid}.json` returns the updated value.
      - `delete.spec.js` — Delete opens a confirm modal; cancelling keeps the recipe; confirming removes it from the list and the public JSON endpoint now 404s.
      - `auth-scoping.spec.js` — log in as user A, import a recipe, log out, log in as user B, assert user B's home is empty and `/recipes/{A's uuid}.json` still 404s or returns "not found" (depending on whether the public endpoint stays public — this is an intentional check of the chosen security model).
    - Run on CI only the chromium project; skip Firefox/WebKit with a comment that they can be added by uncommenting one line.
    - Verify: `cd frontend && npm run test:e2e` is green on a clean checkout (after `npx playwright install chromium`); total runtime under 3 minutes locally.

15. [ ] **Backend: wrap `verify_password` to return `False` for unknown hash formats instead of raising.**
    - Discovered during execution of the tests/CI plan: `passlib.context.CryptContext.verify(plain, garbage_hash)` raises `passlib.exc.UnknownHashError`; the plan's claim that it returns `False` was wrong. The current test (`backend/tests/test_password.py::test_verify_password_non_bcrypt_hash_raises`) asserts the raise, which is the actual behavior today.
    - Change the wrapper to be more robust for production. The function lives in `backend/api.py` today; after step 1 of this plan, it moves to `backend/api/auth.py`. Modify in place:
      ```python
      def verify_password(plain_password: str, hashed_password: str) -> bool:
          try:
              return pwd_context.verify(plain_password, hashed_password)
          except passlib.exc.UnknownHashError:
              return False
      ```
    - Update `backend/tests/test_password.py`: rename `test_verify_password_non_bcrypt_hash_raises` to `test_verify_password_non_bcrypt_hash_returns_false` and flip the assertion to `assert api.verify_password("any-password", "not-a-bcrypt-hash") is False`. Add a one-line comment explaining the change: "Unknown hash formats (e.g. users migrated from another auth system) are treated as 'no match' rather than crashing the request."
    - **Do not wrap `get_password_hash` in the same way.** A failure to hash a new password is a programmer/config error, not a user-facing input error; surface it.
    - Verify:
      - `cd backend && source .venv/bin/activate && pytest tests/test_password.py -v` — all password tests pass, including the renamed one.
      - `cd backend && source .venv/bin/activate && ruff check api/ tests/ && black --check api/ tests/ && isort --check-only api/ tests/` — no new drift.
      - Manual: re-run the full suite to confirm no regression: `cd backend && source .venv/bin/activate && pytest -q`.

16. [ ] **Backend: add type hints across `api/` and `manage_users.py`; tighten CI `typecheck` to fail on errors.**
    - Discovered during execution of the tests/CI plan: the existing `[tool.mypy]` config in `backend/pyproject.toml` is strict (`disallow_untyped_defs = true`, `check_untyped_defs = true`, `disallow_untyped_decorators = true`, etc.) and `api.py` / `manage_users.py` are untyped. The CI workflow's `typecheck` job runs with `continue-on-error: true` to avoid blocking the first PR. This step is the follow-up that delivers on the existing strict config.
    - Scope of the typing work (start at the public surface; can iterate in further follow-ups if the codebase is larger than expected):
      - `backend/api/auth.py` — `get_password_hash`, `verify_password`, `authenticate_user`, `get_user`, `get_user_id`, `create_access_token`, `get_current_user`. Include the `passlib.exc.UnknownHashError` catch added in step 15.
      - `backend/api/db.py` — `get_db_connection`, `init_db`.
      - `backend/api/recipe_extraction.py` — `parse_recipe_with_openai`, `_extract_recipe_from_html`. The BeautifulSoup/regex block in `_extract_recipe_from_html` benefits most from hints because it touches many types.
      - `backend/api/models.py` — Pydantic models are already typed by definition; verify the imports re-export cleanly.
      - `backend/api/routers/{auth,recipes,health}.py` — typed signatures on every route handler. The Depends-in-default-value B008 lint hit goes away once FastAPI's own type stubs catch up; if it still fires, add a single `# noqa: B008` per file.
      - `backend/api/main.py` and `backend/api/config.py` — typed.
      - `backend/manage_users.py` — every public function (`add_user`, `remove_user`, `list_users`, `check_db`, `main`).
    - Once the typing work is done, tighten CI:
      - In `.github/workflows/ci.yml`, change the `typecheck` job's `continue-on-error: true` to `continue-on-error: false` (or remove the line entirely; `false` is the default).
      - In the root `Makefile`, the existing `typecheck` target already runs `mypy .` — confirm it's still wired correctly after the package split.
    - Expected noise: a few `Any` casts in the BeautifulSoup paths and the `responses` mock typing; that's fine, comment why.
    - Verify:
      - `cd backend && source .venv/bin/activate && mypy .` — exits 0 with no errors.
      - `cd backend && source .venv/bin/activate && pytest -q` — all 64+ tests still pass (the new types don't change runtime behavior).
      - Push to a PR; confirm the `CI / Type-check` job in GitHub Actions is green (no longer "expected to fail").
    - This step is intentionally not a `mypy --strict` overhaul. We're closing the gap between the existing strict config and the current untyped code, not raising the bar further.

17. [ ] **Add a `gitleaks` pre-commit hook for secret detection.**
    - Deferred follow-up noted in `.pre-commit-config.yaml` (the file has a comment block listing `gitleaks/gitleaks` as optional). Land it now that the rest of the pre-commit stack is green.
    - Add a `gitleaks` repo block to `.pre-commit-config.yaml`, pinned to a specific tag (e.g. `v8.18.4` or whatever the current stable is at execution time):
      ```yaml
      - repo: https://github.com/gitleaks/gitleaks
        rev: v8.18.4
        hooks:
          - id: gitleaks
      ```
    - Gitleaks scans the working tree. The hook needs no `files:` filter — we want it to scan everything that could contain a secret.
    - If gitleaks fires on a false positive (e.g. a test fixture with a deliberately fake API key, or the canonical test secret in `backend/tests/conftest.py` — `"test-secret-key-for-jwt-signing-only"`), add a `.gitleaks.toml` or `.gitleaksignore` with the path/rule. The "test-secret-key-for-jwt-signing-only" string is a known-safe value; whitelist the line.
    - Install the gitleaks binary on developer machines (the hook uses it). Document in the hook's installation step: `brew install gitleaks` on macOS, `apt install gitleaks` on Debian/Ubuntu, or rely on the pre-commit framework's auto-install.
    - Verify:
      - `cd backend && source .venv/bin/activate && pre-commit run gitleaks --all-files` — exits 0; either nothing flagged, or the only findings are the whitelisted test secrets.
      - Add a deliberate test: drop a string that looks like an AWS access key into a throwaway file, run the hook, confirm it fires, then delete the file.
      - Push a commit; the hook fires in CI-equivalent (locally) on every commit.

18. [ ] **Frontend: add a linter and formatter setup (eslint + prettier).**
    - Discovered during execution of the tests/CI plan: the backend has ruff + black + isort, with a pre-commit chain and a CI job enforcing them. The frontend (after step 12 of this plan) has Vitest + Playwright, but **no linter and no formatter** — JS/CSS/HTML drift will accumulate silently.
    - Add to `frontend/package.json` devDependencies: `eslint@^9`, `eslint-plugin-no-unsanitized@^4` (catches `innerHTML` and similar XSS sinks, which the recipe→HTML helpers will use heavily), and `prettier@^3`. Pin minor versions in `package-lock.json` (committed).
    - Create `frontend/eslint.config.js` using ESLint's flat config format:
      ```js
      import js from '@eslint/js';
      import noUnsanitized from 'eslint-plugin-no-unsanitized';
      export default [
        js.configs.recommended,
        {
          plugins: { 'no-unsanitized': noUnsanitized },
          rules: {
            'no-unsanitized/no-innerhtml': 'warn',
            'no-unsanitized/custom-rules': 'warn',
            'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
          },
        },
        { ignores: ['node_modules/**', 'coverage/**', 'playwright-report/**', 'test-results/**'] },
      ];
      ```
    - Create `frontend/.prettierrc.json` with `{"singleQuote": true, "trailingComma": "all", "printWidth": 100}` and `frontend/.prettierignore` for `node_modules/`, `coverage/`, `playwright-report/`.
    - Add npm scripts in `frontend/package.json`:
      - `lint` → `eslint .`
      - `lint:fix` → `eslint . --fix`
      - `format` → `prettier --write .`
      - `format:check` → `prettier --check .`
    - Add a `frontend-lint` job to `.github/workflows/ci.yml` (parallel to the existing `lint`, `typecheck`, `test`, `frontend-unit`, `frontend-e2e` jobs): `cd frontend && npm ci && npm run lint && npm run format:check`. Cache `~/.npm` keyed on `frontend/package-lock.json` for speed.
    - In the root `Makefile`, extend `make lint` to also run `cd frontend && npm run lint` (only if `frontend/node_modules/` exists; otherwise skip with a one-line note). This keeps the local `make lint` parity with the full CI matrix.
    - **Frontend pre-commit hook (optional, follow-up).** The plan does not add frontend pre-commit hooks in this step (would require a Node-based pre-commit stage, which the existing `.pre-commit-config.yaml` doesn't run for `^frontend/`). The CI `frontend-lint` job is the primary enforcement; pre-commit on frontend can be added in a later plan.
    - Verify:
      - `cd frontend && npm install && npm run lint && npm run format:check` — exits 0 on a clean tree.
      - `cd frontend && npm run lint:fix && npm run format` — reformats any drift; commit the result separately.
      - Push a PR; the `CI / frontend-lint` job is green.
      - `cd /workspace && make lint` runs both backend (ruff/black/isort) and frontend (eslint/prettier) and exits 0.

## Files to touch

- `backend/api/` (new package, step 1) — split of the current `api.py` into `__init__.py`, `main.py`, `config.py`, `db.py`, `models.py`, `auth.py`, `recipe_extraction.py`, and `routers/{auth,recipes,health}.py`. The old `backend/api.py` is deleted.
- `backend/api.py` — **deleted** in step 1. New endpoints, scoping, and schema migration go into the focused modules (`api/routers/recipes.py`, `api/db.py`, etc.) in steps 3–5, not back into a single file.
- `backend/pyproject.toml` — change `[tool.setuptools]` from `py-modules = ["api", …]` to `py-modules = ["run", "manage_users", "generate_password"]` + `packages = ["api", "api.routers"]` (step 1). Also add `httpx` for the URL import (step 5) and `recipe-scrapers` only if the spike in step 2 demands it. The test/CI plan handles the `[project.optional-dependencies.dev]` additions, so we don't touch that here.
- `backend/_spike_url_import.py` (new, gitignored) — feasibility script.
- `backend/tests/test_recipes.py` (new file) — JSON-LD extraction, OpenAI-text fallback, PUT, DELETE, auth scoping. Shares `conftest.py` fixtures with the tests/CI plan. Extended with `mocked_url_fetch` for the URL import path (used by the frontend E2E tests in step 14).
- `backend/tests/conftest.py` — extended (not replaced) with the `mocked_url_fetch` fixture alongside the tests/CI plan's existing `mocked_openai`. After step 1, the test file's `from api import …` lines still work via the back-compat re-exports; step 6 re-points the new test code to the focused module locations (`api.db.init_db`, `api.routers.recipes`, etc.).
- `frontend/index.html` + `frontend/js/app.js` — reframe home; replace direct POST with modal-driven import flow for both photo and URL.
- `frontend/recipes.html` — add auth header; (optional) simple search input over title.
- `frontend/recipe-data.html` — button group with Edit / Delete / Add to Bring; delete confirm modal.
- `frontend/edit-recipe.html` (new) — edit form.
- `frontend/js/lib/recipe-html.js` (new) — pure helpers extracted from `app.js`; consumed via `window.recipeLib`.
- `frontend/js/utils.js` — no major change; `showBringWidget` stays.
- `frontend/css/styles.css` — minor: import-modal polish, button-group spacing, delete-confirm sizing.
- `frontend/service-worker.js` — bump cache version so the new HTML/JS deploys cleanly to installed PWAs.
- `frontend/package.json` (new) — devDeps + npm scripts (added in step 11).
- `frontend/vitest.config.js` (new) — Vitest + jsdom config (step 11).
- `frontend/playwright.config.js` (new) — Playwright config with the two `webServer` entries (step 11).
- `frontend/.gitignore` (new) — node_modules, coverage, playwright artefacts.
- `frontend/tests/unit/recipe-html.test.js` (new) — Vitest unit tests for the extracted helpers (step 12).
- `frontend/tests/unit/setup.js` (new) — jsdom polyfills used by the helpers (step 11).
- `frontend/tests/e2e/*.spec.js` (new) — Playwright specs listed in step 13.
- `frontend/tests/e2e/mocks/*.html` (new) — saved HTML fixtures used by `import-url.spec.js`.
- `frontend/tests/e2e/fixtures.js` (new) — shared `test.extend({ ... })` that mounts the route mocks and seeds a backend user.
- `README.md` — reframe; add a "Frontend tests" section.
- `.github/workflows/ci.yml` (or whichever file the tests/CI plan lands in) — add a `frontend-test` job. **This is an amendment to the tests/CI plan, called out in the Notes section below.**
- `backend/api/auth.py` (or `backend/api.py` pre-refactor) — `verify_password` body (step 15).
- `backend/tests/test_password.py` — rename + flip one test for the `verify_password` change (step 15).
- `backend/api/auth.py`, `backend/api/db.py`, `backend/api/recipe_extraction.py`, `backend/api/routers/*.py`, `backend/api/main.py`, `backend/api/config.py`, `backend/manage_users.py` — type hints added (step 16).
- `.github/workflows/ci.yml` — tighten `typecheck` job to `continue-on-error: false` (step 16).
- `Makefile` — `typecheck` target verified after the package split (step 16).
- `.pre-commit-config.yaml` — add the `gitleaks` repo block (step 17).
- `.gitleaks.toml` or `.gitleaksignore` (new) — whitelist for known-safe test secrets in `backend/tests/conftest.py` (step 17).
- `frontend/package.json` — add `eslint`, `eslint-plugin-no-unsanitized`, `prettier` to devDeps; add `lint`, `lint:fix`, `format`, `format:check` npm scripts (step 18).
- `frontend/eslint.config.js` (new) — ESLint flat config (step 18).
- `frontend/.prettierrc.json` (new) — Prettier config (step 18).
- `frontend/.prettierignore` (new) — Prettier ignore globs (step 18).
- `.github/workflows/ci.yml` — add a `frontend-lint` job (step 18).
- `Makefile` — extend `make lint` to also run frontend lint (step 18).

## Verification

- `cd backend && source .venv/bin/activate && ruff check . && black --check . && isort --check-only .`
- `cd backend && source .venv/bin/activate && mypy api.py` (the existing strict config; loosen only the spike file).
- `cd backend && source .venv/bin/activate && python -c "import api; print(api.app)"` (import smoke test; after step 1, the package re-exports `app` from `__init__.py`).
- `cd backend && source .venv/bin/activate && python -c "from api.routers import auth, recipes, health"` (package layout import check; only valid after step 1).
- `cd backend && source .venv/bin/activate && pytest -q` (the full suite from both plans, all green; the new tests added in step 6 of this plan must pass alongside the rest).
- `cd frontend && npm install` (one-time; committed `package-lock.json` makes subsequent runs use `npm ci` in CI).
- `cd frontend && npm test` — Vitest unit tests pass; coverage report shows ≥80% lines/functions/statements and ≥70% branches on `js/lib/**`.
- `cd frontend && npx playwright install --with-deps chromium` (one-time locally; CI does this automatically).
- `cd frontend && npm run test:e2e` — all Playwright specs pass; total runtime under 3 minutes on a developer laptop.
- CI: a single push to a PR runs `backend-test` (from the tests/CI plan), `frontend-unit` (this plan), `frontend-e2e` (this plan), and `frontend-lint` (step 18 of this plan) in parallel. All must be green before merge.
- Manual end-to-end, in order:
  1. Log in, see "My Recipes" with no entries.
  2. Import from a photo of a real recipe → preview → "Save to library" → entry appears on home and `/recipes`.
  3. Import from a known-good URL (e.g. an Allrecipes page) → preview → "Save to library" → entry appears.
  4. Import from a personal-blog URL → goes through the OpenAI fallback → preview → save.
  5. Open the detail page → click "Add to Bring" → Bring widget loads with the recipe URL.
  6. Click "Edit" → change a field → save → detail page reflects the change.
  7. Click "Delete" → confirm → entry disappears from the list; `/recipes/{uuid}.json` now 404s.
  8. Log out, log in as a second user → confirm the first user's recipes are **not** visible.

### Step 15 (verify_password wrap)
- `cd backend && source .venv/bin/activate && pytest tests/test_password.py -v` — all password tests pass with the renamed `test_verify_password_non_bcrypt_hash_returns_false`.
- `cd backend && source .venv/bin/activate && ruff check api/ tests/ && black --check api/ tests/ && isort --check-only api/ tests/` — no new drift.

### Step 16 (type hints + tighten CI typecheck)
- `cd backend && source .venv/bin/activate && mypy .` — exits 0 with no errors (the existing strict config now applies to typed code).
- `cd backend && source .venv/bin/activate && pytest -q` — all tests still pass (typing doesn't change runtime).
- After the CI change: a push triggers the `CI / Type-check` job with `continue-on-error: false` and it is green (not "expected to fail" anymore).

### Step 17 (gitleaks)
- `cd backend && source .venv/bin/activate && pre-commit run gitleaks --all-files` — exits 0; either nothing flagged, or the only findings are the whitelisted test secrets.
- Add a deliberate AWS-shaped key to a throwaway file, run the hook, confirm it fires, then delete the file.

### Step 18 (frontend lint)
- `cd frontend && npm install && npm run lint && npm run format:check` — exits 0 on a clean tree.
- `cd frontend && npm run lint:fix && npm run format` — reformats any drift; commit the result separately.
- `cd /workspace && make lint` — runs both backend (ruff/black/isort) and frontend (eslint/prettier) and exits 0.
- CI: the `CI / frontend-lint` job is green on a push.

## Notes / risks

- **Open URL access on the server.** Some sites block non-browser User-Agins; we should ship a realistic `User-Agent` (a recent Chrome on macOS string) and respect a short `Retry-After` if we get 429. This is good-citizen behaviour and avoids getting our IP soft-banned.
- **HTML size and LLM cost.** Cap the HTML body sent to OpenAI (e.g. 30 K chars) to keep token cost predictable; ~95% of recipe HTML is chrome, ads, and JSON that we strip first with `beautifulsoup4`.
- **schema.org/Recipe is rich but messy.** Nested `@graph`, arrays, and image-as-ImageObject all happen. The JSON-LD parser should be defensive (handle missing fields, prefer the first `Recipe` in `@graph`, fall back gracefully).
- **Existing user recipes lack `note` and `source`.** The schema-migration step adds nullable columns; the API should treat null as the empty value everywhere.
- **Public Bring URLs leak UUIDs.** This is already true (`GET /recipes/{uuid}.html` is unauthenticated by design so Bring can fetch the recipe). UUIDs are unguessable enough that this is acceptable, but worth a one-liner in the README.
- **No bundler, on purpose.** The frontend stays as plain script tags served as static files; we deliberately avoid a build step to keep the PWA install and the static-server setup simple. Vitest and Playwright don't need a bundler for plain-JS projects, and the UMD-ish `recipeLib` shim in step 13 is the only concession.
- **Back-compat re-exports in `api/__init__.py` (step 1) are temporary scaffolding.** They exist so the 64 existing tests in the tests/CI plan keep passing while the refactor is in flight, and so `run.py` and the deploy script don't need to change. New code (including the tests added in step 6) imports from the focused modules directly. The re-exports can be removed in a follow-up once nothing imports them — call this out in the `_Done:_` note for step 1.
- **The tests/CI plan's step 4 (extract `_extract_recipe_from_html`) is a no-op after this plan's step 1.** That plan's step 4 says "Refactor `parse_recipe_with_openai` in `backend/api.py`…" — but the function no longer lives there. The equivalent move (HTTP-call wrapper vs. pure HTML extraction) is already done as part of the package split. If both plans execute in order, the executor should mark the tests/CI plan's step 4 as already-completed and link back to step 1 of this plan. No code change needed; just a status update.
- **`@app.on_event("startup")` and `datetime.utcnow()` deprecations** are tracked separately, not in scope for step 1's refactor. Both can be addressed in a small follow-up plan once the package layout is stable.
- **CI coordination with the tests/CI plan.** That plan's stated non-goal is "Frontend tests (potential follow-up plan)." This plan supersedes that — the executor should amend the tests/CI plan's CI workflow to add the two new jobs (`frontend-unit`, `frontend-e2e`) and update the plan's "Non-goals" to drop the frontend-tests line. Out of scope here: changing the backend's existing `backend-test` job.
- **Playwright browser binaries in CI.** Adds ~150 MB to the CI image. Use `mcr.microsoft.com/playwright:v1.47.0-jammy` (or the pinned equivalent for our `@playwright/test` version) as the runner image to avoid a slow `npx playwright install` on every run.
- **E2E test flakiness around OpenAI mocks.** The mocked OpenAI route is hit by the *backend*, not the browser, so the mocks must be installed in the backend process before the E2E suite starts. This is automatic if we put the mock in `conftest.py` and run the backend under the tests/CI plan's `app` fixture — but Playwright's `webServer` starts `uvicorn` as a child process, not under pytest. We solve this by exposing a small environment switch (e.g. `RECIPE_TEST_MOCKS=1`) that `api.py` checks on import to install the same route mocks. The mocks return canned responses, so the backend never reaches the real OpenAI.
- **Open question for the user before execution:** should the URL import also pull the source site's hero image and store it as part of the recipe? (Easy to do; adds storage; the schema.org parser already gives us `image`.) Default plan: store the URL only, don't fetch the image. Confirm during plan-execute.
- **Open question:** do we want a search box on `recipes.html` (client-side filter over the loaded list) for v1, or punt to v2? Plan currently lists it as optional in step 10; executor can include or skip.
- **Open question for the user before execution:** Vitest+Playwright vs. Jest+Cypress. The plan picks Vitest+Playwright (modern defaults, single browser in v1, faster install). If your team has strong Cypress familiarity, the trade is feasible — the spec files would just be rewritten. Confirm at plan-execute time.
- **Steps 15–18 are follow-ups discovered during execution of the tests/CI plan** (`.pi/plans/2026-06-14-add-backend-tests-precommit-ci.md`, status `done`). They were originally listed as "Follow-up plan candidates" in that plan's `## Outcome` section. They've been folded into this plan because the work overlaps with the modules this plan already touches (e.g. `api/auth.py`, `manage_users.py`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`). Executor order note: do these steps **after** step 1 of this plan so the new module paths exist. Steps 15, 16, 17 can be done independently; step 18 is independent of all others.
