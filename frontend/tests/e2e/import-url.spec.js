// import-url.spec.js — happy path with a JSON-LD URL, error path with an
// unrecognised URL. The backend's RECIPE_TEST_MOCKS=1 stubs the URL fetch
// for the registered URLs and returns 404 for anything else.

import { test, expect } from '@playwright/test';
import { login } from './fixtures.js';

const GOOD_URL = 'https://example.test/recipe';
const BAD_URL = 'https://example.test/not-registered';

test.beforeEach(async ({ page }) => {
  await login(page);
});

test('happy path: import a known URL via the JSON-LD path', async ({ page }) => {
  await page.click('#importUrlBtn');
  await page.fill('#importUrlInput', GOOD_URL);
  await page.click('#urlImportBtn');

  // Preview modal appears with the parsed recipe.
  const preview = page.locator('#previewModal');
  await expect(preview).toBeVisible();
  await expect(preview).toContainText(/test url recipe/i);
  await preview.locator('#saveToLibraryBtn').click();

  // Recipe appears on the home list.
  await expect(page.locator('#recipe-list')).toContainText(/test url recipe/i);
});

test('error path: unrecognised URL shows a user-readable error', async ({ page }) => {
  await page.click('#importUrlBtn');
  await page.fill('#importUrlInput', BAD_URL);
  await page.click('#urlImportBtn');

  const modal = page.locator('#importUrlModal');
  // The modal stays open and the error block is visible.
  await expect(modal).toBeVisible();
  await expect(modal.locator('#urlModalError')).toBeVisible();
  await expect(modal.locator('#urlModalError')).toContainText(/http|fetch|404/i);
});
