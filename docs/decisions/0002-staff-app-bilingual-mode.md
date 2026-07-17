# Decision 0002: Staff Application Arabic/English Experience

- **Status:** Accepted product direction; implementation not yet complete
- **Date:** 2026-07-17
- **Owner:** Mohamed
- **Product:** El Kheima Beach Resort OS
- **Application:** `frontend/apps/el-kheima`

## Context

The staff application must be safe and comfortable for both Arabic-speaking
and English-speaking employees. Language is an individual user preference, not
a branch-wide switch and not a substitute for permissions or business
configuration.

The current application has shared localization infrastructure and matching
Arabic/English key sets, but it is not yet fully bilingual. The initial
read-only audit found that only a small number of staff views use the i18n
runtime, many views hard-code Arabic text, `dir="rtl"`, or `ar-EG` formatting,
and the global stylesheet forces RTL. Some translation values are placeholder
catalog entries rather than reviewed staff-facing copy. The user model stores
`preferred_language`, but the current-user API and account settings do not yet
provide a complete read/update flow for it.

This record defines the target behavior. It is not evidence that the current
frontend already meets it.

## Accepted decisions

1. The staff application supports **Arabic (`ar`) and English (`en`) in full**.
   These are the only staff-app languages until Mohamed explicitly approves
   another one.
2. The public guest application keeps its own configured language policy. The
   staff-app decision must not remove Russian, Italian, or any other approved
   public-site language.
3. Every employee can change their own display language from a clear account
   or settings screen. Changing language never requires an administrative
   permission.
4. For an authenticated employee, the backend-stored `preferred_language` is
   the source of truth. The API accepts only the staff language allow-list and
   permits an ordinary user to update only their own preference.
5. Before login, a namespaced staff-app local preference may select the login
   language. After login, the application reconciles to the authenticated
   user's server preference. Legacy local-storage language keys must be
   migrated deliberately rather than read indefinitely from several competing
   keys.
6. Locale changes text, direction, dates, times, numbers, and formatting. It
   **does not change the resort's business currency**, tax rules, prices, or
   financial configuration. Currency comes from trusted resort configuration.
7. The application root sets both `lang` and `dir`. Arabic is RTL and English
   is LTR. Components use logical CSS properties where direction matters;
   direction-independent icons are not mirrored.
8. User-facing strings belong in reviewed localization catalogs. Business data
   such as employee names, product names, reference numbers, and API-provided
   content must not be mistaken for translation keys.
9. Missing keys and placeholder-like catalog values must fail a repository
   validation check and be visible during development. Production may show a
   safe reviewed fallback, but must not silently ship raw internal keys.
10. Backend errors are presented through stable error codes and localized
    frontend messages where available. Raw server details, stack traces, and
    internal paths are never translated and displayed to employees.
11. POS, KDS, printed/exported operational views, finance tables, and numeric
    displays receive the same direction and formatting review as ordinary
    administration screens.

## Experience requirements

- The language control is easy to find from the login screen and the signed-in
  employee settings/profile area.
- Switching language updates the active screen without requiring logout.
- A shared terminal loads the signed-in employee's preference, not the
  previous employee's authenticated state.
- Arabic and English layouts preserve the same actions, permissions, data, and
  workflow order. Translation must not change business behavior.
- Dates and times use the resort timezone rules; translated formatting must not
  reintroduce browser/server timezone mistakes.
- Financial tables use deterministic decimal/currency formatting and tabular
  numerals where supported.
- Focus order, keyboard shortcuts, dialogs, toasts, tables, and navigation work
  correctly in both directions.

## Controlled implementation sequence

1. Record a baseline catalog of hard-coded staff strings, forced direction,
   locale formatting, current language storage, and translation quality.
2. Expose and securely update `preferred_language` through the current-user
   contract; add validation and ownership tests.
3. Establish one staff-app locale runtime, namespaced pre-login fallback,
   document `lang`/`dir`, and locale-aware formatting utilities.
4. Translate in reviewed batches:
   - shell, authentication, account, and settings;
   - POS, KDS, waiter, and guest-service operations;
   - administration, finance, inventory, and Dining configuration;
   - PMS, beach, HR, CRM, timeshare, leasing, maintenance, analytics, and hub.
5. Remove intentionality-free hard-coded RTL/LTR and locale formatting as each
   batch is migrated. Do not mix a mass formatting rewrite with business logic.
6. Add a dependency-free localization/catalog validation gate first. Add
   focused component or browser tooling only through a separately justified
   frontend-testing task.
7. Validate Arabic RTL and English LTR on desktop administration, POS, KDS,
   tablet, printing, and exports before declaring completion.

## Acceptance criteria

- Every reachable staff route has reviewed Arabic and English user-facing copy.
- A user can select a login language and can persist their own signed-in
  preference through settings.
- Unsupported language values and attempts to edit another user's preference
  are rejected server-side.
- Reload, logout/login, token refresh, and a second user on the same terminal
  resolve to the correct language behavior.
- There is no global forced RTL rule and no unexplained hard-coded `dir`,
  `left`/`right`, or `ar-EG` behavior in migrated UI.
- Currency and stored financial values do not change when language changes.
- Missing keys, key mismatches, and placeholder catalog values are caught by a
  repeatable check.
- Staff type-check and production build pass, followed by a real browser
  walkthrough in Arabic RTL and English LTR.

## Non-goals for this decision

- Redesigning the public website or changing its approved locale list.
- Adding automatic machine translation at runtime.
- Introducing dark mode or a new visual design solely because localization is
  being completed.
- Storing permissions, secrets, or authenticated identity in the language
  preference mechanism.

## Current status

The direction is approved. No product behavior was changed when this record was
created. Implementation must be delivered in focused, reviewable phases before
Public Phase 0 begins.
