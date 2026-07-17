# 06 — Keep / Adapt / Remove Matrix

**Classification legend** (per handoff):
- **Keep** — safe to preserve substantially, with evidence.
- **Adapt** — useful intent/design, must be rebuilt against current
  contracts/tokens/accessibility/security rules.
- **Remove** — duplicate, unsafe, misleading, obsolete, admin-only,
  unsupported, or inconsistent with the accepted product.
- **Needs decision** — a real product fact that cannot be inferred from code.

Every row cites its evidence source (the earlier numbered documents).

---

## Pages / content groups

| Item | Classification | Rationale | Source | Risk | Acceptance check |
|---|---|---|---|---|---|
| Home hero (photography, badge, headline pattern) | **Adapt** | Current Home is a flat gradient with zero imagery (`03`); legacy hero pattern is proven and on-brand (shared gold accent, `03`). Rebuild against current tokens/components, do not copy legacy markup/CSS. | `02`, `03` | Low — visual only | Visual diff approved by Mohamed; Lighthouse/perf budget for hero image |
| Rooms list + detail pages | **Adapt** | No current equivalent exists at all (`01`); legacy layout/photography is a strong starting point; data must come from `GET /pms/public/room-types` (already reused-classified in `05`), not legacy data | `01`, `05` | Medium — new page, real backend wiring | Renders real PMS room types; no legacy price/copy shown unverified |
| Beach / Restaurant / Activities / Events / Packages / Gallery / About / Contact / FAQ marketing pages | **Adapt** | Same pattern as Rooms — content/layout worth reusing, data/copy must be re-sourced or explicitly marked "needs business verification" | `01`, `04` | Low–Medium per page | Per-page content sign-off before batch closes |
| Blog | **Needs decision** | Legacy has a full blog; current backend has `GET /hub/blog/posts` but no current page. Real editorial effort question, not a code question. | `01`, `05` | Low technically, unknown editorially | Mohamed confirms blog is in scope before any batch includes it |
| Digital Hub *content/visual shell* (category tiles, language picker) | **Adapt** | Visual shell (`02` screenshot) is well-built; underlying self-order behavior is not compliant (`01`, `05`) | `01`, `02`, `05` | High if shell is adapted without also removing the cart | Shell renders `view_and_call`-only actions; cart/checkout code path excluded |
| Digital Hub *cart/checkout logic* (`HubCart.vue`, `confirmOrder()`, tip/coupon/loyalty) | **Remove** (from the guest-facing default path) | Directly contradicts the accepted `view_and_call` default (`05`); the current app already made the same mistake independently — do not compound it by porting the legacy version too | `01`, `05` | Critical if ignored | No unauthenticated cart-to-order path ships without a Gate 1A/8 sign-off |
| `ServiceButtons.vue` / "هات الفاتورة"–"نادِ الجرسون" pattern (waiter-call / bill-request) | **Corrected: Adapt, not Keep.** The *intent* is right; the *current implementation* is not | Post-review verification found the current UI's version of this pattern is broken today (`context_type` mismatch → HTTP 422) and the endpoint it calls has no context/token/dedupe/cooldown validation and no verified branch isolation on the staff-side read/list either (`05`, full detail). Not a working, reusable-as-is contract. | `01`, `02`, `05` | High if treated as already-safe | This becomes the default guest action on the migrated menu page **only after** Gate 8's Service Location/token/Guest Session work closes the gaps in `05` — not by patching the payload string alone |
| Booking + payment flow (`Booking.vue`, Paymob integration) | **Needs decision** | Real-looking legacy integration exists; **corrected** — the current `BookingView.vue` does not call `hub/online-bookings` at all, it submits a plain inquiry to `POST /hub/contact` (no payment, no reservation record). `hub/online-bookings`'s own payment wiring was separately not traced end-to-end (`05`) | `01`, `05` | High — money | Explicit design review before any payment code is touched (matches Gate 1B/4 scope, out of Phase 0/1); first clarify whether `hub/online-bookings` is meant to replace the inquiry flow at all |
| `POST /beach/reservations/{id}/checkin` contract | **Corrected: Adapt, not Reuse.** | Second-review finding: `get_cashier_user` checks only role level, never branch; `User` has no `branch_id`; the service uses the reservation's own branch with no cross-check against the acting cashier. Any cashier-or-above account, from any branch, can check in another branch's reservation by ID (`05`). Classified **High risk / broken object-level authorization**. | `05`, `08` | High | Needs a branch-scoped authorization check (and a `User`→branch assignment mechanism to check against) before this contract is trusted anywhere, independent of any site-migration decision — not a Phase 0/1 fix, tracked in `08` |
| Beach check-in page embedding a real staff login form inside the public bundle | **Needs decision** (new finding) | `BeachCheckinView.vue` renders an `auth.login()` email/password form directly in the unauthenticated `apps/public` app when the session isn't staff-authenticated, reaching the full staff auth contract (login/session-fetch/silent-refresh) from inside the guest bundle (`05`) | `05` | Medium — architecture/boundary, not by itself the authorization bug above | Mohamed/architecture decision: should staff check-in stay embedded in the guest app, or move to the staff (`el-kheima`) app with the guest-visible part reduced to read-only reservation confirmation? |
| `/review/:ref`, `/receipt/:ref` | **Adapt** | Useful public post-stay pages; must be moved out of `apps/ops/` naming/location if reused, and re-pointed at current analytics/review contracts (`01`, `05`) | `01` | Low | Component relocated, no ops-only import leaks into the public bundle |
| `/account` role-adaptive page | **Remove** (as a pattern) | Blurs public/staff boundary that Resort OS already keeps clean (`01`); do not reintroduce | `01` | Medium if ignored | No public route renders staff/owner-only tabs |
| Legal pages (Privacy/Terms) | **Adapt** | Reusable structure; legal *text* itself needs Mohamed's review before publishing verbatim | `01`, `04` | Legal/compliance | Explicit legal sign-off, not an engineering approval |
| `/payment/mock` | **Remove** | Dev-only in legacy, excluded from its own prod build already (`01`); no reason to bring into Resort OS at all | `01` | None | Not present anywhere in the new app |
| Chatbot (Gemini-backed concierge) | **Remove** from Phase 1 scope | No current backend capability (`05`); real new-feature decision, not a migration item | `05` | None (by removing) | Not referenced in any Gate 7 batch |
| Wishlist / loyalty-for-guests | **Needs decision** | Staff-side CRM loyalty exists (2026-07-16) but has no public contract (`05`) | `05` | Low | Product decision on whether guests get a loyalty view at all |

---

## Design system / components

| Item | Classification | Rationale | Source |
|---|---|---|---|
| Legacy gold/navy/sand palette | **Keep the gold specifically** | Legacy `#c9a84c` and current `--color-secondary`/gold `#C9963C` are near-identical — both codebases independently converged here; a genuine, low-risk brand constant | `03` |
| Legacy `src/tokens/*.ts` + duplicate Tailwind palette | **Remove** as a literal system | Two overlapping token representations in the legacy repo itself; Resort OS's single CSS-variable, dark-mode-aware `tokens.css` is already more disciplined | `03` |
| Legacy "Coastal Dark" Hub sub-brand (cyan glassmorphism) | **Needs decision** | Distinct visual language from the marketing pages; adopting it means maintaining two brand languages, which Resort OS's current single-token system does not do today | `03` |
| Legacy `Kelements`/`Kprimitives` component families | **Adapt selectively** | Useful atoms (Card/Input/Chip/Icon/Image/Text/Divider) but two overlapping directories need reconciling first; do not copy both | `03` |
| Legacy `ErrorBoundary`-per-surface pattern | **Adapt** | Good, reusable defensive pattern; current apps should confirm they already have an equivalent before adding a new one | `03` |
| Legacy `SEOHead.vue` + `useSchema.ts` composables | **Adapt** | Current app has localized title coverage for 4 of 7 routes, but lacks dynamic per-page meta descriptions, Open Graph, canonical, hreflang, and structured data (`04`); legacy pattern is a good starting shape but must add the `hreflang` support the legacy version itself is missing | `04` |
| Legacy 47MB local asset library | **Adapt selectively, do not bulk-copy** | Real, valuable photography (`03`). Hash-verified: 56 of 230 files (~10.9MB, ~22%) are exact duplicates of other files in the same library — dedupe first (free size reduction), then compress per-page as migrated. The handoff explicitly forbids a blind 47MB copy. | `03` |
| Legacy Unsplash-hosted Hub imagery | **Remove** | **Corrected rationale:** not a licensing claim (ownership/license was not checked, `03`) — the evidenced reason is that a third-party remote image host is a performance/offline-reliability/privacy liability on a resort site that must work over weak beach/venue networks. Replace with real, locally-hosted resort photography from the 47MB library (after the deduplication in `03`) or new images. | `03` |

---

## Infrastructure / non-visual

| Item | Classification | Rationale |
|---|---|---|
| Legacy backend, database, `.env` values, connection strings | **Remove — never migrate** | Explicit hard boundary in the handoff and Decision 0001; current backend is the only source of truth |
| Legacy `Dockerfile`/`nginx-frontend.conf` | **Needs decision** | Could inform the current app's own deployment config later, but that's a Gate 9 (production evidence) concern, not Phase 0/1 |
| Legacy PWA/offline-order queue | **Remove** as legacy code | Any future offline behavior must be built with a clean idempotency/conflict-resolution contract per `AGENTS.md`, not ported from legacy's queue |
| Legacy `optimize-images.sh` approach | **Adapt the approach, not the script** | Confirms an image pipeline was already used successfully; Resort OS should define its own equivalent step as part of the asset-migration batch |
