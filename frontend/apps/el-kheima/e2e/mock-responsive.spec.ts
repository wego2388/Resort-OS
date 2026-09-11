import { expect, test, type Page } from '@playwright/test'

async function mockCashier(
  page: Page,
  locale: 'ar' | 'en',
  role: 'cashier' | 'waiter' = 'cashier',
) {
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
            email: `${role}-layout@example.invalid`,
            username: `${role}-layout`,
            full_name: locale === 'ar' ? 'كاشير اختبار التجاوب' : 'Responsive Test Cashier',
            role,
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
    if (url.pathname === '/api/v1/finance/shifts/current') {
      return route.fulfill({ status: 404, json: { detail: 'no open shift in layout fixture' } })
    }
    if (url.pathname === '/api/v1/dining/outlets') {
      return route.fulfill({ status: 200, json: [{
        id: 11, name: 'Beach Restaurant', name_ar: 'مطعم الشاطئ',
        outlet_type: 'restaurant', is_active: true,
      }] })
    }
    if (url.pathname === '/api/v1/dining/outlets/11/categories') {
      return route.fulfill({ status: 200, json: [
        { id: 21, name: 'Grill', name_ar: 'مشويات', sort_order: 1 },
        { id: 22, name: 'Drinks', name_ar: 'مشروبات', sort_order: 2 },
      ] })
    }
    if (url.pathname === '/api/v1/dining/outlets/11/items') {
      return route.fulfill({ status: 200, json: [
        { id: 31, name: 'Grilled chicken', name_ar: 'فراخ مشوية', price: '220.00', is_available: true, category_id: 21, station: 'grill', variants: [], extra_groups: [] },
        { id: 32, name: 'Fresh juice', name_ar: 'عصير فريش', price: '90.00', is_available: true, category_id: 22, station: 'bar', variants: [], extra_groups: [] },
        { id: 33, name: 'Seafood pasta', name_ar: 'مكرونة سي فود', price: '260.00', is_available: true, category_id: 21, station: 'hot', variants: [], extra_groups: [] },
      ] })
    }
    if (url.pathname === '/api/v1/dining/branches/1/tables') {
      return route.fulfill({ status: 200, json: [
        {
          id: 41, table_number: '7', status: 'occupied', capacity: 4, section: locale === 'ar' ? 'البحر' : 'Sea',
          active_order_id: 51, active_order_number: 'ORD-GUEST-51', active_order_total: '310.00', active_covers: 2,
          occupied_at: '2026-09-11T08:00:00Z', order_status: 'open', active_order_outlet_id: 11,
          active_order_guest_name: locale === 'ar' ? 'ضيف الطاولة' : 'Table guest', active_order_guest_phone: null,
          active_order_source: 'guest_qr',
        },
        {
          id: 42, table_number: '8', status: 'available', capacity: 4, section: locale === 'ar' ? 'البحر' : 'Sea',
          active_order_id: null, active_order_number: null, active_order_total: null, active_covers: null,
          occupied_at: null, order_status: null, active_order_outlet_id: null,
          active_order_guest_name: null, active_order_guest_phone: null, active_order_source: null,
        },
      ] })
    }
    if (url.pathname === '/api/v1/dining/orders') {
      const all = [{
        id: 51, outlet_id: 11, order_number: 'ORD-GUEST-51', status: 'open', table_id: 41,
        order_type: 'dine_in', total: '310.00', guests_count: 2, created_at: '2026-09-11T08:00:00Z',
        source: 'guest_qr', guest_name: locale === 'ar' ? 'ضيف الطاولة' : 'Table guest', guest_phone: null,
        beach_location_id: null, beach_location_label: null, b2b_contract_id: null, hotel_name: null,
      }]
      const status = url.searchParams.get('status')
      const items = all.filter(order => !status || order.status === status)
      return route.fulfill({ status: 200, json: { items, total: items.length, page: 1, size: 100 } })
    }
    if (url.pathname === '/api/v1/dining/orders/51') {
      return route.fulfill({ status: 200, json: {
        id: 51, branch_id: 1, outlet_id: 11, order_number: 'ORD-GUEST-51', status: 'open',
        order_type: 'dine_in', table_id: 41, created_at: '2026-09-11T08:00:00Z', source: 'guest_qr',
        guests_count: 2, payment_method: null, subtotal: '270.00', vat_amount: '40.00',
        service_charge: '0.00', delivery_fee: '0.00', discount_amount: '0.00',
        refunded_amount: '0.00', total: '310.00', customer_id: null,
        guest_name: locale === 'ar' ? 'ضيف الطاولة' : 'Table guest', guest_phone: null,
        beach_location_id: null, beach_location_label: null, b2b_contract_id: null, hotel_name: null,
        waiter_id: null, waiter_name: null, notes: null,
        items: [{
          id: 501, item_id: 31, name: 'Grilled chicken', name_ar: 'فراخ مشوية',
          unit_price: '270.00', listed_unit_price: null, quantity: 1, notes: null,
          status: 'pending', extras: [], voided_reason: null,
        }],
      } })
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

for (const viewport of [
  { width: 1340, height: 800, label: 'native-landscape' },
  { width: 894, height: 533, label: 'android-logical-landscape' },
]) {
  test(`Dining POS is touch-usable on Lenovo Tab One ${viewport.label}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await mockCashier(page, 'ar')
    await page.goto('/pos/dining')

    await expect(page.getByText('طلب ضيف').first()).toBeVisible()
    await page.getByRole('button', { name: 'طلب جديد', exact: true }).click()
    await expect(page.getByRole('button', { name: /فراخ مشوية/ })).toBeVisible()

    const geometry = await page.evaluate(() => {
      const selectors = [
        '.pos-command-bar button',
        '.pos-category-button',
        '.pos-menu-toolbar button',
        '.pos-products-grid button',
      ]
      const targets = selectors.flatMap(selector =>
        [...document.querySelectorAll<HTMLElement>(selector)]
          .filter(el => {
            const rect = el.getBoundingClientRect()
            return rect.width > 0 && rect.height > 0
          })
          .map(el => {
            const rect = el.getBoundingClientRect()
            return { width: rect.width, height: rect.height }
          }),
      )
      return {
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        targets,
        productAreaHeight: document.querySelector<HTMLElement>('.pos-products-grid')?.getBoundingClientRect().height ?? 0,
      }
    })

    expect(geometry.overflow).toBeLessThanOrEqual(1)
    expect(geometry.targets.length).toBeGreaterThan(8)
    for (const target of geometry.targets) expect(target.height).toBeGreaterThanOrEqual(44)
    expect(geometry.productAreaHeight).toBeGreaterThanOrEqual(130)
  })
}

test('Dining POS keeps the cart thumb-reachable in Lenovo Tab One portrait', async ({ page }) => {
  await page.setViewportSize({ width: 533, height: 894 })
  await mockCashier(page, 'ar')
  await page.goto('/pos/dining')
  await page.getByRole('button', { name: 'طلب جديد', exact: true }).click()
  await page.getByRole('button', { name: /فراخ مشوية/ }).click()

  const cartButton = page.locator('.pos-mobile-cart')
  await expect(cartButton).toBeVisible()
  const bounds = await cartButton.evaluate(element => {
    const rect = element.getBoundingClientRect()
    return { bottom: rect.bottom, height: rect.height, viewport: window.innerHeight }
  })
  expect(bounds.height).toBeGreaterThanOrEqual(56)
  expect(bounds.viewport - bounds.bottom).toBeLessThanOrEqual(24)
})

test('Dining POS raises a live multisensory alert for a new QR guest order', async ({ page }) => {
  await page.setViewportSize({ width: 894, height: 533 })
  await page.addInitScript(() => {
    const sockets: Array<{ url: string; onmessage: ((event: { data: string }) => void) | null }> = []
    ;(window as any).__alertSignals = { tones: 0, vibrations: [] as unknown[] }

    class MockWebSocket {
      static OPEN = 1
      static CONNECTING = 0
      static CLOSING = 2
      static CLOSED = 3
      url: string
      readyState = MockWebSocket.OPEN
      onopen: (() => void) | null = null
      onclose: (() => void) | null = null
      onerror: (() => void) | null = null
      onmessage: ((event: { data: string }) => void) | null = null

      constructor(url: string) {
        this.url = url
        sockets.push(this)
        setTimeout(() => this.onopen?.(), 0)
      }

      send() {}
      close() { this.readyState = MockWebSocket.CLOSED }
    }

    class MockAudioContext {
      currentTime = 0
      destination = {}
      createOscillator() {
        ;(window as any).__alertSignals.tones += 1
        return {
          type: 'sine',
          frequency: { setValueAtTime() {} },
          connect() {},
          start() {},
          stop() {},
        }
      }
      createGain() {
        return {
          gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} },
          connect() {},
        }
      }
    }

    ;(window as any).WebSocket = MockWebSocket
    ;(window as any).AudioContext = MockAudioContext
    Object.defineProperty(navigator, 'vibrate', {
      configurable: true,
      value: (pattern: unknown) => {
        ;(window as any).__alertSignals.vibrations.push(pattern)
        return true
      },
    })
    ;(window as any).__emitGuestOrder = (order: unknown) => {
      const socket = sockets.find(item => item.url.includes('/dining/ws/tables/'))
      socket?.onmessage?.({ data: JSON.stringify({ type: 'guest_order_created', order }) })
    }
  })
  await mockCashier(page, 'ar')
  await page.goto('/pos/dining')
  await expect(page.getByText('طلب ضيف').first()).toBeVisible()
  await page.evaluate(() => {
    ;(window as any).__emitGuestOrder({
      id: 77,
      order_number: 'ORD-QR-77',
      order_type: 'dine_in',
      table_id: 42,
      location_type: 'dining_table',
      location_label: '8',
      items_count: 3,
      total: '570.00',
    })
  })

  const banner = page.getByTestId('guest-order-live-banner')
  await expect(banner).toContainText('طلب جديد وصل من الضيف')
  await expect(banner).toContainText('طاولة 8')
  await expect(banner).toContainText('3 صنف')
  expect(await page.evaluate(() => (window as any).__alertSignals)).toEqual({
    tones: 1,
    vibrations: [[120, 70, 120]],
  })

  await banner.getByRole('button', { name: 'افتح الطلب' }).click()
  await expect(banner).toBeHidden()
  await expect(page.getByText('تفاصيل الطلب').first()).toBeVisible()
})

test('Cashier sees guest-order ownership and add-item controls, then enters split tender directly', async ({ page }) => {
  await page.setViewportSize({ width: 894, height: 533 })
  await mockCashier(page, 'ar')
  await page.goto('/pos/dining')
  await page.getByRole('button', { name: /الطلبات النشطة/ }).click()
  await page.getByRole('button', { name: /ORD-GUEST-51/ }).click()

  await expect(page.getByText('هذا الطلب أرسله الضيف عبر QR')).toBeVisible()
  await expect(page.getByRole('button', { name: /أتولى المتابعة/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /إضافة أصناف للفاتورة/ })).toBeVisible()

  await page.getByRole('button', { name: /تقسيم الدفع/ }).click()
  await expect(page.getByRole('tab', { name: 'تقسيم الدفع' })).toHaveAttribute('aria-selected', 'true')
})

test('Waiter uses the same guest-order workspace without receiving cashier settlement controls', async ({ page }) => {
  await page.setViewportSize({ width: 894, height: 533 })
  await mockCashier(page, 'ar', 'waiter')
  await page.goto('/pos/dining')
  await page.getByRole('button', { name: /الطلبات النشطة/ }).click()
  await page.getByRole('button', { name: /ORD-GUEST-51/ }).click()

  await expect(page.getByRole('button', { name: /أتولى المتابعة/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /إضافة أصناف للفاتورة/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /تحصيل الدفع/ })).toHaveCount(0)
  await expect(page.getByRole('button', { name: /تقسيم الدفع/ })).toHaveCount(0)
})

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
