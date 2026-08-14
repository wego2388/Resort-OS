import { expect, type Page } from '@playwright/test'

// manager@resortos.local — level 60, lands on /admin/dashboard, no 2FA
// enrollment gate (unlike super_admin/accountant) so it's a stable
// Playwright login target. Password matches scripts/status.sh's printed
// demo credentials (dev-only seed, never a real account).
export const MANAGER = { username: 'manager@resortos.local', password: 'Demo@123456' }
export const RECEPTIONIST = { username: 'reception@resortos.local', password: 'Demo@123456' }
// This legacy development identity is usable only after the single-branch
// reconciliation command assigns its El Kheima membership.
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

  // Single-branch accounts are auto-bound. Remaining on this route means the
  // account has zero or multiple memberships and reconciliation is required;
  // there is intentionally no user-facing branch choice.
  if (page.url().includes('/select-branch')) {
    await page.waitForURL((url) => !url.pathname.startsWith('/select-branch'), { timeout: 3_000 }).catch(() => undefined)
    expect(
      page.url(),
      `${creds.username} has an invalid single-branch membership configuration`,
    ).not.toContain('/select-branch')
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
