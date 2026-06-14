// Shared helpers for the Playwright E2E specs.
//
// The fixtures here are deliberately lightweight (no `test.extend`):
// each spec logs in via the login page, which mirrors what a real user
// would do. `RECIPE_TEST_MOCKS=1` is set by the Playwright webServer,
// so the backend has canned OpenAI responses and a pre-seeded user.

import { expect } from '@playwright/test';

export const TEST_USER = {
  email: 'test@example.com',
  password: 'correctpassword',
};

export async function login(page) {
  await page.goto('/login.html');
  await page.fill('input[type="email"], input[name="email"], #email', TEST_USER.email);
  await page.fill('input[type="password"], input[name="password"], #password', TEST_USER.password);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.includes('login')),
    page.click('button[type="submit"], button:has-text("Login"), button:has-text("Log in")'),
  ]);
}

export async function logout(page) {
  // The user modal has a Logout button; the simpler path is to clear
  // the token directly.
  await page.evaluate(() => localStorage.removeItem('auth_token'));
}
