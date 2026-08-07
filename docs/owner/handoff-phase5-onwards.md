# Owner Intelligence Cockpit — Handoff للمرحلة 5+

**تاريخ:** 2026-08-07
**الفرع الحالي:** `claude/CX-02C-frontend-auth-bootstrap`
**آخر Alembic head:** `f8aa1f0fabba` (owner_module_phase2_and_pr_po_linkage — لا migration في Phase 3+4)
**Tests:** 2374 passed, 42 skipped — صفر فشل
**قائد التنفيذ والمراجع النهائي:** Codex

---

## ما اكتمل (لا تعيد بناءه)

### المرحلة 1 — عقود المقاييس ✅
الوثيقة الكاملة: `docs/owner/kpi-contracts.md`

### المرحلة 2 — العزل والأمان ✅
- `owner` role level=10، `get_owner_reader`، `MANDATORY_2FA_ROLES`
- `owner_policy.py` — allowlist fail-closed
- `OwnerWatchlist` + `OwnerAllocationRule` — نماذج DB
- Migration `f8aa1f0fabba` — مطبّق محلياً
- 13 اختبار عزل — كلها نجحت

### المرحلة 3 — Aggregation APIs ✅
**الملفات:**
- `backend/app/modules/owner/services.py` — `get_owner_now()` + `get_owner_performance()`
- `backend/app/modules/owner/schemas.py` — `OwnerNowResponse` + `OwnerPerformanceResponse` + كل الـ schemas
- `backend/app/modules/owner/api/router.py` — `GET /api/v1/owner/now` + `GET /api/v1/owner/performance`
- `backend/tests/test_owner_phase3.py` — 19 اختبار ✅

**المقاييس المنفّذة (A-1 → A-7):**
- A-1: إيراد اليوم ← `get_income_statement(db, branch_id, today, today).total_revenue`
- A-2: كاش الأدراج ← `build_active_shifts_response(db, branch_id)` مجموع expected_cash
- A-3: مصروفات اليوم ← نفس استدعاء A-1 `.total_expense`
- A-4: ذمم B2B ← `B2BContract` + `B2BContractDay` بعد `last_settled_at`
- A-5: ذمم تايم شير ← `TimeshareInstallment` status IN (unpaid/overdue) due_date <= today
- A-6: إشغال الغرف ← `Room.status='occupied'` / كل الغرف ما عدا maintenance/out_of_order
- A-7: سعة الشاطئ ← `BeachInventory` لليوم الحالي (عدّاد تراكمي — موثّق في note)

**الأداء:**
- `GET /owner/now` → 7 مقاييس في طلب واحد — نداءان DB فقط (income_statement + shifts)
- `GET /owner/performance` → 3 مقارنات في طلب واحد — 6 نداءات لـ `get_income_statement`
- كل رقم يحمل `period.is_provisional` — لا رقم provisional يُعرض كأنه نهائي

### المرحلة 4 — Owner PWA ✅
**الملفات في `frontend/apps/owner/`:**
- `src/views/NowScreen.vue` — شاشة "الآن" — 7 بطاقات مع sparklines
- `src/views/PerformanceScreen.vue` — شاشة الأداء — مقارنة 3 فترات
- `src/views/LoginView.vue` — تسجيل دخول مع 2FA
- `src/views/AppShell.vue` — shell مع bottom navigation
- `src/views/TwoFactorSetupView.vue` — إعداد TOTP
- `src/components/MetricCard.vue` — بطاقة مقياس: رقم كبير + sparkline + لون
- `src/components/SparkLine.vue` — رسم بياني SVG للاتجاه (7 أيام)
- `src/components/PeriodComparisonCard.vue` — بطاقة مقارنة فترتين مع delta
- `src/components/SkeletonCards.vue` + `ErrorState.vue` — loading/error states
- `src/router/index.ts` — يرفض أي session غير `owner`/`super_admin` client-side
- `src/composables/useOwnerData.ts` — جلب بيانات now+performance مع auto-refresh
- `src/composables/useFormat.ts` — تنسيق عملة/تاريخ/نسبة RTL
- `src/api/owner.ts` + `types.ts` — API client typed
- `vite.config.ts` — PWA (generateSW) + mobile viewport + Cache-Control: no-store
- `tailwind.config.js` — dark-first، touch targets 48×48px
- **Build:** `✓ built in 2.92s — 11 entries precached`

---

## قرارات محمد المسجّلة — لا تُعدَّل بدون إذنه الصريح

(محفوظة كاملة في `handoff-phase3-onwards.md` قرارات 1-6)

**ملخص:** `owner.elkheima.com` subdomain — cookie منفصلة SameSite=Strict — نفس دورة REL-XX — Documented live walkthrough (لا Playwright) — Vue+Vite+Tailwind+`@vueuse/core` فقط.

**ما يلزم قبل Phase 4 على VPS (عند القرار بالنشر):**
- إضافة DNS record + SSL cert + nginx config لـ `owner.elkheima.com`
- هذا لا يحدث إلا بعد Phase 10 وبإذن صريح من محمد

---

## المرحلة التالية — المرحلة 5 (توقف إلزامي)

**المرحلة 5: مراجعة الأرقام مع محمد على الهاتف الحقيقي**

هذه ليست مرحلة كود — هي human checkpoint إلزامي قبل أي شيء آخر.

**ما يجب أن يحدث:**
1. محمد يفتح الـ owner app على هاتفه (أو على staging لو أُعدّ)
2. يتحقق أن الأرقام السبعة على شاشة "الآن" صحيحة
3. يتحقق أن مقارنات الأداء منطقية
4. يعطي موافقة صريحة أن الأرقام صح قبل بناء أي طبقة إضافية

**لا تبدأ المرحلة 6 إلا بعد موافقة محمد الصريحة.**

---

## ما تبقّى من المراحل

| # | الاسم | الحالة | ملاحظة |
|---|---|---|---|
| **5** | مراجعة الأرقام مع محمد | **التالي — توقف إلزامي** | هاتف حقيقي — لا تتخطاها |
| 6 | تحليلات المبيعات/الشاطئ/القنوات/المشتريات/النفقات | بعد 5 | + `owner_analytics_engine.py` |
| 7 | مراقبة الورديات + موتور الاستثناءات | بعد 6 | ربط `fraud_tasks.py` |
| 8 | اقتصاديات الوحدة | بعد موافقة محمد | يتوقف على نشر قاعدة تخصيص حقيقية |
| 9 | Scenario sandbox | أدنى أولوية | |
| 10 | مراجعة أمنية مستقلة + بوابة الإنتاج | الأخير | قبل أي deploy على VPS |

---

## كيف تبدأ المرحلة 6 (بعد موافقة محمد في Phase 5)

اقرأ بالترتيب:
1. `AGENTS.md` + `CLAUDE.md` + `docs/decisions/0004-owner-intelligence-cockpit.md`
2. هذا الملف كاملاً
3. `docs/owner/kpi-contracts.md` — الـ groups B-E لم تُبنَ بعد

**ما تبنيه في المرحلة 6:**

**`app/resort_os/owner_analytics_engine.py`** — pure engine بدون FastAPI/SQLAlchemy:
- ABC/Pareto classification لـ items بـ `statistics` من stdlib
- per-item margin = (sale_price - recipe_cost) / sale_price × 100 بـ `Decimal`
- trend/variance detection بـ `statistics.mean` + `statistics.stdev`
- لا AI، لا external call، لا pandas/numpy

**Services جديدة:**
- Sales performance service — يعمّم `top_items` query في `dining/api/router.py` ليشمل beach ticket types
- Channel analytics service — `B2BContract` + beach transactions + dining orders → per-hotel aggregate F&B attach (لا guest data)
- Expense analytics service — كل expense category كنسبة من الإيراد عبر الزمن
- Procurement analytics service — spend concentration بـ supplier + price trend per product

**قواعد لا تتغير في المرحلة 6:**
- كل primary metric يُقرأ من مصدر الحقيقة مباشرةً — لا يُعاد حسابه
- لا guest name/phone/email في أي response
- لا payroll per employee — aggregate فقط
- branch_id دائماً من الـ session

---

## قواعد لا تُخترق

1. **لا AI/LLM** في أي مكان في owner module — نهائي بقرار محمد.
2. **لا deploy على VPS** في المراحل 5-9.
3. **لا commit** إلا بإذن صريح من محمد لكل commit بعينه.
4. **المرحلة 5 توقف إلزامي** — لا تبدأ المرحلة 6 إلا بعد تأكيد محمد.
5. **لا بيانات ضيف فردية** — B2B فقط per hotel/contract.
6. **لا payroll per employee** — aggregate فقط.
7. **كل phase تمر بـ:** `pytest tests/ -v` + `alembic heads` + `pnpm run type-check:all` قبل الإعلان عن اكتمالها.
