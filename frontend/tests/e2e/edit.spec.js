// edit.spec.js — the edit page prefills from the API and PUTs back.

import { test, expect } from '@playwright/test';
import { login } from './fixtures.js';

test.beforeEach(async ({ page }) => {
  await login(page);
  await page.click('#importUrlBtn');
  await page.fill('#importUrlInput', 'https://example.test/recipe');
  await page.click('#urlImportBtn');
  await page.locator('#previewModal #saveToLibraryBtn').click();
});

test('editing a field and saving returns to the detail page with the new value', async ({
  page,
}) => {
  await page.goto('/recipes.html');
  await page.locator('#recipes-list .list-group-item').first().click();

  await page.click('#edit-btn');
  await expect(page).toHaveURL(/edit-recipe\.html/);

  await page.fill('#title', 'Edited Title');
  await page.click('#saveBtn');

  await expect(page).toHaveURL(/recipe-data\.html/);
  // The title now appears in the recipe container or fallback.
  await expect(page.locator('#recipe-container, #recipe-fallback')).toContainText('Edited Title');
});
