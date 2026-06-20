# Verify local dev app

Run a fast, minimal verification of the app against the locally-running dev servers. No docker-compose required. Covers backend unit tests, TypeScript build, and live smoke tests if the servers are already up.

## Steps

### 1. Backend unit tests

```bash
cd /home/michael/bring_importer/backend && uv run pytest -q 2>&1
```

Check exit code. If tests fail, show the failure output and stop — do not proceed to smoke tests.

### 2. Frontend TypeScript build check

```bash
cd /home/michael/bring_importer/frontend-react && npm run build 2>&1 | tail -10
```

Check exit code. A non-zero exit means a TypeScript or bundling error — show the output.

### 3. Detect running servers

Check which dev servers are already up:

```bash
# Backend
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health 2>/dev/null

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/ 2>/dev/null
```

If neither is running, report that smoke tests are skipped and go straight to the summary.

### 4. Smoke tests (only if backend is running on :8001)

Run each check and record pass/fail:

| Check | Command | Expected |
|---|---|---|
| Backend health | `curl -sf http://localhost:8001/health` | HTTP 200, body contains `"status":"healthy"` |
| Auth guard | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/recipes` | HTTP 401 (not 200, not 500) |
| Recipe JSON 404 | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/recipes/00000000-0000-4000-0000-000000000000.json` | HTTP 404 |
| Recipe HTML 404 | `curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/recipes/00000000-0000-4000-0000-000000000000.html` | HTTP 404 |

Show the health endpoint response body so the timestamp is visible.

If the frontend dev server is running on :5173, also check:

| Check | Command | Expected |
|---|---|---|
| Frontend root | `curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/` | HTTP 200 |

### 5. Report

Print a compact summary:

```
── Backend tests    ✅ 74 passed
── TS build         ✅ built in 993ms
── Backend running  ✅ :8001
── Health           ✅ 200 {"status":"healthy","timestamp":...}
── Auth guard       ✅ 401
── Recipe 404 json  ✅ 404
── Recipe 404 html  ✅ 404
── Frontend running ✅ :5173  (or ⏭ not running — skipped)
```

Mark failures with ❌ and include the actual value received. If any step failed, end with a clear failure line; otherwise end with "All checks passed."
