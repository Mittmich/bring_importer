// Vitest configuration for the static-script frontend.
//
// We test pure helpers under `js/lib/**` plus small app-shim modules
// that need a DOM. Tests live under `tests/unit/` and use `jsdom`
// (no real browser). E2E lives under `tests/e2e/` and runs under
// Playwright (separate config).

import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['tests/unit/**/*.test.{js,ts}'],
    setupFiles: ['tests/unit/setup.js'],
    coverage: {
      provider: 'v8',
      include: ['js/lib/**'],
      reporter: ['text', 'html'],
      thresholds: {
        lines: 80,
        functions: 80,
        statements: 80,
        branches: 70,
      },
    },
  },
});
