# Decision 0001: QR Guest Service Mode

- **Status:** Accepted product direction; implementation not yet complete
- **Date:** 2026-07-17
- **Owner:** Mohamed
- **Product:** El Kheima Beach Resort OS

## Context

The repository already contains a partial public QR menu, guest-alert flow,
table model, staff alert UI, WebSocket delivery, and POS integration. The
feature must be completed by evolving those parts, not by building a second QR
or table-service system beside them.

No QR code produced by the current development implementation has been printed
or placed into live resort use. The feature is still in testing and
development. Therefore compatibility for an already deployed physical QR fleet
is not a current constraint, although existing database data must still be
handled deliberately and safely.

## Accepted decisions

1. The exact public brand is **El Kheima**.
2. The default guest mode is **`view_and_call`**:
   - view the correct outlet menu;
   - call a waiter;
   - say "ready to order";
   - request assistance or the bill;
   - see the safe status of that request.
3. Unrestricted guest self-ordering is disabled by default. Existing
   self-order code may only remain behind an explicit outlet/resort setting and
   must not send items to preparation or financial posting without the
   controlled workflow approved for that mode.
4. A guest does not need an account merely to view a menu or request service.
5. Public URLs use a stable, random, non-sequential, rotatable token. They do
   not expose internal table, outlet, beach-location, order, or request IDs.
6. After token validation, the backend derives the trusted resort/branch,
   outlet, and service-location context. It does not trust those IDs from the
   public client.
7. QR images are generated locally using repository capabilities. A third-party
   QR image service must not receive guest URLs or tokens.

## Domain direction to validate during discovery

The preferred direction is a generic **Service Location** concept covering a
restaurant/cafe table, umbrella, pergola, cabana, beach seat, VIP area, room
service location, or configured custom type.

This direction must be implemented by safe evolution of existing data:

- evolve/reuse `VenueTable` semantics and preserve existing keys/relationships
  where practical;
- keep `BeachLocation` for its beach-access, occupancy, and transaction
  responsibilities, linking it to the service location rather than merging the
  two domains destructively;
- evolve/reuse `GuestAlert` data as the basis of a structured dining guest
  service request when the audit confirms that this is safer than a parallel
  table;
- keep `DiningOrder.table_id` compatibility initially if renaming it would
  cause an unnecessary broad migration, while exposing clearer service-layer
  language.

These are architecture directions, not permission to skip repository discovery
or migration analysis.

## Phase 1 product boundary

The first implementation slice should establish:

- secure service-location token and correct public menu context;
- active/disabled/rotated-token behavior;
- `view_and_call` as the default;
- call waiter, ready to order, assistance, and request bill;
- unresolved-request deduplication, retry idempotency, cooldown/rate limits,
  and safe status recovery;
- staff queue visibility without broadcasting every request to every employee;
- Arabic RTL and English LTR basics;
- regression and public-security tests.

It must reuse the existing Dining/POS architecture and must not silently enable
direct guest ordering.

## Later phases (not part of Phase 1 by default)

- full waiter accept/arrive/resolve and assignment/escalation workflow;
- one-active-order enforcement and request-to-order linkage;
- cashier monitoring and automatic bill-request resolution after payment;
- multi-worker real-time transport if the current deployment requires it;
- advanced dispatch, push notifications, printer integration, analytics,
  multiple active orders per location, room-service expansion, and full
  offline/PWA behavior.

Each later phase needs its own task brief and quality gate.

## Known current gaps to verify before implementation

The preliminary read-only review found issues that must be revalidated against
the exact task base commit:

- the public frontend's `dining_table` alert context does not match the backend
  validation values;
- public QR/order URLs expose sequential IDs and some public endpoints trust
  client-selected IDs;
- public order-status lookup may allow enumeration;
- rate-limit rules still reference legacy paths;
- duplicate active orders/guest requests are not protected strongly enough;
- current QR generation uses stale host/port assumptions and an external QR
  image/CDN path;
- guest alerts do not yet model the required assignment, state machine,
  timestamps, order link, expiry, idempotency, and deduplication;
- current real-time delivery is broad and in-memory;
- the public order page has incomplete RTL/LTR behavior;
- a duplicate dining CRUD function definition may be shadowing an earlier one.

These are audit findings, not yet recorded as fixed.

## Consequences

- Legacy development QR URLs may be intentionally replaced because there is no
  printed/live QR fleet. Any existing data migration still requires tests and
  rollback reasoning.
- Public security and request reliability are completed before richer guest
  ordering or dispatch features.
- The workflow remains waiter-led and financially controlled by the staff POS.
- Completion may only be claimed after the tested QR-to-request-to-staff flow
  works; later order/payment completion claims require their own end-to-end
  evidence.
