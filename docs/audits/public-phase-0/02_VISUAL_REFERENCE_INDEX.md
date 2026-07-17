# 02 — Visual Reference Index

**Canonical viewports:** desktop `1440x1024`, mobile `390x844` (per handoff §0A.3).
No tablet state was captured — neither pilot app showed a distinct tablet
layout worth a separate state in this pass.

**Capture method:** Playwright (Chromium, system `google-chrome` channel),
headless, `waitUntil: networkidle` + 800ms settle, full-viewport (not
full-page) screenshot. Script and raw JSON result log kept at
`/tmp/el-kheima-public-phase-0/capture-results.json` (not committed — evidence
stays under `/tmp` per the handoff's output-path rule; this document is the
committed index of what was captured and what it shows).

**Total:** 24 screenshots, ~7.6MB, all under `/tmp/el-kheima-public-phase-0/screenshots/`.

---

## Legacy app (`elkheima-beach-resort`, dev server `http://localhost:5173`)

**Environment note (applies to every legacy screenshot):** the legacy app's
own backend (`VITE_API_URL=http://localhost:8000/api`) is not running in this
environment — only its frontend dev server was started. Every legacy page
rendered its full static shell, layout, imagery, and copy correctly, but
dynamic data calls (room list/pricing, hot deals, site settings) failed
client-side and surfaced as stacked red toast banners ("لا يوجد اتصال
بالسيرفر — تأكد من الاتصال بالإنترنت"). This is expected, non-destructive,
and does not indicate a legacy app defect — it confirms graceful client-side
failure handling. All legacy visual evidence below should be read as **shell
and design reference**, not as proof of live legacy data behavior.

| File | Route | Locale | Viewport | What it shows |
|---|---|---|---|---|
| `legacy_home_ar_desktop.png` | `/ar` | ar (RTL) | 1440×1024 | Full-bleed photographic hero (cocktail/beach), gold "منتجع #1 في المنطقة" badge, headline, 3-tab booking widget (الغرفة/الشاطئ/المطعم), top nav with EN/RU/IT language pills, cart icon, AI cookie-consent bubble, floating call button |
| `legacy_home_ar_mobile.png` | `/ar` | ar (RTL) | 390×844 | Same hero, mobile-collapsed nav |
| `legacy_home_en_desktop.png` | `/en` | en (LTR) | 1440×1024 | Confirms LTR mirroring of the same layout works (nav/CTA order flips correctly) |
| `legacy_home_en_mobile.png` | `/en` | en (LTR) | 390×844 | — |
| `legacy_home_ru_desktop.png` | `/ru` | ru (LTR) | 1440×1024 | Russian copy renders; used as the required "one representative LTR shell" for ru |
| `legacy_home_ru_mobile.png` | `/ru` | ru (LTR) | 390×844 | — |
| `legacy_home_it_desktop.png` | `/it` | it (LTR) | 1440×1024 | Italian copy renders; representative LTR shell for it |
| `legacy_home_it_mobile.png` | `/it` | it (LTR) | 390×844 | — |
| `legacy_rooms_ar_desktop.png` | `/ar/rooms` | ar (RTL) | 1440×1024 | Room-category hero ("غرف الأحلام"), same visual language as Home, real interior photography |
| `legacy_rooms_ar_mobile.png` | `/ar/rooms` | ar (RTL) | 390×844 | — |
| `legacy_rooms_en_desktop.png` | `/en/rooms` | en (LTR) | 1440×1024 | — |
| `legacy_rooms_en_mobile.png` | `/en/rooms` | en (LTR) | 390×844 | — |
| `legacy_digital-hub_ar_desktop.png` | `/ar/hub` | ar (RTL) | 1440×1024 | First-visit **language-picker modal** (dark "Coastal Dark" glassmorphism sub-brand, distinct from the marketing site's gold/navy look) — category tiles (room service / housekeeping / concierge) visible behind the modal |
| `legacy_digital-hub_ar_mobile.png` | `/ar/hub` | ar (RTL) | 390×844 | — |
| `legacy_digital-hub_en_desktop.png` | `/en/hub` | en (LTR) | 1440×1024 | — |
| `legacy_digital-hub_en_mobile.png` | `/en/hub` | en (LTR) | 390×844 | — |

Ru/it Digital Hub and Rooms states were **not** captured (out of pilot scope
per handoff §0B — pilot required ar/en desktop+mobile for all three routes,
plus one representative ru/it shell, which was satisfied on Home only).

---

## Current app (`frontend/apps/public`, dev server `http://localhost:3007`,
backend `http://127.0.0.1:8005` — both already running locally, healthy,
used read-only)

| File | Route | Locale | Viewport | What it shows |
|---|---|---|---|---|
| `current_home_ar_desktop.png` | `/` | ar | 1440×1024 | Flat blue gradient hero, no photography, headline/subhead/2 CTAs, 4-stat strip (#1, 35,000m², 225m beachfront, 13,000m² private beach), "مرحباً بكم" intro paragraph |
| `current_home_ar_mobile.png` | `/` | ar | 390×844 | — |
| `current_home_en_desktop.png` | `/` | en | 1440×1024 | Confirms client-side locale switch (localStorage) re-renders the same layout in English |
| `current_home_en_mobile.png` | `/` | en | 390×844 | — |
| `current_dining-menu_ar_desktop.png` | `/dining` | ar | 1440×1024 | Live, real seeded menu data grouped per outlet/category — view-only marketing page (no cart), matches `dining.public.menu` contract |
| `current_dining-menu_ar_mobile.png` | `/dining` | ar | 390×844 | — |
| `current_order-qr_ar_desktop.png` | `/order/2/1` | ar | 1440×1024 | **Live QR-scan guest ordering screen** for real seeded outlet 2 ("المطعم")/table 1. Shows real menu items with per-item "+" (add-to-cart) controls **and** two bottom actions "هات الفاتورة 🧾" / "نادِ الجرسون 🐰". **Correction:** these two buttons match the accepted `view_and_call` pattern **visually and in intent only** — they are not currently functional. Tapping either sends `context_type: 'dining_table'` to `POST /public/alerts`, which the backend rejects with HTTP 422 (the schema only accepts `restaurant_table\|cafe_table\|beach_location\|room\|other`), and the endpoint itself has further unresolved validation/authorization gaps even once that value is fixed — full detail in `05_API_AND_DATA_CONTRACT_MAP.md`. The "+" controls feed a real cart that posts to `POST /dining/public/orders`, which is the separately non-compliant self-ordering part. |
| `current_order-qr_ar_mobile.png` | `/order/2/1` | ar | 390×844 | — |

`/book`, `/confirmation`, `/beach/checkin/:id`, `/survey/:token` were not
rendered in this pilot pass (out of the three named pilot routes; flagged as
static-only in `01_ROUTE_AND_STATE_INVENTORY.md`).

---

## Direct visual comparison (Home)

The single clearest Phase-0 finding from the pilot: the legacy Home page is a
full photographic hero with real resort imagery, a trust badge, and a
3-tab booking widget; the current Home page is a flat two-color gradient with
no imagery at all. This is the primary evidence behind the "reuse legacy
visual design" recommendation in `06_KEEP_ADAPT_REMOVE_MATRIX.md` — it is a
content/photography/layout gap, not a technical one (the current app already
uses a more disciplined, dark-mode-aware shared token system — see
`03_DESIGN_AND_ASSET_INVENTORY.md`).

## Known capture limitations (explicit, not hidden)

- Legacy dynamic data (pricing, availability, hot deals) could not be
  exercised — its backend was not started in this environment (see
  environment note above). This is a legacy-repo-only limitation; the current
  app's backend was live for every current-app screenshot.
- No tablet viewport was captured.
- Only the three pilot routes (plus their nearest current-app equivalents)
  were rendered; the rest of `01_ROUTE_AND_STATE_INVENTORY.md` is
  static-code evidence, explicitly marked as such.
- Loading/empty/error states were not deliberately forced (e.g. no attempt
  to screenshot a legacy page mid-fetch); the red error toasts visible in
  every legacy screenshot are an incidental, honest capture of the real
  no-backend error state, not a staged one.
