# Verify docker-compose stack locally

Spin up the full docker-compose stack, run smoke tests, then report a pass/fail summary. Tears down the stack afterwards unless the user asks to keep it running.

## Steps

### 1. Pre-flight

Run all checks in parallel:

```bash
# Docker daemon reachable?
docker info > /dev/null 2>&1 && echo "docker ok" || echo "docker not running"

# Required files present?
test -f docker-compose.yml && echo "compose ok" || echo "docker-compose.yml missing"
test -f backend/Dockerfile && echo "dockerfile ok" || echo "backend/Dockerfile missing"
```

If Docker is not running, stop here and tell the user to start it. Do not proceed.

### 2. Ensure a test .env exists

The stack needs `SECRET_KEY` at minimum (JWT signing). `OPENAI_API_KEY` can be a placeholder — the health endpoint does not call OpenAI.

Check whether `.env` is present:

```bash
test -f .env && echo "found" || echo "missing"
```

**If `.env` is missing:** write a minimal one for testing purposes:

```bash
cat > .env << 'EOF'
SECRET_KEY=test-secret-key-for-local-verification-only
OPENAI_API_KEY=sk-placeholder
COMPOSE_PROJECT_NAME=bring_importer
NGINX_PORT=80
BACKEND_PORT=8001
APP_VERSION=local-verify
EOF
echo "Wrote minimal .env for verification"
```

**If `.env` exists:** leave it untouched. Inform the user that the existing `.env` will be used.

### 3. Build

```bash
docker compose build --no-cache 2>&1 | tail -20
```

Check exit code. If non-zero, show the last 40 lines of output and stop — the Dockerfile is broken.

### 4. Start the stack

Use `-f docker-compose.yml` to skip the dev override (which mounts live source files and should not be used for verification):

```bash
docker compose -f docker-compose.yml up -d
```

Then wait up to 30 seconds for the backend to become healthy. Poll every 2 seconds:

```bash
for i in $(seq 1 15); do
  status=$(curl -s -o /dev/null -w "%{http_code}" https://localhost/api/health 2>/dev/null)
  [ "$status" = "200" ] && echo "ready after ${i}s" && break
  echo "waiting... (${i}s)"
  sleep 2
done
```

If after 30 s the health endpoint still doesn't return 200, run `docker compose logs --tail=40` and report failure. Do not run smoke tests.

### 5. Smoke tests

Run each check individually and record pass/fail:

| Check | Command | Expected |
|---|---|---|
| Backend health | `curl -sf https://localhost/api/health` | HTTP 200, body contains `"status":"healthy"` |
| Frontend root | `curl -s -o /dev/null -w "%{http_code}" https://localhost/` | HTTP 200 |
| Frontend static asset | `curl -s -o /dev/null -w "%{http_code}" https://localhost/index.html` | HTTP 200 |
| Login page | `curl -s -o /dev/null -w "%{http_code}" https://localhost/login.html` | HTTP 200 |
| API 404 shape | `curl -s https://localhost/api/nonexistent` | HTTP 404, not nginx's default error page |
| API auth guard | `curl -s -o /dev/null -w "%{http_code}" https://localhost/api/recipes` | HTTP 401 or 403 (not 200, not 500) |

For the backend health test extract and show the response body so the timestamp is visible.

### 6. Container state

After tests, show:

```bash
docker compose ps
docker compose logs --tail=10
```

### 7. Report

Print a clear summary table:

```
✅ Backend health   200 {"status":"healthy","timestamp":...}
✅ Frontend root    200
✅ index.html       200
✅ login.html       200
✅ API 404 shape    404
✅ API auth guard   401
```

If any check failed, mark it ❌ and include the actual response.

### 8. Teardown

Ask the user: **"Keep the stack running or shut it down?"**

- If shut down (default): `docker compose down`
- If keep running: print `docker compose logs -f` and `docker compose down` as reminders

### Notes

- The skill uses port 80 by default. If something else is bound to :80, `docker compose up` will fail at the port-binding step — the error message will make this clear.
- If a minimal `.env` was written in step 2, remind the user to replace it with a real `.env` before running the app normally.
- This skill does not test authenticated recipe endpoints (that would require a real user + password). It only validates that the stack starts and the routing layer works.
