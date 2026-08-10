import { defineConfig } from '@playwright/test'

// OPS-DATA-02 UX-API-01 §6.7 — real browser/viewport regression suite.
// Targets the dev server directly (bash scripts/start.sh must be running);
// this does not manage the backend/DB lifecycle itself, since the suite
// needs real seeded demo accounts and real API responses, not mocks.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  // Serial, not parallel: several tests sign in as the same shared demo
  // account (manager@resortos.local etc.) and switch its server-persisted
  // preferred_language via the real LanguageSwitcher flow. Two workers
  // racing that PATCH on the same account would corrupt each other's
  // locale mid-test — correctness over speed for what's meant to be a
  // trustworthy pre-release gate, not a fast feedback loop.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:3001',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
})
