# Recipe to Bring Importer

This is a Progressive Web App (PWA) that lets you upload recipe photos, extract ingredients using OpenAI's Vision API, and import them directly to your Bring shopping list.

## Features

- **Photo Upload**: Take a photo of a recipe or upload an existing one
- **AI-Powered Recipe Parsing**: Uses OpenAI's Vision API to extract recipe information
- **Bring Integration**: Import ingredients directly to the Bring shopping list app
- **Works Offline**: Install as a PWA for offline access
- **Secure**: Your OpenAI API key is stored locally and never sent to any server other than OpenAI

## How to Use

1. Click the settings (⚙️) icon on the sidebar to add your OpenAI API key
2. Upload a photo of a recipe
3. Click "Parse Recipe" to extract the recipe information
4. Review the extracted ingredients
5. Click "Import to Bring" to add ingredients to your Bring shopping list

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

### Running with Nginx

For production-like deployments, you can use Nginx to serve the static frontend files and proxy API requests to the backend:

1. Make sure Nginx is installed:
   ```bash
   brew install nginx     # On macOS
   # or
   sudo apt install nginx # On Ubuntu/Debian
   ```

2. Start the application using the provided script:
   ```bash
   ./start.sh
   ```
   
   This script will:
   - Start the FastAPI backend
   - Configure and start Nginx with the provided configuration
   - Serve the frontend at http://localhost:80
   - Proxy API requests from /api/* to the backend

3. To stop the application:
   ```bash
   ./stop.sh
   ```

Note: If you want to run Nginx on port 80, you'll need to run the start script with sudo privileges:
```bash
sudo ./start.sh
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

Every push and PR to `main` runs `.github/workflows/ci.yml` with three parallel jobs:

- **Lint** — `ruff check` + `black --check` + `isort --check-only`
- **Type-check** — `mypy backend/` (currently `continue-on-error: true` until type hints land)
- **Test** — `pytest --cov-fail-under=80` with JUnit XML uploaded as an artifact

All three must pass before a PR can be merged. The existing `deploy-lightsail.yml` is gated on the `CI` workflow succeeding on `main` via the `workflow_run` event.

To run the same checks locally:

```bash
make ci
```

### Backend testing docs

See `backend/TESTING.md` for the test layout, fixture documentation, and coverage-threshold rationale.
