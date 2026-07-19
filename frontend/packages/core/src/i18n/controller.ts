/**
 * createLocaleController — app-scoped locale runtime factory.
 *
 * Why this exists (Gate 3A / Decision 0002): the staff app (`el-kheima`) and
 * the public guest app must have *independent* language policies — different
 * allow-lists (staff `ar/en`, public `ar/en/ru/it`) and different, namespaced
 * storage keys — so signing in on a shared terminal never rewrites the public
 * site's language and vice-versa. A single shared singleton cannot express two
 * policies, so each app builds its own controller from this factory while
 * still reusing the same reviewed message catalogs.
 *
 * The controller is the ONE place that:
 *   - resolves the initial locale (namespaced key → one-time legacy migration
 *     → fallback),
 *   - applies `<html lang>` and `<html dir>` centrally (never per-component,
 *     never `document.body.dir`, never a global CSS `direction: rtl`),
 *   - persists the choice to its own namespaced key only.
 */
import { createI18n, type I18n } from 'vue-i18n'
import { nextTick } from 'vue'

export interface LocaleControllerOptions {
  /** Message catalogs keyed by locale code (e.g. `{ ar, en }`). */
  messages: Record<string, Record<string, unknown>>
  /** Locales this app is allowed to display. First entry is not special. */
  allowList: readonly string[]
  /** Namespaced localStorage key, e.g. `resort-os:staff:locale`. */
  storageKey: string
  /** Locale used when nothing valid is stored. */
  fallback: string
  /** vue-i18n message fallback. Defaults to the boot fallback. */
  messageFallback?: string
  /** Locales rendered right-to-left. Defaults to `['ar']`. */
  rtlLocales?: readonly string[]
  /**
   * Legacy localStorage keys to adopt ONCE if the namespaced key is empty.
   * The controller reads them a single time, writes the namespaced key, and
   * then never reads or writes these keys again (it also never deletes them —
   * another app may still own them).
   */
  legacyKeys?: readonly string[]
}

export interface LocaleController {
  readonly i18n: I18n
  readonly available: readonly string[]
  /** True when `locale` (or the current locale) renders right-to-left. */
  isRTL(locale?: string): boolean
  /** The locale currently active in the i18n instance. */
  current(): string
  /**
   * Resolve the locale to boot with: namespaced key → one-time legacy
   * migration → fallback. Safe to call before the app mounts.
   */
  resolveInitial(): string
  /** Set `<html lang>` + `<html dir>` for `locale`. Does not persist. */
  applyDocument(locale: string): void
  /**
   * Switch the active locale, apply document lang/dir, and persist to the
   * namespaced key by default. Authenticated account reconciliation can pass
   * `{ persist: false }` so it does not overwrite a terminal's separate
   * pre-login preference. Unsupported locales fall back safely. Returns the
   * locale actually applied.
   */
  setLocale(locale: string, options?: { persist?: boolean }): Promise<string>
}

function hasWindow(): boolean {
  return typeof window !== 'undefined' && typeof localStorage !== 'undefined'
}

export function createLocaleController(options: LocaleControllerOptions): LocaleController {
  const {
    messages,
    allowList,
    storageKey,
    fallback,
    messageFallback = fallback,
    legacyKeys = [],
  } = options
  const rtlLocales = options.rtlLocales ?? ['ar']

  const isSupported = (value: string | null | undefined): value is string =>
    !!value && allowList.includes(value)

  // Track the active locale in a plain closure variable. vue-i18n's composer
  // exposes `locale` as a WritableComputedRef, but createI18n's return type
  // does not narrow `legacy: false`, so reading `.value` off it is awkward to
  // type. `activeLocale` is the single readable source; the composer ref is
  // still written in setLocale so `$t()` re-renders reactively.
  let activeLocale = fallback

  const isRTL = (locale?: string): boolean =>
    rtlLocales.includes(locale ?? activeLocale)

  const applyDocument = (locale: string): void => {
    if (typeof document === 'undefined') return
    // Single source of truth for direction: the document root only. No
    // `body.dir`, no global stylesheet `direction` rule.
    document.documentElement.lang = locale
    document.documentElement.dir = isRTL(locale) ? 'rtl' : 'ltr'
  }

  const resolveInitial = (): string => {
    if (!hasWindow()) return fallback

    const stored = localStorage.getItem(storageKey)
    if (isSupported(stored)) return stored

    // One-time migration from legacy keys — adopt, persist under the
    // namespaced key, then stop reading them forever.
    for (const key of legacyKeys) {
      const legacy = localStorage.getItem(key)
      if (isSupported(legacy)) {
        localStorage.setItem(storageKey, legacy)
        return legacy
      }
    }
    // Persist the fallback as the migration result even when no valid legacy
    // value exists. Without this marker, every future boot would re-read the
    // legacy keys and could unexpectedly adopt a value written later by a
    // different app on the same origin — not a one-time migration at all.
    localStorage.setItem(storageKey, fallback)
    return fallback
  }

  const initial = resolveInitial()
  activeLocale = initial

  const i18n = createI18n({
    legacy: false,
    locale: initial,
    fallbackLocale: messageFallback,
    messages: messages as Record<string, Record<string, string>>,
    globalInjection: true,
    missingWarn: false,
    fallbackWarn: false,
  })

  // Composer `locale` ref — written to switch the reactive translation locale.
  const localeRef = i18n.global.locale as unknown as { value: string }

  // Apply direction/lang for the very first paint.
  applyDocument(initial)

  const setLocale = async (
    locale: string,
    setOptions: { persist?: boolean } = {},
  ): Promise<string> => {
    const target = isSupported(locale) ? locale : fallback
    localeRef.value = target
    activeLocale = target
    await nextTick()
    applyDocument(target)
    if (setOptions.persist !== false && hasWindow()) {
      localStorage.setItem(storageKey, target)
    }
    return target
  }

  return {
    i18n,
    available: allowList,
    isRTL,
    current: () => activeLocale,
    resolveInitial,
    applyDocument,
    setLocale,
  }
}
