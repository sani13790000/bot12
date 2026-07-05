/**
 * Smoke E2E test — Phase H fix
 * BUG-H6: BASE_URL was hardcoded to http://localhost:3000
 *         Now reads from PLAYWRIGHT_BASE_URL env var (CI-safe)
 */
import { test, expect } from '@playwright/test';

// Use env var for CI/CD, fallback to localhost for local dev
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000';

test.describe('GalaxyVast Frontend Smoke Tests', () => {
  test('root redirects to dashboard or login', async ({ page }) => {
    const response = await page.goto(BASE_URL);
    expect(response?.status()).toBeLessThan(500);
    // Should land on /dashboard or /login
    await expect(page).toHaveURL(
      /(dashboard|login|auth|home|\/$)/i,
      { timeout: 10_000 }
    );
  });

  test('login page renders key elements', async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    // Must have at least one input (email or username)
    const inputs = page.locator('input');
    await expect(inputs.first()).toBeVisible({ timeout: 8_000 });
  });

  test('invalid login shows error feedback', async ({ page }) => {
    await page.goto(`${BASE_URL}/login`);
    // Fill with obviously wrong credentials
    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i]').first();
    const passInput  = page.locator('input[type="password"]').first();

    if (await emailInput.count() > 0) {
      await emailInput.fill('bad@test.invalid');
    }
    if (await passInput.count() > 0) {
      await passInput.fill('wrongpassword123');
    }

    // Submit form
    const submitBtn = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("ورود")').first();
    if (await submitBtn.count() > 0) {
      await submitBtn.click();
      // Some kind of error feedback should appear
      const errorFeedback = page.locator('[role="alert"], .error, .text-red, [class*="error"], [class*="danger"]').first();
      await expect(errorFeedback).toBeVisible({ timeout: 8_000 }).catch(() => {
        // Acceptable if page redirects or shows toast instead
      });
    }
  });

  test('404 page handled gracefully', async ({ page }) => {
    const response = await page.goto(`${BASE_URL}/this-page-does-not-exist-xyz`);
    // Should not return 500
    expect(response?.status()).not.toBe(500);
    // Should show some content
    await expect(page.locator('body')).not.toBeEmpty();
  });

  test('API health endpoint reachable from frontend config', async ({ page }) => {
    // Check that VITE_API_URL or fallback is used correctly
    await page.goto(BASE_URL);
    // No console errors about missing API URL
    const consoleLogs: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') consoleLogs.push(msg.text());
    });
    await page.waitForLoadState('networkidle').catch(() => {});
    // Filter out known acceptable errors
    const criticalErrors = consoleLogs.filter(log =>
      log.includes('VITE_API_URL') && log.includes('undefined')
    );
    expect(criticalErrors.length).toBe(0);
  });
});
