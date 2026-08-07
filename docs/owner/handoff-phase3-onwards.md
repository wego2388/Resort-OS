# Owner Intelligence Cockpit — Handoff للمرحلة 3+

**تاريخ:** 2026-08-07
**الفرع الحالي:** `claude/CX-02C-frontend-auth-bootstrap`
**آخر Alembic head:** `f8aa1f0fabba` (owner_module_phase2_and_pr_po_linkage — مطبّق ✅)
**Tests:** 2355 passed, 42 skipped — صفر فشل
**قائد التنفيذ والمراجع النهائي:** Codex

---

## ما اكتمل (لا تعيد بناءه)

### المرحلة 1 — عقود المقاييس ✅
الوثيقة الكاملة: `docs/owner/kpi-contracts.md`
- كل مقياس له: مصدر الحقيقة، الصيغة، الفترة، حالة الاكتمال، مسار الـ drill-down
- قرار مسجّل: ذمم B2B وتايم شير تُعرض كـ buckets منفصلة (ليس مجموعاً واحداً)

### المرحلة 2 — العزل والأمان ✅

**الملفات المعدّلة:**
- `backend/app/core/deps.py` — `owner` role بـ level=10، `get_owner_reader`، `owner` في `MANDATORY_2FA_ROLES`
- `frontend/packages/core/src/stores/auth.ts` — `owner: 10` في `ROLE_LEVELS` (متطابق مع backend)
- `backend/app/modules/owner/owner_policy.py` — طبقة حظر الكتابة المركزية (allowlist fail-closed)
- `backend/app/modules/owner/models.py` — `OwnerWatchlist` + `OwnerAllocationRule`
- `backend/app/modules/owner/schemas.py` — Pydantic schemas
- `backend/app/modules/owner/crud.py` — DB operations
- `backend/app/modules/owner/services.py` — Business logic
- `backend/app/modules/owner/api/router.py` — Watchlist + draft endpoints
- `backend/app/main.py` — `owner` في `_MODULE_KEYS`
- `backend/alembic/env.py` — import `owner.models`
- `backend/alembic/versions/f8aa1f0fabba_owner_module_phase2_and_pr_po_linkage.py` — Migration
- `backend/app/modules/inventory/models.py` — `source_request_id` على `PurchaseOrder`
- `backend/app/modules/inventory/services.py` — `convert_to_purchase_order` يخزّن `source_request_id`
- `backend/tests/conftest.py` — import `owner.models` في `create_all_tables`
- `backend/tests/test_owner_phase2.py` — 13 test ✅

**الضمانات المؤكدة باختبارات:**
- `owner` (level=10) لا يمر من أي gate موجود (waiter=30، cashier=40، manager=60...)
- `cashier` مرفوض صراحةً من `get_owner_reader` رغم مستواه الأعلى
- `manager` مرفوض صراحةً من `get_owner_reader`
- `super_admin` يعدي دائماً (Decision 0003 invariant #1)
- `activate_owner_allocation_rule` غائب من الـ allowlist — لا يمكن تفعيل قاعدة تخصيص بدون super_admin/accountant
- Migration downgrade/upgrade اختُبر على Postgres حقيقي ✅

---

## قرارات محمد المسجّلة (2026-08-07) — لا تُعدَّل بدون إذنه الصريح

### قرار 1 — موقع الـ Owner PWA
**القرار:** `frontend/apps/owner` جوه الـ monorepo (مش مستودع مستقل).

**السبب:** نفس الـ codebase = أمان أقوى (get_owner_reader في نفس المكان)، يشارك `@resort-os/core` بدون duplication، نفس دورة deploy بدون sync يدوي بين مستودعين.

### قرار 2 — الدومين
**القرار:** `owner.elkheima.com` — subdomain مستقل.

**السبب:** cookie isolation، CSP منفصل، لو الـ owner app اتاختُرقت لا تأثر على `app.elkheima.com`.

**ما يلزم قبل Phase 4:** إضافة DNS record + SSL cert + nginx config لـ `owner.elkheima.com` على الـ VPS.

### قرار 3 — Cookie/token scope
**القرار:** Cookie منفصلة على `.elkheima.com` مع `SameSite=Strict`.

**السبب:** يمنع أي cross-app token reuse.

### قرار 4 — Deploy policy
**القرار:** نفس دورة REL-XX لكن الـ owner frontend كـ service منفصل في `docker-compose`.

**السبب:** deploy واحد، rollback واحد، لكن container مستقل.

### قرار 5 — UI verification method
**القرار:** Documented live walkthrough — نفس نمط `el-kheima`.

**السبب:** Playwright مش dependency معلن في الـ repo ولا يُضاف بدون قرار صريح منفصل.

### قرار 6 — Mobile UX approach
**القرار:** Vue + Vite + Tailwind بدون Ionic أو Quasar، مع إضافة `@vueuse/core` كـ dependency في `apps/owner` فقط.

**السبب:** الـ owner app بسيطة (شاشات قراءة)، dependency ضخم مش مبرر. `@vueuse/core` موثوق، tree-shakeable، بيديك `useSwipe` + `useIntersectionObserver` بدون أي overhead.

**القرارات التقنية المعتمدة للـ mobile feel:**
- Minimum touch target 48×48px على كل عنصر تفاعلي
- `touch-action: pan-y` + `overscroll-behavior: contain` على كل card
- `env(safe-area-inset-top/bottom)` للـ iPhone notch/Dynamic Island
- Swipe للتنقل بين الفترات بـ `useSwipe` من `@vueuse/core`
- Pull-to-refresh بـ `useSwipe` (direction=down + scrollTop=0)
- `content-visibility: auto` على cards تحت الـ fold
- `prefers-color-scheme: dark` كـ default (مش toggle)
- `navigator.vibrate?.(10)` على الـ actions المهمة
- Bottom navigation (مش top) — الإبهام يوصلها بسهولة
- رقم واحد كبير لكل بطاقة + sparkline 7 أيام + لون يحكي القصة قبل القراءة

---

## ما تبقّى من المراحل

| # | الاسم | الحالة | ملاحظة |
|---|---|---|---|
| 3 | Aggregation APIs | **التالي** | `/owner/now` + `/owner/performance` — استدعاء دوال موجودة |
| 4 | Owner PWA | بعد 3 | `frontend/apps/owner` — موبايل، dark، بطاقات، sparklines |
| 5 | مراجعة الأرقام مع محمد | توقف إلزامي | هاتف حقيقي — لا تتخطاها |
| 6 | تحليلات المبيعات/الشاطئ/القنوات/المشتريات/النفقات | بعد 5 | + `owner_analytics_engine.py` |
| 7 | مراقبة الورديات + موتور الاستثناءات | بعد 6 | ربط `fraud_tasks.py` |
| 8 | اقتصاديات الوحدة | بعد موافقة محمد | يتوقف على نشر قاعدة تخصيص حقيقية |
| 9 | Scenario sandbox | أدنى أولوية | |
| 10 | مراجعة أمنية مستقلة + بوابة الإنتاج | الأخير | قبل أي deploy على VPS |

---

## قواعد لا تُخترق (من Decision 0004)

1. **لا AI/LLM في أي مكان في owner module** — لا chat، لا Gemini، لا free-text endpoint. هذا محسوم ونهائي بقرار محمد.
2. **لا deploy على VPS** في المراحل 3-9. الـ deploy فقط بعد Phase 10 وبإذن صريح من محمد.
3. **لا commit** إلا بإذن صريح من محمد لكل commit بعينه.
4. **المرحلة 5 توقف إلزامي** — لا تبدأ المرحلة 6 إلا بعد تأكيد محمد أن الأرقام صحيحة على هاتفه الحقيقي.
5. **لا بيانات ضيف فردية** على أي شاشة owner — B2B فقط per hotel/contract.
6. **لا payroll per employee** — aggregate فقط.
7. **كل phase تمر بـ:** `pytest tests/ -v` + `alembic heads` + `pnpm run type-check:all` قبل الإعلان عن اكتمالها.

---

## كيف تبدأ المرحلة 3

اقرأ بالترتيب:
1. `AGENTS.md` + `CLAUDE.md` + `docs/decisions/0003-super-admin-control-plane.md` + `docs/decisions/0004-owner-intelligence-cockpit.md`
2. هذا الملف كاملاً
3. `docs/owner/kpi-contracts.md` — مصدر الحقيقة لكل مقياس ستبنيه

**النقطة الأولى في المرحلة 3:**
- `GET /api/v1/owner/now` — يعيد: إيراد اليوم (A-1)، كاش الأدراج (A-2)، مصروفات اليوم (A-3)، ذمم B2B (A-4)، ذمم تايم شير (A-5)، إشغال الغرف الآن (A-6)، سعة الشاطئ اليوم (A-7).
- `GET /api/v1/owner/performance` — مقارنة فترات: اليوم vs أمس، الأسبوع vs الأسبوع الماضي، الشهر vs الشهر الماضي.

**مصادر البيانات جاهزة — لا تعيد بناء أي دالة موجودة:**
- إيراد/مصروفات: `finance.services.get_income_statement(db, branch_id, date_from, date_to)`
- كاش الأدراج: `finance.services.build_active_shifts_response(db, branch_id)`
- ذمم B2B: `beach.models.B2BContract` + `B2BContractDay`
- ذمم تايم شير: `timeshare.models.TimeshareInstallment`
- إشغال الغرف: `pms.models.Room` حيث `status='occupied'`
- سعة الشاطئ: `beach.models.BeachInventory`

**branch_id:** يُشتق دائماً من الـ session server-side — لا يُقبل من الـ client أبداً.

**كل رقم يحمل:**
- `period` — الفترة التي يغطيها
- `is_provisional` — هل الفترة مفتوحة أم مقفولة (من `finance.models.AccountingPeriod`)
- `computed_at` — timestamp الحساب

**لا تعرض رقماً provisional كأنه نهائي.**
