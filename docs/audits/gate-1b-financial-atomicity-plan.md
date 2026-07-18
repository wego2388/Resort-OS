# Gate 1B — Financial Atomicity: Plan + Implementation Record

**Status (2026-07-18): the bounded Dining-paid slice is implemented and
accepted after the third/final Codex review; it is not yet committed or
pushed.** §§1–2 below are the original **revision 3** plan (three
planning rounds, each independently reviewed by Codex, before any code was
written) — kept verbatim as the historical record of what was approved
before implementation started. §3 ("Implementation summary") documents
what was actually built. §4 documents the fixes applied after a first
post-implementation Codex review found several real defects (narrow
OperationalError→409 classification, silent-skip gaps in strict inventory
deduction, swallowed add_folio_charge failures in three call sites,
payment_method/folio consistency, a stale pre-lock cost_price read, and
thread-test hardening). §5 records the second-review micro-fixes. §6 records
the independent final review and acceptance evidence.

**This work is not yet committed or pushed.** Gate 2 is now unblocked for a
bounded planning pass, but product-code work for it must not be mixed into
this uncommitted diff. Acceptance applies only to the selected Dining-paid
slice and its necessary folio call-site corrections; it is not a claim that
all Gate 1B call sites or the repository are production-ready.

Every correction in revision 3 (§§1–2) was re-verified directly against
the live code before being written — not accepted from the review comment
at face value. Exact line numbers in §§1–2 reflect the code as it stood
*before* implementation and are a historical record, not a live index —
see §3/§4 for current file-level detail.

---

## 1. Call-site inventory

*(Renamed from "Complete call-site inventory" — several rows, noted
individually below, have not been independently re-traced with the same
line-by-line rigor as the selected call site in §2, and should not be read
as fully verified.)*

| Call site | Module | Commit boundary | Failure handling | Duplication/concurrency risk | Recommendation |
|---|---|---|---|---|---|
| **`update_order_status`** ("paid") | dining `services.py:658-770` | **Not single-commit.** Contains an unconditional nested commit (inventory) and, in the common case, at most one additional conditional nested commit (cost-center seeding, idempotent across the two trigger points in one request — see §2) | **Fail-open**: bare `except Exception: pass` around folio charge (718-745) and around inventory deduction (per line, 825-826) | **No row lock on order**; no lock on the folio it charges either | **Atomic** — see the full unit-of-work in §2 |
| `split_bill` | dining `services.py:1010-1099` | Single commit (1096) claimed — **not independently re-traced for nested commits; do not assume clean** | Fail-open (1070-1076, no logging); **plus a real GL bug**: posts full-total cash journal even when part of the order was room-charged | Same missing-lock issue | Atomic — fix swallow *and* the wrong-amount journal logic; re-trace commit boundary with the same rigor as §2 before scoping |
| `refund_order_item` | dining `services.py:1251-1362` | Single commit (1295) claimed — **not independently re-traced** | Fail-open but *logs* (`logger.error`, 1328-1330) | Guarded by item status; no order lock | Atomic — stop swallowing after logging; re-trace commit boundary |
| **`sell_ticket`/`_sell_ticket_no_commit`** | beach `services.py:177-320` | Holds the `BeachInventory` `SELECT FOR UPDATE NOWAIT` lock across the financial posting. **Corrected: not a clean single-commit path** — its revenue/folio-charge/reversal journal calls (`services.py:334,379,578,594`) all pass `cost_center_code="BEACH"`, so they inherit the same conditional `ensure_default_cost_centers` nested-commit exposure as Dining | Fail-open on folio branch (293-312); bare except can mask a poisoned session (no `db.rollback()`) | `local_id` dedup exists for direct sales; `b2b_checkin`, `checkin_location`, `checkout_location`, `check_in_reservation` bypass it | Atomic — isolate the flush in a nested `SAVEPOINT`; apply the same no-commit cost-center fix as Dining; propagate `local_id` to the bypassing callers |
| `void_transaction` | beach `services.py:500-549` | Single commit (547) | No local swallow for the primary reversal (fails closed, good); reversal journal still routes through the shared helper's swallow, and — per the correction above — can also hit the cost-center nested-commit path | **Never acquires the inventory lock at all** | Add the missing lock; apply the same cost-center fix as the sell path |
| `b2b_checkin` | beach `services.py:399-497` | Single commit (495) | Safe by construction (shared helper self-swallows) | **`B2BCheckinRequest` has no `local_id` field at all** | Add idempotency key |
| `check_in_reservation` | beach `services.py:842-879` | **Two separate commits** — `sell_ticket()`'s internal commit, then a second commit for `res.status` | N/A for the split itself | No lock on `BeachReservation`; no `local_id` on the constructed sell request | Call `_sell_ticket_no_commit` directly, fold into one commit; lock the reservation row |
| **`consume_stock`** (COGS) | inventory `services.py:187-226` | Executes *inside* `update_order_status`'s call graph via `_deduct_inventory_for_order` — cannot be deferred from the selected slice. `record_movement()` commits unconditionally at **`inventory/services.py:183`** (corrected — not 178) before `_post_cogs_journal` is attempted | Fail-open, entire body swallowed (239-276 in `_post_cogs_journal`); `record_movement`'s own stock-adjust step fails closed via `InventoryConcurrencyError`, correctly | No idempotency key on the Dining-triggered path. **Corrected:** the risk is a *retried/duplicated "mark paid" request* double-executing `_deduct_inventory_for_order` — not "offline-sync retry" as such; Dining's offline-order-creation path (`sync_offline_order`) never calls `consume_stock` at all (it only creates the order; inventory deduction happens exclusively in the "paid" transition). This risk is the same concurrency gap already covered by the order-level lock in §2, not a separate offline-sync-specific bug | A no-commit primitive is required here specifically because `update_order_status` calls into it directly |
| `receive_purchase_order` | inventory `services.py:292-342` | Single commit (311) — verified correct | Fail-open by construction of the shared helper | `ReceiveItemsRequest` has no idempotency key | Keep atomic; add idempotency key |
| `approve_stock_count` | inventory `services.py:553-625` | Single commit (623) | N/A — posts no journal entry at all | Low (state-machine guarded) | Finance-First coverage gap, not an atomicity bug |
| **`_post_payroll_journal`** | hr `services.py:541-649` | Same commit as `approve_payroll_run` (536) | Confirmed unchanged: bare `except Exception: pass` (646-649), no logging | `run.status` guard blocks double-approval but also blocks retry after a silent failure | Independent occurrence of the same bug class |
| Salary advances (disburse/cancel) | hr `services.py:654-690` | N/A | N/A — post zero journal entries ever, documented design gap | N/A | Out of scope — design completeness |
| **`_post_checkout_journal`** | pms `services.py:214-282` | Single commit (255) | Fail-open via the shared helper — zero log trace | No retry path once checked out | Tied to the deferred room-revenue design decision (CLAUDE.md §18) — defer |
| `_post_room_revenue_for_night_audit` | pms `services.py:393-496` | Single commit (442) | The code's own comment claims it logs failures — confirmed dead code (the exception never reaches the outer `except`) | Same non-retryable-once-completed pattern | Defer with PMS/room-revenue |
| `request_early_late` | pms `services.py:285-337` | Single commit (335) | Local except logs correctly (324-328) | Designed to be called repeatedly, but additively double-charges on repeat calls for the same event | Smaller, separable fix |
| `post_simple_revenue_journal` (shared helper) | finance `services.py:837-914` | N/A (helper). **Corrected:** its `ensure_default_cost_centers` call is at **line 883** (not 872-875); `ensure_default_cost_centers` itself (`finance/services.py:1111-1121`) commits only if it actually creates new cost centers (line 1120) | The root cause: deliberately swallows all exceptions, returns `None`, zero logging | N/A | 14 external call sites across beach/dining/pms/timeshare/leasing/inventory + 2 internal — high blast radius, separate dedicated slice |
| `close_shift` | finance `services.py:580-702` | Single commit (696) | Reconciliation math is real and correct | No row lock — two concurrent closes can overwrite each other's `expected_cash`/`variance` | Add `SELECT FOR UPDATE` |
| `Payment` model | finance `models.py:91-121` | — | — | No unique constraint on `reference`. Dining's `update_order_status` never creates a `Payment` row at all (unlike beach's `sell_ticket`) | Add idempotency constraint; Dining's missing `Payment` row is a separate, larger gap — see §2 deferred list |
| `AccountingPeriod`/period lock | finance `models.py:295-306` | — | — | Pure application-layer `if` check, zero DB-level enforcement | Structural finding, informs future work |
| `Folio` row (no dedicated row before revision 3) | finance `crud.py:129,169,194` (`get_folio`/`add_charge`/`recalculate_folio_total`) | N/A | **New in revision 3**: none of these three functions lock the `Folio` row. Five call sites write to a folio's charges without any serialization: beach `services.py:297`, dining `services.py:740` (`update_order_status`), dining `services.py:1071` (`split_bill`), finance `services.py:99` (`post_charge`), pms `services.py:317` (`request_early_late`) | Two concurrent charges to the same folio (e.g. a room-service order and a beach charge landing at the same moment) can race `recalculate_folio_total` | See §2 — centralize a blocking folio lock through `add_charge` so all five callers inherit it |

---

## 2. Selected highest-risk call site: `dining.services.update_order_status`'s "paid" transition

**File:** `backend/app/modules/dining/services.py:658-770`

Kept as the top-level workflow across all three review rounds — the
volume/severity reasoning is unchanged. Each round has corrected the shape
of the required fix, not the choice of call site.

### Corrected transaction trace (line numbers re-verified for revision 3)

```
update_order_status (dining/services.py:658)
├─ order.status = "paid", payment_method, folio_id resolved   [flush only]
├─ [if folio_id] add_charge + recalculate_folio_total          [flush only,
│                                                                 wrapped in
│                                                                 try/except
│                                                                 Exception: pass]
├─ _deduct_inventory_for_order(db, order)                       (line 753)
│    └─ per order_item, wrapped in try/except Exception: continue:
│         └─ per consumed recipe/product line, NOT per order_item:
│              inventory.services.consume_stock(...)            (dining/services.py:796,814)
│              ├─ record_movement(db, data, moved_by, ...)      (inventory/services.py:218)
│              │    └─ crud.adjust_stock(...)
│              │    └─ db.commit(); db.refresh(mov)             ← UNCONDITIONAL
│              │         NESTED COMMIT (inventory/services.py:183)
│              └─ _post_cogs_journal(...)                       (inventory/services.py:222)
│                   └─ try/except Exception: pass wraps:
│                        └─ [if cost center missing] ensure_default_cost_centers(db, branch_id)
│                             (inventory/services.py:253)
│                             └─ db.commit()  ← CONDITIONAL NESTED COMMIT
│                                (finance/services.py:1120, only if it seeds
│                                 new default cost centers for this branch)
│                        └─ create_journal_entry(...)            [flush only]
├─ _post_order_folio_charge_journal / _post_order_revenue_journal   (line 757/759)
│    └─ post_simple_revenue_journal(...)                        (finance/services.py:837)
│         └─ try/except Exception: return None wraps:
│              └─ [if cost_center_code set and cost center missing]
│                   ensure_default_cost_centers(db, branch_id)   (finance/services.py:883)
│                   └─ db.commit()  ← CONDITIONAL NESTED COMMIT (same helper as above)
│              └─ create_journal_entry(...)                      [flush only]
├─ [if customer_id] record_customer_visit(...)                  [flush only]
└─ db.commit(); db.refresh(order)                                (line 768, FINAL commit)
```

**Corrected fact (revision 3):** `ensure_default_cost_centers` is
idempotent within a single request/session — it queries existing cost
centers via `crud.list_cost_centers` (`finance/services.py:1113`), creates
only the `DEFAULT_COST_CENTERS` codes not already present, and commits only
`if created_any`. Because both trigger points (`_post_cogs_journal` at
`inventory/services.py:253`, and `post_simple_revenue_journal` at
`finance/services.py:883`) share the same DB session, whichever one runs
first seeds **all** default cost centers for the branch and commits once;
the second trigger point's lookup then finds them already present (visible
in-session, no re-commit needed) and takes no action. **In the normal case,
at most one cost-center-seeding commit occurs per request — not two** — but
this is exactly the fragile, order-dependent, only-safe-by-accident
behavior the fix must eliminate outright (see below), not merely document.

### Why this call site, not the others (unchanged)

1. **Volume** — every dining sale in the resort flows through this
   function.
2. **Compounding defects** — fail-open swallows, zero row-level locking,
   and nested commits reachable from three points in the call graph.
3. **Direct guest-facing money.**
4. **Direct descendant of the original C-01 finding.**

### Why the others stay deferred, with corrections

- **`inventory.consume_stock`** — not deferred; addressed in this slice's
  unit-of-work (unchanged from revision 2).
- **`beach.sell_ticket` and `void_transaction`** — revision 3 correction:
  these are **not** clean single-commit paths either (see table). They
  inherit the identical cost-center nested-commit exposure. They remain
  deferred as a near-identical *follow-up* slice, but must not be described
  as already safe.
- **`post_simple_revenue_journal` (shared helper)** — still deferred as a
  full rewrite for all 14+ external callers; this slice adds a narrowly
  scoped, backward-compatible no-commit path for Dining's (and, once
  extended, Beach's) use.
- **`split_bill`, `refund_order_item`** — deferred pending their own
  line-by-line trace, not because they're confirmed clean.
- **HR payroll, PMS checkout/night-audit** — monthly/nightly frequency;
  PMS checkout entangled with the deferred room-revenue design question.

### Implementation slice (plan only — not implemented)

**Root cause:** (a) the folio-charge swallow (`services.py:744-745`); (b)
two nested-commit trigger points reachable from inside this function's own
call graph, one unconditional (inventory) and one conditional but currently
only "safe" by session-ordering coincidence (cost-center seeding); (c) no
row lock on `DiningOrder`; (d) no row lock on `Folio`, shared with four
other call sites.

**One explicit unit-of-work, to replace the current flow:**

1. Lock the `DiningOrder` row (new `crud.get_order_for_update`, `SELECT ...
   FOR UPDATE NOWAIT`, mirroring `beach.crud.lock_inventory_for_update`'s
   existing pattern) **before** checking `order.status`.
2. Re-check `order.status` under the lock. If already `"paid"`, return the
   `ORDER_ALREADY_PAID` conflict (see contract table below) without any
   further mutation.
3. Resolve `payment_method`/`folio_id` (existing logic, no side effects).
4. If a folio charge is needed: acquire the **blocking Folio row lock**
   (new — see the dedicated Folio-locking design below) before inserting
   the charge and recalculating the total. **No `except Exception: pass`**
   — a failure here propagates and aborts the whole unit of work.
5. Deduct inventory via a **no-commit primitive**: `record_movement` and
   `consume_stock` keep their exact current public signatures and
   commit-on-return behavior for every other existing caller (backward-
   compatible wrapper); this strict Dining flow calls an internal no-commit
   variant instead, so stock adjustment and the `StockMovement` insert
   happen via `flush()` only, inside the same outer transaction. Genuine
   inventory failures propagate; only the already-intentional "not
   inventory-linked" cases (no recipe and no `linked_product_id`) continue
   to skip silently — that distinction must be preserved explicitly, not
   collapsed into the same `except` as real errors. Retain
   `crud.lock_product_for_update` per product.
6. Post the COGS journal and the revenue/folio-charge journal through a
   **no-commit/flush-only cost-center helper**. **Revision 3 removes
   "pre-warm cost centers with a commit before acquiring the order lock" as
   an option — approved decision: the paid workflow must contain exactly
   one successful commit, full stop, with no configuration-seeding commit
   before or inside the payment attempt.** Concretely: `ensure_default_cost_centers`
   gained a `commit: bool = True` parameter (default preserves every
   existing caller's behavior unchanged); the strict Dining path always
   calls it with `commit=False` so a missing default cost center is
   created via **flush only**, inside the same transaction as everything
   else. **Exact rule (implemented):** if a default cost center is
   missing, it *is* created as a side effect of the payment attempt —
   flush-only, no independent commit — and on overall success it becomes
   durable together with the single outer `db.commit()`; on any later
   failure it rolls back with everything else, exactly like it was never
   created. **Fail-closed cases**, both raising `FinancialConfigurationError`
   (caught by the same outer rollback path as any other failure): a
   required GL account is missing for the branch, or the cost center is
   *still* unavailable after the flush-only preparation attempt (e.g. the
   flush itself failed). Missing GL/cost-center configuration never leaks
   raw SQL/DB error text to the API response — it surfaces as `503`
   `FINANCIAL_CONFIGURATION_ERROR` with a clean Arabic message.
7. Exactly **one** outer `db.commit()` on full success.
8. On any failure inside the unit of work: explicit `db.rollback()`.
9. Distinguish intentional "not inventory-linked" outcomes from actual
   errors, as in step 5.

**Folio serialization (new, concrete design for revision 3):**
- Add `backend/app/modules/finance/crud.py` to expected files.
- Add a blocking row lock on `Folio` (`SELECT ... FOR UPDATE`, no `NOWAIT`
  — **decision confirmed and implemented**: a folio charge waits briefly
  for a concurrent charge/settlement to finish rather than rejecting
  outright, unlike the Order/Product NOWAIT locks below) acquired
  **before** `FolioCharge` insertion and before `recalculate_folio_total`.
- **Centralize through the existing `add_charge` path** (`finance/
  crud.py:169`) rather than each of the five callers re-implementing
  locking independently — confirmed callers, all currently calling
  `add_charge` directly with no lock: `beach/services.py:297`,
  `dining/services.py:740` (`update_order_status`),
  `dining/services.py:1071` (`split_bill`), `finance/services.py:99`
  (`post_charge`), `pms/services.py:317` (`request_early_late`). Locking
  inside `add_charge` (or a thin wrapper all five are migrated to call)
  means all five inherit the fix without duplicating lock-acquisition
  logic at each call site.
- `recalculate_folio_total` (`finance/crud.py:194`) currently does
  `db.expire(folio, ["charges"])` then sums the relationship — this expires
  the *collection*, not the `folio` row itself. Under the new lock, this
  must be re-verified/corrected to use `populate_existing()` (or equivalent
  fresh-read semantics) so `folio.total` is computed from charges that are
  fully committed and visible under the lock, not stale session-cached
  data left over from before the lock was acquired — the same class of
  identity-map staleness issue CLAUDE.md §13 bullet ⓫ documents for beach/
  timeshare locking.
- **Document caller impact**: locking inside `add_charge` changes its
  latency/blocking characteristics for all five existing callers, not just
  Dining's new strict path. Each existing caller's behavior under
  contention must be reasoned about (do any of them currently assume
  `add_charge` never blocks?) before this change ships.
- **Add regression tests for existing charge flows** — `post_charge`
  (finance's own direct-charge endpoint), beach's charge-to-room path, and
  PMS's `request_early_late` must all continue to behave identically for
  the non-concurrent case after the lock is added.

**Branch authorization — corrected scope for revision 3:** apply
`core.services.assert_branch_access(db, user, order.branch_id, ...)` (the
exact Gate 1A helper, `app/modules/core/services.py`) to the **entire**
`PATCH /dining/orders/{order_id}/status` endpoint
(`dining/api/router.py:547-557`), not only the `"paid"` branch — the same
endpoint also cancels orders and transitions other statuses for a branch
the acting user may not belong to, and today has **no branch check at all**
for any of those transitions either. Preserve the existing `super_admin`-
only unconditional bypass. Add cross-branch rejection tests for **both** a
`"paid"` attempt and a non-paid (e.g. `"cancelled"`) attempt from a
cashier/waiter linked to a different branch. This slice does not add a new
fine-grained `permission_catalog` entry for payment processing specifically
— that belongs to the later authorization/Dining-integrity gate; recorded
as deferred, not solved.

**Exact conflict contracts (revision 3 — precise, not just "map to 409"):**

| Condition | Response |
|---|---|
| Order row lock busy (`NOWAIT` contention) | `409`, code `ORDER_PAYMENT_IN_PROGRESS` |
| Order already `"paid"` (status re-check under lock finds a prior commit) | `409`, code `ORDER_ALREADY_PAID` |
| Inventory product-row lock busy (`InventoryConcurrencyError`) | `409`, code `INVENTORY_BUSY` |
| Branch mismatch (`PermissionError` from `assert_branch_access`) | `403` |
| Any other DB/configuration error (missing GL account, constraint violation, anything not caused by concurrent access to this order/product/folio) | **Not** mapped to `409`; surfaces as a real error (500, or 400 for a validation-shaped `ValueError`, matching existing router convention) — and never exposes raw SQL/driver error text in the response body |

**Migration impact:** none expected — locking uses `SELECT FOR UPDATE`, no
new column, matching `beach.crud.lock_inventory_for_update`'s existing,
migration-free precedent. The no-commit cost-center helper reuses
`ensure_default_cost_centers`'s existing logic with a commit toggle; no
schema change.

**Rollback approach:** pure code revert (no migration to reverse).
Functionally: a failed "mark paid" attempt must leave zero trace — no
committed order-status change, no folio charge, no stock movement, no
journal entry, **no cost-center seeding either** (revision 3's "exactly one
commit" rule makes this automatic rather than a separate concern) —
verified by querying a **fresh** database session after the failure, not
just asserting on the in-memory/rolled-back session object.

**Failure-injection tests:**
- FolioCharge creation failure → full rollback, order not paid.
- Missing GL account / failing revenue journal → full rollback, no
  cost-center row created either.
- Inventory movement failure occurring after the order's paid state was
  already staged in-session → full rollback of the staged state too.
- COGS journal failure → full rollback.
- Missing cost-center path exercised **without** any commit firing
  mid-transaction — assert via a commit-count probe that only one commit
  happens for the whole request, covering both the "cost centers already
  exist" and "cost centers must be created but fail closed instead" cases.
- Inventory (product-level) lock contention → `409 INVENTORY_BUSY`.
- Concurrent "mark paid" on the same order → one succeeds, the other gets
  `409 ORDER_PAYMENT_IN_PROGRESS` or `409 ORDER_ALREADY_PAID` depending on
  timing, never a second silent success.
- Concurrent charges affecting the same folio from two different orders →
  both succeed with correct, non-clobbered folio totals (serialized by the
  new folio lock), never a lost update.
- Cross-branch rejection: a `"paid"` attempt and a `"cancelled"` attempt,
  both from a cashier/waiter linked to a different branch than the order →
  both `403`, before any lock is even acquired.
- For every case above: reconnect with a fresh session after the test and
  query the DB directly to confirm nothing persisted.

**Test cardinality — corrected for revision 3:**
- Exactly **one** revenue `JournalEntry` for a normal (non-room-charged)
  paid order (the folio-charge and cash-revenue postings are mutually
  exclusive branches of the same `if order.folio_id: ... else: ...`, never
  both).
- Exactly **one** `FolioCharge`, and only for a room-charged order — zero
  for a cash order.
- `StockMovement` and COGS-journal-line counts follow the number of
  **consumed recipe/product lines actually deducted**, not "one per order
  item" — a single order item with a multi-line recipe produces one
  `StockMovement` per recipe line (confirmed: `_deduct_inventory_for_order`
  loops `recipe_lines` and calls `consume_stock` once per line when a
  recipe exists, `dining/services.py:790-806`); an item with no recipe and
  no `linked_product_id` produces zero.

**Acceptance criteria:**
- Zero nested commits inside the strict "paid" unit of work, including the
  cost-center path — provable by test (commit-count probe), not just code
  review.
- No bare `except Exception: pass`/silent-`None`-tolerant path remains in
  the "paid" transition's financial writes.
- A folio-charge, inventory, COGS, journal-posting, or missing-configuration
  failure aborts the entire transaction.
- Concurrent double-payment attempts on the same order are serialized;
  exactly one succeeds, with the correct distinguishable conflict code.
- Concurrent charges to the same folio are serialized, not lost.
- Branch authorization enforced on the whole endpoint (paid and non-paid
  transitions), with passing cross-branch rejection tests for both.
- All existing dining tests still pass, updated only where they asserted
  the old fail-open/no-lock/no-branch-check behavior.
- New failure-injection and concurrency tests pass on real Postgres.
- `alembic heads` — still one head (no migration added).

**Expected files:**
- `backend/app/modules/dining/services.py` — the strict unit-of-work.
- `backend/app/modules/dining/crud.py` — `get_order_for_update`.
- `backend/app/modules/dining/api/router.py` — branch-access check applied
  to the whole endpoint, conflict-code → HTTP-status translation.
- `backend/app/modules/inventory/services.py` — no-commit primitive for
  `record_movement`/`consume_stock`, preserving the existing public API for
  every other caller.
- `backend/app/modules/inventory/crud.py` — only if a new internal helper
  is needed; no public API change expected.
- `backend/app/modules/finance/services.py` — no-commit cost-center helper
  (commit toggle on `ensure_default_cost_centers` or an equivalent
  flush-only variant), scoped narrowly.
- `backend/app/modules/finance/crud.py` — the blocking `Folio` lock,
  centralized in `add_charge`; corrected `recalculate_folio_total`
  fresh-read semantics.
- Tests: `backend/tests/test_api/test_dining_http.py`,
  `test_pos_full_cycle_http.py`, regression tests for `post_charge`/beach
  charge-to-room/`request_early_late` (existing-flow-unchanged proof for
  the new folio lock), plus a new dedicated Postgres-only concurrency test
  module (matching the existing `test_dining_migration.py`-style
  skip-by-DSN-condition pattern) for order-lock, folio-lock, and
  inventory-lock contention scenarios.
- No new dependency.

**Explicitly deferred, not solved by this slice:**
- Dining's `update_order_status` creates no `Payment` row at all for cash
  sales, unlike `beach.sell_ticket`'s `_record_shift_payment` — confirmed;
  no `finance.crud.create_direct_payment`-equivalent call exists anywhere
  in `dining/services.py`. Dining cash sales are not attributable to a
  cashier/shift today.
- **New in revision 3, confirmed by direct code read:** Dining's inventory
  movements are posted with `moved_by=0` hardcoded (`dining/services.py:
  804,822`), and both dining journal-posting call sites
  (`_post_order_revenue_journal`, `_post_order_folio_charge_journal`) never
  pass `created_by`, defaulting to `post_simple_revenue_journal`'s
  `created_by: int = 0`. **The "paid" transition has no complete actor/
  audit trail** — nothing in the inventory movement or journal entry
  records which staff member actually processed the payment. Combined with
  the missing `Payment`/cashier/shift attribution above, this is a real,
  confirmed gap. These remain **Gate 5**, not solved here.
- Payment actor/audit attribution beyond generic order fields is
  incomplete.
- `payment_method` defaults silently to `"cash"` when not supplied
  (`services.py:669-671`).
- The full Dining state machine, an order-level idempotency key, and a
  fine-grained payment permission entry belong to Gate 5.
- Zero-total/complimentary order handling: `post_simple_revenue_journal`
  currently returns `None` silently for `amount <= 0`
  (`finance/services.py:872-873`). The strict path must fail closed
  (reject the "paid" transition explicitly) for a zero/negative-total order
  until an approved complimentary-order workflow exists.

**Exact validation commands — for implementation time, not now:**
```bash
cd backend
# targeted, during development:
.venv/bin/pytest tests/test_api/test_dining_http.py tests/test_api/test_pos_full_cycle_http.py -v
# full suite before considering the slice complete:
.venv/bin/pytest tests/ -v
.venv/bin/alembic heads
cd ../frontend
pnpm run type-check:all
pnpm run build:all
cd ..
docker compose config --quiet
docker compose -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-only.yml config --quiet
git diff --check
git status --short --branch
```
A dedicated real-Postgres concurrency test run (separate from the
SQLite-backed default suite) is required for the order-lock, folio-lock,
and inventory-lock contention scenarios. **None of the above has been run
in this revision** — the full suite, migration checks, and concurrency
tests are implementation-time steps, not part of this plan-only revision.

---

## 3. Implementation summary (revision 3 → actual build, 2026-07-17)

Implemented as designed, with the folio/order/product lock decisions from
§2 confirmed exactly as drafted (blocking `Folio` lock, `NOWAIT` for
`Order`/`Product`). No deviations from the approved design; the notes
below record what shipped concretely.

**New/changed production code:**
- `finance/services.py` — `FinancialConfigurationError` exception class;
  `ensure_default_cost_centers(..., commit: bool = True)`;
  `post_simple_revenue_journal(..., commit_cost_centers: bool = True,
  strict: bool = False)` (raises `FinancialConfigurationError` on missing
  account/cost-center/FX-failure when `strict=True`); new
  `FolioClosedError` exception; new `add_folio_charge(db, folio_id, data)`
  — the single centralized entry point that locks the folio
  (`crud.lock_folio_for_update`, blocking), re-checks `folio.status` under
  the lock (rejects `closed`/`cancelled`), inserts the charge, and
  recalculates the total from a fresh read; `post_charge` and
  `settle_folio` both now acquire the same folio lock before doing
  anything else.
- `finance/crud.py` — new `lock_folio_for_update` (blocking `FOR UPDATE`
  + `populate_existing()`); `recalculate_folio_total` rewritten to query
  `FolioCharge` fresh with `populate_existing()` instead of
  `db.expire(folio, ["charges"])`.
- `inventory/crud.py` — `lock_product_for_update` gained the missing
  `.populate_existing()`.
- `inventory/services.py` — `record_movement(..., commit: bool = True)`
  now locks the product *first* (`crud.lock_product_for_update`, wrapped
  in the standard `OperationalError` → `InventoryConcurrencyError`
  pattern) and runs the negative-stock check against that freshly-locked
  row, not a pre-lock read; `consume_stock(..., commit: bool = True,
  strict: bool = False)` passes both through; `_post_cogs_journal(...,
  commit_cost_centers: bool = True, strict: bool = False)` mirrors
  `post_simple_revenue_journal`'s strict contract exactly.
- `dining/crud.py` — new `get_order_for_update` (`NOWAIT` +
  `populate_existing()`, mirrors `beach.crud.lock_inventory_for_update`).
- `dining/services.py` — three new exception classes
  (`OrderPaymentConcurrencyError`, `OrderAlreadyPaidError`,
  `InvalidOrderTotalError`); `update_order_status` now delegates the
  `"paid"` transition entirely to a new private `_mark_order_paid`, which
  is the strict unit of work: lock the order → reject if already
  paid/cancelled → reject zero/negative total → assign payment
  method/folio → transition status → release table → `add_folio_charge`
  (if room-charged) → `_deduct_inventory_for_order(commit=False,
  strict=True)` → post the revenue or folio-charge journal
  (`commit_cost_centers=False, strict=True`) → best-effort CRM visit
  (unchanged, non-financial) → exactly one `db.commit()`; the whole body
  is wrapped in `try/except Exception: db.rollback(); raise`. Non-`"paid"`
  transitions keep their pre-existing behavior unchanged, minus the
  now-dead `"paid"`-only branches that were removed as part of the
  refactor. `_deduct_inventory_for_order`/`_post_order_revenue_journal`/
  `_post_order_folio_charge_journal` all gained the same
  `commit`/`strict`/`commit_cost_centers` passthrough params,
  default-`True`/`False` so `split_bill` (explicitly out of scope) is
  behaviorally unchanged.
- `dining/api/router.py` — `PATCH /dining/orders/{id}/status` now calls
  `core.services.assert_branch_access` before *any* status mutation
  (super_admin bypass preserved), then maps the new exceptions precisely:
  `OrderPaymentConcurrencyError`→409 `ORDER_PAYMENT_IN_PROGRESS`,
  `OrderAlreadyPaidError`→409 `ORDER_ALREADY_PAID`,
  `InvalidOrderTotalError`→400 `INVALID_ORDER_TOTAL`,
  `InventoryConcurrencyError`→409 `INVENTORY_BUSY`,
  `FinancialConfigurationError`→503 `FINANCIAL_CONFIGURATION_ERROR`,
  `FolioClosedError`→400, generic `ValueError`→400 (existing convention).
  Codes are carried in the `HTTPException.detail` dict
  (`{"error_code": ..., "message": ...}`) — no prior router in this
  codebase used the kernel's `APIError`/`error_code` machinery for a
  per-endpoint contract like this, so a plain structured `detail` dict was
  used instead of introducing that pattern for a single endpoint.
- `beach/services.py`, `pms/services.py`, `dining/services.py`
  (`split_bill` only) — the three other confirmed `add_charge` call sites
  (charge-to-room, `request_early_late`, split-bill room charges) were
  migrated to call the new `finance.services.add_folio_charge` instead of
  `finance.crud.add_charge` directly, so they inherit the folio lock
  without any of their own (unchanged) swallow-on-failure behavior being
  touched. **Superseded by §4 item 3 below** — this "unchanged
  swallow-on-failure" description was accurate for this round-1 state
  only. The first post-implementation Codex review correctly flagged that
  leaving the swallow in place meant a folio-lock failure could still be
  silently absorbed; §4 item 3 removes the swallow and adds an explicit
  `db.rollback()` in all three sites, a deliberate fail-closed behavior
  change, not a no-op migration. §4 item 3 also documents an independent,
  pre-existing bug this change surfaced in `pms/services.py`.

**Deviations from the plan:** none. The one open question the plan left
explicit ("NOWAIT vs blocking for the folio lock — to be confirmed during
implementation") was resolved as blocking, matching the plan's own stated
default rationale, and is now recorded as a confirmed decision in §2
above rather than an open item.

**Test-fixture fallout (expected, not a design change):** enabling
`strict=True` financial failures surfaces a real, pre-existing gap in
several test fixtures across `test_dining.py`, `test_food_cost_report.py`,
`test_menu_item_variants.py`, `test_pos_full_cycle_http.py`,
`test_refund_after_payment_http.py`, `test_hr.py`, and
`test_analytics_tasks.py`: many paid-order test setups never created the
GL accounts (`1100`/`1150`/`1200`/`5200`/revenue codes) that `seed.py`
always creates in a real environment, and several HTTP-level tests used
the shared, branch-unlinked `waiter_headers`/`cashier_headers`/
`manager_headers` fixtures to transition orders on ad-hoc test branches —
previously invisible because the old code silently no-opped on missing
accounts and had no branch check at all. Both gaps were fixed at the test
level (extended `make_finance_accounts` helpers; new
`make_branch_linked_headers` helpers following the exact pattern already
established in `test_guest_alerts.py` for Gate 1A), not by weakening the
new strict/branch-check behavior. One test
(`test_food_cost_report.py::test_cancelled_item_excluded_from_sales`) had
a genuine behavior-changing scenario (an order whose only item is
cancelled now correctly rejects the resulting zero-total "paid" attempt
via `INVALID_ORDER_TOTAL`) and was adjusted to add a second, non-cancelled
item so the order retains a positive total — matching the existing
sibling test's established pattern for isolating item-level behavior from
order-level payability.

**Tests added:**
- `backend/tests/test_api/test_dining_paid_atomicity.py` (SQLite,
  17 tests) — exactly-one-commit probe (plain and cost-center-seeding
  paths), fresh-session zero-side-effects proof for missing-GL-account,
  closed-folio, inventory-lock-contention, and missing-COGS-account
  failures; zero-total rejection; stale-identity-map proof for
  `get_order_for_update` and `lock_folio_for_update` (mirrors
  `test_beach.py`'s `dbA`/`dbB` pattern); same-order double-payment
  (sequential and lock-contention-simulated); full router error-code
  contract (503/400/409×2/403×2, plus the super_admin bypass).
- `backend/tests/test_dining_paid_concurrency.py` (Postgres-only, 4
  tests, skips by default via `DINING_CONCURRENCY_TEST_ADMIN_URL`,
  mirrors `test_dining_migration.py`'s throwaway-database pattern exactly)
  — genuine multi-threaded proof against a live Postgres: (1) a second
  concurrent "paid" attempt gets `OrderPaymentConcurrencyError` while the
  first thread demonstrably still holds the order's `NOWAIT` lock, and a
  subsequent attempt succeeds once released; (2) two orders charged to the
  same folio simultaneously both succeed with a correct, non-clobbered
  combined `folio.total` (proves the blocking folio lock actually
  serializes instead of losing an update); (3) a genuine add-charge-vs-
  settle race resolves to exactly one of the two contractually valid
  outcomes (a charge on a still-open folio, or a closed folio with zero
  unsettled charges) and never the excluded third outcome (a closed folio
  missing the raced charge); (4) product-lock contention gets
  `InventoryConcurrencyError` under the same real-lock-holding technique
  as (1). **Actually run against the live dev Postgres instance
  (`localhost:5436`) during this implementation — all 4 passed; throwaway
  databases confirmed cleaned up afterward.** This is genuine concurrency
  acceptance, not a claim made without infrastructure to back it.

**Residual risks confirmed still open (unchanged from §2's deferred
list):** `moved_by=0`/`created_by=0` payment-actor attribution, no
`Payment`/cashier/shift row for Dining cash sales, no fine-grained payment
permission entry, no full Dining state machine/idempotency key, and —
newly explicit per binding clarification — **concurrent delete/refund/void
`FolioCharge` mutations are not covered by this slice's folio lock**;
`dining.services._reduce_folio_charge_for_refund` still reads/mutates a
`FolioCharge` row without acquiring `lock_folio_for_update` first. This is
a real, documented gap for a future gate, not a claim that all Folio
mutation races are solved.

**Full validation actually run (this revision, not projected):**
- `pytest tests/ -v` → **1847 passed, 7 skipped** (7 skips: pre-existing
  ETA/eslint-adjacent skips plus the 4 new Postgres-only concurrency tests
  skipping by default with no DSN set).
- `DINING_CONCURRENCY_TEST_ADMIN_URL=... pytest
  tests/test_dining_paid_concurrency.py -v` → **4 passed**, run against
  live Postgres at `localhost:5436` (throwaway database per test, cleaned
  up).
- `alembic heads` → single head, unchanged — confirms no migration was
  needed, matching this section's own prediction.
- `pnpm run type-check:all` and `pnpm run build:all` (both `el-kheima` and
  `public`) → clean (zero frontend files touched by this slice).
- `docker compose config --quiet` (base), `-f docker-compose.prod.yml`,
  and `-f docker-compose.prod.yml -f docker-compose.prod.ip-only.yml` →
  all three valid.
- `git diff --check` → no whitespace errors. `git status --short
  --branch` → clean working tree on `gate-1b-financial-atomicity` aside
  from this slice's own changes.
- An independent self-review pass (separate agent, fresh read of the full
  production-code diff against six risk categories) ran **before** the
  first post-implementation Codex review and reported no findings in that
  pass. **That result was superseded**: the first Codex review that
  followed found several real, confirmed defects (documented in full in
  §4) that this self-review pass missed — most notably that "no explicit
  `db.commit()`" alone does not guarantee no partial persistence
  (flushed-but-uncommitted rows remain visible to other sessions on this
  test suite's shared `StaticPool` connection until an explicit
  `db.rollback()` runs), and the several silent-skip/broad-except gaps
  documented in §4. This file does not claim "zero defects" — the
  self-review's clean result was real but incomplete, and the honest
  status is "fixed once, pending a second review," not "verified clean."
No files have been staged, committed, or pushed. `wagdy.md` **has** been
updated (a new dated Gate 1B section, in simple Arabic, describing this
work as implemented-but-not-yet-approved — see the file itself, not this
plan doc, for the exact wording). Gate 2 has not started and remains
blocked pending the second Codex review of this implementation.

---

## 4. Round 2 review fixes (2026-07-18, after the first post-implementation Codex review)

The first Codex review of the implementation described in §3 found seven
categories of real, confirmed issues. Each is fixed and re-tested below;
none were theoretical — every fix was verified against a failing test
before being applied, and the test suite was re-run green after.

1. **Blanket `OperationalError` → 409 conversion was too broad.**
   `dining/services.py` (around `get_order_for_update`) and
   `inventory/services.py` (around the product lock, in `record_movement`
   and — after fix #5 below — `consume_stock`) converted *any*
   `OperationalError` into a domain concurrency error (409), including
   errors with no relation to row-lock contention (e.g. a lost
   connection). Fixed with a new shared helper,
   `app/core/db_errors.py::is_lock_not_available`, which checks
   `exc.orig.sqlstate == "55P03"` (PostgreSQL's `lock_not_available`,
   the code `SELECT ... FOR UPDATE NOWAIT` raises on real contention) —
   any other `OperationalError` now propagates untouched to the generic
   secure-500 handler. New tests in `tests/conftest.py`
   (`make_lock_not_available_error`/`make_unrelated_operational_error`)
   and companion "unrelated error is not masked" tests in
   `test_inventory.py` and `test_dining_paid_atomicity.py` prove both
   directions.

2. **Strict inventory deduction still silently skipped real configuration
   gaps.** `dining/services.py::_deduct_inventory_for_order` had several
   bare `continue` statements that did not distinguish "item genuinely has
   no recipe and no linked product" (the one case that must stay silent,
   even in `strict=True`) from real data-integrity problems: a missing
   `DiningItem`, a missing recipe/linked product, a product with no
   warehouse, or a product belonging to a different branch than the
   order. Fixed with a new `InventoryConfigurationError` (503
   `INVENTORY_CONFIGURATION_ERROR`), raised for every one of those cases
   when `strict=True`, via a small `_skip_or_raise` helper that keeps the
   non-strict (`split_bill`) behavior byte-for-byte identical. Four new
   fresh-session-zero-side-effects tests in `test_dining_paid_atomicity.py`
   cover missing linked product (via monkeypatch, since the real FK is
   `ON DELETE SET NULL` and cannot produce a genuinely dangling row in
   this test schema), cross-branch product, and no-warehouse product.

3. **`add_folio_charge` failures were still swallowed in three call
   sites** — `beach/services.py` (charge-to-room), `pms/services.py::
   request_early_late`, and `dining/services.py::split_bill` — each with
   its own `except Exception: pass` (beach, split_bill) or log-then-swallow
   (pms). This meant a beach sale, a PMS extra charge, or a split-bill
   room portion could all "succeed" and commit with no corresponding
   `FolioCharge` if the folio was closed or the charge failed for any
   other reason. `FolioClosedError` now inherits from `ValueError` (so
   each router's existing generic `except ValueError → 400` catches it
   without new per-router wiring). Removing the swallow alone was **not
   sufficient** — a real gap was found and fixed here: on this test
   suite's SQLite `StaticPool` setup (and, more importantly, as a general
   correctness matter not specific to the test environment), a flushed
   but never-committed row remains visible until an *explicit*
   `db.rollback()` runs; "just don't call `db.commit()`" left the
   already-flushed transaction/inventory/order-status rows visible to a
   fresh verification query. All three sites now wrap the
   `add_folio_charge` call in `try/except Exception: db.rollback(); raise`.
   Three new zero-trace tests (`test_beach.py`,
   `test_pms.py`, `test_dining.py::TestSplitBillFolioFailClosed`) prove a
   closed folio leaves no BeachTransaction/capacity change, no
   Booking field mutation, and no `paid` order / FolioCharge, respectively
   — each written *first* against the "remove the swallow only" fix, where
   they failed, which is what surfaced the missing-rollback gap.

   **A second, independent real bug surfaced by this same fix**:
   `pms/services.py::request_early_late`'s `FolioChargeCreate(...)` call
   was missing the required `posted_at` field entirely — a pre-existing
   bug, not introduced by Gate 1B. Under the old swallow-after-logging
   behavior this `pydantic.ValidationError` fired on *every* early/late
   charge with a folio and was silently caught, meaning **no PMS
   early-checkin/late-checkout charge has ever actually posted a
   `FolioCharge` in this codebase's history** — the booking's own
   `extra_charge`/`total_rate` fields updated correctly (that mutation
   happens before the try block), giving the appearance of success, but
   the guest's folio itself was never charged. Caught by
   `tests/test_api/test_pms_coverage.py::test_pms_late_checkout_with_charge`
   (a pre-existing, unrelated test) failing 400 instead of 200 once the
   swallow was removed — not a new test written for Gate 1B. Fixed by
   adding `posted_at=datetime.utcnow()`, matching the pattern already used
   at the other three `FolioChargeCreate` call sites (dining ×2, beach).

4. **No `payment_method`/`folio_id` consistency contract.** Nothing
   previously prevented `payment_method="room"` with no folio to charge,
   `charge_to_room_id` combined with `payment_method="cash"/"card"`, or
   (pre-existing folio, no explicit method) silently defaulting to
   `"cash"` while a folio charge was about to post. Fixed with a new
   `InvalidPaymentMethodError` (400 `INVALID_PAYMENT_METHOD`) raised
   before any mutation for the first two cases, an explicit default to
   `"room"` (not `"cash"`) when a folio is or will be present and no
   method was supplied, and a final belt-and-suspenders invariant check
   (`bool(order.folio_id) == (order.payment_method == "room")`) right
   before the status transition. Five new tests in
   `test_dining_paid_atomicity.py::TestPaymentMethodFolioConsistency`.
   Explicitly **not** extended to card/wallet GL design or
   Payment/cashier/shift attribution — those remain documented Gate 5
   risks, per instruction, not addressed here.

5. **Stale pre-lock `cost_price` read in `consume_stock`.**
   `inventory/services.py::consume_stock` read `product.cost_price` via
   an unlocked `get_product_or_404` *before* `record_movement` acquired
   the row lock, so `StockMovement.unit_cost` and the COGS journal amount
   could be built from a stale price if another transaction changed
   `cost_price` in between. Fixed by having `consume_stock` itself lock
   the product first (`crud.lock_product_for_update`, the same lock
   `record_movement` re-acquires — reentrant and safe within one
   Postgres transaction, the same accepted pattern already used
   elsewhere in this codebase) and read `cost_price` from that locked
   row. A new `dbA`/`dbB` real-session regression test in
   `test_inventory.py` (mirroring `test_beach.py`'s established pattern)
   proves `unit_cost` and the COGS journal line reflect the freshly
   committed price, not an earlier identity-map read.

6. **Thread-based Postgres concurrency tests didn't verify threads
   actually finished.** `tests/test_dining_paid_concurrency.py` read
   result dictionaries populated by worker threads immediately after
   `thread.join(timeout=...)`, without checking `thread.is_alive()` — a
   hang would have produced a confusing `KeyError` on a missing dict key
   instead of a clear "thread did not finish" failure. All four
   `join()` call sites now assert `not thread.is_alive()` with an
   explicit message before touching any thread-populated state.

7. **Documentation overclaims** — this file's header still said "no
   product code has been implemented" beneath a populated §3
   Implementation Summary; falsely claimed `wagdy.md` was untouched; and
   the self-review's "zero confirmed defects" line stood unqualified
   after a real review found real defects. All three are corrected above
   (see the status block at the top of this file and the note right
   before this section). `wagdy.md`'s Gate 1B section is being updated
   in the same pass to say "implemented, pending second review" — not
   "approved" or "closed."

**Full validation re-run after all seven fixes plus the PMS `posted_at`
bug fix (2026-07-18):**
- `pytest tests/ -v` → **1861 passed, 7 skipped, 0 failed** — a verified
  **+14** net increase over the pre-round-2 baseline (1847 passed),
  computed by direct subtraction of the two actual `pytest` run totals,
  not by counting new test functions (an earlier draft of this section
  guessed "+26 new tests" from a rough count of added `def test_` lines;
  that number does not equal the net pass-count delta once a pre-existing
  test's status is accounted for — `test_pms_coverage.py::
  test_pms_late_checkout_with_charge` was silently passing for the wrong
  reason before this round and now correctly exercises the fixed code
  path — and has been corrected here to the actual measured delta).
- `DINING_CONCURRENCY_TEST_ADMIN_URL=... pytest
  tests/test_dining_paid_concurrency.py -v` → **4 passed**, re-run against
  live Postgres after the thread-hardening fix (#6 above).
- `alembic heads` → single head, unchanged.
- `pnpm run type-check:all` / `build:all` → clean (still zero frontend
  files touched).
- `docker compose config --quiet` (base + prod + prod/ip-only) → all
  three valid.
- `git diff --check` → no whitespace errors.
**Still no commit, no push, no Gate 2 — stopped here for the second Codex
review.**

---

## 5. Round 3 micro-fixes (2026-07-18, after the second post-implementation Codex review)

The second Codex review accepted the seven round-2 fixes in substance but
found one remaining gap plus test-coverage/documentation follow-ups.
Fixed and re-tested below.

1. **Missing `db.rollback()` in `inventory/services.py::consume_stock`'s
   first lock-acquisition failure.** `consume_stock`'s own
   `crud.lock_product_for_update` call (added in round 2, fix #5, to read
   `cost_price` from a freshly-locked row) raised
   `InventoryConcurrencyError` on real lock contention (SQLSTATE 55P03)
   without first calling `db.rollback()` — on real PostgreSQL this leaves
   the transaction in `aborted` state, so any further use of that same
   session (even a plain read) fails with `InFailedSqlTransaction` until
   an explicit rollback runs. This specifically harmed direct/non-strict
   callers of `consume_stock` outside `_mark_order_paid`'s own outer
   rollback wrapper (`record_movement`'s two equivalent lock-failure
   branches already had the rollback from round 2 — only this one,
   newer, call site was missing it). Fixed by adding `db.rollback()`
   before raising. Two new tests: a SQLite-level test
   (`test_inventory.py::test_consume_stock_lock_failure_rolls_back_and_session_stays_usable`)
   proving the session remains usable for a subsequent real DB operation
   immediately after catching the error, and a real-Postgres test
   (`test_dining_paid_concurrency.py::
   test_consume_stock_itself_gets_busy_and_session_stays_usable`) calling
   `consume_stock` itself (not just `record_movement`) under genuine lock
   contention from a second thread.

2. **Incomplete warehouse/branch validation in strict inventory
   deduction.** `_deduct_inventory_for_order`'s strict-mode checks
   verified `product.branch_id == order.branch_id` and that
   `product.warehouse_id` was non-null, but never verified the
   *warehouse itself* exists or belongs to the order's branch.
   `inventory.services.create_product` has no validation tying a
   product's `warehouse_id` to its own `branch_id` — a product legitimately
   assigned to branch A can be linked to a warehouse belonging to branch
   B, and the old check would have let that pass silently through to
   `consume_stock`. Fixed by fetching the `Warehouse` row via
   `inventory_crud.get_warehouse` and checking both existence and
   `warehouse.branch_id == order.branch_id`, in both the recipe-line and
   linked-product branches. New fresh-session regression test
   (`test_dining_paid_atomicity.py::
   test_product_with_cross_branch_warehouse_aborts_everything`) proves a
   product correctly assigned to the right branch but linked to a
   cross-branch warehouse aborts the whole payment with zero trace: no
   paid order, no `StockMovement`, no `JournalEntry`.

3. **Test coverage gaps closed.** Added:
   `test_recipe_product_missing_in_strict_mode_aborts_everything` (a
   recipe line pointing at a product `get_product` can't find, via
   monkeypatch since the real FK is `ON DELETE RESTRICT` and cannot
   produce a genuinely dangling row here); HTTP-level exact-code tests
   for `INVALID_PAYMENT_METHOD` (400) and `INVENTORY_CONFIGURATION_ERROR`
   (503), matching the existing pattern for the other five error codes;
   and an HTTP-level (not just service-level) proof that an unrelated
   `OperationalError` reaches the client as a generic 500 through
   `SecureErrorMiddleware` with no SQL/driver/file-path text anywhere in
   the response body.

4. **Weak assertion in the PMS `posted_at` bug-fix test.**
   `test_pms_coverage.py::test_pms_late_checkout_with_charge` (the
   pre-existing test that caught the round-2 `posted_at` bug) only
   asserted `HTTP 200` and the booking's `total_rate` — both of which
   the old, broken code also satisfied, since those mutations happen
   before the swallowed `FolioChargeCreate` failure. Strengthened with
   positive assertions: exactly one `FolioCharge` exists, with the
   correct `charge_type` (`"room_extra"`), `amount` (150), a `posted_at`
   within 5 minutes of test execution, and `folio.total` updated to the
   correct value (150).

5. **Documentation numbers and claims corrected** (this section and the
   status note above §4): the round-2 pass-count delta is the verified
   **+14** (1847→1861 by direct subtraction), not the earlier guessed
   "+26 new tests." `wagdy.md`'s claim that Beach/PMS/split_bill moved to
   the centralized folio lock "without any visible behavior change" was
   wrong and has been corrected there: the behavior change to fail-closed
   was deliberate, and PMS specifically began persisting a real
   `FolioCharge` for the first time in the codebase's history (see §4
   item 3's bug account). Both documents now also state explicitly that
   Beach's `sell_ticket` and `split_bill` remain fail-open in financial
   respects *other than* the `add_folio_charge` path fixed in §4 item 3
   — this slice did not audit or fix every fail-open call site in those
   two functions (see the original §1 call-site inventory for what else
   is still open in Beach specifically).

**Deferred risks — documented only, not addressed in this round (do not
expand scope):**
- The current order lock (`get_order_for_update`, held only for the
  duration of `_mark_order_paid`) does not protect against a race between
  a "paid" attempt and a concurrent `split_bill` call, or a concurrent
  add-items/void-item/apply-discount call, on the same order — those
  other endpoints do not acquire the same lock. Closing this gap requires
  the fuller Dining state-machine/idempotency work already scoped to
  Gate 5, not a Gate 1B micro-fix.
- Branch isolation is not yet enforced on Finance's or Beach's own folio
  endpoints (e.g. `POST /finance/folios/{id}/charges`, Beach's own
  reservation/checkin endpoints) the way it now is on
  `PATCH /dining/orders/{id}/status`. That work belongs to Gate 2
  (Super Admin / cross-cutting authorization), not this slice.

**Full validation after round 3 (2026-07-18):** see the process report
accompanying this revision for exact `pytest`/`alembic`/`pnpm`/
`docker compose`/`git diff --check` output and the final, precisely
measured pass count. **Still no commit, no push, no Gate 2 — stopped here
for the third (hopefully final) Codex review.**

---

## 6. Third/final Codex review and acceptance (2026-07-18)

Codex independently inspected the live working-tree diff and re-ran the
acceptance gates. One small test-harness defect remained: the first real-
PostgreSQL product-lock test did not release/join its holder thread or close
the holder session in its own `finally`, while equivalent cleanup lines were
duplicated after the following test. The operational code was unaffected.
The cleanup was moved to the correct test, the duplicate was removed, and
the real concurrency suite was rerun.

Final evidence collected after that correction:

- `pytest tests/ -q` → **1867 passed, 8 skipped, 0 failed** (**1875 tests
  collected**). The eight skips are the repository's explicitly conditional
  PostgreSQL-only tests when their admin DSNs are absent from the default run.
- `DINING_CONCURRENCY_TEST_ADMIN_URL=... pytest
  tests/test_dining_paid_concurrency.py -q` → **5 passed** against live
  PostgreSQL; a follow-up query confirmed that no disposable concurrency-test
  database remained.
- `alembic heads` → one unchanged head: `9989c0432ccc`.
- `pnpm run type-check:all` → passed for `el-kheima` and `public`.
- `pnpm run build:all` → passed for both applications. Existing non-blocking
  Vite warnings about shared i18n imports and large entry chunks remain and
  were not introduced by this backend-only slice.
- Base, production, and production/ip-only `docker compose config --quiet`
  checks → all passed.
- `git diff --check` → passed.

**Decision:** the bounded Dining-paid Gate 1B slice is accepted. The deferred
risks in §5 remain open by design. No commit or push was performed during the
review, and Gate 2 implementation must begin only after this diff has its own
clean checkpoint.
