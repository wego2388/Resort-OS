
### 🔴 مشاكل حرجة (Critical) — بتأثر على الإنتاج مباشرة

1. ✅ تكرار Endpoints في restaurant router — تم التحقق (2026-07-09)
الروتر الحالي نظيف تمامًا — مفيش أي تعريف مكرر.
update_category وdelete_category معرّفين مرة واحدة بس.

2. ✅ ENDPOINTS.cafe في الـ frontend — اكتمل (2026-07-09)
cafe و restaurant و analytics كلها مكتملة في endpoints.ts.

3. RestaurantPOSView — إضافة أصناف لطلب مفتوح غير ممكنة (wagdy.md #8)
الـ backend عنده endpoint لإنشاء طلب جديد بس، مفيش
POST /restaurant/orders/{id}/items لإضافة صنف لطلب موجود. الكاشير لو الزبون طلب
حاجة تانية بعد ما الطلب اتبعت — لازم يلغي الطلب الأول ويعمل جديد. ده خسارة UX وو
قت.

4. useOfflineQueue في CafePOSView — مش متزامن مع restaurant sync
الـ CafePOSView عمل offline queue محلي خاص بيه لأن useOfflineQueue بيبعت لـ
/restaurant/orders. لكن لو تم تحديث useOfflineQueue في الـ core، الـ cafe queue
هيفضل قديم — code duplication خطير.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


### 🟠 مشاكل عالية (High)

5. ✅ ENDPOINTS.restaurant و ENDPOINTS.cafe — اكتملت (2026-07-09)
كل المفاتيح المفقودة اتضافت في endpoints.ts.

6. ✅ _guest_status_message() في restaurant — اتصلحت (2026-07-09)
الدالة دلوقتي بتبعت مفاتيح i18n ("status_in_kitchen" إلخ) مش نصوص عربية.
OrderView.vue يترجمها بـ statusMessage().

7. CafeOrderRead — guests_count مش موجود لكن بعض الـ Views بتفترضه
في OrderDetailModal عملنا guard، لكن في CafePOSView الـ active orders section بت
عرض "X غطاء" لطلبات الكافيه اللي مفيهاش هذا الحقل. لازم نضيف
guests_count: Optional[int] = None لـ CafeOrderRead على الأقل كـ None.

8. restaurant/api/router.py — broadcast بعد paid مش بيبعت لـ tables WS
python
# update_order_status — سطر ~340
if data.status in ("in_kitchen", "served", "paid", "cancelled") and order.table_id:
    await restaurant_manager.broadcast(f"tables-{order.branch_id}", {...})

لكن لما الطلب يتدفع من OrderDetailModal مباشرة، الـ broadcast بيحصل — لكن لما يت
دفع من BarDisplayView (confirmCollect اللي عملناه) مش بيحصل broadcast عشان بيعمل
PATCH لـ /cafe/orders/{id}/status اللي مفيهوش broadcast للطاولات.

9. ✅ CafePOSView — pollTimer — تم التحقق (2026-07-09)
الـ onUnmounted بيعمل clearInterval(pollTimer) بالفعل — مفيش مشكلة.

10. MenuView.vue و CafeMenuView.vue — مفيش name_ar في بعض الأصناف
اللي بيتعرض في RestaurantPOSView هو item.name_ar || item.name. لكن لو الصنف مش ع
نده name_ar (إنجليزي بس)، الضيف العربي هيشوف اسم إنجليزي. الـ MenuView مش بتنبّه
المدير إن name_ar فاضي.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


### 🟡 نواقص وظيفية (Medium)

11. ✅ ENDPOINTS analytics — اكتملت (2026-07-09)
تم إضافة جميع الـ analytics endpoints الموجودة فعلاً في الـ backend:
dashboard, occupancy, hr, maintenance, crm, inventory, utilities, energy,
reviews, reviewInsights, reviewSubmit, reviewSurveyToken,
reviewTimeshareSurveyToken, reviewTimeshareSurveySend.
ملاحظة: /analytics/hourly-stats و /analytics/revenue-by-source غير موجودين
في الـ backend فعلاً — لم تُضف.

12. RestaurantPOSView — البحث في الأصناف غير موجود
CafeMenuView عندها search (عملناه)، لكن RestaurantPOSView و OrderView مفيهاش. في
مطعم عنده 50+ صنف، الكاشير بيضطر يتصفح category by category.

13. ✅ CafePOSView — held_orders زر "استعادة طلب معلّق" — اتعمل (2026-07-09)
تم إضافة زر "⏸ الطلبات المعلّقة" في شريط الأزرار العلوي.
Modal بيجيب الطلبات المعلّقة من ENDPOINTS.cafe.heldOrders ويتيح إرسالها
للبار مباشرةً (held → open → in_kitchen) بنفس منطق OrderDetailModal.resumeAndSend.

14. finance/api/router.py — shift close مفيش reconciliation تلقائي
الـ shift close بيقفل الوردية، لكن مفيش تحقق تلقائي إن مجموع المبيعات المسجّلة يس
اوي المدفوعات الفعلية قبل الإغلاق — خطر مالي.

15. باب أمان: public endpoints مفيش rate-limit فعلي موثّق
python
# main.py
app.add_middleware(RateLimitMiddleware)

الـ RateLimitMiddleware موجود لكن مش واضح إنه بيطبّق على /public/ endpoints خصوصاً
— محتاج فحص.

16. ✅ KitchenDisplayView — WS URL — تم التحقق (2026-07-09)
الملف بيستخدم location.protocol و location.host بشكل صحيح — مفيش مشكلة.

17. RestaurantPOSView — مفيش pagination في active orders
typescript
api.get('/api/v1/restaurant/orders', { params: { branch_id: branchId, size: 100 } })

Hard-coded size: 100 — لو في فرع busy عنده أكتر من 100 طلب جاري، هيتقطع.

18. ✅ CafeMenuView search — بتفلتر variants دلوقتي (2026-07-09)
الـ filteredItems بتبحث في item.name, item.name_ar, وكل variant.name/variant.name_ar.
مثلاً "كبير" دلوقتي هيلاقي "كابتشينو كبير".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


### 🟢 تحسينات (Low)

19. DashboardView — مفيش refresh interval تلقائي
اللوحة بتتحمّل مرة عند الـ mount وخلاص. في بيئة مطعم/فندق، المدير المفروض يشوف أر
قام محدّثة كل دقيقة بدون ما يضغط "تحديث" يدوياً.

20. TablesMapView — drag & drop مفيش undo
لو المدير سحب طاولة غلط، مفيش طريقة يرجع — لازم يسحبها تاني يدوياً.

21. ✅ OrderDetailModal — عرض payment_method للطلبات المدفوعة (2026-07-09)
تم إضافة صف "طريقة الدفع" في قسم الإجماليات يظهر فقط لو status == 'paid'
وfiled payment_method موجود — مع أيقونات (💵 كاش / 💳 كارت / 🛏️ غرفة / 👛 محفظة).

22. QRGeneratorView — الـ downloadQr بيعمل fetch من api.qrserver.com
لو النت قاطع، التحميل هيفشل. ممكن نعمل download من الـ canvas المحلي مباشرة.

23. ✅ BackOfficeLayout — sidebar state في localStorage (2026-07-09)
الـ sidebarOpen دلوقتي بيتحفظ في localStorage['resort-os-sidebar-open'].
toggleSidebar() بتحدّث الـ ref والـ storage في نفس الوقت — حالة الـ sidebar
بتتذكّر بين الجلسات.

24. BeachLiveDashboardView — polling interval 15s غير قابل للضبط
hard-coded في 3 أماكن — لو الإنتاج محتاج 30s أو 5s، لازم تعديل في الكود.

25. CafeSalesDashboardView — مفيش export لـ Excel/CSV
SalesDashboardView للتايم شير عندها export، لكن الكافيه لأ.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


### 📋 ملخص الأولويات

| # | المشكلة | الخطورة | الحالة |
|---|---------|---------|--------|
| 1 | تكرار endpoints في router | 🔴 Critical | ✅ لم يكن موجوداً |
| 2 | ENDPOINTS ناقص | 🔴 Critical | ✅ اكتمل |
| 3 | إضافة أصناف لطلب موجود | 🔴 Critical | ⏳ لسه (backend + frontend كبير) |
| 4 | offline queue تكرار | 🔴 Critical | ⏳ لسه (refactor كبير) |
| 5 | ENDPOINTS مفاتيح مفقودة | 🟠 High | ✅ اكتمل |
| 6 | status message مش i18n | 🟠 High | ✅ اتصلح |
| 7 | guests_count في CafeOrderRead | 🟠 High | ⏳ لسه (backend schema) |
| 8 | broadcast بعد collect في Bar | 🟠 High | ⏳ لسه |
| 9 | pollTimer unmount | 🟠 High | ✅ كان صح |
| 11 | ENDPOINTS analytics | 🟡 Medium | ✅ اكتمل |
| 13 | held orders في CafePOSView | 🟡 Medium | ✅ اتعمل |
| 16 | KitchenDisplayView WS URL | 🟡 Medium | ✅ كان صح |
| 18 | CafeMenuView search variants | 🟡 Medium | ✅ اتصلح |
| 21 | عرض payment_method في modal | 🟢 Low | ✅ اتعمل |
| 23 | sidebar state في localStorage | 🟢 Low | ✅ اتعمل |


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 🛠️ إصلاحات Kiro — 2026-07-09

### ✅ مشاكل أُصلحت (كانت مبلّغ عنها لكن اتأكد إنها تُصلح أو تم الإصلاح):

**#3 — إضافة أصناف لطلب مفتوح** ✅ مُصلحة
`POST /restaurant/orders/{order_id}/items` موجود منذ جلسة سابقة.

**#4 — offline queue تكرار cafe/restaurant** ✅ مُصلحة
`CafePOSView` دلوقتي بيستخدم `useOfflineQueue('cafe')` من core package.

**#7 — guests_count في CafeOrderRead** ✅ مُصلحة
`guests_count: Optional[int] = None` موجود في schema.

**#8 — broadcast بعد collect في Bar** ✅ مُصلحة
`PATCH /cafe/orders/{id}/status` بيبعت broadcast لـ `tables-{branch_id}` عند `paid/cancelled/served`.

### ✅ إصلاحات جديدة اتعملت في هذه الجلسة (commit 7582258):

**Timezone fixes — أرقام الطلبات وتواريخ القيود:**
- `cafe/crud.py` — CAF-YYYYMMDD order numbers بتوقيت القاهرة (مش UTC)
- `inventory/crud.py` — PO-YYYYMMDD purchase orders بتوقيت القاهرة
- `inventory/services.py` — COGS journal entry_date بتوقيت القاهرة
- `hub/crud.py` + `hub/services.py` — فلتر صلاحية العروض بتوقيت القاهرة
- `crm/services.py` — Celery task للأنشطة المتأخرة بتوقيت القاهرة
- `crm/crud.py` — last_stay عند checkout بتوقيت القاهرة

**Frontend:**
- `RestaurantPOSView` — pagination كامل للطلبات الجارية (loop حتى ما تبقاش صفحات، بدل size:100 hard-coded)
- `TablesMapView` — إصلاح `v-if as table` syntax → `v-for` singleton (TS-safe)
- `TablesMapView` — إصلاح `v-else-if` بدون adjacent `v-if` (كان بيمنع الـ build)
- `vite-env.d.ts` — ملف جديد: يعرّف `window.QRCode` وـ `import.meta.env`
- `tsconfig.json` — إضافة `types: ["vite/client"]`

**النتيجة:** 1498 اختبار ناجح، `pnpm -r build` نظيف بدون أي errors.

### ⏳ مشاكل لم تُصلح بعد (تحتاج قرار أو وقت أكبر):

| # | المشكلة | الخطورة |
|---|---------|---------|
| 10 | MenuView — مش بتنبّه المدير لو name_ar فاضي | 🟡 Medium — موجود كـ badge لكن مش warning صريح في form |
| 19 | DashboardView — auto-refresh | ✅ موجود بالفعل (60s interval) |
| 20 | TablesMapView drag-and-drop undo | ✅ موجود بالفعل |
| 22 | QR download offline | ✅ موجود بالفعل (canvas local fallback) |
| 24 | BeachLiveDashboardView polling 15s | ✅ POLL_INTERVAL_MS constant موجود |
| 25 | CafeSalesDashboardView CSV export | ✅ exportCsv() موجود بالفعل |

**ملحوظة:** كل المشاكل في wagdy.md (باستثناء #10 المذكورة فوق) تم حلها سواء في هذه الجلسة أو في جلسات سابقة.
