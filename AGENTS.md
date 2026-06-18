# AGENTS.md

Guidance for AI coding agents (pi and others) working on the **Recipe to Bring Importer** repository.

## What this repo is

A Progressive Web App that turns a recipe photo into a **Bring!** shopping list:

1. User uploads/captures a photo of a recipe.
2. Backend (`backend/api.py`, FastAPI) sends the image to **OpenAI GPT-4o** and parses out ingredients + recipe metadata.
3. Authenticated user reviews the result and triggers an import to their Bring! shopping list via the Bring API.

**Stack at a glance:**

- **Backend:** FastAPI + SQLite + JWT, Python 3.8+. Entry point: `backend/run.py` → `backend/api.py`.
- **Frontend:** Vanilla JS, Bootstrap 5, PWA (`service-worker.js`, `manifest.json`). No build step — files in `frontend/` are served as-is.
- **Reverse proxy / static serving:** Nginx via `nginx.conf` rendered from `nginx.conf.template` by `start.sh`.
- **External APIs:** OpenAI (vision), Bring! (shopping list).

## Repo map (read these first)

| Path                          | Purpose / when to touch                                                   |
| ----------------------------- | ------------------------------------------------------------------------- |
| `backend/api.py`              | All HTTP routes — recipes, auth, Bring integration, OpenAI call.          |
| `backend/run.py`              | Uvicorn launcher used by `start.sh`.                                      |
| `backend/manage_users.py`     | CLI for the `users` table. Prefer this over editing `users.json`.         |
| `backend/generate_password.py`| Password hashing helper used by `manage_users.py`.                        |
| `backend/pyproject.toml` / `uv.lock` | Python deps. Add libs here, then re-run `uv pip install -e .`.     |
| `frontend/index.html`         | Main app shell (upload + parse + import flow).                            |
| `frontend/login.html`         | Login page.                                                               |
| `frontend/recipes.html` / `recipe-data.html` | Recipe list and detail views.                                |
| `frontend/env-config.html` + `env-config.js` | Legacy client-side config (localStorage). Server-side injection via Nginx is preferred. |
| `frontend/js/`                | App JS modules. Add new behavior here.                                    |
| `frontend/css/`               | Styles.                                                                   |
| `frontend/service-worker.js`  | Bump cache version when shipping frontend changes.                        |
| `frontend/manifest.json`      | PWA manifest.                                                             |
| `nginx.conf.template`         | Template — the nginx container renders it at startup via envsubst.        |
| `docker-compose.yml`          | Orchestrates backend + nginx. `docker compose up -d` to start.           |
| `docker-compose.override.yml` | Dev overrides: live-reload backend with `--reload`.                      |
| `backend/Dockerfile`          | Backend container image (python:3.12-slim + uv).                         |
| `setup-dev.sh` / `setup-env.sh` | One-shot dev environment bootstrap (bare-metal only).                  |
| `.devcontainer/`              | VS Code dev container (Python + Ruff + Black + isort).                    |
| `.env.example`                | Reference env vars. Never commit a real `.env`.                          |

## Environment & setup

Required env vars (loaded by `start.sh` from `.env` at repo root, or exported manually for direct backend runs):

```
OPENAI_API_KEY=...
SECRET_KEY=...                 # JWT signing
USERS_FILE=users.json          # initial users seed
FRONTEND_ROOT=/abs/path/to/frontend
API_URL=http://localhost:8001
FRONTEND_URL=http://localhost
BACKEND_URL=http://localhost:8001
NGINX_PORT=80
BACKEND_PORT=8001
```

Bootstrap (Docker):

```bash
cp .env.example .env           # fill in OPENAI_API_KEY and SECRET_KEY
docker compose up -d           # builds backend image, starts backend + nginx
docker compose logs -f         # tail logs
docker compose down            # stop everything
```

Bare backend (no Docker, rapid iteration):

```bash
cd backend && source .venv/bin/activate && python3 run.py   # http://localhost:8001
cd frontend && python3 -m http.server 8000                  # http://localhost:8000
```

## Build / test / lint commands

There is **no formal test suite in this repo.** When making changes, verify with:

```bash
# Backend syntax / import sanity
cd backend && source .venv/bin/activate && python3 -c "import api"

# Lint / format (matches dev container settings)
cd backend && ruff check .
cd backend && black --check .
cd backend && isort --check-only .

# Smoke test the running API
curl -s http://localhost:8001/health   # or whichever health endpoint exists
```

If you add tests, follow FastAPI's `TestClient` convention and put them under `backend/tests/`.

## Conventions agents must follow

### General

- **Read before editing.** Use the `read` tool on the relevant file(s) before proposing changes. Don't guess at function signatures or route shapes.
- **Match existing style.** Black (line-length default), isort, Ruff — already configured in `.devcontainer/`. Do not introduce new formatters.
- **No new top-level dependencies without justification.** Add to `backend/pyproject.toml` and re-run `uv pip install -e .`.
- **No build step for the frontend.** Do not introduce bundlers, transpilers, or package managers. Plain HTML/CSS/JS only.

### Backend (`backend/`)

- FastAPI routes live in `api.py` — add new endpoints there, keeping auth decorators (`Depends(...)`) consistent with existing handlers.
- Use **Pydantic models** for request/response bodies (match the style already in `api.py`).
- DB access is direct SQLite — preserve that pattern unless the user asks for an ORM migration.
- **Never log or echo `OPENAI_API_KEY`, `SECRET_KEY`, or user passwords.** Redact before printing.
- Errors returned to the client should use `HTTPException` with a meaningful `status_code` and `detail`.
- The OpenAI call streams / parses structured output — when changing the prompt, keep JSON parsing robust (handle partial/malformed responses).
- The Bring integration hits the Bring API with user-scoped credentials — be careful not to cross-contaminate users' lists.

### Frontend (`frontend/`)

- All pages are static HTML. Put page-specific JS in `frontend/js/<page>.js` and load it with a regular `<script>` tag.
- Use **Bootstrap 5 classes** for layout/styling before adding custom CSS.
- When you change any static asset, **bump the cache version** in `service-worker.js` (e.g. `CACHE_NAME = 'recipe-bring-vN'`) so installed PWAs pick up the change.
- The PWA must keep working **offline** for the UI shell — only the `/api/*` calls need network.
- Prefer **server-side env injection** (already wired up in `nginx.conf.template`) over the legacy `env-config.html` / `localStorage` path for new config.

### Configuration / secrets

- `.env`, `users.json`, `recipes.db`, `logs/`, `*.pyc`, `.venv`, and `*.egg-info/` are gitignored. Do not commit them.
- Update `.env.example` when you add a new env var.
- Edit `nginx.conf.template`, **not** `nginx.conf` — the latter is regenerated by `start.sh`.

### Users / auth

- Users are seeded from `users.json` and managed via `./manage_users.py`. Do **not** add self-registration.
- Passwords are hashed via `generate_password.py` — never store plaintext, never log them.

## Common tasks — quick recipes

- **Add a new API endpoint:** edit `backend/api.py`, add a Pydantic model, wire it to a router function with the same auth pattern as neighbors. Smoke-test with `curl`.
- **Add a new frontend page:** create `frontend/<page>.html`, add `frontend/js/<page>.js`, link it from the sidebar in `index.html`. Bump `service-worker.js` cache version.
- **Change the OpenAI prompt:** edit the prompt string in `api.py`, keep JSON-mode / structured-output parsing intact, and test with at least one real recipe image.
- **Change a port or URL:** update `.env.example` and the matching `nginx.conf.template` placeholder. Do not hand-edit the rendered `nginx.conf`.
- **Add a Python dependency:** add to `backend/pyproject.toml` → `uv pip install -e .` → commit `uv.lock`.

## Plans workflow (read this before non-trivial work)

This repo uses **plan files in `.claude/plans/`** as the source of truth for in-flight work.

### When to make a plan

- **Make a plan** for any non-trivial change (multi-step, multi-file, or anything the user might want to review before code is written).
- **Skip the plan** for trivial fixes (one-line typo, single-file obvious bug fix) — but if in doubt, make the plan. The cost of a short plan file is tiny compared to the cost of going the wrong direction.
- **Always** read the active plan (if any) before starting work that touches the same area. Run `ls .claude/plans/` to list plans.

### When executing a plan

- Read the plan file from `.claude/plans/`, confirm with the user, flip `status: draft` → `status: active`, do the work **in step order**, and edit the plan file to check off each step as you finish. The plan file is the progress log — never rely on chat history.
- Update the plan's `updated:` frontmatter field whenever you change the file.
- When all steps are checked: set `status: done` and append an `## Outcome` section.

### Plan status lifecycle

`draft` → `active` → `done`, with `archived` as the off-ramp for plans that get superseded or abandoned. New plans you create start as `draft`. They become `active` only when the user explicitly approves execution (typically via `/plan-execute`).

## Things to watch out for

- The dev container `devcontainer.json` has a hard-coded host path (`/home/michael/bring_importer`) and a host user (`michael`). If you regenerate the container, update those to match the current host or VS Code will fail to mount.
- `nginx.conf.template` is rendered by the nginx container at startup via `envsubst`. If you add a new `${VAR}` placeholder, make sure it is set in the `environment:` block of the `nginx` service in `docker-compose.yml`.
- The `setup-dev.sh` script has a `#!/bin/zsh` shebang — run it with `zsh` if your default shell is bash and you hit odd quoting issues.
- OpenAI model: pinned to GPT-4o for vision. Don't silently downgrade — surface it if cost/availability forces a change.
- The Bring! API is third-party and can change; keep the Bring client code isolated so it's easy to update.

## Out of scope for agents

- Do not modify `recipes.db`, `users.json`, or anything under `logs/` directly — those are runtime artifacts.
- Do not push to remote or create releases/tags unless explicitly asked.
- Do not rewrite the project in a different framework. Match the existing stack.
