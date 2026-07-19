/**
 * Public-app locale runtime.
 *
 * This module is intentionally available only through
 * `@resort-os/core/i18n`. The staff app uses the separate
 * `@resort-os/core/i18n/staff` runtime so neither application's import can
 * evaluate the other singleton or overwrite its document direction.
 */
import ar from './locales/ar.json'
import en from './locales/en.json'
import ru from './locales/ru.json'
import it from './locales/it.json'
import { createLocaleController } from './controller'

export const SUPPORTED_LOCALES = ['ar', 'en', 'ru', 'it'] as const
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]

export const PUBLIC_LOCALE_STORAGE_KEY = 'resort-os:public:locale'
export const PUBLIC_LEGACY_LOCALE_KEYS = ['locale', 'kheima_lang', 'app_language'] as const

const publicLocale = createLocaleController({
  messages: { ar, en, ru, it } as Record<string, Record<string, unknown>>,
  allowList: SUPPORTED_LOCALES,
  storageKey: PUBLIC_LOCALE_STORAGE_KEY,
  fallback: 'ar',
  // Preserve the public runtime's historical missing-message fallback while
  // keeping Arabic as the initial display default.
  messageFallback: 'en',
  rtlLocales: ['ar'],
  legacyKeys: PUBLIC_LEGACY_LOCALE_KEYS,
})

const i18n = publicLocale.i18n

/** Return the public app's already-resolved, namespaced locale. */
export function getSavedLocale(): SupportedLocale {
  return publicLocale.current() as SupportedLocale
}

/**
 * Catalogs are eager-loaded above, so this remains a compatibility check for
 * existing callers rather than dynamically importing a second copy.
 */
export async function loadLocale(locale: string): Promise<void> {
  if (!SUPPORTED_LOCALES.includes(locale as SupportedLocale)) {
    throw new Error(`Unsupported public locale: ${locale}`)
  }
}

export async function switchLocale(locale: string): Promise<void> {
  const target = SUPPORTED_LOCALES.includes(locale as SupportedLocale)
    ? (locale as SupportedLocale)
    : 'en'
  await publicLocale.setLocale(target)
  if (typeof window !== 'undefined') {
    ;(window as any).__LANGUAGE__ = target
  }
}

if (typeof window !== 'undefined') {
  ;(window as any).__VUE_I18N__ = i18n
  ;(window as any).__LANGUAGE__ = publicLocale.current()
}

export default i18n
