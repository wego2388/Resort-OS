# Decision 0004: Owner Intelligence Cockpit

- **Status:** Accepted product direction; implementation not started
- **Date:** 2026-08-07
- **Owner:** Mohamed
- **Product:** El Kheima Beach Resort OS

## Context

Mohamed wants a dedicated application for the resort **owner** — not a second
super admin, not an operational role, not a page bolted onto the staff app.
The owner needs to see the true state of the business (accounting-accurate
revenue, profit, expense, and purchasing detail), understand why it is what
it is, see risk and opportunity before they become a crisis, and estimate the
effect of a hypothetical decision — without being able to create, edit,
approve, or cancel anything. The experience must be mobile-first (the owner
mainly opens it on a phone), pull-based (he opens the app and finds what he
needs; the product does not push reports over WhatsApp), and must feel like a
distinct, professional analytical product rather than a reskinned page from
`el-kheima`.

This record follows the same discipline as
`docs/decisions/0003-super-admin-control-plane.md`: it defines the accepted
direction and its non-negotiable invariants. It is not a claim that any of it
is built yet.

## What this is deliberately not

- **Not a second super admin and not a control plane.** The owner role has no
  authority over users, roles, permissions, settings, or any operational
  workflow. Decision 0003's invariants are untouched by this record.
- **Not a new business domain**, unlike `timeshare`. `timeshare_admin` is
  isolated because it owns a genuinely separate slice of data. The owner role
  owns almost no data of its own — it is a read-only aggregation layer over
  every existing module, plus a thin, explicit configuration surface (cost
  allocation rules the owner approves, a watchlist of pinned metrics). It
  must not accumulate a parallel set of business tables.
- **Not a second calculation engine.** Every figure shown to the owner is
  produced by calling the same finance/dining/inventory/beach/pms/timeshare
  service functions every other part of the application already calls for
  that number. Nothing is recomputed independently. If an owner-facing number
  and an accountant-facing number can ever diverge, that is a defect in this
  feature, not an acceptable rounding difference.
- **Not delivered by push.** No WhatsApp report delivery, no proactive
  messages for routine content. The owner opens the product and finds
  everything current. The one legitimate exception is a security notification
  for a new-device login on the owner's own account — that protects his
  account, it is not a business report.
- **Not built on a new heavy dependency.** The project has no `pandas` or
  `numpy` today and does not need them at single-resort data volumes. Every
  "smart" computation this record calls for (ABC/Pareto classification, item
  margin, trend/variance detection) is achievable with the standard library
  (`decimal`, `statistics`) combined with the project's existing SQL
  aggregation idiom, consistent with `resort_os/food_cost_engine.py` and
  `resort_os/discount_engine.py`.

## Scope

1. **Now** — a single mobile screen: today's revenue, today's expense, net
   cash position, collections by tender, current and forecast occupancy,
   overdue receivables, all sourced live from the same reports staff use.
2. **Performance** — day/week/month/year comparisons and prior-period /
   prior-year comparisons, computed by calling the existing report functions
   twice (or across a range) and diffing, not by a separate comparison
   engine.
3. **Sales / product performance** — which products and services actually
   sell and actually make money: ranked lists, ABC/Pareto classification,
   real per-item margin where recipe costing exists, trend direction per
   item.
4. **Expense analytics** — every expense category as a percentage of
   revenue over time (not absolute figures alone), with automatic variance
   flags when a category's share of revenue moves abnormally.
5. **Procurement / purchasing analytics** — spend concentration by supplier,
   price trend per purchased product over time, purchase-request-estimate
   vs. purchase-order-actual variance.
6. **Unit economics** — profit per room-night, beach unit, table/dish, and
   timeshare unit, computed only after Mohamed approves the cost-allocation
   rules that make the computation meaningful (see "Unit economics
   preconditions" below). Never invented by the system.
7. **Exceptions** — an always-current, severity-ranked list of things that
   deserve the owner's attention, generalized from the existing fraud/anomaly
   detection pattern already running in `app/tasks/fraud_tasks.py`.
8. **Narrative intelligence** — short, citable, auto-generated explanations
   attached to the numbers above, produced by an AI layer that explains
   deterministic results; it never computes a financial figure itself.
9. **Ask your business** — a free-form question box, answered only through a
   fixed allowlist of read-only tools over the same aggregation layer.
10. **Scenario sandbox** — transparent, assumption-based projections
    ("if X changes and Y stays fixed, the range is A–B"), explicitly not a
    trained forecasting model in the first version.

Items 1–5 and 7 are the core of the product and should be built first. Items
6, 9, and 10 depend on items 1–5 and on explicit Mohamed sign-off where noted,
and should be sequenced after the core is solid — this is a Priority #3 (new
feature) initiative under `CLAUDE.md` §2 and must not be allowed to crowd out
Priority #1/#2 work without Mohamed's explicit say-so for this initiative.

## Isolation model (non-negotiable invariants)

1. **Role.** A new `owner` role is added to `ROLE_LEVELS` in
   `backend/app/core/deps.py` **and** the matching table in
   `frontend/packages/core/src/stores/auth.ts` (the shared `ROLE_LEVELS`
   consumed by every frontend app, not a per-app copy), per the existing rule
   that the two must stay identical (`CLAUDE.md` §13 item 5). Its numeric
   level is placed low — **below `employee` (20)** — specifically so it can
   never accidentally satisfy an existing `>= N` level check anywhere else in
   the application. This mirrors, and is stricter than, the documented
   reasoning behind `timeshare_admin`'s deliberate `level=55` placement.
2. **Dependency.** `get_owner_user` in `deps.py` authorizes by **direct role
   name match** (`user.role == "owner"`), the same mechanism already
   documented for `get_timeshare_admin_user`, not by a level threshold. The
   frontend must mirror this exactly: `ROLE_LEVELS`/`hasRole()` in
   `stores/auth.ts` is for generic display/guard use only — real access to
   the owner app's routes is gated by a direct role-name check in the new
   `frontend/apps/owner`'s own `router/index.ts` (`requiredRoles`), the same
   two-layer pattern already used for `timeshare_admin` (confirmed in
   `stores/auth.ts`'s own comment on that role).
3. **Mandatory 2FA.** Add `"owner"` to `MANDATORY_2FA_ROLES` in `deps.py`.
4. **Central write block — the critical control.** Level isolation alone is
   **not sufficient**: a code audit for this record found real mutating
   endpoints (for example `POST /crm/customers`, `PATCH /crm/customers/{id}`,
   `POST /beach/transactions/{id}/void`, and others across `crm`, `beach`,
   `hub`, `inventory`) authorized only by `get_current_active_user`, i.e. any
   active session regardless of role level. A low `owner` level does not
   protect against these. The implementation must add one central
   enforcement point — a dependency or middleware applied to every route,
   not a per-endpoint decoration — that rejects any `POST`/`PUT`/`PATCH`/
   `DELETE` request from `role == "owner"` **except** an explicit, short
   allowlist: the owner's own profile, 2FA/session management, and the
   owner's cost-allocation-rule endpoint (the one legitimate write, see
   below). This must be provable by a project-wide test, not spot checks.
5. **Read-only database access.** The `owner` router must not be able to
   mutate data even if the central write block above had a bug. Use a
   dedicated PostgreSQL role with `SELECT`-only grants for the connection/
   session the owner API uses (a second engine bound only to
   `app/modules/owner/`), or a read replica if one becomes available first.
   This is defense in depth on top of item 4, not a replacement for it.
6. **Audit.** Every owner login, report view, drill-down, export, and chat
   query is written to the existing `audit_logs` table (`AuditLog` model in
   `app/modules/core/models.py`) using distinct `action` values. No second
   audit table — the project has an explicit, documented decision against
   that (see `fraud_tasks.py`'s module docstring).
7. **No new PII exposure.** Payroll appears as an aggregate and a percentage
   of revenue by default, never itemized per employee. An employee's name
   appears only when directly tied to a flagged exception (for example a
   cashier fraud signal), never as general roster access. Guest personal
   data is not surfaced beyond what an exception genuinely requires.

## Numbers must equal the source of truth

Every figure the owner sees is produced by calling the existing report
functions directly:

- `finance/reports/income-statement`, `.../balance-sheet`,
  `.../trial-balance`, `finance/cost-centers/report`, `finance/periods`,
  `finance/journal-entries` for anything accounting-related.
- The generalized sales-performance service (see below) for product/service
  performance.
- `inventory` supplier/purchase-order/stock-movement records for procurement
  analytics.

Each number carries: the period it covers, whether that period is closed
(posted) or still open/provisional (from `finance/periods`), and a
computed-at timestamp. The owner cockpit must never present a provisional
number as if it were final.

## New engineering surface

- **`app/modules/owner/`** — a normal module following the project's
  five-layer convention (`models.py`, `schemas.py`, `crud.py`, `services.py`,
  `api/router.py`). Its own tables are limited to `OwnerAllocationRule`
  (versioned — see "Unit economics preconditions") and `OwnerWatchlist`
  (pinned metrics/preferences). No other domain tables.
- **`app/resort_os/owner_analytics_engine.py`** — a pure engine (no FastAPI
  or SQLAlchemy imports, matching `food_cost_engine.py`/`discount_engine.py`)
  containing: ABC/Pareto classification, per-item margin computation given
  recipe-cost and sale-price inputs, and trend/variance detection using
  `statistics` from the standard library. This is where "smart" analysis
  lives — not a new dependency, not scattered inline SQL.
- **`OWNER_EXCEPTION_RULES`** — a single catalog dict inside the owner
  module, following the exact pattern already established by
  `app/modules/core/policy_engine.py`'s `SENSITIVE_ACTIONS` and
  `permission_catalog.py`: one place that defines every exception rule's
  key, label, source, severity tier, and impact calculation. Ranking is
  **tiered first** (`critical` / `attention` / `watch`, with operational
  safety issues hard-pinned to `critical` regardless of financial size),
  then sorted by `impact × confidence` inside each tier. Every exception is
  tagged `realized` / `projected` / `potential`. Reuse
  `app/tasks/fraud_tasks.py`'s existing signals as one exception source
  instead of duplicating fraud detection.
- **Sales performance service** — generalizes the existing `top_items`
  query in `app/modules/dining/api/router.py` (currently inline in one
  endpoint, dining-only, ranked by quantity only, and using `float()` for
  money) into a reusable, multi-outlet service that ranks by revenue and
  margin as well as quantity, and uses `Decimal` throughout — the `float`
  usage in the current code must not be copied forward.
- **Narrative + ask-your-business** — a new, isolated Gemini integration
  under `app/modules/owner/`. It must **not** share `app/modules/chat`'s
  conversation state, rate-limit counters, or cost budget — separate config,
  separate keys, so heavy owner usage cannot degrade the guest-facing
  assistant or vice versa. Tool-calling is restricted to an explicit
  allowlist of the read-only owner service functions above — never raw SQL,
  never direct model access. The same hardening already proven for `chat`
  during its CL-01 pass is a **mandatory baseline, not optional**: escaped
  rendering (no unsanitized `v-html`), a daily request cap per session, a
  circuit breaker on upstream failure, and no PII/secrets ever entering the
  prompt.
- **Frontend** — a new pnpm workspace app, `frontend/apps/owner`, the third
  app alongside `el-kheima` and `public`. Mobile-first PWA, dark-first,
  card-based, sparkline-driven design system distinct from the staff
  BackOffice. It reuses only `@resort-os/core` (API client, auth store) and
  genuinely generic parts of `@resort-os/ui` (currency/date formatting,
  i18n/RTL, accessibility primitives) — no BackOffice layout or components.
  The router must refuse to render for any non-`owner` session client-side,
  as a second layer on top of the backend's 403.

## Unit economics preconditions

Per-unit profitability (room-night, beach unit, table/dish, timeshare unit)
is only shown once Mohamed has explicitly approved, through the owner's own
`OwnerAllocationRule` screen, how to allocate: utilities, shared payroll,
room/equipment depreciation, shared beach cost, and channel commission per
booking source. The system never invents these percentages. Allocation rules
are **versioned**: a rule change takes effect for periods from that point
forward; historical unit-economics figures continue to use the rule that was
in force when they were computed, so a later policy change cannot silently
rewrite the past.

## Controlled implementation sequence

Each phase is a separate, independently reviewable diff/commit and must meet
the project's existing Definition of Done (`CLAUDE.md` §3.8 / `AGENTS.md`
§8) before the next phase begins. No phase includes a production deployment.

1. **Phase 0 — Isolation and safety rails (backend only, no owner-facing
   data yet).** `owner` role + `get_owner_user` + `MANDATORY_2FA_ROLES` +
   central write block + read-only DB session + `app/modules/owner/`
   skeleton with only `OwnerAllocationRule`/`OwnerWatchlist`. Prove
   isolation before anything else is built on top of it.
2. **Phase 1 — Read-only aggregation services.** Wrap existing finance
   reports; build the generalized sales-performance service (with the
   `Decimal` fix); build procurement and expense-analytics services. No new
   endpoints yet — service-layer only, covered by tests that assert byte-
   for-byte agreement with the underlying finance/dining functions.
3. **Phase 2 — Exceptions engine.** `OWNER_EXCEPTION_RULES` catalog, tiered
   ranking, integration with `fraud_tasks.py` signals.
4. **Phase 3 — Owner API surface (`/api/v1/owner/*`).** Wire Phases 1–2
   into endpoints behind `get_owner_user` and the read-only session.
5. **Phase 4 — Narrative + ask-your-business.** Isolated Gemini
   integration, tool allowlist, CL-01-equivalent hardening and red-team
   tests.
6. **Phase 5 — Frontend: Owner PWA.** Now / Performance / Exceptions
   screens, drill-down, mobile interaction patterns.
7. **Phase 6 — Unit economics.** Only after Mohamed approves initial
   allocation rules through the Phase 0 screen.
8. **Phase 7 — Scenario sandbox.** Lowest priority; transparent,
   assumption-based ranges only.
9. **Phase 8 — Independent security/authorization review and production
   readiness gate.** A dedicated review of the central write block and
   read-only isolation specifically (mirroring Decision 0003's own closing
   step), plus the complete validation contract in `AGENTS.md` §8.

## Required tests and acceptance criteria

- An `owner` session fails every existing `get_waiter_user` /
  `get_cashier_user` / `get_manager_user` / `get_admin_user` /
  `get_super_admin_user` check in the application (regression sweep).
- A parametrized test iterating the OpenAPI schema's mutating routes proves
  an `owner` session receives 403 from all of them except the explicit
  allowlist.
- Every owner-facing figure equals the corresponding finance/dining service
  function's return value exactly, for a seeded scenario (`Decimal`
  equality, not approximate).
- ABC/Pareto classification is deterministic and handles empty input, a
  single item, and all-equal values without error.
- Exception ranking places a `critical`-tier, small-value item above an
  `attention`-tier, large-value item.
- Allocation-rule changes never alter previously computed unit-economics
  figures (versioning proof).
- Narrative sentences carry structured citation metadata (period, source,
  computed-at, confidence) alongside the generated text.
- The ask-your-business chat rejects any tool call outside its allowlist,
  and a red-team suite mirroring `chat`'s CL-01 pass (prompt injection,
  secret/PII leakage, daily cap, circuit breaker) is green.
- The owner frontend's router blocks a non-owner session client-side; a
  Playwright walkthrough (login → Now/Performance/Exceptions → drill into a
  real seeded number) shows correct data and zero console errors.
- Full backend suite green, single Alembic head with a proven
  upgrade/downgrade cycle, and `pnpm run type-check:all` /
  `pnpm run build:all` clean — before any phase is marked complete.

## Work instructions for the implementing agent

- Read `AGENTS.md`, `CLAUDE.md`, and this record fully before touching code.
  This record does not repeat the repository's standing engineering rules
  (layering, `Decimal` for money, migration discipline, etc.) — they apply
  in full.
- Work one phase at a time, in order. Do not start a phase before the
  previous phase's Definition of Done is met, committed, and (if the user
  requests it) reviewed.
- Run the full validation contract (`AGENTS.md` §8: backend pytest, Alembic
  heads, frontend type-check/build) once at the completion of each phase —
  not after every small edit, and not skipped at the end of any phase.
- **Do not deploy anything to the VPS during Phases 0–7.** Deployment is
  only in scope after Phase 8's independent review passes, and only with
  Mohamed's explicit authorization for that specific release, per the
  standing rule in `AGENTS.md` §6/§7 that commit/push/deploy require the
  current user's explicit authorization.
- If a required business input is missing (most likely: the cost-allocation
  percentages for unit economics), stop and ask Mohamed. Do not invent
  master data.
- Update this record's "Current status" section and `PROJECT_STATUS.md`
  only when a phase is actually merged and verified — not in advance of the
  work.

## Current status

Direction accepted 2026-08-07 after an extended design discussion with
Mohamed covering scope, isolation model, analytics depth, and delivery
experience. No implementation has started. Phase 0 has not begun.
