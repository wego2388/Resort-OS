/**
 * useSEO — one global composable, called once from App.vue, that keeps
 * <title>, <meta name="description">, Open Graph tags, <link rel="canonical">
 * and hreflang alternates in sync with the current route + active locale.
 *
 * Reads `route.meta.titleKey` / `route.meta.descriptionKey` (i18n keys under
 * the `marketing` namespace) and `route.meta.noindex` — see router/index.ts.
 *
 * ⚠️ Self-referencing hreflang, not per-locale URLs: this app has a single
 * URL per route and switches locale client-side (`switchLocale()`, no path
 * prefix/query param — confirmed in docs/audits/public-phase-0/04). Real
 * hreflang alternates are supposed to point at a *different* URL per
 * language; there isn't one here. Pointing every locale code (incl.
 * x-default) at the same canonical URL is the correct, honest thing to do
 * for this architecture per Google's own guidance for single-URL sites —
 * it is not a substitute for real per-locale routing, which would be a much
 * bigger, separate change.
 */
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

const HREFLANG_CODES = ['ar', 'en', 'ru', 'it'] as const

function setMeta(attr: 'name' | 'property', key: string, content: string): void {
  let el = document.head.querySelector(`meta[${attr}="${key}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute(attr, key)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

function setLink(rel: string, href: string, hreflang?: string): void {
  const selector = hreflang ? `link[rel="${rel}"][hreflang="${hreflang}"]` : `link[rel="${rel}"]`
  let el = document.head.querySelector(selector)
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', rel)
    if (hreflang) el.setAttribute('hreflang', hreflang)
    document.head.appendChild(el)
  }
  el.setAttribute('href', href)
}

export function useSEO(): void {
  const { t, locale } = useI18n()
  const route = useRoute()

  function update(): void {
    const titleKey = route.meta.titleKey as string | undefined
    const descriptionKey = route.meta.descriptionKey as string | undefined
    const brand = locale.value === 'ar' ? t('marketing.brand.nameNative') : t('marketing.brand.name')
    const pageTitle = titleKey ? t(titleKey) : undefined
    const fullTitle = pageTitle ? `${pageTitle} | ${brand}` : brand
    document.title = fullTitle

    const description = descriptionKey ? t(descriptionKey) : t('marketing.seo.home')
    setMeta('name', 'description', description)
    setMeta('property', 'og:title', fullTitle)
    setMeta('property', 'og:description', description)
    setMeta('property', 'og:type', 'website')
    setMeta('property', 'og:site_name', brand)
    setMeta('property', 'og:locale', locale.value)
    setMeta('property', 'og:url', window.location.href)

    setMeta('name', 'robots', route.meta.noindex ? 'noindex, nofollow' : 'index, follow')

    const canonicalUrl = window.location.origin + route.path
    setLink('canonical', canonicalUrl)
    for (const code of HREFLANG_CODES) setLink('alternate', canonicalUrl, code)
    setLink('alternate', canonicalUrl, 'x-default')
  }

  watch([locale, () => route.path, () => route.meta.titleKey], update, { immediate: true })
}
