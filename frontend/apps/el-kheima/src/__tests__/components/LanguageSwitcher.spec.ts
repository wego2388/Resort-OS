/**
 * Gate 3C — LanguageSwitcher: ar/en only, pre-login vs signed-in persistence,
 * failure rollback, and loading/disabled behavior.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '@resort-os/core'
import { staffI18n, staffLocale } from '@resort-os/core/i18n/staff'
import { useToast } from '@resort-os/ui'
import LanguageSwitcher from '../../components/LanguageSwitcher.vue'

function mountSwitcher() {
  return mount(LanguageSwitcher, {
    global: { plugins: [staffI18n] },
  })
}

beforeEach(async () => {
  setActivePinia(createPinia())
  await staffLocale.setLocale('ar')
  // Drain any toasts left by a previous test.
  useToast().toasts.value.splice(0)
})

describe('LanguageSwitcher — options', () => {
  it('offers exactly the two staff locales (no ru/it)', async () => {
    const wrapper = mountSwitcher()
    await wrapper.find('button').trigger('click')
    const text = wrapper.text()
    expect(text).toContain('العربية')
    expect(text).toContain('English')
    expect(text).not.toContain('Русский')
    expect(text).not.toContain('Italiano')
  })
})

describe('LanguageSwitcher — pre-login (unauthenticated)', () => {
  it('applies + persists locally without a server call', async () => {
    const auth = useAuthStore()
    const spy = vi.spyOn(auth, 'updatePreferredLanguage')
    const wrapper = mountSwitcher()

    await wrapper.find('button').trigger('click')
    const btns = wrapper.findAll('button'); await btns[btns.length - 1].trigger('click') // "English"
    await Promise.resolve()

    expect(spy).not.toHaveBeenCalled()
    expect(staffLocale.current()).toBe('en')
    expect(localStorage.getItem('resort-os:staff:locale')).toBe('en')
  })
})

describe('LanguageSwitcher — signed in', () => {
  it('persists the choice on the server first', async () => {
    const auth = useAuthStore()
    auth.token = 'test-token'
    auth.user = { id: 1, role: 'cashier', preferred_language: 'ar' } as any
    const spy = vi.spyOn(auth, 'updatePreferredLanguage').mockResolvedValue('en')

    const wrapper = mountSwitcher()
    await wrapper.find('button').trigger('click')
    const btns = wrapper.findAll('button'); await btns[btns.length - 1].trigger('click')
    await new Promise((r) => setTimeout(r, 0))

    expect(spy).toHaveBeenCalledWith('en')
    expect(staffLocale.current()).toBe('en')
    expect(localStorage.getItem('resort-os:staff:locale')).toBe('ar')
    expect(wrapper.text().toLowerCase()).toContain('en')
  })

  it('rolls back and surfaces an error when the server rejects', async () => {
    const auth = useAuthStore()
    auth.token = 'test-token'
    auth.user = { id: 1, role: 'cashier', preferred_language: 'ar' } as any
    vi.spyOn(auth, 'updatePreferredLanguage').mockRejectedValue(new Error('boom'))

    const wrapper = mountSwitcher()
    await wrapper.find('button').trigger('click')
    const btns = wrapper.findAll('button'); await btns[btns.length - 1].trigger('click')
    await new Promise((r) => setTimeout(r, 0))

    // The compact label still reads the previous locale (no false success)…
    expect(wrapper.text().toLowerCase()).toContain('ar')
    // …and an error toast was raised.
    const toasts = useToast().toasts.value
    expect(toasts.some((t) => t.type === 'error')).toBe(true)
  })

  it('reacts when login/refresh/PIN switch applies another user locale', async () => {
    const wrapper = mountSwitcher()
    expect(wrapper.text().toLowerCase()).toContain('ar')
    await staffLocale.setLocale('en')
    await wrapper.vm.$nextTick()
    expect(wrapper.text().toLowerCase()).toContain('en')
  })

  it('disables the trigger while the server preference is being saved', async () => {
    const auth = useAuthStore()
    auth.token = 'test-token'
    auth.user = { id: 1, role: 'cashier', preferred_language: 'ar' } as any
    let resolveSave!: (value: string) => void
    vi.spyOn(auth, 'updatePreferredLanguage').mockImplementation(
      () => new Promise((resolve) => { resolveSave = resolve }),
    )

    const wrapper = mountSwitcher()
    await wrapper.find('button').trigger('click')
    const buttons = wrapper.findAll('button')
    await buttons[buttons.length - 1].trigger('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()

    resolveSave('en')
    await new Promise((r) => setTimeout(r, 0))
    expect(wrapper.find('button').attributes('disabled')).toBeUndefined()
  })
})

describe('LanguageSwitcher — accessibility', () => {
  it('exposes an expandable listbox trigger', async () => {
    const wrapper = mountSwitcher()
    const trigger = wrapper.find('button')
    expect(trigger.attributes('aria-haspopup')).toBe('listbox')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('[role="listbox"]').exists()).toBe(true)
  })
})
