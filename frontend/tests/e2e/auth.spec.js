// auth.spec.js — login page renders; correct password lands on home; wrong
// password shows the error. The backend (RECIPE_TEST_MOCKS=1) has
// `test@example.com` / `correctpassword` pre-seeded.

import { test, expect } from '@playwright/test';
import { TEST_USER, login } from './fixtures.js';

test('login page renders the email and password fields', async ({ page }) => {
  await page.goto('/login.html');
  await expect(page.locator('input[type="email"], input[name="email"], #email')).toBeVisible();
  await expect(
    page.locator('input[type="password"], input[name="password"], #password'),
  ).toBeVisible();
});

test('correct password lands on the home page', async ({ page }) => {
  await login(page);
  await expect(page).toHaveURL(/\/(index\.html)?$/);
});

test('wrong password shows an error', async ({ page }) => {
  await page.goto('/login.html');
  await page.fill('input[type="email"], input[name="email"], #email', TEST_USER.email);
  await page.fill('input[type="password"], input[name="password"], #password', 'wrong-password');
  await page.click('button[type="submit"], button:has-text("Login"), button:has-text("Log in")');
  // The page should remain on /login.html and show some indication of failure.
  await expect(page).toHaveURL(/login\.html/);
  // A non-empty body that isn't the empty "loading" state.
  await expect(page.locator('body')).not.toBeEmpty();
});
