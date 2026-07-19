/**
 * Gate 3C — locale controller: storage migration, namespacing, reconciliation,
 * fallback, and central `<html lang/dir>` application.
 */
import { describe, it, expect } from 'vitest'
import { createLocaleController } from '@resort-os/core'

const MESSAGES = { ar: { hi: 'مرحبا' }, en: { hi: 'Hi' } }

function makeStaffController() {
  return createLocaleController({
    messages: MESSAGES,
    allowList: ['ar', 'en'],
    storageKey: 'resort-os:staff:locale',
    fallback: 'ar',
    rtlLocales: ['ar'],
    legacyKeys: ['locale', 'kheima_lang', 'app_language'],
  })
}

describe('createLocaleController — initial resolution', () => {
  it('falls back to the configured default when nothing is stored', () => {
    const c = makeStaffController()
    expect(c.current()).toBe('ar')
    expect(localStorage.getItem('resort-os:staff:locale')).toBe('ar')
    expect(document.documentElement.lang).toBe('ar')
    expect(document.documentElement.dir).toBe('rtl')
  })

  it('reads the namespaced key when present', () => {
    localStorage.setItem('resort-os:staff:locale', 'en')
    const c = makeStaffController()
    expect(c.current()).toBe('en')
    expect(document.documentElement.dir).toBe('ltr')
  })

  it('ignores an unsupported stored value and uses the fallback', () => {
    localStorage.setItem('resort-os:staff:locale', 'ru')
    const c = makeStaffController()
    expect(c.current()).toBe('ar')
  })
})

describe('createLocaleController — one-time legacy migration', () => {
  it('adopts a legacy key once and persists under the namespaced key', () => {
    localStorage.setItem('kheima_lang', 'en')
    const c = makeStaffController()
    expect(c.current()).toBe('en')
    // Namespaced key now written…
    expect(localStorage.getItem('resort-os:staff:locale')).toBe('en')
    // …and the legacy key is NOT deleted (another app may own it) but is never
    // read again once the namespaced key exists.
    expect(localStorage.getItem('kheima_lang')).toBe('en')
  })

  it('prefers the namespaced key over any legacy key', () => {
    localStorage.setItem('resort-os:staff:locale', 'ar')
    localStorage.setItem('kheima_lang', 'en')
    const c = makeStaffController()
    expect(c.current()).toBe('ar')
  })

  it('skips a legacy value outside the staff allow-list', () => {
    localStorage.setItem('locale', 'ru') // public-only language
    const c = makeStaffController()
    expect(c.current()).toBe('ar')
  })

  it('marks migration complete even when no valid legacy value existed', () => {
    const firstBoot = makeStaffController()
    expect(firstBoot.current()).toBe('ar')
    expect(localStorage.getItem('resort-os:staff:locale')).toBe('ar')

    // A different app writes an old generic key later. Staff must not adopt
    // it because its one-time migration already completed on first boot.
    localStorage.setItem('locale', 'en')
    const laterBoot = makeStaffController()
    expect(laterBoot.current()).toBe('ar')
  })
})

describe('createLocaleController — setLocale', () => {
  it('switches locale, applies dir/lang, and persists namespaced only', async () => {
    const c = makeStaffController()
    await c.setLocale('en')
    expect(c.current()).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.dir).toBe('ltr')
    expect(localStorage.getItem('resort-os:staff:locale')).toBe('en')
    // Never writes the retired legacy keys.
    expect(localStorage.getItem('kheima_lang')).toBeNull()
    expect(localStorage.getItem('app_language')).toBeNull()
  })

  it('normalizes an unsupported target to the fallback', async () => {
    const c = makeStaffController()
    const applied = await c.setLocale('ru')
    expect(applied).toBe('ar')
    expect(c.current()).toBe('ar')
  })

  it('can apply an authenticated locale without overwriting pre-login storage', async () => {
    const c = makeStaffController()
    expect(localStorage.getItem('resort-os:staff:locale')).toBe('ar')
    await c.setLocale('en', { persist: false })
    expect(c.current()).toBe('en')
    expect(localStorage.getItem('resort-os:staff:locale')).toBe('ar')
  })

  it('drives RTL/LTR from the active locale without reload', async () => {
    const c = makeStaffController()
    expect(c.isRTL()).toBe(true)
    await c.setLocale('en')
    expect(c.isRTL()).toBe(false)
    await c.setLocale('ar')
    expect(c.isRTL()).toBe(true)
  })
})

describe('createLocaleController — public/staff isolation', () => {
  it('a staff switch never touches a differently-namespaced public key', async () => {
    localStorage.setItem('resort-os:public:locale', 'ru')
    const staff = makeStaffController()
    await staff.setLocale('en')
    expect(localStorage.getItem('resort-os:public:locale')).toBe('ru')
  })
})
