# Owner Intelligence Cockpit — Handoff للمرحلة 8 (Security Review)

**تاريخ:** 2026-08-08
**الفرع الحالي:** `claude/CX-02C-frontend-auth-bootstrap`
**آخر Alembic head:** `f8aa1f0fabba` (لا migration جديدة في Phase 6+7+7a)
**Tests:** 150 owner passed — صفر فشل
**قائد التنفيذ والمراجع النهائي:** Codex

---

## ما اكتمل (لا تعيد بناءه)

### المرحلة 1 — عقود المقاييس ✅
الوثيقة الكاملة: `docs/owner/kpi-contracts.md`

### المرحلة 2 — العزل والأمان ✅
- `owner` role level=10، `get_owner_reader`، `MANDATORY_2FA_ROLES`
- `owner_policy.py` — allowlist fail-closed
- `OwnerWatchlist` + `OwnerAllocationRule` — نماذج DB
- Migration `f8aa1f0fabba` — مطبّق
- 13 اختبار عزل — كلها نجحت

### المرحلة 3 — Aggregation APIs ✅
- `GET /api/v1/owner/now` — 7 مقاييس (A-1 → A-7)
- `GET /api/v1/owner/performance` — 3 مقارنات (اليوم/أسبوع/شهر)

### المرحلة 4 — Owner PWA ✅
- `NowScreen.vue` + `PerformanceScreen.vue` + `LoginView.vue` + `AppShell.vue`
- منشور على `owner.elkheima.com`

### المرحلة 5 — مراجعة الأرقام ✅
- محمد فتح التطبيق على الهاتف (2026-08-08)
- الأرقام صفر بسبب seed data — النظام يقرأ صح
- 2FA login fix: `LoginView.vue` يتعرف على `2FA_CODE_REQUIRED`

### المرحلة 6 — Analytics ✅ (2026-08-08)
**Endpoints:**
- `GET /api/v1/owner/sales` — top items + ABC + هامش
- `GET /api/v1/owner/beach-performance` — تذاكر بالنوع
- `GET /api/v1/owner/channel-analytics` — B2B per hotel
- `GET /api/v1/owner/expense-analytics` — مصروفات كـ % + variance
- `GET /api/v1/owner/procurement-analytics` — موردون + PR/PO variance

**Frontend:**
- `SalesScreen.vue` — tab dining (ABC + هامش) / beach (تذاكر)
- `ExpensesScreen.vue` — tab expenses (variance flags) / procurement (موردون)

### المرحلة 7 — Shifts + Exceptions ✅ (2026-08-08)
**Endpoints:**
- `GET /api/v1/owner/shifts` — ورديات مفتوحة + حركات كاش + variance tier
- `GET /api/v1/owner/exceptions` — critical/attention/watch مرتّبة

**Frontend:**
- `ShiftsScreen.vue` — tab exceptions (badge عدد حرجة) / shifts (قابل للطي)

### المرحلة 7a — PWA Polish ✅ (2026-08-08)
- `public/icon-192.png` + `public/icon-512.png` — من logo الأصلي
- `GET /api/v1/owner/now/history?days=7` — sparklines endpoint
- `NowScreen.vue` — sparklines حقيقية على A-1/A-2/A-3/A-6/A-7
- Bottom nav: 5 tabs (الآن / الأداء / المبيعات / المصروفات / الورديات)
- Build: 16 entries precached

---

## قرارات محمد المسجّلة

1. لا AI/LLM في أي مكان — نهائي
2. `owner.elkheima.com` subdomain — cookie منفصلة SameSite=Strict
3. **Phase 8 (Unit economics) و Phase 9 (Scenario sandbox) محذوفان** — قرار محمد 2026-08-08
4. المنتج ينتهي عند Phase 7a + Security Review

---

## ما تبقّى من المراحل

| # | الاسم | الحالة | ملاحظة |
|---|---|---|---|
| **7b** | UX completion | **التالي** | logout + date range + channel screen + shift history + 2FA |
| **7c** | HR + Payroll visibility | بعد 7b | موظفين + رواتب + حضور aggregate |
| **7d** | Discount & customer group analytics | بعد 7c | خصومات كاشير + أداء المجموعات |
| **8** | Security review + production gate | الأخير | مراجعة أمنية مستقلة |
| ~~8~~ | ~~Unit economics~~ | **محذوف** | قرار محمد 2026-08-08 |
| ~~9~~ | ~~Scenario sandbox~~ | **محذوف** | قرار محمد 2026-08-08 |

---

## Phase 7b — UX Completion (التفاصيل)

### 1. Logout button
- زرار في header الـ `AppShell.vue`
- يستدعي `auth.logout()` → redirect لـ `/login`
- أمان أساسي

### 2. Date range picker
- Component `DateRangePicker.vue`: 4 أزرار سريعة (اليوم / أمبارح / هذا الأسبوع / هذا الشهر) + date inputs
- يُضاف في أعلى `SalesScreen` + `ExpensesScreen`
- `date_from`/`date_to` تتحدث reactively وتعيد جلب البيانات

### 3. PerformanceScreen breakdown
- Backend: `OwnerPerformanceResponse` + optional `breakdown` field: `dining_revenue / beach_revenue / rooms_revenue / other_revenue`
- Frontend: collapsible row في `PeriodComparisonCard` — collapsed بـ default

### 4. Channel Analytics screen
- Backend جاهز: `GET /owner/channel-analytics`
- Frontend: tab ثالث في `SalesScreen` (dining / beach / فنادق B2B)

### 5. Shift history
- Backend: `GET /owner/shifts/history?days=7` — ورديات مغلقة مع variance + cash_movements
- Frontend: tab ثالث في `ShiftsScreen` (التنبيهات / مفتوحة / **تاريخ**)
- مصدر: `CashierShift` status='closed' + `CashMovement`

### 6. 2FA setup flow
- `TwoFactorSetupView.vue` حالياً stub
- يُكمل: QR code + كود التحقق + تأكيد التفعيل
- endpoints موجودة: `/2fa/setup`, `/2fa/enable`

---

## Phase 7c — HR + Payroll (التفاصيل)

**قاعدة:** استثناء صريح من "لا payroll per employee" — المالك يشوف موظفيه.
**ما يُعرض:** الاسم + المسمى + net_salary + penalty + advance + حضور aggregate.
**ما لا يُعرض:** national_id (مشفر) + monthly_tax + social_insurance تفاصيل.

- Backend: `GET /owner/hr-summary` — قائمة موظفين + آخر PayrollLine + attendance هذا الشهر
- Frontend: `HRScreen.vue` — tab سادس في bottom nav
- مصدر: `Employee` + `PayrollLine` + `AttendanceRecord`

---

## Phase 7d — Discount Analytics (التفاصيل)

- Aggregate: إجمالي خصم per type (conditional/customer_group/manual) + % من الإيراد
- Per cashier: إجمالي خصم يدوي لهذا الشهر (لا raw transactions — aggregate فقط)
- Customer groups: عدد عملاء + إجمالي مبيعات + إجمالي خصم + متوسط فاتورة per group
- لا أسماء عملاء أفراد — aggregate per group فقط
- Backend: `GET /owner/discount-analytics`
- Frontend: tab في `SalesScreen` أو قسم في `ExpensesScreen`

---

## أوامر التحقق

```bash
# Backend
cd backend && source .venv/bin/activate
pytest tests/ -k "owner" -v          # 150 tests حالياً
alembic heads                         # f8aa1f0fabba — single head

# Frontend
cd ../frontend
pnpm --filter owner type-check        # نظيف
pnpm --filter owner build             # 16 entries precached

# Production
curl https://owner.elkheima.com/icon-192.png -o /dev/null -w "%{http_code}"  # 200
curl https://owner.elkheima.com/icon-512.png -o /dev/null -w "%{http_code}"  # 200
curl https://owner.elkheima.com/login  -o /dev/null -w "%{http_code}"        # 200
```
