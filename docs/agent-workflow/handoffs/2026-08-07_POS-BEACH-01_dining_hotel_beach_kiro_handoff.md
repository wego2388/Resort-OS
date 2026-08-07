# Handoff — POS-BEACH-01: Beach Map + Hotel B2B in Dining POS Cashier

**التاريخ:** 2026-08-07
**الـ commit:** `155afcc`
**الفرع:** `claude/CX-02C-frontend-auth-bootstrap`
**الحالة:** مرفوع ✅ — **لم يُنشر على VPS بعد (ينتظر إذن Mohamed)**

---

## ما تغيّر ولماذا

### المشكلة الجذرية
الباك إند كان يرجّع `hotel_name` في `OrderRead`، لكن الفرونت كان يبحث عن `b2b_hotel_name` — mismatch صامت يجعل اسم الفندق لا يظهر في أي مكان في الـ POS.

### الإصلاحات (5 مشاكل + فيتشرين جديدين)

**١. `hotel_name` mismatch (الأهم)**
- `types.ts`: `b2b_hotel_name` → `hotel_name` في `ActiveOrder` و`DiningOrderDetail`
- `DiningOrderDetailModal.vue` + `POSActiveOrdersWorkspace.vue` + `ShiftDashboardView.vue`: كلها تعرض `hotel_name` الصح الآن

**٢. `beach_location_label` في modal التفاصيل**
- `tableLabel` computed في `DiningOrderDetailModal` يتحقق `beach_location_id` أولاً ويرجّع `beach_location_label` — كان موجوداً لكن الـ template كان يستخدم الاسم الخطأ للفندق فأخفى الـ label

**٣. Cash presets خاطئة**
- `money.ts`: `steps` من `[50_000, 100_000, 200_000, 500_000]` إلى `[5_000, 10_000, 20_000, 50_000]` قرش
- النتيجة: presets الآن 50ج / 100ج / 200ج / 500ج — مناسب لفواتير الدايننج

**٤. i18n مفقود**
- `ar.json` + `en.json`: أضيف `workspaceNav.beachMap` — كان يكسر `i18n validation` ويفشل الـ frontend tests

**٥. ShiftDashboard لا يعرض الفندق**
- `ShiftDashboardView.vue`: `LiveOrder` type أضيف له `hotel_name`، وبطاقة كل طلب تعرضه الآن

**فيتشرين جديدين (كانوا موجودين في الكود لكن غير مكتملين):**
- `POSBeachMapWorkspace.vue`: خريطة الشمسيات التفاعلية في الـ POS
- `POSHotelSelector.vue`: اختيار الفندق المتعاقد من الـ cart

---

## الملفات المتأثرة

### Backend (جديد/معدّل)
| الملف | التغيير |
|---|---|
| `backend/alembic/versions/a3f9c1d2e4b5_...py` | migration: b2b_contract_id + beach_location_id على dining_orders |
| `dining/models.py` | إضافة العمودين على `DiningOrder` |
| `dining/schemas.py` | `OrderCreate` + `OrderRead` يقبلوا/يرجّعوا الحقلين + `hotel_name` |
| `dining/api/router.py` | `_enrich_order` + `_enrich_order_list` + GET b2b-contracts + تقرير hotel-consumption |
| `dining/crud.py` | `get_b2b_contracts_for_dining` |
| `test_dining_router_coverage.py` | 9 tests جديدة (TestHotelB2BFeature + TestBeachLocationFeature) |

### Frontend (جديد/معدّل)
| الملف | التغيير |
|---|---|
| `dining-pos/types.ts` | `b2b_hotel_name` → `hotel_name` في ActiveOrder + DiningOrderDetail |
| `DiningOrderDetailModal.vue` | hotel_name الصح |
| `POSActiveOrdersWorkspace.vue` | hotel_name في كارت الطلب |
| `ShiftDashboardView.vue` | hotel_name في LiveOrder + عرض في بطاقة |
| `dining-pos/money.ts` | cash presets steps صُحّحت |
| `locales/ar.json` + `en.json` | workspaceNav.beachMap |
| `POSBeachMapWorkspace.vue` | جديد — خريطة الشمسيات |
| `POSHotelSelector.vue` | جديد — اختيار الفندق في الـ cart |

---

## نتائج الاختبارات

```
Backend (dining router coverage):  50/50 passed ✅
Frontend tests:                    95/95 passed ✅
TypeScript type-check:             نظيف ✅
Alembic heads:                     a3f9c1d2e4b5 (head واحد) ✅
i18n validation:                   نظيف ✅
```

---

## توافق Schema والـ API

- **backward compatible تماماً** — كل الحقول الجديدة nullable، أي طلب قديم بدون `b2b_contract_id`/`beach_location_id` يشتغل عادي
- migration آمنة: `ADD COLUMN ... nullable` + index — صفر downtime
- `hotel_name` و`beach_location_label` computed في الراوتر (مش عمود) — مفيش migration للحذف

---

## خطوات النشر على الـ VPS (ينتظر إذن Mohamed)

1. اتبع `DEPLOYMENT.md §5` المعتاد
2. بعد `alembic upgrade head` هتُطبَّق migration `a3f9c1d2e4b5`:
   - `ADD COLUMN b2b_contract_id` + index
   - `ADD COLUMN beach_location_id` + index + partial unique index
3. مفيش حاجة تانية — الكود متوافق مع `52f4544e50d2` (الحالي على الـ VPS)

**rollback:** `alembic downgrade -1` يحذف العمودين والـ indexes — لا تأثير على الطلبات الموجودة

---

## مخاطر متبقية

| المخاطرة | الأثر | التخفيف |
|---|---|---|
| `POSBeachMapWorkspace` لم يُختبر بـ E2E | مجرد UI | يُختبر يدوياً قبل النشر |
| migration على DB الإنتاج بدون downtime | منخفض (ADD COLUMN nullable) | متحقق في tests |
| `branchId = null` في WS URL | connection وهمي على `/ws/map/0` | موثّق في المراجعة كـ نقطة ٤ — يحتاج إصلاح مستقبلي |

---

## commit/push/deploy

- ✅ commit: `155afcc`
- ✅ push: `origin/claude/CX-02C-frontend-auth-bootstrap`
- ⏳ deploy: **ينتظر إذن صريح من Mohamed**
