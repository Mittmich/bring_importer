// import-photo.spec.js — happy path through the photo modal.
//
// The photo "file" we upload is a tiny in-memory PNG; OpenAI is mocked
// to return the canonical recipe HTML, so the parse + preview steps
// complete without any real network.

import { test, expect } from '@playwright/test';
import { login } from './fixtures.js';

// 1x1 transparent PNG. The bytes don't matter; the test mocks OpenAI.
const TINY_PNG = Buffer.from(
  '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4' +
    '890000000a49444154789c6300010000000500010d0a2db40000000049454e44ae426082',
  'hex',
);

test.beforeEach(async ({ page }) => {
  await login(page);
});

test('happy path: import from photo saves the recipe to the library', async ({ page }) => {
  await page.click('#importPhotoBtn');
  await page.setInputFiles('#photo', {
    name: 'recipe.png',
    mimeType: 'image/png',
    buffer: TINY_PNG,
  });
  await page.click('#photoParseBtn');

  // The preview modal should appear with the parsed recipe.
  const preview = page.locator('#previewModal');
  await expect(preview).toBeVisible();
  await expect(preview).toContainText(/pancakes|recipe/i);

  // Save to library.
  await preview.locator('#saveToLibraryBtn').click();

  // The home page now lists the recipe.
  await expect(page.locator('#recipe-list')).toContainText(/pancakes|test/i);
});

test('error path: missing file shows an error and keeps the modal open', async ({ page }) => {
  await page.click('#importPhotoBtn');
  // No file selected; just click Parse.
  await page.click('#photoParseBtn');
  const modal = page.locator('#importPhotoModal');
  await expect(modal).toBeVisible();
  await expect(modal.locator('#photoModalError')).toBeVisible();
});
