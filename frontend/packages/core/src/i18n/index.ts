import { createI18n } from 'vue-i18n'
import { nextTick } from 'vue'

// ✅ Import all locale files (Eager load - faster switching)
import ar from './locales/ar.json'
import en from './locales/en.json'
import ru from './locales/ru.json'
import it from './locales/it.json'

export const SUPPORTED_LOCALES = ['ar', 'en', 'ru', 'it'] as const
export type SupportedLocale = typeof SUPPORTED_LOCALES[number]

// Get saved locale or use default
export const getSavedLocale = (): 'ar' | 'en' | 'ru' | 'it' => {
  const stored = localStorage.getItem('locale') ??
                 localStorage.getItem('kheima_lang') ??
                 localStorage.getItem('app_language')

  if (stored && ['ar', 'en', 'ru', 'it'].includes(stored)) {
    return stored as 'ar' | 'en' | 'ru' | 'it'
  }

  return 'ar' // Default to Arabic
}

const savedLocale = getSavedLocale()

const i18n = createI18n({
  legacy: false,
  locale: savedLocale as 'ar' | 'en' | 'ru' | 'it',
  fallbackLocale: 'en' as const,
  messages: { ar, en, ru, it },
  globalInjection: true,
  missingWarn: false,
  fallbackWarn: false,
})

export async function loadLocale(locale: string): Promise<void> {
  if (!['ar', 'en', 'ru', 'it'].includes(locale)) {
    console.warn(`🌍 Invalid locale: ${locale}. Using fallback: en`)
    locale = 'en'
  }
  if (i18n.global.availableLocales.includes(locale as any)) {
    return Promise.resolve()
  }
  try {
    const messages = await import(`./locales/${locale}.json`)
    i18n.global.setLocaleMessage(locale, messages.default)
    return Promise.resolve()
  } catch (error) {
    console.error(`🌍 Failed to load locale: ${locale}`, error)
    return Promise.reject(error)
  }
}

export async function switchLocale(locale: string): Promise<void> {
  try {
    await loadLocale(locale)
    ;(i18n.global.locale as any).value = locale
    await nextTick(() => {
      document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr'
      document.documentElement.lang = locale
      document.body.dir = locale === 'ar' ? 'rtl' : 'ltr'
    })
    localStorage.setItem('locale', locale)
    localStorage.setItem('kheima_lang', locale)
    localStorage.setItem('app_language', locale)
    return Promise.resolve()
  } catch (error) {
    console.error(`🌍 Failed to switch locale to ${locale}:`, error)
    return Promise.reject(error)
  }
}

if (typeof window !== 'undefined') {
  const currentLocale = getSavedLocale()
  document.documentElement.dir = currentLocale === 'ar' ? 'rtl' : 'ltr'
  document.documentElement.lang = currentLocale
  document.body.dir = currentLocale === 'ar' ? 'rtl' : 'ltr'
  ;(window as any).__VUE_I18N__ = i18n
  ;(window as any).__LANGUAGE__ = currentLocale
}

export default i18n
