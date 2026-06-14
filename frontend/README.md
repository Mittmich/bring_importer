# Frontend (Recipe to Bring Importer)

Static HTML/CSS/JS. No build step.

## Quick reference

```bash
# Install dev/test deps (one-time)
npm install

# Run Vitest unit tests for js/lib/**
npm test

# Run Vitest with coverage (≥80% lines/functions/statements, ≥70% branches on js/lib/**)
npm run test:coverage

# Install Chromium for Playwright (one-time)
npx playwright install --with-deps chromium

# Run E2E suite (starts the FastAPI backend + a static http-server automatically)
npm run test:e2e
```

See the project-root `README.md` for the app's user-facing docs and `TESTING.md` for backend testing.
