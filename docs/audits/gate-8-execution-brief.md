# Gate 8 Execution Brief — Secure QR Menu and Guest Service

## Control

- **Status:** implementation complete and automated acceptance verified on
  2026-07-22; physical camera/printed-QR field acceptance remains pending
- **Owner:** Mohamed
- **Implementation engineer/reviewer:** Codex in one continuous owned worktree;
  final acceptance remains Mohamed's decision
- **Base commit:** `dfa7e1e`
- **Branch/worktree:** `gate-8-qr-guest-service-completion` at
  `/home/wego/projects/resort-os`
- **Accepted direction:** Decision 0001 plus Mohamed's 2026-07-22 approval to
  complete all four bounded phases below and correct the inherited A/B/C work
  where required

## Product outcome

A guest scans one locally generated QR at a physical service location, sees
the correct El Kheima context, chooses an active dining outlet available at
that branch, browses its menu, and requests waiter service without an account.
The guest can safely recover request status after retries or a weak connection.
Staff see a branch-scoped, assignable queue and cashiers can monitor bill
requests. A service request alone never creates a kitchen or financial effect.
Self-order remains disabled by default and, if explicitly enabled later, uses
the same trusted QR/session context rather than raw public location IDs.

## Starting evidence

- Gate 8 Batch A (`7b03ff5`) repaired GuestAlert context validation and added
  sequential deduplication/cooldown.
- Gate 8 Batch B (`dfa7e1e`) added `ServiceLocationToken`, mint/rotate/resolve
  endpoints, and migration `5fed6e302861`.
- Inherited uncommitted Batch C/D/E work makes public alert creation token-based,
  lists active tokens for the QR screen, exposes the self-order gate state, and
  adds four-locale strings.
- Existing reusable parts: `VenueTable`, `BeachLocation`, `Room`, `GuestAlert`,
  Dining public menu/order services, `GuestAlertsBell.vue`, the authenticated
  branch checks, the shared API client, public locale runtime, and the installed
  local `qrcode` package.
- Verified baseline on 2026-07-22: `agent-check.sh` PASS; 2,061 tests collected;
  targeted Gate 8 tests 64/64 PASS; full backend suite 2,028 passed + 33 skipped.
- Gaps verified in code: no task-specific Gate 8 brief; no guest session or
  safe public status recovery; token rotation and alert dedupe are not
  concurrency-safe; the resolver exposes internal context IDs and does not
  return validated outlet choices; the current QR generator sends URLs/tokens
  to third parties; the public page still uses raw outlet/table routes; staff
  status/assignment/fallback/cashier handling is incomplete.

## Implemented outcome (2026-07-22)

- Added opaque guest sessions whose bearer value is returned once and stored in
  the database only as SHA-256. Every public mutation revalidates the live QR,
  branch, physical location, and expiry; rotating a QR revokes its sessions.
- Replaced public trust in branch/table/order/request IDs with `/s/:token`, a
  safe context response, backend-derived active outlets, random public
  references, and session-bound menu/order/status contracts.
- Added database-backed concurrent uniqueness for one active QR per physical
  location and one active request per location/type, plus idempotent retry,
  request expiry, rate limits, row locking, assignment ownership, state
  transitions, and secret-free audit events.
- Kept `view_and_call` as the default. Optional self-order remains disabled by
  default and requires both deployment and branch flags; when enabled it uses
  the same guest session and existing Dining financial transaction.
- Rebuilt guest, staff, cashier, and QR-admin UX: four service actions, status
  recovery, Arabic/English operational flow, public four-locale direction,
  local `qrcode` render/print/download, explicit rotation warnings, staff
  labels/assignment/arrive/resolve, WebSocket plus polling fallback, and bill
  auto-resolution inside successful payment.
- Added migration `8c12d9e4f6a1`; it preserves historical rows, reconciles
  pre-existing duplicates deterministically, and installs the new partial
  uniqueness constraints on SQLite and PostgreSQL.

## Confirmed decisions

1. One QR represents one physical service location. For a shared dining table,
   the guest may choose among active outlets that the backend derives from the
   token's trusted branch. The client cannot select a branch or table.
2. Public URLs contain only a high-entropy rotatable token (`/s/:token`).
3. QR images are rendered locally with the repository's installed `qrcode`
   package; no token or guest URL is sent to a third party.
4. `view_and_call` is the default. Self-order is false by default and may only
   operate through a validated guest session when both deployment and branch
   settings explicitly enable it.
5. Public retains its independent Arabic/English/Italian/Russian locale policy;
   the operational acceptance journey is verified at minimum in Arabic and
   English.
6. No existing development QR fleet needs backward compatibility, but existing
   database rows and old staff/POS contracts must be preserved safely.

## Phased scope

### Phase 8A — Trusted backend foundation

- Forward-only migration for guest sessions, request public references,
  assignment/state timestamps, optional outlet/order links, concurrency-safe
  uniqueness, and Dining guest-session linkage.
- Token-aware public session/context/menu/order/status APIs with no trusted raw
  branch/table IDs from the client.
- Active-location checks, safe rotation/revocation behavior, audit events,
  explicit transition rules, idempotency and concurrent deduplication.

### Phase 8B — Guest scan and view-and-call

- `/s/:token` route, outlet selection derived from the trusted branch, public
  menu, four service actions, safe request-status polling/recovery, weak-network
  feedback, and cart visibility only when self-order is explicitly enabled.
- No public request ID enumeration and no kitchen/financial side effect from a
  service request.

### Phase 8C — Staff, cashier, and QR administration

- Local-only QR mint/render/print/download/rotate UI.
- Staff queue with real location/outlet labels, accept/arrive/resolve ownership,
  Arabic/English staff i18n, polling fallback, and request-bill emphasis.
- Link an active table order safely and auto-resolve the matching bill request
  after a successful Dining payment in the same controlled workflow.

### Phase 8D — Evidence and handoff

- HTTP, negative, retry, migration, PostgreSQL concurrency, frontend component,
  type-check/build, and end-to-end flow evidence.
- Update `wagdy.md`, `PROJECT_STATUS.md`, and curated cockpit snapshots only
  after the behavior is verified.

## Explicitly out of scope

- Enabling self-order in production by default.
- Guest card/payment collection, push notifications, printers, analytics, or
  a new microservice/message broker.
- Destructive replacement of `VenueTable`, `BeachLocation`, or `Room`.
- Multi-outlet items on one financial order; the previously documented revenue
  attribution decision remains separate.
- Production deployment, physical QR printing, commit, or push.

## Invariants

### Data and finance

- At most one active QR token per `(branch, location_type, location_id)` under
  real concurrency.
- At most one unresolved request of the same type for the same guest/location;
  retries with one idempotency key return one result.
- A request never opens an order, sends a KDS ticket, posts a journal, touches a
  shift, or changes inventory by itself.
- Optional self-order continues through the existing Dining service and Gate 4
  financial controls; guest status access is bound to its guest session.

### Authorization and audit

- Manager+ may mint/rotate/list tokens only for an accessible branch.
- Waiter+ may view and act on requests only for an accessible branch.
- Assignment prevents one waiter silently completing another waiter's request;
  a manager override must be attributable.
- Token lifecycle, request state/assignment/order linkage, and automatic
  payment resolution produce existing `AuditLog` events without secrets.

### API and compatibility

- Staff/POS APIs remain compatible unless a stronger response is additive.
- Legacy raw public QR routes are not used by generated codes and do not regain
  unsafe order-status access.
- Public responses may expose display labels and validated outlet choices, but
  URLs expose no internal branch, table, beach-location, room, order, or request
  identifiers.

### UX, Arabic, and accessibility

- Guest primary device: mobile browser after camera scan.
- Arabic RTL and English/Italian/Russian LTR come from the public locale runtime;
  staff Arabic/English come from the staff runtime with no forced `dir`.
- Loading, invalid/rotated QR, disabled location, empty menu, duplicate tap,
  offline/retry, missed realtime event, and expired session states are explicit.
- Touch targets, focus, button labels, status text, and screen-reader semantics
  must remain usable.

## Migration plan

- Add a forward migration after `5fed6e302861`; do not rewrite the committed
  migration.
- Preserve all existing token and GuestAlert rows. New public/session fields are
  nullable for historical rows and required by new service paths.
- Add partial/conditional uniqueness and indexes with compatible SQLAlchemy
  metadata plus explicit SQLite/PostgreSQL behavior.
- Validate upgrade/downgrade/upgrade and concurrency on an isolated PostgreSQL
  database; never use destructive experiments on production.

## Acceptance criteria

1. Scanning `/s/{token}` produces only token-derived location and validated
   active-outlet choices; invalid, rotated, or disabled locations fail safely.
2. Four rapid/retried/concurrent identical requests create one unresolved row
   and return one stable public reference.
3. A guest can reload and recover requests from a still-valid session at the
   same physical location (needed for location-wide deduplication); order
   status remains strictly limited to the exact unexpired issuing session.
4. Staff outside the branch cannot see or act on the request; two waiters cannot
   both claim it; allowed manager override is audited.
5. A bill request is visible to the cashier and resolves after successful
   payment, while a call/assistance request alone has zero financial/KDS effect.
6. QR render/print/download succeeds with network calls to no QR/CDN service.
7. Arabic and English complete scan-to-close flows work on mobile and after a
   simulated connection interruption.

## Validation evidence

- Targeted Gate 8, public-menu/order, payment, and configuration regressions
  pass, including disabled/rotated location, token hashing, retry, stale
  expiry, ID injection, assignment theft, and bill-payment audit cases.
- A scoped real-PostgreSQL race produced exactly one commit and one uniqueness
  conflict for both concurrent active-QR creation and concurrent active-request
  creation; the temporary branch was removed afterward.
- The forward migration was applied to the local PostgreSQL development
  database and Alembic reports one head. The repository still has known legacy
  autogenerate drift outside this Gate 8 migration, so `alembic check` is not
  claimed as clean.
- Full backend suite passed 2,036 + 33 skipped from 2,069 collected; frontend
  passed 60/60 tests and 5,438-key Arabic/English parity while preserving the
  public Arabic/English/Russian/Italian policy. Both production builds/type
  checks, Compose development/production configs, byte-compilation,
  `agent-check.sh`, and `git diff --check` passed.
- Not performed: physical phone-camera scan, printed-code field trial,
  production deployment, or isolated downgrade/upgrade rehearsal. Gate 8 is
  therefore code-complete with automated acceptance, not production-certified;
  those physical/deployment checks belong to the remaining handoff/Gate 9.

## Stop conditions

Stop for Mohamed only if implementation requires destructive live-data loss,
production credentials, real QR printing/deployment, an external purchase, or
an irreversible business decision not covered above.

## Handoff

Report exact changes, migrations, compatibility, security/finance/RTL/a11y
impact, exact check results, residual risks, and confirm no commit/push unless
Mohamed separately authorizes them.
