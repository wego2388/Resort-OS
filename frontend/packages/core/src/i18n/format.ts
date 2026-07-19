/**
 * Locale-aware display formatting (Gate 3A).
 *
 * Hard rule (Decision 0002 §6): locale changes *formatting only*. Currency is
 * NEVER derived from the language — `formatMoney` requires the currency code
 * from the caller (trusted resort config), so switching ar↔en can never change
 * which currency an amount is shown in, nor its stored value.
 *
 * Money uses fixed 2-fraction, deterministic decimal display with Western
 * (latn) digits regardless of locale, so finance/POS tables stay unambiguous
 * and column-aligned in both directions. Only the grouping/decimal separators
 * and symbol placement follow the locale.
 */

import { parseApiTimestamp } from '../utils/dates'

const BIDI_TAG: Record<string, string> = {
  ar: 'ar-EG',
  en: 'en-GB',
}

/** Single-resort operational timezone; mirrors the trusted backend setting. */
export const RESORT_TIME_ZONE = 'Africa/Cairo'

/** Map a staff locale code to a BCP-47 tag; unknown locales pass through. */
export function localeTag(locale: string): string {
  return BIDI_TAG[locale] ?? locale
}

function toNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : null
}

export function formatNumber(
  value: number | string | null | undefined,
  locale: string,
  options: Intl.NumberFormatOptions = {},
): string {
  const n = toNumber(value)
  if (n === null) return '—'
  return new Intl.NumberFormat(localeTag(locale), {
    numberingSystem: 'latn',
    ...options,
  }).format(n)
}

/**
 * Format a monetary amount. `currency` is REQUIRED and comes from trusted
 * resort configuration — never inferred from the display language.
 */
export function formatMoney(
  value: number | string | null | undefined,
  currency: string,
  locale: string,
): string {
  const n = toNumber(value)
  if (n === null) return '—'
  return new Intl.NumberFormat(localeTag(locale), {
    style: 'currency',
    currency,
    numberingSystem: 'latn',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n)
}

function toDate(value: Date | string | number | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null
  // Backend TIMESTAMP values are serialized without a zone even though they
  // represent UTC. Reuse the repository's established parser so centralized
  // formatting does not reintroduce the old +2/+3 hour timestamp bug.
  const d = value instanceof Date
    ? value
    : typeof value === 'string' && value.includes('T')
      ? parseApiTimestamp(value)
      : new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

export function formatDate(
  value: Date | string | number | null | undefined,
  locale: string,
  options: Intl.DateTimeFormatOptions = { year: 'numeric', month: 'short', day: 'numeric' },
): string {
  const d = toDate(value)
  if (d === null) return '—'
  return new Intl.DateTimeFormat(localeTag(locale), {
    numberingSystem: 'latn',
    timeZone: RESORT_TIME_ZONE,
    ...options,
  }).format(d)
}

export function formatTime(
  value: Date | string | number | null | undefined,
  locale: string,
  options: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' },
): string {
  const d = toDate(value)
  if (d === null) return '—'
  return new Intl.DateTimeFormat(localeTag(locale), {
    numberingSystem: 'latn',
    timeZone: RESORT_TIME_ZONE,
    ...options,
  }).format(d)
}

export function formatDateTime(
  value: Date | string | number | null | undefined,
  locale: string,
): string {
  const d = toDate(value)
  if (d === null) return '—'
  return new Intl.DateTimeFormat(localeTag(locale), {
    numberingSystem: 'latn',
    timeZone: RESORT_TIME_ZONE,
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d)
}
