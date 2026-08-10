import { expect, type Page } from '@playwright/test'

// manager@resortos.local — level 60, lands on /admin/dashboard, no 2FA
// enrollment gate (unlike super_admin/accountant) so it's a stable
// Playwright login target. Password matches scripts/status.sh's printed
// demo credentials (dev-only seed, never a real account).
export const MANAGER = { username: 'manager@resortos.local', password: 'Demo@123456' }
export const RECEPTIONIST = { username: 'reception@resortos.local', password: 'Demo@123456' }
// Found broken while building this suite (2026-08-10), not usable yet:
// both timeshare_admin@resortos.local and timeshare_agent@resortos.local
// have zero active branch memberships in this dev seed and dead-end on
// /select-branch ("لا يوجد فرع تشغيلي مسند لهذا الحساب"). Real, separate
// demo-seed gap — flagged, not fixed as part of UX-API-01.
export const TIMESHARE_ADMIN = { username: 'timeshare_admin@resortos.local', password: 'Demo@123456' }

export async function login(
  page: Page,
  creds: { username: string; password: string } = MANAGER,
): Promise<void> {
  await page.goto('/login')
  await page.locator('#login-username').fill(creds.username)
  await page.locator('#login-password').fill(creds.password)
  await page.locator('button[type="submit"]').click()
  // Land somewhere past /login — exact home route depends on role
  // (homeRouteFor), so just wait for the redirect rather than a fixed path.
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 10_000 })

  // An account with >1 active branch membership lands on /select-branch
  // first (a screen with no LanguageSwitcher — switchLanguage() would hang
  // here). Branch buttons render before the trailing logout button
  // (BranchSelectionView.vue) once the async branches fetch resolves, so
  // more than one button means a real branch is present, not just logout.
  // An account with *zero* branches also lands here but never gains a
  // second button (empty-state message instead) — the assertion below
  // fails loudly with that distinction rather than hanging on a click.
  if (page.url().includes('/select-branch')) {
    await expect(
      page.locator('button'),
      `${creds.username} landed on /select-branch with only a logout button — `
        + 'no active branch membership for this account (see TIMESHARE_ADMIN comment)',
    ).not.toHaveCount(1)
    await page.locator('button').first().click()
    await page.waitForURL((url) => !url.pathname.startsWith('/select-branch'), { timeout: 10_000 })
  }
}

// The signed-in account's server-side preferred_language is the real source
// of truth for locale post-login (main.ts — deliberate, per Decision 0002:
// pre-login localStorage only controls the login screen itself). Setting
// localStorage before login has no effect once authenticated, so tests that
// need a specific post-login locale must drive the real LanguageSwitcher,
// which persists via PATCH /auth/me/preferences (auth.updatePreferredLanguage).
export async function switchLanguage(page: Page, locale: 'ar' | 'en'): Promise<void> {
  const current = await page.locator('html').getAttribute('lang')
  if (current === locale) return
  await page.locator('button[aria-haspopup="listbox"]').first().click()
  await page.locator('ul[role="listbox"] li[aria-selected="false"] button').first().click()
  await expect(page.locator('html')).toHaveAttribute('lang', locale)
}
