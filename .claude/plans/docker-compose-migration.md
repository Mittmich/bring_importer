---
name: docker-compose-migration
status: done
created: 2026-06-18
updated: 2026-06-18
---

# Plan: Migrate start.sh / stop.sh to docker-compose + update CI/deploy pipeline

## Goal

Replace the brittle `start.sh` / `stop.sh` scripts with a `docker-compose.yml` that orchestrates the backend (FastAPI) and frontend/proxy (Nginx) services. The result should be `docker compose up -d` to start and `docker compose down` to stop — no PID files, no manual dependency checks, no `envsubst` shell gymnastics.

## Background / what's awkward today

**Local scripts:**

| Pain point | Where it lives |
|---|---|
| `envsubst` call to render `nginx.conf.template` → `nginx.conf` | `start.sh:31` |
| PID file written to `logs/backend.pid`, manual `kill -0` health check | `start.sh:79–87` |
| `nginx -g "user ${NGINX_USER} ${NGINX_USER_GROUP};"` flag required | `start.sh:94` |
| `FRONTEND_ROOT` must be an absolute host path | `.env.example` |
| `stop.sh` manually loops with `kill` / `kill -9` fallback | `stop.sh:26–42` |
| OS-level dependency checks (`command_exists nginx`, `python3`) | `start.sh:48–63` |
| venv activation before starting backend | `start.sh:72–75` |

**CI/deploy pipeline (`deploy-lightsail.yml`):**

| Pain point | Where it lives |
|---|---|
| `sudo ./stop.sh` / `sudo ./start.sh` — sudo needed because nginx binds port 80 | `deploy-lightsail.yml:55,79` |
| uv installed on the Lightsail host (idempotent check, but still host-level state) | `deploy-lightsail.yml:39–51` |
| venv wiped on every deploy to avoid permission errors from `sudo` / user mismatch | `deploy-lightsail.yml:62–68` |
| `uv sync` re-installs all deps from scratch on the server on every deploy | `deploy-lightsail.yml:74–75` |
| No CI validation that the `Dockerfile` builds — a broken image only surfaces at deploy time | `ci.yml` (absent) |

## Architecture after migration

```
docker-compose.yml
├── backend   (python:3.11-slim)  → exposes :8001 internally
└── nginx     (nginx:alpine)      → exposes :${NGINX_PORT:-80} to host
      ├── mounts frontend/ as static files
      └── proxies /api/ → backend:8001
```

Both services share a user-defined bridge network. Nginx reaches the backend as `http://backend:8001`.

## Steps

### ✅ 1. Create `backend/Dockerfile`

- Base: `python:3.11-slim`
- Copy `backend/` into `/app`, set `WORKDIR /app`
- Install deps: `pip install uv && uv pip install --system -e .`
- `CMD ["python3", "run.py"]`
- Expose port `8001`
- Pass `OPENAI_API_KEY`, `SECRET_KEY`, `USERS_FILE`, `BACKEND_PORT` from compose env

### ✅ 2. Update `nginx.conf.template` for container use

Changes needed:
- Remove the `user` top-level directive (nginx Docker image runs as its own user; passing it via `-g` is not needed in containers)
- Hard-code `root /usr/share/nginx/html;` — `FRONTEND_ROOT` is no longer a host path, the files live inside the container
- Change `${BACKEND_URL}` default to `http://backend:8001` (service name on the compose network)
- Set `NGINX_LOGDIR` default to `/var/log/nginx` (standard nginx image path)
- Keep the `sub_filter` block for `env-config.js` injection — it still works the same way

The official `nginx:alpine` image automatically processes any `*.conf.template` file placed in `/etc/nginx/templates/` by running `envsubst` at startup and writing the result to `/etc/nginx/conf.d/`. This replaces the manual `envsubst` call in `start.sh`.

### ✅ 3. Create `docker-compose.yml`

```yaml
services:
  backend:
    build: ./backend
    env_file: .env
    environment:
      BACKEND_PORT: ${BACKEND_PORT:-8001}
    volumes:
      - ./backend/recipes.db:/app/recipes.db
      - ./backend/users.json:/app/users.json
    networks:
      - app

  nginx:
    image: nginx:alpine
    ports:
      - "${NGINX_PORT:-80}:80"
    env_file: .env
    environment:
      BACKEND_URL: http://backend:${BACKEND_PORT:-8001}
      NGINX_LOGDIR: /var/log/nginx
    volumes:
      - ./frontend:/usr/share/nginx/html:ro
      - ./nginx.conf.template:/etc/nginx/templates/default.conf.template:ro
      - ./logs:/var/log/nginx
    depends_on:
      - backend
    networks:
      - app

networks:
  app:
```

### ✅ 4. Update `.env.example`

- Remove `FRONTEND_ROOT` (no longer needed — frontend is mounted in the nginx container)
- Remove `NGINX_USER` / `NGINX_USER_GROUP` (not applicable in containers)
- Change `BACKEND_URL` default comment to `http://backend:8001` for compose; keep `http://localhost:8001` as the note for bare runs
- Add `COMPOSE_PROJECT_NAME=bring_importer` for stable container names

### ✅ 5. Update `AGENTS.md` / `README.md` startup instructions

Replace the `./start.sh` / `./stop.sh` section with:

```bash
# Start
docker compose up -d

# Stop
docker compose down

# Logs
docker compose logs -f
```

Keep the "Bare backend (no Nginx)" section — it's still useful for rapid iteration without containers.

### ✅ 6. Retire `start.sh` / `stop.sh`

Options (choose one):
- **Delete** them — clean break, grep-friendly.
- **Stub** them to `exec docker compose up / down` — preserves muscle memory.

Recommendation: delete them and update docs. The scripts exist only because there was no compose file; keeping stubs adds confusion.

### ✅ 7. (Optional) Add a `docker-compose.override.yml` for dev

Mount `backend/` as a live volume so code changes reload without rebuilding:

```yaml
services:
  backend:
    volumes:
      - ./backend:/app
    command: uvicorn api:app --host 0.0.0.0 --port 8001 --reload
```

This is purely optional — skip if the team always rebuilds.

### ✅ 8. Add a `docker-build` job to `ci.yml`

Validates that `backend/Dockerfile` builds successfully on every PR. Fails fast before the deploy step ever runs.

Add after the existing `frontend-lint` job:

```yaml
docker-build:
  name: Docker build (backend)
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3
    - name: Build backend image
      uses: docker/build-push-action@v6
      with:
        context: ./backend
        push: false
        cache-from: type=gha
        cache-to: type=gha,mode=max
```

The `type=gha` layer cache means repeat builds on unchanged deps are near-instant. `push: false` keeps this purely a validation step — no registry credentials needed.

### ✅ 9. Rewrite `deploy-lightsail.yml`

Replace everything after the SSH key setup with a single `docker compose up -d --build`. The complete new deploy job:

```yaml
jobs:
  deploy:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up SSH key
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.LIGHTSAIL_SSH_KEY }}

      - name: Add Lightsail host to known_hosts
        run: ssh-keyscan -H ${{ secrets.LIGHTSAIL_HOST }} >> ~/.ssh/known_hosts

      - name: Pull latest code
        run: |
          ssh ${{ secrets.LIGHTSAIL_USER }}@${{ secrets.LIGHTSAIL_HOST }} \
            'cd ${{ secrets.LIGHTSAIL_APP_PATH }} && git fetch origin && git reset --hard origin/main'

      - name: Deploy with docker compose
        run: |
          ssh ${{ secrets.LIGHTSAIL_USER }}@${{ secrets.LIGHTSAIL_HOST }} \
            'cd ${{ secrets.LIGHTSAIL_APP_PATH }} && docker compose up -d --build'

      - name: Print deployment success
        run: echo "Deployment to AWS Lightsail completed."
```

**What this removes:** the uv install step, the venv wipe, the `uv sync`, `sudo ./stop.sh`, and `sudo ./start.sh`. Docker handles process management; `--build` rebuilds only changed layers (fast thanks to layer caching on the server); `up -d` gracefully replaces running containers.

**`sudo` note:** `docker compose` can run without sudo if the deploy user is in the `docker` group on the Lightsail instance. Run once on the instance: `sudo usermod -aG docker $USER`. No workflow change needed.

#### Alternative: build image in CI, push to GHCR, pull on Lightsail

If the Lightsail instance is underpowered (≤1 GB RAM), building the Docker image on it may be slow or OOM. The alternative is to build and push to GitHub Container Registry (GHCR) in CI, then just `docker compose pull && docker compose up -d` on the server.

Trade-offs:

| | Build on server (recommended for now) | Build in CI → GHCR |
|---|---|---|
| Complexity | Low — no registry | Medium — needs `GHCR_TOKEN` secret, image tag strategy |
| Deploy speed | Rebuilds on server (layer cache helps) | Pull pre-built image — very fast |
| Server load | Higher during build | Minimal |
| Best fit | Small project, ≤2 deploys/day | High-frequency deploys or small server |

Recommendation: start with build-on-server (simpler). Switch to GHCR if deploy times become painful.

## Env vars that change meaning

| Var | Before | After |
|---|---|---|
| `FRONTEND_ROOT` | Host absolute path to `frontend/` | **Removed** — path is fixed inside nginx container |
| `BACKEND_URL` | `http://localhost:8001` | `http://backend:8001` in compose; `http://localhost:8001` for bare runs |
| `NGINX_USER` / `NGINX_USER_GROUP` | Passed via `nginx -g "user ..."` | **Removed** |
| `NGINX_LOGDIR` | Host path to `logs/` | `/var/log/nginx` (still bind-mounted to host `logs/`) |

## Files touched

| File | Action |
|---|---|
| `backend/Dockerfile` | Create |
| `docker-compose.yml` | Create |
| `docker-compose.override.yml` | Create (optional, dev only) |
| `nginx.conf.template` | Edit (remove `user` directive, fix `FRONTEND_ROOT`) |
| `.env.example` | Edit (remove dead vars, update defaults) |
| `.github/workflows/ci.yml` | Edit (add `docker-build` job) |
| `.github/workflows/deploy-lightsail.yml` | Rewrite (replace uv/venv/start.sh steps with `docker compose up -d --build`) |
| `AGENTS.md` | Edit (update startup instructions, repo map) |
| `README.md` | Edit (update quickstart) |
| `start.sh` | Delete |
| `stop.sh` | Delete |

## One-time server setup

Before the new deploy workflow can run, the Lightsail instance needs Docker and Compose installed, and the deploy user must be in the `docker` group:

```bash
# Install Docker Engine (Ubuntu)
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin

# Allow deploy user to run docker without sudo
sudo usermod -aG docker $USER   # log out + back in to take effect
```

This is a one-time manual step; it does not go in the workflow.

## Outcome

All 9 steps implemented. `start.sh` and `stop.sh` deleted. Stack is now `docker compose up -d`. CI validates the Dockerfile on every PR. Deploy pipeline reduced from 7 steps to 2 (pull + `docker compose up -d --build`).

## Definition of done

- `docker compose up -d` starts both services with no manual steps.
- `http://localhost` serves the frontend; `/api/health` returns 200 proxied from the backend.
- `docker compose down` stops everything cleanly.
- `logs/` on the host receives nginx access/error logs.
- `recipes.db` persists between `down` / `up` cycles via bind mount.
- `start.sh`, `stop.sh` are gone.
- `.env.example` has no dead vars.
- CI `docker-build` job passes on a clean PR.
- Deploy workflow no longer contains `uv`, `venv`, or `start.sh` references.
- A push to `main` that passes CI triggers a deploy via `docker compose up -d --build` with no `sudo`.
