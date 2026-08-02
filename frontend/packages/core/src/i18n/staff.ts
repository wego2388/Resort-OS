/**
 * Staff-app locale runtime (Gate 3A / Decision 0002).
 *
 * The staff application (`frontend/apps/el-kheima`) is Arabic/English only.
 * This module owns the staff locale controller — a dedicated i18n instance
 * with the `ar/en` allow-list and its own namespaced storage key. It is fully
 * separate from the public app's shared singleton in `./index.ts` (which keeps
 * `ar/en/ru/it`); the two never share an allow-list or a storage key.
 *
 * Shared message catalogs are reused (same `ar.json`/`en.json` as the public
 * runtime) — only the *policy* differs, not the source of truth.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import ar from './locales/ar.json'
import en from './locales/en.json'
import { createLocaleController } from './controller'
import {
  formatDate,
  formatDateTime,
  formatMoney,
  formatNumber,
  formatTime,
} from './format'

export const STAFF_LOCALES = ['ar', 'en'] as const
export type StaffLocale = (typeof STAFF_LOCALES)[number]

/** Namespaced key — replaces the three legacy keys the old singleton wrote. */
export const STAFF_LOCALE_STORAGE_KEY = 'resort-os:staff:locale'

/** Legacy keys migrated once, then never read/written again by the staff app. */
export const STAFF_LEGACY_LOCALE_KEYS = ['locale', 'kheima_lang', 'app_language'] as const

export const staffLocale = createLocaleController({
  messages: { ar, en } as Record<string, Record<string, unknown>>,
  allowList: STAFF_LOCALES,
  storageKey: STAFF_LOCALE_STORAGE_KEY,
  fallback: 'ar',
  rtlLocales: ['ar'],
  legacyKeys: STAFF_LEGACY_LOCALE_KEYS,
})

/** The staff vue-i18n instance to `app.use(...)` in the staff app. */
export const staffI18n = staffLocale.i18n

/** Normalize any value to a supported staff locale (safe default `ar`). */
export function normalizeStaffLocale(value: string | null | undefined): StaffLocale {
  return value && (STAFF_LOCALES as readonly string[]).includes(value)
    ? (value as StaffLocale)
    : 'ar'
}

/** Anything with an English base name plus an optional Arabic one — menu
 * items, outlets, categories, order lines, extras — all share this shape. */
export interface StaffLocalizable {
  name: string
  name_ar?: string | null
}

/**
 * Composable exposing the active staff locale plus locale-aware formatters
 * bound to it. Currency still comes from the caller — never the language.
 *
 * `name()` (2026-08-03): اسم موحّد حسب لغة الموظف (عربي/إنجليزي بس، راجع
 * docstring الملف) — بديل الترنري `locale === 'ar' ? x.name_ar : x.name`
 * المكرر يدويًا في كل شاشة (خريطة الطاولات، السلة، الطلبات النشطة، الـKDS...).
 * باج حقيقي اتصلح: بند الطلب نفسه (DiningOrderItem.name_ar) ماكانش موجود
 * أصلاً قبل كده، فحتى الشاشات اللي كانت بتستخدم الترنري ده صح مع صنف
 * المنيو، كانت بترجع للإنجليزي دايمًا لبند طلب مُقدَّم فعليًا — دلوقتي
 * الحقل موجود، والدالة دي بقت نقطة مركزية واحدة تقرأه صح في كل مكان.
 */
export function useStaffFormat() {
  const { locale } = useI18n()
  const current = computed(() => String(locale.value))
  const isRTL = computed(() => staffLocale.isRTL(current.value))

  return {
    locale: current,
    isRTL,
    name: (entity: StaffLocalizable | null | undefined) =>
      current.value === 'ar' ? (entity?.name_ar || entity?.name || '') : (entity?.name || ''),
    formatNumber: (value: number | string | null | undefined, options?: Intl.NumberFormatOptions) =>
      formatNumber(value, current.value, options),
    formatMoney: (value: number | string | null | undefined, currency: string) =>
      formatMoney(value, currency, current.value),
    formatDate: (value: Date | string | number | null | undefined, options?: Intl.DateTimeFormatOptions) =>
      formatDate(value, current.value, options),
    formatTime: (value: Date | string | number | null | undefined, options?: Intl.DateTimeFormatOptions) =>
      formatTime(value, current.value, options),
    formatDateTime: (value: Date | string | number | null | undefined) =>
      formatDateTime(value, current.value),
  }
}
