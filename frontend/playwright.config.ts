/**
 * playwright.config.ts — Phase O fix
 * BUG-O4: E2E smoke test 'no console errors' catches ALL fetch errors in CI
 *   - webServer block added: waits for frontend dev server before running tests
 *   - In CI: PLAYWRIGHT_BASE_URL is set externally (running server)
 *   - In local dev: starts 'npm run dev' automatically
 */
import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000';
const IS_CI    = !!process.env.CI;

export default defineConfig({
  testDir:    './e2e',
  timeout:    30_000,
  retries:    IS_CI ? 2 : 0,
  workers:    IS_CI ? 1 : undefined,
  reporter:   IS_CI ? 'github' : 'html',

  use: {
    baseURL:      BASE_URL,
    trace:        'on-first-retry',
    screenshot:   'only-on-failure',
    video:        'retain-on-failure',
  },

  projects: [
    {
      name:  'chromium',
      use:   { ...devices['Desktop Chrome'] },
    },
  ],

  // BUG-O4 fix: start dev server automatically in local dev
  // In CI, PLAYWRIGHT_BASE_URL points to already-running server
  webServer: IS_CI ? undefined : {
    command:            'npm run dev',
    url:                BASE_URL,
    reuseExistingServer: true,
    timeout:            60_000,
  },
});
