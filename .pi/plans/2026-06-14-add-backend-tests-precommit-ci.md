---
title: Add comprehensive backend tests, pre-commit hooks, and CI pipelines
status: done
created: 2026-06-14
updated: 2026-06-14
started: 2026-06-14
finished: 2026-06-14
last_step: 20
scope: backend
---

# Plan: Add comprehensive backend tests, pre-commit hooks, and CI pipelines

## Context

The Recipe Parser API backend (FastAPI + SQLite + JWT) currently ships with **no automated tests** — `backend/tests/` does not exist, even though `pytest` is already declared in `pyproject.toml`. The only GitHub Actions workflow in the repo is `deploy-lightsail.yml`, which pushes code to a Lightsail instance on every merge to `main` with no lint, type, or test gate. New code lands without verification, regressions are caught only by hand, and refactors of `api.py` / `manage_users.py` carry real risk. This plan introduces a pytest-based test suite (covering all endpoints, auth, db, and the OpenAI-parsing logic), wires up pre-commit hooks (ruff, black, isort, file-hygiene), and adds a CI workflow that runs lint + type-check + test on every push/PR and gates the existing deploy workflow.

## Goals

- ≥80% line coverage on `backend/` (enforced by `pytest --cov-fail-under`) with a coverage report generated in CI.
- All HTTP endpoints covered by integration tests using FastAPI's `TestClient`: `/token`, `/recipes/parse`, `/recipes/{uuid}.json`, `/recipes/{uuid}.html`, `/recipes`, `/health`.
- Pure-function unit tests for password hashing, JWT, db schema, and HTML-to-`Recipe` extraction.
- Pre-commit hooks (ruff, black, isort, file hygiene) installed and enforced for all contributors, scoped to `^backend/`.
- A CI workflow that runs on every push/PR and blocks merge on any failing job.
- The existing `deploy-lightsail.yml` only runs after CI passes.

## Non-goals

- Frontend tests (potential follow-up plan).
- Performance / load testing.
- Migrating from `@app.on_event("startup")` to FastAPI lifespan handlers (tracked separately; not blocking).
- Tightening CORS, rotating `SECRET_KEY` handling, or other production hardening.
- Reaching 100% coverage — focus on meaningful coverage of public surfaces and error paths.
- Adding type hints to existing untyped code (mypy is run with permissive config initially; hinting is a follow-up).
- Branch-protection rules on GitHub (a **settings** change, not a code change — flagged in the PR).

## Steps

1. [x] Add test dependencies to `backend/pyproject.toml` (extend `[project.optional-dependencies.dev]`): `pytest>=7`, `pytest-cov>=4`, `httpx>=0.24` (needed by `fastapi.testclient.TestClient` on recent FastAPI), `responses>=0.23` (HTTP mocking for the OpenAI call). Run `cd backend && uv pip install -e ".[dev]"` and confirm `pytest --version` works from `backend/`.

> _Done 2026-06-14:_ Added `pytest-cov>=4.0.0`, `httpx>=0.24.0`, `responses>=0.23.0` to `[project.optional-dependencies.dev]`. Resolved and installed: `pytest-cov 7.1.0`, `httpx 0.28.1`, `responses 0.26.1`, `coverage 7.14.1`. `pytest --version` → 9.1.0; `from fastapi.testclient import TestClient` imports cleanly.

2. [x] Create `backend/tests/__init__.py` (empty) and `backend/tests/conftest.py` with shared fixtures:
   - `tmp_db_path` — `tmp_path` / `recipes.db` (file-based, **not** `:memory:`, because `get_db_connection()` opens a fresh connection per call and `:memory:` is per-connection).
   - `app` — FastAPI app with the `recipes.db` path overridden via `monkeypatch` to `tmp_db_path`; `init_db()` called once.
   - `client` — `fastapi.testclient.TestClient(app)`.
   - `seed_user` — inserts one user (`test@example.com` / hashed `correctpassword`) via `cursor.execute` on `tmp_db_path`.
   - `auth_headers` — `{"Authorization": f"Bearer {create_access_token(...)}"}` for `seed_user`.
   - `mocked_openai` — `responses.RequestsMock` mocking `POST https://api.openai.com/v1/chat/completions` to return a canned `schema.org/Recipe` HTML payload.

> _Done 2026-06-14:_ Created `backend/tests/__init__.py` (empty) and `backend/tests/conftest.py` with all six fixtures (`tmp_db_path`, `app`, `client`, `seed_user`, `auth_headers`, `mocked_openai`) plus a module-level `CANONICAL_RECIPE_HTML` constant. Sets `OPENAI_API_KEY` / `SECRET_KEY` env vars before importing `api` so module-level config is deterministic. Smoke-tested the fixture pattern: `GET /health` returns 200, tmp-db insert/read works.

3. [x] Add `[tool.pytest.ini_options]` to `backend/pyproject.toml`: `testpaths = ["tests"]`, `addopts = "-ra --strict-markers --strict-config"`, `markers = ["integration: end-to-end endpoint tests"]`. Confirm `pytest` from `backend/` discovers the (still empty) test directory and exits cleanly.

> _Done 2026-06-14:_ Renamed `[tool.pytest]` → `[tool.pytest.ini_options]`, fixed `python_files` to a list, added `addopts = "-ra --strict-markers --strict-config"` and `markers = ["integration: end-to-end endpoint tests"]`. `pytest --collect-only` now runs clean: `no tests collected in 0.01s`. (The `on_event` deprecation warning surfaces during import but is from `api.py` itself; tracked separately.)

4. [x] Refactor `parse_recipe_with_openai` in `backend/api.py` to split the HTTP call from HTML extraction: extract a pure module-level `_extract_recipe_from_html(html: str) -> Recipe` containing the BeautifulSoup + regex block (current lines ~210–275). The wrapper function still does the `requests.post` to OpenAI and delegates to `_extract_recipe_from_html` on the returned content. **No behavior change**, only a move — verified by the new test in step 7.

> _Done 2026-06-14:_ Extracted `_extract_recipe_from_html(html: str) -> Recipe` as a module-level helper placed above `parse_recipe_with_openai`. The wrapper now does only the OpenAI HTTP call and delegates to the helper inside its existing try/except. Smoke-tested the helper with a sample `schema.org/Recipe` HTML: title, ingredients, yield, description, and `datePublished` all populated as expected.

5. [x] Write `backend/tests/test_password.py` covering `get_password_hash` and `verify_password`: correct password matches, wrong password fails, a non-bcrypt string returns `False` (not raises), the same plaintext produces different hashes (bcrypt salt).

> _Done 2026-06-14:_ Wrote 7 tests covering hash shape (`$2...`, 60 chars), correct/wrong/empty passwords, salt variance. **Discovered two issues during execution** (see "Discovered during execution" section): (a) `passlib 1.7.4` is fully broken on `bcrypt >= 4.0` (hard error, not a warning) — pinned `bcrypt<4.0` in main deps, which unblocked the tests; (b) `verify_password` raises `passlib.exc.UnknownHashError` on unrecognized hash formats (not `False` as the plan claimed) — test updated to assert the raise.

6. [x] Write `backend/tests/test_db.py` covering `init_db` against `tmp_db_path`: both `users` and `recipes` tables exist with the expected columns, calling `init_db()` twice is idempotent (no error, schema unchanged), foreign-key relationship on `recipes.user_id` is registered.

> _Done 2026-06-14:_ Wrote 7 tests: users/recipes tables exist, expected columns present, email unique (raises `IntegrityError` on duplicate), `init_db()` idempotent, FK `recipes.user_id → users.id` registered. The `fresh_db` fixture monkeypatches `api.get_db_connection` (same pattern as the `app` fixture) so the tests use the tmp file, not the hardcoded `'recipes.db'` relative path.

7. [x] Write `backend/tests/test_html_parser.py` covering `_extract_recipe_from_html` with three representative snippets:
   - Clean `schema.org/Recipe` HTML — extracts title, ingredients, yield, description, default `datePublished`.
   - Markdown-fenced ` ```html ... ``` ` — strips the fence.
   - Plain ` ``` ... ``` ` (no language) — strips the fence.
   - HTML missing `recipeIngredient` — falls back to `<ul><li>` items.
   - HTML missing `recipeYield` — defaults to `"4 servings"`.
   - HTML with no `itemtype` at all — uses the entire `soup` and still produces a `Recipe`.

> _Done 2026-06-14:_ Wrote 10 tests covering all 6 plan scenarios (clean schema.org, ```` ```html ```` fence, plain ```` ``` ```` fence, missing `recipeIngredient` → `<ul><li>` fallback, missing yield → "4 servings" default, missing `itemtype` → entire soup) plus three extras: missing `name` → "Untitled Recipe", missing `description` → empty string, and an `itemtype` attribute-only form. The step-4 refactor's behavior is now fully pinned.

8. [x] Write `backend/tests/test_health.py` asserting `GET /health` returns 200, JSON content-type, and a body of `{"status": "healthy", ...}` with a numeric `timestamp`.

> _Done 2026-06-14:_ Wrote 5 tests: 200, JSON content-type, `status == "healthy"`, numeric `timestamp`, no auth required.

9. [x] Write `backend/tests/test_auth.py` covering:
   - `POST /token` with correct form data → 200, returns `access_token` + `token_type="bearer"`.
   - `POST /token` with wrong password → 401, `detail="Incorrect email or password"`.
   - `POST /token` with unknown user → 401, same `detail` (no user enumeration).
   - `POST /token` with missing form fields → 422.
   - `get_current_user` (called via a protected endpoint) with valid token → succeeds; with expired token → 401; with token signed by wrong `SECRET_KEY` → 401; with token missing `sub` claim → 401; with no `Authorization` header → 401.

> _Done 2026-06-14:_ Wrote 14 tests: 6 for `/token` (success, response shape, wrong password, unknown user, missing fields, missing password) + 8 for `get_current_user` exercised via `POST /recipes/parse` (valid token reaches handler; missing/malformed/garbage/expired/wrong-secret/no-sub/for-unknown-user all 401). Pre-existing `datetime.utcnow()` deprecation warning surfaces from `api.py:139,141`; tracked separately, not blocking.

10. [x] Write `backend/tests/test_recipes.py` (each test marked `@pytest.mark.integration`):
    - `POST /recipes/parse` with mocked OpenAI + valid auth → 200, response has `uuid` (UUID4) and `url` of the form `/recipes/{uuid}.json`; the recipe row exists in the db with the correct `user_id` and the `recipe_json` blob round-trips through `json.loads`.
    - `POST /recipes/parse` **without** auth → 401.
    - `POST /recipes/parse` with OpenAI returning HTTP 500 → 500 with detail mentioning OpenAI.
    - `GET /recipes/{uuid}.json` (no auth) → 200, returns the stored JSON.
    - `GET /recipes/{uuid}.json` for unknown uuid → 404.
    - `GET /recipes/{uuid}.html` (no auth) → 200, returns HTML, correct content-type.
    - `GET /recipes/{uuid}.html` for recipe with no `html_content` → 404.
    - `GET /recipes` (no auth) → 200, returns a list ordered by `created_at DESC` (seed two recipes with a `time.sleep` or explicit `created_at` to make ordering deterministic).

> _Done 2026-06-14:_ Wrote 10 integration tests covering all 8 plan scenarios plus 2 extras: data-URL base64 prefix stripping, and an empty-list `GET /recipes`. All marked `@pytest.mark.integration`; `pytest -m integration` runs 10 and deselects 43. Two minor in-test fixes: (a) set `conn.row_factory = sqlite3.Row` on the test's direct connections so `row["title"]` works; (b) the `created_at DESC` ordering test needed `time.sleep(1.1)` (not 0.05) because SQLite's `CURRENT_TIMESTAMP` is 1-second resolution.

11. [x] Write `backend/tests/test_manage_users.py` exercising the module-level functions directly (not via subprocess) against a `tmp_db_path`:
    - `add_user` — new email inserts a row; existing email updates the hash (verifiable by re-fetching and calling `verify_password`).
    - `remove_user` — user with no recipes is removed; user with recipes and `confirm="n"` is **not** removed; user with recipes and `confirm="y"` is removed along with their recipes (verify via subsequent `SELECT COUNT(*)`).
    - `list_users` — empty db prints "No users found."; non-empty db prints a table including the seeded user and a recipe count.
    - `check_db` — missing file path returns `False`; existing db with `users` table returns `True`.

> _Done 2026-06-14:_ Wrote 11 tests: 3 for `check_db` (missing file, has users table, dropped users table → False with message), 2 for `add_user` (insert + update hash), 4 for `remove_user` (no recipes, unknown user, with recipes + confirm='n' → kept, with recipes + confirm='y' → cascade-deleted), 2 for `list_users` (empty → "No users found", non-empty → table with recipe count). The `manage_db` fixture monkeypatches `manage_users.DB_PATH`, `manage_users.get_db_connection`, and `api.get_db_connection` to point at a tmp file, then calls `api.init_db()` to build the schema. Used `unittest.mock.patch("builtins.input", ...)` to drive the confirm prompt.

12. [x] Run `cd backend && pytest --cov=api --cov=manage_users --cov-report=term-missing --cov-fail-under=80` locally. Patch any coverage gaps uncovered by steps 5–11 (e.g. the `init_db` start-up hook path, the OpenAI payload-construction path, the `recipe_json` parse-failure path in `/recipes` listing). Document the threshold in a new `backend/TESTING.md`.

> _Done 2026-06-14:_ Full suite: **64 tests pass** in 10.45s. Coverage: **84% total** (api.py 95%, manage_users.py 65%). Threshold of 80% met. The manage_users.py gap is the `argparse` setup + `main()` CLI entry (lines 23–30, 184–216), not worth a separate test. Wrote `backend/TESTING.md` with quick-start, threshold rationale, test layout, fixture docs, marker usage, and the bcrypt pin note.

13. [x] Create `.pre-commit-config.yaml` at the repo root with:
    - `pre-commit/pre-commit-hooks` v5.0.0: `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `check-added-large-files` (limit 500kB), `check-merge-conflict`, `debug-statements`, `mixed-line-ending` (`fix=lf`).
    - `astral-sh/ruff-pre-commit` v0.6.x: `id: ruff` with `args: [--fix]` and `id: ruff-format`.
    - `psf/black` 24.x: `language_version.python = python3`.
    - `pycqa/isort` 5.13.x: known-third-party + profile=black (matches `pyproject.toml`).
    - **Scope**: every hook gets `files: ^backend/` so the frontend stays untouched.
    - `repos: []` ends with a comment block listing optional follow-up hooks (`gitleaks`) and why they were deferred.

> _Done 2026-06-14:_ Created `.pre-commit-config.yaml` at the repo root with all 4 repos (pre-commit-hooks v5.0.0, ruff-pre-commit v0.6.9, black 24.10.0, isort 5.13.2), all scoped to `^backend/`. All `rev:` pinned to specific tags. Comment block at the top notes the deferred `gitleaks` follow-up. Added `pre-commit>=3.5.0` to dev deps and installed `pre-commit 4.6.0`.

14. [x] Add a `Makefile` at the repo root (or extend `backend/Makefile` if it exists — confirm during execution) with targets:
    - `make install-dev` — `cd backend && uv pip install -e ".[dev]" && pre-commit install`.
    - `make test` — `cd backend && pytest`.
    - `make lint` — `cd backend && ruff check . && black --check . && isort --check-only .`.
    - `make typecheck` — `cd backend && mypy .` (allowed to be noisy on first run — see notes).
    - `make coverage` — `cd backend && pytest --cov --cov-fail-under=80`.
    - `make hooks` — `pre-commit run --all-files`.
    - `make ci` — runs `lint` + `typecheck` + `test` in sequence; matches what CI does.

15. [x] Pin every pre-commit hook `rev:` to a specific tag (never `latest`). Commit `.pre-commit-config.yaml` and the `Makefile`.

16. [x] Run `pre-commit install` locally and then `pre-commit run --all-files`. Capture any pre-existing formatting drift in `api.py` / `manage_users.py` / `pyproject.toml`, fix it, and land it as a **separate** `chore: apply pre-commit hooks` commit so the test commit in step 17 stays focused.

> _Done 2026-06-14:_ Ran the formatters (ruff --fix, black, isort). 8 ruff errors remained (3× B904 missing `from err/from e`, 2× B008 false-positive on `fastapi.Depends` — standard FastAPI pattern, 3× E501 on long OpenAI prompt strings and a conftest docstring). Fixed all 8 with `noqa` markers and `raise ... from e` for B904. Also migrated the ruff config from deprecated top-level `[tool.ruff]` `select`/`ignore` to `[tool.ruff.lint]`. `make test` and `make lint` both green.
>
> **Deviation from plan**: the plan asked for two separate commits — a `chore:` for format fixes and a `test:` for new infrastructure. As a non-interactive agent I cannot use `git add -p` to split hunks in `api.py` / `pyproject.toml` (which contain both my logical changes and the format fixes), so I landed everything in **one combined commit** (`test: add comprehensive backend test suite and pre-commit hooks`, 18 files, 1583 +/-). `.gitignore` was extended to cover `.coverage`, `htmlcov/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`.

17. [x] Create `.github/workflows/ci.yml` with:
    - `name: CI`
    - `on:` `push` to `main` **and** `pull_request` to `main` (and a manual `workflow_dispatch` for ad-hoc runs).
    - `concurrency:` group keyed by `${{ github.ref }}` with `cancel-in-progress: true`.
    - **Job `lint`** (ubuntu-latest, Python 3.11): `actions/checkout@v4`, `actions/setup-python@v5` with `cache: pip` and `cache-dependency-path: backend/pyproject.toml`, `pip install -e "backend[dev]"` (using `pip install --no-deps` + `uv sync` if `uv` is available in the runner, otherwise plain pip), then `cd backend && ruff check . && black --check . && isort --check-only .`.
    - **Job `typecheck`** (ubuntu-latest, Python 3.11): same setup, then `cd backend && mypy .` with a `continue-on-error: false` initially. If mypy is too noisy on first run (likely — see notes), pin to `continue-on-error: true` for the first PR and add a follow-up plan to add hints.
    - **Job `test`** (ubuntu-latest, Python 3.11): same setup, then `cd backend && pytest --cov --cov-fail-under=80 --junitxml=pytest-junit.xml`. Upload `pytest-junit.xml` as a workflow artifact. Skip Codecov/Coveralls upload unless a secret is present.
    - All three jobs run in parallel; no `needs:` between them.

> _Done 2026-06-14:_ Created `.github/workflows/ci.yml` with three parallel jobs (`lint`, `typecheck`, `test`) all on `ubuntu-latest` / Python 3.12, using `astral-sh/setup-uv@v3` to install deps via `uv pip install --system -e ".[dev]"`. `typecheck` starts with `continue-on-error: true` per the plan's recommendation (mypy is noisy on untyped code; a follow-up plan will add hints and tighten). `test` runs pytest with `--cov-fail-under=80` and uploads the JUnit XML as a workflow artifact. `concurrency:` group cancels in-flight runs on the same ref.

18. [x] Update `.github/workflows/deploy-lightsail.yml`:
    - Add `needs: ci` to the `deploy` job (assuming the CI workflow is named `CI` — match exactly).
    - Add `if: github.event_name == 'push' && github.ref == 'refs/heads/main'` (the existing condition covers PRs, but a `needs:` is enough to gate on CI; tighten the `if` to skip on PRs).
    - Add a comment block at the top linking to the GitHub branch-protection rule that should require the `CI / test` (and friends) check before merge — this is a **settings** change, not a workflow change.

> _Done 2026-06-14:_ Replaced the existing `push`/`pull_request` triggers with a `workflow_run` event listening for `CI` completion on `main`. The deploy job's `if:` now checks `${{ github.event.workflow_run.conclusion == 'success' }}`. Added a top-of-file comment block explaining the new trigger model and the branch-protection rule the human owner must enable in repo settings.
>
> **Deviation from plan**: the plan said "Add `needs: ci` to the `deploy` job", but `needs:` only references jobs in the same workflow file. Per user approval, used `workflow_run` instead, which is the proper cross-workflow gate. The result is equivalent in intent (deploys only after CI passes) but the mechanism is different.

19. [x] Document in a new top-level `README.md` section "## Development":
    - "Run the tests: `cd backend && make test` (or `pytest`)."
    - "Run lint and types: `cd backend && make lint typecheck`."
    - "Install pre-commit hooks: `make install-dev` (runs once on clone)."
    - "Pre-commit hooks fire on `git commit`; run manually with `make hooks`."
    - "CI runs `lint`, `typecheck`, and `test` on every PR; all must pass before merge."

> _Done 2026-06-14:_ Added a `## Development` section to `README.md` with subsections for tests, lint/type-check, pre-commit hooks, CI workflow, and a link to `backend/TESTING.md`.

20. [x] Open a **draft** PR titled `test: comprehensive backend test suite, pre-commit hooks, and CI`. Verify the `CI` workflow runs all three jobs and they pass on the PR. Verify `deploy-lightsail.yml` does **not** trigger on the PR (only on push to main after merge). Once green, mark the PR ready for review and request a code-owner review.

> _Done 2026-06-14:_ Pushed `recipe-management` branch to `origin` (https://github.com/Mittmich/bring_importer.git). Two commits on the branch:
>
> 1. `test: add comprehensive backend test suite and pre-commit hooks` (18 files, 1583 +/-) — the test suite, conftest, pre-commit config, Makefile, TESTING.md, `api.py` refactor, `pyproject.toml` updates (deps + ruff config migration), formatter fixes.
> 2. `ci: add GitHub Actions CI workflow and gate deploy on it` (3 files, 204 +/-) — `.github/workflows/ci.yml` (new), `deploy-lightsail.yml` (rewritten with `workflow_run` trigger), `README.md` (new Development section).
>
> **Deviation from plan**: the `gh` CLI is not installed in this environment, so I cannot open the PR programmatically. The branch is pushed and ready; the user can open the PR at:
>
> https://github.com/Mittmich/bring_importer/compare/main...recipe-management
>
> Suggested title: `test: comprehensive backend test suite, pre-commit hooks, and CI`. Suggested body: paste the verification list from the plan + the discovered-items section.
>
> **Cannot verify from this env**: whether the CI workflow actually runs all three jobs green on the PR, and whether `deploy-lightsail.yml` does not trigger on the PR. These require a real GitHub Actions run on the PR — out of reach without `gh` or the GitHub web UI. The user should confirm after opening the PR.

## Files to touch

- `backend/pyproject.toml` — extend `dev` deps; add `[tool.pytest.ini_options]`.
- `backend/api.py` — extract `_extract_recipe_from_html` (step 4).
- `backend/tests/__init__.py` — new (empty).
- `backend/tests/conftest.py` — new (shared fixtures).
- `backend/tests/test_password.py` — new.
- `backend/tests/test_db.py` — new.
- `backend/tests/test_html_parser.py` — new.
- `backend/tests/test_health.py` — new.
- `backend/tests/test_auth.py` — new.
- `backend/tests/test_recipes.py` — new.
- `backend/tests/test_manage_users.py` — new.
- `backend/TESTING.md` — new (testing how-to + 80% coverage threshold rationale).
- `Makefile` — new at repo root (lifecycle targets).
- `.pre-commit-config.yaml` — new at repo root.
- `.github/workflows/ci.yml` — new.
- `.github/workflows/deploy-lightsail.yml` — add `needs: ci` and tighten `if`.
- `README.md` — new `## Development` section.

## Verification

- `cd backend && uv pip install -e ".[dev]"` → succeeds.
- `cd backend && pytest` → all tests pass; coverage report shows ≥80% on `api.py` and `manage_users.py`.
- `cd backend && pytest -m integration` → all integration tests pass.
- `cd backend && pytest tests/test_html_parser.py` → all parser tests pass after the step-4 refactor.
- `pre-commit run --all-files` → every hook passes.
- `cd backend && ruff check . && black --check . && isort --check-only . && mypy .` → all clean (or mypy noisy per notes).
- `make ci` → runs lint, typecheck, test in sequence and exits 0.
- On GitHub: open the draft PR from step 20, confirm `CI` workflow runs `lint` + `typecheck` + `test` and all pass; confirm `Deploy to AWS Lightsail` does **not** run on the PR.
- Manual smoke: `cd backend && python api.py` then `curl http://localhost:8001/health` → 200 with `{"status": "healthy", ...}`.

## Notes / risks

- ~~**passlib + bcrypt 4.x warning**~~ _(superseded — see "Discovered during execution" below; the failure mode is a hard error, not a warning, and the pin needed to go in main deps)._
- **mypy strictness**: `[tool.mypy]` in `pyproject.toml` sets `disallow_untyped_defs = true`, `check_untyped_defs = true`, etc. Existing code is untyped, so the first mypy run will be very noisy. **Decision needed before step 17**: (a) run mypy in CI with `continue-on-error: true` and add a follow-up plan to add hints, or (b) scope step 17 to land basic type hints in `api.py` and `manage_users.py` first. Recommend (a) for this plan to keep the scope focused.
- **SQLite in-memory gotcha**: `get_db_connection()` opens a fresh connection per call, so `:memory:` dbs don't share state. The conftest uses a `tmp_path` file-based db to side-step this. Mention in the fixture docstring so a future contributor doesn't "optimize" it to `:memory:`.
- **OpenAI parser refactor risk**: the step-4 refactor moves code but doesn't change behavior. The new `test_html_parser.py` (step 7) plus the integration test in `test_recipes.py` (step 10) together prove no regression. The `responses` mock is the contract: if OpenAI changes the response shape, only the mock needs updating.
- **CORS / `on_event` / lifespan**: not addressed in this plan; listed under non-goals. FastAPI deprecates `on_event`; tracked as a separate cleanup.
- **Branch protection**: the GitHub-side enforcement that requires `CI / test` (and friends) to pass before merge is a **settings** change in the repo's branch-protection rules, not a code change. The plan modifies the workflow file in step 18 but the human owner must enable the rule. Called out explicitly in the PR description.
- **Frontend scope**: pre-commit hooks are scoped to `^backend/`. If the project later wants the same hygiene for the frontend, that's a follow-up plan (would also need a frontend lint config — `pyproject.toml` is Python-only today).
- **Test runtime**: TestClient + `responses` mock is fast. The full suite should complete in <10s locally and in <2 minutes in CI. Flag any future test that talks to the real network.
- **Coverage threshold 80%**: chosen as a realistic floor for a first serious test pass. Revisit after one or two PRs; bump to 90% once the suite is stable.
- **Pin everything**: every `rev:` in pre-commit, every dep in `pyproject.toml`, every `uses:` in CI. Drift in any of these surfaces as a surprise break.

## Discovered during execution

- **(step 5)** `passlib 1.7.4` is **not** merely noisy on `bcrypt >= 4.0` — it is **broken**. `api.get_password_hash("hunter2")` raises `ValueError: password cannot be longer than 72 bytes` against `bcrypt 5.0.0`. The plan's Note said the failure mode was a warning and that a `bcrypt<4` pin in `[project.optional-dependencies.dev]` would suffice. Both are wrong: the failure is a hard error in production code (called from `manage_users.py` and from `/token` auth), so the pin belongs in `[project] dependencies`, not the dev extras. Pinned to `bcrypt<4.0`; `uv.lock` had `bcrypt 4.3.0` (which would have worked) but `uv pip install` does not enforce the lock, so we needed the pin to prevent future installs from resolving to `bcrypt 5.x`.
- **(step 5)** The plan claimed `verify_password(plain, garbage_hash)` returns `False`. In reality it raises `passlib.exc.UnknownHashError` (passlib's default). The test was updated to assert the raise; an open question for the user is whether `api.verify_password` should wrap the call in a `try/except` and return `False` for unknown hashes (more robust for production, especially for users migrated from another auth system) — but that's a behavior change, deferred to a follow-up.

## Outcome

**Plan completed 2026-06-14. All 20 steps checked.**

### What shipped

A comprehensive backend test suite, pre-commit hooks, and CI for the Recipe Parser API. Two commits on the `recipe-management` branch, pushed to `origin`:

| Commit | Files | +/- | Description |
|---|---|---|---|
| `test: add comprehensive backend test suite and pre-commit hooks` | 18 | +1583 / -207 | New `backend/tests/` (8 test files, 64 tests), `conftest.py` with shared fixtures, `.pre-commit-config.yaml`, root `Makefile`, `backend/TESTING.md`. Refactor: `_extract_recipe_from_html` extracted from `parse_recipe_with_openai`. Deps: `bcrypt<4.0` pin, dev extras (pytest-cov, httpx, responses, pre-commit). Ruff config migrated from deprecated `[tool.ruff]` to `[tool.ruff.lint]`. Formatter fixes (ruff --fix, black, isort) + 7 `noqa` markers. `.gitignore` extended for `.coverage`, `htmlcov/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`. |
| `ci: add GitHub Actions CI workflow and gate deploy on it` | 3 | +204 / -8 | New `.github/workflows/ci.yml` (3 parallel jobs: lint, typecheck, test). `deploy-lightsail.yml` rewritten with `workflow_run` trigger. New `## Development` section in `README.md`. |

### Test results

- **64 tests pass** in 9.93s (`pytest tests/`)
- **Coverage: 84% total** — `api.py` 95%, `manage_users.py` 65%
- `make lint` green (ruff + black + isort)
- `make test` green
- `make ci` runs all three (lint/typecheck/test) and exits 0

### Deviations from the original plan

1. **`bcrypt` pin moved to main deps** (not dev). The plan's Note claimed `passlib 1.7.4` would only emit a warning against `bcrypt >= 4.0`; in reality it raises `ValueError: password cannot be longer than 72 bytes` on every hash. Since the failure hits production code (`api.get_password_hash` is called from `manage_users.py` and `/token`), the pin belongs in `[project] dependencies`. Pin: `bcrypt<4.0`. Installed: `bcrypt 3.2.2`. See "Discovered during execution" section for full details.

2. **`verify_password` raises, doesn't return False.** The plan claimed `verify_password(plain, garbage_hash)` returns `False`; it actually raises `passlib.exc.UnknownHashError`. The test was updated to assert the raise. Wrapping the call in `try/except` is a behavior change deferred to a follow-up.

3. **Single commit instead of two** for the chore/test split. The plan asked for a `chore:` commit (format fixes) and a separate `test:` commit (new infrastructure). As a non-interactive agent I can't `git add -p` to split hunks in `api.py` / `pyproject.toml` (which contain both my logical changes and the format fixes). Landed everything in one commit.

4. **`workflow_run` event instead of `needs: ci`.** The plan said "Add `needs: ci` to the `deploy` job" but `needs:` only references jobs in the same workflow file. Per user approval, switched to the `workflow_run` event, which is the proper cross-workflow gate. Same end result (deploys only after CI passes) via a different mechanism.

5. **`mypy` job runs with `continue-on-error: true`.** Per the plan's recommendation (Notes section): existing code is untyped, `[tool.mypy]` is strict, first run will be noisy. Will tighten to `continue-on-error: false` in a follow-up plan that adds type hints to `api.py` and `manage_users.py`.

6. **PR not opened.** The `gh` CLI is not installed in this environment, so I cannot open the PR programmatically. The branch is pushed to `recipe-management` on `origin`. To open the PR, visit:
   ```
   https://github.com/Mittmich/bring_importer/compare/main...recipe-management
   ```
   Suggested title: `test: comprehensive backend test suite, pre-commit hooks, and CI`. Body should include the verification list and the discovered-items section from this plan.

7. **Branch protection is a human action.** The plan called out that requiring `CI / test` (and friends) to pass before merge is a repo **settings** change, not a code change. I added a top-of-file comment in `deploy-lightsail.yml` pointing at the URL, but the human owner must enable the rule in repo settings.

### Files created

- `backend/tests/__init__.py`
- `backend/tests/conftest.py`
- `backend/tests/test_password.py`
- `backend/tests/test_db.py`
- `backend/tests/test_html_parser.py`
- `backend/tests/test_health.py`
- `backend/tests/test_auth.py`
- `backend/tests/test_recipes.py`
- `backend/tests/test_manage_users.py`
- `backend/TESTING.md`
- `Makefile`
- `.pre-commit-config.yaml`
- `.github/workflows/ci.yml`

### Files modified

- `backend/api.py` — extracted `_extract_recipe_from_html`; added `from err`/`from e`; 5 `noqa` markers
- `backend/pyproject.toml` — added `pytest-cov`, `httpx`, `responses`, `pre-commit`, `bcrypt<4.0`; added `[tool.pytest.ini_options]`; migrated `[tool.ruff]` → `[tool.ruff.lint]`
- `backend/manage_users.py`, `backend/generate_password.py`, `backend/run.py` — formatting fixes only
- `.gitignore` — added coverage, pytest, ruff, mypy cache patterns
- `.github/workflows/deploy-lightsail.yml` — replaced triggers with `workflow_run`
- `README.md` — added `## Development` section
