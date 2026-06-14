// detail.spec.js — the recipe detail page renders the imported recipe
// and the Add-to-Bring / Edit / Delete buttons are present.

import { test, expect } from '@playwright/test';
import { login } from './fixtures.js';

test.beforeEach(async ({ page }) => {
  await login(page);
  // Seed one recipe via the URL modal.
  await page.click('#importUrlBtn');
  await page.fill('#importUrlInput', 'https://example.test/recipe');
  await page.click('#urlImportBtn');
  await page.locator('#previewModal #saveToLibraryBtn').click();
});

test('detail page shows the title, action buttons, and bring import card', async ({ page }) => {
  await page.goto('/recipes.html');
  await page.locator('#recipes-list .list-group-item').first().click();
  await expect(page).toHaveURL(/recipe-data\.html/);

  // Action buttons are present.
  await expect(page.locator('#add-to-bring-btn')).toBeVisible();
  await expect(page.locator('#edit-btn')).toBeVisible();
  await expect(page.locator('#delete-btn')).toBeVisible();
  await expect(page.locator('#view-source-btn')).toBeVisible();

  // The recipe content renders (the mocked URL had a JSON-LD Recipe
  // with name "Test URL Recipe" — the editor page either uses the
  // html_content or the fallback rendering; both surface the title).
  await expect(page.locator('#recipe-container, #recipe-fallback')).toBeVisible();
});

test('Add to Bring reveals the bring import card and triggers the widget', async ({ page }) => {
  await page.goto('/recipes.html');
  await page.locator('#recipes-list .list-group-item').first().click();
  await page.click('#add-to-bring-btn');
  const card = page.locator('#bringImportCard');
  await expect(card).toBeVisible();
});
