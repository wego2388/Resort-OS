import { expect, test, type Page } from '@playwright/test'

const ROUTES = ['now', 'performance', 'sales', 'expenses', 'shifts', 'hr']

async function mockAuthenticatedOwner(page: Page, withNowData = false) {
  page.on('pageerror', error => console.error('Owner page error:', error.message))
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/auth/refresh') {
      return route.fulfill({ status: 200, json: { access_token: 'owner-layout-test-token' } })
    }
    if (url.pathname === '/api/v1/auth/bootstrap') {
      return route.fulfill({
        status: 200,
        json: {
          contract_version: 1,
          user: {
            id: 7001,
            email: 'owner-layout@example.invalid',
            username: 'owner-layout',
            full_name: 'Owner Layout Test',
            role: 'owner',
            is_active: true,
            must_change_password: false,
            two_factor_enabled: true,
          },
          branches: [{
            id: 1,
            code: 'ELK',
            name: 'El Kheima Beach Resort',
            name_ar: 'منتجع الخيمة بيتش',
            timezone: 'Africa/Cairo',
            is_default: true,
          }],
          active_branch_id: 1,
          default_branch_id: 1,
          allowed_branch_ids: [1],
          requires_branch_selection: false,
          effective_permissions: [],
          employee_id: null,
        },
      })
    }
    if (withNowData && url.pathname === '/api/v1/owner/now/history') {
      return route.fulfill({
        status: 200,
        json: {
          days: [
            { day: '2026-08-13', revenue: '98000', expense: '42000', cash_in_drawers: '0', occupancy_pct: '72', beach_utilisation_pct: '68', is_provisional: false },
            { day: '2026-08-14', revenue: '125000', expense: '48600', cash_in_drawers: '32800', occupancy_pct: '86', beach_utilisation_pct: '91', is_provisional: true },
          ],
          computed_at: new Date().toISOString(),
        },
      })
    }
    if (withNowData && url.pathname === '/api/v1/owner/now') {
      return route.fulfill({
        status: 200,
        json: {
          revenue_today: '125000',
          cash_in_drawers: '32800',
          expense_today: '48600',
          b2b_receivables: [{ contract_id: 1, hotel_name: 'شركة سياحة باسم طويل لاختبار العرض', outstanding: '75000', is_overdue: true, credit_limit: '100000', last_settled_at: null }],
          b2b_total_outstanding: '75000',
          timeshare_receivables: [{ contract_id: 22, total_overdue: '12000', installment_count: 2 }],
          timeshare_total_overdue: '12000',
          occupancy: { occupied_rooms: 43, total_rooms: 50, occupancy_pct: '86', computed_at: new Date().toISOString() },
          beach_capacity: { capacity_used: 273, capacity_max: 300, utilisation_pct: '91', inventory_date: '2026-08-14', note: 'السعة تقترب من الحد التشغيلي.' },
          period: { date_from: '2026-08-14', date_to: '2026-08-14', is_provisional: true, computed_at: new Date().toISOString() },
          open_shift_count: 3,
          credit_account_outstanding: '18500',
          credit_account_count: 1,
        },
      })
    }
    if (withNowData && url.pathname === '/api/v1/owner/credit-receivables') {
      return route.fulfill({
        status: 200,
        json: {
          branch_id: 1,
          accounts: [{ account_id: 8, holder_type: 'customer', holder_name: 'عميل بحساب آجل طويل الاسم', current_balance: '18500', credit_limit: '25000', status: 'active', last_charge_at: null, days_since_last_charge: 7, is_overdue: true }],
          total_outstanding: '18500',
          overdue_count: 1,
          computed_at: new Date().toISOString(),
        },
      })
    }
    if (withNowData && url.pathname === '/api/v1/owner/exceptions') {
      return route.fulfill({
        status: 200,
        json: {
          critical_count: 1,
          attention_count: 1,
          watch_count: 0,
          exceptions: [
            { exception_id: 'shift:1', tier: 'critical', category: 'shift_variance', title: 'فرق كاش يحتاج مراجعة', detail: 'يوجد فرق في وردية الكاشير المسائية.', entity_id: 4, entity_name: 'موظف تجريبي', impact: '950', confidence: '1', status: 'realized', source: 'cashier_shifts', score: '950' },
            { exception_id: 'b2b:1', tier: 'attention', category: 'b2b_overdue', title: 'ذمة فندق متأخرة', detail: 'تجاوز العقد تاريخ السداد المسجل.', entity_id: 1, entity_name: 'شركة سياحة', impact: '0', confidence: '1', status: 'realized', source: 'b2b_contracts', score: '0' },
          ],
          computed_at: new Date().toISOString(),
        },
      })
    }
    if (withNowData && url.pathname === '/api/v1/owner/watchlist') {
      return route.fulfill({ status: 200, json: [] })
    }
    // Error states are deliberate here: layout safety must not depend on a
    // specific production data shape, and every route still mounts its real
    // screen/component tree.
    return route.fulfill({ status: 503, json: { detail: 'layout test' } })
  })
}

test.describe('owner decision view', () => {
  test.use({ viewport: { width: 412, height: 915 }, timezoneId: 'Africa/Cairo' })

  test('puts decisions before details on a large Samsung-class phone', async ({ page }) => {
    await mockAuthenticatedOwner(page, true)
    await page.goto('/now')

    await expect(page.getByText('El Kheima Beach Resort')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'تدخل مطلوب الآن' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'حركة اليوم' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'مبالغ تحتاج تحصيل' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'التشغيل الآن' })).toBeVisible()

    const order = await page.evaluate(() => [
      document.querySelector('#operating-state-title')?.getBoundingClientRect().top,
      document.querySelector('#today-money-title')?.getBoundingClientRect().top,
    ])
    expect(order[0]).toBeLessThan(order[1]!)

    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(1)

    const navTargets = await page.locator('.bottom-nav-item').evaluateAll(items =>
      items.map(item => item.getBoundingClientRect().height),
    )
    expect(navTargets.every(height => height >= 56)).toBeTruthy()
  })

  test('date presets use the Cairo business day', async ({ page }) => {
    const salesRequests: string[] = []
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/v1/owner/sales') salesRequests.push(request.url())
    })
    await mockAuthenticatedOwner(page)
    await page.goto('/sales')
    await page.getByRole('button', { name: 'اليوم' }).click()
    await page.getByRole('button', { name: 'هذا الشهر' }).click()

    const expectedStart = await page.evaluate(() => {
      const date = new Date()
      const month = String(date.getMonth() + 1).padStart(2, '0')
      return `${date.getFullYear()}-${month}-01`
    })
    await expect.poll(() => salesRequests.some(raw =>
      new URL(raw).searchParams.get('date_from') === expectedStart,
    )).toBeTruthy()
  })
})

for (const viewport of [
  { width: 320, height: 568 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1280, height: 800 },
]) {
  test.describe(`${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport })

    test('all owner destinations stay inside the viewport', async ({ page }) => {
      await mockAuthenticatedOwner(page)
      await page.goto('/now')

      for (const routeName of ROUTES) {
        await page.goto(`/${routeName}`)
        await expect(page).toHaveURL(new RegExp(`/${routeName}$`))
        const overflow = await page.evaluate(() => ({
          document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          body: document.body.scrollWidth - document.body.clientWidth,
        }))
        expect(overflow.document).toBeLessThanOrEqual(1)
        expect(overflow.body).toBeLessThanOrEqual(1)
      }
    })

    test('navigation never covers the owner content region', async ({ page }) => {
      await mockAuthenticatedOwner(page)
      await page.goto('/now')
      const nav = page.getByRole('navigation', { name: 'التنقل الرئيسي' })
      const main = page.locator('main.owner-main')
      await expect(nav).toBeVisible()

      const geometry = await page.evaluate(() => {
        const navElement = document.querySelector<HTMLElement>('.bottom-nav')!
        const mainElement = document.querySelector<HTMLElement>('.owner-main')!
        const navRect = navElement.getBoundingClientRect()
        const mainRect = mainElement.getBoundingClientRect()
        const mainStyle = getComputedStyle(mainElement)
        return {
          navWidth: navRect.width,
          navHeight: navRect.height,
          mainWidth: mainRect.width,
          paddingBottom: parseFloat(mainStyle.paddingBottom),
          marginInlineEnd: parseFloat(mainStyle.marginInlineEnd),
        }
      })

      if (viewport.width < 1024) {
        expect(geometry.paddingBottom).toBeGreaterThanOrEqual(geometry.navHeight - 1)
      } else {
        expect(geometry.navWidth).toBeGreaterThanOrEqual(100)
        expect(geometry.navHeight).toBeGreaterThan(viewport.height / 2)
        expect(geometry.marginInlineEnd).toBeGreaterThanOrEqual(100)
        expect(geometry.mainWidth).toBeLessThan(viewport.width)
      }
    })
  })
}
