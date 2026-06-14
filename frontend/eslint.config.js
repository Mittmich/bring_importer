// ESLint flat config for the Recipe to Bring Importer frontend.
//
// Catches common bugs (unused vars, undefined refs) and surfaces XSS
// risks via the `no-unsanitized` plugin (catches `innerHTML` and friends),
// which the recipe→HTML helpers use heavily.

import js from '@eslint/js';
import globals from 'globals';
import noUnsanitized from 'eslint-plugin-no-unsanitized';

export default [
  js.configs.recommended,
  {
    languageOptions: {
      // Browser globals for the app code; Node + Vitest globals for the
      // test files. The frontend is a mix: app code runs in a browser,
      // tests run under Vitest (Node + jsdom).
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.vitest,
        // Some pages still have inline script tags; allow the noop
        // localStorage stub used by jsdom.
        localStorage: 'readonly',
        fetch: 'readonly',
        atob: 'readonly',
        btoa: 'readonly',
        FileReader: 'readonly',
        Image: 'readonly',
        DataTransfer: 'readonly',
        bootstrap: 'readonly',
        // Used by the Edit-page spec.
        Buffer: 'readonly',
        // The app's window.* globals — these come from script tags
        // that load before app.js (env-config.js, config.js, utils.js,
        // lib/recipe-html.js). Treat them as readable browser globals.
        config: 'readonly',
        recipeLib: 'readonly',
        showBringWidget: 'readonly',
      },
    },
    plugins: { 'no-unsanitized': noUnsanitized },
    rules: {
      'no-unsanitized/property': 'warn',
      'no-unsanitized/method': 'warn',
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      // The fallback URLs in js/config.js are literal strings on the
      // right-hand side of `||` (intentional dev defaults). The rule
      // flags them; disable it.
      'no-constant-binary-expression': 'off',
    },
  },
  {
    ignores: [
      'node_modules/**',
      'coverage/**',
      'playwright-report/**',
      'test-results/**',
      'playwright/.cache/**',
    ],
  },
];
