# Decision 0006 — Beach prices are final with no VAT

**Date:** 2026-08-15
**Status:** Accepted by the owner
**Scope:** El Kheima Beach Resort, single operating branch

## Decision

Beach admission and towel prices are final operational prices. No VAT is
added to a Beach sale. `BeachTransaction.total_amount` is the single source of
truth for the amount shown in the POS, printed on the thermal ticket, charged
to cash/card/wallet/credit/folio, posted to the ledger, attributed to CRM and
included in cashier-shift reconciliation. New Beach transactions retain the
legacy `vat_amount` field for schema compatibility but always store `0.00`.

The general `vat_percentage` setting continues to apply to dining and ETA
flows; it does not affect Beach sales.

## Reason

The previous flow displayed and printed a final Beach price of EGP 200 while
also creating a hidden EGP 28 VAT component. The shift payment was therefore
recorded as EGP 228, producing a false EGP 28 shortage when the cashier counted
the EGP 200 actually collected. The displayed total, receipt total and drawer
ledger must never disagree.

## Data reconciliation

The controlled `backend/scripts/disable_beach_vat.py` tool repairs active
legacy Beach sales atomically across transactions, direct payments, original
journals, folio charges, CRM spend and stored closed-shift totals. Voided sales
remain historically unchanged. The tool is dry-run by default and requires
exact production counts before apply.

The same controlled operation archives `Restaurant HIST` and `Cafe HIST` by
setting them inactive. Their historical orders remain intact for audit and
reporting; every active outlet endpoint and operational screen exposes only
`Restaurant / المطعم` and `Cafe / الكافيه`.
Any zero-value HIST order left active after all of its items were cancelled is
closed as `cancelled` in the same atomic operation. A HIST order with money or
an active item makes the tool fail closed for manual review.

## Acceptance checks

- A Beach ticket priced at EGP 200 produces `total_amount=200.00` and
  `vat_amount=0.00`.
- The thermal ticket contains no VAT row and prints EGP 200 as the total.
- The linked payment and Beach journal are both exactly EGP 200.
- Closing the shift with EGP 200 counted produces zero variance when there are
  no other drawer movements.
- Active outlet APIs return only Restaurant and Cafe in production.
