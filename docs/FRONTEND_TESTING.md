# Frontend Testing — El Kheima Staff App

> Introduced in Gate 3C. This is a **jsdom / component-level** harness, not a
> full browser E2E system. It does not render a real browser, take screenshots,
> or drive a live backend. Playwright / Storybook / Jest are intentionally
> **not** used (Decision: the current architecture does not justify a parallel
> stack; see the Gate 3 execution brief).

## Toolchain

| Tool | Version | Why |
| --- | --- | --- |
| Vitest | 1.6.1 | Vite-native test runner; compatible with the app's Vite 5.2 / Vue 3.4. |
| @vue/test-utils | 2.4.6 | Mount/inspect Vue 3 SFCs. |
| jsdom | 24.1.3 | DOM + `localStorage` + `document.documentElement` so direction/storage behave like the browser. |
| axe-core | 4.10.3 | Focused accessibility assertions, used directly (no wrapper stack). |

All four are `devDependencies` of `apps/el-kheima` and pinned to versions
compatible with the existing Vue/Vite toolchain.

## Scripts (`apps/el-kheima/package.json`)

| Script | What it runs |
| --- | --- |
| `pnpm --filter el-kheima validate:i18n` | Dependency-free localization gate (Node only). |
| `pnpm --filter el-kheima test:unit` | `vitest run` — all component/unit/smoke tests. |
| `pnpm --filter el-kheima test:a11y` | `vitest run` over `src/__tests__/a11y` only. |
| `pnpm --filter el-kheima test:frontend` | `validate:i18n` **then** `vitest run` — the full gate. |

Vitest config: `apps/el-kheima/vitest.config.ts` (jsdom env, Vue plugin, `@`
alias, `src/__tests__/setup.ts` resets DOM dir/lang + localStorage per test).

## `validate:i18n` — the dependency-free gate

`apps/el-kheima/scripts/validate-i18n.mjs` (Node built-ins only). Enforces:

1. Staff **ar/en catalog parity** — identical key sets, zero missing keys.
2. **No empty / placeholder** values (TODO/TBD/FIXME/…).
3. **Public locale policy intact** — `ru`/`it` catalogs remain present and the
   isolated Public runtime advertises `ar/en/ru/it` without importing Staff's
   initialized runtime.
4. **No missing runtime keys** — every static `t()`/`$t()` key in the strict
   reference screens exists in both catalogs.
5. **No forced `dir="rtl"`** and **no hard-coded `ar-EG`/`en-US`/`en-GB`** tags
   in the migrated scope.
6. **Retired legacy locale keys** (`kheima_lang`, `app_language`) and the old
   shared-singleton APIs (`switchLocale`, `getSavedLocale`) never return to the
   staff app (tests excepted — they prove the migration).

The strict-file and direction-clean-file lists in that script are the **adoption
ratchet**: extend the strict list as each new screen batch is migrated.

## Test suites (`src/__tests__/`)

| File | Covers |
| --- | --- |
| `i18n/localeController.spec.ts` | Storage migration (legacy→namespaced, once), namespacing, fallback, `setLocale`, RTL/LTR without reload, staff/public isolation. |
| `i18n/staffLocaleSync.spec.ts` | Server-authoritative authenticated language, PIN/user switching, and isolation from the terminal's pre-login preference. |
| `i18n/format.spec.ts` | `formatMoney` currency-independent-of-language invariant, latn digits, deterministic 2-dp money, nullish handling, and exact resort-timezone conversion. |
| `components/LanguageSwitcher.spec.ts` | ar/en only, pre-login local persist (no server call), signed-in server-first persist, live external/PIN changes, failure rollback + error toast, listbox ARIA. |
| `components/uiPrimitives.spec.ts` | AppInput label/aria-invalid/error, AppButton name/loading, AppModal dialog role + accessible name + Escape + initial-open/unmount focus restoration. |
| `a11y/referenceScreens.spec.ts` | ProfileView rendered in ar/RTL and en/LTR: correct `<html dir/lang>`, real translated copy (no raw keys), **zero critical/serious axe violations**. |
| `smoke/router.spec.ts` | Role landing map, reference routes resolve, auth guard redirects unauthenticated users to `/login`. |

## Known limitations (honest scope)

- **jsdom only.** No real layout, so axe **color-contrast is disabled** — that
  must be checked by human/browser review. No screenshots, no real navigation
  paint, no service worker.
- Locale-sensitive glyph shape is not asserted across ICU builds; the semantic
  money invariants and exact API-timestamp-to-`Africa/Cairo` time conversion are
  asserted.
- KDS/POS reference screens are covered for direction/format hygiene and by the
  smoke router test, not by full component render tests (copy migration
  deferred).
