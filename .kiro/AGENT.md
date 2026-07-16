# Resort OS — دليل الوكيل السريع
> اقرأ هذا الملف أولاً قبل أي عمل. يعطيك صورة كاملة في 5 دقائق.
> للتفاصيل الكاملة: `CLAUDE.md` | للحالة التشغيلية: `PROJECT_STATUS.md` | للتايم شير: `TIMESHARE_STATUS.md`

---

## 1. ما هو هذا المشروع؟

**El Kheima Beach Resort OS** — نظام تشغيل كامل لمنتجع شاطئي حقيقي في مصر.
ليس MVP ولا demo — نظام إنتاج يُستخدم يومياً.

**صاحب المشروع:** Mohamed (wagdy)
**أولوياته:** جودة الكود > استقرار الموديولات الموجودة > ميزات جديدة

---

## 2. التكنولوجيا

| الطبقة | التقنيات |
|--------|---------|
| Backend | FastAPI + PostgreSQL + SQLAlchemy + Alembic + Celery + Redis |
| Frontend | Vue 3 + TypeScript + Pinia + TailwindCSS (pnpm monorepo) |
| Auth | JWT + Refresh Token + 2FA (إلزامي لـ super_admin, accountant) |
| Python env | `/home/wego/projects/resort-os/backend/.venv/bin/python3` |
| Build | `pnpm --filter el-kheima build` |

---

## 3. هيكل المشروع

```
resort-os/
├── backend/
│   ├── app/
│   │   ├── core/              ← Auth, DB, config, deps.py (ROLE_LEVELS هنا)
│   │   ├── modules/           ← كل موديول: models/schemas/crud/services/api/router.py
│   │   │   ├── core/          ← Users, Branches, Permissions, Notifications
│   │   │   ├── timeshare/     ← نظام التايم شير الكامل ⭐
│   │   │   ├── pms/           ← Property Management (غرف + حجوزات)
│   │   │   ├── finance/       ← محاسبة + ورديات + فواتير
│   │   │   ├── restaurant/    ← مطعم + KDS
│   │   │   ├── cafe/          ← كافيه
│   │   │   ├── beach/         ← شاطئ
│   │   │   ├── hr/            ← موارد بشرية + رواتب + إجازات
│   │   │   ├── inventory/     ← مخزون
│   │   │   ├── crm/           ← إدارة العملاء
│   │   │   ├── analytics/     ← تحليلات + استبيانات رضا
│   │   │   ├── leasing/       ← عقود إيجار تجاري
│   │   │   └── maintenance/   ← صيانة
│   │   ├── resort_os/         ← Pure domain logic (timeshare_engine, timezone_utils...)
│   │   └── tasks/             ← Celery tasks (timeshare_tasks, inventory_tasks...)
│   └── .venv/                 ← البيئة الافتراضية
│
├── frontend/
│   ├── packages/
│   │   ├── core/              ← api client, useAuthStore, i18n
│   │   └── ui/                ← AppCard, AppButton, AppModal, AppBadge, useToast...
│   └── apps/
│       ├── el-kheima/         ← الواجهة الرئيسية للموظفين (port 3001)
│       │   └── src/views/admin/
│       │       ├── TimeshareView.vue    ← التايم شير ⭐ (~1200 سطر)
│       │       ├── PermissionsView.vue ← إدارة الصلاحيات
│       │       ├── FinanceView.vue
│       │       └── ...
│       └── public/            ← بوابة الضيوف (port 3002)
│
├── CLAUDE.md          ← الدستور الهندسي الكامل — اقرأه للعمق
├── PROJECT_STATUS.md  ← حالة كل موديول
├── TIMESHARE_STATUS.md← التايم شير: كل endpoint + باجات + قرارات معمارية
└── wagdy.md           ← خارطة الطريق والمهام
```

---

## 4. نظام الصلاحيات — مهم جداً

```
ROLE_LEVELS (deps.py):
  super_admin=100 | admin=80 | accountant=70 | hr_manager=70
  manager=60 | supervisor=50 | receptionist=40 | cashier=40
  waiter=30 | chef=30 | kitchen=30
  timeshare_agent=25   ← جديد — للتايم شير فقط بـ UserPermission صريح
  employee=20 | customer=0 | guest=0

طبقتان:
  1. Role Level:   get_manager_user (≥60), get_cashier_user (≥40), get_timeshare_user (≥25+permission)
  2. Permission Matrix: UserPermission — منح/منع صريح لـ resource.action لمستخدم بعينه
                        يكسب الـ role تماماً — راجع require_permission() في deps.py

صلاحيات التايم شير في permission_catalog.py:
  timeshare.access/view         ← إلزامي لـ timeshare_agent (بوابة get_timeshare_user)
  timeshare.contracts/view      | timeshare.contracts/create  | timeshare.contracts/edit
  timeshare.installments/view   | timeshare.installments/collect
  timeshare.visits/view         | timeshare.visits/create     | timeshare.visits/edit
  timeshare.calendar/view       | timeshare.waitlist/view     | timeshare.waitlist/create
```

---

## 5. التايم شير — الوضع الحالي ⭐

**مكتمل 100%** — لا نواقص تشغيلية متبقية.

### ما يشتغل:
- 23 endpoint (عقود/أقساط/زيارات/كالندر/وحدات/قائمة انتظار/تقارير)
- Frontend: 8 تابات (داشبورد/مبيعات/كالندر/عملاء/أقساط/زيارات/انتظار/إحصائيات)
- Celery tasks: تذكيرات واتساب + علامة متأخر + تجميد الحجز
- محاسبة: Dr.1100/Cr.4600 على كل دفعة
- صلاحيات: `timeshare_agent` role + permission matrix

### قرار معماري معلّق (يحتاج موافقة Mohamed):
`TimeshareVisit.booking_id` → ربط بالـ PMS أو لا؟ لا تنفّذ من غير موافقة.

---

## 6. القواعد الذهبية — لازم تحفظها

```
① اقرأ الكود المحيط قبل أي تعديل — لا تخمن، تحقق
② لا تخترق الـ layering: router ← service ← crud ← model
③ الأموال = Decimal دايماً، مش float
④ PII (رقم هوية/جواز) = EncryptedString في الـ model
⑤ كل تغيير DB = migration جديدة بـ alembic
⑥ كل تغيير backend = تحقق من frontend types/stores أيضاً
⑦ قبل ما تنشئ = ابحث لو الكود موجود في core/ أو resort_os/
⑧ Finance First: كل دفعة لازم عندها قيد يومية (راجع CLAUDE.md §9.2)
⑨ لا race condition في الحجوزات: استخدم SELECT FOR UPDATE NOWAIT
⑩ الوقت دايماً = business_today(settings.TIMEZONE) من resort_os/timezone_utils
```

---

## 7. أوامر مفيدة

```bash
# تشغيل الـ backend
cd /home/wego/projects/resort-os && ./scripts/start.sh

# build الـ frontend
cd /home/wego/projects/resort-os/frontend && pnpm --filter el-kheima build

# TypeScript check
cd /home/wego/projects/resort-os/frontend/apps/el-kheima && npx vue-tsc --noEmit

# تشغيل الـ tests
cd /home/wego/projects/resort-os/backend && .venv/bin/pytest tests/ -v

# تشغيل test محدد
.venv/bin/pytest tests/test_api/test_timeshare_calendar_visits.py -v

# alembic migration
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "description"

# Python interpreter
/home/wego/projects/resort-os/backend/.venv/bin/python3

# status النظام
./scripts/status.sh
```

---

## 8. أنماط الكود — اتبعها

### Backend
```python
# ✅ صح — service يرمي ValueError، router يترجمها
def create_contract(db, data):
    if not valid:
        raise ValueError("رسالة عربية واضحة")

@router.post("/timeshare/contracts")
def endpoint(db: DbDep, _=Depends(get_timeshare_user)):
    try:
        return services.create_contract(db, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

# ✅ صح — Decimal للمال
from decimal import Decimal
amount: Decimal = Field(..., gt=0)

# ✅ صح — timezone
from app.resort_os.timezone_utils import business_today
today = business_today(settings.TIMEZONE)
```

### Frontend
```typescript
// ✅ استخدم مكونات @resort-os/ui دايماً
import { AppCard, AppBadge, AppButton, AppModal, useToast, useConfirm } from '@resort-os/ui'
import { api, useAuthStore } from '@resort-os/core'

// ✅ error handling pattern
try {
  await api.post('/api/v1/timeshare/contracts', payload)
  toast.success('تم الإنشاء')
} catch (e: any) {
  toast.error(e?.response?.data?.detail ?? 'حصل خطأ')
}
```

---

## 9. الموديولات الحساسة — انتبه

| الموديول | السبب |
|---------|-------|
| `finance/` | أي تغيير = تحقق من القيود المحاسبية (Dr/Cr) |
| `timeshare/services.py` | فيه 4 باجات محاسبية اتصلحت — لا تتراجع عنها |
| `pms/` | race condition في الحجوزات — FOR UPDATE NOWAIT |
| `core/deps.py` | ROLE_LEVELS + require_permission — تغييرها بتأثر على كل المشروع |
| `permission_catalog.py` | كل صف لازم يطابق endpoint حقيقي بـ require_permission فعلاً |

---

## 10. لو شُغّلت على مهمة تايم شير تحديداً

1. اقرأ `TIMESHARE_STATUS.md` كاملاً أولاً
2. الـ endpoints كلها بتستخدم `get_timeshare_user` (مش `get_current_active_user`)
3. `timeshare_agent` role يحتاج `UserPermission` صريح على `timeshare.access/view`
4. القرار المعلّق (PMS integration) — لا تلمسه من غير موافقة Mohamed
5. الكالندر بيجمع مصدرين: عقود ثابتة (`source=contract`) + زيارات فعلية (`source=visit`)
6. `booking_frozen=True` = حجز مجمّد بسبب متأخرات — يُرفع أوتوماتيكياً لما تتسدد

---

## 12. حالة الموديولات — نظرة سريعة

| الموديول | الحالة | ملاحظة مهمة |
|---------|--------|-------------|
| **dining** | ✅ مكتمل | حلّ محل `restaurant`+`cafe` نهائياً (cutover 2026-07-13). `restaurant`/`cafe` modules أرشيف فقط |
| **timeshare** | ✅ مكتمل | راجع القسم 5 + `TIMESHARE_STATUS.md` |
| **finance** | ✅ مكتمل | ورديات + فواتير + محاسبة + fraud detection + cost centers |
| **pms** | ✅ مكتمل | غرف + حجوزات + Night Audit + rate plans |
| **hr** | ✅ مكتمل | موارد بشرية + رواتب + إجازات + أداء موظفين |
| **beach** | ✅ مكتمل | شاطئ + معاملات + خريطة |
| **inventory** | ✅ مكتمل | مخزون + موردين حقيقيين + أوامر شراء |
| **crm** | ✅ مكتمل | عملاء + مجموعات بخصم دائم + blacklist |
| **analytics** | ✅ مكتمل | تقارير + استبيانات رضا ضيوف |
| **leasing** | ✅ مكتمل | عقود إيجار تجاري + جدول دفعات |
| **maintenance** | ✅ مكتمل | تذاكر صيانة + تعيين موظف |
| **hub** | ✅ مكتمل | بوابة الضيوف العامة (port 3002) |
| **core** | ✅ مكتمل | Users + Branches + Permissions + Notifications + PIN + AuditLog |

---

## 13. Celery Tasks — الجدول الكامل

```
PMS:
  night-audit              → 00:01 يومياً
  no-show-check            → كل ساعة

Finance:
  check-due-reminders      → 09:00 يومياً

Timeshare:
  timeshare-mark-overdue        → 02:00 يومياً (pending/partial → overdue + booking_frozen)
  timeshare-visit-reminders     → 09:00 يومياً (واتساب 3 أيام قبل الزيارة)
  timeshare-installment-reminders → 09:15 يومياً (واتساب 7 أيام قبل الاستحقاق)

Leasing:
  leasing-mark-overdue     → 02:30 يومياً
  leasing-due-reminders    → 09:00 يومياً

Inventory:
  inventory-low-stock      → 07:00 يومياً (واتساب للمدير)

Fraud Detection:
  scan-for-fraud-signals   → كل 15 دقيقة (مرتجعات/إلغاءات/خصومات/فتح درج)
```

---

## 14. قرارات معمارية مهمة — يجب معرفتها

### اتُخذت ولا تُعكَس بدون موافقة Mohamed:

**① dining بدل restaurant+cafe**
`restaurant` و`cafe` modules موجودان كأرشيف فقط — أي كود جديد للطعام يروح لـ `dining` حصراً.

**② وحدات التايم شير منفصلة عن غرف الفندق**
`TimeshareUnit` ≠ `pms.Room` — قرار معماري متعمد (مبنى منفصل فعلياً في المنتجع).

**③ `TimeshareVisit.booking_id` → معلّق**
FK لـ PMS موجود لكن لا يُنشأ حجز PMS تلقائياً — يحتاج قرار Mohamed قبل التنفيذ.

**④ لا `second audit log`**
كل fraud detection يقرأ من `AuditLog` الموجود مباشرة — لا جدول تدقيق ثانٍ.

**⑤ خصم مجموعة العميل لا يُجمع مع خصم شرطي**
يُطبّق الأعلى قيمة فقط — قرار تجاري موثّق في `dining/services.py`.

**⑥ `Account.parent_id` — هرمية من مستوى واحد فقط**
4 حسابات أب (1000/2000/4000/5000). لا تبني هرمية أعمق من غير طلب صريح.

---

## 15. مصادر الحقيقة

| السؤال | المصدر |
|--------|--------|
| "ما هي أولوياتي؟" | `CLAUDE.md` §2 |
| "ما حالة الموديولات؟" | `PROJECT_STATUS.md` |
| "ما تفاصيل التايم شير؟" | `TIMESHARE_STATUS.md` |
| "ما المهام القادمة؟" | `wagdy.md` |
| "كيف تشتغل المحاسبة؟" | `CLAUDE.md` §9 |
| "ما قواعد الأمان؟" | `CLAUDE.md` §8 |
| "ما حسابات الاختبار؟" | `backend/app/seed.py` |
| "ما الـ migrations؟" | `backend/alembic/versions/` |


```
Base URL: /api/v1/

# التايم شير
GET    /timeshare/contracts          → list (timeshare_user)
POST   /timeshare/contracts          → create (manager + permission)
PATCH  /timeshare/contracts/{id}     → update (manager + permission)
POST   /timeshare/contracts/{id}/cancel       → (manager + permission)
POST   /timeshare/contracts/{id}/transfer-unit → (manager)
GET    /timeshare/contracts/{id}/pdf → (timeshare_user)
GET    /timeshare/installments       → list (timeshare_user)
POST   /timeshare/installments/{id}/pay → (timeshare_user + permission)
GET    /timeshare/calendar           → 52-week ISO (timeshare_user)
GET    /timeshare/available-weeks    → للمبيعات (timeshare_user)
GET    /timeshare/cs-summary         → داشبورد (timeshare_user)
GET    /timeshare/sales-dashboard    → (timeshare_user)
GET    /timeshare/stats              → (timeshare_user)
GET    /timeshare/visits             → (timeshare_user)
POST   /timeshare/visits             → جدولة (timeshare_user + permission)
PATCH  /timeshare/visits/{id}        → تحديث (timeshare_user + permission)
GET    /timeshare/units              → (timeshare_user)
GET    /timeshare/waitlist           → (timeshare_user)
POST   /timeshare/waitlist           → (timeshare_user + permission)

# الصلاحيات
GET    /permissions/catalog  → كتالوج الصلاحيات
GET    /permissions?user_id= → صلاحيات مستخدم
POST   /permissions          → منح/منع صلاحية (manager+)
DELETE /permissions/{id}     → سحب صلاحية
GET    /permissions/me       → صلاحياتي الفعلية
```
