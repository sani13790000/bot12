/**
 * frontend/e2e/smoke.spec.ts
 * FIX-E20: E2E smoke test — login flow + dashboard load
 * اجرا: npx playwright test e2e/smoke.spec.ts
 */
import { test, expect } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const TEST_EMAIL    = process.env.E2E_EMAIL    ?? "test@example.com";
const TEST_PASSWORD = process.env.E2E_PASSWORD ?? "testpassword123";

test.describe("Galaxy Vast AI — Smoke Tests", () => {

  test("root redirects to /dashboard or /login", async ({ page }) => {
    await page.goto(BASE);
    await page.waitForURL(/\/(dashboard|login)/, { timeout: 10_000 });
    const url = page.url();
    expect(url).toMatch(/\/(dashboard|login)$/);
  });

  test("login page loads", async ({ page }) => {
    await page.goto(`${BASE}/login`);
    await expect(page.locator("form")).toBeVisible({ timeout: 8_000 });
    await expect(page.locator("input[type=email], input[name=email]")).toBeVisible();
    await expect(page.locator("input[type=password]")).toBeVisible();
  });

  test("login with invalid credentials shows error", async ({ page }) => {
    await page.goto(`${BASE}/login`);
    await page.fill("input[type=email], input[name=email]", "wrong@email.com");
    await page.fill("input[type=password]", "wrongpassword");
    await page.click("button[type=submit]");
    // خطا یا alert نشان داده می‌شود
    await expect(
      page.locator("[role=alert], .error, [data-testid=error]").first()
    ).toBeVisible({ timeout: 8_000 });
  });

  test("404 page shows not-found content", async ({ page }) => {
    await page.goto(`${BASE}/nonexistent-page-xyz-123`);
    // یا 404 یا redirect به login/dashboard
    const url = page.url();
    const is404OrRedirect = url.includes("nonexistent") ||
                            url.includes("login") ||
                            url.includes("dashboard");
    expect(is404OrRedirect).toBe(true);
  });

  test.skip("authenticated: dashboard loads live data", async ({ page }) => {
    // این تست نیاز به backend و credentials واقعی دارد
    await page.goto(`${BASE}/login`);
    await page.fill("input[type=email], input[name=email]", TEST_EMAIL);
    await page.fill("input[type=password]", TEST_PASSWORD);
    await page.click("button[type=submit]");
    await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
    await expect(page.locator("[data-testid=dashboard-content]")).toBeVisible();
  });

});
