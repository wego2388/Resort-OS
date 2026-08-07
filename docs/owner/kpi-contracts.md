# Owner Intelligence Cockpit — KPI Contracts (Phase 1)

**Status:** Draft — Phase 1 of Decision 0004
**Date:** 2026-08-07
**Rule:** A metric with no entry here gets no service function, no endpoint, and no place on any owner screen.

Each entry specifies: exact formula · source of truth · period/timing · inclusion/exclusion rules · book vs. reconciled · data-completeness status · drill-down path.

---

## Group A — "Now" Screen (Primary Metrics)

### A-1. Today's Net Revenue

| Field | Value |
|---|---|
| **Formula** | Sum of all revenue journal lines (account_type = "revenue") for today's accounting date, credit minus debit, from `journal_entries` + `journal_lines` where `entry_date` falls within today's Cairo-timezone date range converted to UTC |
| **Source function** | `finance.services.get_income_statement(db, branch_id, date_from=today, date_to=today)` → `result.total_revenue` |
| **Period** | Calendar day, Cairo timezone (Africa/Cairo). "Today" = `business_today()` from `resort_os.timezone_utils` |
| **Inclusion** | All posted journal lines with `account_type = "revenue"`, all outlets (dining, beach, PMS, timeshare, leasing) |
| **Exclusion** | Voided/reversed entries (they produce offsetting journal lines that net to zero automatically) |
| **Book vs. reconciled** | Book balance — posted journal entries only. No unposted accruals |
| **Completeness status** | Open period (today is never closed mid-day). Always shown as "provisional" with today's date |
| **Drill-down** | Breakdown by account code → links to `GET /finance/journal-entries?date_from=today&date_to=today` |
| **Data-readiness** | ✅ EXISTS — `get_income_statement` is live and tested. Verified: chart of accounts seeded on production 2026-07-27 |

---

### A-2. Today's Net Cash Position

| Field | Value |
|---|---|
| **Formula** | Sum of all open cashier shifts' `expected_cash` (the live computed value before close): `opening_float + net_cash_sales + cash_movements_effect`. "Net cash position" = total expected cash across all open shifts in the branch |
| **Source function** | `finance.services.build_active_shifts_response(db, branch_id)` → sum of `shift.expected_cash` across all `shifts` |
| **Period** | Live / point-in-time (no date filter — open shifts only) |
| **Inclusion** | All open `CashierShift` records for the branch. Cash method payments only for the cash component; card/credit excluded from cash position |
| **Exclusion** | Closed shifts (their final variance is a historical fact, not live position) |
| **Book vs. reconciled** | Live computed — NOT a reconciled balance. Represents expected cash in drawers, not audited vault balance |
| **Completeness status** | Live/provisional always. Labelled "كاش متوقع في الأدراج" — not "رصيد الخزينة" |
| **Drill-down** | Per-shift breakdown → each `shift_id` → `GET /finance/shifts/{id}/report` |
| **Data-readiness** | ✅ EXISTS — `build_active_shifts_response` is live. Cash movements included via `_cash_movement_expected_effect` |

---

### A-3. Today's Expense Total

| Field | Value |
|---|---|
| **Formula** | Sum of all expense journal lines (account_type = "expense") for today, debit minus credit, from `journal_entries` + `journal_lines` |
| **Source function** | `finance.services.get_income_statement(db, branch_id, date_from=today, date_to=today)` → `result.total_expense` |
| **Period** | Calendar day, Cairo timezone |
| **Inclusion** | All posted expense journal lines. Includes COGS lines (account 5xxx), payroll accruals, utility costs |
| **Exclusion** | Reversed/voided entries (net to zero). Unposted accruals |
| **Book vs. reconciled** | Book balance — posted only |
| **Completeness status** | Open period — provisional |
| **Drill-down** | Breakdown by expense account code → `GET /finance/reports/income-statement?date_from=today&date_to=today` |
| **Data-readiness** | ✅ EXISTS — same call as A-1 |

---

### A-4. Open Receivables — B2B Beach Contracts

| Field | Value |
|---|---|
| **Formula** | For each active `B2BContract`: sum of `B2BContractDay.total_amount` since `last_settled_at` (or contract `valid_from` if never settled). Overdue flag = `is_overdue` field on the contract (set by nightly `beach_tasks.mark_b2b_overdue` Celery task) |
| **Source function** | `beach.crud` — query `B2BContract` with `is_active=True`, join `B2BContractDay` filtered after `last_settled_at`. `is_overdue` is a precomputed boolean on the model |
| **Period** | Outstanding balance since last settlement date. Not a single calendar period |
| **Inclusion** | All active B2B contracts for the branch |
| **Exclusion** | Settled transactions (periods before `last_settled_at`). Voided beach transactions |
| **Book vs. reconciled** | Book balance — `B2BContractDay.total_amount` is populated at check-in time (same as revenue journal posting). Known gap: voiding a B2B check-in reverses the journal entry but the historical `B2BContractDay` row is not removed (see beach/models.py comment). This is a known limitation, not acceptable rounding |
| **Completeness status** | Live / rolling balance |
| **Drill-down** | Per-contract detail: volume, amount, overdue status, credit limit vs. balance |
| **Data-readiness** | ✅ EXISTS — `B2BContract.is_overdue`, `credit_limit`, `last_settled_at`, `B2BContractDay` all live on production |

---

### A-5. Open Receivables — Timeshare Installments

| Field | Value |
|---|---|
| **Formula** | Sum of `TimeshareInstallment.amount` where `status IN ('unpaid', 'overdue')` and `due_date <= today` for the branch |
| **Source function** | `timeshare.crud` — query `TimeshareInstallment` filtered by branch via contract join, `status IN ('unpaid','overdue')`, `due_date <= today` |
| **Period** | All unpaid installments due on or before today |
| **Inclusion** | All active timeshare contracts for the branch |
| **Exclusion** | Future installments (due_date > today), paid/waived installments |
| **Book vs. reconciled** | Book balance |
| **Completeness status** | Point-in-time. `overdue` status is set by nightly `timeshare_tasks.mark_overdue` |
| **Drill-down** | Per-contract: installment schedule, overdue count, total outstanding |
| **Data-readiness** | ✅ EXISTS — `TimeshareInstallment.status` with overdue detection live. No unified "total overdue across sources" function exists yet — **needs new aggregation** combining B2B (A-4) and timeshare here |

**⚠️ Decision needed (Mohamed):** Should B2B overdue + timeshare overdue + folio balances be shown as one "Overdue Receivables" total, or as separate labelled buckets? Default: **separate buckets** — they represent different business relationships. Owner cockpit will show them separately.

---

### A-6. Current Occupancy

| Field | Value |
|---|---|
| **Formula** | Rooms with `status = 'occupied'` / total rooms in branch × 100. NOT a forecast — confirmed, physically checked-in guests only |
| **Source function** | `pms.crud.count_rooms(db, branch_id)` for denominator. Numerator: `db.query(Room).filter(Room.status == 'occupied', Room.branch_id == branch_id).count()` |
| **Period** | Right now — point-in-time |
| **Inclusion** | All rooms in the branch |
| **Exclusion** | Rooms with status 'maintenance', 'out_of_order'. Bookings not yet checked in |
| **Book vs. reconciled** | Operational state — not a financial balance |
| **Completeness status** | Live |
| **Drill-down** | Room list with current status → `GET /pms/rooms?branch_id=X` |
| **Data-readiness** | ✅ EXISTS — Room.status is maintained in real-time by PMS check-in/check-out. No single `get_occupancy_now()` function — **needs new 2-query wrapper** (trivial) |

---

### A-7. Beach Capacity Utilisation — Today

| Field | Value |
|---|---|
| **Formula** | `BeachInventory.capacity_used / BeachInventory.capacity_max × 100` for today. This is the running count of tickets sold today (cumulative, does not decrease on checkout — matches the reference system's behaviour per beach/models.py) |
| **Source function** | `beach.crud` — query `BeachInventory` for branch and today's date |
| **Period** | Today (cumulative daily counter) |
| **Inclusion** | All beach ticket types (entry, entry_towel, towel_rent) — BeachInventory tracks total capacity_used across types |
| **Exclusion** | Voided transactions (voiding does NOT decrement capacity_used — known limitation per beach/models.py. Owner screen must note this.) |
| **Book vs. reconciled** | Operational counter |
| **Completeness status** | Live |
| **Drill-down** | Active locations map → `GET /beach/locations?branch_id=X` |
| **Data-readiness** | ✅ EXISTS — `BeachInventory` is live. Note: capacity_used is a one-way counter; owner screen will label it "تذاكر مباعة اليوم" not "إشغال فعلي الآن" |

---

## Group B — Performance Screen (Period Comparisons)

### B-1. Revenue Comparison (Current vs. Prior Period / Prior Year)

| Field | Value |
|---|---|
| **Formula** | `get_income_statement(db, branch_id, period_A)` vs `get_income_statement(db, branch_id, period_B)` → diff and percentage change. "Prior period" = same duration shifted back. "Prior year" = same calendar period last year |
| **Source function** | Two calls to `finance.services.get_income_statement`. Delta computed in owner service layer, not in finance module |
| **Period** | Day / Week / Month / Year — selectable. Cairo timezone |
| **Inclusion** | All revenue accounts |
| **Drill-down** | Account-level breakdown for each period |
| **Data-readiness** | ✅ EXISTS — two calls to existing function. No new data needed |

---

### B-2. Per-Outlet Revenue Trend

| Field | Value |
|---|---|
| **Formula** | Daily/weekly revenue totals by outlet (dining, beach, PMS, timeshare) using existing `analytics.services.get_dining_revenue_by_outlet_type` for dining + direct queries for others, over a rolling window |
| **Source function** | `analytics.api.router.revenue_summary` pattern — daily granularity by iterating over date range |
| **Period** | Last 7 days / 30 days / custom |
| **Drill-down** | Outlet-level daily breakdown |
| **Data-readiness** | ✅ EXISTS for totals. **Needs new**: daily granularity loop (trivial — call income_statement per day or use journal_lines date grouping) |

---

## Group C — Sales / Product Performance

### C-1. Top Items by Revenue and Quantity (Dining)

| Field | Value |
|---|---|
| **Formula** | Per `DiningItem`: `SUM(DiningOrderItem.quantity)` as qty_rank, `SUM(DiningOrderItem.unit_price × DiningOrderItem.quantity)` as revenue_rank, per-item margin = `(unit_price - recipe_cost) / unit_price × 100` where recipe exists |
| **Source function** | Generalised from existing inline query in `dining.api.router` (lines 1124–1136). Current version: dining-only, quantity-rank only, `float()` money. **Needs new**: `owner_analytics_engine.py` function accepting outlet_ids + date range + rank_by param, uses `Decimal` throughout |
| **Period** | Selectable: today / 7d / 30d |
| **Inclusion** | Paid orders only (`DiningOrder.status = 'paid'`), non-cancelled items |
| **Exclusion** | Cancelled items (`DiningOrderItem.status = 'cancelled'`), voided orders |
| **Drill-down** | Item detail: daily trend, recipe cost (if exists), margin |
| **Data-readiness** | ⚠️ PARTIAL — query logic exists inline in router (not a service function). Recipe cost data exists in `MenuItemRecipeLine`. **Needs**: extraction into `owner_analytics_engine.py` as `rank_items(db, outlet_ids, date_from, date_to, rank_by)` |

---

### C-2. ABC / Pareto Classification (Dining Items)

| Field | Value |
|---|---|
| **Formula** | Sort items by revenue descending. Cumulative revenue %. A = top items covering 0–70% of total revenue. B = next tier 70–90%. C = bottom 90–100%. Computed in `owner_analytics_engine.py` |
| **Source function** | **Needs new**: `owner_analytics_engine.classify_abc(items: list[ItemMetric]) -> list[ItemMetric]` — pure function, no DB, takes output of C-1 |
| **Determinism requirements** | Must handle: empty list → empty list; single item → class A; all-equal revenue → stable tie-break by item name alphabetical |
| **Data-readiness** | ❌ NOT EXISTS — new pure function needed in `resort_os/owner_analytics_engine.py` |

---

### C-3. Beach Ticket Performance by Type

| Field | Value |
|---|---|
| **Formula** | Per `tx_type` (entry / entry_towel / towel_rent / towel_return): count, sum(total_amount), average unit price, for a given period |
| **Source function** | **Needs new**: query `BeachTransaction` grouped by `tx_type` where `voided_at IS NULL` and `tx_date` in range |
| **Period** | Selectable |
| **Inclusion** | Non-voided transactions |
| **Exclusion** | Voided |
| **Drill-down** | Daily trend per ticket type |
| **Data-readiness** | ✅ Data exists. ❌ No aggregation function — **needs new** |

---

### C-4. B2B Hotel Partner Performance

| Field | Value |
|---|---|
| **Formula** | Per `B2BContract`: total check-ins (sum `B2BContractDay.checked_in_count`), total beach revenue (sum `B2BContractDay.total_amount`), current outstanding balance (from A-4), credit limit, is_overdue, F&B attach = `SUM(DiningOrder.total)` for `DiningOrder.b2b_contract_id = contract.id` in period — **per hotel/contract only, never per named guest** |
| **Source function** | **Needs new** channel analytics service reading `B2BContract` + `B2BContractDay` + `DiningOrder.b2b_contract_id` (added in REL-10 migration `a3f9c1d2e4b5`) |
| **Period** | Month-to-date / custom |
| **PII constraint** | Response schema MUST NOT contain guest name, phone, or any personal identifier. Only aggregate per hotel |
| **Data-readiness** | ✅ Data model complete (`B2BContractDay`, `DiningOrder.b2b_contract_id` in production). ❌ No analytics service yet — **needs new** |

---

## Group D — Expense Analytics

### D-1. Expense by Category as % of Revenue

| Field | Value |
|---|---|
| **Formula** | For each expense account: `account_total / total_revenue × 100` for the period. Uses `get_income_statement` for both numerator (expense lines) and denominator (total_revenue) |
| **Source function** | `finance.services.get_income_statement(db, branch_id, date_from, date_to)` — provides both `expense_lines` and `total_revenue` |
| **Period** | Month / custom |
| **Variance flag** | Automatic flag when `current_period_%` differs from `prior_period_%` by more than threshold (default: 20% relative change). Computed in `owner_analytics_engine.detect_variance` |
| **Data-readiness** | ✅ EXISTS for raw data. ❌ `detect_variance` function needed in `owner_analytics_engine.py` |

---

### D-2. Payroll as % of Revenue

| Field | Value |
|---|---|
| **Formula** | `PayrollRun.total_net` (sum for period) / `total_revenue` for same period × 100. Shown as aggregate only — NOT per employee |
| **Source function** | `hr.crud` — sum `PayrollRun.total_net` where `period_year/month` in range. Denominator from `get_income_statement` |
| **Period** | Month |
| **PII constraint** | Shown as aggregate total only. Individual employee names/salaries NEVER shown in general view. Employee name visible ONLY when directly tied to a flagged exception (e.g. fraud signal or open shift) |
| **Data-readiness** | ✅ `PayrollRun.total_net` exists. ❌ No combined "payroll % of revenue" query — **needs new aggregation** |

---

## Group E — Procurement Analytics

### E-1. Purchase Spend by Supplier

| Field | Value |
|---|---|
| **Formula** | Per `Supplier`: sum of `PurchaseOrder.total_amount` where `status IN ('received','partial')` and `ordered_at` in period |
| **Source function** | **Needs new**: query `PurchaseOrder` grouped by `supplier_id`, joined to `Supplier.name` |
| **Period** | Month / custom |
| **Concentration flag** | If one supplier accounts for > 50% of total spend → flag. Threshold configurable in `Settings` |
| **Data-readiness** | ✅ `Supplier`, `PurchaseOrder`, `PurchaseOrderItem` all exist. ❌ No spend-by-supplier aggregation — **needs new** |

---

### E-2. Purchase Request Estimate vs. Actual (PO Variance)

| Field | Value |
|---|---|
| **Formula** | Per product: `PurchaseRequestItem.estimated_unit_cost` vs. `PurchaseOrderItem.unit_cost` for the matching conversion (linked via `PurchaseRequest.status = 'converted'` → `PurchaseOrder`). Variance = `(actual - estimate) / estimate × 100` |
| **Source function** | **Needs new**: join `PurchaseRequest` → `PurchaseRequestItem` → `PurchaseOrderItem` via order linkage. **Note**: current schema has `PurchaseRequest` and `PurchaseOrder` as separate entities connected by conversion workflow, but no direct FK linking the resulting PO back to the originating PR. **Gap**: need to verify if `convert_to_purchase_order` stores the source PR id on the PO. |
| **Data-readiness** | ⚠️ PARTIAL — `estimated_unit_cost` on `PurchaseRequestItem` and `unit_cost` on `PurchaseOrderItem` both exist. **Needs verification**: does the conversion store `source_request_id` on `PurchaseOrder`? If not, variance cannot be computed accurately. |

**⚠️ Confirmed gap (inspected 2026-08-07):** `inventory.services.convert_to_purchase_order` does NOT store the originating `PurchaseRequest.id` on the created `PurchaseOrder`. The PR is marked `converted` but no FK links back to it. **Action: add `source_request_id` nullable FK on `purchase_orders` in Phase 2 migration, and update `convert_to_purchase_order` to populate it.**

---

## Group F — Staff & Shift Monitoring

### F-1. Who Is On Shift Right Now

| Field | Value |
|---|---|
| **Formula** | All `CashierShift` records where `status = 'open'` and `branch_id = X`, with cashier name (joined from `User`) |
| **Source function** | `finance.services.build_active_shifts_response(db, branch_id)` — already returns cashier name, opened_at, total_sales, expected_cash |
| **Period** | Live point-in-time |
| **PII constraint** | Cashier name shown only in context of their shift monitoring — acceptable per Decision 0004 §Isolation model item 7 |
| **Data-readiness** | ✅ EXISTS — live and tested |

---

### F-2. Shift Cash Variance (at Close)

| Field | Value |
|---|---|
| **Formula** | `CashierShift.variance = counted_cash - expected_cash` (set at shift close). Positive = overage, negative = shortage. For open shifts: live variance = `counted_cash` not yet known → show expected_cash only |
| **Source function** | `CashierShift.variance` (closed shifts). Live: from `build_active_shifts_response` |
| **Abnormal flag** | `abs(variance) > FRAUD_SHIFT_VARIANCE_THRESHOLD` (configurable, default: 50 EGP). Flag → `OWNER_EXCEPTION_RULES` as `critical` tier |
| **Data-readiness** | ✅ EXISTS — `variance` column live on production |

---

### F-3. Manual Cash Movements per Shift

| Field | Value |
|---|---|
| **Formula** | All `CashMovement` records for a shift: type, amount, direction, reason, performed_by (name), approved_by (name), timestamp |
| **Source function** | `finance.crud.list_cash_movements(db, shift_id)` |
| **Shown to owner** | Read-only. Owner cannot approve/dispute/close from this surface |
| **Data-readiness** | ✅ EXISTS |

---

## Group G — Exceptions Engine

### G-1. Fraud / Anomaly Signals

| Field | Value |
|---|---|
| **Formula** | Reuse existing thresholds from `app/tasks/fraud_tasks.py`: refund count > `FRAUD_REFUND_COUNT_THRESHOLD` per cashier per 60 min window; void count > `FRAUD_VOID_COUNT_THRESHOLD`; discount count > `FRAUD_DISCOUNT_COUNT_THRESHOLD`; drawer opens > `FRAUD_DRAWER_OPEN_COUNT_THRESHOLD` per 24h. These are already computed and trigger WhatsApp notifications. Owner exceptions engine reads from `AuditLog` — does NOT duplicate the detection logic |
| **Source function** | Read results from `AuditLog` where `action IN ('void_item','refund','apply_discount','cash_movement')` within rolling window. Reuse `fraud_tasks.find_fraud_signals()` output |
| **Tier** | `critical` — hard-pinned regardless of financial size |
| **Tags** | `realized` |
| **Data-readiness** | ✅ EXISTS — `fraud_tasks.py` + `AuditLog` live. ❌ No owner-facing read API yet — **needs new** |

---

### G-2. Abnormal Shift Variance

| Field | Value |
|---|---|
| **Formula** | `abs(CashierShift.variance) > threshold` at close, or `abs(live_expected - opening_float) > threshold` for open shifts with unusually low/high sales. Source: F-2 |
| **Tier** | `critical` |
| **Tags** | `realized` (closed shifts), `potential` (open shifts) |
| **Data-readiness** | ✅ Data exists. ❌ Exception scoring wrapper needed |

---

### G-3. Expense Category Variance

| Field | Value |
|---|---|
| **Formula** | When expense-as-%-of-revenue moves > threshold vs. prior period (from D-1) |
| **Tier** | `attention` |
| **Tags** | `realized` |
| **Data-readiness** | Depends on D-1 `detect_variance` — ❌ not yet |

---

### G-4. B2B Overdue Alerts

| Field | Value |
|---|---|
| **Formula** | `B2BContract.is_overdue = True` |
| **Tier** | `attention` |
| **Tags** | `realized` |
| **Data-readiness** | ✅ EXISTS |

---

## Group H — NOT in scope (confirmed removed)

| Item | Status |
|---|---|
| Any AI/LLM narrative | ❌ Explicitly removed from scope. Never to be added without a new Decision record |
| "Ask your business" chat | ❌ Removed |
| Per-employee salary detail | ❌ Out of scope for owner — aggregate only |
| Individual guest identity | ❌ Never surfaced. B2B is per hotel/contract only |
| Unit economics | Deferred to Phase 8 — requires Mohamed to approve a published allocation rule first |
| Scenario sandbox | Deferred to Phase 9 |

---

## Data-Readiness Summary

| Group | Metrics | Status |
|---|---|---|
| A — Now | A-1, A-2, A-3, A-7 | ✅ Exists |
| A — Now | A-4, A-5, A-6 | ✅ Data exists / trivial wrapper needed |
| B — Performance | B-1 | ✅ Exists (two calls) |
| B — Performance | B-2 | Needs daily granularity loop |
| C — Sales | C-1 | ⚠️ Inline, needs extraction to engine |
| C — Sales | C-2 | ❌ New pure function needed |
| C — Sales | C-3 | ❌ New aggregation needed |
| C — Sales | C-4 | ❌ New service needed (data model complete) |
| D — Expense | D-1 | ⚠️ Needs `detect_variance` |
| D — Expense | D-2 | ❌ Needs combined query |
| E — Procurement | E-1 | ❌ Needs aggregation |
| E — Procurement | E-2 | ⚠️ Needs `source_request_id` verification |
| F — Shifts | F-1, F-2, F-3 | ✅ Exists |
| G — Exceptions | G-1 | ✅ Detection exists / owner read API needed |
| G — Exceptions | G-2, G-3, G-4 | ⚠️ Data exists / scoring wrapper needed |

---

## Open Decisions (must resolve before Phase 3 starts)

1. **E-2 PR→PO linkage**: `convert_to_purchase_order` confirmed (inspected) to NOT store `source_request_id`. → **Add `source_request_id` nullable FK on `purchase_orders` in Phase 2 migration. Update `convert_to_purchase_order` to populate it.**
2. **A-5 Overdue display**: Show B2B + timeshare overdue as one total or separate? → **Decision: separate** (recorded above as default, Mohamed can override).
3. **Periods before first allocation rule (Phase 8)**: Unit economics for pre-rule periods → **default: not shown** per Decision 0004.
4. **Owner app domain**: `owner.elkheima.com` vs path under staff domain — must be decided before Phase 4 frontend starts (per Decision 0004 "Frontend" section).

---

*Phase 1 complete. No code written. Every metric above has a defined source function (existing or new). Phase 2 (Isolation & Safety Rails) may now begin.*
