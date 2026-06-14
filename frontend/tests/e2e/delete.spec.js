// delete.spec.js — confirm modal flow; cancel keeps, confirm removes.

import { test, expect } from '@playwright/test';
import { login } from './fixtures.js';

test.beforeEach(async ({ page }) => {
  await login(page);
  await page.click('#importUrlBtn');
  await page.fill('#importUrlInput', 'https://example.test/recipe');
  await page.click('#urlImportBtn');
  await page.locator('#previewModal #saveToLibraryBtn').click();
});

test('cancelling the delete confirm keeps the recipe', async ({ page }) => {
  await page.goto('/recipes.html');
  await page.locator('#recipes-list .list-group-item').first().click();
  await page.click('#delete-btn');

  const modal = page.locator('#deleteConfirmModal');
  await expect(modal).toBeVisible();
  await modal.locator('button:has-text("Cancel")').click();
  await expect(modal).toBeHidden();

  // Still on the detail page; recipe still exists.
  await expect(page).toHaveURL(/recipe-data\.html/);
  await page.goto('/recipes.html');
  await expect(page.locator('#recipes-list .list-group-item')).toHaveCount(1);
});

test('confirming the delete removes the recipe and navigates home', async ({ page }) => {
  await page.goto('/recipes.html');
  await page.locator('#recipes-list .list-group-item').first().click();
  await page.click('#delete-btn');
  await page.locator('#deleteConfirmModal #confirmDeleteBtn').click();

  // We navigate to the home page on success.
  await expect(page).toHaveURL(/\/(index\.html)?$/);
  await expect(page.locator('#recipe-list-empty')).toBeVisible();
});
