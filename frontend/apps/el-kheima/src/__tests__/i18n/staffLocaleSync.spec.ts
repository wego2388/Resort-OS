/**
 * Authenticated locale reconciliation on a shared staff terminal.
 *
 * The signed-in user's server preference controls the active session, while
 * the separate pre-login preference remains unchanged for the next logout.
 * Replacing the auth user (login/refresh/PIN switch) must immediately apply
 * the replacement user's language instead of retaining the former operator's.
 */
import { defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useAuthStore } from '@resort-os/core'
import { staffLocale } from '@resort-os/core/i18n/staff'
import { useStaffLocaleSync } from '../../composables/useStaffLocaleSync'

const SyncHost = defineComponent({
  setup() {
    useStaffLocaleSync()
    return () => null
  },
})

async function settleLocaleWatcher() {
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
}

beforeEach(async () => {
  setActivePinia(createPinia())
  await staffLocale.setLocale('ar')
})

describe('useStaffLocaleSync', () => {
  it('applies each authenticated operator without changing pre-login storage', async () => {
    const auth = useAuthStore()
    mount(SyncHost)

    auth.user = { id: 1, role: 'cashier', preferred_language: 'en' } as any
    await settleLocaleWatcher()
    expect(staffLocale.current()).toBe('en')
    expect(localStorage.getItem('resort-os:staff:locale')).toBe('ar')

    // PIN switch / second login replaces the user object. The next employee's
    // server preference wins immediately; the first employee never leaks.
    auth.user = { id: 2, role: 'waiter', preferred_language: 'ar' } as any
    await settleLocaleWatcher()
    expect(staffLocale.current()).toBe('ar')
    expect(localStorage.getItem('resort-os:staff:locale')).toBe('ar')

    // Identity is part of the watch source: even when two consecutive users
    // prefer the same language, replacing the operator reasserts that server
    // preference over any temporary local preview/drift.
    await staffLocale.setLocale('en', { persist: false })
    auth.user = { id: 3, role: 'waiter', preferred_language: 'ar' } as any
    await settleLocaleWatcher()
    expect(staffLocale.current()).toBe('ar')
  })
})
