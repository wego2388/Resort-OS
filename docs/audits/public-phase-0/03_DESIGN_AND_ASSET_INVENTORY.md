# 03 — Visual System and Asset Inventory

**Evidence basis:** read-only research pass over both repositories'
`tailwind.config`/token files, component directories, and `public/`/`src/assets`
folders (`find`/`du`/`grep`, no files opened destructively), cross-checked
visually against the Phase 0 screenshots in `02_VISUAL_REFERENCE_INDEX.md`.

---

## Legacy design system (`elkheima-beach-resort/frontend`)

### Tokens

A real, dedicated token system exists at `src/tokens/`: `colors.ts`,
`typography.ts`, `spacing.ts`, `sizing.ts`, `radiuses.ts`, `shadows.ts`,
`borders.ts`, `opacity.ts`, `motion.ts`, `breakpoints.ts`, `z-index.ts`,
`a11y.ts`, `semantic-colors.ts`, plus a documentation file
`src/tokens/DESIGN_SYSTEM.md` that claims WCAG 2.1 AA and a
single-source-of-truth principle (claim not independently re-verified in
this pass — see `06_KEEP_ADAPT_REMOVE_MATRIX.md`).

**Palette:** Ocean (primary blue), **Gold `#c9a84c`** (accent, explicitly
marked as single source of truth), Sand (neutral), Coral/Teal (accents 2/3),
plus semantic success/warning/error/info. `tailwind.config.js` (11.4KB)
duplicates/extends the same palette under different token names
(`brand-orange`, `brand-blue`, `brand-gold`, `brand-navy`, `coastal-*` cyan,
`gold-*`, `navy-*`, `sand-*`) — i.e. **two overlapping token
representations** (the `src/tokens/` TS files and the Tailwind config) that
would need reconciling, not copying verbatim, if adopted.

Dark mode is explicitly **removed** in this codebase ("نستخدم Coast Dark theme
دائماً" per a config comment) — Ops/Admin/Dima views are dark-only by design,
which is a different model from Resort OS's current light/dark-aware token
system (see below).

**Two visually distinct sub-brands observed:** the marketing pages
(Home/Rooms/etc.) use a gold/navy/sand "Coastal" light look with real
photography (confirmed in screenshots); the Digital Hub uses a separate
cyan-accent (`--ds-accent: #00d4ff`) dark glassmorphism look (confirmed in
the `legacy_digital-hub_*` screenshots). These are not the same design
language and should not be merged uncritically.

### Component families

- **Layout:** `TheNavbar.vue`, `TheFooter.vue`, `PageContainer.vue`.
- **Common/shared:** `BackToTop.vue`, `ScrollProgress.vue`, `Toast.vue`,
  `HeroSection.vue`, `PageBookingModal.vue`.
- **UI kit** (`src/components/ui/`): `Button.vue`, `Icon.vue`,
  `Pagination.vue` — small, curated.
- **Two parallel primitive families** worth reconciling rather than copying
  both: `src/elements/` (`KCard`, `KInput`, `KRating`, `KChip`, `KButton`,
  `KDropdown`) and `src/primitives/` (`KIcon`, `KImage`, `KText`, `KDivider`).
- **Booking:** `BookingModal.vue`, `PaymentModal.vue`.
- **Hub-specific:** `HubCart.vue`, `HubConcierge.vue`, `HubRoomServices.vue`,
  `HubSpaSection.vue`.
- **Utility/marketing:** `SEOHead.vue`, `LocalBusinessSchema.vue`,
  `LanguageSelector.vue`, `TourOverlay.vue`, `CookieConsent.vue`,
  `HotDealsBar.vue`, `LoyaltyWidget.vue`, `SmartUpsell.vue`,
  `UrgencyTimer.vue`, `TripAdvisorWidget.vue`, `AbandonmentRecovery.vue`,
  `PWAInstallBanner.vue`, `BeachMap.vue`, `BookingComparison.vue`,
  `SunbedOrderModal.vue`.
- **Error boundaries per surface:** `ErrorBoundary.vue`,
  `AdminErrorBoundary.vue`, `OpsErrorBoundary.vue`, `HubErrorBoundary.vue` —
  a consistent, reusable pattern worth keeping conceptually.

### Assets

| Location | Size | File count |
|---|---|---|
| `public/images/` | 47MB | 230 |
| `public/icons/` | 284KB | 11 |
| `src/assets/` | 72KB | 3 |
| **Total `public/`** | **49MB** | **241** |

Per-subfolder counts (`public/images/*`): rooms 25, gallery 34, beach 31
(incl. `beach/views`), products 45, pages 26, hero 14, restaurant 12 (+
`restaurant/food`), resort 5, activities 5, events 5, manage-page 8,
packages 3, menu 10 root + 10 category subfolders (one `category.webp` per
menu category — legitimate repetition, not duplication). `blog/` and `home/`
subfolders exist but are **empty**.

**Remote dependency (real risk for a slow-network resort site):** the Digital
Hub hard-codes remote Unsplash URLs for category hero images and a background
image (`CATEGORY_HERO`/`SECTION_HERO`/`TYPE_FALLBACKS` maps in
`DigitalHub.vue`). **Correction:** the first version of this document
described these as "not owned/licensed" — that claim was not supported by
any evidence gathered in this pass and has been removed. What is actually
verified: these images are served from a third-party host (`images.unsplash.com`),
not from the repository's own asset library. Ownership/licensing terms for
these specific images were not checked. The evidenced, concrete risk is
independent of licensing either way: a third-party remote dependency is a
performance liability (extra DNS/TLS/connection round-trips), an
offline/weak-network reliability liability (the whole point of a
beach/venue-network-aware resort site), and a minor privacy liability
(leaking guest requests to a third party) — any of which is reason enough to
replace these with owned, locally-hosted images before adopting this pattern,
without needing to assert anything about their license.

**Correction — asset duplication was re-checked with real content hashes,
not just filenames.** The first version of this document stated "no
`_v2`/`_old` duplicate-asset naming pattern was found" and implied minimal
duplication from that alone. A full `sha256sum` pass over all 230 legacy
images (`find ... -exec sha256sum {} \;`, results kept at
`/tmp/el-kheima-public-phase-0/legacy-image-hashes.txt`) found:

- **40 distinct groups of byte-identical files** (same photo, different
  filename, often in different category folders — e.g. `hero/hero-01.webp`
  is the exact same file as `products/e23200a940f7423a8b415b8a53941b0b.webp`,
  `manage-page/hero-beach.webp`, `rooms/view-01.webp`, and
  `beach/views/beach-view-01.webp` — five copies of one image).
- **96 files are involved in some duplicate group; 56 of those are fully
  redundant copies** that could be deleted with zero content loss (keeping
  one canonical copy per group).
- **~10.9MB of the 49MB total (~22%) is pure duplication.**

This is a real, previously-unverified finding, not a naming-pattern
assumption — it directly informs `07_MIGRATION_BATCH_PROPOSAL.md`'s asset
batch: deduplicating before compressing/migrating saves roughly a fifth of
the transfer/storage cost for free, before any lossy optimization.

A `dist/` build output directory and an `optimize-images.sh` script exist at
the repo root, indicating an image-optimization step was already part of
this project's own build pipeline — worth reusing the *approach*, not the
specific script, since target formats/sizes should match Resort OS's own
asset pipeline
decisions.

---

## Current design system (`resort-os/frontend`)

### Tokens

`packages/ui/src/styles/tokens.css` (87 lines) + `packages/ui/tailwind-preset.js`
define a **single**, dark-mode-aware CSS-variable token system shared by both
`el-kheima` (staff) and `public` apps:

- `--color-primary-ring: 11 79 138` (light) / `96 165 250` (dark) — an ocean
  blue, conceptually aligned with the legacy "Ocean" primary.
- `--color-secondary: 201 150 60` ("gold DEFAULT #C9963C", light) / `245 215
  142` ("gold.light", dark) — **near-identical brand gold to the legacy
  palette's `#c9a84c`**. This is a concrete, low-risk "keep the brand color"
  finding: both codebases independently converged on the same gold accent.
- `--color-success`/`--color-danger`/`--color-surface` semantic tokens, with
  light/dark pairs (`white` / `stone-900` for surface) — this is a **more
  disciplined single-source-of-truth token system** than the legacy's two
  overlapping representations (TS token files + separate Tailwind config).

### Components

`packages/ui/src/components/` — 43 shared components used by the staff app's
POS/KDS/admin screens (confirmed count from `docs/audits/PRODUCTION_READINESS_AUDIT.md`'s
360° review, not recounted independently here). The current `apps/public`
itself has only 3 local components: `SiteHeader.vue`, `SiteFooter.vue`,
`LanguageSelector.vue` — it does not yet draw on the shared 43-component
library beyond what these three wrap.

### Assets

| Location | Size |
|---|---|
| `apps/public/public/` (just `favicon.png`) | 8KB |
| `apps/public/src/assets/` (`el-kheima-logo.svg`, `main.css`) | 16KB |
| **Total** | **24KB** |

This is the starkest concrete number in this audit: **24KB of current public
assets versus 49MB of legacy public assets** — a ~2000× gap, and it is the
direct, measurable cause of the flat/photography-free look confirmed in the
`current_home_*` screenshots versus the `legacy_home_*` screenshots.

---

## Accessibility and reuse caveats (do not assume "attractive = reusable")

Per the handoff's explicit instruction, the following were **not**
independently verified in this pass and must not be assumed from the legacy
`DESIGN_SYSTEM.md`'s own WCAG claim:

- color contrast ratios on the gold-on-white and cyan-on-dark combinations;
- focus order/visible-focus-ring behavior across the K-component families;
- keyboard operability of `HubCart.vue`'s quantity steppers and modals;
- touch target sizing on mobile (the cookie-consent buttons and stacked
  error toasts in the captured screenshots visually appear tight against the
  390px viewport edge — worth a dedicated a11y pass, not a blocking Phase 0
  finding);
- `reduced-motion` handling (a `motion.ts` token file exists but its actual
  application was not traced);
- Arabic typography quality (font choice, line-height) under real device
  conditions and outdoor/sunlight readability — cannot be assessed from a
  screenshot alone.

These become explicit acceptance-criteria items for whichever migration batch
adopts legacy visual patterns (see `07_MIGRATION_BATCH_PROPOSAL.md`), not
assumptions carried over from the legacy claim.
