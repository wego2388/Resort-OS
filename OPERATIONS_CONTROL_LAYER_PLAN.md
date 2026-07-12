# Operations & Control Layer — Audit, Reconciliation & Phased Plan

> **Status:** audit complete, no implementation done except where explicitly noted.
> **Source spec:** `wagdy.md` lines ~910–1565 ("Operations & Control Layer").
> **Purpose of this document:** map every piece of that spec against code that
> was already shipped 2026-07-07…07-11 (Shift System, PIN system, Discount
> Engine, Permission Catalog), so nobody rebuilds a parallel/competing system.
> **This document is a plan, not a change.** Per CLAUDE.md §15, anything here
> that touches auth/permission/money flows needs Mohamed's explicit sign-off
> before a batch starts — see §5.

---

## 1. Already satisfied

These spec items are **fully covered by existing, shipped code**. Do not
rebuild them under a new name.

### 1.1 "Officer PIN Approval" pattern (Discount / Void / Refund / Shift Close)

The spec's diagram — `Discount → Officer PIN → Reason → Audit`, with `Who
Requested / Who Approved / Time / Reason` recorded — is exactly what shipped
2026-07-07/08/11:

- **`PinCredential`** (`backend/app/modules/core/models.py:176`) — 4–6 digit
  bcrypt PIN, separate from the JWT/password login, 3-attempts/60s lockout
  (`PIN_MAX_ATTEMPTS`, `PIN_LOCKOUT_SECONDS` in `core/services.py:38-39`).
- **`core.services.resolve_pin_approval`** (`core/services.py:96-137`) — the
  single central gate. If the acting user's role level already clears
  `min_approver_level` (default 60 = manager+), no PIN is needed at all
  (self-qualified). Otherwise it requires `approver_user_id` + `approver_pin`,
  validates the approver is active and at/above the required level, verifies
  the PIN, and returns `approved_by` (or raises `ValueError` with a
  user-facing Arabic message).
- **`AuditLog.approved_by`** (`core/models.py:96`) — separate column from
  `user_id` (who executed) recording who approved, already populated by every
  caller below.
- **Wired into three real flows already:**
  - `restaurant.services.void_order_item` / `cafe` equivalent — cancel with
    reason (`OrderItemVoidRequest.reason` + `approver_user_id`/`approver_pin`,
    `restaurant/schemas.py:270-276`), gated by
    `require_permission("restaurant.void_order_item", "execute",
    min_role_level=40)` (`restaurant/api/router.py:492-494`).
  - `restaurant.services.refund_order_item` / cafe equivalent — same pattern,
    `min_role_level=60`.
  - `finance.services.close_shift` variance override (`finance/services.py:
    593-626`) — `force_close=True` + `approver_user_id`/`approver_pin`
    (`CashierShiftClose`, `finance/schemas.py:231-233`) writes
    `AuditLog(action="close_shift_variance_override")` with old/new numbers
    (`expected_cash`, `counted_cash`, `variance`, `reject_threshold`,
    `total_sales`) in `new_data`.
- **Frontend:** `PinGuardModal.vue` (`frontend/apps/el-kheima/src/components/
  PinGuardModal.vue`) — reusable, `min-level` prop, self-qualifies silently
  for managers+, shows approver picker + PIN pad otherwise. Used by
  `OrderDetailModal.vue` (void) and `InvoiceLogModal.vue`/shift-close flow
  (`S-03` in wagdy.md, already ✅).
- **`GET /pins/approvers`** (`core.services.list_eligible_approvers`,
  `core/services.py:60-67`) — populates the approver picker, filters by
  `ROLE_LEVELS >= min_level`, no PII beyond name/role.

**Conclusion:** wagdy.md's "Officer PIN → Reason → Audit" is not a new
concept to build — it is `resolve_pin_approval` + `PinGuardModal.vue`. Every
new sensitive action the spec lists (Price Override, Open Drawer, Cancel
Payment, Cash Adjustment, Transfer Bill, Split Payment, Manual Price) should
call the **same** function and reuse the **same** component, not a new
approval flow.

### 1.2 Operator switching (part of "Device/Session" spirit, not literal spec item)

`POST /pins/switch` (`core.services.pin_switch_login`, `core/services.py:
148-180`) — same-terminal operator switch without full logout/login, issues a
new JWT via the existing `create_access_token`. Capped at `PIN_SWITCH_MAX_ROLE_LEVEL
= 60` so it cannot be used to bypass mandatory 2FA on `super_admin`/
`accountant` (`MANDATORY_2FA_ROLES` in `core/deps.py:75`). Frontend:
`OperatorSwitchModal.vue`.

### 1.3 Permission model beyond simple Role

The spec asks for `Role + Permission + Outlet + Branch + Shift + Approval
Level`. Two of six axes are already real, generic infrastructure:

- **Role** — `ROLE_LEVELS` in `backend/app/core/deps.py:26-41` (mirrored in
  `useAuthStore.ts`), 14 roles, numeric levels 0–100.
- **Permission** (per-user override on top of role) — `UserPermission` model
  (`core/models.py:112-129`), scoped by `(user_id, resource, action,
  branch_id)`. `branch_id=NULL` = all branches, `branch_id=X` = one branch —
  **this already covers the spec's "Branch" axis** for every resource in the
  catalog, it is not a separate thing to build.
  `core.services.has_permission` (`core/services.py:356-383`): explicit
  grant/deny wins over role fallback; `require_permission()` dependency
  (`core/deps.py:231-259`) is the sole gate wired onto 10 sensitive
  operations across 8 modules (`core/permission_catalog.py` — single source
  of truth, cross-checked against real endpoints by convention, not
  aspiration — see the file's own docstring).
  Admin UI: `GET /permissions/catalog`, `GET /permissions/me`,
  `/admin/permissions` (super_admin only).
- **Approval Level** — `resolve_pin_approval`'s `min_approver_level` param
  *is* an approval-level concept already, just not yet tiered by discount %
  (see §3.1 below — that's the genuinely new part).

**Not yet real:** Outlet and Shift as first-class dimensions of the
permission grant itself (see §3 — this is additive, not a rebuild).

### 1.4 Shift Management

Spec asks for: open/close/suspend/resume/transfer/emergency-close/recount/
blind-count/safe-drop/cash-pickup/float.

- **Open/close/float/blind-count** — done. `CashierShift` model
  (`finance/models.py:114-141`), `open_shift`/`close_shift`
  (`finance/services.py:353`, `508`), `opening_float` field, blind-count
  guaranteed by `build_shift_end_report` never exposing `expected_cash` to
  the cashier before they submit `counted_cash`
  (`test_blind_cash_count_never_reveals_expected_cash_before_close`).
  Multi-currency cash counting: `CashierShiftCashCount`
  (`finance/models.py:143-164`).
- **X-Report** (mid-shift report without closing) —
  `GET /finance/shifts/{id}/report` (S-04, ✅).
- **Not built:** suspend/resume/transfer/emergency-close/recount/safe-drop/
  cash-pickup as distinct shift *states* or actions — today a shift is only
  `open`/`closed`. This is genuinely new (§3.2).

### 1.5 Discount Engine — most of the type/condition/scope taxonomy

`app/resort_os/discount_engine.py` is a pure domain engine (no FastAPI/SQLAlchemy),
already supports:

- **Condition types:** `total_amount`, `item_count`, `day_of_week`,
  `customer_group`, `time_of_day` (Happy Hour, midnight-spanning ranges via
  `_is_time_in_range`), `combo_items`.
- **Discount types:** `percentage`, `fixed_amount`, `free_item`,
  `combo_fixed_price`.
- **Scope:** `order | outlet | category | item` (`_is_scope_met`,
  `_scope_base_amount`) — a discount can be restricted to "cafe only",
  "desserts category", or a single item.
- **Rules:** `max_uses`, `valid_from`/`valid_until` (expiration), priority
  ordering with deterministic tie-break, `Decimal` throughout with
  `ROUND_HALF_UP`.
- **Endpoints:** `POST /cafe/orders/{id}/discount` and
  `POST /restaurant/orders/{id}/discount` — both apply the single
  best-matching active rule server-side (no manual amount entry, the cashier
  does not pick a rule). Shared frontend composable:
  `frontend/packages/core/src/composables/useOrderDiscount.ts`, called from
  both `RestaurantPOSView.vue`/`CafePOSView.vue` (`applyDiscountToCart()`,
  P-02 wagdy.md ✅) and `OrderDetailModal.vue`.

**This already covers, structurally, the spec's:** Percentage, Fixed,
Happy Hour, Corporate/VIP/Employee/Staff (via `customer_group` +
`scope_type`), Comp Meal-ish (via `free_item`), Promotion/Combo
(`combo_items`/`combo_fixed_price`). **What's missing is enumerated
explicitly and separately in §3.4** — do not read this section as "discount
engine is done," it means "the condition/scope taxonomy is done, several
named discount *categories* from the spec still need actual rows/logic."

### 1.6 Audit Log — core mechanism

`AuditLog` (`core/models.py:75-96`) already has `user_id`, `branch_id`,
`action`, `entity_type`, `entity_id`, `old_data`/`new_data` (JSON),
`ip_address`, `user_agent`, `approved_by`, and is indexed on
`user_id`/`branch_id`/`action`/`entity_type`/`entity_id` (added specifically
because `GET /audit-logs` was doing full table scans as the log grew — see
CLAUDE.md §13 note on `AuditLog`). It is already the write target for
`close_shift_variance_override`, void, refund, role/permission changes
(`update_user_role`, `grant_permission`/`revoke_permission` — check
`core/services.py`), and login/logout is already covered by the kernel auth
service. **This is the one audit log the spec wants — do not create a second
"OperationsAuditLog" table.**

### 1.7 Kitchen Control — status ownership is real

`restaurant.services.update_order_status` already enforces station-based KDS
routing (`MenuItem.station`, `CafeItem.station` — added 2026-07-08 fixing a
real bug where cafe kitchen items always routed to `bar`). Status transitions
are gated at the router level (`get_waiter_user` vs kitchen-only endpoints) —
verify exact chef-vs-waiter status-change gating during Batch 2 (§5) rather
than assuming; this needs a direct grep before claiming it's 100% done.

### 1.8 Customer Control — soft delete already the pattern

`crm.services.blacklist_customer`/`unblacklist_customer` (`crm/services.py:
83-97`) already model "no hard delete, just a status flag with reason" —
`Customer.blacklisted` + `blacklist_reason`. There is no
`DELETE /crm/customers/{id}` endpoint that hard-deletes a customer today.
This satisfies the *pattern* the spec wants ("Soft Delete only") even though
blacklist and delete are conceptually different actions — reuse this pattern
literally if/when a genuine "delete customer" action is ever requested,
rather than inventing a new soft-delete convention.

---

## 2. Needs extension, not replacement

Real gaps where the fix is "add a parameter / add a table column / add a
tier lookup to an existing engine" — **not** a new subsystem.

### 2.1 Discount Engine needs approval-tier thresholds bolted on

The spec's tiered table (cashier <5% → supervisor 10% → manager 20% → GM 40%
→ owner above) has **no representation today**. `discount_engine.py` computes
`amount_saved`/a percentage-equivalent but nothing consults `ROLE_LEVELS`
against it. This is an extension:

- Add a small pure function to `discount_engine.py` (or a sibling module) —
  `required_approval_level(discount_pct: Decimal) -> int` — mapping a
  computed discount percentage to a `ROLE_LEVELS` value. This is the natural
  place because it's pure/testable and already owns `Decimal` percentage math.
- The two discount endpoints (`restaurant`/`cafe` `.../discount`) need to:
  1. compute the rule result as today,
  2. call the new tier function,
  3. if `acting_user_level < required_level`, **do not silently apply** —
     require `approver_user_id`/`approver_pin` and route through
     `resolve_pin_approval(..., min_approver_level=required_level)`, same as
     `close_shift`'s variance-override pattern.
- This means `POST .../orders/{id}/discount` needs new optional request-body
  fields (`approver_user_id`, `approver_pin`) — currently the endpoint takes
  **no body at all** (`apply_discount(order_id, db, _=Depends(get_cashier_user))`,
  `restaurant/api/router.py:567-573`). That's a real (small) breaking-surface
  change to the request contract, not a new endpoint.

### 2.2 `resolve_pin_approval` becomes the mandatory single mechanism

Anywhere the spec asks for "Officer PIN" (Price Override, Open Drawer,
Cancel Payment, Cash Adjustment, Transfer Bill, Split Payment, Manual Price),
the implementation is: call `resolve_pin_approval` with the right
`min_approver_level`, write one `AuditLog` row with `approved_by` populated,
reuse `PinGuardModal.vue` on the frontend. **Explicitly do not invent a
second approval primitive** — no new "ApprovalRequest" table, no new PIN
verification code path. Every future sensitive action is a thin wrapper
around what exists.

### 2.3 Shift lifecycle needs new states, not a new shift concept

`CashierShift.status` is currently a two-value enum (`open`/`closed`).
Suspend/Resume/Emergency-Close/Recount are new *states and transitions* on
the **existing** `CashierShift` model — not a new "ShiftSession" table. Safe
Drop/Cash Pickup are new **ledger events** referencing `CashierShift.id` via
FK (see §3.2 Cash Control — same table family, don't fork it).

### 2.4 Reports permission gating extends the existing catalog

"كل تقرير له صلاحية مستقلة" (Sales/Profit/Cash/Inventory/Payroll/VIP/
Discount/Audit/Kitchen reports) is additional **rows in
`PERMISSION_CATALOG`** (`core/permission_catalog.py`) plus
`Depends(require_permission(...))` on each report endpoint — the exact
mechanism already governing 10 other sensitive operations. Not a new
authorization system.

### 2.5 Table Control — some ops exist informally, most don't

Reopen/Cancel exist implicitly through order status transitions today. Merge/
Split/Transfer/Move do **not exist at all** (confirmed by grep — zero hits
for `transfer_table`/`merge`/`split` in `restaurant/services.py` or
`api/router.py`). `P-01` (Table Transfer) is already tracked ⬜ in wagdy.md's
own punch list — **do not treat this as new scope discovered by the
Operations & Control Layer spec; it's the same gap already tracked**. When
built, each op should get its own `PERMISSION_CATALOG` row exactly like
`restaurant.void_order_item`, not a bespoke "table permission" system.

---

## 3. Genuinely net-new

Nothing below exists in any form today. Confirmed by direct grep across
`backend/app/modules/` and `backend/app/resort_os/` — zero hits for `Device`,
`fraud`, `safe_drop`, `petty_cash`, `cash_in`/`cash_out`, `drawer_open`,
session-cap logic, or KPI aggregation beyond the sales leaderboard and the
occupancy/beach/maintenance live-KPI websocket.

### 3.1 Approval Level tiers by discount %

The lookup table itself (which % maps to which role level) — covered as an
*extension point* in §2.1, but the actual threshold numbers
(<5%/10%/20%/40%/above) are a **business decision Mohamed needs to confirm**,
including how it maps onto the *existing* role set (there is no literal
"supervisor" tier distinct from "manager" in terms of discount authority
today even though `supervisor` (level 50) exists as a role — need to confirm
whether supervisor=10%, manager=20% maps directly, and whether "GM" =
`admin` (80) and "Owner" = `super_admin` (100) in this system, since those
exact titles don't exist as roles).

### 3.2 Cash Control ledger (Cash In/Out, Petty Cash, Safe Drop, Drawer Open, Correction)

New table, e.g. `CashMovement` (branch_id, shift_id FK → `CashierShift`,
type: `cash_in|cash_out|petty_cash|safe_drop|drawer_open|correction`, amount,
reason, performed_by, approved_by, created_at) + service functions each
writing an `AuditLog` row. `Open Drawer` specifically needs to be loggable
**even with no sale attached** (spec: "حتى بدون بيع") — that's a new
`POST /finance/shifts/{id}/drawer-open` style endpoint with reason capture,
distinct from any payment flow. Every write here contributes to Fraud
Detection thresholds (§3.5).

### 3.3 Device Management

New model, e.g. `PosDevice` (branch_id, device_label like "POS-01"/"Beach POS",
last_user_id, last_shift_id, last_login_at, last_ip, mac_address,
app_version). Needs a registration/heartbeat endpoint the frontend calls on
login (device fingerprint isn't currently captured anywhere — confirmed zero
hits for `device_id`/`Device` across the backend).

### 3.4 Session Management (concurrent-device cap per cashier)

New: a cap on simultaneous active JWTs per user (e.g. max 2 devices). Today
there is no session registry beyond `TokenBlacklist`/revocation-by-timestamp
(kernel). Needs either a Redis-backed active-session set keyed by user_id
(consistent with how `revoke_user_tokens` already uses Redis via
`core/deps.py:56-62`) or a DB-backed `UserSession` table — Redis is more
consistent with the existing revocation mechanism's storage choice.

### 3.5 Fraud Detection (threshold alerts)

New: a Celery periodic task (pattern: `beach_tasks.mark_b2b_overdue`,
`inventory_tasks.check_low_stock`) that queries `AuditLog`/`CashMovement`/
void-refund counts per cashier per rolling hour window and raises a
`Notification`/WhatsApp alert when thresholds are crossed (15+ refunds/hr,
20+ drawer opens, high discount volume, high void rate — exact numbers need
Mohamed's confirmation, same caveat as §3.1). This is pure aggregation over
data the Audit Log / Cash Control ledger already produces once §3.2 exists —
sequence matters, this cannot be built before §3.2.

### 3.6 Per-role KPI aggregates + Manager Dashboard alert feed

`GET /hr/leaderboard` (`hr/services.py:626`) already computes some
cashier-adjacent stats (sales ranking) but not the spec's full Cashier KPI
set (Void Rate, Refund Rate, Discount Rate, Cash Difference, Shift Accuracy,
Orders/Hour) or Kitchen KPIs (avg prep time, late/cancelled/recalled dishes).
The existing `/ws/analytics/kpis/{branch_id}` websocket
(`analytics/api/router.py:389-444`, `_compute_live_kpis`) is a **good
extension point structurally** (same push pattern) but currently only
computes PMS occupancy / beach capacity / open work orders — it has nothing
to do with cashier/kitchen/fraud alerts. The spec's "Manager Dashboard" alert
feed (🚨 discounts/refund/void/drawer-open/shift-diff/offline-sales/
failed-payments/slow-kitchen/complaints) is a new aggregation layer that
should **reuse this websocket's transport pattern**, not invent a new one,
but its data sources (Cash Control, Fraud Detection, Discount) mostly don't
exist yet (§3.2, §3.5) — this is necessarily one of the last batches.

### 3.7 Remaining discount types — explicit overlap with wagdy.md punch list

- **Loyalty Points** as a redeemable discount — **this is wagdy.md's own
  `C-01`** (⬜, size L, "Backend: `customer.points` + endpoints صرف/كسب").
  Confirmed zero `loyalty_points`/`LoyaltyPoint` model anywhere in the repo.
  **Do not plan this twice** — when it's built, it is simultaneously "C-01"
  and "the Loyalty Points discount type from the Operations & Control Layer
  spec." One implementation satisfies both.
- **Voucher / Gift Card** — **this is wagdy.md's own `C-02`** (⬜, size L,
  "Backend: جدول `vouchers` جديد", explicitly noted as "different from
  ConditionalDiscount"). Same flag: one build satisfies both the punch list
  and the spec.
- Both should ultimately plug into `discount_engine.py` as new
  `discount_type` values (or a parallel "redemption" path that produces the
  same `DiscountResult` shape) so the existing scope/condition/audit
  machinery isn't duplicated for them.

---

## 4. Explicit conflict/duplication risks if implemented literally

If someone reads wagdy.md §"Operations & Control Layer" cold and starts
building without this reconciliation pass, these are the concrete collisions
that would happen:

1. **A second PIN/approval system.** The spec's "Officer PIN → Reason →
   Audit" diagram reads as a self-contained feature request. Building it
   fresh would produce a competing `OfficerApproval` table/service sitting
   next to `PinCredential`/`resolve_pin_approval`, with two different lockout
   policies, two different audit trails, and two different frontend modals.
   **Mitigation:** everything in §2.2 routes through the existing function.

2. **A second audit log.** "سجل كل شيء" read literally invites a new
   `OperationsAuditLog` table. There is already one `AuditLog` with indexed
   columns built specifically to survive growth — a second table would mean
   two places to check per incident, and the existing admin audit-log screen
   would not show the new table's rows.

3. **A second discount-rule model.** "أنشئ محرك خصومات" reads as "build a
   discount engine" — but one already exists with `Decimal`-correct math,
   scope/condition taxonomy, and two live endpoints. A naive fresh build
   would either duplicate `discount_engine.py` under a new name or, worse,
   run in parallel with subtly different rounding/tie-break rules, producing
   two different "correct" discount amounts for the same order depending on
   which code path a developer used.

4. **Permission model built as Role+Outlet+Branch+Shift+Approval from
   scratch.** The spec's `User → Role → Permission Set → Branch → Outlet →
   Shift → Device → Approval Level → Business Rules` chain reads as "design a
   new permission engine." Branch is already solved via `UserPermission.
   branch_id`. Approval Level is already solved via `resolve_pin_approval`'s
   `min_approver_level`. Only Outlet/Shift/Device are genuinely new axes —
   building a whole new permission engine to add three axes would replace
   working, tested infrastructure (`require_permission`, the catalog, the
   `/admin/permissions` screen) rather than extend it.

5. **Table Control treated as new scope.** P-01 (Table Transfer) is already
   tracked in wagdy.md's own Phase 1 punch list. Treating "Table Control" from
   the Operations & Control Layer spec as separately-discovered scope risks
   two different implementations (or two different people picking it up
   independently) for the same feature.

6. **Loyalty Points / Voucher built twice.** Same risk as #5 — C-01/C-02 are
   already tracked. Flagged explicitly in §3.7.

7. **KPI dashboard built as a new realtime channel.** A fresh build would
   likely open a second WebSocket (`/ws/manager-dashboard` or similar)
   duplicating `/ws/analytics/kpis/{branch_id}`'s auth (`get_websocket_user`,
   already fixed for a real pre-existing "no auth on WebSockets" bug — A-01
   in wagdy.md) and reconnect logic that the frontend's
   `useResortWebSocket` composable already handles generically.

---

## 5. Phased implementation plan

Per CLAUDE.md §7 (small, safe, production-verifiable batches — analyze →
plan → implement → test → review → document → commit, each batch leaves the
project healthier than before). **Every batch below needs Mohamed's sign-off
before it starts** — this whole area is auth/money/permission surface
(CLAUDE.md §15). Ordered by unblock value, not by spec section order.

### Batch 0 (prerequisite, not code) — Confirm business-rule numbers with Mohamed
Before any of Batches 1–3 can be implemented correctly, get explicit answers:
- Discount approval tiers: exact % breakpoints and which existing role
  (`cashier`/`supervisor`/`manager`/`admin`/`super_admin`) sits at each tier —
  spec uses "GM"/"Owner" labels that don't exist as roles today.
  Confirm: `manager(60)`=20% ceiling, `admin(80)`≈"GM"=40% ceiling,
  `super_admin(100)`≈"Owner"=unlimited? `supervisor(50)`=10% ceiling?
  Below `supervisor`, cashier(40) ceiling=5%?
- Fraud thresholds: are 15 refunds/hr, 20 drawer-opens/hr, etc. the actual
  numbers Mohamed wants, or illustrative examples from the spec text?
- Cash Control: does "Correction" need its own approval tier, or does it
  always require manager+ PIN regardless of amount?

### Batch 1 — Wire approval tiers onto the two live discount endpoints
**Highest value, smallest footprint, closes the one gap already flagged as a
real, currently-ungated hole in a live money-flow.**
1. Add `required_approval_level(discount_pct: Decimal) -> int` (pure
   function) to `discount_engine.py`, tested with the tier table from Batch 0.
2. Add optional `approver_user_id`/`approver_pin` fields to the discount
   request schemas (new `ApplyDiscountRequest` body replacing the current
   empty-body `POST .../discount`).
3. `restaurant.services.apply_order_discount` / `cafe` equivalent: after
   computing the result, if `acting_user_level < required_approval_level(pct)`,
   call `resolve_pin_approval` before committing; write `AuditLog` with
   `action="discount_approval_override"`, old/new amounts, `approved_by`.
4. Frontend: `useOrderDiscount.ts` gains a two-step flow (compute → if 403 with
   an approval-required code, show `PinGuardModal` with the right
   `min-level`, retry with approver fields) mirroring `OrderDetailModal.vue`'s
   existing void flow exactly.
5. Tests: tier boundary cases (exactly at threshold, self-qualified manager,
   wrong PIN, locked-out approver), regression on existing discount tests.

### Batch 2 — Report permission catalog rows
Small, no schema changes, no new tables. Add the report-specific
`PERMISSION_CATALOG` entries (Sales/Profit/Cash/Inventory/Payroll/VIP/
Discount/Audit/Kitchen) and `require_permission` dependencies on the
corresponding report endpoints. Verify Kitchen Control status-change gating
(§1.7 caveat) as part of this batch's "understand the system" step, since
it's a report-adjacent area and cheap to confirm while already in that code.

### Batch 3 — Cash Control ledger
New `CashMovement` table + migration, service functions (`cash_in`,
`cash_out`, `petty_cash_out`, `safe_drop`, `drawer_open`, `correction`), each
requiring the right `resolve_pin_approval` tier from Batch 0, each writing
`AuditLog`. Frontend: a "Cash Control" panel in `ShiftDashboardView.vue` next
to the existing shift close flow. This unblocks Batch 5 (Fraud Detection)
and extends Batch 6 (KPIs).

### Batch 4 — Shift lifecycle states (Suspend/Resume/Emergency-Close/Recount)
Extend `CashierShift.status` beyond `open`/`closed`, add transition
endpoints, each gated by the same approval mechanism where the spec implies
supervision (Emergency Close, Recount). Depends on Batch 3 only loosely
(Recount likely references cash-count lines already in place).

### Batch 5 — Device Management + Session cap
New `PosDevice` model + registration/heartbeat call on login. Session cap:
Redis-backed active-session set per user, checked at login, consistent with
the existing `revoke_user_tokens` Redis pattern. Independent of Batches 1–4;
can run in parallel if a second agent/session is available.

### Batch 6 — Fraud Detection
Celery periodic task querying `AuditLog` + `CashMovement` (from Batch 3) per
cashier per rolling window, raises `Notification` + WhatsApp alert past
threshold (numbers from Batch 0). Follows the exact pattern of
`beach_tasks.mark_b2b_overdue`/`inventory_tasks.check_low_stock`. **Hard
dependency on Batch 3** (no cash-movement data to alert on otherwise).

### Batch 7 — Per-role KPIs + Manager Dashboard alert feed
Cashier/Kitchen/Restaurant KPI aggregation functions (pure, testable,
`resort_os/`-style if the math is nontrivial) + extend
`/ws/analytics/kpis/{branch_id}`'s payload (or add a sibling websocket using
the identical `get_websocket_user` auth pattern) to push the 🚨 alert feed.
**Depends on Batch 3 (cash data) and Batch 6 (fraud alerts) for the alert
feed to have real content** — KPI numbers alone (avg ticket, void rate) can
land earlier if Mohamed wants partial value sooner.

### Batch 8 — Loyalty Points (C-01) / Voucher-Gift Card (C-02)
Tracked as its own wagdy.md punch-list pair, sized L each. Build as new
`discount_type` values plugging into the existing engine (§3.7). Not
sequenced tightly with the rest of this plan — can happen whenever C-01/C-02
come up in the normal roadmap; flagged here only so it isn't accidentally
built twice under two different names.

### Batch 9 — Table Control (Transfer/Merge/Split/Move)
This is P-01 plus its siblings, already tracked. Each op gets its own
`PERMISSION_CATALOG` row per §2.5. Not new scope from this spec — sequence
per the existing roadmap, not as part of this track.

---

## 6. What was and wasn't done in this pass

This audit did **not** implement any of the above. The one candidate for a
"small, obviously-safe, non-conflicting first step" — wiring
`resolve_pin_approval` onto the currently-ungated discount button — turned
out **not** to qualify as "obviously safe": it requires a live production
policy decision (the exact % tier breakpoints and which existing role sits
at each tier — Batch 0 above) that changes real cashier behavior at a resort
that is currently deployed and in use. Implementing a threshold table with
guessed numbers would be exactly the kind of unreviewed change to
"العمليات المالية" that CLAUDE.md §15 exists to prevent. That decision is
deferred to Mohamed via Batch 0, then Batch 1 is ready to implement
immediately once numbers are confirmed.

**Baseline confirmed during this audit:** `pytest tests/ -v` → **1761
passed**, 0 failed, run against the current worktree before any changes were
made (no changes were made, so this baseline is also the current state).
