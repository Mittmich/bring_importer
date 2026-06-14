// home.spec.js — empty state, import buttons render, modals open.

import { test, expect } from '@playwright/test';
import { login } from './fixtures.js';

test.beforeEach(async ({ page }) => {
  await login(page);
});

test('home page shows both import buttons', async ({ page }) => {
  await expect(page.locator('#importPhotoBtn')).toBeVisible();
  await expect(page.locator('#importUrlBtn')).toBeVisible();
});

test('import from photo button opens the photo modal', async ({ page }) => {
  await page.click('#importPhotoBtn');
  const modal = page.locator('#importPhotoModal');
  await expect(modal).toBeVisible();
  await expect(modal.locator('#photo')).toBeVisible();
  // Close it.
  await modal.locator('button[data-bs-dismiss="modal"], .btn-close').first().click();
  await expect(modal).toBeHidden();
});

test('import from URL button opens the URL modal', async ({ page }) => {
  await page.click('#importUrlBtn');
  const modal = page.locator('#importUrlModal');
  await expect(modal).toBeVisible();
  await expect(modal.locator('#importUrlInput')).toBeVisible();
  await modal.locator('button[data-bs-dismiss="modal"], .btn-close').first().click();
  await expect(modal).toBeHidden();
});

test('empty home shows the "no recipes" hint', async ({ page }) => {
  await expect(page.locator('#recipe-list-empty')).toBeVisible();
});
