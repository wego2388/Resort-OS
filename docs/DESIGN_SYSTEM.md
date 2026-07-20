# El Kheima Beach Resort OS — Design System

> Status: **baseline adopted** on the Gate 3B reference surfaces (app shell,
> Account/Profile, Sessions, Settings, and direction/format hygiene on the
> Dining KDS and Unified POS). This is not a claim that all 50+ staff screens
> are migrated — see the ratchet/inventory at the end. Light mode and
> operational clarity are the priority; dark mode is preserved where it already
> worked and is not expanded here.

The design system is the shared package **`@resort-os/ui`** (`frontend/packages/ui`)
plus its tokens (`src/styles/tokens.css`, `tailwind-preset.js`) and base rules
(`src/styles/base.css`). Both apps (`el-kheima`, `public`) consume the same
package; do not create parallel component copies.

## 1. Brand principles

- Calm, predictable, high-legibility screens for staff who use the system all
  day, often outdoors or on a wall-mounted display.
- One primary action per screen; destructive actions are visually separate.
- Real loading / empty / error / offline states — never a blank screen.
- Bilingual by construction (Arabic RTL, English LTR) with a single central
  direction source; currency and money formatting are locale-independent.

## 2. Tokens

Defined as CSS custom properties in `src/styles/tokens.css`, exposed to Tailwind
via `tailwind-preset.js`. Colors are stored as `R G B` triplets so Tailwind's
opacity modifier works (`rgb(var(--color-x) / <alpha>)`).

| Token | Purpose |
| --- | --- |
| `--color-background` | Page background |
| `--color-surface` | Cards, panels, modals |
| `--color-border` | Dividers, input borders |
| `--color-muted` | Secondary text |
| `--color-secondary` | Gold brand accent (#C9963C) |
| `--color-success` / `--color-warning` / `--color-danger` / `--color-info` | Status semantics |
| `--color-primary-ring` | Focus ring (matches primary #0B4F8A) |

Each token has a `.dark` counterpart in the same file. Semantic status colors
must always be paired with text/iconography — **never color alone** to convey
state.

Spacing, radii, shadows (`shadow-elevation-1/2`), and the `shadow-focus-ring`
utility come from the preset. Touch targets on POS/KDS use a 44–48px minimum.

## 3. Typography and numerals

- Arabic renders comfortably with the Cairo family; English is not forced onto
  an Arabic-only font (system fallback).
- Numeric/tabular displays (money, clocks, counts) use **Latin (latn) digits
  with tabular alignment** in both languages, via the central formatters, so
  finance/POS columns stay unambiguous and aligned. See §6.

## 4. Direction (RTL / LTR) — central, not per-component

Direction is owned by the **staff locale controller**
(`@resort-os/core/i18n/staff`). It sets `<html lang>` and `<html dir>` from the active locale;
`dir` cascades to `body` and every component.

Rules:
- **Never** hard-code `dir="rtl"` on a component root. (Removed from the shell
  layouts, Dining KDS, Unified POS, and Profile in Gate 3B.)
- **Never** add a global CSS `direction: rtl` rule. (Removed from
  `el-kheima/src/assets/main.css`.)
- Use **logical** Tailwind utilities where direction matters: `ms-*`/`me-*`
  (margin), `ps-*`/`pe-*` (padding), `start-*`/`end-*` (inset), `text-start`/
  `text-end`. Avoid physical `ml-*`/`mr-*`/`left-*`/`right-*` in migrated code.
- A `dir="ltr"` on a purely numeric token (a clock, a phone number) is an
  allowed, commented exception — it is not directional text.

The `validate:i18n` gate fails the build if `dir="rtl"` or a hard-coded
`ar-EG`/`en-US`/`en-GB` tag reappears in the migrated scope.

## 5. Components (`@resort-os/ui`)

Use the shared primitives instead of new copies: `AppButton`, `AppInput`,
`AppModal`, `AppBadge`, `AppCard`, `AppSpinner`, `DataTable`, `EmptyState`,
`ErrorState`, `LoadingState`, toasts (`useToast`), confirms (`useConfirm`).

Contracts hardened in Gate 3B:
- **AppInput** — label associated via `for`/`id`; `aria-invalid` + a
  `role="alert"` error message when `error` is set.
- **AppButton** — accessible name from its slot; `disabled` + `aria-busy` while
  `loading`.
- **AppModal** — `role="dialog"`, `aria-modal="true"`, accessible name from
  `title` (`aria-labelledby`) or an `ariaLabel` prop; **focus moves in on open,
  returns to the opener on close**, a **Tab focus trap**, and **Escape closes**.
  Additive only — no prop removed, no visual change, all existing call sites
  (StepUp/PinGuard/Dining modals, `useConfirm`) keep working.

## 6. Formatting utilities

Central, locale-aware, in `@resort-os/core` (`useStaffFormat` composable, or the
raw `formatMoney/formatNumber/formatDate/formatTime/formatDateTime`).

- `formatMoney(value, currency, locale)` — **currency is a required argument
  from trusted resort config; it is NEVER derived from the display language.**
  Two fraction digits, deterministic, latn digits.
- Nullish/invalid inputs render an em dash (`—`), never `NaN`/`Invalid Date`.
- Dates/times reuse the established API timestamp parser and render in the
  resort timezone (`Africa/Cairo`), rather than inheriting the browser's local
  timezone.

## 7. Feedback, confirmation, empty/error/loading

- Errors surface through `useToast().error()` and localized error copy, not raw
  server details or stack traces.
- Dangerous actions use `useConfirm()` (which renders through `AppModal`, so it
  inherits the focus trap and Escape behavior).
- Every data view provides a real loading state (`AppSpinner`/`LoadingState`),
  an empty state (`EmptyState`), and an error state (`ErrorState`).

## 8. POS / KDS patterns

- Dark, low-eye-strain surfaces for long shifts; large touch targets.
- Totals must remain visible above the fold; primary "pay/confirm" action is
  distinct from destructive "void/refund" (which require PIN approval — a
  business rule left untouched by Gate 3).
- KDS station routing, order totals, and money logic are **display-only** in
  Gate 3 — no business/financial logic was changed while restyling.

## 9. Do / Don't

**Do**
- Reuse `@resort-os/ui` primitives and the central formatters.
- Drive direction from `<html dir>`; use logical utilities.
- Keep currency separate from language.

**Don't**
- Add a second design system, a second i18n runtime, or a duplicate primitive.
- Hard-code `dir`, `ar-EG`, or physical left/right in migrated code.
- Change money/permissions/business logic during a visual refactor.

## 10. Adoption ratchet / inventory

Fully migrated (reviewed ar/en copy, central direction + formatting, shared
primitives, covered by `validate:i18n` strict checks):

- `layouts/BackOfficeLayout.vue`, `layouts/FieldLayout.vue`,
  `layouts/KioskLayout.vue`
- `components/LanguageSwitcher.vue`
- `views/portal/ProfileView.vue`
- `views/account/SessionsView.vue`
- `views/admin/SettingsView.vue`
- `views/admin/CRMView.vue` (Gate 5 Batch 3, 2026-07-20 — largest screen
  migrated so far, 7 tabs + 2 modals; removed a hard-coded `dir="rtl"` and
  `ar-EG`/`ar-EG` locale calls that predated Gate 3, fixed 2 physical
  `text-right`/`mr-2` utilities, renamed a `t` loop variable/function
  parameter shadowing vue-i18n's `t()`, and computed-ified all label/config
  lookup maps so they react to locale changes)

Direction-normalized reference screens (forced `dir`/hard-coded locale tags
removed, formatting centralized; **full copy migration deliberately deferred**
— they still contain hard-coded Arabic strings):

- `views/kds/DiningKDSView.vue`
- `views/pos/UnifiedPOSView.vue`

Not yet migrated (tracked debt, next batches — do not claim bilingual):
the remaining ~39 admin/ops/pos/portal screens. Migrate in reviewed batches
per Decision 0002, extending the strict list in
`apps/el-kheima/scripts/validate-i18n.mjs` as each batch lands.
