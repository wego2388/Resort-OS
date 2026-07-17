# 01 — Route and State Inventory

**Scope:** every public route in the legacy app and every route in the current
`frontend/apps/public`. Staff/admin/ops/ERP routes are listed only where a
public page depends on them.

**Evidence basis:** legacy inventory produced by a read-only research pass
over `/home/wego/projects/elkheima-beach-resort/frontend/src/router/`
(5 route modules, confirmed by direct file reads); current inventory read
directly from `frontend/apps/public/src/router/index.ts` (28 lines, single
file). Live-render status confirmed for the three pilot routes via Playwright
(see `02_VISUAL_REFERENCE_INDEX.md`); all other rows are static-code
classification, not rendered.

---

## A. Legacy public routes (`elkheima-beach-resort/frontend`)

Router: `src/router/index.ts` composes `routes/{public,auth,ops,admin,dima}.routes.ts`.
Locale mechanism: **URL path-prefix** `:locale(ar|en|ru|it)?`, applied only to
`public.routes.ts` via a `withLocalePrefix()` wrapper. A global `beforeEach`
redirects to the saved/default locale if the prefix is missing or invalid.
`vue-i18n` loads all 4 locale catalogs eagerly (no lazy chunking).

### A1. Public/customer routes (`public.routes.ts`) — locale-prefixed

| Route | Component | Class | Params/query | Evidence status |
|---|---|---|---|---|
| `/` | `Home.vue` | static | — | rendered (ar/en/ru/it, desktop+mobile) |
| `/rooms` | `Rooms.vue` | static | — | rendered (ar/en, desktop+mobile) |
| `/rooms/:id` | `RoomDetails.vue` | dynamic | `id` | static-only (not rendered) |
| `/beach` | `Beach.vue` | static | — | static-only |
| `/beach/:id` | `ServiceDetails.vue` (shared) | dynamic | `id` | static-only |
| `/restaurant` | `Restaurant.vue` | static | — | static-only |
| `/activities` | `Activities.vue` | static | — | static-only |
| `/activities/:id` | `ServiceDetails.vue` (shared) | dynamic | `id` | static-only |
| `/events` | `Events.vue` | static | — | static-only |
| `/events/:id` | `ServiceDetails.vue` (shared) | dynamic | `id` | static-only |
| `/packages` | `Packages.vue` | static | — | static-only |
| `/packages/:id` | `ServiceDetails.vue` (shared) | dynamic | `id` | static-only |
| `/gallery` | `Gallery.vue` | static | — | static-only |
| `/about` | `About.vue` | static | — | static-only |
| `/contact` | `Contact.vue` | static | — | static-only |
| `/faq` | `FAQ.vue` | static | — | static-only |
| `/blog` | `Blog.vue` | static | — | static-only |
| `/blog/:slug` | `BlogPost.vue` | dynamic | `slug` | static-only |
| `/products` | `Products.vue` | static | — | static-only |
| `/product/:id` | `ProductDetail.vue` | dynamic | `id` | static-only |
| `/booking` | `Booking.vue` | transactional | query (room/dates) | static-only — **do not migrate payment logic in Phase 0/1** |
| `/booking/success` | `BookingSuccess.vue` | transactional | — | static-only |
| `/track-booking` | `TrackBooking.vue` | transactional (lookup) | — | static-only |
| `/review/:ref` | `apps/ops/ReviewPage.vue` | dynamic | `ref` | static-only — **component physically lives under `apps/ops/` despite being a public, no-auth route; naming/location mismatch to fix if adapted** |
| `/receipt/:ref` | `apps/ops/ReceiptPage.vue` | dynamic | `ref` | static-only — same location mismatch |
| `/payment/success` | `PaymentSuccess.vue` | transactional | query | static-only |
| `/payment/failure` | `PaymentFailure.vue` | transactional | query | static-only |
| `/payment/mock` | `PaymentMock.vue` | dev-only | — | excluded from prod build (`import.meta.env.DEV` gate) — **do not migrate** |
| `/hub` | `DigitalHub.vue` | guest-service | — | rendered (ar/en, desktop+mobile) — **see Digital Hub note below** |
| `/menu` | redirect → `/hub` | redirect | preserves params/query | not exercised |
| `/privacy` | `Privacy.vue` | legal | — | static-only |
| `/terms` | `Terms.vue` | legal | — | static-only |
| `/:pathMatch(.*)*` | `apps/auth/NotFound.vue` | 404 | — | not locale-prefixed; static-only |

### A2. Auth routes (`auth.routes.ts`) — no locale prefix, out of migration scope except one flag

`/login`, `/admin/login`, `/staff/login`, `/unauthorized`, `/register`,
`/verify-email`, `/forgot-password`, `/reset-password` — staff/account auth,
out of scope for the public marketing/content migration.

**`/account`** (`Account.vue`, `requiresAuth: true`) is flagged separately:
it is registered as a "public" route but is **role-adaptive** — it renders
`TabHousekeeping.vue` / `TabOwnerHub.vue` for staff/owner roles inside what
is nominally a guest account page. This blurs the public/staff boundary and
must not be copied as-is; Resort OS already separates staff self-service
(`el-kheima` app) from the guest-facing `public` app cleanly, and Phase 1+
should preserve that separation rather than reintroduce this pattern.

### A3. Ops / Admin / Dima routes — **out of scope**, listed for completeness only

- `ops.routes.ts`: 9 staff routes (Staff Radar, Cashier POS, Housekeeping
  board, Prep/KDS, Gate Cashier, Tenant, Spa) — all `requiresAuth`, role-gated.
- `admin.routes.ts`: `/settings` + a ~30-tab `/dashboard` ERP tree (calendar,
  discounts, reviews, reports, `erp/*`, channel-manager, HR, coupons,
  bookings, customers, revenue, blog, broadcast, chatbot, etc.).
- `dima.routes.ts`: `/dima/*`, `/finance/*`, `/gm/*`, `/supervisor` —
  super-admin/finance/GM shells.

No public page was found to depend on these at render time other than the
`/account` role-adaptive tabs noted above.

### Digital Hub — state/behavior trace (`DigitalHub.vue`, 1317 lines)

This is **not** a passive menu viewer. Confirmed by direct code reading:

1. `addToCart(product)` pushes into a Pinia `cartStore`.
2. `HubCart.vue` provides a full cart UI: quantity edit, tip
   (`tipPercent`/`tipCustom`), coupon discount, loyalty-point redemption
   (`POST /loyalty/redeem`), guest phone/notes.
3. `confirmOrder()` **submits directly to the backend**: `POST /orders/location`
   with items/total/tip/discount/points — with an offline-queue fallback that
   syncs the same payload later.
4. After submit, a guest WebSocket (`useHubWS`) streams live status; a
   `BillModal.vue` explicitly tells the guest to pay at the gate cashier in
   person (no online payment capture for Hub orders specifically).
5. Separately, `ServiceButtons.vue` implements a lightweight, cart-free
   pattern: `POST /staff-alerts` with `waiter_call` / `bill_request` /
   `housekeeping_call` / `front_desk_call`.

**Conclusion:** the legacy Hub's *default* behavior is full self-ordering
(cart → real order → kitchen fulfillment → pay in person), which does not
match the accepted `view_and_call` default. Only `ServiceButtons.vue`'s
call/request pattern matches the accepted default. See
`05_API_AND_DATA_CONTRACT_MAP.md` for the compliance check required by the
handoff, and `06_KEEP_ADAPT_REMOVE_MATRIX.md` for the classification.

---

## B. Current routes (`frontend/apps/public/src/router/index.ts`, 28 lines total)

No locale-prefixed URLs. Locale is a client-side `vue-i18n` value persisted to
`localStorage['locale']` (shared mechanism in `packages/core/src/i18n/index.ts`,
also writes legacy-compatible keys `kheima_lang`/`app_language`). This means
**there are no distinct per-locale URLs today** — a structural gap versus the
legacy's path-prefixed, hreflang-capable routing (see `04_CONTENT_I18N_SEO_MAP.md`).

| Route | Component | Class | Params | Evidence status |
|---|---|---|---|---|
| `/` | `HomeView.vue` (214 lines) | static + dynamic room list from PMS | — | rendered (ar/en, desktop+mobile) |
| `/dining` | `DiningView.vue` (194 lines) | dynamic (live menu, view-only) | — | rendered (ar, desktop+mobile) |
| `/book` | `BookingView.vue` (144 lines) | transactional | — | static-only (not rendered in this pass) |
| `/confirmation` | `ConfirmationView.vue` (20 lines) | transactional | — | static-only |
| `/order/:outletId(\d+)/:tableId(\d+)` | `OrderView.vue` (750 lines) | **guest-service, but implements full self-ordering** | numeric `outletId`, `tableId` (untrusted, trusted from URL — see risk below) | rendered (ar, desktop+mobile, real seeded outlet 2/table 1) |
| `/beach/checkin/:reservationId` | `BeachCheckinView.vue` (159 lines) | transactional (check-in) | `reservationId` | static-only |
| `/survey/:token` | `SurveyView.vue` (251 lines) | dynamic (token-based) | `token` (opaque token — correct pattern) | static-only |
| `/:pathMatch(.*)*` | redirect → `/` | catch-all | — | not exercised |

### OrderView.vue — state/behavior trace (confirmed by direct code reading)

`OrderView.vue` (the current app's QR-scan landing page) implements the
**same class of self-ordering as the legacy Digital Hub**, independently
re-confirmed here with line-level evidence:

- `const cart = ref<CartItem[]>([])` (line 79) — a real cart, with
  `addToCartDirect()`, quantity adjustment, extras/variant selection, notes.
- `placeOrder()` posts to `POST /api/v1/dining/public/orders` (no auth
  header, no CSRF/session token) — this is the same endpoint traced in
  `05_API_AND_DATA_CONTRACT_MAP.md` that creates a real `DiningOrder` row
  indistinguishable from a staff-entered order.
- The rendered screenshot (`current_order-qr_ar_desktop.png`) shows both the
  cart "+"-per-item affordance **and** two bottom action buttons visually
  matching the accepted pattern: "هات الفاتورة" (bring the bill) and "نادِ
  الجرسون" (call the waiter). **Correction (post-review, verified against the
  actual request payload): these two buttons are currently broken, not a
  working reusable pattern.** `sendGuestAlert()` (`OrderView.vue:340`) posts
  `context_type: 'dining_table'`, but `GuestAlertCreate` on the backend
  (`backend/app/modules/core/schemas.py:238`) only accepts
  `^(restaurant_table|cafe_table|beach_location|room|other)$` — `dining_table`
  is not in that set, so every call/bill-request tap from this screen returns
  HTTP 422 today. This was wrongly reported as working in the first version
  of this document on visual/screenshot evidence alone, without exercising
  the actual network call. See `05_API_AND_DATA_CONTRACT_MAP.md` for the
  full trace and `06_KEEP_ADAPT_REMOVE_MATRIX.md`/`07_MIGRATION_BATCH_PROPOSAL.md`
  for the corrected classification.

**This means the self-ordering gap is not legacy-only.** The current,
already-shipped `apps/public` also defaults to guest-initiated real orders
today, via the same trust-boundary pattern flagged as C-02 in
`docs/audits/PRODUCTION_READINESS_AUDIT.md`. Any Phase 1+ work on this route
must close this gap; it is not something Phase 0 evidence alone resolves.

---

## Coverage gaps between legacy and current (explicit, not inferred)

The current `apps/public` has **7 views** against the legacy's **~32 public
routes**. Pages with no current equivalent at all: Rooms *list* (current only
has a rooms teaser on Home, no dedicated `/rooms` page or `/rooms/:id`
detail), Beach (marketing page), Restaurant (marketing page — distinct from
the live `/dining` menu), Activities, Events, Packages, Gallery, About,
Contact, FAQ, Blog, Products, and the legal pages (Privacy/Terms). This
confirms the scale of reusable legacy design/content referenced in `wagdy.md`.

## Notes on evidence method

- "Rendered" = captured live via Playwright against a running local dev
  server in this pass (see `02_VISUAL_REFERENCE_INDEX.md` for exact files).
- "Static-only" = classified from router/component source reading only; not
  rendered in this pass. Exhaustive rendering of all ~40 combined routes
  across 4 locales × 2 viewports was out of budget for Phase 0 pilot; the
  pilot intentionally covered the three routes named in the handoff (Home,
  Rooms, Digital Hub) plus their current-app equivalents. A full-coverage
  capture pass is recommended as an explicit Phase 0 follow-up task, not
  assumed complete here.
