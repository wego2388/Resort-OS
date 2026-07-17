# 05 — API and Data-Contract Comparison

**Rule enforced throughout this section:** the current Resort OS backend
(`backend/app/modules/*`) is the only future source of truth. Legacy
endpoints are evidence of what a guest journey needs to do, never a target
to reimplement or copy data from.

**Explicit `view_and_call` compliance check** (required by handoff §0F) is
in its own subsection below, covering both the legacy Digital Hub and the
current `/order/:outletId/:tableId` route side by side, since both were
found to have the same category of gap.

> **Correction notice (second pass, post independent review, verified
> against the actual code — not just re-asserted):** the previous version of
> this document mischaracterized two contracts as "already correct/reusable"
> without exercising the real request payload or reading the full call
> chain; those were fixed in the first correction pass. This second pass
> fixes a miscount in that same correction (11 call sites / 8 distinct
> contracts was itself imprecise — the table below already had 12 rows; it
> was a counting error, not a missing-evidence one), and adds a
> previously-omitted class of *indirect* calls that `BeachCheckinView.vue`
> triggers through the shared auth store.

---

## Every real API call made from `frontend/apps/public` (exhaustive, re-verified twice)

### Direct calls (issued by an `apps/public` view file itself)

Found via `grep -rn "axios\.\|api\." --include="*.vue" --include="*.ts" src/`
across the whole app — **12 call sites, 10 distinct backend method/path
contracts** (two contracts are each called from two different places: room
types from Home+Booking, the dining menu from DiningView+OrderView):

| File | Call | Backend path |
|---|---|---|
| `HomeView.vue:61` | `axios.get` | `GET /api/v1/pms/public/room-types` |
| `BookingView.vue:36` | `axios.get` | `GET /api/v1/pms/public/room-types` |
| `BookingView.vue:54` | `axios.post` | `POST /api/v1/hub/contact` — **not** `/hub/online-bookings` (correction, see Room booking row below) |
| `DiningView.vue:99` | `axios.get` | `GET /api/v1/dining/public/outlets` |
| `DiningView.vue:104` | `axios.get` | `GET /api/v1/dining/public/menu` |
| `OrderView.vue:170` | `axios.get` | `GET /api/v1/dining/public/menu` (via `${apiBase}/menu`) |
| `OrderView.vue:289` | `axios.post` | `POST /api/v1/dining/public/orders` (via `${apiBase}/orders`) |
| `OrderView.vue:314` | `axios.get` | `GET /api/v1/dining/public/orders/{id}` (via `${apiBase}/orders/${orderId}`) |
| `OrderView.vue:340` | `axios.post` | `POST /api/v1/public/alerts` — **currently returns 422**, see below |
| `SurveyView.vue:128` | `axios.post` | `POST /api/v1/analytics/reviews/submit` — this is the **only** call `SurveyView.vue` makes; see the corrected Survey row below for what it does *not* call |
| `BeachCheckinView.vue:47` | `api.get` | `GET /api/v1/beach/reservations/{id}/public` |
| `BeachCheckinView.vue:72` | `api.post` | `POST /api/v1/beach/reservations/{id}/checkin` |

### Indirect calls (issued by shared `@resort-os/core` infrastructure, triggered from `apps/public`)

**New in this pass** — the direct-call grep above only searches `apps/public`'s
own view/component files; it does not surface calls made by shared store/
client code that a public view merely *invokes*. `BeachCheckinView.vue:60`
calls `auth.login(email.value, password.value)` (the shared Pinia auth
store), which itself makes real network calls not visible in the direct-call
grep:

| Trigger | Shared code | Backend path |
|---|---|---|
| `BeachCheckinView.vue:60` → `auth.login()` | `packages/core/src/stores/auth.ts`'s `login()` | `POST /api/v1/auth/login` |
| same `login()` call, immediately after | same file's `fetchUser()` | `GET /api/v1/auth/me` |
| any subsequent authenticated request that receives a 401 | `packages/core/src/api/client.ts`'s response interceptor | `POST /api/v1/auth/refresh` (conditional — only fires on a 401, then retries the original request once) |

This means the unauthenticated `apps/public` bundle can, once a staff member
authenticates on the embedded `BeachCheckinView.vue` login form (see `05`'s
architecture-concern note below), reach the **full staff auth contract**
(login, session fetch, silent refresh) — not just the beach-checkin
endpoints. This context matters directly for the authorization finding
below.

**Scope statement, corrected:** "no other network call exists in
`apps/public` today" (as stated in the previous version of this document)
was accurate only for *direct* calls issued by `apps/public`'s own view
files. It did not account for calls made by shared core code that a public
view triggers indirectly. With that class included, the complete picture is:
12 direct call sites (10 distinct direct contracts) + 3 indirect contracts
reachable through the embedded staff-login flow. No chatbot, wishlist,
loyalty, or blog call exists in either category — those rows in the
contract table below remain legacy-only comparisons with no current-app
equivalent.

---

## Contract-by-contract table

| Guest action | Legacy call | Current call | Owner module | Gap / risk | Decision |
|---|---|---|---|---|---|
| View room types | (legacy `Rooms.vue`, calls its own `/products?type=room...`) | `GET /pms/public/room-types?branch_id=` — confirmed in `backend/app/modules/pms/api/router.py:111`, explicitly unauthenticated, read-only. **Corrected:** `branch_id` is **client-supplied**, not derived server-side — `apps/public` sends a hardcoded frontend constant (`PUBLIC_BRANCH_ID = 1`, `constants/resort.ts:27`), but nothing stops any caller from sending a different value; the backend does not validate it against a configured/trusted resort context. | PMS | Read-only and low-sensitivity today (this is the correct part of the original assessment) — but "no client-supplied ID trusted" was not accurate; branch selection itself is client-supplied and would need real validation the moment a second branch exists | **Reuse current contract for the read**, but note the branch-selection gap so it isn't carried unexamined into a future multi-branch setup |
| View live dining menu | Legacy: `HubCart`/menu category composition inside `DigitalHub.vue`, backend unknown (legacy backend not inspected beyond routes) | `GET /dining/public/outlets?branch_id=`, `GET /dining/public/menu?outlet_id=&table_id=` — confirmed in `backend/app/modules/dining/api/router.py:894-935`, unauthenticated | Dining | **Corrected:** the previous version of this row said `outlet_id` "is meant to be embedded in a QR code" — that is not something this pass verified and overstates the current design's safety. What is accurate: a numeric `outlet_id` is low-sensitivity *today*, for selecting which public menu catalog to display (read-only, no PII/money). It is **not** evidence that sequential numeric IDs are an acceptable long-term identity/location mechanism — Decision 0001's Service Location design explicitly calls for a secure, opaque token, not a sequential `outlet_id`/`table_id` pair, and the current `/order/:outletId/:tableId` route (which reuses this same menu endpoint) is exactly the case where that distinction matters (see the compliance subsection below). | **Reuse the read-only menu-listing contract as-is for now**; do not extend the current `outlet_id`/`table_id` URL pattern into the future secure Service Location design |
| **Submit a self-order** | `POST /orders/location` (legacy backend, not the current one) — full cart, tip, coupon, loyalty | `POST /dining/public/orders` — confirmed in `backend/app/modules/dining/api/router.py:940-965`, **no auth, no rate limit registered (see below), creates a real `DiningOrder` via the same `services.create_order()` staff orders use** | Dining | **Critical — violates the accepted `view_and_call` default in both codebases.** See dedicated subsection below. | **Adapt: keep the endpoint (staff still needs orders created from a QR-originated ticket eventually), but the UI must not expose an unrestricted cart by default; the endpoint itself needs a trusted-context/token/rate-limit rework before any Gate 7/8 reliance** |
| Poll order status | Legacy: WebSocket (`useHubWS`) | `GET /dining/public/orders/{order_id}` — confirmed in `router.py:977-998`, **sequential integer `order_id`, no session/token check, 10s polling per `OrderView.vue`'s own code comment** | Dining | Order status/total is enumerable by guessing sequential IDs (matches `docs/audits/PRODUCTION_READINESS_AUDIT.md` C-02 exactly, independently re-confirmed here) | **Adapt** — needs to be scoped to a guest session/token, not a bare integer path param |
| **Call waiter / request bill** | Legacy: `POST /staff-alerts` (not independently re-verified against the legacy backend in this pass — legacy backend was not running) | `POST /public/alerts` — confirmed in `backend/app/modules/core/api/router.py:511-533` | Core (`GuestAlert`) | **Corrected finding, verified against actual code (see full subsection below): this call is currently broken (HTTP 422) and the endpoint itself has multiple unresolved security gaps even when the payload is fixed.** Not a safe, ready-to-reuse contract. | **Adapt, do not reuse as-is.** Fix the immediate `context_type` mismatch is not a Phase 0/1 task either — it requires the same Service-Location/token/Guest-Session design work as the rest of Gate 8, not a one-line payload patch that ships without the missing validation. |
| Room booking | `POST /bookings/smart/room` + `POST /payments/create` (Paymob, real-looking integration; `pay_on_arrival` alternative) | **Corrected:** `BookingView.vue` does **not** call `POST /hub/online-bookings`. It calls `GET /pms/public/room-types` to populate the room picker, then submits the whole booking as a **contact-form inquiry** via `POST /hub/contact` (`BookingView.vue:54`, confirmed by direct source reading) — there is no payment step, no confirmation record, no booking row created. `POST /hub/online-bookings` (`hub/api/router.py:146`) exists in the backend but is **not called by any current frontend code** found in this pass. | Hub/PMS | Current guest-facing "booking" is really a lead/inquiry, not a reservation; `hub/online-bookings`'s own payment wiring was not traced in this pass either | **Needs decision**: is `hub/online-bookings` meant to replace the inquiry flow, and does it have real payment integration? Needs a dedicated read of `hub.services` before any Batch touches booking. |
| Track/lookup a booking | `GET` via `TrackBooking.vue` (endpoint not traced) | Not present in the current app (`BookingView.vue`/`ConfirmationView.vue` exist; no track-booking view) | — | Current gap — no current route/page for this journey | **Needs decision** — likely low priority versus Gate 4/7 work |
| **Beach reservation check-in (view)** | Legacy: no direct equivalent traced | `GET /beach/reservations/{reservation_id}/public` (`backend/app/modules/beach/api/router.py:382`) — **sequential integer `reservation_id`, no token** | Beach | **Corrected — this is not a "coarse status" leak.** `BeachReservationPublic` (`backend/app/modules/beach/schemas.py:164-173`) returns `guest_name`, `guests_count`, `with_towel`, `reservation_date`, `status`, and `total_amount` — a real guest's name, party size, and the reservation's money amount, all readable by guessing sequential integers with zero authentication. This is a real PII/financial-exposure finding, not previously listed in `PRODUCTION_READINESS_AUDIT.md`'s C-02 examples. | **New finding for this audit — Adapt, and treat as higher severity than originally reported.** Needs a token/QR-derived context before any public rollout, same as the dining order-status endpoint. |
| **Beach reservation check-in (confirm)** | — | `POST /beach/reservations/{id}/checkin` (`beach/api/router.py:390`), gated behind `Depends(get_cashier_user)` | Beach | **Corrected — this is a real, High-severity broken object-level authorization (BOLA/IDOR), not "properly protected."** `get_cashier_user` (`app/core/deps.py:193-196`) checks only the caller's role *level* (`>= 40`), never a branch. The `User` model itself has no `branch_id` column at all (confirmed: `grep branch_id` on `app/core/kernel/models/user.py` returns nothing — a pre-existing platform limitation, not new). `check_in_reservation` (`beach/services.py:842-866`) fetches the reservation by a bare sequential `reservation_id` with no branch filter, then performs the check-in using **the reservation's own `branch_id`**, never checking it against anything belonging to the authenticated cashier. **Net effect: any authenticated cashier-level-or-above account, from any branch, can check in a reservation belonging to a different branch, simply by knowing or guessing its sequential ID.** This was incorrectly described as "properly protected" in the previous version of this document — that assessment checked *authentication* (a real login is required) but not *authorization scope* (which branch the login is allowed to act on), which is the actual gap. | **Adapt before reuse — do not carry this into any Gate 7/8 work as-is.** Needs a branch-scoped authorization check (e.g. compare the reservation's `branch_id` against the cashier's assigned branch — which first requires giving `User` a `branch_id` or an equivalent branch-assignment mechanism) before this endpoint can be trusted, independent of any site-migration decision. Logged in `08_OPEN_QUESTIONS_AND_RISKS.md`. |
| Post-stay review/survey | Legacy: `POST /reviews`, `POST /complaints` | **Corrected — the public page makes exactly one call:** `SurveyView.vue` only issues `POST /analytics/reviews/submit?token=...` (`analytics/api/router.py:616-632`), which internally calls `verify_survey_token`/`submit_review` as part of handling that single request. The two `GET /analytics/reviews/survey-token/{booking_id}` and `GET /analytics/reviews/survey-token/timeshare/{visit_id}` endpoints (`router.py:637-661`) are a **separate, staff-authenticated contract** (`Depends(get_current_active_user)`) used to *issue* the token in the first place (e.g. from a checkout screen or the WhatsApp survey-send flow) — `SurveyView.vue` never calls them; a guest only ever receives an already-issued token via a link. | Analytics | **Correct pattern for the public half** — opaque JWT token in the URL, not a sequential ID, and the guest-facing endpoint itself requires no separate authentication beyond the token | **Reuse the public submit contract as the reference pattern for how the order-status and beach-checkin endpoints above should be fixed**; the staff-issuance endpoints are out of scope for any public-app work |
| Blog/content | `GET /blog/posts` | `GET /hub/blog/posts` (`hub/api/router.py:228`) — not called by any current `apps/public` page today | Hub | Current app has no blog view yet (`apps/public` has no `/blog` route) | **Adapt when Gate 7 content batches reach blog** |
| Contact form | `POST /leads/` | `POST /hub/contact` (`hub/api/router.py:184`, rate-limited `30/60s`) — already in live use today, by `BookingView.vue` (see correction above), not by a dedicated contact page | Hub | Current app has no standalone contact page yet | **Reuse current contract when a dedicated contact page is built** |
| Concierge chatbot | `POST /chat/*` (Gemini-backed per legacy env vars) | No equivalent found in current backend modules | — | Not a Resort OS capability today | **Remove from Phase 1 scope** — flagged as a possible future feature only, not a migration item |
| Wishlist / loyalty widget | `GET/POST /users/me/wishlist`, `POST /loyalty/redeem` | CRM loyalty exists in the staff app (`crm.loyalty.*`, built 2026-07-16 per `PROJECT_STATUS.md`) but has no public-facing contract yet | CRM | Current gap | **Needs decision** — loyalty-for-guests is a real product idea but out of Phase 0/1 scope |

---

## `view_and_call` compliance check (required by handoff)

**Decision 0001 requirement:** the default guest mode is `view_and_call` —
view menu, call waiter, say "ready to order," request assistance/bill.
"Unrestricted guest self-ordering is disabled by default."

**Finding, evidenced at the code level in both codebases:**

1. **Legacy `DigitalHub.vue`** defaults to a full cart → `POST /orders/location`
   self-checkout flow (see `01_ROUTE_AND_STATE_INVENTORY.md`). Not compliant.
2. **Current `OrderView.vue`** (`frontend/apps/public/src/views/OrderView.vue`,
   confirmed by direct source reading: `const cart = ref<CartItem[]>([])` at
   line 79, `addToCartDirect()`, and a `placeOrder()` that calls
   `POST /dining/public/orders`) **also** defaults to a cart-based self-order
   flow today, already shipped in the current codebase. Not compliant.
3. The lightweight, compliant-in-*intent* pattern also exists in both
   codebases — legacy's `ServiceButtons.vue` (`POST /staff-alerts`, not
   re-verified against a live legacy backend in this pass) and the current
   app's "هات الفاتورة" / "نادِ الجرسون" buttons visible in
   `current_order-qr_ar_desktop.png`. **Correction: the current app's version
   of this pattern does not actually work today.**
   `sendGuestAlert()` (`OrderView.vue:340`) sends
   `context_type: 'dining_table'` in the POST body; the backend's
   `GuestAlertCreate` schema (`backend/app/modules/core/schemas.py:238`,
   pattern `^(restaurant_table|cafe_table|beach_location|room|other)$`)
   rejects that value with **HTTP 422** — every tap of either button on this
   screen fails today. This was incorrectly reported as a working,
   ready-to-reuse pattern in the first version of this document, based on
   the screenshot showing the buttons rendered, without actually issuing the
   request and reading the response.
4. **Even setting the `context_type` mismatch aside, `POST /public/alerts`
   is not a safe, complete contract as it stands** (verified by reading
   `core/services.create_guest_alert` and the staff-facing `GET /alerts`
   endpoint in full):
   - `services.create_guest_alert` (`backend/app/modules/core/services.py:518-525`)
     validates only that `branch_id` exists. It **never validates that
     `context_id` refers to a real table/location, or that it actually
     belongs to the given `branch_id`/outlet** — any integer is accepted.
   - There is no QR token or guest session; `branch_id`/`context_type`/
     `context_id` are trusted directly from the unauthenticated client body.
   - There is no unresolved-duplicate check — a guest (or anyone) can submit
     the same call/bill-request repeatedly with no dedupe.
   - There is no per-context cooldown or idempotency key; the only
     protection is the generic IP-keyed rate limit (`("public", 20, 60)` in
     `app/core/rate_limit.py`), which does not stop one guest from spamming
     just under the limit, and does not distinguish guests behind a shared
     resort/venue IP.
   - **New finding, staff side:** `GET /alerts` (`core/api/router.py:540-558`)
     takes `branch_id` as a plain client-supplied query parameter and never
     checks it against the authenticated staff user's own branch — any
     waiter-level-or-above account can read another branch's guest alerts by
     changing the query string. `PATCH /alerts/{id}/status` has the same gap
     (no branch-ownership check before letting a staff member resolve an
     alert). This means "the staff alert queue/WebSocket enforces branch/zone
     isolation" cannot be asserted from this codebase as it stands.

**Corrected conclusion:** the gap is not "legacy has a bad pattern, current
has a good one to build on." **Neither codebase has a working, safe
`view_and_call` implementation today.** The current app's cart/self-order
path is non-compliant with the product decision (as originally found), *and*
its supposedly-compliant fallback (call waiter / request bill) is currently
broken end-to-end, *and* the endpoint backing that fallback has real,
unresolved trust-boundary and authorization gaps on both the guest-submit
and staff-read sides. None of this is fixed here — it is exactly the scope
of Gate 1A (Public/QR containment) and Gate 8 (QR + Guest Service) in
`docs/audits/SMART_EXECUTION_ROADMAP.md`, which already requires a real
Service Location, secure/rotatable token, Guest Session, and a proper
Guest-Request workflow — this finding is evidence for *why* those gate
requirements exist, not a reason to shortcut them with a payload-string fix.
No code change is proposed here.

---

## A related, newly found architecture concern: staff login embedded in the public bundle

`BeachCheckinView.vue` (a route inside the unauthenticated `apps/public`
app) renders a real staff credential form when the viewing session isn't
already authenticated: email/password inputs and a call to
`auth.login(email.value, password.value)` (`BeachCheckinView.vue:57-62`),
gated only by `v-else-if="!auth.isAuthenticated"`. This means the public,
guest-facing bundle ships real staff-login UI and wiring, not just a
guest-only surface. This is a design-boundary concern (a public,
unauthenticated app embedding staff credential entry) worth a decision
before any Gate 7 batch touches this page, not a proposed fix here.

---

## Rate-limiting map cross-check (evidence for C-02, independently reproduced)

`backend/app/core/rate_limit.py`'s `_LIMITED_ROUTES` map was read directly.
It still registers the **retired** legacy paths:

```
("GET",  "/api/v1/cafe/public/menu")
("GET",  "/api/v1/restaurant/public/menu")
("POST", "/api/v1/restaurant/public/orders")
("POST", "/api/v1/cafe/public/orders")
```

These modules were deleted in the D-05→D-08 Dining cutover (2026-07-13, per
`PROJECT_STATUS.md`) — these four map entries are dead weight, not active
protection. The **currently active** paths that replaced them —
`/api/v1/dining/public/menu` and `/api/v1/dining/public/orders` — are **not
present in the map at all**, meaning the real, live, unauthenticated
self-order-creation endpoint has **zero rate limiting today**. This
independently reproduces `docs/audits/PRODUCTION_READINESS_AUDIT.md`'s C-02
finding with the exact current file content, one item more precisely than
the original audit (which cited the general pattern; this pass confirms the
literal dead/missing map entries). No fix is proposed here — this belongs to
Gate 1A, not Phase 0.

---

## PII, money, and idempotency notes (evidence only, no fix proposed)

- `GET /beach/reservations/{id}/public` returns real PII (`guest_name`) and a
  real money amount (`total_amount`), not just status — see the corrected
  table row above. This is the most significant *read-side* PII/financial
  exposure found in this pass.
- `POST /beach/reservations/{id}/checkin` has a real, High-severity
  authorization gap on the *write* side — a cross-branch broken
  object-level-authorization issue, not a PII leak — see the corrected table
  row above and `08_OPEN_QUESTIONS_AND_RISKS.md`.
- `POST /dining/public/orders` creates a real financial-adjacent record
  (a `DiningOrder`, which later flows into shift/payment reporting per the
  2026-07-17 finance-audit work in `PROJECT_STATUS.md`) with **no
  idempotency key** — a retried/duplicated client POST (network retry,
  double-tap) would create two separate orders. Not fixed here; feeds Gate 4
  (Dining financial integrity) and Gate 8 (QR) acceptance criteria.
- `GET /dining/public/orders/{id}` leaks order existence, status, and total
  via a sequential ID (no guest PII directly, based on the `GuestOrderRead`
  fields read in this pass) — full payload contents were not exhaustively
  diffed field-by-field beyond what's cited here.
- `POST /public/alerts` has no idempotency key either — see the compliance
  subsection above for the full list of gaps on this specific contract.
