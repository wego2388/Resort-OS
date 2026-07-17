# 07 — Migration Batch Proposal

**Governing rule:** per `docs/audits/SMART_EXECUTION_ROADMAP.md`'s Gate 7,
migration batches depend on Gate 6 (this Phase 0 evidence) **and** Gates 2
(Super Admin safeguards) and 3 (i18n/design-system foundation). No batch
below should start until those gates close — this document proposes the
*order and shape* of batches, it does not authorize starting one.

Every batch is scoped to be reversible in isolation, non-transactional (no
QR/booking/payment cutover before its dedicated safety gates), and small
enough for one Claude-implements → Codex-reviews → Mohamed-approves cycle.

---

## Batch 1 — Shell and tokens (no content pages yet)

**Correction:** an earlier version of this batch included "fix the stuck
`<html lang>`/`dir` gap" as a deliverable. That gap does not exist — verified
against `packages/core/src/i18n/index.ts`, `switchLocale()` already sets
`document.documentElement.dir`/`lang` and `document.body.dir` on every locale
change, and also on initial load, and `apps/public`'s `LanguageSelector.vue`
already calls `switchLocale()` (`04`, corrected). No fix is needed or
proposed for this. The regression test is kept below purely to guard the
behavior that already works, not to fix anything.

**Scope:** `SiteHeader.vue`/`SiteFooter.vue` visual rework using the shared
`@resort-os/ui` token system (not legacy tokens — `06`), add a real per-page
`useSEO`-style composable shell (empty/default content, no legacy copy yet).
**Corrected:** current `App.vue` already updates `document.title` per
locale, but only for the 4 of 7 routes that declare `meta.titleKey`
(`/`, `/dining`, `/book`, `/confirmation` — `04`, corrected) — `/order`,
`/beach/checkin`, and `/survey` still fall back to the brand name only. This
batch's SEO work is therefore two things, not one: extend `titleKey` to the
remaining 3 routes (small, no title-fix needed elsewhere), and add
meta description/OG/canonical/hreflang/structured data across all 7.

**Why reversible:** touches layout chrome only; no route behavior, no new
backend calls, no content claims.

**Explicit acceptance check:** a regression test confirms `<html dir>`
continues to flip correctly when the locale switches (protecting existing,
working behavior — not fixing anything); type-check/build clean; visual
review in ar RTL and en/ru/it LTR.

## Batch 2 — Static pages (Home rebuild, About, Contact, FAQ, Privacy, Terms)

**Scope:** rebuild Home's hero/stat-strip/intro against current design
tokens using legacy layout as reference (not copied markup); add About/
Contact/FAQ/Privacy/Terms as new static pages. Contact form wired to the
already-current `POST /hub/contact` contract (`05`, already classified
Reuse).

**Why reversible:** still no transactional/guest-order logic; contact form
is the only new write path, and it's already a current, rate-limited
contract.

**Explicit acceptance check:** every legal/marketing claim on these pages is
either sourced from the current backend or explicitly marked pending
Mohamed's content sign-off (`04`'s content-sourcing rule) — no silent legacy
fact treated as true.

## Batch 3 — Dynamic marketing pages (Rooms, Dining marketing page, Beach, Restaurant, Activities, Events, Packages, Gallery)

**Scope:** each page wired to its current backend contract per `05`'s table
(`GET /pms/public/room-types` for Rooms; Dining's existing `/dining/public/*`
read endpoints for the marketing Dining page, distinct from the QR order
flow). One page or tightly related group per implementation/review cycle,
per the handoff's own batching instruction.

**Why reversible:** all reads, no writes beyond what Batch 2 already added.

**Explicit acceptance check:** Keep/Adapt items from `06` are demonstrably
adapted (rebuilt against current contracts/tokens), not copied; asset budget
respected (no bulk 47MB import — indexed/deduplicated/compressed subset per
page, per `03`).

## Batch 4 — Asset pipeline and image budget

**Scope:** formalize an image-optimization step (informed by, not copied
from, legacy's `optimize-images.sh` — `06`) and apply it retroactively to
Batches 2–3's images. Can run in parallel with Batch 3 rather than strictly
after it, since it doesn't change page behavior.

**Explicit acceptance check:** measured page-weight budget per route, not a
subjective "looks fine."

## Batch 5 — SEO layer

**Scope:** real per-page meta/OG/canonical via the Batch-1 `useSEO` shell,
**plus** the `hreflang` support the legacy app itself never had (`04`) —
this is where the current app should end up *better* than the legacy one,
not at parity with it.

**Depends on:** Batches 1–3 existing (pages to attach SEO metadata to).

## Batch 6 — Guest-service menu page (view_and_call only) — **CLOSED, not schedulable, until Gate 8 prerequisites exist**

**Correction (post independent review):** the original version of this batch
assumed `POST /public/alerts` was a safe, working contract to wire a new
screen to, on the strength of a screenshot showing two working-looking
buttons. Verified against the real code (`05`), that assumption was wrong on
two independent counts: the current guest UI's call to this endpoint is
broken today (`context_type` mismatch, HTTP 422), and the endpoint itself has
no context/location validation, no QR token or Guest Session, no
duplicate-request prevention, no cooldown/idempotency beyond a generic IP
rate limit, and no verified branch isolation on the staff-facing read side
either.

**This batch cannot be scheduled as "depends on Gate 1A" alone.** It
requires the full Gate 8 prerequisite set from
`docs/audits/SMART_EXECUTION_ROADMAP.md` — a real Service Location concept,
a secure/rotatable QR token, a Guest Session, and a proper Guest-Request
workflow (assignment, state machine, dedupe) — before any guest-facing screen
is wired to this contract, even in the reduced `view_and_call`-only shape
originally proposed here. Treat this batch as **closed/blocked**, not
"next in line after Gate 1A," until Gate 8's own prerequisites are met.

**Scope, once unblocked:** replace the current `/dining` marketing page's
read-only display with the compliant Digital-Hub-style category browsing
shell from `06` (Adapt), wired to a corrected, Gate-8-hardened version of the
call/bill-request contract — **explicitly excluding** any cart/
`POST /dining/public/orders` UI. This remains the first batch that touches
guest-service UX; it still does not touch the existing (already-shipped,
non-compliant) `/order/:outletId/:tableId` route at all — that route's fix
is Gate 1A/8 work on the existing Dining module, independent of any
site-migration batch.

**Explicit acceptance check:** no code path in this batch can create a
`DiningOrder`; only validated, deduplicated, session-scoped `GuestAlert`s.

## Not a batch — explicitly out of Phase 1 site-migration scope

- Fixing/reworking the existing `/order/:outletId/:tableId` self-order flow
  and its missing rate-limit map entries (`05`) — this is Gate 1A/8 work on
  the *existing* Resort OS Dining module, not a site-migration batch. It
  should happen regardless of whether any site-migration batch ever ships,
  and it should not be bundled into a "make the site pretty" diff.
- Fixing `POST /public/alerts`'s `context_type` mismatch and its missing
  context/token/dedupe/cooldown/branch-isolation validation (`05`) — same
  Gate 1A/8 scope as above, not a small payload patch to slip into a
  migration batch.
- Booking/payment integration (`Needs decision` in `06`) — Gate 1B/4 scope.
- Blog, wishlist/loyalty-for-guests, chatbot — deferred `Needs decision`
  items, not scheduled here.

## Smallest safe first batch, restated

**Batch 1 (shell/tokens)** is the recommended starting point if and when
Gates 2–3 close: it is the smallest, has zero new backend calls (no defect
to fix here — the `lang`/`dir` behavior already works correctly, see the
correction above), and every later batch depends on it existing first.
