# Gate 3 — Staff UI, i18n, Design-System & Quality Foundation

**Status:** **Accepted after independent Codex review and correction.** The
implementation checkpoint is `2083567` (`feat(frontend): establish bilingual
UI quality foundation`) on branch `gate-3-ui-i18n-quality-foundation`; it
passed the complete backend and frontend gates. No push was performed.

**Scope contract:** `docs/audits/gate-3-execution-brief.md` and
`docs/decisions/0002-staff-app-bilingual-mode.md`. Delivered as one package in
three internal slices (3A i18n runtime + saved preference, 3B design-system
adoption baseline, 3C minimal frontend quality harness).

---

## 0. Baseline (repeatable)

- Both apps previously shared **one** vue-i18n singleton
  (`packages/core/src/i18n/index.ts`) advertising `ar/en/ru/it` and writing
  three legacy localStorage keys (`locale`, `kheima_lang`, `app_language`).
- `el-kheima/src/assets/main.css` forced `body { direction: rtl }` even under an
  English session; `switchLocale` also set `document.body.dir` — direction had
  multiple sources.
- `User.preferred_language` existed (`String(10) default 'ar'`, migration
  `af9285101fa9`) but was not exposed or updatable through `/auth/me`.
- Reference screens carried forced `dir="rtl"` and hard-coded `ar-EG`/`en-US`
  formatting (shell layouts, DiningKDSView, UnifiedPOSView, ProfileView,
  SessionsView, SettingsView).
- ar/en catalogs: **3115 leaf keys each, perfect parity, 0 empty, 0 placeholder**
  values (measured by the new gate).
- Frontend had type-check/build only — no i18n validation, no component/a11y/
  smoke tests.

The baseline invariants are now encoded as an executable gate
(`apps/el-kheima/scripts/validate-i18n.mjs`) rather than prose numbers.

---

## Slice 3A — Staff-only bilingual runtime & saved preference

### Backend contract (design as built)

- `UserRead` now exposes `preferred_language` (normalized to the staff
  allow-list on the way out — legacy `null`/`ru`/`it` become the safe default
  `ar`, so the UI never receives an unrenderable value).
- New `PATCH /auth/me/preferences` (`backend/app/core/me_router.py`):
  - target user is derived from the token — **no `user_id` accepted**;
  - `UserPreferencesUpdate` schema with `extra="forbid"` (rejects
    mass-assignment / `role`/`is_active` smuggling with HTTP 422) and an
    `ar|en` allow-list validator;
  - delegates mutation/transaction/audit behavior to
    `core.services.update_user_preferences()` so the HTTP router does not own
    business logic;
  - **real-change guard**: a no-op writes nothing and emits no audit;
  - a real change writes one attributable `AuditLog`
    (`user.preferences.language_changed`, IP + user-agent, no secrets), then
    commits.
- `normalize_staff_language()` shared helper (schemas.py) — single source for
  the allow-list + safe default. **No migration** added: the column already
  exists and normalization covers legacy rows (data check confirmed safe).

### Frontend runtime (design as built)

- New **`createLocaleController` factory** (`packages/core/src/i18n/controller.ts`)
  — app-scoped vue-i18n instance + controller that (a) resolves the initial
  locale (namespaced key → one-time legacy migration → fallback), (b) applies
  `<html lang>`/`<html dir>` **centrally** (no `body.dir`, no global CSS
  `direction`), (c) persists to its own namespaced key only.
- **Staff instance** (`packages/core/src/i18n/staff.ts`): `staffLocale` +
  `staffI18n`, allow-list `['ar','en']`, key `resort-os:staff:locale`, one-time
  migration from the three legacy keys (adopt + persist namespaced; never delete
  them — another app may own them; never read them again).
- **Public behavior preserved and runtime isolated**: Public keeps
  `ar/en/ru/it`, now behind the explicit `@resort-os/core/i18n` export and the
  namespaced key `resort-os:public:locale`; Staff imports only
  `@resort-os/core/i18n/staff`. The root package barrel exports neither
  initialized singleton, so building either app cannot execute the other
  app's locale controller. A one-time legacy migration remains for both apps.
- **Central formatters** (`packages/core/src/i18n/format.ts` + `useStaffFormat`):
  `formatMoney(value, currency, locale)` takes currency **explicitly from
  trusted config — never from language**; latn tabular digits; deterministic
  2-dp money; `—` for nullish/invalid. Date/time formatting reuses the existing
  API timestamp parser and explicitly targets the resort timezone
  `Africa/Cairo`, rather than the browser's local timezone.
- Auth store: `updatePreferredLanguage()` (PATCH, updates local user from
  server response, rethrows on failure); `User.preferred_language` type added;
  `ENDPOINTS.auth.mePreferences` added.
- `useStaffLocaleSync` (App.vue) reconciles the UI to the signed-in user's
  server `preferred_language` on login / refresh / **PIN switch** (shared
  terminal loads the *new* operator's language). Authenticated reconciliation
  deliberately uses `{ persist: false }`, so one employee cannot overwrite the
  terminal's independent pre-login language. Logout reloads to `/login`, so
  that pre-login preference re-applies deterministically.
- `LanguageSwitcher` rewritten to ar/en only: pre-login persists locally;
  signed-in persists **server-first** then applies; on failure it rolls back
  visibly and toasts an error (never a false success); listbox ARIA + disabled/
  loading state.
- Global forced RTL removed from `main.css`; shell layouts no longer set
  per-component `dir`.

### 3A tests

- Backend `tests/test_api/test_me_preferences.py` (17 tests): DTO exposure +
  null/public normalization, ownership (no `user_id` targeting), `ar|en`
  allow-list (422 on ru/it/fr/…/empty), case/trim, no-op audit suppression,
  real-change audit-once, mass-assignment rejection, auth required.
- Frontend (Vitest): locale controller migration/namespacing/reconciliation/
  fallback/RTL, formatter currency-independence, LanguageSwitcher behavior — see
  3C.

---

## Slice 3B — Design-system adoption baseline

Applied `@resort-os/ui` + central direction/formatting to the reference
surfaces named in the brief (not a whole-app rewrite):

- **Shell:** `BackOfficeLayout`, `FieldLayout`, `KioskLayout` — removed forced
  `dir`, moved clocks/date to `useStaffFormat`, i18n'd the last hard-coded
  strings (`reception`, quick-search label + placeholder, kiosk logout), added
  `backoffice.nav.reception` + `backoffice.layout.{quickSearch,searchPlaceholder,
  languageSaveFailed}` keys (ar+en, parity kept).
- **Account/Profile:** `ProfileView` fully migrated — i18n (`backoffice.profile.*`),
  `AppInput`/`AppButton`, `formatDate`, `<form>`+`role=alert/status`, no forced
  dir. `SessionsView` + `SettingsView` moved to the central `formatDateTime`.
- **Admin reference:** `SettingsView`/`SessionsView`/`PermissionsView` already
  used shared primitives + i18n from Gate 2B3A/2B3B; verified clean of forced
  dir/hard-coded locale.
- **KDS reference:** `DiningKDSView` — removed forced `dir="rtl"`, clock + ticket
  time via `useStaffFormat`. (Copy migration of its Arabic strings deferred —
  tracked.)
- **POS reference:** `UnifiedPOSView` — removed forced `dir="rtl"` only; order/
  money/business logic untouched.
- **Shared primitive hardened:** `AppModal` gained `role="dialog"`,
  `aria-modal`, accessible name (title/`ariaLabel`), **focus-on-open,
  focus-return, Tab trap, Escape-to-close** — additive, no API/visual change, no
  caller regression (verified by build + tests across both apps). Initial-open
  mounts and parent-driven unmounts are covered as well as ordinary open/close.
- Documentation: `docs/DESIGN_SYSTEM.md` (tokens, typography, central direction,
  component contracts, formatting, POS/KDS patterns, do/don't, adoption
  ratchet). A dev-only interactive UI catalog was **deferred** (optional in the
  brief) to avoid shipping an unverified view; the ratchet lives in the
  validation script instead.

---

## Slice 3C — Minimal frontend quality harness

**Dependencies added (justified):** `vitest@1.6.1`, `@vue/test-utils@2.4.6`,
`jsdom@24.1.3`, `axe-core@4.10.3` — all pinned to versions compatible with the
existing Vue 3.4 / Vite 5.2 toolchain. No Playwright / Storybook / Jest.

**Dependency-free gate:** `apps/el-kheima/scripts/validate-i18n.mjs`
(`validate:i18n`) — ar/en parity, empty/placeholder scan, public policy intact,
missing-runtime-key check on strict reference screens, forced-dir / hard-coded-
locale ban in the migrated scope, and a ban on the retired legacy keys /
singleton APIs in staff src. It is also the **adoption ratchet** (strict vs.
direction-clean file lists).

**Vitest suites** (`src/__tests__/`, jsdom): public/staff locale controllers,
authenticated shared-terminal reconciliation, formatters, LanguageSwitcher,
shared UI primitives (Input/Button/Modal a11y), reference-screen axe
(ProfileView in ar/RTL + en/LTR), router smoke/guards.

**Scripts:** `validate:i18n`, `test:unit`, `test:a11y`, `test:frontend`.
Documented in `docs/FRONTEND_TESTING.md`, including the honest jsdom-only
limitation (color-contrast disabled — needs human/browser review).

---

## Verification (commands actually run)

| Command | Result |
| --- | --- |
| `pnpm --filter el-kheima validate:i18n` | ✅ pass — 3115 keys parity, 0 empty/placeholder, public policy intact, 7 strict + 2 direction-clean files, no legacy keys |
| `pnpm --filter el-kheima test:frontend` | ✅ validate:i18n + **60 vitest tests passed** (7 files) |
| `pnpm --filter el-kheima type-check` | ✅ pass |
| `pnpm --filter el-kheima build` | ✅ built (vue-tsc + vite + PWA) |
| `pnpm --filter public type-check` | ✅ pass (core changes safe for public) |
| `pnpm --filter public build` | ✅ built |
| `backend .venv/bin/pytest tests/test_api/test_me_preferences.py -v` | ✅ 17 passed |
| `backend .venv/bin/pytest tests/ -q` | ✅ exit 0 — full suite passed (see below) |
| `backend .venv/bin/alembic heads` | ✅ single head `b8f4d2a19c07` |
| `git diff --check` | ✅ clean |

Full backend suite: **1992 passed, 20 skipped, 0 failed** (2012 tests collected
in total; includes the 17 new `test_me_preferences.py`). The earlier wording
"2012 passed" incorrectly treated the JUnit total as the passed count and has
been corrected here.

Production-bundle isolation was also inspected after building both apps:
Public contains only `resort-os:public:locale`, while Staff contains only
`resort-os:staff:locale`. Neither initialized app runtime leaked into the other
bundle.

Not run: real-browser walkthrough / screenshots (no browser+fonts+GPU in this
sandbox; the harness is jsdom/component-level by design). Arabic-RTL / English-
LTR visual confirmation on a real device remains for review.

---

## Changed / new files

**Backend:** `app/core/me_router.py`, `app/modules/core/schemas.py`,
`app/modules/core/services.py`,
`tests/test_api/test_me_preferences.py` (new).

**Frontend core (`packages/core/src`):** `i18n/controller.ts` (new),
`i18n/staff.ts` (new), `i18n/format.ts` (new), `index.ts`, `api/endpoints.ts`,
`stores/auth.ts`, `types/index.ts`, `package.json`, `i18n/locales/ar.json`,
`i18n/locales/en.json`. Public's locale entrypoint/component comments were
updated to the isolated public runtime without removing `ru` or `it`.

**Frontend ui (`packages/ui/src`):** `components/Modal.vue`.

**Staff app (`apps/el-kheima`):** `package.json`, `vitest.config.ts` (new),
`scripts/validate-i18n.mjs` (new), `src/main.ts`, `src/App.vue`,
`src/assets/main.css`, `src/composables/useStaffLocaleSync.ts` (new),
`src/components/LanguageSwitcher.vue`, `src/layouts/{BackOffice,Field,Kiosk}Layout.vue`,
`src/views/portal/ProfileView.vue`, `src/views/account/SessionsView.vue`,
`src/views/admin/SettingsView.vue`, `src/views/kds/DiningKDSView.vue`,
`src/views/pos/UnifiedPOSView.vue`, `src/views/dev/ProjectCockpitView.vue`,
`src/__tests__/**` (new). `frontend/pnpm-lock.yaml` (deps).

**Docs:** `docs/DESIGN_SYSTEM.md` (new), `docs/FRONTEND_TESTING.md` (new), this
report (new), plus `wagdy.md`, `PROJECT_STATUS.md`, Project Cockpit data.

---

## Bugs found / fixed during the work

- **Forced RTL under English sessions** (`main.css` `direction: rtl` +
  per-component `dir="rtl"` on shell/KDS/POS/Profile) — an English-preferring
  user still got a right-to-left layout. Fixed by centralizing direction on
  `<html dir>`.
- **`AppModal` had no dialog semantics or focus management** — no `role`, no
  focus trap, no focus return, no Escape. Hardened (additive) so every modal in
  the app (incl. `useConfirm`, StepUp, PinGuard) is keyboard-accessible.

## Independent Codex review findings and corrections

The review did not accept the self-verified diff unchanged. It reproduced and
corrected these confirmed defects before acceptance:

1. **High — app-runtime cross-contamination:** the root core barrel re-exported
   both initialized i18n singletons. Public's production bundle executed the
   Staff fallback and could have its Russian/Italian document direction
   overwritten. Explicit package subpath exports and bundle assertions now
   isolate the apps.
2. **High — shared-terminal preference leak:** applying an authenticated
   employee's server language also overwrote the terminal's pre-login setting.
   Authenticated changes now apply without persisting locally; regression tests
   cover user and PIN-operator changes.
3. **Medium — migration and UI state:** the no-legacy fallback did not mark the
   one-time migration complete, and `LanguageSwitcher` could display stale
   state after server/PIN changes. Both now have explicit reactive tests.
4. **Medium — resort time drift:** the new formatters used the browser timezone
   and parsed naive API timestamps as local time. They now reuse the established
   parser and `Africa/Cairo`; an exact UTC-to-resort-time test protects it.
5. **Medium — modal lifecycle gaps:** mounting already open and parent-driven
   unmount did not reliably move/restore focus. Both paths are now covered.
6. **Low/maintainability — HTTP/business layering and directional CSS:** the
   preference transaction moved into the service layer, and remaining physical
   direction utilities in the migrated reference scope were replaced and added
   to the validation ratchet.

## Deferred risks / debt (honest)

- KDS + Unified POS still contain hard-coded Arabic copy (direction/format
  normalized only) — tracked in the ratchet; migrate in later batches.
- ~40 other staff screens not yet migrated — do **not** claim the app is fully
  bilingual. Decision 0002 remains "implementation in progress".
- No real-browser/visual verification in this environment.
- `branch_id` fallback (`= 1`) is a pre-existing data-model limitation, out of
  scope (see CLAUDE.md §13).

**Checkpoint:** `2083567`. **No push was performed.**
