# Decision 0005: Website Catalog and Online Payment

- **Status:** Draft — awaiting Approval A from Mohamed before any implementation starts.
- **Date:** 2026-08-07
- **Owner:** Mohamed
- **Product:** El Kheima Beach Resort OS + `elkheima-marketing-website`

## Context

The marketing site currently shows static package and activity content sourced
from i18n files. There is no way for the resort manager to add, edit, or hide
a product on the website without editing source code and rebuilding Docker.
There is also no online payment flow — every booking lands as a contact-form
inquiry that requires manual follow-up.

The hub module already has `hub_offers` (temporary promotional pricing),
`hub_online_bookings` (with PMS auto-create on confirmation), and a
`HubManagementView` in the staff app. The backend `.env.example` already
declares `PAYMOB_API_KEY`, `PAYMOB_CARD_INTEGRATION_ID`, and
`PAYMOB_VODAFONE_INTEGRATION_ID`.

Stripe is not available in Egypt. Paymob is the established Egyptian payment
gateway supporting Visa/Mastercard and Vodafone Cash; it uses a hosted payment
page (no card data touches the resort server) with HMAC-SHA512 webhook
verification.

This decision record covers the accepted direction only. Execution requires
a separate written Approval A from Mohamed per the execution plan
`docs/agent-workflow/HUB-CATALOG-01_WEBSITE_CATALOG_AND_PAYMOB_PLAN_AR.md`.

## What this is deliberately not

- **Not a modification of `hub_offers`.** `hub_offers` is for time-limited
  promotional pricing and already has live tests and UI. The new catalog is a
  separate `hub_catalog_items` table with different semantics: permanent
  products, per-person pricing, four-language content, multiple images. The
  two coexist.
- **Not a new payments subsystem.** Paymob payments follow the existing
  `create_direct_payment` / `Payment` record pattern used by dining/beach POS.
  Finance integration reuses that path — no second payment table.
- **Not an AI or forecast feature.** Every price, booking count, and status is
  a real, recorded value. No generated text, no LLM call.
- **Not a replacement for the existing contact/inquiry flow.** Products without
  a confirmed price remain as inquiry-only. `usePageBooking` continues to work
  unchanged for those pages.
- **Not a public price commitment before Approval B.** `PUBLIC_TRUTH.publish.prices`
  stays `false` until Mohamed explicitly approves the specific prices to show,
  per the existing public-truth gating discipline.

## Accepted decisions

1. **Separate catalog table.** `hub_catalog_items` is a new table. `hub_offers`
   is not modified. The two are independent.

2. **Per-person pricing, server-side total.** `total_amount = price_per_person
   × guests_count` is always computed server-side. A client-supplied total is
   never trusted.

3. **Four languages.** `name_ar / name_ru / name_it` follow the same column
   pattern as `PublicMenuItemRead`. The same four languages as the website.

4. **Paymob, hosted page only.** No card data touches the resort server. The
   checkout endpoint calls the Paymob API and returns a `payment_url`. The
   guest is redirected there. Paymob calls back via webhook.

5. **HMAC-first webhook.** `verify_webhook_hmac()` is the first operation
   inside the webhook handler. Any request that fails verification returns 400
   immediately; no DB read or write is attempted.

6. **Idempotent webhook.** A `paymob_order_id` unique constraint ensures a
   duplicate webhook does not create a duplicate Finance `Payment` record.

7. **Fail-closed payment config.** If any Paymob config variable is empty,
   the checkout endpoint returns 503 `payment_not_configured`. No crash, no
   silent failure.

8. **Pure-Python gateway.** `app/resort_os/paymob_gateway.py` contains no
   FastAPI or SQLAlchemy imports, consistent with `food_cost_engine.py` and
   `discount_engine.py`. It is independently testable without a running
   database.

9. **Static fallback.** If the public catalog API returns an empty list (no
   published items), the Activities and Packages pages fall back silently to the
   existing static i18n content. No error is shown to the visitor.

10. **No price display without Approval B.** `PUBLIC_TRUTH.publish.prices`
    controls whether the catalog price is displayed. It stays `false` until
    Mohamed provides a written Approval B naming the specific categories and
    confirmed prices.

11. **Branch derived from slug, never from client.** The checkout endpoint
    derives `branch_id` from the catalog item looked up by slug. A
    client-supplied `branch_id` is rejected.

12. **Encrypted guest PII.** `guest_name` and `guest_phone` on
    `hub_online_bookings` are already stored as `EncryptedString`. The new
    `catalog_item_id`, `paymob_order_id`, `paymob_txn_id`, and
    `payment_method` columns added to the same table are operational metadata,
    not PII, and are stored plaintext.

13. **Finance posting on webhook only.** A `Payment` record is created in the
    Finance module only after a successful, HMAC-verified webhook from Paymob.
    No Finance record is created at checkout time or by any staff action.

14. **Status lifecycle.** `HubOnlineBooking.status` gains two values:
    `payment_pending` (checkout initiated, payment not yet confirmed) and
    `payment_failed` (Paymob reported failure). Existing values (`pending`,
    `confirmed`, `cancelled`, `no_show`) are unchanged. The `status` column is
    VARCHAR, so no `ALTER TYPE` migration is required.

## Non-negotiable invariants

1. `price_per_person × guests_count` must equal `total_amount` at every stage;
   this equality is asserted in tests and enforced in the service layer, not
   just the schema.
2. The webhook HMAC check is structural — placed in the auth/request-handling
   chain, not as an afterthought inside the service function.
3. `hub_offers`, its existing tests, and the `HubManagementView` offers/pages/
   bookings/blog tabs are not modified by this work.
4. No AI, no LLM call, no outbound call to any third-party service other than
   Paymob's documented REST API.
5. Every financial amount uses `Decimal`/`Numeric(10,2)`, never `float`.

## Open questions before Phase 1 can start

These require Mohamed's explicit answer, not an assumed default:

- Are Vodafone Cash payments required at launch, or Visa/Mastercard only?
- Should a booking-confirmation SMS/WhatsApp message be sent to the guest
  after a successful Paymob payment? If yes, via which channel (the existing
  WhatsApp task, a new one)?
- What should happen if Paymob returns a `payment_failed` webhook — show an
  error page and allow retry, or redirect back to the product page?
- Is there a refund/cancellation policy to encode (e.g. "no refunds within
  48 hours of activity date")? If yes, this must be stored on the catalog item
  and shown to the guest before payment.

## Current status

Direction accepted 2026-08-07. Execution plan written. No code has been
written. Awaiting Approval A from Mohamed to begin Phase 1.
