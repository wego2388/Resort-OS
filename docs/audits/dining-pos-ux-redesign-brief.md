# Dining POS UX Redesign — Execution Brief

**Branch:** `dining-pos-foodics-ux-redesign`
**Base:** `dfa7e1e`
**Workspace:** `/home/wego/projects/resort-os-pos-redesign`
**Status:** Implemented and verified

## Objective

Rebuild the El Kheima cashier experience into a fast, legible, touch-friendly
workflow that is at least as easy to operate as modern restaurant POS systems,
while preserving Resort OS dining, PMS, CRM, offline, authorization, and
financial contracts.

The result must reduce navigation and reopen steps for the cashier, keep the
current order and total visible, and make tables, active orders, customers, and
payment first-class workspaces instead of stacking all of them into one crowded
screen.

## In scope

- A workspace shell for tables, order entry, and active orders.
- A persistent order-entry layout with category navigation, large product
  targets, search, and a stable cart/totals panel.
- A larger active-orders workspace with useful state, outlet, type, table, and
  elapsed-time context.
- A direct path from cart creation to the resulting order and payment, without
  forcing the cashier to rediscover the order.
- A payment experience for exact single tender and existing atomic split tender
  contracts, including cash received/change assistance and checked-in room
  lookup for room charge.
- Customer lookup by name or phone and attaching `customer_id` to order creation.
- Arabic and English copy, direction-safe layout, keyboard/touch accessibility,
  and responsive behavior for 1366x768 desktop and tablet landscape.
- Focused frontend tests and documentation/status updates.
- A targeted Timeshare UX/UI redesign pass covering both light and dark
  themes, responsive density, hierarchy, actions, tables/cards, and empty,
  loading, and error states.
- A staff-app visual consistency sweep: fix concrete theme, contrast,
  overflow, touch-target, or hierarchy defects discovered while reviewing the
  shared shell and reachable operational screens. The final light/dark pass
  covers every staff Vue screen and shared UI primitive, following explicit
  approval to correct the full reachable surface.

## Financial and operational invariants

- The backend remains the source of truth for subtotal, VAT, service, delivery,
  discounts, totals, status transitions, table occupancy, and settlement.
- Direct and split payment continue to use the existing Dining Gate 4 endpoints,
  idempotency semantics, exact tender validation, open-shift rules, PIN/step-up
  policies, authorization, and audit behavior.
- A room charge may target only a real room selected from PMS context; the UI
  must not present a raw internal-ID field as the normal workflow.
- Offline order capture remains supported. Payment is never presented as
  successful while offline and is never placed in the order offline queue.
- Branch and outlet scoping remain explicit. Shared branch tables must not be
  accidentally narrowed to a single outlet.
- Frontend calculations such as cash change and split remaining are interaction
  aids only; the server validates and records all money.
- Existing Gate 8 QR work in the original worktree is outside this branch and
  must remain untouched.

## Planned implementation surface

- `frontend/apps/el-kheima/src/views/pos/UnifiedPOSView.vue`
- `frontend/apps/el-kheima/src/components/DiningOrderDetailModal.vue`
- New focused components under
  `frontend/apps/el-kheima/src/components/dining-pos/`
- `frontend/packages/core/src/i18n/locales/ar.json`
- `frontend/packages/core/src/i18n/locales/en.json`
- `frontend/apps/el-kheima/src/views/admin/TimeshareView.vue`
- Shared staff-app theme/layout styles or UI primitives only when a proven
  cross-screen defect is best fixed at its source
- Relevant frontend unit/component tests and i18n validation ratchets
- This execution brief and the i18n/test validation ratchets

Backend changes are not planned. They are allowed only if implementation proves
that an existing documented contract is missing or unsafe; any such change must
be narrow and separately tested.

## Acceptance criteria

- Tables and menu no longer compete vertically on the same crowded screen.
- The current cart, item count, total context, and primary action remain visible
  during order entry without page scrolling at the target desktop size.
- Operational tap targets are at least 44px, normal operational text is legible,
  and status is communicated with text as well as color.
- An occupied table opens its active order; an available table starts an order.
- After creating/sending an order, the cashier can continue to order detail or
  payment without reopening the active-orders list.
- Active orders are searchable/filterable and show enough context to distinguish
  similarly timed orders.
- Cash payment shows exact/change assistance; card and wallet remain fail-closed
  according to backend configuration; room charge uses checked-in guest/room
  context; split tenders must sum exactly to the server total.
- Customer lookup uses human identifiers (name/phone), not raw database IDs.
- All new reachable staff copy is present in Arabic and English and no component
  hardcodes document direction or locale-specific currency formatting.
- Empty, loading, error, offline, and narrow-screen states remain usable.

## Validation

- Focused frontend tests for order-workspace state, payment/split calculations,
  room/customer selection, and i18n keys.
- Type checking and production frontend build.
- Repository whitespace/i18n checks.
- Full `scripts/agent-check.sh` before handoff, with any unrelated or
  environment-only failure reported honestly.
- Manual browser inspection at 1366x768 and a tablet-landscape viewport when the
  local stack can be started safely.
- Timeshare visual inspection in Arabic/English and light/dark themes at desktop
  and tablet widths, plus a targeted staff-shell contrast/overflow sweep.

## Out of scope

- Replacing backend pricing or payment services.
- Introducing a new loyalty-redemption financial contract.
- Hardware integrations, real payment-terminal certification, or production
  deployment.
- A wholesale redesign of every staff screen without a concrete defect found
  during the bounded visual audit.
- Committing, pushing, merging, or changing the separate Gate 8 branch.

## Delivered

- Replaced the crowded POS page with three explicit workspaces: tables, order
  entry, and active orders.
- Added a stable cart, responsive mobile cart sheet, customer lookup, outlet and
  order-type guards, shortcut keys, direct order-detail continuation, and safe
  offline behavior.
- Added a server-backed payment flow for cash, card, wallet, checked-in room
  charge, and exact 2–10 tender split payment with idempotency-key reuse.
- Rebuilt dining order detail as a drawer while preserving transfer, merge,
  item void, item refund, discounts, kitchen status, service, and payment.
- Reworked Timeshare hierarchy, responsive overflow, cards, tables, filters,
  loading/empty states, touch targets, currency/date formatting, contract
  pagination, and light/dark contrast.
- Made FieldLayout genuinely light/dark instead of permanently dark, and fixed
  direction/i18n/contrast defects at their shared source in theme, command,
  autocomplete, combobox, wizard, empty-state, and money-input primitives.
- Migrated guest alerts, manager PIN, cash control, invoice log, and legacy
  extras selection to inherited direction, Arabic/English copy, and dark-mode
  safe styling.
- Replaced the mixed navy/brown staff dark palette with a coherent slate/navy
  token set, defined inherited page/form foreground colors, and added explicit
  dark variants for every pale semantic status surface (`50`/`100`/`200`) in
  the staff app and shared UI package.
- Corrected low-contrast status text across dashboard, beach, reception,
  rooms, bookings, finance, HR, CRM, analytics, inventory, settings, account,
  and employee portal views. Added automated WCAG token checks and source-level
  guards that reject future pale semantic cards without a dark counterpart.

## Verification result

- `pnpm --filter el-kheima test:frontend`: **69 tests passed** across nine
  files, including exact-money/split-allocation tests, the existing
  accessibility suite, and three new staff-theme contrast guardrails.
- i18n gate: **5,690 keys per locale**, exact ar/en parity, no placeholders,
  and **55 strict reference files**.
- `pnpm --filter el-kheima type-check`: passed.
- `pnpm --filter el-kheima build`: passed; PWA generated with 75 precache
  entries. Vite reports the existing non-blocking main-chunk size warning
  (`676.51 kB`, `238.20 kB` gzip); the lazy POS view chunk is `86.89 kB`
  (`22.09 kB` gzip).
- `bash scripts/agent-check.sh`: passed; one Alembic head, 2,059 backend tests
  collected, development and production Compose configs valid, and whitespace
  clean.
- Live browser inspection passed against the stable branch backend and the
  existing development database without a reset or seed mutation. Dashboard,
  Beach Admin, Timeshare, Rooms, Reception, and Finance were inspected at
  1600x900; representative light and dark states now use coherent surfaces and
  readable foreground/status colors. The earlier authentication error belonged
  to the separate, incomplete Gate 8 worktree backend rather than this branch.
