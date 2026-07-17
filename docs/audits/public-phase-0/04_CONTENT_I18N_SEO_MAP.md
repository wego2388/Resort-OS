# 04 — Content, Localization, and SEO Map

**Confirmed decision governing this section:** the public site keeps Arabic,
English, Russian, and Italian as independently reviewed guest languages
(Arabic RTL, the other three LTR) — separate from the staff-app-only
Arabic/English decision in `docs/decisions/0002-staff-app-bilingual-mode.md`.

> **Correction notice (post independent review):** the first version of this
> document made two claims — a "stuck `<html dir>`" defect and an "86-key
> ru/it translation gap" — that were not verified against the actual code
> before being reported. Both are corrected below with line-level evidence.
> A third claim (single static `<title>` for every route) was also partially
> wrong and is corrected. See `08_OPEN_QUESTIONS_AND_RISKS.md`'s "Retracted"
> section for the full list of what changed and why.

---

## Locale mechanism comparison

| | Legacy | Current (`apps/public`) |
|---|---|---|
| URL shape | Path-prefixed: `/ar/rooms`, `/en/rooms`, `/ru/rooms`, `/it/rooms` | **No locale in the URL at all** — single `/dining` etc. for every language. This part of the original finding stands — it is a real, structural gap versus the legacy's hreflang-capable routing. |
| Locale source | `beforeEach` guard validates `route.params.locale`, redirects to saved/default if missing/invalid | Client-side `vue-i18n` `locale` ref, persisted to `localStorage['locale']` (`packages/core/src/i18n/index.ts`, shared with the staff app) |
| `<html lang>`/`dir` runtime update | Set per navigation by the router guard (not independently re-verified line-by-line, but the rendered screenshots confirm correct RTL/LTR mirroring for ar vs en/ru/it) | **Corrected — this already works.** `packages/core/src/i18n/index.ts`'s `switchLocale()` sets `document.documentElement.dir`, `document.documentElement.lang`, and `document.body.dir` on every locale change (and an `if (typeof window !== 'undefined')` block does the same on initial module load). `apps/public/src/components/LanguageSelector.vue:28` calls `await switchLocale(code)` directly — confirmed by reading both files end to end. |
| Catalog loading | Eager — all 4 locale JSONs loaded at boot (`src/i18n/index.ts`) | Eager — all 4 locale JSONs loaded at boot (`packages/core/src/i18n/index.ts`) |

**Retracted finding:** the first version of this document claimed the
current app's `<html dir="rtl">` "never changes... because nothing in
`App.vue` mutates `documentElement`." That check only looked at `App.vue`
and missed the shared `packages/core/src/i18n/index.ts` module, which is
where this logic actually lives (a research gap in the original pass, not a
code defect). **There is no `lang`/`dir` runtime-update defect to fix.**
`07_MIGRATION_BATCH_PROPOSAL.md`'s Batch 1 has been corrected to keep this
only as a regression test (protecting existing, working behavior), not a
"fix."

**Still accurate, unaffected by the correction:** `index.html`'s single
static `<meta name="description">` (present before any JS runs) is
English-language copy while `lang="ar"` is declared in the same static
markup — a real, if minor, mismatch in the pre-hydration HTML, separate
from the runtime `lang`/`dir` behavior above, which is correct once the app
mounts.

---

## Translation catalog coverage

> **Correction:** the first version of this section only checked
> `packages/core/src/i18n/locales/*.json` and concluded the current app has
> an 86-key ru/it shortfall. That file is shared with the **staff** app
> (`el-kheima`); it also missed a second, public-app-specific catalog file
> entirely. Both gaps are fixed below.

| App | ar | en | ru | it | Parity |
|---|---|---|---|---|---|
| Legacy (`src/i18n/locales/*.json`) | 2453 keys | 2453 keys | 2453 keys | 2453 keys | **Exact match across all 4** |
| Current, shared catalog (`packages/core/src/i18n/locales/*.json`) | 2881 keys | 2881 keys | 2795 keys | 2795 keys | 86 keys differ — **but see correction below: this is not a public-site gap** |
| Current, public-only catalog (`apps/public/src/i18n/marketing.ts`) | typed, complete | typed, complete | typed, complete | typed, complete | **Exact match across all 4** — a `MarketingMessages` TypeScript interface is implemented once per locale (`ar`/`en`/`ru`/`it` objects, lines 125/228/331/434), so a missing key would fail the type-check, not just silently fall back |
| Current, `qr.*` namespace (inside the shared catalog, used by `OrderView.vue`) | 38 keys | 38 keys | 38 keys | 38 keys | **Exact match across all 4** |

**Corrected finding:** all 86 "missing" keys in the shared catalog are under
the `backoffice.*` top-level namespace (verified by recursively diffing key
sets between locales and inspecting every differing key's prefix — zero
non-`backoffice.*` keys differ). `backoffice.*` is staff-app-only content,
correctly restricted to Arabic/English per
`docs/decisions/0002-staff-app-bilingual-mode.md` — Russian/Italian are not
supposed to have these keys. **This is not a public-site translation gap at
all**, and the original framing ("a live parity gap in a codebase already
claiming 4-locale support") was misleading. The public site's own two
sources of guest-facing copy (`marketing.ts` and the `qr.*` namespace) both
have complete, matching key coverage across all four locales.

**The one real, narrower content-quality note** (not a missing-key defect):
`marketing.ts`'s own header comment documents that its Arabic/English copy
is sourced from real brand material
(`/home/wego/projects/elkheima-beach-resort-marketing/`, `BRAND_GUIDE.md`
and related files), while "Russian + Italian are reasonable machine-quality
translations of that same source copy... treat those two locales as
translation-quality, not brand-reviewed copy." This is an honest,
self-documented caveat already in the codebase, not a newly discovered gap
— worth a business-side review pass on ru/it marketing copy before Gate 7
ships it as final, but it is a quality/review item, not a missing-coverage
bug.

**Legacy dead catalogs (do not migrate):** `ar-backup.json`, `en-backup.json`,
`ru-backup.json`, `it-backup.json` exist in the legacy repo with smaller,
mismatched key counts (1276/1276/1531/1421) and are **not imported anywhere**
(confirmed via `grep` for `-backup` references in `src/i18n/index.ts` and
elsewhere) — dead files, safe to ignore entirely.

**Legacy hard-coded strings found (bypass i18n despite the app otherwise
being fully wired through `t()`):** `BillModal.vue` and `ServiceButtons.vue`
contain fully hard-coded Arabic UI strings ("فاتورتك جاهزة", "يرجى التوجه
لكاشير البوابة للدفع", "نداء ويتر", "طلب الحساب", "تعذر الإرسال، حاول مرة
أخرى"). Note: these legacy components were originally cited in
`01_ROUTE_AND_STATE_INVENTORY.md` as the reusable `view_and_call`-compliant
*pattern* — that pattern classification is about legacy intent/shape, not a
claim that the current app's equivalent works today (the current app's
equivalent is confirmed broken — see `05_API_AND_DATA_CONTRACT_MAP.md`). Any
future adaptation of either version must re-author these strings through the
catalog, not copy hard-coded text from either codebase.

**Current app hard-coded strings:** not exhaustively audited in this pass
(the current app is small — 7 views — so this is a bounded follow-up, not a
blocker); spot-reading during route inventory did not surface obvious
hard-coded user-facing strings in `HomeView.vue`/`DiningView.vue`/`OrderView.vue`
beyond expected data-driven content (item names, prices from the API).

---

## SEO comparison

| Capability | Legacy | Current |
|---|---|---|
| Per-page `<title>` | Yes — `SEOHead.vue` + `useSEO.ts` composable, invoked on every legacy public page | **Corrected twice — a real foundation exists, but it is not per-page for every route.** `apps/public/src/App.vue` watches `route.meta.titleKey` and the active `locale`, and sets `document.title` to `${t(titleKey)} | ${brand}` on route change and locale switch (confirmed by reading the full 18-line file and the router). **But `meta.titleKey` is only declared on 4 of the 7 routes** (`/`, `/dining`, `/book`, `/confirmation` — confirmed in `router/index.ts`). The other 3 (`/order/:outletId/:tableId`, `/beach/checkin/:reservationId`, `/survey/:token`) have no `titleKey`, so `updateTitle()`'s own ternary falls through to the brand name alone for those. The original claim of "a single static title for the entire app, identical on every route" was wrong (a first correction already fixed that), but the corrected claim of unqualified "per-route" title handling was also imprecise — it is per-route **only for the 4 routes that declare it**. |
| Per-page meta description | Yes | **No** — still accurate; only the one static, pre-hydration `<meta name="description">` in `index.html` exists, and `App.vue`'s title-sync logic does not touch it |
| Open Graph | Yes — full set (`og:title/description/image/url/type/site_name/og:locale`); `og:locale` maps `ar`→`ar_EG`, else `en_US` (**no ru/it OG locale mapping**, a legacy gap too) | None found |
| Twitter Card | Yes | None found |
| `hreflang` alternate links | **None found**, despite 4-locale path-prefixed routing — a real gap even in the legacy app | Not applicable (no locale-prefixed URLs to alternate between) |
| Canonical link | Yes (`useSEO.ts`) | None found |
| Structured data (JSON-LD) | Yes — `useSchema.ts` supports `organization`/`product`/`breadcrumb`/`review`; separate `LocalBusinessSchema.vue` component | None found |
| `sitemap.xml` | Static files present (`sitemap.xml`, `sitemap-enhanced.xml`) — not confirmed to be dynamically generated per-locale | None found |

**Conclusion (revised twice):** the current public app already has a
dynamic, per-locale `<title>` foundation, but it is not yet applied to every
route — 4 of 7 (`/`, `/dining`, `/book`, `/confirmation`) have it; the other
3 (`/order`, `/beach/checkin`, `/survey`) currently fall back to the brand
name only. This is a real, working foundation, not nothing, but "per-page
for every route" would overstate it. What is still genuinely missing across
*all* routes is everything *beyond* the title: meta description, Open
Graph, Twitter Card, canonical links, structured data, and `hreflang`. The
legacy app has real, if imperfect (missing hreflang, incomplete OG-locale
mapping), infrastructure for those remaining pieces that is a reasonable
reuse candidate for the *pattern* (extending the current app's existing
title-sync composable — completed for all 7 routes — into a fuller
`useSEO`-style one), not a verbatim copy.

---

## Content sourcing rule (per handoff — no legacy fact is authoritative)

No legacy price, availability figure, phone number, legal text, or marketing
claim observed during this pass (e.g. the "35,000m² total resort area /
225m private beachfront / 13,000m² private beach" stat strip already present
on the *current* Home page, or any room rate implied by legacy screenshots)
should be treated as verified/current without Mohamed's explicit
confirmation. `06_KEEP_ADAPT_REMOVE_MATRIX.md` marks all such content as
"needs business verification," not "keep as-is."
