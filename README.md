# Zestry

A recipe app that turns photos, web pages or hand-written recipes into a shared collection and a Bring! shopping list.

This is a Progressive Web App (PWA) and a small **recipe library**: log in, import recipes (from a photo or a webpage URL), and your personal library becomes the home surface. Each recipe can be edited, deleted, or sent to your Bring shopping list.

## Features

- **Recipe library** — a personal list of your saved recipes, scoped to your account.
- **Import from photo** — take a photo of a recipe (or upload one) and OpenAI's Vision API extracts the structured recipe.
- **Import from URL** — paste a recipe-page URL; the server first tries the page's `schema.org/Recipe` JSON-LD block (no LLM cost), then falls back to OpenAI text extraction if the page has no JSON-LD.
- **Edit & delete** — update a recipe's title, yield, description, ingredients, and your private note; delete with a confirmation.
- **Add to Bring** — a per-recipe action on the detail page that hands the recipe to the Bring widget.
- **Languages (English / Deutsch)** — the UI is fully translated (pick a language under Account, or on the login screen). Imports are written in your language (photo/HTML extraction writes it directly; JSON-LD imports keep the page's original text and store a translation alongside). Recipes are shown in your language when a version in it exists; otherwise the edit screen offers **Translate with AI**. See `backend/api/i18n.py` and `frontend-react/src/i18n/`.
- **Add recipes three ways** — "Add recipe" offers *From a photo*, *From a website* or *Write it yourself*. Writing it yourself opens the editor on an unsaved draft (`/recipes/new`); the first Save creates it (`POST /recipes`, which also accepts ingredients one per line via `ingredients_text`, split by `backend/api/ingredient_lines.py`).
- **Duplicate** — the recipe's "⋯" menu (with PDF export, sharing, public link and delete) can duplicate a recipe: your own become "… (copy)" with photo, note and tags; recipes shared with you or public ones become your own copy. `POST /recipes/{uuid}/clone`.
- **Gradient covers** — recipes without a photo get a warm gradient (stable per recipe) in lists, cards and the recipe view.
- **PDF export** — "Export PDF" in each recipe's "⋯" menu (and a PDF button on public share pages) produces a printable A4 PDF with the photo, servings-scaled ingredients, numbered steps and note, in your language. On phones it opens the share sheet (save to Files, print, send); on desktop it downloads. Rendered server-side by `GET /recipes/{uuid}.pdf` (`backend/api/recipe_pdf.py`, fpdf2 + a subset of DejaVu Sans).
- **Admin control plane** — admins get *Account → Admin*: all users with usage stats (recipes, sign-up date, last login, who invited them), one-time **sign-up links** (optionally locked to an email, 1–30 days), one-time **password-reset links** (24 h), disabling/enabling accounts, *log out everywhere*, promoting admins and deleting users with all their data. Links are shown once and stored only as a hash; the app sends no email, so you pass links on yourself. See [Users & admins](#users--admins).
- **Works Offline** — install as a PWA for offline access.
- **Secure** — your OpenAI API key stays server-side; you authenticate to the backend with a JWT.

## How to Use

1. Log in at `/login` with the account an admin created for you (via a sign-up link, or `manage_users.py`).
2. The home page (`index.html`) is your recipe library: shows recent recipes with a "See all" link, plus two import actions.
3. **Import from photo**: choose / take a photo → preview the parsed recipe → "Save to library" or "Add to Bring".
4. **Import from URL**: paste a recipe page URL (and an optional note) → preview → "Save to library" or "Add to Bring".
5. Open a recipe to see its detail page with **Add to Bring**, **Edit**, **Delete**, **View HTML Source**, and **Open Raw HTML** actions.
6. The "Add to Bring" widget on the detail page takes the recipe URL and hands it to Bring.

### Privacy & external requests

- Imported URLs are **fetched server-side** by the backend (10 s timeout, 5 MB cap, real browser User-Agent).
- When the page exposes `schema.org/Recipe` JSON-LD, **no LLM call is made** for the URL import — only the structured data is used.
- When JSON-LD is missing, the cleaned page body is sent to **OpenAI** (gpt-4o-mini) for text extraction. The OpenAI request includes the source URL; no extra metadata is shared.
- Recipe **translation** (on JSON-LD import into another language, or "Translate with AI" in the editor) sends the recipe's title, description, yield, ingredients and steps to the configured translation provider (`TRANSLATION_PROVIDER`, default OpenAI).
- Photo imports always call OpenAI's vision model; the image is resized to ≤1200×1200 JPEG at quality 0.85 before upload.

## Users & admins

- **Becoming the first admin:** run the *Grant admin* workflow (Actions → Grant admin → your email). It calls
  `manage_users.py admin <email>` in the backend container. After that, promote further admins in the app.
  Nobody can demote, disable or delete themselves, and the last admin can't be demoted.
- **New users** sign up through an admin's sign-up link (`/signup/<token>`); there is no open registration.
  The *Add user* workflow (shared default password) still works as a fallback.
- **Forgotten passwords:** an admin creates a reset link (`/reset/<token>`, 24 h, single use) and sends it.
  Using it sets the new password and logs the user out on every other device.
- **Sessions are revocable:** every login token carries the user's `token_version`; disabling, a password
  reset or *Log out everywhere* bumps it, which invalidates all earlier tokens immediately.
- Locally: `cd backend && uv run python manage_users.py admin you@example.com [--revoke]`.

## Setup & Installation

### Backend (FastAPI)

The backend server uses FastAPI and requires Python 3.8 or later.

#### Using uv (Recommended)

[uv](https://github.com/astral-sh/uv) is a fast Python package installer and virtual environment manager.

1. Install uv if you don't have it yet:
   ```bash
   pip install uv
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -r requirements.txt
   # Or using pyproject.toml
   uv pip install -e .
   ```

3. Create a `.env` file with your OpenAI API key and a secret key:
   ```
   OPENAI_API_KEY=your_openai_api_key
   SECRET_KEY=a_random_secret_key_for_jwt_tokens
   USERS_FILE=users.json
   ```
   
   The application will use the `users.json` file to initialize users on startup.

4. Start the server:
   ```bash
   python api.py
   ```
   The API will be available at http://localhost:8001

#### Using pip

If you prefer using pip:

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Follow steps 3-4 from the uv setup above.

### Frontend

After setting up the backend, you need to serve the frontend files.

```bash
# Using any local server, e.g. with Python:
python -m http.server 8000
```

Then navigate to http://localhost:8000 in your browser.

### Running with Docker Compose (recommended)

Docker Compose builds the backend image and starts both the FastAPI backend and an Nginx reverse proxy with a single command. No host-level Python, nginx, or uv installation needed.

1. Copy `.env.example` to `.env` and fill in the required values:
   ```bash
   cp .env.example .env
   # edit .env — set OPENAI_API_KEY and SECRET_KEY at minimum
   ```

2. Start the stack:
   ```bash
   docker compose up -d
   ```
   The frontend is served at http://localhost (or `http://localhost:$NGINX_PORT`).

3. Tail logs:
   ```bash
   docker compose logs -f
   ```

4. Stop:
   ```bash
   docker compose down
   ```

### Requirements

- Python 3.8 or higher for the backend
- An OpenAI API key with access to the GPT-4o model
- A modern web browser (Chrome, Firefox, Safari, Edge)

## Tech Stack

- **Frontend**: HTML5, CSS3, JavaScript, Bootstrap 5
- **Backend**: FastAPI, SQLite, JWT authentication
- **APIs**: OpenAI GPT-4o for image processing, Bring API for shopping list integration
- **PWA Features**: Service Worker API for offline capabilities

## Privacy Notice

This app stores user credentials and parsed recipes in a SQLite database on the server. Users are initialized from the `users.json` file (no self-registration). Your OpenAI API key is stored only on the server and used for processing images. User authentication is handled with secure JWT tokens.

### Managing Users

Users can be managed directly in the database using the `manage_users.py` script:

```bash
# List all users
./manage_users.py list

# Add a new user (will prompt for password)
./manage_users.py add user@example.com

# Add a new user with password specified in command line
./manage_users.py add user@example.com --password securepassword

# Remove a user (will prompt for confirmation if user has recipes)
./manage_users.py remove user@example.com
```

This is more convenient than editing the `users.json` file directly.

### Environment Configuration

The app now supports two ways to configure environment variables:

#### 1. Server-Side Environment Configuration (Recommended)

The application uses environment variables for configuration, with Nginx server-side rendering to inject these values:

1. Copy `.env.example` to `.env` and modify the values:
   ```bash
   cp .env.example .env
   ```
   
2. Edit the `.env` file to set your configuration:
   ```
   # Frontend root directory (absolute path)
   FRONTEND_ROOT=/path/to/your/bring_importer/frontend
   
   # API configuration
   API_URL=http://localhost:8001
   FRONTEND_URL=http://localhost
   
   # Backend configuration 
   BACKEND_URL=http://localhost:8001
   ```

3. Run the setup-env.sh script to install necessary dependencies:
   ```bash
   ./setup-env.sh
   ```

4. Start the application with the new configuration:
   ```bash
   ./start.sh
   ```

This server-side approach allows configuration without modifying code and injects environment variables directly into the frontend at runtime.

#### 2. Browser Local Storage (Legacy)

You can still use the browser's localStorage approach:

1. Open the `env-config.html` page in your browser
2. Set the API URL (e.g., `http://localhost:8001` for local development or `https://api.example.com` for production)
3. Set the Frontend URL (e.g., `http://localhost:8000` for local or `https://app.example.com` for production)
4. Click "Save Settings"
5. Refresh the app to apply the new settings

These settings are stored in the browser's localStorage and persist until cleared.

## Development

The repo is split into `backend/` (FastAPI + SQLite) and `frontend/` (static SPA). All commands run from the repo root via the `Makefile`.

### Run the tests

```bash
make test            # fast, no coverage
make coverage        # with coverage; fails under 80%
pytest -m integration  # only the end-to-end tests
```

### Run lint and type-check

```bash
make lint            # ruff + black --check + isort --check-only
make typecheck       # mypy (allowed to be noisy until type hints land)
```

### Install pre-commit hooks

The first time you clone, install the pre-commit hooks so they fire on every commit:

```bash
make install-dev
```

To run them manually against every file:

```bash
make hooks
```

### CI

Every push and PR to `main` runs `.github/workflows/ci.yml` with four parallel jobs:

- **Lint** — `ruff check` + `black --check` + `isort --check-only`
- **Type-check** — `mypy backend/`
- **Test** — `pytest --cov-fail-under=80` with JUnit XML uploaded as an artifact
- **Docker build** — validates `backend/Dockerfile` builds successfully (with GHA layer cache)

All four must pass before a PR can be merged. `deploy-lightsail.yml` is gated on the `CI` workflow succeeding on `main` via the `workflow_run` event.

To run the same checks locally:

```bash
make ci
```

### Backend testing docs

See `backend/TESTING.md` for the test layout, fixture documentation, and coverage-threshold rationale.
