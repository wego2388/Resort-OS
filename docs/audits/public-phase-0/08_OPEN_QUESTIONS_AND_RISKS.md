# 08 — Open Questions and Risks

> **Correction notice:** this document was revised after an independent
> review (Codex) found several claims in the first version were reported
> without verifying the actual request payload or full call chain. Every
> correction below was re-verified against the current code directly (not
> re-asserted from the review comment alone) before being applied. See
> `05_API_AND_DATA_CONTRACT_MAP.md` for the full evidence trail.

## Risks (ranked, with source evidence — re-verify against the exact task
base commit before acting on any of these; this is a snapshot)

### Critical

1. **The current, already-shipped `/order/:outletId/:tableId` route defaults
   to unauthenticated self-ordering**, not `view_and_call`, and the endpoint
   it posts to (`POST /dining/public/orders`) has no rate limiting
   registered (`05`). This is a pre-existing production-readiness risk
   independently reproduced by this audit, not introduced by it, and not
   fixed by it — it belongs to Gate 1A/8, tracked in
   `docs/audits/PRODUCTION_READINESS_AUDIT.md` (C-02).
2. **The same route's "compliant" fallback (call waiter / request bill) is
   also broken and also unsafe — corrected finding.** `OrderView.vue`'s
   `sendGuestAlert()` sends `context_type: 'dining_table'`, which the
   backend's `GuestAlertCreate` schema rejects (HTTP 422) because it only
   accepts `restaurant_table|cafe_table|beach_location|room|other`. Even if
   that string were fixed, `POST /public/alerts` validates only that
   `branch_id` exists — `context_id` is never checked for existence or for
   belonging to that branch, there is no QR token or Guest Session, no
   duplicate-request prevention, and no cooldown/idempotency beyond a
   generic 20-req/60s IP rate limit. The staff-facing `GET /alerts` also
   accepts a client-supplied `branch_id` with no check against the
   authenticated user's own branch — a real cross-branch read/authorization
   gap on the staff side too. Full detail and line numbers in `05`. This
   means **neither of the current app's two guest-service code paths is
   currently safe or working** — not "one bad, one good to build on," which
   is what the first version of this report incorrectly concluded from a
   screenshot alone.
3. **`GET /beach/reservations/{id}/public` leaks real guest PII and a real
   money amount, not just status — corrected finding, upgraded severity.**
   `BeachReservationPublic` returns `guest_name`, `guests_count`,
   `with_towel`, `reservation_date`, `status`, and `total_amount`, all
   readable by guessing a sequential integer with zero authentication (`05`).
   The first version of this report described this as "coarse status only,"
   which understated it. Not previously listed in
   `PRODUCTION_READINESS_AUDIT.md`'s C-02 examples — worth adding there.

### High

4. **`POST /beach/reservations/{id}/checkin` has a broken object-level
   authorization (BOLA/IDOR) gap, not "properly protected" as the first
   version of this report stated.**
   `get_cashier_user` (`app/core/deps.py:193-196`) checks only the caller's
   role level (`>= 40`); it never checks a branch. The `User` model has no
   `branch_id` column at all (confirmed by direct inspection of
   `app/core/kernel/models/user.py`). `check_in_reservation`
   (`beach/services.py:842-866`) looks up the reservation by a bare
   sequential ID with no branch filter, then acts using **the reservation's
   own** `branch_id` — never the acting cashier's. **Any authenticated
   cashier-level-or-above account, from any branch, can check in a
   reservation belonging to a different branch, simply by knowing or
   guessing its sequential ID.** This is an operational/business-logic
   integrity risk (a cashier consuming another branch's beach
   capacity/towels/inventory against the wrong branch's reservation), not
   just a data-exposure one. Full detail in `05`.
5. Booking/payment contract parity — **corrected**: `BookingView.vue` does
   not call `hub/online-bookings` at all; it submits a plain inquiry via
   `POST /hub/contact` with no payment step and no reservation record
   created (`05`). Whether `hub/online-bookings` (which does exist in the
   backend, unused by any current frontend page found in this pass) has real
   payment integration was still not traced end-to-end. Needs a dedicated
   read before any Batch touches booking, and a product decision on whether
   the inquiry-only flow is intentional or a placeholder.
6. **New finding:** `BeachCheckinView.vue`, part of the unauthenticated
   `apps/public` bundle, renders a real staff email/password login form
   (`auth.login()`) when the viewing session isn't staff-authenticated
   (`05`). This is not just a UI oddity — `auth.login()` reaches the full
   shared staff auth contract (`POST /auth/login`, `GET /auth/me`, and a
   conditional `POST /auth/refresh` on any subsequent 401), meaning the
   unauthenticated guest bundle can, once a staff member types credentials
   into it, carry a real staff session. A public, guest-facing app shipping
   staff-credential-entry UI is an architecture/boundary concern worth a
   decision, independent of whether it's exploitable today.

### Medium

7. Two overlapping legacy design-token representations would need
   reconciling before literal reuse (`03`) — not a Resort OS risk today,
   but a trap for whoever adapts legacy components without noticing.
8. Legacy Digital Hub's remote Unsplash dependency (`03`) — **corrected
   framing**: ownership/licensing of these specific images was not verified
   in this pass (no claim of "unlicensed" is supported by evidence); the
   concrete, evidenced risk is that a remote, third-party image host is a
   performance, offline-reliability, and privacy (third-party request)
   liability for a resort site that must work on weak beach/venue networks,
   regardless of the licensing question. Either way, these should be
   replaced with owned, locally-hosted images before this pattern is
   adopted.
9. No `hreflang` support exists in either codebase (`04`) — an SEO gap that
   predates this audit in the legacy app and remains unaddressed in the
   current one (which has no per-locale URLs to alternate at all yet).
10. `POST /dining/public/orders` and `POST /public/alerts` both lack an
    idempotency key — a retried/duplicated client request (network retry,
    double-tap) can create duplicate orders or duplicate alerts (`05`).
11. **New finding:** the current app's per-route `<title>` foundation only
    covers 4 of 7 routes (`04`) — `/order`, `/beach/checkin`, and `/survey`
    (three of the more sensitive/transactional routes, incidentally) fall
    back to the brand name alone in the browser tab.

### Low / informational

12. Legacy `/review/:ref` and `/receipt/:ref` public routes are implemented
    under `apps/ops/` despite being public, no-auth pages (`01`) — a
    naming/location smell worth fixing if these are ever adapted, not a
    security issue by itself (confirmed no-auth is intentional for these
    routes based on route meta).
13. Legacy `*-backup.json` locale files are dead, unused code (`04`) — no
    action needed, just noting they exist so nobody mistakes them for a
    real, more-complete catalog.

### Retracted from the first version of this report (verified incorrect)

- ~~"Current app's `<html dir>` never updates at runtime."~~ **False,
  retracted.** `packages/core/src/i18n/index.ts`'s `switchLocale()` sets
  `document.documentElement.dir`/`lang` and `document.body.dir` on every
  locale change and on initial load; `apps/public`'s `LanguageSelector.vue`
  already calls `switchLocale()`. Verified by direct code reading, not
  reasserted from the review comment. See `04` for the corrected section.
- ~~"Current app's ru/it translation catalogs are 86 keys short of ar/en —
  a live parity gap."~~ **Misleading, retracted as stated.** All 86 keys are
  under the `backoffice.*` namespace, which is staff-app-only content —
  correctly ar/en-only per `docs/decisions/0002-staff-app-bilingual-mode.md`.
  Not a public-site gap. Separately, `apps/public/src/i18n/marketing.ts` (a
  dedicated public-marketing catalog this audit missed entirely in its first
  pass) and the `qr.*` namespace both have complete, matching key counts
  across all four locales. The one real, narrower finding: `marketing.ts`'s
  own header comment documents that its ru/it copy is "translation-quality,
  not brand-reviewed" (ar/en are sourced from real brand material; ru/it are
  machine-quality translations of it) — a content-quality note, not a
  missing-keys defect. See `04` for the corrected section.
- ~~"No `_v2`/`_old` duplicate-asset naming pattern was found" (implying no
  meaningful duplication).~~ **Incomplete, now corrected with real data.**
  A full SHA-256 hash pass over all 230 legacy images (naming-pattern
  checks alone were not sufficient, as the review correctly pushed back on)
  found **40 distinct duplicate-content groups covering 96 files, 56 of
  which are fully redundant copies (~10.9MB, ~22% of the 49MB total)** — the
  same photo saved under different names in different folders. See `03` for
  the full corrected asset section.

## Explicitly unresolved / needs Mohamed's decision

- Is the legacy site's booking/payment flow (Paymob) still the intended
  payment provider for Resort OS, or is `hub/online-bookings` meant to
  replace the current inquiry-only `hub/contact` submission? (`05`, `06`)
- Is a blog in scope for the near-term public site, given it requires
  ongoing editorial content, not just code? (`06`)
- Should the Digital Hub's "Coastal Dark" cyan glassmorphism sub-brand be
  adopted, or should the guest-service menu page (now blocked pending Gate 8,
  `07`) stay visually consistent with the rest of the marketing site
  instead? (`03`, `06`)
- Is a guest-facing loyalty/wishlist view wanted at all, given the staff-side
  CRM loyalty feature has no public contract today? (`05`, `06`)
- Should beach staff check-in stay embedded in the guest-facing `apps/public`
  bundle, or move fully into the staff (`el-kheima`) app? (`05`, `06`)
- Every legacy marketing claim, price, and stat (including ones already
  echoed on the *current* Home page, like the 35,000m²/225m/13,000m² stats)
  needs explicit "still accurate" confirmation before Batch 2 ships it as
  fact (`04`).

## What remains blocked or unverified from this pass specifically

- Exhaustive route rendering: only the three named pilot routes (plus
  current-app equivalents) were live-rendered; the remaining ~30 legacy
  routes and 4 current routes are static-code evidence only (`01`).
- Legacy dynamic data behavior (pricing, availability, hot deals) could not
  be exercised because the legacy backend was not running in this
  environment (`02`) — every legacy screenshot is shell/design evidence
  only, not a proof of legacy runtime correctness.
- Accessibility (contrast, keyboard, screen-reader, reduced-motion) was not
  audited beyond noting that it must not be assumed from the legacy repo's
  own WCAG claim (`03`).
- The booking/payment backend contract (`hub/online-bookings` payment
  wiring) was not traced past the route signature level (`05`, risk #4
  above).
- No tablet viewport was captured (`02`).
- Full field-by-field PII diffing of every response payload (beyond the
  fields explicitly named in `05`) was not performed.

Asset-level hash deduplication, previously listed here as unverified, was
completed during this correction pass and is no longer open (see `03`).

None of the above blocked items were worked around by assumption; each is
listed here specifically so a future session does not have to rediscover
that it's unverified.
