# Resort OS — التوثيق المعماري العميق
> للمطور الذي يريد إضافات وتعديلات — اقرأ هذا قبل أي سطر كود

---

## 1. الخريطة الكاملة للمشروع

```
resort-os/
├── backend/
│   ├── app/
│   │   ├── main.py                    ← نقطة الدخول الوحيدة
│   │   ├── celery_app.py              ← تعريف Celery + Beat schedule
│   │   ├── seed.py                    ← seed البيانات (111KB)
│   │   ├── seed_food.py               ← seed قائمة الطعام
│   │   ├── core/
│   │   │   ├── config.py              ← Settings (يرث kernel)
│   │   │   ├── database.py            ← re-export من kernel
│   │   │   ├── deps.py                ← كل Auth dependencies
│   │   │   ├── encryption.py          ← Fernet field encryption
│   │   │   ├── rate_limit.py          ← IP-based rate limiting
│   │   │   ├── me_router.py           ← /auth/me endpoint
│   │   │   └── kernel/                ← "النواة" المستقلة
│   │   │       ├── config.py          ← CoreSettings
│   │   │       ├── database.py        ← SQLAlchemy engine + session
│   │   │       ├── auth/              ← login/logout/2FA/refresh
│   │   │       ├── models/
│   │   │       │   ├── user.py        ← User, RefreshToken, TokenBlacklist
│   │   │       │   └── mixins.py      ← TimestampMixin
│   │   │       ├── security.py        ← JWT sign/verify, hash
│   │   │       ├── cache.py           ← Redis wrapper
│   │   │       ├── worker.py          ← make_celery factory
│   │   │       ├── whatsapp.py        ← Meta Cloud API client
│   │   │       ├── email_service.py   ← SMTP client
│   │   │       ├── errors.py          ← global exception handlers
│   │   │       ├── middleware.py      ← Security headers + timing
│   │   │       ├── correlation.py     ← X-Correlation-ID header
│   │   │       └── sentry.py          ← Sentry init
│   │   ├── modules/                   ← 13 module نشط
│   │   │   ├── core/                  ← Branch, Setting, Notification, AuditLog, UserPermission
│   │   │   ├── pms/                   ← إدارة الغرف والحجوزات
│   │   │   ├── finance/               ← Folio, Payment, Journal, Cashier
│   │   │   ├── dining/                ← المطاعم والـ POS الموحّد
│   │   │   ├── hr/                    ← الموظفين والمرتبات
│   │   │   ├── inventory/             ← المخازن والمشتريات
│   │   │   ├── beach/                 ← إدارة الشاطئ والـ B2B
│   │   │   ├── maintenance/           ← أوامر الصيانة والأصول
│   │   │   ├── crm/                   ← العملاء والـ leads
│   │   │   ├── analytics/             ← التقارير والإحصاءات
│   │   │   ├── hub/                   ← الموقع والحجز الإلكتروني
│   │   │   ├── leasing/               ← عقود الإيجار
│   │   │   └── timeshare/             ← عقود التايم شير
│   │   ├── resort_os/                 ← Business Engines (خالية من DB/HTTP)
│   │   │   ├── folio_engine.py        ← حسابات الفاتورة
│   │   │   ├── discount_engine.py     ← قواعد الخصم
│   │   │   ├── beach_engine.py        ← حسابات الشاطئ
│   │   │   ├── hr_engine.py           ← حسابات الرواتب/الحضور
│   │   │   ├── timeshare_engine.py    ← حسابات التايم شير
│   │   │   ├── food_cost_engine.py    ← تكلفة الأصناف
│   │   │   └── timezone_utils.py      ← UTC ↔ Cairo
│   │   └── tasks/                     ← Celery tasks
│   │       ├── pms_tasks.py
│   │       ├── finance_tasks.py
│   │       ├── hr_tasks.py
│   │       ├── timeshare_tasks.py
│   │       ├── leasing_tasks.py
│   │       ├── inventory_tasks.py
│   │       ├── beach_tasks.py
│   │       ├── maintenance_tasks.py
│   │       ├── crm_tasks.py
│   │       ├── analytics_tasks.py
│   │       └── hub_tasks.py
│   ├── tests/                         ← 80 test file
│   └── alembic/versions/              ← 62 migration
│
└── frontend/
    ├── apps/
    │   ├── el-kheima/                 ← ERP Dashboard (47 view)
    │   └── public/                    ← Guest Portal (11 view)
    └── packages/
        ├── core/                      ← API client, stores, composables
        └── ui/                        ← Design system components
```

---

## 2. طبقات النظام (Layers)

### Layer 1: Kernel (النواة)
`app/core/kernel/` — كود مستقل قابل لإعادة الاستخدام في أي مشروع آخر.

- **لا يعرف** شيئاً عن Resort OS بالذات
- يوفر: Auth، Database، Cache، Worker، WhatsApp، Email
- **لا تعدّل هنا** إلا لو في bug حقيقي في البنية التحتية

### Layer 2: Core App
`app/core/` — يربط الـ Kernel بـ Resort OS.

- `config.py` — يضيف settings خاصة بالـ Resort فوق `CoreSettings`
- `deps.py` — **المكان الأهم** — كل Auth dependencies وصلاحيات الأدوار
- `encryption.py` — تشفير fields حساسة (national_id، passport)

### Layer 3: Business Engines
`app/resort_os/` — منطق الأعمال **الخالص** بدون DB أو HTTP.

```python
# مثال: الـ engine يشتغل على dataclasses
from app.resort_os.folio_engine import FolioEngine, ChargeItem

engine = FolioEngine()
result = engine.calculate_total(charges=[...], taxes=...)
# قابل للاختبار بدون أي DB connection
```

**القاعدة:** أي حساب معقد (رواتب، خصومات، تايم شير) يروح هنا، مش في الـ service مباشرة.

### Layer 4: Modules
`app/modules/{module}/` — كل module فيه:
```
{module}/
├── models.py      ← SQLAlchemy models
├── schemas.py     ← Pydantic schemas (input/output)
├── crud.py        ← database operations (SELECT/INSERT/UPDATE)
├── services.py    ← business logic (بيستخدم crud + engines)
└── api/
    └── router.py  ← FastAPI endpoints
```

### Layer 5: Tasks
`app/tasks/` — Celery background jobs.
كل task بيستخدم `SessionLocal` مباشرة (مش `get_db`) لأنه خارج الـ request cycle.

---

## 3. نظام الـ Auth والصلاحيات بعمق

### الأدوار ومستوياتها
```python
ROLE_LEVELS = {
    "super_admin":   100,
    "admin":          80,
    "accountant":     70,
    "hr_manager":     70,
    "manager":        60,
    "supervisor":     50,
    "receptionist":   40,
    "cashier":        40,
    "waiter":         30,
    "chef":           30,
    "kitchen":        30,
    "employee":       20,
    "customer":        0,
    "guest":           0,
}
```

### Dependencies الجاهزة (استخدمها في أي endpoint جديد)
```python
from app.core.deps import (
    get_current_active_user,   # أي مستخدم مسجّل ونشط
    get_employee_user,         # level >= 20 (موظف)
    get_waiter_user,           # level >= 30
    get_cashier_user,          # level >= 40
    get_manager_user,          # level >= 60
    get_admin_user,            # level >= 80
    get_super_admin_user,      # level == 100
)
```

### Permission Matrix (صلاحيات دقيقة)
فوق نظام الـ roles — لمنح/منع صلاحية محددة لمستخدم بعينه:
```python
from app.core.deps import require_permission

@router.post("/void", dependencies=[
    Depends(require_permission("finance.void_payment", "execute", min_role_level=60))
])
def void_payment(...):
    ...
```

### 2FA الإلزامي
`super_admin` و`accountant` لازم يفعّلوا 2FA وإلا كل طلباتهم (ماعدا `/auth/*`) هترفض بـ `2FA_REQUIRED`.

### WebSocket Auth
```python
from app.core.deps import get_websocket_user

@router.websocket("/live")
async def ws_endpoint(websocket: WebSocket, db: DbDep):
    user = await get_websocket_user(websocket, db, min_level=30)
    if user is None:
        return  # الاتصال اتقفل تلقائياً
    await websocket.accept()
    ...
```

---

## 4. العلاقات بين الـ Modules

```
┌─────────────────────────────────────────────────────────┐
│                      FINANCE (المركز)                    │
│  Folio ← كل charge من أي module يمر هنا                │
│  Payment, Journal, CashierShift                         │
└───────────┬─────────────┬──────────────┬────────────────┘
            │             │              │
     ┌──────▼──────┐ ┌────▼────┐  ┌─────▼──────┐
     │     PMS     │ │ DINING  │  │   BEACH    │
     │  Booking    │ │  Order  │  │Transaction │
     │  Folio link │ │  → Folio│  │  → Folio  │
     └─────────────┘ └─────────┘  └────────────┘
            │
     ┌──────▼──────────────────────────────────┐
     │              INVENTORY                   │
     │  dining_items → recipe_lines → products  │
     │  purchase_orders → stock_movements       │
     └──────────────────────────────────────────┘
```

### Cross-module dependencies الفعلية:
| Module | يعتمد على |
|--------|-----------|
| dining | finance (post_simple_revenue_journal, FolioCharge) |
| beach | finance (FolioCharge) |
| pms | finance (folio_for_room) |
| leasing | finance (journal entries) |
| timeshare | finance (journal entries) |
| maintenance | inventory (parts/products) |
| hr | core (AuditLog) |
| كل module | core (PaginatedResponse, AuditLogCreate) |

### القاعدة المهمة:
`finance` هو الـ module الوحيد الذي يُستورد منه في modules أخرى.
`core` يوفر schemas/utilities مشتركة.
**لا يجوز** أن يستورد `finance` من `dining` أو أي module آخر (one-way dependency).

---

## 5. الـ Folio — قلب النظام المالي

الـ Folio هو "الفاتورة المفتوحة" للضيف. كل خدمة تُضاف كـ FolioCharge:

```
Booking (PMS)
    └── Folio (finance)
         ├── FolioCharge: room (من PMS)
         ├── FolioCharge: dining (من dining)
         ├── FolioCharge: beach (من beach)
         └── FolioCharge: other
              └── Payment (يغلق الـ Folio)
                   └── JournalEntry (محاسبة)
```

### إضافة charge من module جديد:
```python
from app.modules.finance.services import post_simple_revenue_journal
from app.modules.finance.schemas import FolioChargeCreate

charge = FolioChargeCreate(
    folio_id=folio_id,
    charge_type="beach",   # من CHARGE_TYPES في folio_engine.py
    description="Sunbed rental",
    amount=Decimal("150.00"),
    currency="EGP",
)
finance_crud.add_charge(db, charge)
```

---

## 6. Dining Module — الأكبر والأكثر تعقيداً

### هيكل البيانات:
```
Outlet (مطعم/كافيه/poolbar)
  └── VenueTable (طاولة)
       └── DiningOrder (طلب)
            ├── DiningOrderItem (صنف)
            │    ├── DiningOrderItemExtra (إضافات)
            │    └── DiningItemVariant (مقاس/نوع)
            └── DiningKitchenTicket → DiningKDSScreen
```

### Recipe/Cost chain:
```
DiningItem
  └── DiningItemRecipeLine → Product (inventory)
       └── StockMovement (يُخصم عند تنفيذ الطلب)
```

### الـ POS flow:
1. فتح طاولة → إنشاء `DiningOrder`
2. إضافة items → `DiningOrderItem` + kitchen ticket
3. KDS (kitchen display) يستقبل من `DiningKDSScreen`
4. إغلاق الطلب → `FolioCharge` أو payment مباشر
5. `post_simple_revenue_journal` → `JournalEntry`

---

## 7. نظام Tasks (Celery)

### ترتيب التشغيل اليومي (Beat):
```
00:01 — Night Audit (PMS)        → تسوية الغرف + رسوم الإقامة
00:05 — Hub expire offers        → إيقاف العروض المنتهية
01:00 — Daily stats (Analytics)  → بعد Night Audit
02:00 — Timeshare mark overdue
02:15 — Beach B2B mark overdue
02:30 — Leasing mark overdue
03:00 — Sitemap refresh
06:00 — Maintenance preventive   → إنشاء أوامر الصيانة الدورية
07:00 — Inventory low stock      → تنبيه المخزون المنخفض
08:00 — Maintenance overdue alert
08:00 — CRM birthday greetings
09:00 — Finance check reminders
09:00 — Timeshare visit reminders
09:00 — Leasing due reminders
09:00 — CRM activity reminders
09:15 — Timeshare installment reminders
10:00 — CRM overdue activities
10:00 — Hub pending bookings
10:00 — HR payroll reminder (28-31 كل شهر)
11:05 — Beach reservation no-shows
23:59 — HR mark absent
```

### إضافة task جديد:
```python
# في app/tasks/my_module_tasks.py
from app.celery_app import celery_app
from app.core.database import SessionLocal

@celery_app.task(name="app.tasks.my_module_tasks.do_something")
def do_something():
    db = SessionLocal()
    try:
        # ...
        db.commit()
    finally:
        db.close()
```

ثم أضفه في `celery_app.py`:
```python
"my-task": {
    "task": "app.tasks.my_module_tasks.do_something",
    "schedule": crontab(hour=9, minute=0),
},
```

---

## 8. Frontend — البنية الكاملة

### el-kheima (ERP Dashboard)
المستخدم: الموظفون

```
layouts/
  BackOfficeLayout.vue  ← admin pages (sidebar + header)
  FieldLayout.vue       ← ops pages (simplified)
  KioskLayout.vue       ← POS/Beach kiosk (fullscreen)

views/
  account/    ← Login, Reset Password, 2FA Setup
  admin/      ← Analytics, Finance, HR, Inventory, CRM, Settings...
  kds/        ← Kitchen Display System
  ops/        ← Bookings, Rooms, Housekeeping
  portal/     ← Staff self-service (Attendance, Leaves, Payroll)
  pos/        ← Beach POS, Unified POS, Shift Dashboard
```

### public (Guest Portal)
المستخدم: الضيوف عبر QR code أو رابط WhatsApp

```
HomeView.vue        ← الصفحة الرئيسية
OrderView.vue       ← طلب من الغرفة/الشاطئ
DiningView.vue      ← قائمة الطعام
BookingView.vue     ← حجز إلكتروني
BeachCheckinView.vue← تسجيل وصول للشاطئ
SurveyView.vue      ← استبيان رضا الضيف
```

### packages/core — المشترك بين التطبيقين
```typescript
// API client موحّد
import { useApi } from '@resort-os/core'

// Auth store
import { useAuthStore } from '@resort-os/core'

// Composables
import { useWebSocket, useOfflineQueue, useOrderDiscount } from '@resort-os/core'
```

### packages/ui — Design System
```typescript
import { Button, DataTable, Drawer, Badge, Card } from '@resort-os/ui'
```

---

## 9. كيف تضيف Module جديد (Step by Step)

### Backend:

**1. أنشئ هيكل الـ module:**
```bash
mkdir -p backend/app/modules/my_module/api
touch backend/app/modules/my_module/__init__.py
touch backend/app/modules/my_module/models.py
touch backend/app/modules/my_module/schemas.py
touch backend/app/modules/my_module/crud.py
touch backend/app/modules/my_module/services.py
touch backend/app/modules/my_module/api/__init__.py
touch backend/app/modules/my_module/api/router.py
```

**2. models.py:**
```python
from sqlalchemy import Column, Integer, String, ForeignKey
from app.core.kernel.database import Base
from app.core.kernel.models.mixins import TimestampMixin

class MyEntity(Base, TimestampMixin):
    __tablename__ = "my_entities"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"))
```

**3. router.py:**
```python
from fastapi import APIRouter, Depends
from app.core.deps import get_current_active_user, get_manager_user, DbDep

router = APIRouter(prefix="/my-module", tags=["My Module"])

@router.get("/")
def list_items(db: DbDep, user=Depends(get_current_active_user)):
    ...

@router.post("/")
def create_item(db: DbDep, user=Depends(get_manager_user)):
    ...
```

**4. سجّل في main.py:**
```python
_MODULE_KEYS = (
    "core", "finance", ..., "my_module",  # ← أضفه هنا
)
```

**5. أنشئ migration:**
```bash
cd backend
source .venv/bin/activate
alembic revision --autogenerate -m "add_my_module_tables"
alembic upgrade head
```

### Frontend (el-kheima):

**1. أضف view:**
```
frontend/apps/el-kheima/src/views/admin/MyModuleView.vue
```

**2. أضف route في router:**
```typescript
{
  path: '/my-module',
  component: () => import('@/views/admin/MyModuleView.vue'),
  meta: { requiresAuth: true, minLevel: 60 }
}
```

**3. أضف API endpoint في core:**
```typescript
// packages/core/src/api/endpoints.ts
export const MY_MODULE = {
  list: '/api/v1/my-module/',
  create: '/api/v1/my-module/',
  detail: (id: number) => `/api/v1/my-module/${id}`,
}
```

---

## 10. قواعد التوقيت — مهم جداً

**المشكلة:** PostgreSQL بيخزّن كل timestamps بـ UTC. الـ Resort في Africa/Cairo (UTC+2 أو UTC+3 في الصيف).

**القاعدة:**
```python
from app.resort_os.timezone_utils import now_cairo, utc_to_cairo, cairo_to_utc

# عند إنشاء record جديد
record.created_at = now_cairo()

# عند إرسال للـ frontend
response.date = utc_to_cairo(db_record.created_at)

# عند استقبال من الـ frontend
db_value = cairo_to_utc(user_input_datetime)
```

**لا تستخدم** `datetime.utcnow()` أو `datetime.now()` مباشرة في أي service.

---

## 11. الـ Pagination Pattern

كل list endpoint لازم يرجع `PaginatedResponse`:

```python
from app.modules.core.schemas import PaginatedResponse

@router.get("/", response_model=PaginatedResponse[MySchema])
def list_items(
    page: int = 1,
    page_size: int = 20,
    db: DbDep = ...,
    user = Depends(get_current_active_user),
):
    query = db.query(MyModel)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
```

---

## 12. الـ AuditLog Pattern

أي عملية مهمة (حذف، تعديل مالي، تغيير صلاحيات) لازم تتسجّل:

```python
from app.modules.core.schemas import AuditLogCreate
from app.modules.core import crud as core_crud

core_crud.create_audit_log(db, AuditLogCreate(
    user_id=user.id,
    entity_type="payment",
    entity_id=payment.id,
    action="void",
    detail={"reason": reason, "amount": str(payment.amount)},
))
```

---

## 13. WhatsApp Integration

لإرسال رسالة WhatsApp:
```python
from app.core.kernel.whatsapp import send_whatsapp_message

await send_whatsapp_message(
    phone=guest.phone,      # بالصيغة الدولية: +201XXXXXXXXX
    template="booking_confirmation",
    params={"name": guest.name, "room": room.number},
)
```

---

## 14. نقاط الدخول للـ Frontend

| الـ App | URL | الـ Port |
|---------|-----|---------|
| el-kheima (ERP) | http://localhost:3001 | 3001 |
| public (Guest) | http://localhost:3002 | 3002 |
| API Backend | http://localhost:8005 | 8005 |
| API Docs | http://localhost:8005/docs | 8005 |

---

## 15. الملفات المهمة للقراءة قبل التعديل

| الملف | متى تقرأه |
|-------|-----------|
| `CLAUDE.md` | دايماً — فيه كل القرارات المعمارية |
| `DINING_CUTOVER_PLAN.md` | لو بتعدّل في dining أو restaurant/cafe |
| `wagdy.md` | فيه bugs مكتشفة وقرارات تقنية مهمة |
| `PROJECT_STATUS.md` | الحالة الحالية وما اتعمل |
| `core/deps.py` | قبل أي تعديل في Auth أو صلاحيات |
| `resort_os/folio_engine.py` | قبل أي تعديل في المالية |

---

## 16. أهم الـ Patterns المستخدمة

### Pattern 1: Lazy Import للـ circular dependencies
```python
# في deps.py
def get_current_active_user(...):
    from app.modules.core.services import has_permission  # noqa: PLC0415
    ...
```
مستخدم في أماكن كتير لتجنب circular imports.

### Pattern 2: Services تستخدم Engines
```python
# في services.py
from app.resort_os.hr_engine import HREngine

def calculate_payroll(db, employee_id, month, year):
    engine = HREngine()
    attendance = get_attendance(db, employee_id, month, year)
    return engine.compute_net_salary(attendance=attendance, ...)
```

### Pattern 3: Tasks منفصلة عن HTTP
```python
# في tasks/hr_tasks.py
@celery_app.task
def mark_attendance_absent():
    db = SessionLocal()
    try:
        service.mark_absent_for_today(db)
        db.commit()
    finally:
        db.close()
```

### Pattern 4: Branch isolation
كل entity مهمة عندها `branch_id` — الـ Resort ممكن يكون فيه أكتر من فرع.

---

## 17. الـ Tests — كيف تكتب

```python
# في tests/test_api/test_my_module_http.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def admin_token(client, db):
    # موجود في conftest.py
    ...

def test_list_items(client: TestClient, admin_token: str):
    response = client.get(
        "/api/v1/my-module/",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
```

---

## 18. قاموس المصطلحات

| المصطلح | المعنى |
|---------|--------|
| Folio | الفاتورة المفتوحة للضيف |
| FolioCharge | خدمة مضافة للفاتورة |
| Night Audit | تسوية يومية منتصف الليل |
| KDS | Kitchen Display System |
| B2B Contract | عقد مع شركة سياحية |
| Outlet | مطعم/كافيه/نقطة بيع |
| RatePlan | خطة سعرية للغرف |
| POS | Point of Sale |
| Beat | Celery scheduler للـ periodic tasks |
| Kernel | النواة المستقلة في core/kernel/ |
| Engine | Business logic خالص بدون DB/HTTP |
