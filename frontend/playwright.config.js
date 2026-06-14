// Playwright configuration for the Recipe to Bring Importer E2E suite.
//
// Two web servers: the FastAPI backend (uvicorn on 8001) and a
// static file server for the frontend on 8000. Both are started
// automatically by Playwright before the tests run.
//
// Per the comprehensive-recipe-management plan, v1 targets Chromium
// only. To re-enable Firefox/WebKit, uncomment the additional
// `projects` blocks below.

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://localhost:8000',
    actionTimeout: 10_000,
    trace: 'on-first-retry',
  },
  webServer: [
    {
      command: 'cd ../backend && RECIPE_TEST_MOCKS=1 uv run uvicorn api.main:app --port 8001',
      url: 'http://localhost:8001/health',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: 'npx http-server . -p 8000 -s',
      url: 'http://localhost:8000',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'webkit',
    //   use: { ...devices['Desktop Safari'] },
    // },
  ],
});
