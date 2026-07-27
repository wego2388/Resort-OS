# Handoff CL-01R — Codex

- **Implementer:** Codex
- **Date:** 2026-07-26
- **Scope:** `backend/app/modules/chat/**` and the marketing-site chatbot
- **Review basis:** `2026-07-26_CL-01_codex_review.md`
- **Status:** implementation complete; ready for independent review
- **Commit / push / deploy:** none

## Outcome

CL-01R closes H-01 through H-05 and M-01 through M-05 with a deliberately
privacy-minimised, fail-closed design.

The chatbot is not silently production-enabled. A deployment must configure an
explicit public-host-to-branch map, Redis, Gemini credentials, approved public
facts, and the provider data-governance confirmation. Until then, the public
endpoints fail with a clear `503` instead of using branch `1` or invented
content.

## Security and privacy decisions

### H-01 — prompt boundary and history

- `ChatRequest` no longer accepts `history`, `context`, branch, or location.
  Unknown fields are rejected with `422`, rather than silently trusted.
- Every provider call is one stateless user turn. The message appears once in
  `contents`; instructions use Gemini's real `systemInstruction`.
- Guest location is optional and comes only from a valid
  `X-Guest-Session` capability resolved by the existing Gate 8 backend.
  Client query/body location values never enter the prompt.

### H-02 — PII and retention

- The `chat_messages` table/model was removed before release.
- The backend stores no guest message or model reply. It keeps only lifecycle
  metadata and aggregate token/message counters.
- The browser keeps visible messages in memory only. The new code writes no
  raw chat history, leads, or analytics to `localStorage`, and removes legacy
  keys on open.
- The UI requires an explicit disclosure action before starting an AI session.
- Each Gemini request sends `"store": false`.
- Silent CRM lead capture was removed. No message text is copied to CRM.

### H-03 — approved facts only

- `chat_public_facts` is an auditable allowlist with
  `draft|approved|retired`, approval timestamp, source reference, and optional
  expiry.
- Only approved, non-expired rows enter the prompt.
- Dining/PMS operational rows are no longer presented as automatically
  approved public prices or booking availability.
- No fallback star rating, phone, address, payment method, cancellation
  policy, coupon, scarcity message, or seasonal offer is generated.
- The marketing chatbot's hardcoded coupons/offers and direct fallback phone
  actions were removed.

### H-04 — branch and trusted location

- `_DEFAULT_BRANCH_ID = 1` no longer exists.
- `CHAT_PUBLIC_HOST_BRANCH_MAP` is the only site-to-branch source. Unknown
  hosts and inactive/missing branches fail closed.
- Chat bearer tokens are branch-bound.
- A Gate 8 guest session from another branch is rejected.

### H-05 — cost protection

- Existing per-minute IP middleware remains.
- Daily IP, daily bearer-session, global request, and global estimated-cost
  budgets are independent settings.
- Cost is reserved conservatively before the provider call using the pinned
  model's configured input/output token rates.
- A distributed concurrency guard runs before Gemini.
- Production requires Redis. Redis loss is fail-closed; the in-memory fallback
  is allowed only in `development|test|testing`.
- Anonymous counters hash IP/session values. Metrics count requests,
  rejections, provider errors, prompt/output tokens, and actual estimated cost
  inputs without storing message content.

## Medium findings

- **M-01:** server-issued 256-bit bearer secret; only SHA-256 digest stored;
  short TTL; no token in URL; unknown end/rate remains non-enumerable.
- **M-02:** `x-goog-api-key` header, stable `gemini-3.6-flash`,
  `systemInstruction`, no deprecated `temperature/topP/topK`, and no prefilled
  model turn.
- **M-03:** real locale at start, separate rate endpoint that does not end the
  session, explicit end endpoint, clean restart, and no partial raw-turn
  transaction because raw turns are not persisted.
- **M-04:** internal routes remain same-origin; external actions require an
  explicit HTTPS host allowlist and open with `noopener,noreferrer`.
  `javascript:`, `data:`, protocol-relative, HTTP, and unapproved hosts fail
  closed.
- **M-05:** a dedicated middleware adds `Cache-Control: no-store` to every
  `/api/v1/chat...` response, including validation and error responses.

## Files

### Resort OS

- `backend/app/modules/chat/models.py`
- `backend/app/modules/chat/schemas.py`
- `backend/app/modules/chat/crud.py`
- `backend/app/modules/chat/services.py`
- `backend/app/modules/chat/api/router.py`
- `backend/alembic/versions/dc6bfb5b79e8_chat_module.py`
- `backend/tests/test_api/test_chat.py`
- `backend/app/core/config.py`
- `backend/app/core/rate_limit.py`
- `backend/app/main.py`
- `backend/.env.example`
- `backend/alembic/env.py`

### Marketing website

- `src/composables/booking/useChatbot.ts`
- `src/composables/booking/useChatbotFallback.ts`
- `src/components/chatbot/ChatbotWindow.vue`
- `src/components/chatbot/ChatbotButton.vue`
- `src/components/chatbot/ChatbotMessage.vue`
- `src/components/chatbot/actionSafety.ts`
- `src/apps/public/DigitalHub.vue`
- `src/api/client.ts`
- removed duplicate `src/components/hub/HubConcierge.vue`

## Verification

```text
pytest -q tests/test_api/test_chat.py
→ 25 passed

pytest -q tests/test_api/test_chat.py \
  tests/test_api/test_guest_alerts.py \
  tests/test_api/test_service_location_tokens.py
→ 69 passed

python -m compileall -q app/modules/chat app/main.py app/core/config.py
→ pass

alembic heads
→ dc6bfb5b79e8 (head) at CL-01R migration freeze

Isolated PostgreSQL invocation of dc6bfb5b79e8 upgrade + downgrade
with a prerequisite branches table
→ pass; temporary database removed

npm run build
→ pass, 2048 modules transformed

npm run type-check
→ not runnable: `vue-tsc: not found`
```

The full migration chain on a brand-new PostgreSQL database was attempted but
stopped in the pre-existing migration
`e3f5a7b9c2d4_drop_legacy_dining_cafe_restaurant_tables.py`: it tries to drop
`fk_dining_order_items_split_id`, which does not exist in that fresh chain.
That failure occurs before CL-01R. The CL-01R migration itself was therefore
validated directly in an isolated PostgreSQL database and round-tripped
successfully.

No live Gemini request was made after this rewrite. Provider failure remains
safe: backend returns a controlled 502/503/504 and the UI uses a generic,
fact-free local fallback.

## Production enablement checklist

Do not enable AI traffic until all are true:

1. `CHAT_PUBLIC_HOST_BRANCH_MAP` contains the exact production host and real
   branch ID.
2. Redis is healthy and shared by all backend workers.
3. A dedicated Gemini key and the pinned stable model are configured.
4. Gemini project logging/data-sharing settings are reviewed, then
   `CHAT_PROVIDER_DATA_GOVERNANCE_VERIFIED=true` is set.
5. `chat_public_facts` contains owner-approved, sourced, non-expired public
   statements. An empty fact set is safe but intentionally unhelpful.
6. Cost/request/concurrency thresholds and token prices are approved for the
   production budget.
7. UAT verifies consent, Arabic/English/Russian/Italian replies, Gate 8
   location, provider outage fallback, 429/503 behavior, and deletion of legacy
   browser chat keys.

Model and API choices were checked against Google's official documentation on
2026-07-26:

- <https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash>
- <https://ai.google.dev/gemini-api/docs/latest-model>
- <https://ai.google.dev/api/generate-content>

## Explicitly not done

- No commit, push, deployment, DNS, VPS, or external dashboard change.
- No admin fact-management UI; this belongs with the later public-content
  control-plane work.
- No package/toolchain change. `vue-tsc` remains owned by CL-02.
