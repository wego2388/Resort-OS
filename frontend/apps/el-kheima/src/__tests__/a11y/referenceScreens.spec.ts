/**
 * Gate 3C — accessibility smoke for reference screens.
 *
 * Renders the migrated Profile reference screen in ar/RTL and en/LTR and runs
 * axe-core, asserting no critical/serious violations and no unresolved
 * translation keys ("backoffice.profile.*" must render as real copy, not the
 * raw key). Color-contrast is disabled because jsdom cannot compute layout
 * colors; that is covered by human/browser review, noted in the report.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import axe from 'axe-core'
import { api } from '@resort-os/core'
import { staffI18n, staffLocale } from '@resort-os/core/i18n/staff'
import ProfileView from '../../views/portal/ProfileView.vue'

const FAKE_PROFILE = {
  id: 1,
  employee_code: 'EMP-001',
  full_name: 'Mona Ali',
  email: 'mona@example.com',
  phone: '+201000000000',
  position: 'Cashier',
  department: 'Front Office',
  hire_date: '2024-01-15T00:00:00Z',
}

const AXE_OPTIONS: axe.RunOptions = {
  rules: { 'color-contrast': { enabled: false } },
  resultTypes: ['violations'],
}

async function renderProfileIn(locale: string) {
  await staffLocale.setLocale(locale)
  const wrapper = mount(ProfileView, {
    global: { plugins: [staffI18n] },
    attachTo: document.body,
  })
  // Let onMounted's api.get resolve and the DOM settle.
  await new Promise((r) => setTimeout(r, 0))
  await wrapper.vm.$nextTick()
  return wrapper
}

async function criticalViolations(el: HTMLElement) {
  const results = await axe.run(el, AXE_OPTIONS)
  return results.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious')
}

beforeEach(() => {
  vi.spyOn(api, 'get').mockResolvedValue({ data: FAKE_PROFILE } as any)
})
afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe.each([
  ['ar', 'rtl'],
  ['en', 'ltr'],
])('ProfileView in %s (%s)', (locale, dir) => {
  it(`sets the document direction to ${dir}`, async () => {
    await renderProfileIn(locale)
    expect(document.documentElement.dir).toBe(dir)
    expect(document.documentElement.lang).toBe(locale)
  })

  it('renders real translated copy, not raw keys', async () => {
    const wrapper = await renderProfileIn(locale)
    const text = wrapper.text()
    expect(text).not.toMatch(/backoffice\.profile\./)
    expect(text).toContain('Mona Ali')
  })

  it('has no critical/serious axe violations', async () => {
    const wrapper = await renderProfileIn(locale)
    const violations = await criticalViolations(wrapper.element as HTMLElement)
    if (violations.length) {
      console.error(violations.map((v) => `${v.id}: ${v.help}`).join('\n'))
    }
    expect(violations).toHaveLength(0)
  })
})
