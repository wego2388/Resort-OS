# CL-02C — Marketing consent and tracking containment handoff

**Date:** 2026-07-26  
**State:** implemented and included in the IP-only deployment  
**Commit / push:** none

## Result

- Analytics consent defaults to denied.
- GA, GTM, and Meta initialization are gated by the accepted categories.
- Decline and revoke paths update provider consent and remove client tracking
  state.
- Consent stores a version, timestamp, and category choices.
- QR/service routes are classified as no-tracking routes.
- The public site URL defaults to `https://191.218.161.133:8443`.
- Domain/email facts derived from `elkheimabeachresort.com` were removed from
  the runtime truth contract after Mohamed's explicit IP-only decision.
- The unused invented chatbot data source and obsolete enhanced sitemap were
  removed.
- Legacy Digital Hub complaint/rating calls were withheld because they posted
  without the new versioned disclosure; they require a dedicated operational
  feedback contract before returning.

## Main areas changed

- consent and analytics services;
- GA/GTM/Meta composables;
- application startup and router tracking policy;
- cookie-consent and privacy UI/copy in four locales;
- brand/public-truth configuration;
- SEO/schema/footer/mobile contact surfaces;
- `index.html`, robots, sitemap, and marketing Nginx headers.

## Verification

- `npm run validate`: pass.
  - public-truth gate: pass;
  - `vue-tsc --noEmit`: pass;
  - Vite production build: pass (`2039` modules).
- `npm audit --audit-level=high`: `0 vulnerabilities`.
- `git diff --check`: pass after normalizing three EOF blank lines.
- Production Docker build: pass.
- External HTTPS smoke test on the deployed IP: pass.
- Built marketing assets were scanned and contain no
  `elkheimabeachresort.com` dependency.

## Deferred

- A browser network-interception regression suite for every consent
  transition.
- Owner-approved analytics IDs and policy/legal review.
- Dedicated consent-aware operational complaint/order-rating workflow.
