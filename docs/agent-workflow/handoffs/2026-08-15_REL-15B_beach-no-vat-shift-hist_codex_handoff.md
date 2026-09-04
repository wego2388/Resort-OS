# REL-15B — Beach final price, shift reconciliation, and HIST retirement

**Date:** 2026-08-15
**Branch:** `codex/rel-15-auth-ops-readiness`
**Active commit:** `df27697d53a7ec93a10ed2f8898945ecb4a434a6`
**Active release:**
`/opt/resort-os-releases/df27697d53a7ec93a10ed2f8898945ecb4a434a6`

## Owner decision and incident

The owner reported a real Beach cashier mismatch: a ticket displayed and
collected `200 EGP`, while a hidden `28 EGP` VAT amount made the linked cash
payment and shift expectation `228 EGP`. The same report requested removing
`Restaurant HIST` and `Cafe HIST` from operations, leaving only Restaurant
and Cafe.

A second screenshot showed `GET /finance/shifts/current` returning `404`
when no shift was open. “No open shift” is a normal state, not an HTTP
resource error, so the endpoint now returns `200` with `null`.

## Implemented policy

- Beach prices are final prices. No VAT is added to a Beach ticket.
- The ticket, Payment, folio charge, CRM spend, credit transaction, journal,
  and shift use the same `BeachTransaction.total_amount` source of truth.
- Beach receipts omit the VAT row and the Staff POS states that the displayed
  total is final with no VAT added.
- Dining and ETA VAT behavior is unchanged.
- HIST outlets are soft-archived to preserve historical orders and accounting
  references. Only a dangling zero-total order with no active items may be
  cancelled by the reconciliation.

The design decision is recorded in
`docs/decisions/0006-beach-final-price-no-vat.md`.

## Controlled production reconciliation

The dry-run/apply tool is `backend/scripts/disable_beach_vat.py`. It requires
exact count guards, one exact branch named `El Kheima Beach Resort`, a literal
confirmation phrase, and a reason. It takes row locks and commits one atomic
transaction with an AuditLog record.

Pre-apply dry-run:

```json
{"applied":false,"branch_id":1,"customer_count":0,"folio_charge_count":0,"hist_active_order_count":1,"journal_count":130,"outlet_count":2,"payment_count":153,"shift_count":60,"total_vat_removed":"20284.60","transaction_count":155}
```

The first apply attempt stopped at commit because the standalone CLI had not
registered the `users` table required by `AuditLog.approved_by`. PostgreSQL
rolled the transaction back; a repeated dry-run returned the same exact
pre-apply counts, proving no partial write. Commit `df27697` adds the explicit
model registration and a standalone-process regression test.

Final apply succeeded, then the idempotency dry-run returned all zero counts.
Post-apply SQL evidence:

- active Beach VAT rows: `0`
- active Beach Payment/transaction mismatches: `0`
- active outlets: `1:Restaurant, 2:Cafe`
- active HIST outlets/orders: `0 / 0`
- dangling order `192`: `cancelled`
- transaction `267`: total `200.00`, VAT `0.00`
- transaction `268`: total `200.00`, VAT `0.00`
- shift `112`: expected `200.00`, counted `200.00`, variance `0.00`
- unbalanced active Beach journals: `0`
- active Beach VAT journal lines: `0`
- reconciliation AuditLog rows: `1`

## Verification

- Backend full suite from the documented `backend/` working directory:
  `2806 passed, 68 skipped` from 2874, with zero failures. An earlier run from
  the repository root had only two owner source-inspection failures because
  those tests intentionally use paths relative to `backend/`; both also passed
  `2/2` when rerun from the documented directory.
- Reconciliation tests: dry-run count guards, exact `200 + 28` repair,
  Payment source normalization, shift `-28 -> 0`, journal VAT removal and
  balance, HIST archive and safe dangling-order cancellation, AuditLog, and
  standalone foreign-key registration.
- Staff: unit `106/106`, mock responsive `8/8`, type-check, i18n `6324` keys,
  production build.
- Owner: build and responsive E2E `12/12`.
- `scripts/agent-check.sh`: pass; Alembic head `e2f3a4b5c6d7`.

## Immutable deployment evidence

- source archive:
  `/var/backups/resort-os/source-releases/resort-os-df27697d53a7ec93a10ed2f8898945ecb4a434a6.tar.gz`
- archive SHA-256:
  `af66a3652e2d800c3d741740d547d579259f69c5fc96d20a8e09b8a8b29fcf6d`
- verified DB dump:
  `/opt/resort-os-releases/df27697d53a7ec93a10ed2f8898945ecb4a434a6/backups/resort_os_20260815_001751.dump`
- dump size/SHA-256/mode: `751035` bytes,
  `1c6851f7602f0ca41ae35b3f07c6e34a6e2bbdf5f4028bb5c62c7ccbb20132a7`,
  `0600`; `pg_restore --list` passed.
- rollback manifest:
  `/var/backups/resort-os/source-releases/df27697d53a7ec93a10ed2f8898945ecb4a434a6-rollback-images.txt`
- backend, worker, and beat use identical image
  `sha256:05aecfe436096d6fe94d6d087ad66b5c50bc3d0439fc348f9e9f4ef138c87412`,
  revision `df27697...`, and `RestartCount=0`.
- Staff, Owner, backend, worker, beat, and Nginx use the final release working
  directory; Marketing was deliberately preserved.
- `elkheima.com`, `www`, Staff, and Owner return `200`; protected API returns
  `401`; health is OK; TLS SAN contains all four names; DB/Redis remain bound
  to loopback only.
- Resort OS health gate passed `16/16`. The only item in `systemctl --failed`
  is the separate WegoDivers staging health service, outside Resort OS.
- No traceback/critical/fatal/emergency event exists in the released service
  logs. The string `notify_critical_work_order` is only a registered Celery
  task name, not an error.

## Human UAT

1. Open a fresh Beach cashier shift with zero opening float.
2. Sell one adult Beach ticket priced `200 EGP` for cash.
3. Confirm the receipt has no VAT row and total `200 EGP`.
4. Close the shift with counted cash `200 EGP`; expected and variance must be
   `200 / 0`.
5. Open Dining POS and confirm the outlet selector contains only Restaurant
   and Cafe.
6. With no open shift, confirm the UI shows the normal empty state without a
   red `404` request in the browser Console.

No credential, enrollment token, recovery code, TOTP secret, or personal
roster data is included in this handoff.
