# TIMESHARE-01 — خطة التطوير الشاملة لموديول الملكية الجزئية
**تاريخ الإعداد:** 2026-08-09
**المالك:** Mohamed
**قائد التنفيذ:** Codex / Kiro
**المرجع:** PDFs — نموذج الحجز الداخلي، التعليمات واللوائح الداخلية، مصروفات الصيانة 2026

---

## 1. الوضع الحالي — ما هو موجود بالفعل

### 1.1 الجداول القائمة
| الجدول | الغرض |
|---|---|
| `timeshare_contracts` | العقد الأساسي — بيانات العميل، الوحدة، الأسبوع، المالية |
| `timeshare_installments` | جدول الأقساط |
| `timeshare_maintenance_dues` | مستحقات الصيانة السنوية |
| `timeshare_visits` | الزيارات الفعلية المنفَّذة |
| `timeshare_visit_requests` | طلبات زيارة من بوابة العميل |
| `timeshare_support_tickets` | تذاكر دعم فني خاصة بأصحاب العقود |
| `timeshare_support_ticket_replies` | ردود المحادثة |
| `timeshare_waitlist` | قائمة انتظار للأسابيع العائمة |
| `timeshare_units` | مخزون الوحدات |

### 1.2 الـ Endpoints القائمة
- CRUD كامل للعقود (إنشاء، عرض، تعديل، إلغاء، نقل وحدة)
- تحصيل أقساط + مستحقات صيانة مع قفل صف لمنع race condition
- بوابة عميل عامة (OTP → JWT) — `/timeshare/public/*`
- طلبات زيارة + موافقة/رفض
- تذاكر دعم فني + ردود
- تقارير: CS dashboard، sales dashboard، monthly collection Excel، calendar
- استيراد Excel جماعي
- إدارة موظفي الملكية الجزئية

### 1.3 النواقص المكتشفة بعد مراجعة الـ PDFs والكود

#### أ) نواقص في بيانات العقد (models + schemas)
| الحقل الناقص | المصدر | الأثر |
|---|---|---|
| `unit_capacity` (2/4/6 أفراد) | تعميم الصيانة 2026 | مبلغ الصيانة مرتبط بالسعة — بدونه مفيش تحقق |
| `beneficiary_name` (اسم الزوجة/المستفيد) | نموذج الحجز الداخلي | مطلوب في ورقة الحجز |
| `customer_phone_work` (تليفون عمل) | نموذج الحجز الداخلي | موجود work/home/mobile في الورقة، النظام عنده mobile بس |
| `customer_phone_home` (تليفون منزل) | نموذج الحجز الداخلي | نفس السبب |
| `mailing_address` (عنوان المراسلة) | نموذج الحجز الداخلي | `address` موجود لكنه عنوان إقامة — المراسلة قد تختلف |

#### ب) نواقص في طلب الحجز (timeshare_visit_requests)
| الناقص | المصدر |
|---|---|
| 3 تواريخ بديلة (alt_start_1/end_1، alt_start_2/end_2) | نموذج الحجز — "يرجى كتابة ثلاث فترات بديلة" |
| `special_requests` | نموذج الحجز — "طلبات خاصة" — موجود كـ `notes` ✅ |
| Checkbox موافقة على التعليمات واللوائح (18 بند) | اللوائح الداخلية |
| Checkbox موافقة على قواعد الحجز (12 بند) | نموذج الحجز |
| علامة ذروة `is_peak` في الـ response | منطق الأولوية |

#### ج) نواقص في منطق الأسابيع
| الناقص | التفاصيل |
|---|---|
| بداية الأسبوع من السبت | الكود يبدأ من الإثنين (ISO weekday=1)؛ المطلوب السبت (weekday=6) |
| جدول مواسم الذروة | لا يوجد `timeshare_peak_seasons` — الذروة مش محددة في الـ DB |
| قاعدة "أسبوع واحد بس في الذروة" | لا يوجد أي تحقق |
| قاعدة "مش أعياد متتالية" | لا يوجد أي تحقق |
| إحصاء الاستخدام التراكمي في الذروة | لا يوجد — مطلوب لحساب الأولوية |

#### د) نواقص في لوحات العرض والتقارير
| الناقص | التفاصيل |
|---|---|
| ملف العميل الكامل بتبويبات | البيانات الشخصية — سجل الاستخدام — الماليات — نموذج الحجز |
| عدد الأسابيع المستخدمة إجمالاً | غير محسوب في أي endpoint |
| تاريخ الاستخدام التراكمي في الذروة | غير محسوب |
| مبلغ الصيانة المقترح (حسب السعة + تاريخ العقد) | غير موجود — يُحسب يدوياً |
| تحذير مبلغ الصيانة عند تعارضه مع تعميم 2026 | غير موجود |

#### هـ) نواقص في بوابة العميل
| الناقص | التفاصيل |
|---|---|
| عرض سجل الاستخدام التاريخي الكامل | `/public/my-visits` غير موجود |
| إظهار الزيارة القادمة بالتاريخ الفعلي | الـ endpoint الحالي لا يحسبها للعميل |
| تأكيد استلام نموذج الحجز (فوتشر رقمي) | لا يوجد PDF لطلب الزيارة |

---

## 2. قواعد العمل المستخرجة من الـ PDFs

### 2.1 قواعد الحجز (12 قاعدة — نموذج الحجز الداخلي)
1. الأولوية: أسبوع العام أولاً ← استخدام تراكمي ذروة أقل ← تاريخ تقديم الطلب
2. التأكيد من خدمة العملاء — بشرط: إتاحة + سداد الصيانة + التزامات مالية
3. فوتشر تأكيد إلزامي — لا دخول بدونه
4. الرد خلال 10 أيام عمل
5. الضيافة/الإيجار: موافقة الشركة + رسوم ضيافة + بيانات الضيف قبل شهرين
6. طلب موقع وحدة: بالإتاحة + الاستخدام التراكمي — قبول العميل = لا اعتراض
7. الأبناء بدون الوالدين: توقيع العميل على إقرار مسؤولية كاملة
8. الإلغاء في الذروة: إشعار 30 يوماً قبل؛ عادي: 15 يوماً — وإلا يُحتسب الأسبوع
9. إلغاء بعد التأكيد في فترات الإلغاء: نفس الغرامة
10. **قاعدة الذروة: أسبوع واحد فقط + شاليه واحد + لا أعياد متتالية**
11. أي تعديل على النموذج = تعليق الحجز
12. التوقيع = موافقة نهائية غير قابلة للاعتراض

### 2.2 التعليمات واللوائح الداخلية (18 بنداً)
- Check-in: 2 م — Check-out: 10 ص (غرامة تأخر: 1500/2000/2500 ج حسب السعة)
- الأطفال حتى 8 سنوات: لا يُحتسبون من الطاقة الإيوائية
- 25% خصم على المطاعم لأصحاب العقود
- تنظيف 3 مرات أسبوعياً كحد أقصى
- حمام سباحة نادي شرم: مرتين أسبوعياً كحد أقصى
- فرد إضافي زيادة: 500 ج/ليلة (بحد أقصى فرد واحد بدون سرير)
- المربية = فرد من العدد المخصص

### 2.3 مصروفات الصيانة 2026
| تاريخ العقد | 2 أفراد | 4 أفراد | 6 أفراد |
|---|---|---|---|
| قبل 1 مايو 2026 | 1,750 ج | 2,000 ج | 2,500 ج |
| من 1 مايو 2026 | 2,000 ج | 3,000 ج | 4,000 ج |

---

## 3. خطة التنفيذ — 5 مراحل


---

### المرحلة 1 — تصحيحات فورية (صفر Migration، صفر breaking change)

**الهدف:** تصحيح سلوك الأسابيع + إضافة Checkboxes الموافقة.

#### 1-أ: بداية الأسبوع → السبت
**الملف:** `backend/app/resort_os/timeshare_engine.py`
```python
# السطر الحالي (calculate_visit_window)
visit_start = date.fromisocalendar(year, week_number, 1)  # الإثنين ISO

# يُصبح
visit_start = date.fromisocalendar(year, week_number, 6)  # السبت
```
**الأثر:** كل `calculate_visit_window` + `find_next_visit` + CS dashboard + calendar.
**التحقق:** `pytest tests/ -v -k "timeshare"` — تحديث expected dates في التستات.

#### 1-ب: Checkboxes الموافقة في بوابة العميل
**الملف:** `backend/app/modules/timeshare/schemas.py`
```python
class TimeshareVisitRequestCreate(BaseModel):
    preferred_start: date
    preferred_end:   date
    notes:           Optional[str] = Field(None, max_length=500)
    # جديد:
    terms_accepted:         bool = Field(..., description="وافق على التعليمات واللوائح الداخلية للاستخدام (18 بنداً)")
    booking_rules_accepted: bool = Field(..., description="وافق على قواعد والتزامات الحجز (12 قاعدة)")
```
**الملف:** `backend/app/modules/timeshare/services.py` — في `request_visit`:
```python
def request_visit(db, contract_id, data):
    if not data.terms_accepted:
        raise ValueError("يجب الموافقة على التعليمات واللوائح الداخلية قبل إرسال الطلب")
    if not data.booking_rules_accepted:
        raise ValueError("يجب الموافقة على قواعد والتزامات الحجز قبل إرسال الطلب")
    # ... باقي المنطق الحالي
```
**صفر Migration** — validation فقط، لا حقول جديدة في الـ DB.

**Definition of Done المرحلة 1:**
- [ ] `pytest tests/ -v -k "timeshare"` → صفر failures
- [ ] تست يدوي: طلب زيارة بدون checkbox → 400
- [ ] تست يدوي: أسبوع 28 → يبدأ السبت الصح

---

### المرحلة 2 — Migration-01: بيانات العقد الموسّعة + طلب الحجز الكامل

**الهدف:** إضافة السعة + المستفيد + أرقام الهاتف + 3 تواريخ بديلة.

#### 2-أ: أعمدة جديدة على `timeshare_contracts`
```python
# في models.py — TimeshareContract
unit_capacity:        Mapped[int]         = mapped_column(Integer, default=2)
# 2 | 4 | 6 أفراد — مطلوب لحساب الصيانة الصحيح وتطبيق غرامات التأخير

beneficiary_name:     Mapped[str | None]  = mapped_column(String(200), nullable=True)
# اسم الزوجة أو المستفيد الآخر — من نموذج الحجز الداخلي

customer_phone_work:  Mapped[str | None]  = mapped_column(String(20), nullable=True)
# تليفون العمل — نموذج الحجز يطلب: عمل + منزل + موبايل

customer_phone_home:  Mapped[str | None]  = mapped_column(String(20), nullable=True)
# تليفون المنزل

mailing_address:      Mapped[str | None]  = mapped_column(String(300), nullable=True)
# عنوان المراسلة — قد يختلف عن address (عنوان الإقامة الموجود بالفعل)
```

**Validation في `TimeshareContractCreate`:**
```python
unit_capacity: int = Field(2, pattern=None)  # يُقيَّد بـ Literal[2, 4, 6]
```

**ربط الصيانة بالسعة:** في `services.py` — دالة مساعدة:
```python
MAINTENANCE_FEES_2026 = {
    "before_may_2026": {2: Decimal("1750"), 4: Decimal("2000"), 6: Decimal("2500")},
    "from_may_2026":   {2: Decimal("2000"), 4: Decimal("3000"), 6: Decimal("4000")},
}

def get_recommended_maintenance_fee(contract_date: date, unit_capacity: int) -> Decimal:
    """يحسب مبلغ الصيانة المقترح من تعميم 2026 — للتحقق والعرض فقط،
    القرار النهائي يبقى في maintenance_fee المدخل يدوياً."""
    tier = "from_may_2026" if contract_date >= date(2026, 5, 1) else "before_may_2026"
    return MAINTENANCE_FEES_2026[tier].get(unit_capacity, Decimal("0"))
```

**endpoint جديد:** `GET /timeshare/maintenance-fee-suggestion?contract_date=YYYY-MM-DD&unit_capacity=4`
→ يرجع `{"suggested_fee": 2000.00}` — للعرض في واجهة إنشاء العقد.

#### 2-ب: أعمدة جديدة على `timeshare_visit_requests`
```python
# في models.py — TimeshareVisitRequest
alt_start_1: Mapped[date | None] = mapped_column(Date, nullable=True)
alt_end_1:   Mapped[date | None] = mapped_column(Date, nullable=True)
alt_start_2: Mapped[date | None] = mapped_column(Date, nullable=True)
alt_end_2:   Mapped[date | None] = mapped_column(Date, nullable=True)
# البديل الثالث = preferred_start/preferred_end الأصليين دايماً
```

**في `TimeshareVisitRequestCreate`:**
```python
alt_start_1: Optional[date] = None
alt_end_1:   Optional[date] = None
alt_start_2: Optional[date] = None
alt_end_2:   Optional[date] = None
```

**Validation في service:**
- لو alt_start_1 موجود، alt_end_1 لازم موجود كمان والعكس
- alt_end يجب أن يكون بعد alt_start
- لا يُشترط أن تبدأ البدائل من السبت (العميل حر، المسؤول يختار)

**في `TimeshareVisitRequestRead`:** إضافة الحقول الأربعة للـ response.

**في شاشة مراجعة الطلب (staff):** المسؤول يشوف التواريخ الثلاثة ويختار المتاح.

#### 2-ج: Alembic migration
```bash
alembic revision --autogenerate -m "timeshare_01_capacity_beneficiary_alt_dates"
# مراجعة الـ migration قبل التطبيق — كل الأعمدة nullable أو بـ default
alembic upgrade head
```

**Definition of Done المرحلة 2:**
- [ ] `alembic heads` → head واحد
- [ ] `pytest tests/ -v -k "timeshare"` → صفر failures
- [ ] اختبار: إنشاء عقد بـ unit_capacity=4 → يقبل
- [ ] اختبار: إنشاء عقد بـ unit_capacity=5 → 422
- [ ] اختبار: `GET /timeshare/maintenance-fee-suggestion?contract_date=2026-01-01&unit_capacity=4` → 2000
- [ ] اختبار: طلب زيارة بـ 3 تواريخ → يُخزَّن صح

---

### المرحلة 3 — Migration-02: جدول مواسم الذروة

**الهدف:** Mohamed يدير مواسم الذروة سنوياً من الواجهة.

#### 3-أ: الـ Model
```python
class TimesharePeakSeason(Base, TimestampMixin):
    """فترة ذروة يدخلها timeshare_admin كل سنة — مثال:
    "صيف 2026" (1 يونيو → 30 سبتمبر) أو "عيد الأضحى 2026" (5 يونيو → 12 يونيو).
    الأعياد الهجرية بتتغير كل سنة — Mohamed هو اللي يدخلها يدوياً بدل أي
    حساب تلقائي قد يكون غلط."""
    __tablename__ = "timeshare_peak_seasons"

    id:          Mapped[int]        = mapped_column(primary_key=True)
    branch_id:   Mapped[int]        = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"))
    name:        Mapped[str]        = mapped_column(String(100))   # "عيد الفطر 2026"
    season_year: Mapped[int]        = mapped_column(Integer, index=True)
    start_date:  Mapped[date]       = mapped_column(Date, index=True)
    end_date:    Mapped[date]       = mapped_column(Date)
    created_by:  Mapped[int]        = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    notes:       Mapped[str | None] = mapped_column(String(300), nullable=True)
```

#### 3-ب: الـ Schemas
```python
class TimesharePeakSeasonCreate(BaseModel):
    branch_id:   int
    name:        str  = Field(..., min_length=3, max_length=100)
    season_year: int  = Field(..., ge=2026, le=2100)
    start_date:  date
    end_date:    date
    notes:       Optional[str] = None

class TimesharePeakSeasonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; branch_id: int; name: str; season_year: int
    start_date: date; end_date: date; notes: Optional[str]
    created_at: datetime
```

#### 3-ج: الـ CRUD + Service
```python
# crud.py
def list_peak_seasons(db, branch_id, year=None): ...
def create_peak_season(db, data, created_by): ...
def delete_peak_season(db, season_id): ...
def is_date_range_peak(db, branch_id, start_date, end_date) -> bool:
    """هل الفترة [start, end] تتقاطع مع أي موسم ذروة لنفس السنة؟"""
    ...

# services.py — دالة مساعدة
def get_peak_overlap(db, branch_id, start_date, end_date) -> list[str]:
    """يرجع أسماء مواسم الذروة المتقاطعة — للعرض للمسؤول وقت مراجعة الطلب."""
    ...
```

#### 3-د: الـ Endpoints (timeshare_admin فقط)
```
GET    /timeshare/peak-seasons?branch_id=&year=    ← قايمة المواسم
POST   /timeshare/peak-seasons                      ← إضافة موسم
DELETE /timeshare/peak-seasons/{id}                 ← حذف موسم
```

#### 3-هـ: دالة مساعدة في الـ engine
```python
# timeshare_engine.py
def check_peak_overlap(
    season_ranges: list[tuple[date, date]],  # قايمة (start, end) من DB
    check_start: date,
    check_end: date,
) -> list[tuple[date, date]]:
    """Pure Python — يرجع الفترات المتقاطعة (للتست بدون DB)."""
    return [
        (s, e) for s, e in season_ranges
        if s <= check_end and e >= check_start
    ]
```

**Definition of Done المرحلة 3:**
- [ ] `alembic heads` → head واحد
- [ ] `pytest tests/ -v -k "timeshare"` → صفر failures
- [ ] اختبار: إنشاء موسم ذروة "صيف 2026" → يُخزَّن
- [ ] اختبار: `is_date_range_peak` على تاريخ داخل الصيف → True
- [ ] اختبار: `is_date_range_peak` على تاريخ خارج المواسم → False

---

### المرحلة 4 — قواعد الذروة في الـ Service (صفر Migration)

**الهدف:** تطبيق قاعدة الأسبوع الواحد + الأعياد المتتالية تلقائياً.

#### 4-أ: حقل `is_peak` في الـ response
في `TimeshareVisitRequestRead`:
```python
is_peak: bool = False          # هل الفترة تقع في موسم ذروة؟
peak_season_names: list[str] = []  # أسماء المواسم المتقاطعة
```
يُملأ في service `request_visit` + قائمة `list_visit_requests` للمسؤول.

#### 4-ب: قاعدة الأسبوع الواحد في الذروة
في `services.request_visit`:
```python
def _count_peak_visits_this_year(db, contract_id, year) -> int:
    """يحسب عدد طلبات/زيارات الذروة المعتمدة للعقد في سنة معينة.
    يشمل: visit_requests со status=approved + timeshare_visits со status in
    (scheduled, active, completed) — فقط اللي تقاطعت مع موسم ذروة."""
    ...

# في request_visit:
if is_peak_request:
    peak_count = _count_peak_visits_this_year(db, contract_id, preferred_start.year)
    if peak_count >= 1:
        raise ValueError(
            f"تم استخدام حصة أسبوع الذروة لهذا العقد في سنة {preferred_start.year} — "
            "لا يُسمح بأكثر من أسبوع ذروة واحد في السنة لتحقيق تكافؤ الفرص بين جميع الأعضاء"
        )
```

#### 4-ج: قاعدة الأعياد المتتالية
```python
def _has_adjacent_peak_booking(db, contract_id, start_date, end_date,
                                peak_seasons: list) -> bool:
    """هل يوجد طلب/زيارة ذروة أخرى للعقد ملاصقة للفترة المطلوبة؟
    "ملاصق" = الفجوة بين نهاية الأول وبداية الثاني < 30 يوم."""
    ...

# في request_visit:
if is_peak_request and _has_adjacent_peak_booking(...):
    raise ValueError(
        "لا يُسمح بحجز أعياد متتالية — الفجوة بين أسبوعي ذروة يجب أن تكون 30 يوماً على الأقل"
    )
```

#### 4-د: إحصاء الاستخدام التراكمي في الذروة
```python
# في crud.py
def get_contract_peak_usage_stats(db, contract_id) -> dict:
    """يرجع:
    - total_visits: إجمالي الزيارات
    - peak_visits: زيارات الذروة
    - peak_years_used: السنوات التي استُخدمت فيها الذروة
    - last_peak_visit: آخر زيارة ذروة
    """
    ...
```

**يُضاف للـ CS Dashboard** و**ملف العميل**.

**Definition of Done المرحلة 4:**
- [ ] تست: طلب ذروة ثاني في نفس السنة → 400
- [ ] تست: طلبان ذروة بفجوة < 30 يوم → 400
- [ ] تست: طلب ذروة بعد فجوة 31 يوم → مقبول
- [ ] تست: طلب عادي (غير ذروة) → مقبول دايماً بغض النظر
- [ ] `pytest tests/ -v -k "timeshare"` → صفر failures

---

### المرحلة 5 — ملف العميل الكامل + تحسينات الواجهة (Frontend)

**الهدف:** شاشة موحدة تعرض كل بيانات العميل بأربعة تبويبات.

#### 5-أ: Backend — endpoint ملف العميل الموحد
```
GET /timeshare/contracts/{contract_id}/profile
```
يرجع:
```json
{
  "contract": { ... },           // كل بيانات العقد
  "usage_stats": {
    "total_visits": 3,
    "peak_visits": 1,
    "peak_years_used": [2024],
    "last_visit": "2025-07-12",
    "next_visit": "2026-07-05",
    "weeks_used_this_year": 1
  },
  "financials": {
    "total_value": 150000,
    "total_paid": 80000,
    "total_remaining": 70000,
    "overdue_installments": 0,
    "overdue_maintenance": 0,
    "next_installment_due": "2026-09-01",
    "next_maintenance_due": "2027-01-01",
    "recommended_maintenance_fee": 2000.00   // من جدول 2026
  },
  "visits": [ ... ],             // كل الزيارات التاريخية
  "active_visit_request": { ... } // الطلب الجاري لو موجود
}
```

#### 5-ب: تبويبات ملف العميل في الواجهة

**التبويب 1: البيانات الشخصية**
- اسم المشترك
- اسم الزوجة/المستفيد الآخر ← جديد
- عنوان المراسلة
- البريد الإلكتروني
- تليفون عمل + منزل + موبايل ← عمل ومنزل جديدان
- رقم العقد + تاريخ التعاقد
- نوع الوحدة + السعة (2/4/6) ← جديد
- رقم الأسبوع
- الحالة

**التبويب 2: سجل الاستخدام**
- عدد الأسابيع المستخدمة إجمالاً
- مرات استخدام الذروة + السنوات
- جدول كل الزيارات (تاريخ من/إلى + حالة + وحدة)
- آخر زيارة + الزيارة القادمة
- طلبات الزيارة الجارية والتاريخية

**التبويب 3: الماليات**
- الأقساط: مدفوع / متبقي / متأخر
- صف لكل قسط: رقم + تاريخ استحقاق + المبلغ + الحالة
- الصيانة: جدول سنة × سنة + حالة السداد
- مبلغ الصيانة المقترح لسنة 2027 (مُحسَّب من السعة)

**التبويب 4: نموذج طلب الحجز الجديد**
بيانات pre-filled (للقراءة فقط):
- رقم العقد
- تاريخ التعاقد
- سعة الوحدة في العقد (2/4/6)
- نوع العقد (Chalet/Studio)

بيانات يملؤها العميل:
- التاريخ الأول المطلوب (من/إلى)
- البديل الأول (من/إلى) — اختياري
- البديل الثاني (من/إلى) — اختياري
- طلبات خاصة

موافقة إلزامية:
- ✅ **Checkbox 1:** "اطلعت ووافقت على التعليمات واللوائح الداخلية للاستخدام (18 بنداً)" — مع رابط لعرض النص
- ✅ **Checkbox 2:** "اطلعت ووافقت على قواعد والتزامات الحجز (12 قاعدة)" — مع رابط لعرض النص

زر "إرسال طلب الحجز" — مُعطَّل حتى يتم تعبئة التاريخ الأول + الموافقتين.

#### 5-ج: تحسين بوابة العميل العامة
```
GET /timeshare/public/my-visits          ← سجل الزيارات التاريخية
GET /timeshare/public/my-visit-request   ← الطلب الجاري
GET /timeshare/public/my-profile         ← ملف مبسط (بدون بيانات إدارية)
```

**Definition of Done المرحلة 5:**
- [ ] `GET /timeshare/contracts/{id}/profile` يرجع كل البيانات
- [ ] الواجهة: 4 تبويبات كاملة
- [ ] الواجهة: زر الإرسال مُعطَّل بدون Checkboxes
- [ ] الواجهة: pre-filled fields للقراءة فقط
- [ ] `pnpm --filter el-kheima type-check` → نظيف
- [ ] `pnpm --filter el-kheima test:frontend` → صفر failures

---

## 4. ترتيب التنفيذ الكامل

| # | المرحلة | Migration | الزمن التقديري | الأولوية |
|---|---|---|---|---|
| 1 | بداية الأسبوع السبت + Checkboxes موافقة | لا | 1-2 ساعة | عالية جداً |
| 2 | سعة الوحدة + المستفيد + هواتف + 3 تواريخ بديلة | نعم (01) | 3-4 ساعات | عالية |
| 3 | جدول مواسم الذروة + CRUD + endpoints | نعم (02) | 2-3 ساعات | متوسطة |
| 4 | قواعد الذروة في الـ service | لا | 2-3 ساعات | متوسطة |
| 5 | ملف العميل الكامل (Backend + Frontend) | لا | 4-6 ساعات | متوسطة |

**المراحل 1+2 في branch واحد.**
**المراحل 3+4 في branch ثاني (بعد merge المرحلة 2).**
**المرحلة 5 في branch ثالث (مستقل عن 3+4، يمكن تنفيذها بالتوازي).**

---

## 5. قواعد التنفيذ الإلزامية

### 5.1 معمارية الكود
```
crud.py       ← DB فقط — is_date_range_peak / get_contract_peak_usage_stats
services.py   ← Business logic — قواعد الذروة / التحقق من السعة
timeshare_engine.py ← Pure Python — check_peak_overlap (بدون DB)
router.py     ← HTTP layer فقط
```

### 5.2 قواعد لا تُكسر
- الأموال = `Decimal` دايماً — مفيش `float`
- كل `SELECT FOR UPDATE` + `.populate_existing()` للعمليات المتزامنة
- `business_today(settings.TIMEZONE)` بدل `date.today()`
- PII جديد (لو أضفنا رقم هوية إضافي) = `EncryptedString`
- كل migration جديدة → `alembic heads` أول + `--autogenerate` + مراجعة يدوية

### 5.3 Checklist الـ PR

```
☐ pytest tests/ -v -k "timeshare" → صفر failures
☐ alembic heads → head واحد
☐ type-check نظيف (backend + frontend)
☐ لا N+1 queries جديدة
☐ لا API contracts مكسورة
☐ لا dead code أو imports غير مستخدمة
☐ التوثيق محدّث لو السلوك تغيّر (PROJECT_STATUS.md + wagdy.md)
```

---

## 6. ملف تعميم الصيانة — الأرقام الرسمية 2026

مصدر: `مصروفات الصيانة عام 2026 - منتجع الخيمة - شرم الشيخ.pdf`

```python
# backend/app/modules/timeshare/services.py
MAINTENANCE_FEES_2026 = {
    # عقود قبل 1 مايو 2026
    "before_may_2026": {
        2: Decimal("1750"),
        4: Decimal("2000"),
        6: Decimal("2500"),
    },
    # عقود من 1 مايو 2026
    "from_may_2026": {
        2: Decimal("2000"),
        4: Decimal("3000"),
        6: Decimal("4000"),
    },
}
```

**ملاحظة:** هذه الأرقام لـ 2026 فقط — الزيادات المستقبلية بقرار من لجنة فض المنازعات بغرفة المنشآت الفندقية ووزارة السياحة المصرية، وليست نسبة سنوية ثابتة. Mohamed يُدخل الأرقام الجديدة يدوياً عبر تحديث `maintenance_fee` في كل عقد أو عبر bulk update.

---

## 7. مؤشرات النجاح (Definition of Done الكاملة)

```
☐ المرحلة 1: أسبوع 28 يبدأ السبت + طلب بدون checkbox → 400
☐ المرحلة 2: عقد بـ unit_capacity=4 + 3 تواريخ بديلة → يُخزَّن ويُعرَض
☐ المرحلة 3: Mohamed يدخل موسم ذروة + يُقرأ في التحقق
☐ المرحلة 4: طلب ذروة ثاني في نفس السنة → 400 بـ رسالة واضحة
☐ المرحلة 5: ملف العميل 4 تبويبات + واجهة بوابة العميل كاملة
☐ pytest tests/ -v → صفر failures كاملة (مش كـ"timeshare" بس)
☐ pnpm run type-check:all → نظيف
☐ pnpm run build:all → ناجح
☐ PROJECT_STATUS.md + wagdy.md محدَّثَيْن
```

---

**آخر تحديث:** 2026-08-09
**الفرع المقترح للبدء:** `feature/timeshare-01-phase1-weekday-checkboxes`
