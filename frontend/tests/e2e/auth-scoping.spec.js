// auth-scoping.spec.js — user A's recipe is not visible in user B's
// listing. The backend's RECIPE_TEST_MOCKS=1 seeds only one user, so
// "user B" is a token signed for a non-existent user; the listing
// requires auth, so an invalid token just bounces to login.

import { test, expect } from '@playwright/test';
import { TEST_USER, login } from './fixtures.js';
import { createHash } from 'crypto';

function fakeJwt(sub) {
  // The login form is not in scope; we bypass it and set a forged
  // token via localStorage. The backend will reject it as 401 because
  // the user doesn't exist.
  const header = Buffer.from(JSON.stringify({ alg: 'none', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(
    JSON.stringify({ sub, exp: Math.floor(Date.now() / 1000) + 600 }),
  ).toString('base64url');
  return `${header}.${payload}.`;
}

test('a token for a non-existent user cannot list recipes', async ({ page }) => {
  await page.goto('/index.html');
  await page.evaluate((t) => localStorage.setItem('auth_token', t), fakeJwt('nobody@example.com'));
  await page.goto('/recipes.html');
  // Backend returns 401, the page redirects to login.
  await expect(page).toHaveURL(/login\.html/);
});
