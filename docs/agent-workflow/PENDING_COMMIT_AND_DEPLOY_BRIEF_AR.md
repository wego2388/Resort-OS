# مهمة وكيل: Commit + Deploy تعديلات 2026-07-28/29

**تاريخ الإنشاء:** 2026-07-29
**المؤلف:** Kiro (مراجعة يدوية كاملة للتعديلات)
**الحالة:** ⏳ جاهز للتنفيذ — لم يُرفع بعد

---

## 📋 القراءة الإلزامية قبل أي خطوة

```
AGENTS.md          ← أولاً دايمًا
CLAUDE.md          ← الدستور الهندسي الكامل (§0–§18)
PROJECT_STATUS.md  ← آخر checkpoint
wagdy.md           ← أولويات Mohamed الحالية
docs/agent-workflow/CODEX_TO_CLAUDE_CONTINUATION_AR.md ← حالة VPS
```

**قاعدة صارمة من CLAUDE.md §3:** لا تُعدّل كود قبل القراءة الكاملة.
**قاعدة صارمة من AGENTS.md §1:** السلطة الأعلى = قرار المستخدم الصريح الحالي.

---

## 🎯 المهمة

التعديلات موجودة محلياً في `/home/wego/projects/resort-os` وغير مرفوعة على GitHub.
المطلوب: **commit → push → deploy على الـ VPS**.

لا يوجد تعارض مع الكود الحالي على `origin/main` — التعديلات كلها `modified` فقط
(لا `conflicts`) + 5 ملفات `untracked` جديدة.

---

## 🔍 ما تم فحصه واكتشافه (2026-07-29)

### البـاجـات المُصلَحة — 9 بـاجـات حقيقية موثّقة

#### 🔴 أمنية حرجة

**B-01: Branch Isolation مفقودة من 8 موديولات**
- الملفات: `beach/api/router.py`, `crm/api/router.py`, `finance/api/router.py`,
  `hub/api/router.py`, `inventory/api/router.py`, `leasing/api/router.py`,
  `maintenance/api/router.py`, `timeshare/api/router.py`
- الخطورة: أي موظف من أي فرع كان يقدر يقرأ ويعدّل بيانات فرع آخر بمجرد تخمين الـ ID
- الإصلاح: `_assert_*_branch()` helper في كل router يستدعي `core_services.assert_branch_access()`
- اتأكد: بريبرو حي — كاشير فرع B وصل لبيانات فرع A بنجاح قبل الإصلاح

**B-02: Finance — folio/branch_id من body الطلب (مش الـ path)**
- الملف: `finance/services.py → add_payment()`
- الخطورة: تحصيل دفعة على فوليو فرع مختلف عن المتحقق منه
- الإصلاح: `data = data.model_copy(update={"folio_id": folio_id, "branch_id": folio.branch_id})`

**B-03: Finance — إلغاء دفعة بيع مباشر عبر مسار خاطئ**
- الملف: `finance/services.py → void_payment()`
- الخطورة: رصيد "ذمم فوليو" وهمي والإيراد يفضل متضخّم لأجل غير مسمى
- الإصلاح: رفض صريح لو `payment.folio_id is None` مع رسالة توجيهية

#### 🔴 مالية حرجة (Race Conditions)

**B-04: Timeshare — Race Condition في تحصيل الأقساط**
- الملفات: `timeshare/services.py`, `timeshare/crud.py`
- الخطورة: كاشيرين يحصّلوا نفس القسط في نفس اللحظة → فلوس تختفي من الدفاتر بصمت
- الإصلاح: `_lock_installment_or_raise()` + `SELECT FOR UPDATE NOWAIT`
- اتأكد: بريبرو حي على حالتين منفصلتين قبل الإصلاح

**B-05: Leasing — نفس Race Condition في تحصيل الدفعات**
- الملفات: `leasing/services.py`, `leasing/crud.py`
- الإصلاح: `_lock_payment_or_raise()` + `SELECT FOR UPDATE NOWAIT`

**B-06: Maintenance — `add_part_to_wo` كانت 400 دايمًا (ثلاثة أخطاء)**
- الملف: `maintenance/services.py`
- الأخطاء: (1) `product.unit_cost` مش عمود موجود (الصح: `cost_price`)،
  (2) `movement_type="out"` غير موجود في الـ pattern،
  (3) `warehouse_id/moved_at` الإجباريين ناقصين
- الإصلاح: استبدال بـ `inv_svc.consume_stock()` (نفس دالة dining)

#### 🔴 مالية — فقدان بيانات

**B-07: Dining — `create_order` يطلع 500 خام عند التصادم**
- الملف: `dining/services.py → create_order()`
- الخطورة: `IntegrityError` من `db.flush()` داخل `create_order_with_items`
  كان يفجّر 500 لأن الـ `try/except` كان يلف `db.commit()` فقط
- الإصلاح: `try/except IntegrityError` يحيط `create_order_with_items` مباشرة
  + `_raise_order_integrity_error()` هلبر مشترك

**B-08: Leasing Tasks — دفعات `partial` و`overdue` مش بتتفحّص**
- الملف: `app/tasks/leasing_tasks.py`
- الخطورة: (1) دفعات جزئية التسديد تتجاهل للأبد بدون غرامة،
  (2) غرامة دفعة `overdue` تتجمّد على أول قيمة بدل ما تتصاعد مع الوقت
- الإصلاح: توسيع الفلتر لـ`(pending, partial, overdue)` +
  استخدام `leasing.services.calculate_penalty` (مصدر واحد للحساب)

**B-09: HR — صافي راتب يطلع سالب عند تعدد السلف**
- الملف: `hr/services.py → run_payroll_for_branch()`
- الخطورة: إجمالي خصم السلف مكانش له سقف → net_salary أقل من صفر
- الإصلاح: `_cap_advance_deductions()` بتوزيع ذكي: السلف أولاً (تخصيص جزئي)،
  الدفعات ثانياً (كاملة أو لا شيء)

---

### تحسينات الأداء — 3 مشاكل N+1

| الملف | المشكلة | الإصلاح |
|---|---|---|
| `dining/crud.py → list_orders()` | استعلام لكل طلب + لكل سطر | `selectinload(items).selectinload(extras)` |
| `leasing/crud.py → list_contracts()` | استعلام لكل عقد | `selectinload(payments)` |
| `hr/services.py → run_payroll_for_branch()` | 2×عدد الموظفين استعلام | تحميل مسبق مرة واحدة للفرع + `penalties_by_employee` dict |

---

### تشديد صلاحيات HR

| الـ endpoint | قبل | بعد | السبب |
|---|---|---|---|
| `GET /hr/employees/{id}` | `active_user` | `manager` | بيانات موظف حساسة |
| `POST /hr/leave-requests` | `active_user` | `manager` | المدير هو من يُدخل الطلب |
| `GET /hr/payroll/{run_id}/payslip/{id}` | `active_user` | `manager` | كشف راتب حساس |

---

### ملفات جديدة (untracked)

| الملف | الوصف |
|---|---|
| `backend/alembic/versions/88d1c505a9dc_encrypt_hub_online_bookings_guest_pii.py` | Migration تشفير PII لـ hub_online_bookings — يوسّع VARCHAR فقط (encryption على مستوى ORM) |
| `backend/tests/test_timeshare_leasing_concurrency.py` | اختبار Race Condition على Postgres حقيقي (يتخطى تلقائياً لو `DINING_CONCURRENCY_TEST_ADMIN_URL` مش موجود) |
| `deploy/nginx/edge-domain.conf` | Nginx config لـ elkheima.com (جاهز، لم يُفعَّل بعد) |
| `docker-compose.prod.domain.yml` | Docker Compose override للدومين (جاهز، لم يُفعَّل بعد) |
| `scripts/switch-to-domain.sh` | سكريبت تحويل كامل من IP-TLS لـ elkheima.com |

---

## ✅ خطوات التنفيذ (بالترتيب الصارم)

### الخطوة 1 — تحقق من حالة الـ worktree

```bash
cd /home/wego/projects/resort-os
git status
git diff --stat HEAD
```

**التوقع:** 42 ملف modified + 5 untracked. لو فيه أي شيء غير متوقع، أوقف وبلّغ.

---

### الخطوة 2 — تشغيل التيستات محلياً

```bash
cd /home/wego/projects/resort-os/backend
source .venv/bin/activate
pytest tests/ -x -q --timeout=60 2>&1 | tail -30
```

**التوقع:** كل التيستات تعدي. لو فيه فشل:
- افهم السبب أولاً — هل هو مرتبط بالتعديلات؟
- لا تعمل commit على كود فيه تيستات فاشلة
- بلّغ بالفشل قبل ما تكمّل

---

### الخطوة 3 — Commit

```bash
cd /home/wego/projects/resort-os
git add -A
git commit -m "fix(security+finance+perf): branch isolation ×8 modules, payment race locks (timeshare+leasing), HR payroll cap, dining integrity error, leasing tasks partial/overdue, maintenance consume_stock, N+1 fixes ×3, HR permission tightening, hub PII encryption migration"
```

**قواعد من AGENTS.md:**
- لا تستخدم `--no-verify` (تحترم الـ hooks)
- الـ commit message صريح ومبرر
- لا `git add .` بدون مراجعة — استخدم `git add -A` بعد `git status`

---

### الخطوة 4 — Push

```bash
git push origin main
```

**التوقع:** يمشي بدون مشاكل — الـ remote اتحدّث آخر مرة بـ `0a13c97` وما فيش
commits جديدة عليه من وقتها.

لو فيه `rejected`:
```bash
git fetch origin main
git log --oneline origin/main -5
# افهم الفرق ثم بلّغ — لا تعمل force push
```

---

### الخطوة 5 — Deploy على الـ VPS

```bash
# من الجهاز المحلي:
ssh resort-os-vps "cd /opt/resort-os && bash scripts/deploy.sh"
```

**ما يعمله `deploy.sh` تلقائياً:**
1. ✅ Backup للـ DB قبل أي شيء
2. ✅ `git fetch` + `git merge --ff-only` (fast-forward فقط)
3. ✅ `python3 scripts/validate_prod_env.py` (فحص `.env.prod`)
4. ✅ `docker compose build --parallel`
5. ✅ `alembic upgrade head` (يطبّق migration الـ PII الجديد)
6. ✅ `docker compose up -d`
7. ✅ Health check على `http://127.0.0.1:8005/health`

**ملاحظة مهمة:** السكريبت يتطلب worktree نضيف (committed) على `origin/main` — ولهذا الخطوة 3 و4 لازم تكون خلصت أولاً.

---

### الخطوة 6 — تحقق من نجاح الـ Deploy

```bash
ssh resort-os-vps "
  cd /opt/resort-os

  echo '=== Container Status ==='
  docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml ps

  echo '=== Health Check ==='
  curl -fsS https://191.218.161.133/health | python3 -m json.tool

  echo '=== Migration Status ==='
  docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml \
    run --rm backend alembic current

  echo '=== Last 20 Backend Logs ==='
  docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml \
    logs backend --tail=20
"
```

**علامات النجاح:**
- كل الـ containers: `Up (healthy)`
- Health: `{"status": "ok", "database": {"status": "ok"}, "redis": {"status": "ok"}}`
- Alembic current: `88d1c505a9dc (head)` ← Migration الـ PII الجديد
- لوجات Backend: بدون أي `ERROR` جديد

---

### الخطوة 7 — تحقق من الـ Migration

```bash
ssh resort-os-vps "
  docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml \
    exec db_postgres psql -U postgres -d resort_os -c \
    \"SELECT column_name, character_maximum_length
      FROM information_schema.columns
      WHERE table_name='hub_online_bookings'
        AND column_name IN ('guest_name','guest_phone','guest_email');\"
"
```

**التوقع:**
```
 column_name  | character_maximum_length
--------------+--------------------------
 guest_email  |      512
 guest_name   |      512
 guest_phone  |      255
```

لو الأطوال لسه 200/20/150 → الـ migration ما اتطبّقش. بلّغ فوراً.

---

## ⚠️ تعليمات احترازية مهمة

### ما لا تفعله
- ❌ لا تعمل `git push --force` مهما كان
- ❌ لا تعمل `docker compose down -v` (يحذف الـ volumes والـ database)
- ❌ لا تعدّل `backend/.env.prod` على الـ VPS إلا لو التعليمات صريحة
- ❌ لا تشغّل `app.seed` على production (بيانات تجريبية وهمية)
- ❌ لا تحذف backup موجود في `/opt/resort-os/backups/`
- ❌ لا تشغّل migration مباشرة بـ `psql` — استخدم `alembic upgrade head` دايمًا

### لو فشل الـ Deploy
```bash
# 1. شوف اللوجات
ssh resort-os-vps "cd /opt/resort-os && \
  docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml \
  logs backend --tail=50"

# 2. لو فيه مشكلة في الـ migration، رجعه
ssh resort-os-vps "cd /opt/resort-os && \
  docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml \
  run --rm backend alembic downgrade -1"

# 3. لو محتاج restore DB (آخر backup)
ssh resort-os-vps "cd /opt/resort-os && \
  ls -lt backups/*.dump | head -3"
# ثم استشر المستخدم قبل أي restore
```

---

## 📊 ملخص الـ Migration الجديد

**`88d1c505a9dc_encrypt_hub_online_bookings_guest_pii`**

```
down_revision: c4d8e2f6a901
operation: ALTER COLUMN (VARCHAR width only — no data migration)

hub_online_bookings:
  guest_name:  200 → 512  (Fernet ciphertext أطول من plaintext)
  guest_phone:  20 → 255  (Fernet ciphertext أطول بكتير من رقم تليفون)
  guest_email: 150 → 512  (Fernet ciphertext أطول من email)

ملاحظة: الـ encryption نفسه على مستوى ORM (EncryptedString TypeDecorator)
— الـ DDL بيوسّع VARCHAR فقط. البيانات القديمة (plaintext) ستبقى
plaintext في الـ DB والـ ORM سيقرأها صح تلقائياً (TypeDecorator
بيتعامل مع كلاهما).
```

---

## 🗺️ ما بعد الـ Deploy — مهام مستقبلية (ليست جزءاً من هذه المهمة)

1. **ربط elkheima.com**: بعد إضافة DNS Zone في Hostinger →
   `ssh resort-os-vps "bash scripts/switch-to-domain.sh"`

2. **تشفير بيانات hub_online_bookings القديمة**: البيانات الحالية في الـ DB
   plaintext، المطلوب migration يُشفّرها (مهمة منفصلة — تحتاج script مؤمّن
   + approval من Mohamed + backup مُتحقَّق منه)

3. **اختبار Race Condition على Postgres حقيقي**:
   ```bash
   DINING_CONCURRENCY_TEST_ADMIN_URL=postgresql+psycopg://postgres:<pass>@localhost:5436/postgres \
     pytest backend/tests/test_timeshare_leasing_concurrency.py -v
   ```

---

## 🔗 مراجع سريعة للـ VPS

```
SSH:       ssh resort-os-vps
           أو: ssh -i ~/.ssh/id_ed25519 resortos@191.218.161.133
Project:   /opt/resort-os
Marketing: /opt/elkheima-marketing-website
Compose:   docker compose -f docker-compose.prod.yml -f docker-compose.prod.ip-tls.yml
Health:    https://191.218.161.133/health
Staff App: https://191.218.161.133/
Public:    https://191.218.161.133:8443/
```

---

*الملف ده مكتوب بعد مراجعة يدوية كاملة لكل `git diff` — كل باج موثّق بالملف والسطر والسبب
الجذري والإصلاح. أي وكيل يكمّل من هنا لازم يقرأ القراءة الإلزامية في الأعلى أولاً.*
