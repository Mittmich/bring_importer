# Run CI locally

Mirror the GitHub Actions CI pipeline locally. Runs in the same order as CI: lint → typecheck → tests → frontend build. Stops on the first failure and reports clearly.

Docker build is skipped (slow, impractical locally — CI handles it).

---

## Step 1 — Backend: sync deps

Ensure the backend virtualenv is up to date before running any checks:

```bash
cd /home/michael/bring_importer/backend && uv sync --extra dev 2>&1
```

If this fails (e.g. uv not installed), stop and report the error.

---

## Step 2 — Backend: lint

Run all three linters in order. Stop at the first failure.

```bash
cd /home/michael/bring_importer/backend && uv run ruff check . 2>&1
```

```bash
cd /home/michael/bring_importer/backend && uv run black --check . 2>&1
```

```bash
cd /home/michael/bring_importer/backend && uv run isort --check-only . 2>&1
```

For each: if the exit code is non-zero, show the full output and stop with a lint failure message.

---

## Step 3 — Backend: type-check

```bash
cd /home/michael/bring_importer/backend && uv run ty check . 2>&1
```

If exit code is non-zero, show the output and stop.

---

## Step 4 — Backend: pytest with coverage

```bash
cd /home/michael/bring_importer/backend && uv run pytest --cov=api --cov=manage_users --cov-fail-under=80 -v 2>&1
```

If tests fail or coverage is below 80%, show the failure output and stop.

---

## Step 5 — Frontend: install and build

First, install npm deps (equivalent to CI's `npm ci`):

```bash
cd /home/michael/bring_importer/frontend-react && npm install 2>&1 | tail -5
```

Then type-check + build (this runs `tsc -b && vite build`):

```bash
cd /home/michael/bring_importer/frontend-react && npm run build 2>&1
```

If exit code is non-zero, show the full output (TypeScript errors are important to see) and stop.

---

## Step 6 — Report

Print a compact summary of all steps:

```
── Backend sync     ✅ / ❌
── ruff             ✅ / ❌
── black            ✅ / ❌
── isort            ✅ / ❌
── ty typecheck     ✅ / ❌
── pytest (cov)     ✅ N passed, X% coverage / ❌
── npm install      ✅ / ❌
── Frontend build   ✅ built in Xs / ❌
```

If everything passed, end with **"CI passed."**
If any step failed, end with **"CI failed at: <step name>"** and a one-line summary of the error.
