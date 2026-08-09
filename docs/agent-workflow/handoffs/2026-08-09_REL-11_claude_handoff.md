# Handoff — REL-11: Security/N+1/accounting hardening + real journal entries admin view

**Date:** 2026-08-09
**Agent:** Claude
**Commit:** `92aa769` — resort-os (`claude/CX-02C-frontend-auth-bootstrap`)
**Status:** Deployed to production, verified

---

## ما اتعمل

دفعة إصلاحات من جولة المراجعة النهائية قبل الإطلاق، بإذن صريح من محمد
("راجع انت و اعملي كوميت و ارفع علي الفي بي اس"):

1. **أمان — فجوة حقيقية في `/ops`**: الراوت الأب (استقبال/غرف/حجوزات/
   تدبير منزلي) كان `meta: { requiresAuth: true, requiresBranch: true }`
   فقط — من غير أي `requiredRole`. الحماية الوحيدة كانت
   `requiredPermission` على كل شاشة فرعية. موظف/نادل (level 20/30)
   اتعطاله permission غلط بالخطأ كان يقدر يوصل للاستقبال كاملة. اتضاف
   `requiredRole: 'receptionist'` (level 40) كطبقة دفاع تانية.

2. **N+1 queries**: `inventory.list_purchase_orders/list_purchase_requests/
   list_stock_counts`، `maintenance.list_work_orders`،
   `finance.list_journal_entries` — كلهم بقوا يستخدموا `selectinload`
   بدل lazy-load متكرر. `pms.create_booking` كان بيعيد نداء
   `get_available_rooms`/`get_room_type` لكل غرفة في الحجز (نفس
   الاستعلام بالظبط N مرة) وبيعيد `get_room` تاني في نهاية الدالة رغم
   إن الصف نفسه متقفول ومتاح بالفعل في `locked_rooms` — اتصلحوا الكل.

3. **قفل PMS**: `lock_room_for_booking` كان ناقص `.populate_existing()`
   — نفس فئة الباج الموثّقة في CLAUDE.md §13⓫ (SELECT FOR UPDATE NOWAIT
   من غير populate_existing ممكن يسيب lost update تحت ضغط فعلي).

4. **صمت محاسبي**: `finance.post_simple_revenue_journal` (الدالة
   المشتركة اللي 6 موديولات بترحّل بيها) كانت بتبتلع 3 أنواع فشل (حساب
   مش معرّف، فشل تحويل عملة، استثناء غير متوقع) وترجع `None` بصمت —
   صفر log. اتضاف `logger.error`/`logger.exception` على المسارات
   التلاتة، من غير ما يتغيّر سلوك `strict=False` نفسه (العملية
   التشغيلية لازم تكمل، بس دلوقتي الفشل ظاهر في اللوج).

5. **دفتر اليومية — تاب إداري حقيقي** (كان اتبدأ قبل كده في نفس
   الجلسة، اتكمل ومراجعته هنا): تاب جديد في `FinanceView.vue` بيقرا
   `GET /finance/journal-entries` (مدير+) — فلترة تاريخ/مصدر، صفوف
   قابلة للطي بتعرض كل سطر مدين/دائن والإجمالي. **باج حقيقي اتكشف
   واتصلح أثناء المراجعة**: `JournalLineRead` schema مكانش فيه
   `account_code`/`account_name` خالص (بس `account_id`) رغم إن الشاشة
   بترسمهم مباشرة من غير أي join تاني — عمود "الحساب" كان هيفضل فاضي
   لكل سطر في كل قيد، دايمًا. اتضاف `@model_validator(mode="before")`
   (نفس نمط `dining.DiningItemRead._inject_recipe_fields`) بيقرا من
   الـ`account` relationship + `selectinload(JournalEntry.lines).
   selectinload(JournalLine.account)` في الـcrud (وإلا N+1 جديد). كمان
   اتكشف مفتاحين i18n مكررين بالغلط (`tabs`, `refresh` ظاهرين مرتين
   جوه نفس كائن `finance` في `ar.json`/`en.json` — JSON duplicate key،
   آخر واحد بيكسب بصمت) ومفتاح `loadJournalError` غلط (الكومبوننت كان
   بينادي مفتاح مختلف عن الموجود فعليًا في الـi18n) — اكتشفه
   `validate-i18n.mjs` نفسه فعليًا وقت `pnpm test:frontend`، مش تخمين.

6. **موثّق، مش مُصلَح**: فجوة محاسبية حقيقية في تسوية checkout الـPMS —
   `_post_checkout_journal` بيسوّي رصيد 1150 بمبلغ `booking.total_rate`
   (سعر الغرفة بس)، مش `Folio.total` (اللي بيشمل أي "شحن على حساب
   الغرفة" من الشاطئ/الدايننج). النتيجة: أي شحنات إضافية بتفضل قايمة
   على 1150 للأبد بعد الـcheckout، بصمت. اتوثّقت بالتفصيل في
   `PROJECT_STATUS.md` §8.1 — قرار سياسة التسوية لازم يرجع لمحمد، مش
   قرار هندسي منفرد.

**لا migration** — Alembic head `d0e1f2a3b4c5` بدون تغيير.

---

## Validation ✅ (محلي، قبل أي نشر)

```
cd backend && .venv/bin/pytest tests/ -q       → 100% (صفر F/E)، exit 0
cd backend && .venv/bin/alembic heads          → d0e1f2a3b4c5 (head)
bash scripts/agent-check.sh                    → PASS بالكامل
git diff --check                               → نظيف

cd frontend
pnpm run type-check:all                        → نضاف (el-kheima + owner)
pnpm --filter el-kheima test:frontend           → 95 اختبار عدّوا +
                                                   i18n validator نظيف
                                                   (بعد إصلاح المفتاح الغلط)
VITE_PUBLIC_SITE_URL=https://elkheima.com \
  pnpm --filter el-kheima build                 → نجح (نفس قيمة الإنتاج
                                                   الحقيقية، اتأكد محليًا
                                                   بدل الاعتماد على بناء
                                                   الـDocker بس)
docker compose config --quiet                   → PASS
```

---

## خطوات النشر المنفَّذة (DEPLOYMENT.md §5)

نطاق backend + el-kheima frontend — `marketing_site`/`owner` متلمسوش
خالص، برّه نطاق هذه الدفعة.

```
COMMIT=92aa769
git archive → sha256 90e5445d... → scp → verify checksum على الـVPS
  (مطابق تمامًا)
extract → /opt/resort-os-releases/92aa769 (جديد)
نسخ backend/.env.prod من الإصدار الفعّال (eda6617) بصلاحية 0600
python3 scripts/validate_prod_env.py → passed
tag rollback images لكل الـ6 خدمات → pre-92aa769
  (منفَّذ في /var/backups/resort-os/source-releases/92aa769-rollback-images.txt)
pre-release DB backup → resort_os_20260809_115233.dump (620K)
  اتحقق منه فعليًا: docker cp للحاوية → pg_restore --list →
  1472 TOC entry، Format: CUSTOM — أرشيف صالح
  (ملاحظة تنفيذية: BACKUP_DIR الافتراضي بتاع backup_db.sh بيحاول ينشئ
  backups/ جوه working dir السكريبت، اللي resortos user معهوش صلاحية
  كتابة فيه جوه /opt/resort-os-current — استُخدم BACKUP_DIR=/var/backups/
  resort-os صراحةً بدل الافتراضي، نفس القيمة المستخدمة في
  resort-os-backup.service الفعلي)
docker compose build backend celery_worker celery_beat el_kheima → نجح
preflight: python -c 'from app.main import app; print(app.title)' → El Kheima Beach
alembic heads/upgrade head → d0e1f2a3b4c5 (head)، لا migration
staged replacement (كل مرحلة اتأكد منها healthy قبل التالية):
  up -d --no-deps backend                → healthy خلال ~35 ثانية
  up -d --no-deps celery_worker celery_beat → healthy خلال ~6 ثواني
  up -d --no-deps el_kheima               → healthy فورًا
  up -d --no-deps --force-recreate nginx  → up
ln -sfn /opt/resort-os-releases/92aa769 /opt/resort-os-current
```

---

## Post-deploy acceptance ✅

```
docker ps → كل الحاويات المستبدلة healthy، صفر restart
curl -fsSI https://elkheima.com/        → HTTP/2 200
curl -fsSI https://www.elkheima.com/    → HTTP/2 200
curl -fsSI https://app.elkheima.com/    → HTTP/2 200
curl -fsS  https://app.elkheima.com/health
  → {"status":"ok", database: ok (1.7ms), redis: ok (1.3ms)}
working_dir label (backend + el_kheima) = /opt/resort-os-releases/92aa769  ✅
RestartCount = 0 لكل الخدمات المستبدلة                                     ✅
TLS SAN = app.elkheima.com, elkheima.com, owner.elkheima.com, www.elkheima.com ✅
DB/Redis loopback-only (127.0.0.1:5436 / 127.0.0.1:6381) — بدون تغيير      ✅
alembic current = d0e1f2a3b4c5 (head)                                      ✅
DB sanity: users=5, branches=1 — نفس البيانات الحقيقية                     ✅
GET /api/v1/finance/journal-entries بدون توكن → 401 (مسار جديد حي ومحمي)   ✅
backend/celery_worker/nginx/el_kheima logs → صفر traceback/critical/fatal  ✅
مفيش قاعدة بيانات استرجاع مؤقتة اتسابت                                     ✅
```

**تأكيد إضافي غير مخطَّط**: أثناء النشر كان فيه جلسة مستخدم حقيقية شغالة
فعليًا (WebSocket alerts/shifts) — استمرت من غير انقطاع ملحوظ في اللوج
أثناء استبدال حاوية backend.

---

## Rollback (لو حاجة وحشت)

```bash
docker tag resort-os-rollback/backend:pre-92aa769 \
  resort-os-prod-backend:latest
docker tag resort-os-rollback/celery-worker:pre-92aa769 \
  resort-os-prod-celery_worker:latest
docker tag resort-os-rollback/celery-beat:pre-92aa769 \
  resort-os-prod-celery_beat:latest
docker tag resort-os-rollback/el-kheima:pre-92aa769 \
  resort-os-prod-el_kheima:latest
docker tag resort-os-rollback/nginx:pre-92aa769 \
  resort-os-prod-nginx:latest

cd /opt/resort-os-releases/eda6617
# (نفس نمط استخراج DB_PASSWORD ثم)
docker compose --env-file backend/.env.prod \
  -f docker-compose.prod.yml -f docker-compose.prod.domain.yml \
  up -d --no-deps backend celery_worker celery_beat el_kheima nginx

sudo ln -sfn /opt/resort-os-releases/eda6617 /opt/resort-os-current
```

---

## ملاحظات

- **لا migration** — Alembic head بدون تغيير (`d0e1f2a3b4c5`).
- **`marketing_site`/`owner` متلمسوش خالص** — صفر تعديل كود في نطاقهم
  في هذه الدفعة.
- فجوة محاسبية موثّقة (checkout/folio) **لسه محتاجة قرار محمد** — راجع
  `PROJECT_STATUS.md` §8.1. مفيش backfill رجعي مقترح.
- قائمة UI مؤجَّلة (Rota screen، إغلاق فترة محاسبية UI، barcode labels،
  fraud task visibility، i18n validation عامة) موثّقة في
  `PROJECT_STATUS.md` §8.2 — أولوية §2 #2، مش bug.
