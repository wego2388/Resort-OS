import { expect, test, type Page } from '@playwright/test'

async function mockCashier(page: Page, locale: 'ar' | 'en') {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/auth/refresh') {
      return route.fulfill({ status: 200, json: { access_token: 'cashier-layout-token' } })
    }
    if (url.pathname === '/api/v1/auth/bootstrap') {
      return route.fulfill({
        status: 200,
        json: {
          contract_version: 1,
          user: {
            id: 8101,
            email: 'cashier-layout@example.invalid',
            username: 'cashier-layout',
            full_name: locale === 'ar' ? 'كاشير اختبار التجاوب' : 'Responsive Test Cashier',
            role: 'cashier',
            is_active: true,
            must_change_password: false,
            two_factor_enabled: false,
            preferred_language: locale,
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
          employee_id: 501,
        },
      })
    }
    if (url.pathname === '/api/v1/alerts') {
      return route.fulfill({ status: 200, json: { items: [], total: 0, page: 1, size: 50 } })
    }
    return route.fulfill({ status: 503, json: { detail: 'layout test' } })
  })
}

async function mockHrManager(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/auth/refresh') {
      return route.fulfill({ status: 200, json: { access_token: 'hr-layout-token' } })
    }
    if (url.pathname === '/api/v1/auth/bootstrap') {
      return route.fulfill({
        status: 200,
        json: {
          contract_version: 1,
          user: {
            id: 8201,
            email: 'hr-layout@example.invalid',
            username: 'hr-layout',
            full_name: 'مدير موارد بشرية للاختبار',
            role: 'hr_manager',
            is_active: true,
            must_change_password: false,
            two_factor_enabled: false,
            preferred_language: 'ar',
          },
          branches: [{ id: 1, code: 'ELK', name: 'El Kheima Beach Resort', name_ar: 'منتجع الخيمة بيتش', timezone: 'Africa/Cairo', is_default: true }],
          active_branch_id: 1,
          default_branch_id: 1,
          allowed_branch_ids: [1],
          requires_branch_selection: false,
          effective_permissions: [],
          employee_id: 601,
        },
      })
    }
    if (url.pathname === '/api/v1/hr/employees') {
      return route.fulfill({
        status: 200,
        json: {
          total: 1,
          page: 1,
          size: 100,
          items: [{
            id: 601,
            branch_id: 1,
            employee_code: 'EMP-0601',
            full_name: 'موظف باسم عربي طويل لاختبار بطاقة الهاتف',
            position: 'خدمة العملاء والزيارات',
            department: 'الملكية الجزئية',
            basic_salary: 6500,
            status: 'active',
            user_id: 9001,
            phone: '01012345678',
          }],
        },
      })
    }
    return route.fulfill({ status: 503, json: { detail: 'layout test' } })
  })
}

for (const locale of ['ar', 'en'] as const) {
  for (const viewport of [
    { width: 320, height: 568 },
    { width: 390, height: 844 },
    { width: 768, height: 1024 },
  ]) {
    test(`cashier header fits ${viewport.width}x${viewport.height} ${locale}`, async ({ page }) => {
      await page.setViewportSize(viewport)
      await mockCashier(page, locale)
      await page.goto('/pos/dining')
      await expect(page.locator('.field-shell > header')).toBeVisible()
      await expect(page.locator('html')).toHaveAttribute('dir', locale === 'ar' ? 'rtl' : 'ltr')

      const layout = await page.evaluate(() => {
        const header = document.querySelector<HTMLElement>('.field-shell > header')!
        const visibleButtons = [...header.querySelectorAll<HTMLElement>('button')]
          .filter((button) => {
            const style = getComputedStyle(button)
            const rect = button.getBoundingClientRect()
            return style.display !== 'none' && rect.width > 0 && rect.height > 0
          })
          .map((button) => {
            const rect = button.getBoundingClientRect()
            return { left: rect.left, right: rect.right }
          })
        return {
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
          visibleButtons,
        }
      })
      expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth + 1)
      for (const bounds of layout.visibleButtons) {
        expect(bounds.left).toBeGreaterThanOrEqual(-1)
        expect(bounds.right).toBeLessThanOrEqual(viewport.width + 1)
      }
    })
  }
}

test('public timeshare portal is usable at 320px without authentication', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 })
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/v1/auth/refresh') {
      return route.fulfill({ status: 401, json: { detail: 'signed out' } })
    }
    if (url.pathname === '/api/v1/timeshare/public/portal-config') {
      return route.fulfill({
        status: 200,
        json: {
          resort_name: 'El Kheima Beach Resort',
          terms_version: 'terms-test',
          booking_rules_version: 'rules-test',
        },
      })
    }
    return route.fulfill({ status: 503, json: { detail: 'layout test' } })
  })
  await page.goto('/timeshare-portal')
  await expect(page.getByRole('heading', { name: /بوابة عملاء/ })).toBeVisible()
  await expect(page.getByLabel(/رقم العقد/)).toBeVisible()
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
})

test('HR employee table becomes labeled cards on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockHrManager(page)
  await page.goto('/admin/hr')
  const table = page.locator('table.responsive-card-table')
  await expect(table).toBeVisible()
  await expect(table.locator('thead')).toHaveCSS('display', 'none')
  const row = table.locator('tbody tr').first()
  await expect(row).toContainText('موظف باسم عربي طويل')
  const geometry = await row.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    const beforeScroll = document.documentElement.scrollLeft
    window.scrollBy(2000, 0)
    const afterScroll = document.documentElement.scrollLeft
    return {
      left: rect.left,
      right: rect.right,
      viewportWidth: document.documentElement.clientWidth,
      beforeScroll,
      afterScroll,
      labels: [...element.querySelectorAll('td[data-label]')].map(cell => cell.getAttribute('data-label')),
    }
  })
  expect(geometry.left).toBeGreaterThanOrEqual(-1)
  expect(geometry.right).toBeLessThanOrEqual(geometry.viewportWidth + 1)
  expect(geometry.afterScroll).toBe(geometry.beforeScroll)
  expect(geometry.labels.length).toBeGreaterThanOrEqual(5)
})
