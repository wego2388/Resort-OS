/**
 * Gate 3C — locale-aware formatting utilities.
 *
 * The load-bearing invariant (Decision 0002 §6): currency is a required
 * argument and is NEVER derived from the display language. Switching ar↔en
 * changes only formatting, never the currency or the underlying value.
 */
import { describe, it, expect } from 'vitest'
import { formatMoney, formatNumber, formatDate, formatTime } from '@resort-os/core'

describe('formatMoney — currency independent of language', () => {
  it('keeps the same currency (EGP) in both ar and en', () => {
    const ar = formatMoney(1234.5, 'EGP', 'ar')
    const en = formatMoney(1234.5, 'EGP', 'en')
    // Different formatting is allowed; the currency and the numeric value are not.
    expect(ar).toMatch(/1[,.]?234/)
    expect(en).toMatch(/1,234\.50/)
    expect(en).toMatch(/EGP|E£|£/)
  })

  it('renders a non-EGP currency exactly as asked, regardless of locale', () => {
    expect(formatMoney(10, 'USD', 'ar')).toMatch(/10\.00/)
    expect(formatMoney(10, 'USD', 'en')).toMatch(/\$?\s?10\.00/)
  })

  it('always shows two fraction digits (deterministic money display)', () => {
    expect(formatMoney(5, 'EGP', 'en')).toMatch(/5\.00/)
    expect(formatMoney(5.1, 'EGP', 'en')).toMatch(/5\.10/)
  })

  it('returns a dash for nullish/invalid amounts', () => {
    expect(formatMoney(null, 'EGP', 'en')).toBe('—')
    expect(formatMoney('abc', 'EGP', 'en')).toBe('—')
  })
})

describe('formatNumber — Latin digits for operational clarity', () => {
  it('uses Western digits even in Arabic', () => {
    expect(formatNumber(2026, 'ar')).toMatch(/2026|2,026/)
  })
  it('returns a dash for nullish values', () => {
    expect(formatNumber(undefined, 'en')).toBe('—')
  })
})

describe('formatDate / formatTime', () => {
  it('formats a valid date without throwing in both locales', () => {
    const d = new Date('2026-07-19T08:30:00Z')
    expect(formatDate(d, 'ar')).not.toBe('—')
    expect(formatDate(d, 'en')).not.toBe('—')
  })
  it('returns a dash for invalid input', () => {
    expect(formatDate('not-a-date', 'en')).toBe('—')
    expect(formatTime('', 'en')).toBe('—')
  })

  it('treats timezone-less API timestamps as UTC and displays resort time', () => {
    const displayed = formatTime('2026-01-19T08:30:00', 'en', {
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
    // Cairo is UTC+2 in January: 08:30 UTC → 10:30 resort time, regardless
    // of the workstation/browser timezone running this test.
    expect(displayed).toContain('10:30')
  })
})
