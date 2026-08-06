# مراجعة الدين التقني وتغطية الاختبارات — Resort OS

**تاريخ المراجعة:** 2026-08-06  
**المراجع:** Claude (بتفويض Codex)  
**السياق:** جولة ذكية بعد إغلاق N+1 queries ورفع coverage لـ `dining/api/router.py`

---

## 1. الحالة العامة — قوي وناضج

**الأدلة الكمية:**
- **2333 test** passed، 42 skipped، صفر failures
- **Coverage إجمالي: 86%** (25,454 سطر total، 3,561 غير مغطى)
- Alembic **head واحد نظيف** (`52f4544e50d2`)
- Frontend type-check **نظيف بالكامل** (صفر errors)
- الـ N+1 queries في dining **اتصلحت فعليًا** بـ batch-load

**ملخص المعمارية:**
- فصل router/service/crud/resort_os **محترم عبر كل الـ13 موديول**
- مفيش router بيكلّم DB مباشرة
- مفيش business logic في schemas
- Domain engines (`resort_os/`) **pure Python** من غير FastAPI/SQLAlchemy

---

## 2. ما يستحق الإشادة

### 2.1 الأمان جدي — fail-closed في كل مكان

```python
# payment_policy.py — 67% coverage بس السلوك صح
def resolve_direct_tender_account(method: str) -> str:
    """Card/wallet بيرفضوا 503 لو الـ GL account مش متهيّأ
    بدل ما يكتبوا على cash 1100 بالغلط."""
    if method == "card" and not settings.DINING_CARD_SETTLEMENT_ACCOUNT:
        raise PaymentMethodNotConfiguredError(...)
```

- `EncryptedString` (Fernet) على كل PII (national_id، passport، phone)
- `SELECT FOR UPDATE NOWAIT` + `.populate_existing()` في كل race condition حقيقي
- Rate limiting على كل endpoint عام (20/60s للـ chat، 30/60s للـ public)
- Auth chain كامل: JWT → blacklist → 2FA gate → role level → branch access

### 2.2 N+1 queries اتحلّت صح — مش workaround

```python
# dining/services.py — _deduct_inventory_for_order
# قبل: crud.get_item() لكل order_item → N queries
# بعد: crud.get_items_by_ids() مرة واحدة → 1 query
item_ids = [req.item_id for req in data.items]
items_map = crud.get_items_by_ids(db, item_ids)
for item_req in data.items:
    item = items_map.get(item_req.item_id)  # lookup من الـ dict
```

نفس النمط في: `create_order`، `add_items_to_order`، `sync_offline_order`، `_deduct_inventory_for_order`.

### 2.3 التوثيق حي — مش boilerplate

- `CLAUDE.md` (2920 سطر) — الدستور الهندسي بتواريخ حقيقية
- `PROJECT_STATUS.md` — سجل release-by-release بأدلة نشر حقيقية
- Docstrings بتشرح **ليه** مش بس **إزاي** (مثال: كل باج حقيقي اتصلح بتاريخه)

---

## 3. الدين التقني المتبقي — محدد وقابل للتنفيذ

### 🔴 أولوية 1 — Flaky test يكسر CI بالصدفة

**المكان:** `tests/test_api/test_timeshare_report_audit.py::TestInstallmentPaymentAuditLog::test_pay_installment_creates_audit_log`

**الوصف:**  
بيعدي لوحده، بيفشل في full suite بسبب test ordering. السبب: `AccountingPeriod` shared state بين timeshare وdining tests.

**الحل:**  
عزل الـ `AccountingPeriod` في fixture منفصلة لكل test أو استخدام `branch_id` فريد.

**الأثر:** لو اتكرر ده في CI ممكن يخفي regression حقيقي.

---

### 🟡 أولوية 2 — dining/services.py (2920 سطر) — أكبر ملف في المشروع

**Coverage: 86%** — ممتاز، لكن صعب التنقل.

**المحتوى:**
- Order lifecycle (create/update/status/void)
- Payment (split_bill/merge/refund/currency)
- Inventory deduction
- KDS ticket generation
- Food cost calculation
- Receipt PDF generation

**الاقتراح — تقسيم منطقي:**
```
dining/
  ├── services/
  │   ├── __init__.py       ← re-exports الـ public API
  │   ├── _order.py         ← create_order, add_items, sync_offline
  │   ├── _payment.py       ← split_bill, merge, refund, apply_discount
  │   ├── _inventory.py     ← _deduct_inventory_for_order, _resolve_extras
  │   ├── _kitchen.py       ← KDS ticket generation, status transitions
  │   └── _reports.py       ← food cost, receipt PDF, sales report
```

**مش refactor جذري** — بس extract داخلي عشان الملف الواحد يبقى ≤800 سطر.

---

### 🟡 أولوية 3 — endpoints حرجة بدون تست

**dining/api/router.py — 75% coverage (177 سطر غير مغطى)**

الـ endpoints المهمة المفقودة:
1. **`POST /dining/orders/{id}/split-bill`** — سيناريو مالي معقد (تقسيم فاتورة لدفعات)
2. **`POST /dining/orders/{id}/merge`** — دمج طلبين نشطين (WebSocket broadcast + table state)
3. **`POST /dining/orders/{id}/items/{item_id}/void`** — إلغاء صنف مع PIN approval
4. **`POST /dining/items/{id}/upload-image`** — رفع صور المنيو
5. **`WebSocket /dining/ws/tables/{branch_id}`** — بث حي للطاولات

**التأثير:**  
split-bill ومerge **موجودين في الإنتاج** بدون أي تغطية — لو في باج مالي فيهم مش هنعرف إلا في production.

**الحل المقترح:**  
```python
# tests/test_api/test_dining_split_merge.py
class TestSplitBill:
    def test_split_equal_shares(self, client, db): ...
    def test_split_custom_amounts(self, client, db): ...
    def test_split_requires_manager_pin(self, client, db): ...

class TestMergeOrders:
    def test_merge_same_outlet(self, client, db): ...
    def test_merge_releases_source_table(self, client, db): ...
    def test_merge_rejects_different_branch(self, client, db): ...
```

---

### 🟢 أولوية 4 — موديولات تانية coverage ضعيف

| الموديول | Coverage | الملاحظات |
|---|---|---|
| `timeshare/api/router.py` | **72%** | أضعف router — منطق معقد (ISO weeks, installments, visits) |
| `crm/services.py` | **73%** | loyalty redeem، customer groups، paths غير مغطية |
| `leasing/api/router.py` | **76%** | عقود إيجار، penalties، cash logs |
| `chat/services.py` | **80%** | Gemini integration، circuit breaker، daily cap |

**الاقتراح:** جولة تانية بعد dining لرفع timeshare/crm لـ ≥85%.

---

### 🟢 أولوية 5 — ملفات Vue كبيرة في frontend

```
2054 سطر   TimeshareView.vue
1700 سطر   HRView.vue
1479 سطر   CRMView.vue
1236 سطر   FinanceView.vue
1061 سطر   UnifiedPOSView.vue
```

**الملاحظة:** دي admin views بمنطق CRUD كتير. مش ضرورة تتقسم دلوقتي لكن لو أي view منهم احتاج تعديلات متكررة، extract الـ sections لـ composables منفصلة.

---

### 🟢 أولوية 6 — ملفات قديمة محتاجة قرار

**`tests/test_api/test_cafe_public_orders.py`** — لسه موجود رغم إن `cafe` module اتحذف (Batch 6 من dining cutover). ربما بيختبر dining المكافئ دلوقتي أو بيتجاهل 404s.

**الحل:** راجع الملف — لو بيختبر `/cafe/public/*` قديم وفاشل، امسحه. لو بيختبر `/dining/public/*` الجديد، غيّر اسمه.

---

## 4. ما لا يحتاج تدخل فوري

### 4.1 kernel coverage منخفض لكن ده متوقع

```
app/core/kernel/cache.py         45%   ← Redis fallback paths
app/core/kernel/health.py        33%   ← startup hooks
app/core/kernel/sentry.py        19%   ← error reporting (تُختبر في production)
app/core/kernel/whatsapp.py      41%   ← external API (mock في tests)
app/core/kernel/email_service.py  0%   ← SendGrid (مش مفعّل بعد)
```

**التقييم:** دي infrastructure utilities — low-frequency paths. الـ happy paths مغطية (auth/database/middleware 100%).

### 4.2 seed files مش محتاجة coverage

```
app/seed.py                      2287 سطر   ← demo data
app/production_demo_seed.py      1395 سطر
app/seed_recipes_2026.py         1126 سطر
```

**التقييم:** idempotent seeding ليه tests منفصلة (`test_production_demo_seed.py`) — مش محتاج unit coverage على الملف نفسه.

---

## 5. القرار التنفيذي — الترتيب المقترح

بناءً على الأثر والخطر:

### المرحلة الأولى — الأحق (أسبوع واحد)
1. **إصلاح الـ flaky test** (يوم واحد) — ده بيهدد CI stability
2. **split-bill + merge tests** (يومين) — سيناريوهات مالية في production بدون تغطية
3. **void_order_item مع PIN approval** (يوم واحد) — endpoint حساس

### المرحلة الثانية — تحسين (أسبوعين)
4. **تقسيم dining/services.py** (3 أيام) — extract منطقي بدون breaking changes
5. **رفع timeshare router coverage** (3 أيام) — من 72% → 85%+
6. **WebSocket dining tests** (يومين) — broadcast scenarios
7. **مراجعة test_cafe_public_orders.py** (ساعة واحدة) — حذف أو rename

### المرحلة الثالثة — تنضيف اختياري (لو فيه وقت)
8. **CRM services tests** — loyalty/groups scenarios
9. **Image upload endpoint test** — validation/storage

---

## 6. خلاصة — المشروع production-ready

**الحقائق:**
- 2333 test، 86% coverage، Alembic نظيف، type-check نظيف
- Architecture نظيف، أمان جدي، N+1 اتحلّت
- الدين المتبقي **محدد وقابل للحل**، مش هيكلي

**الباقي تنضيف وتعلية coverage في نقاط محددة، مش إعادة بناء.**

الأولوية الأعلى: **flaky test** (يهدد CI) ثم **split-bill/merge tests** (مالية حرجة في production بدون تغطية).

---

**التوصية النهائية:**  
المشروع جاهز للإنتاج من ناحية هندسية. النقاط المذكورة فوق هي **تحسينات جودة**، مش حواجز إطلاق.
