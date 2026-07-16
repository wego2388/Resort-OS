# نواقص الفرونت إند — El Kheima Beach Resort OS

> **آخر تحديث:** 2026-07-15 (جلسة الليل — Kiro CLI)
> **المنهجية:** مقارنة فعلية بين كل `@router.(get|post|patch|put|delete)` في الباك إند
> وكل `api.(get|post|patch|put|delete)` في الفرونت إند — مش تخمين.
> **TypeScript check:** ✅ صفر أخطاء (2026-07-15).
> **Hardcoded API strings:** ✅ صفر — كل الـ views + components تستخدم `ENDPOINTS.*` حصراً.
> **🎉 كل بنود FRONTEND_GAPS منجزة بالكامل — صفر gaps متبقية.**

---

## ✅ اتنجز (2026-07-14 — جلسة Kiro CLI)

| الملف | ما اتعمل |
|---|---|
| `DashboardView.vue` | إصلاح import مكرر + حذف onMounted المكرر + إضافة onUnmounted الناقص + migration KPI cards لـ StatCard DS component + revenueTrend computed |
| `DiningMenuView.vue` | إضافة KDS Screens tab كامل (load/create/edit/delete + modal) + إصلاح Tables tab من `v-else` لـ `v-else-if` + loadKdsScreens في onMounted |
| `endpoints.ts` | إضافة `timeshare` + `maintenance` + `leasing` blocks كاملة (30+ endpoint جديد) |
| `TimeshareView.vue` | إضافة ENDPOINTS import + استبدال كل hardcoded `/api/v1/timeshare/*` و survey-token strings بـ ENDPOINTS constants |
| `MaintenanceView.vue` | إضافة ENDPOINTS import + استبدال كل hardcoded `/api/v1/maintenance/*` strings بـ ENDPOINTS constants |
| `dining/services.py` | إضافة `split_bill` (P-07) — تقسيم الفاتورة على أكثر من طريقة دفع |
| `dining/api/router.py` | إضافة `POST /dining/orders/{id}/split-bill` endpoint (كاشير+) |
| `endpoints.ts` | إضافة `dining.orderSplitBill` |
| `DiningOrderDetailModal.vue` | إضافة UI كامل لـ Split Bill — panel مطوي، توزيع تلقائي للباقي، تحقق من المجموع |
| `tests/test_api/test_dining_http.py` | إضافة `TestSplitBillHTTP` (5 tests) — 86/86 passed |
| `dining/services.py` | إضافة `split_bill` (P-07) — تقسيم الفاتورة على أكثر من طريقة دفع |
| `dining/api/router.py` | إضافة `POST /dining/orders/{id}/split-bill` endpoint (كاشير+) |
| `endpoints.ts` | إضافة `dining.orderSplitBill` |
| `DiningOrderDetailModal.vue` | إضافة UI كامل لـ Split Bill — panel مطوي، توزيع تلقائي للباقي، تحقق من المجموع |
| `tests/test_api/test_dining_http.py` | إضافة `TestSplitBillHTTP` (5 tests) — 86/86 passed |

---

## ✅ اتنجز اليوم (2026-07-14)

| الملف | ما اتعمل |
|---|---|
| `packages/core/src/api/endpoints.ts` | أُضيف 80+ endpoint — finance/hr/inventory/pms/hub كاملين، حُذف pms القديم المكرر |
| `FinanceView.vue` | tab "ميزانية تجريبية" جديد (trial-balance + group_by_parent) + زرار Void Payment في drill-down الوردية مع modal سبب |
| `BookingsView.vue` | زرار "إلغاء حجز" لـ pending/confirmed — desktop table + mobile cards |
| `ShiftPanel.vue` | حُذفت مراجع `varianceOverride`/`pendingClosePayload` المتبقية من force_close المُلغى |
| `HRView.vue` | tab "طلبات الإجازة" (leave-requests + approve/reject) + tab "إعدادات الرواتب" (social-insurance form + tax-brackets عرض) |
| `InventoryView.vue` | section "طلبات الشراء" (purchase-requests: create + approve/reject/convert) |
| `DashboardView.vue` | 4 analytics sub-cards جديدة (HR / صيانة / CRM / مخزون) مربوطة بـ ENDPOINTS.analytics |
| `tests/test_api/test_finance_http.py` | تحديث TestCloseShiftVarianceOverrideHTTP + test_close_shift_large_cash_variance_closes_with_warning لتعكس قرار إلغاء force_close — 91/91 passed |

---

## ✅ اتنجز (2026-07-14 — جلسة المساء الثانية)

| الملف | ما اتعمل |
|---|---|
| `ReceptionView.vue` | **جديد** — شاشة الاستقبال الكاملة: KPI stats + خريطة الغرف + check-in/out modals + حجز جديد + Night Audit |
| `router/index.ts` | `receptionist` → `/ops/reception` + route + sidebar nav |
| `packages/core/src/api/endpoints.ts` | إضافة 40+ endpoint جديد: `pms_extra` / `auth.changePassword` / `hr_extra` / `settings` / `permissions` / `finance_eta` / `leasing` sub-paths / `dining` recipe lines / `hub.blogPost` / `leasing.contractCashLogs` / `leasing.contractApplyPenalties` |
| **كل الـ views** | **صفر hardcoded `/api/v1/` strings** — ترحيل كامل لـ 40+ استدعاء في 15 ملف: `EInvoiceView` / `SalesDashboardView` / `HubManagementView` / `DashboardView` / `TimeshareView` / `SettingsView` / `HRView` / `LeasingView` / `RecipesView` / `PermissionsView` / `BookingsView` / `RoomsView` / `HousekeepingView` / `ReceptionView` / `ProfileView` / `LeavesView` / `AttendanceView` / `PayrollView` / `BeachPOSView` |
| **TypeScript check** | ✅ **صفر أخطاء** |

---



| الملف | ما اتعمل |
|---|---|
| `HRView.vue` | إصلاح merge bug — إضافة `</div></template>` الناقصين في نهاية الملف + تصحيح TS error في `row-key` جدول شرائح الضريبة (`min_income` كـ key) — صفر أخطاء TypeScript ✅ |
| `ReceptionView.vue` | **جديد** — شاشة الاستقبال الكاملة: KPI stats (دخل/خروج/وصول/غرف/تنظيف) + خريطة الغرف + قائمة وصولات اليوم + check-in modal + check-out modal + حجز جديد + Night Audit (admin+) + ربط بالـ router |
| `router/index.ts` | `receptionist` → `/ops/reception` + route جديد `/ops/reception` + sidebar nav item |
| `packages/ui/src/components/ChartWrapper.vue` | **جديد** — Chart.js + vue-chartjs wrapper، 5 أنواع (bar/line/area/pie/doughnut)، DS colors، loading/error/empty states |
| `packages/ui/src/components/FiltersPanel.vue` | **جديد** — inline + drawer variants، 5 أنواع fields، active badge، reset |
| `packages/ui/src/components/Combobox.vue` | **جديد** — searchable select، keyboard nav كامل، async search debounce، groups، Teleport |
| `packages/ui/src/components/Autocomplete.vue` | **جديد** — free-text input مع suggestions، debounce، keyboard nav |
| `packages/ui/src/components/Wizard.vue` | **جديد** — multi-step form، step indicator، validate prop، completed/active/upcoming states |
| `packages/ui/src/components/CommandPalette.vue` | **جديد** — fuzzy search، recent items، groups، Ctrl+K، keyboard nav، Teleport z-[200] |
| `packages/ui/src/components/VirtualTable.vue` | **جديد** — windowed rendering بدون مكتبة خارجية، IntersectionObserver + ResizeObserver، overscan |
| `packages/ui/src/index.ts` | أُضيفت الـ 7 exports الجديدة + types |
| `packages/ui/package.json` | أُضيف `chart.js@^4.5.1` + `vue-chartjs@^5.3.4` |
| `BackOfficeLayout.vue` | أُضيف CommandPalette + زرار Ctrl+K في topbar |
| `DashboardView.vue` | تصليح `</script>` المفقود + `quickLinks` + `todayLabel` في script |
| **TypeScript check** | ✅ **صفر أخطاء** |

---

## 🔴 غائب بالكامل — باك إند موجود، شاشة مفيهاش خالص

> **ملاحظة 2026-07-14:** معظم هذه البنود **اتنجزت** في جلسات سابقة. المتبقي الفعلي موثّق أدناه.

### Finance — ✅ منجز بالكامل
| Endpoint | الوصف | الحالة |
|---|---|---|
| `GET /finance/journal-entries` / `GET /{id}` | عرض قيود اليومية مباشرة | ✅ tab "قيود اليومية" في FinanceView |
| `GET /finance/revenue-audit-logs` | سجل تدقيق الإيرادات | ✅ tab "audit-log" في FinanceView |
| `GET /finance/cost-centers` | مراكز التكلفة (report) | ✅ tab "مراكز التكلفة" في FinanceView |

### Inventory — ✅ منجز بالكامل
| Endpoint | الوصف | الحالة |
|---|---|---|
| `GET /inventory/products/barcode-labels` | طباعة باركود المنتجات | ✅ منجز — modal تحميل PDF في InventoryView |

### HR — ✅ منجز بالكامل
| Endpoint | الوصف | الحالة |
|---|---|---|
| `GET/POST /hr/rota/swap-requests` / approve | ✅ موجود في Rota tab كشريط تنبيه | ✅ |
| `GET/POST /hr/shifts` | ✅ منجز في إعدادات HR | ✅ |
| `GET/POST /hr/departments` | ✅ منجز في إعدادات HR | ✅ |
| `GET/PATCH /hr/employees/{id}/link-user` | ربط موظف بحساب مستخدم | ✅ منجز |
| `GET/POST /hr/employees/{id}/allowances` | بدلات الموظف — قائمة البدلات الحالية | ✅ منجز |
| `GET /hr/me/leave-balance-monthly` | رصيد إجازة الشهر (self-service portal) | ✅ موجود في LeavesView portal |

### Dining — ✅ منجز بالكامل
| Endpoint | الوصف | الحالة |
|---|---|---|
| `GET /dining/reports/food-cost` | تقرير تكلفة الطعام الموحّد (كل المنافذ) | ✅ منجز — tab "كل المنافذ" في FoodCostReportView |

### Timeshare — ✅ منجز بالكامل
| Endpoint | الوصف | الحالة |
|---|---|---|
| `GET /timeshare/upcoming-visits` | ✅ منجز في DashboardView | ✅ |

---

## 🟡 موجود في الشاشة لكن مش في `endpoints.ts`

> ✅ **هذا القسم منجز بالكامل** — كل الـ hardcoded strings في جميع الشاشات والـ components اتنقلت لـ `ENDPOINTS` constants.
> آخر تحديث: 2026-07-14 — **صفر** `/api/v1/` hardcoded strings في أي ملف `.vue` أو `.ts`.

---

## 🟠 شاشات فيها وظائف ناقصة (الشاشة موجودة بس بعض الأزرار/الـ tabs مش شغالة)

### FinanceView.vue
- ~~**Balance Sheet tab**~~ ✅ **منجز** — tab "المركز المالي" + `loadBalanceSheet()`
- ~~**قواعد الخصم**~~ ✅ **منجز** — tab "قواعد الخصم" + create/edit/toggle
- ~~**أسعار الصرف**~~ ✅ **منجز** — tab "أسعار الصرف" + add/edit
- ~~**إلغاء دفعة**~~ ✅ **منجز** — زرار Void في drill-down الوردية + modal سبب

### HRView.vue
- ~~**Rota / جدول المناوبات**~~ ✅ **منجز** — grid أسبوعي كامل + assignments + templates + swap-requests
- ~~**إعدادات الرواتب**~~ ✅ **منجز** — tab "إعدادات الرواتب" (social-insurance + tax-brackets)

### InventoryView.vue
- ~~**طلبات الشراء**~~ ✅ **منجز** — create + approve/reject/convert
- ~~**جرد المخزون**~~ ✅ **منجز** — tab جرد المخزون (create + submit + approve)

### HubManagementView.vue
- ~~**موافقة/رفض الحجوزات الأونلاين**~~ ✅ **منجز** — زرار confirm + cancel

### BookingsView.vue (ops)
- ~~**إلغاء حجز**~~ ✅ **منجز** — زرار إلغاء (pending/confirmed)

---

## 🔵 ناقص في `endpoints.ts` (شاشات موجودة بتكلمه مباشرة)

هذه entries ممكن تُضاف لـ `packages/core/src/api/endpoints.ts` لتوحيد المسارات:

```typescript
// Finance — missing from endpoints.ts
finance: {
  // ...existing...
  discounts: '/api/v1/finance/discounts',
  discount: (id: number) => `/api/v1/finance/discounts/${id}`,
  exchangeRates: '/api/v1/finance/exchange-rates',
  journalEntries: '/api/v1/finance/journal-entries',
  folios: '/api/v1/finance/folios',
  folio: (id: number) => `/api/v1/finance/folios/${id}`,
  folioCharges: (id: number) => `/api/v1/finance/folios/${id}/charges`,
  folioPayments: (id: number) => `/api/v1/finance/folios/${id}/payments`,
  folioSettle: (id: number) => `/api/v1/finance/folios/${id}/settle`,
  folioStatementPdf: (id: number) => `/api/v1/finance/folios/${id}/statement/pdf`,
  periods: '/api/v1/finance/periods',
  periodClose: (y: number, m: number) => `/api/v1/finance/periods/${y}/${m}/close`,
  reportsTrialBalance: '/api/v1/finance/reports/trial-balance',
  reportsBalanceSheet: '/api/v1/finance/reports/balance-sheet',
  revenueAuditLogs: '/api/v1/finance/revenue-audit-logs',
  paymentVoid: (id: number) => `/api/v1/finance/payments/${id}/void`,
  costCenters: '/api/v1/finance/cost-centers',
  bankAccounts: '/api/v1/finance/bank-accounts',
  bankAccount: (id: number) => `/api/v1/finance/bank-accounts/${id}`,
  bankAccountStatementLines: (id: number) => `/api/v1/finance/bank-accounts/${id}/statement-lines`,
  bankAccountAutoMatch: (id: number) => `/api/v1/finance/bank-accounts/${id}/statement-lines/auto-match`,
  depreciationEntries: '/api/v1/finance/depreciation/entries',
  depreciationRun: '/api/v1/finance/depreciation/run',
  incomeStatement: '/api/v1/finance/reports/income-statement',
}

// HR — missing from endpoints.ts
hr: {
  // ...existing...
  leaveTypes: '/api/v1/hr/leave-types',
  leaveBalanceMonthly: '/api/v1/hr/leave-balance-monthly',
  leaveRequests: '/api/v1/hr/leave-requests',
  leaveRequestApprove: (id: number) => `/api/v1/hr/leave-requests/${id}/approve`,
  leaveRequestReject: (id: number) => `/api/v1/hr/leave-requests/${id}/reject`,
  salaryAdvances: '/api/v1/hr/salary-advances',
  salaryAdvanceCancel: (id: number) => `/api/v1/hr/salary-advances/${id}/cancel`,
  advancePayments: '/api/v1/hr/advance-payments',
  penalties: '/api/v1/hr/penalties',
  penaltyTypes: '/api/v1/hr/penalty-types',
  leaderboard: '/api/v1/hr/leaderboard',
  attendancePolicy: '/api/v1/hr/attendance-policy',
  attendanceImport: '/api/v1/hr/attendance/import-excel',
  payrollRunLines: (id: number) => `/api/v1/hr/payroll-runs/${id}/lines`,
  payrollRunApprove: (id: number) => `/api/v1/hr/payroll-runs/${id}/approve`,
  payrollRunExcel: (id: number) => `/api/v1/hr/payroll/${id}/excel`,
  employeePayslip: (id: number) => `/api/v1/hr/employees/${id}/payslip`,
  rota: '/api/v1/hr/rota',
  rotaAssignments: '/api/v1/hr/rota/assignments',
  rotaTemplates: '/api/v1/hr/rota/templates',
  rotaTemplate: (id: number) => `/api/v1/hr/rota/templates/${id}`,
  rotaSwapRequests: '/api/v1/hr/rota/swap-requests',
  rotaSwapApprove: (id: number) => `/api/v1/hr/rota/swap-requests/${id}/approve`,
  departments: '/api/v1/hr/departments',
  configTaxBrackets: '/api/v1/hr/config/tax-brackets',
  configSocialInsurance: '/api/v1/hr/config/social-insurance',
  shifts: '/api/v1/hr/shifts',
  meLeaveBalanceMonthly: '/api/v1/hr/me/leave-balance-monthly',
}

// Inventory — missing from endpoints.ts
inventory: {
  // ...existing...
  categories: '/api/v1/inventory/categories',
  warehouses: '/api/v1/inventory/warehouses',
  purchaseRequests: '/api/v1/inventory/purchase-requests',
  purchaseRequest: (id: number) => `/api/v1/inventory/purchase-requests/${id}`,
  purchaseRequestApprove: (id: number) => `/api/v1/inventory/purchase-requests/${id}/approve`,
  purchaseRequestConvert: (id: number) => `/api/v1/inventory/purchase-requests/${id}/convert`,
  stockCounts: '/api/v1/inventory/stock-counts',
  stockCountSubmit: (id: number) => `/api/v1/inventory/stock-counts/${id}/submit`,
  stockCountApprove: (id: number) => `/api/v1/inventory/stock-counts/${id}/approve`,
  barcodeLabels: '/api/v1/inventory/products/barcode-labels',
}

// Analytics — missing from endpoints.ts
analytics: {
  // ...existing...
  hrSummary: '/api/v1/analytics/hr',
  maintenanceSummary: '/api/v1/analytics/maintenance',
  crmSummary: '/api/v1/analytics/crm',
  inventorySummary: '/api/v1/analytics/inventory',
}

// CRM — missing from endpoints.ts
crm: {
  // ...existing (customer-groups موجود)...
  leadCallNotes: (id: number) => `/api/v1/crm/leads/${id}/call-notes`,
  leadConvert: (id: number) => `/api/v1/crm/leads/${id}/convert`,
  leadDetails: (id: number) => `/api/v1/crm/leads/${id}/details`,
  customerInteractions: (id: number) => `/api/v1/crm/customers/${id}/interactions`,
  customerGroup: (id: number) => `/api/v1/crm/customers/${id}/group`,
  customerBlacklist: (id: number) => `/api/v1/crm/customers/${id}/blacklist`,
  interactions: '/api/v1/crm/interactions',
}

// Dining — missing from endpoints.ts
dining: {
  // ...existing...
  kdsScreens: '/api/v1/dining/kds-screens',
  foodCostReportAll: '/api/v1/dining/reports/food-cost',
  recipeLinesItem: (itemId: number) => `/api/v1/dining/items/${itemId}/recipe-lines`,
  recipeLine: (lineId: number) => `/api/v1/dining/recipe-lines/${lineId}`,
  variantRecipeLine: (lineId: number) => `/api/v1/dining/variant-recipe-lines/${lineId}`,
  variantRecipeLines: (variantId: number) => `/api/v1/dining/variants/${variantId}/recipe-lines`,
  outletOrdersSync: (outletId: number) => `/api/v1/dining/outlets/${outletId}/orders/sync`,
  foodCostExport: (outletId: number) => `/api/v1/dining/outlets/${outletId}/reports/food-cost/export`,
}

// Hub — missing from endpoints.ts
hub: {
  // ...existing...
  onlineBooking: (id: number) => `/api/v1/hub/online-bookings/${id}`,
  onlineBookingConfirm: (id: number) => `/api/v1/hub/online-bookings/${id}/confirm`,
  onlineBookingCancel: (id: number) => `/api/v1/hub/online-bookings/${id}/cancel`,
  blogPosts: '/api/v1/hub/blog/posts',
  contact: '/api/v1/hub/contact',
}

// Timeshare — missing from endpoints.ts
timeshare: {
  // ...existing...
  upcomingVisits: '/api/v1/timeshare/upcoming-visits',
  visit: (id: number) => `/api/v1/timeshare/visits/${id}`,
  contractCancel: (id: number) => `/api/v1/timeshare/contracts/${id}/cancel`,
  contractPdf: (id: number) => `/api/v1/timeshare/contracts/${id}/pdf`,
  contractTransferUnit: (id: number) => `/api/v1/timeshare/contracts/${id}/transfer-unit`,
  installmentPay: (id: number) => `/api/v1/timeshare/installments/${id}/pay`,
}

// PMS — missing from endpoints.ts
pms: {
  // ...existing...
  bookingCancel: (id: number) => `/api/v1/pms/bookings/${id}/cancel`,
  bookingCheckin: (id: number) => `/api/v1/pms/bookings/${id}/checkin`,
  bookingCheckout: (id: number) => `/api/v1/pms/bookings/${id}/checkout`,
  bookingEarlyLate: (id: number) => `/api/v1/pms/bookings/${id}/early-late`,
  roomStatus: (id: number) => `/api/v1/pms/rooms/${id}/status`,
  ratePlan: (id: number) => `/api/v1/pms/rate-plans/${id}`,
  nightAudit: '/api/v1/pms/night-audit',
  housekeepingTask: (id: number) => `/api/v1/pms/housekeeping/tasks/${id}`,
}
```

---

## ✅ مغطى بالكامل (للمرجع)

هذه الموديولات عندها تغطية فرونت إند كاملة أو شبه كاملة:

| الموديول | الشاشة | الحالة |
|---|---|---|
| Auth | LoginView, TwoFactorSetupView, ForgotPasswordView, ResetPasswordView | ✅ كامل |
| Beach POS | BeachPOSView, BeachMapView | ✅ كامل |
| Beach Admin | BeachAdminView (B2B, surge, settle, credit) | ✅ كامل |
| Beach Live | BeachLiveDashboardView | ✅ كامل |
| Dining POS | UnifiedPOSView, DiningOrderDetailModal | ✅ كامل |
| Dining KDS | DiningKDSView | ✅ كامل |
| Dining Menu | DiningMenuView (outlets/categories/items/extras/variants/tables) | ✅ كامل |
| Inventory | InventoryView (products/movements/PO/suppliers/warehouses/categories) | ✅ جيد |
| CRM | CRMView (customers/leads/groups/campaigns/activities/opportunities) | ✅ جيد |
| Timeshare | TimeshareView (contracts/visits/installments/units/waitlist) | ✅ جيد |
| Finance | FinanceView (checks/accounts/cost-centers/depreciation/bank-reconciliation/shifts) | ✅ جيد |
| HR | HRView (employees/payroll/attendance/leaves/advances/penalties/policy) | ✅ جيد |
| Leasing | LeasingView (contracts/payments/cash-logs) | ✅ كامل |
| Maintenance | MaintenanceView (assets/work-orders/schedules/parts) | ✅ كامل |
| Ops/PMS | RoomsView, BookingsView, HousekeepingView | ✅ جيد |
| Portal | AttendanceView, LeavesView, PayrollView, ProfileView | ✅ كامل |
| Shift | ShiftDashboardView + CashControlPanel + ShiftPanel | ✅ كامل |
| Permissions | PermissionsView | ✅ كامل |
| Settings | SettingsView | ✅ كامل |
| Hub | HubManagementView (offers/pages/online-bookings + confirm/cancel + blog/contact) | ✅ كامل |
| Analytics | AnalyticsView (revenue/occupancy/reviews/energy/utilities) | ✅ hr/maintenance/crm/inventory cards منجزة في Dashboard |
| Dashboard | DashboardView | ✅ analytics sub-cards منجزة (HR/صيانة/CRM/مخزون) |
| QR | QRGeneratorView | ✅ كامل |
| Food Cost | FoodCostReportView | ✅ جيد |
| Sales | SalesDashboardView | ✅ كامل |
| Reception | ReceptionView | ✅ جديد — check-in/out/new booking/night audit |
| **ENDPOINTS** | **كل الـ views + components** | ✅ **صفر hardcoded `/api/v1/` strings** |

---

## 📋 ترتيب الأولوية المقترح (محدّث 2026-07-14 — جلسة المساء)

### ✅ منجز بالكامل
- `finance/reports/trial-balance` ✅
- `POST /finance/payments/{id}/void` ✅
- `hub/online-bookings confirm/cancel` ✅
- `inventory/purchase-requests` ✅
- `hr/config/tax-brackets` + `social-insurance` ✅
- `pms/bookings/{id}/cancel` ✅
- Dashboard analytics sub-cards (hr/maintenance/crm/inventory) ✅
- `hr/leave-requests` approve/reject ✅
- `endpoints.ts` توحيد كامل ✅
- `hr/rota` + assignments + templates + swap-requests ✅ — grid أسبوعي كامل
- `finance/discounts` → tab إدارة الخصومات في FinanceView ✅
- `finance/exchange-rates` → section في FinanceView ✅
- `finance/reports/balance-sheet` → tab في FinanceView ✅
- `inventory/stock-counts` → tab في InventoryView ✅
- `hr/departments` + `hr/shifts` → settings في HRView ✅
- `finance/folios` → tab عرض/إدارة في FinanceView ✅
- CRMView DS migration (DataTable/StatusBadge/AppTabs/SearchInput) ✅
- AnalyticsView DS migration (StatCard/ChartWrapper/DataTable/AppProgress) ✅
- BackOfficeLayout → `#111827` sidebar + gold active + CommandPalette Ctrl+K ✅
- 7 DS components جديدة (ChartWrapper/FiltersPanel/Combobox/Autocomplete/Wizard/CommandPalette/VirtualTable) ✅
- `HRView.vue` merge bug fix → صفر أخطاء TypeScript ✅

### 🔴 عالية — المتبقي (التالي فوراً)
1. **`router/index.ts`** — redirect بعد login لكل دور لشاشته الصح بدل `/admin/dashboard` للجميع ✅ *(كان موجوداً بالفعل — homeRouteFor() كامل)*
2. **`HRView.vue` attendance tab** — DataTable بدل HTML table خام + FiltersPanel ✅ *(كان موجوداً بالفعل — DataTable مُستخدم)*
3. **`FinanceView.vue` DS Migration** — DataTable + StatCard + FiltersPanel في كل tabs ✅ *(منجز — إصلاح كامل للملف)*

### 🟡 متوسطة — التالي بعد الأولوية العالية
- `hr/rota/swap-requests` → عرض طلبات التبديل المعلقة في Rota tab بشكل أوضح ✅
- ~~`InventoryView.vue` DS migration — DataTable + FiltersPanel~~ ✅ **منجز** — suppliers + purchase-requests لـ DataTable
- ~~`HubManagementView.vue` — Blog posts tab (GET/POST `/hub/blog/posts`)~~ ✅ **موجود بالفعل**
- ~~Beach hardcoded strings → ENDPOINTS في BeachAdminView + BeachLiveDashboardView~~ ✅ **منجز** — BeachLiveDashboardView 5 hardcoded strings → ENDPOINTS
- `hr/employees/{id}/link-user` — ربط موظف بحساب مستخدم ✅ **منجز** — زرار + modal في HRView
- `hr/employees/{id}/allowances` — بدلات الموظف ✅ **منجز** — modal عرض + إضافة في HRView

### 🔵 منخفضة — تحسينات
- `AppButton` migration من `bg-blue-700` → `primary-700` DS token ✅ *(مكتمل بالفعل)*
- `AppBadge` ألوان hardcoded → DS tokens ✅ *(مكتمل بالفعل)*
- Active tab محفوظ في URL query param (navigation state) ✅ *(منجز — HRView + InventoryView)*
- `ReceptionView.vue` جديدة — شاشة الاستقبال (L.1 من specs) ✅
- `DiningKDSView.vue` — Timer + urgency colors (أخضر/أصفر/أحمر) + صوت تنبيه ✅
- **Hardcoded `/api/v1/` strings** → ENDPOINTS constants في كل الشاشات ✅ *(صفر strings متبقية)*
- `finance/journal-entries` — عرض قيود اليومية ✅ **منجز** — tab "قيود اليومية" كامل في FinanceView
- `finance/revenue-audit-logs` — سجل التدقيق ✅ **منجز** — tab "audit-log" كامل في FinanceView
- `finance/cost-centers` — إدارة مراكز التكلفة ✅ **منجز** — tab "مراكز التكلفة" كامل في FinanceView
- `inventory/products/barcode-labels` — طباعة باركود ✅ **منجز** — modal تحميل PDF في InventoryView
- `dining/reports/food-cost` موحّد ✅ **منجز** — tab "كل المنافذ" في FoodCostReportView + `foodCostReportAll` endpoint

---

## 🎨 قسم الديزاين — Design System الكامل

> **آخر تحديث:** 2026-07-14  
> **المصدر:** قراءة مباشرة للكود — `tailwind-preset.js` + `tokens.css` + `packages/ui/src/` + layouts

---

### 1. المكدس التقني للـ Frontend

| الطبقة | التفاصيل |
|--------|---------|
| Framework | Vue 3 (Composition API + `<script setup>`) |
| Language | TypeScript صارم |
| State | Pinia |
| Routing | Vue Router 4 |
| Styling | TailwindCSS v3 (JIT) + CSS Custom Properties |
| Build | Vite |
| Monorepo | pnpm workspace |
| Icons | `@heroicons/vue` v2 (24/outline) — مُجرَّد خلف `AppIcon` |
| i18n | vue-i18n — AR (RTL) + EN + IT |
| Realtime | WebSocket composable (`useWebSocket`) |
| Offline | `useOfflineQueue` — طوابير الطلبات وقت انقطاع الإنترنت |

---

### 2. هيكل الـ Monorepo

```
frontend/
├── packages/
│   ├── core/                    ← shared logic (no UI)
│   │   └── src/
│   │       ├── api/
│   │       │   ├── client.ts    ← axios instance + interceptors
│   │       │   └── endpoints.ts ← كل المسارات كـ constants
│   │       ├── stores/
│   │       │   └── auth.ts      ← useAuthStore (JWT + role + permissions)
│   │       ├── composables/
│   │       │   ├── useTheme.ts       ← dark mode singleton
│   │       │   ├── useOfflineQueue.ts← queue للطلبات offline
│   │       │   ├── useWebSocket.ts   ← WebSocket reactive
│   │       │   ├── useOrderDiscount.ts
│   │       │   └── usePrintDocument.ts
│   │       ├── i18n/            ← locale files + switchLocale()
│   │       ├── types/           ← TypeScript interfaces مشتركة
│   │       └── utils/
│   │           └── dates.ts
│   └── ui/                      ← Design System (components + tokens)
│       └── src/
│           ├── styles/
│           │   └── tokens.css   ← CSS Custom Properties (light + dark)
│           ├── composables/
│           │   ├── useToast.ts  ← global toast singleton
│           │   ├── useConfirm.ts← confirm dialog singleton
│           │   └── onClickOutside.ts
│           ├── icons/
│           │   └── registry.ts  ← ICONS map (IconName type)
│           ├── views/
│           │   └── LoginView.vue
│           ├── utils/
│           │   └── inputClasses.ts ← shared field CSS utility
│           └── components/      ← كل مكونات الـ UI (30+ component)
│
├── apps/
│   ├── el-kheima/               ← Back-office + POS + KDS (port 3001)
│   │   ├── tailwind.config.js
│   │   ├── src/
│   │   │   ├── assets/main.css  ← tokens import + base styles
│   │   │   ├── layouts/
│   │   │   │   ├── BackOfficeLayout.vue  ← sidebar + topbar
│   │   │   │   ├── FieldLayout.vue       ← POS/waiter header
│   │   │   │   └── KioskLayout.vue       ← KDS fullscreen
│   │   │   ├── components/      ← app-specific components
│   │   │   ├── views/
│   │   │   │   ├── admin/       ← إدارة (FinanceView, HRView...)
│   │   │   │   ├── ops/         ← تشغيل (BookingsView, RoomsView...)
│   │   │   │   ├── pos/         ← نقاط البيع
│   │   │   │   ├── kds/         ← شاشة المطبخ
│   │   │   │   ├── portal/      ← self-service موظفين
│   │   │   │   └── account/     ← login/2FA/reset
│   │   │   └── router/index.ts
│   └── public/                  ← بوابة الضيوف العامة (port 3002)
│       └── tailwind.config.js
```

---

### 3. نظام الألوان

#### 3.1 اللوحة الأساسية (el-kheima — back-office)

```
primary:
  DEFAULT / 700  →  #0B4F8A   (نيلي داكن — اللون السيادي)
  50             →  #EFF6FF
  100            →  #DBEAFE
  200            →  #BFDBFE
  300            →  #93C5FD
  400            →  #60A5FA
  500            →  #3B82F6
  600            →  #2563EB
  800            →  #083C6A
  900            →  #05294A

gold:
  DEFAULT        →  #C9963C   (ذهبي — للتمييز والـ active state)
  light          →  #F5D78E
  dark           →  #A07530

resort:
  bg             →  #F9F7F4   (خلفية الصفحة — warm white)
  surface        →  #FFFFFF
  border         →  #E5E0D8
```

#### 3.2 Semantic Tokens (Design System — CSS vars)

| Token | Light | Dark | الاستخدام |
|-------|-------|------|----------|
| `secondary` | `#C9963C` (gold) | `#F5D78E` | أزرار ثانوية، highlights |
| `success` | `green-600` | `green-400` | حالات نجاح |
| `warning` | `amber-600` | `amber-400` | تحذيرات |
| `danger` | `red-600` | `red-400` | أخطاء، حذف |
| `info` | `blue-600` | `blue-400` | معلومات |
| `surface` | `white` | `stone-900` | خلفية البطاقات |
| `border` | `#E5E0D8` | `stone-700` | حدود |
| `muted` | `stone-500` | `stone-400` | نصوص ثانوية |
| `background` | `#F9F7F4` | `near-black` | خلفية عامة |
| `dark` | `stone-900` | `stone-100` | نص داكن |
| `light` | `white` | `stone-900` | نص فاتح |

#### 3.3 لوحة ألوان `public` app (بوابة الضيوف)

```
brand:
  ocean     →  #0077BE   (أزرق بحري)
  sandy     →  #E8D5B7   (رملي دافئ)
  sunset    →  #FF6B35   (برتقالي غروب)
  teal      →  #006B7D   (فيروزي)
  warmwhite →  #FDFBF7
  coral     →  #FFB4A2
  charcoal  →  #2C3E50
  lightgray →  #ECF0F1
```

---

### 4. التيبوغرافيا

```
fontFamily:
  el-kheima:  Cairo, Tajawal, system-ui, sans-serif      (عربي أول)
  public:     Montserrat/Open Sans + Cairo/Tajawal fallback

font scale (من tailwind-preset.js):
  xs   →  0.75rem  / lh: 1rem    / ls: 0.01em
  sm   →  0.875rem / lh: 1.25rem / ls: 0
  base →  1rem     / lh: 1.5rem  / ls: 0
  lg   →  1.125rem / lh: 1.75rem / ls: 0
  xl   →  1.25rem  / lh: 1.75rem / ls: -0.01em
  2xl  →  1.5rem   / lh: 2rem    / ls: -0.01em
  3xl  →  1.875rem / lh: 2.25rem / ls: -0.015em
  4xl  →  2.25rem  / lh: 2.5rem  / ls: -0.02em

body default: font-family Cairo, direction: rtl
```

---

### 5. الـ Breakpoints (حجم الشاشات)

```
Tailwind defaults (محفوظة كاملاً):
  sm   →  640px
  md   →  768px
  lg   →  1024px
  xl   →  1280px
  2xl  →  1536px

Design System additions (additive — لا تحل محل الافتراضية):
  mobile   →  375px   ← هواتف الموظفين (تحقق من الحضور، إجازات)
  tablet   →  768px   ← هاندهيلدز النادل والهاوس كيبينج
  pos      →  1024px  ← أجهزة الكاشير الثابتة (landscape)
  desktop  →  1280px  ← شاشات الإدارة والمحاسبة
```

**الاستخدام الفعلي حسب الشاشة:**
- **BackOfficeLayout** → `w-60` sidebar مفتوح / `w-16` مغلق — يتذكر في localStorage
- **FieldLayout (POS)** → header مضغوط، nav tabs أفقية في الأسفل
- **KioskLayout (KDS)** → fullscreen، لا sidebar، لا topbar
- **public app** → responsive marketing pages

---

### 6. Elevation (ظلال)

```
elevation-0  →  none
elevation-1  →  0 1px 2px  rgb(0 0 0 / 0.06)           ← بطاقات عادية
elevation-2  →  0 2px 8px  + 0 1px 2px                  ← dropdowns، popovers
elevation-3  →  0 8px 16px + 0 2px 6px                  ← sidebars، side panels
elevation-4  →  0 16px 32px + 0 4px 12px                ← modals
elevation-5  →  0 24px 48px + 0 8px 20px                ← drawers، highest overlay

focus-ring   →  0 0 0 2px surface + 0 0 0 4px primary-ring
```

---

### 7. الحركة والانيميشن

```
durations:
  fast   →  120ms   ← hover states، micro interactions
  base   →  200ms   ← فتح/غلق modals، transitions
  slow   →  320ms   ← slide animations

easing:
  ds-standard   →  cubic-bezier(0.4, 0, 0.2, 1)   ← الافتراضي
  ds-decelerate →  cubic-bezier(0, 0, 0.2, 1)      ← عناصر تدخل
  ds-accelerate →  cubic-bezier(0.4, 0, 1, 1)      ← عناصر تخرج

keyframes:
  ds-fade-in     / ds-fade-out
  ds-scale-in    (scale 0.96 → 1)
  ds-slide-up    (translateY 8px → 0)
  ds-slide-down  (translateY -8px → 0)
  ds-pulse-ring  (focus ring animation)
  ds-indeterminate (progress bar sweep)
```

**ملاحظة أمان:** `prefers-reduced-motion` مُفعّل بـ `tokens.css` — كل الأنيميشن تُلغى أوتوماتيكياً لمن يحتاجها.

---

### 8. كتالوج المكونات (packages/ui)

#### 8.1 مكونات الـ Core (موجودة في كل شاشة)

| المكون | الـ Export | الوصف |
|--------|-----------|-------|
| `AppButton` | ✅ | `variant`: primary/secondary/danger/ghost/outline — `size`: sm/md/lg/xl |
| `AppCard` | ✅ | wrapper بيض rounded-xl — `padding`: none/sm/md/lg |
| `AppBadge` | ✅ | pill ملون — `variant`: success/warning/danger/info/neutral — `size`: sm/md |
| `AppModal` | ✅ | Teleport to body — `size`: sm/md/lg/xl — `zIndex` prop (لحل باج ConfirmDialog) |
| `AppInput` | ✅ | text field — error/disabled states — start/end slots |
| `AppSpinner` | ✅ | loading spinner |
| `ToastContainer` | ✅ | global toast (يُضاف في App.vue مرة واحدة) |
| `ConfirmDialogContainer` | ✅ | global confirm dialog — `zIndex: 'z-[60]'` فوق أي AppModal |

#### 8.2 مكونات الـ Design System (Phase 2)

| المكون | الـ Export | الوصف |
|--------|-----------|-------|
| `AppIcon` | ✅ | `<AppIcon name="..." size="xs/sm/md/lg/xl" />` — يستخدم ICONS registry |
| `IconButton` | ✅ | زرار أيقونة فقط (مربع) مع tooltip |
| `AppTextarea` | ✅ | textarea — نفس classes الـ Input |
| `AppSelect` | ✅ | select + `SelectOption` type |
| `SearchInput` | ✅ | input + أيقونة بحث مدمجة |
| `MoneyInput` | ✅ | numeric input للمبالغ |
| `PhoneInput` | ✅ | phone number input |
| `DatePicker` | ✅ | date picker |
| `TimePicker` | ✅ | time picker |
| `StatCard` | ✅ | بطاقة KPI — label/value/icon/trend/variant |
| `ErrorState` | ✅ | حالة خطأ مع زرار Retry |
| `LoadingState` | ✅ | حالة تحميل |
| `EmptyState` | ✅ | حالة فراغ مع title/subtitle |
| `Skeleton` | ✅ | loading skeleton bar |
| `AppAvatar` | ✅ | avatar دائري (initial أو صورة) |
| `StatusBadge` | ✅ | badge حالة جاهز بخريطة افتراضية للحالات (pending/confirmed/paid...) |
| `RoleBadge` | ✅ | badge الدور (admin/manager/cashier...) |
| `PermissionBadge` | ✅ | badge الصلاحية |
| `AppDrawer` | ✅ | side panel — `side`: start/end — `width`: sm/md/lg — RTL-aware |
| `AppTabs` | ✅ | tab strip v-model — keyboard navigation (Arrow/Home/End) |
| `AppAccordion` | ✅ | accordion قابل للطي |
| `AppTimeline` | ✅ | timeline events مع `TimelineItem` type |
| `AppProgress` | ✅ | progress bar — determinate + indeterminate |
| `Paginator` | ✅ | pagination — page/totalPages/totalItems |
| `FloatingActionButton` | ✅ | FAB زرار عائم |
| `Dropdown` | ✅ | dropdown menu مع click-outside |
| `DataTable` | ✅ | جدول كامل — sort/pagination/loading/empty/error/scoped slots |
| `ThemeToggle` | ✅ | زرار تبديل light/dark |

#### 8.3 Views في الـ UI package

| الـ View | الوصف |
|---------|-------|
| `LoginView` | صفحة تسجيل الدخول (مشتركة بين التطبيقين) |

---

### 9. أنماط الـ Form Fields

كل fields تستخدم `fieldClasses()` من `utils/inputClasses.ts`:

```typescript
// classes موحّدة لكل Input/Textarea/Select/Money/Phone/Date/Time:
'w-full rounded-lg border bg-white dark:bg-surface text-gray-900'
'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500'
// error:    border-red-400 bg-red-50
// disabled: opacity-50 cursor-not-allowed bg-gray-50
// with-start-slot: ps-9 pe-3 py-2
// default:  px-3 py-2

fieldLabelClasses  = 'text-sm font-medium text-gray-700 dark:text-gray-300'
fieldErrorClasses  = 'text-xs text-danger'
fieldHintClasses   = 'text-xs text-muted'
```

---

### 10. الـ Layouts

#### BackOfficeLayout (admin/ops/portal routes)
```
┌──────────────────────────────────────────────────────┐
│  Topbar: [hamburger] [breadcrumb + title]   [alerts] [date] │
├──────────┬───────────────────────────────────────────┤
│ Sidebar  │                                           │
│ slate-900│         <RouterView />                    │
│ w-60/w-16│         p-6                               │
│ (toggle) │                                           │
└──────────┴───────────────────────────────────────────┘

- Sidebar active item: bg-amber-500 text-white
- Sidebar default item: text-slate-300 hover:bg-slate-800
- Logo: bg-amber-500 rounded-xl "RO"
- State: محفوظ في localStorage key: 'resort-os-sidebar-open'
- Breadcrumb: section / page (من allSections نفسها)
```

#### FieldLayout (POS/waiter routes)
```
┌─────────────────────────────────────────────────────┐
│ Header: [Logo POS] [ShiftPanel] [Bell] [●online] [Clock] [User] │
├─────────────────────────────────────────────────────┤
│ Nav tabs: [Beach POS] [Beach Map] [Dining POS] [Shift] │
├─────────────────────────────────────────────────────┤
│                    <RouterView />                    │
└─────────────────────────────────────────────────────┘

- Active tab: bg-blue-700 text-white
- Clock: Arabic-Indic numerals للـ AR locale، Latin للغيره
- Online dot: green-500 / amber-500 animate-pulse
```

#### KioskLayout (KDS)
```
- Fullscreen، لا sidebar، لا topbar
- مناسب للشاشات الثابتة في المطبخ
```

---

### 11. نظام الأيقونات

المصدر الوحيد: `@heroicons/vue/24/outline` — مُجرَّد خلف `AppIcon`:

```vue
<AppIcon name="check" />              <!-- size default: md (24px) -->
<AppIcon name="delete" size="lg" />   <!-- xs/sm/md/lg/xl -->
<AppIcon name="currency" class="text-gold" />
```

**الأيقونات المتاحة (مختارة):**

```
Actions:    check, close, add, remove, delete, edit, refresh, download, upload
Navigation: chevron-down/up/left/right, arrow-left/right, menu, more-h/v
User:       user, users, user-circle, id, logout, login
Content:    document, clipboard, calendar, clock, bell, search, filter
Finance:    currency, cash, card, discount, scale, calculator, receipt
Business:   outlet, branch, building, inventory, cart, tag, delivery
Status:     success, error, warning, info, help, alert-circle, void, verified
HR:         hr, training, users, id
Layout:     table, grid, list, home
Media:      camera, photo, qrcode, print, send, link
Theme:      moon, sun, language, online, offline, mobile, desktop
Charts:     chart, chart-pie, trend
Other:      kitchen, dessert, sparkles, flag, location, phone, email
```

---

### 12. نظام Dark Mode

```typescript
// useTheme() — singleton من packages/core
// 3 خيارات: 'light' | 'dark' | 'system'
// يُحفظ في localStorage key: 'resort-os-theme'
// يُطبَّق بإضافة class="dark" على <html>
// prefers-color-scheme: dark مدعوم تلقائياً عند اختيار 'system'

// التهيئة — مرة واحدة في main.ts قبل app.mount():
import { initTheme } from '@resort-os/core/composables'
initTheme()

// في أي component:
const { isDark, preference, toggleTheme, setTheme } = useTheme()
```

---

### 13. RTL/LTR Support

```
- direction: rtl افتراضي على body (main.css)
- تبديل لحظي: locale === 'ar' ? 'rtl' : 'ltr' على <div> الـ layout
- i18n: ar (افتراضي) + en + it
- Cairo/Tajawal تغطي العربية، Montserrat/Open Sans تغطي اللاتينية
- Drawer.vue: slide direction يتحكم فيه [dir="rtl"] CSS
- Tabs.vue: ArrowRight/ArrowLeft تعمل صح في RTL و LTR بدون branch منفصل
- Clock في FieldLayout: toLocaleTimeString('ar-EG') للأرقام العربية
```

---

### 14. باجات الـ CSS المعروفة (اتحلّت)

| الباج | الأثر | الحل |
|-------|-------|------|
| `presets: [dsPreset]` بدون `defaultTheme` | كل ألوان Tailwind الافتراضية (blue-900, gray-500...) تختفي من CSS | `presets: [defaultTheme, dsPreset]` في كلا التطبيقين |
| `content` مش شامل `../../packages/ui/src` | Toast/Confirm classes تتشال بصمت → تظهر بلا تنسيق | أضيف `../../packages/ui/src/**/*.{vue,ts}` |
| `AppModal` و `ConfirmDialogContainer` نفس `z-50` | زرار Confirm مقفول خلف Modal | `zIndex` prop في AppModal، ConfirmDialogContainer يستخدم `z-[60]` |
| `:global([dir="rtl"]) .class` داخل `<style scoped>` | Vue compiler يحذف الـ class → كل `[dir="rtl"]` elements تتحرك خارج الشاشة | نقل القواعد لـ `<style>` غير scoped |

---

### 15. أنماط CSS المشتركة (global classes في main.css)

```css
/* page wrapper */
.page-container { max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 }

/* section header */
.section-title { text-xl font-bold text-gray-900 mb-4 }

/* table styles */
.data-table { w-full border-collapse bg-white rounded-xl overflow-hidden shadow-sm }
.data-table th { px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase bg-stone-50 border-b border-stone-200 }
.data-table td { px-4 py-3 text-sm text-gray-800 border-b border-stone-100 }
.data-table tr:hover td { bg-blue-50/30 }

/* scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px }
::-webkit-scrollbar-thumb { background: #C9963C; border-radius: 3px }  /* ذهبي */
::-webkit-scrollbar-track { background: #F9F7F4 }
```

---

### 16. أنماط الـ UX المستخدمة

#### Error Handling Pattern
```typescript
try {
  await api.post(ENDPOINTS.something, payload)
  toast.success('تم بنجاح')
} catch (e: any) {
  toast.error(e?.response?.data?.detail ?? 'حصل خطأ')
}
```

#### Confirm Before Destructive Action
```typescript
const { confirm } = useConfirm()
const ok = await confirm({ title: 'تأكيد الحذف', message: '...', danger: true })
if (!ok) return
// proceed
```

#### Loading States
- جداول: `DataTable` يعرض 5 rows skeleton أثناء التحميل
- أزرار: `AppButton :loading="true"` يعرض spinner ويعطّل الزرار
- بطاقات KPI: `StatCard :loading="true"` يعرض pulse placeholder

#### Empty States
- `EmptyState` component مع title/subtitle اختياري
- `DataTable` يعرضه أوتوماتيكياً لو `items.length === 0`

#### Permissions Guard
```typescript
// في الـ template — إخفاء حسب الدور
v-if="auth.hasRole('manager')"

// في الـ nav — فلترة أوتوماتيكية في BackOfficeLayout
items.filter(item => !item.requiredRole || auth.hasRole(item.requiredRole))
```

---

### 17. ما ينقص في الـ Design System (فرص تحسين)

| الموضوع | التفاصيل |
|---------|---------|
| **AppButton لم يُهاجَر بعد** | لازال يستخدم `bg-blue-700` بدل `primary-700` DS token — tracked كـ follow-up |
| **AppBadge ألوان hardcoded** | `bg-green-100 text-green-800` بدل `success/10` DS tokens |
| **screens لم تُهاجَر بعد** | كل الشاشات الحالية لا تستخدم `DataTable`/`StatCard`/`StatusBadge` بعد — في خطة المرحلة التالية |
| **Dark Mode تغطية جزئية** | tokens.css يدعم dark mode لكن معظم الشاشات لا تستخدم DS tokens بعد |
| **Column picker/resize/export** | مخطط لـ Phase 9 في wagdy.md |
| **Saved views** | مخطط لـ Phase 9 |

---

## 🎨 Design System — الرؤية الكاملة v2 (Professional Warm Dark)

> **تاريخ القرار:** 2026-07-14
> **المرجع:** wagdy.md المراحل 1–16 + تحليل مباشر للكود
> **القاعدة الذهبية:** لا ألوان خارج الـ tokens، لا CSS خارج الـ Design System، لا مكون يُكرَّر

---

### A. لماذا نحتاج إعادة تصميم؟

المشكلة ليست في الكود — الكود سليم ومنظم. المشكلة في **3 مستويات**:

**المستوى 1 — الـ Design System موجود لكن معزول:**
- `DataTable` موجود في packages/ui → لكن 0 شاشات تستخدمه (كل view عندها table خاصة)
- `StatCard` موجود → لكن DashboardView لا تستخدمه
- `StatusBadge` موجود → لكن الجداول تستخدم AppBadge يدوياً
- النتيجة: 30+ component جاهز لكن الشاشات تتجاهله

**المستوى 2 — 7 مكونات غائبة بالكامل:**
Combobox، Autocomplete، Wizard، CommandPalette، VirtualTable، ChartWrapper، Filters
بدونهم مستحيل تبني Timeshare contract wizard أو global search أو analytics charts

**المستوى 3 — لا هوية بصرية للمنتجع:**
- Sidebar: `bg-slate-900` → generic مش resort
- POS: خلفية بيضاء → صعبة في الشمس على الكاشير
- لا hierarchy بصري واضح في الصفحات

---

### B. Color System الجديد

#### B.1 القرار: ماذا يتغير وماذا يُحفظ

```
يُحفظ بالكامل (عشرات الشاشات تعتمد عليه):
  primary.50–900   →  #EFF6FF … #05294A  (لا تغيير)
  gold.DEFAULT     →  #C9963C            (لا تغيير — الـ accent)
  gold.light/dark  →  #F5D78E / #A07530  (لا تغيير)

يتغير أو يُضاف:
  Sidebar bg:     #111827  (gray-900 — دافئ أكثر من slate-900)
  Surface:        #FFFFFF
  Background:     #F8F7F5  (warm white — أدفأ قليلاً من #F9F7F4)
  Border:         #E5E2DC
  Success:        #059669  (emerald-600 — أوضح من green-600)
  Info:           #0284C7  (sky-600 — أجمل من blue-600)
  Warning:        #D97706  (amber-600 — يُحفظ)
  Danger:         #DC2626  (red-600 — يُحفظ)
```

#### B.2 POS Dark Theme (ثابت — لا يتأثر بـ light/dark mode)

الكاشير يشتغل على شاشة لمس في الشمس 8+ ساعات.
الخلفية البيضاء مُرهقة. الـ dark warm theme يقلل التعب ويحسن الـ contrast.

```css
/* يُضاف في FieldLayout.vue فقط — لا يؤثر على BackOfficeLayout */
.pos-theme {
  --pos-bg:         #1E2530;   /* dark warm navy */
  --pos-surface:    #252D3A;   /* كارد داخل الـ POS */
  --pos-surface-2:  #2E3748;   /* elevated surface */
  --pos-border:     #374151;   /* gray-700 */
  --pos-text:       #F9FAFB;   /* gray-50 */
  --pos-text-muted: #9CA3AF;   /* gray-400 */
  --pos-accent:     #C9963C;   /* gold — active/selected */
  --pos-accent-bg:  rgba(201,150,60,0.15); /* selected item background */
  --pos-success:    #10B981;
  --pos-danger:     #F87171;
}
```

**التطبيق:**
- `BeachPOSView.vue` → `class="pos-theme bg-[var(--pos-bg)]"`
- `UnifiedPOSView.vue` → نفس الشيء
- `FieldLayout.vue` header → `bg-[var(--pos-surface)]` بدل `bg-white`
- `KioskLayout.vue` (KDS) → يستخدم `pos-theme` بالكامل

#### B.3 Semantic Tokens المحدّثة في tokens.css

```css
:root {
  --color-secondary:   201 150 60;    /* gold #C9963C */
  --color-success:     5 150 105;     /* emerald-600 #059669 ← تحديث */
  --color-warning:     217 119 6;     /* amber-600 */
  --color-danger:      220 38 38;     /* red-600 */
  --color-info:        2 132 199;     /* sky-600 #0284C7 ← تحديث */
  --color-surface:     255 255 255;
  --color-border:      229 226 220;   /* #E5E2DC ← تحديث طفيف */
  --color-muted:       120 113 108;
  --color-background:  248 247 245;   /* #F8F7F5 ← تحديث طفيف */
  --color-dark:        17 24 39;      /* gray-900 #111827 ← تحديث */
  --color-light:       255 255 255;
  --color-primary-ring: 11 79 138;
}

.dark {
  --color-success:     52 211 153;    /* emerald-400 */
  --color-info:        56 189 248;    /* sky-400 */
  --color-surface:     17 24 39;      /* gray-900 */
  --color-border:      55 65 81;      /* gray-700 */
  --color-muted:       156 163 175;   /* gray-400 */
  --color-background:  11 15 25;
  --color-dark:        249 250 251;
  --color-primary-ring: 96 165 250;
}
```

---

### C. Typography System الموحّد

```
القاعدة: لا text-* خارج هذه الـ classes في الشاشات الجديدة

Page Title:      text-2xl font-bold text-gray-900          (كان text-xl)
Section Title:   text-lg font-semibold text-gray-800
Card Title:      text-base font-semibold text-gray-800
Table Header:    text-xs font-semibold text-gray-500 uppercase tracking-wider
Body Default:    text-sm text-gray-800
Body Muted:      text-sm text-muted
Caption/Meta:    text-xs text-muted
Stat Value:      text-2xl font-bold tabular-nums text-gray-900
Stat Label:      text-sm font-medium text-muted
Money:           text-base font-semibold tabular-nums      (دايماً tabular-nums)
```

---

### D. Spacing System

```
نظام الـ 4px base unit — فقط هذه القيم في الشاشات الجديدة:

gap/padding/margin:
  1  →  4px
  2  →  8px
  3  →  12px
  4  →  16px
  5  →  20px
  6  →  24px
  8  →  32px
  10 →  40px
  12 →  48px
  16 →  64px

Card padding:     p-5 (20px) افتراضي، p-4 للـ compact، p-6 للـ spacious
Section gap:      gap-6 (24px)
Form field gap:   gap-4 (16px)
Button gap:       gap-2 (8px)
Topbar height:    h-14 (56px)
Sidebar width:    w-60 مفتوح، w-16 مغلق
```

---

### E. Border Radius System

```
rounded-lg   → أزرار، inputs، badges (8px)
rounded-xl   → cards، dropdowns، modals (12px)
rounded-2xl  → modals كبيرة، drawers (16px)
rounded-full → avatars، pills، dots
rounded-none → table cells (بدون radius في الـ cells)

ممنوع: rounded-md، rounded-sm، rounded-3xl في شاشات جديدة
```

---

### F. المكونات الـ 7 الغائبة — Specs كاملة

#### F.1 Combobox

**الاستخدام:** HR employee picker، Inventory product search، كل حقل فيه search + select
**الفرق عن Select:** يسمح بالكتابة والفلترة، لا يقتصر على dropdown

```typescript
// packages/ui/src/components/Combobox.vue
interface ComboboxOption {
  value: string | number
  label: string
  sublabel?: string      // اسم ثانوي (رقم الموظف، الكود)
  disabled?: boolean
  group?: string
}

props: {
  modelValue: string | number | null
  options: ComboboxOption[]
  placeholder?: string
  loading?: boolean      // بيعمل spinner وقت جلب الـ options
  clearable?: boolean
  error?: boolean
  disabled?: boolean
  // للـ async search — بيعمل debounce 300ms تلقائياً
  onSearch?: (query: string) => void
}
emit: ['update:modelValue', 'search']
```

**السلوك:**
- Keyboard: Arrow Up/Down للتنقل، Enter للاختيار، Escape للإغلاق
- RTL-aware: Teleport to body لتجنب overflow clip
- Loading state: spinner بدل الـ options لما `loading=true`
- Clear button: x صغير لما `clearable=true` وعنده قيمة

#### F.2 Autocomplete

**الاستخدام:** CRM customer search (بيجيب من API)، PMS booking search، Inventory supplier search
**الفرق عن Combobox:** القيمة المختارة string حر مش مقيّد بالـ options، يسمح بـ free text

```typescript
// packages/ui/src/components/Autocomplete.vue
props: {
  modelValue: string
  suggestions: Array<{ label: string; value: string; meta?: string }>
  placeholder?: string
  loading?: boolean
  minChars?: number      // default 2 — ما يبحثش قبل 2 حرف
  debounce?: number      // default 300ms
}
emit: ['update:modelValue', 'select', 'search']
```

#### F.3 Wizard (Multi-step Form)

**الاستخدام الأساسي:** Timeshare contract creation (4 خطوات)، HR employee onboarding

```typescript
// packages/ui/src/components/Wizard.vue
interface WizardStep {
  id: string
  label: string
  sublabel?: string
  icon?: IconName
  validate?: () => boolean | Promise<boolean>  // validation قبل الخطوة التالية
}

props: {
  steps: WizardStep[]
  modelValue: string        // active step id
  allowJump?: boolean       // السماح بالضغط على خطوة سابقة مكتملة
}
emit: ['update:modelValue', 'complete', 'cancel']
```

**الـ Layout:**
```
┌─────────────────────────────────────────────────┐
│  ① بيانات العقد  →  ② الوحدة  →  ③ الأقساط  →  ④ تأكيد │
│  ──────────────────                              │
│                                                 │
│         [محتوى الخطوة الحالية]                   │
│                                                 │
│  [إلغاء]              [السابق]  [التالي / إنهاء] │
└─────────────────────────────────────────────────┘

Step indicator: دوائر مرقمة + خط رابط
- completed: bg-success text-white + checkmark
- active: bg-primary-700 text-white
- upcoming: bg-background text-muted border
```

#### F.4 CommandPalette

**الاستخدام:** Global search في BackOfficeLayout — Ctrl+K أو Cmd+K
**المرجع:** Linear، Vercel Dashboard

```typescript
// packages/ui/src/components/CommandPalette.vue
interface CommandItem {
  id: string
  label: string
  sublabel?: string
  icon?: IconName
  category?: string      // 'صفحات' | 'إجراءات' | 'موظفين' | 'عملاء'
  shortcut?: string[]    // ['Ctrl', 'K']
  action: () => void
}

props: {
  open: boolean
  items: CommandItem[]
  loading?: boolean
  placeholder?: string
}
emit: ['close']
```

**السلوك:**
- يفتح بـ Ctrl+K من BackOfficeLayout
- Teleport to body + z-[200] فوق كل حاجة
- Fuzzy search على label + sublabel + category
- Arrow Up/Down للتنقل، Enter للتنفيذ، Escape للإغلاق
- Recent items محفوظة في localStorage (آخر 5)

**التكامل مع BackOfficeLayout:**
```typescript
// في BackOfficeLayout.vue — يُضاف
const showCommandPalette = ref(false)
onMounted(() => {
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault()
      showCommandPalette.value = true
    }
  })
})
```

#### F.5 VirtualTable

**الاستخدام:** Inventory products (ممكن آلاف)، HR payroll lines، Finance journal entries
**الفرق عن DataTable:** لا يرندر كل الـ rows — بيرندر بس اللي في الـ viewport

```typescript
// packages/ui/src/components/VirtualTable.vue
// يعتمد على @tanstack/virtual (مكتبة مثبّتة؟ — تحقق قبل التنفيذ)
// لو مش مثبّتة: npm install @tanstack/vue-virtual

props: {
  columns: DataTableColumn[]    // نفس type الـ DataTable
  items: T[]
  rowKey: (item: T) => string | number
  rowHeight?: number            // default 48px — fixed height للـ virtualization
  loading?: boolean
  error?: boolean
  sortKey?: string
  sortDir?: 'asc' | 'desc'
  // لا paginator — VirtualTable = infinite scroll داخلي
}
emit: ['sort', 'row-click', 'retry', 'load-more']
```

**متى تستخدم DataTable vs VirtualTable:**
- DataTable: أقل من 500 row أو محتاج pagination server-side
- VirtualTable: أكثر من 500 row في الـ client أو infinite scroll

#### F.6 ChartWrapper

**الاستخدام:** AnalyticsView، DashboardView، Finance income statement، HR leaderboard

```typescript
// packages/ui/src/components/ChartWrapper.vue
// يعتمد على Chart.js + vue-chartjs (تحقق من وجوده في package.json)
// لو غائب: npm install chart.js vue-chartjs

type ChartType = 'bar' | 'line' | 'pie' | 'doughnut' | 'area'

props: {
  type: ChartType
  data: {
    labels: string[]
    datasets: Array<{
      label: string
      data: number[]
      color?: string      // اختياري — الـ Design System يختار اللون
    }>
  }
  title?: string
  loading?: boolean
  error?: boolean
  height?: number         // default 300px
  currency?: boolean      // بيضيف EGP على الـ Y-axis labels
  percentage?: boolean    // بيضيف % على الـ Y-axis labels
}
```

**لوحة الألوان للـ Charts (من Design System):**
```
dataset[0]: #0B4F8A  (primary)
dataset[1]: #C9963C  (gold)
dataset[2]: #059669  (success)
dataset[3]: #0284C7  (info)
dataset[4]: #D97706  (warning)
dataset[5]: #6366F1  (indigo)
```

#### F.7 Filters (Panel)

**الاستخدام:** InventoryView (فلتر category/warehouse/supplier)، HRView (فلتر department/status)، كل الجداول
**الفكرة:** panel موحّد بيحل محل الـ filter inputs المبعثرة فوق كل جدول

```typescript
// packages/ui/src/components/FiltersPanel.vue
interface FilterField {
  key: string
  label: string
  type: 'select' | 'date-range' | 'text' | 'boolean' | 'number-range'
  options?: SelectOption[]   // للـ select
  placeholder?: string
}

props: {
  fields: FilterField[]
  modelValue: Record<string, unknown>
  loading?: boolean
  // variant:
  // 'inline' → أفقي فوق الجدول (للـ desktop)
  // 'drawer' → زرار فلتر يفتح AppDrawer (للـ mobile وللـ filters كتيرة)
  variant?: 'inline' | 'drawer'
}
emit: ['update:modelValue', 'reset', 'apply']
```

---

### G. خطة Migration الشاشات

#### الأولوية: من الأعلى أثراً للأقل

**G.1 المرحلة الأولى — Infrastructure (لا تحتاج design review)**

```
الهدف: ربط الشاشات الموجودة بالـ DS بدون تغيير بصري

1. endpoints.ts — إضافة كل المسارات الـ hardcoded (راجع قسم 🔵 أعلاه)
2. BackOfficeLayout — تحديث لون الـ sidebar من slate-900 إلى #111827
3. DashboardView — استبدال KPI cards بـ StatCard component
4. كل الجداول المهمة — استبدال <table> يدوي بـ DataTable component
5. كل الـ status badges — استبدال بـ StatusBadge component
```

**G.2 المرحلة الثانية — المكونات الـ 7 الجديدة**

```
الترتيب المقترح حسب الأثر:

1. ChartWrapper     → AnalyticsView فيها charts يدوية (أو مفيش charts أصلاً)
2. FiltersPanel     → كل view محتاجاه
3. Combobox         → HR employee picker، Inventory product
4. VirtualTable     → Inventory products list
5. Wizard           → Timeshare contract creation
6. CommandPalette   → BackOfficeLayout global search
7. Autocomplete     → CRM customer search
```

**G.3 المرحلة الثالثة — POS Redesign**

```
الأولوية: الأعلى تأثيراً على اليومي

1. FieldLayout.vue     → dark header (#111827) + pos-theme
2. BeachPOSView.vue    → pos-theme + بطاقات أكبر للـ ticket types
3. UnifiedPOSView.vue  → pos-theme + item grid بكروت أكبر للمس
4. ShiftDashboardView  → تحديث الـ stats بـ StatCard
```

**G.4 المرحلة الرابعة — Admin Views**

```
كل view بنفس النمط:
1. Page header موحّد: title + subtitle + action buttons
2. Stats row بـ StatCard (لو في KPIs)
3. DataTable بدل الـ table اليدوية
4. FiltersPanel فوق الجدول
5. Wizard للـ creation flows (Timeshare أهمهم)
```

---

### H. قواعد "No Ad-hoc" — إجبارية للكود الجديد

```
❌ ممنوع في أي كود جديد:
  bg-blue-700    → استخدم bg-primary-700
  bg-amber-500   → استخدم bg-secondary أو bg-gold
  bg-green-600   → استخدم bg-success
  bg-red-600     → استخدم bg-danger
  text-green-800 → استخدم text-success
  text-red-700   → استخدم text-danger
  #HEXCODE       → استخدم CSS var أو Tailwind token
  style="color:  → استخدم class فقط
  rounded-md     → استخدم rounded-lg أو rounded-xl
  shadow-md/lg   → استخدم shadow-elevation-1/2/3

✅ المسموح:
  bg-primary-{50-900}    (للـ primary scale الكامل)
  bg-gold / text-gold    (للـ accent)
  bg-success/warning/danger/info  (من DS tokens)
  bg-surface/background/border/muted  (من DS tokens)
  shadow-elevation-{0-5}
  rounded-lg / rounded-xl / rounded-2xl / rounded-full
```

---

### I. Navigation الجديدة — BackOfficeLayout v2

**التحسينات المطلوبة على BackOfficeLayout الحالي:**

```
الحالي:
  sidebar: bg-slate-900 + emoji icons
  topbar: breadcrumb بسيط + تاريخ

المطلوب:

1. Sidebar:
   - bg-[#111827] بدل slate-900
   - AppIcon بدل emoji (بعد إضافة icons للـ nav items)
   - Tooltip على الـ items لما sidebar مقفول (w-16)
   - Pinned pages section (مرحلة لاحقة)

2. Topbar:
   - إضافة زرار CommandPalette (🔍 بحث سريع أو Ctrl+K hint)
   - Notification bell مع badge عدد (بدل GuestAlertsBell فقط)
   - User avatar بدل الأحرف الأولى text فقط

3. قواعد ثابتة:
   - active item: bg-gold text-white (بدل bg-amber-500)
   - hover: hover:bg-white/10 (بدل hover:bg-slate-800)
   - section labels: text-gray-500 uppercase tracking-widest text-[10px]
```

---

### J. POS Design Specs الكاملة

#### J.1 BeachPOS الجديد

```
Layout:
┌─────────────────┬──────────────────────────────┐
│   Ticket Types  │         Order Summary        │
│   (dark cards)  │         (dark surface)       │
│                 │                              │
│  ┌──────────┐   │  البالغين    × 2    200 ج    │
│  │ 👤 بالغ  │   │  أطفال       × 1     60 ج   │
│  │ 100 ج    │   │  مناشف       × 2     40 ج   │
│  └──────────┘   │  ─────────────────────────  │
│  ┌──────────┐   │  الإجمالي           300 ج   │
│  │ 👶 طفل   │   │                              │
│  │  60 ج    │   │  💳 بطاقة  💵 كاش  📱 محفظة │
│  └──────────┘   │                              │
│                 │   [تأكيد البيع — 300 ج]      │
└─────────────────┴──────────────────────────────┘

الـ ticket cards:
  min-height: 100px (touch-friendly)
  bg: var(--pos-surface)
  border: 1px solid var(--pos-border)
  active/selected: border-[var(--pos-accent)] bg-[var(--pos-accent-bg)]
  font: text-base font-semibold text-[var(--pos-text)]
  price: text-xl font-bold text-[var(--pos-accent)]
```

#### J.2 UnifiedPOS (Dining) الجديد

```
Layout (Foodics-inspired):
┌──────────┬──────────────────────┬──────────────┐
│ Outlets/ │    Item Grid         │  Order       │
│ Categories│  (4 cols, dark bg)  │  Sidebar     │
│          │                      │  (dark)      │
│ 🍽️ صالة  │  ┌────┐ ┌────┐ ┌────┐│              │
│ 🥡 تيكاوي│  │Item│ │Item│ │Item││  بيتزا مرغريتا│
│ 🛵 توصيل │  └────┘ └────┘ └────┘│  × 2  120 ج │
│          │                      │              │
│ ─────── │  ┌────┐ ┌────┐ ┌────┐│  ─────────── │
│ 🥗 سلطات│  │Item│ │Item│ │Item││  الإجمالي    │
│ 🍖 رئيسية│  └────┘ └────┘ └────┘│  320 ج       │
│ 🍰 حلويات│                      │              │
└──────────┴──────────────────────┴──────────────┘

Item cards:
  min-height: 90px
  bg: var(--pos-surface)
  border-radius: rounded-xl
  unavailable: opacity-40 cursor-not-allowed
  out-of-stock: relative + "نفذ" badge أحمر

Order sidebar:
  bg: var(--pos-surface)
  line items: flex justify-between + qty stepper inline
  payment: 3 أزرار كبيرة (48px+) كاش/بطاقة/غرفة
```

---

### K. Definition of Done للـ Design System

مكون جديد لا يُعتبر مكتملاً إلا إذا:

```
□ يستخدم DS tokens فقط (لا ألوان hardcoded)
□ يدعم dark mode (اختبار بـ ThemeToggle)
□ يدعم RTL و LTR (اختبار بـ locale switch)
□ كل interactive element ≥ 48px على mobile
□ keyboard navigation (Tab/Arrow/Enter/Escape)
□ focus ring على كل focusable element
□ loading state
□ error state  
□ empty state (لو مناسب)
□ موثّق في packages/ui/src/index.ts
□ اسمه في FRONTEND_GAPS.md يتحول لـ ✅
```

---

## 🧑‍💼 Operational UX — إعادة تصميم حول مهام الأدوار

> **المبدأ:** الموظف لا يفتح "صفحة" — يُنجز "مهمة".
> كل واجهة تُبنى حول السؤال: **ماذا يحتاج هذا الشخص أن يفعل الآن؟**
> لا تغيير في Backend، لا تغيير في Permissions — تغيير في طريقة عرض نفس البيانات.

---

### L.1 Reception (الاستقبال)

**الأدوار:** receptionist (level 40)
**الجهاز:** desktop أو tablet landscape
**ساعات العمل:** 24/7 بالوردية

#### المهام اليومية بالترتيب الفعلي:

| # | المهمة | الحالة الحالية | الهدف |
|---|--------|---------------|-------|
| 1 | Check-in ضيف قادم | BookingsView → بحث → مودال | شاشة واحدة مخصصة ≤ 3 clicks |
| 2 | Check-out وتسوية الفاتورة | BookingsView → فوليو → دفع | wizard خطوتين |
| 3 | تحويل غرفة | RoomsView → بحث → نقل | inline في خريطة الغرف |
| 4 | بحث عن ضيف | متفرق في عدة شاشات | global search بـ CommandPalette |
| 5 | Night Audit | RoomsView → زرار مخفي | زرار واضح في topbar الاستقبال |
| 6 | Housekeeping status | HousekeepingView منفصلة | widget في شاشة الاستقبال |

#### شاشة الاستقبال المقترحة (ReceptionView):

```
┌─────────────────────────────────────────────────────┐
│  [🔍 بحث ضيف / غرفة — Ctrl+K]     [Night Audit ⚡]  │
├──────────────┬──────────────┬───────────────────────┤
│  اليوم       │   الغرف       │   وصول اليوم          │
│  ─────────── │   ─────────── │   ─────────────────── │
│  ✅ دخل:  12  │   🟢 شاغلة:32 │   [ضيف A] غرفة 101   │
│  🚪 خرج:  8   │   🔵 محجوزة:5 │   [ضيف B] غرفة 205   │
│  📋 قادم:  6  │   🟡 تنظيف:3  │   [ضيف C] غرفة 310   │
│              │   ⚪ فارغة:8  │   [+ 3 أخرى...]       │
├──────────────┴──────────────┴───────────────────────┤
│  [تسجيل دخول جديد +]    [تسجيل خروج]    [حجز جديد]  │
└─────────────────────────────────────────────────────┘
```

#### Check-in Workflow — الهدف ≤ 4 clicks:
```
1. بحث باسم الضيف أو رقم الحجز (CommandPalette أو SearchInput)
2. بطاقة الحجز تظهر: الاسم + الغرفة + المدة + السعر
3. [تأكيد Check-in] → يفتح مودال صغير: رقم الهوية + طريقة الدفع
4. [تأكيد] → checked_in + طباعة بطاقة الترحيب اختياري
```

#### Check-out Workflow — الهدف ≤ 5 clicks:
```
1. بحث بالغرفة أو الاسم
2. عرض الفوليو: إيجار + مشتريات المطعم + الشاطئ + extras
3. مراجعة سريعة + إمكانية إضافة charge يدوي
4. [تسوية] → اختيار طريقة الدفع (كاش/بطاقة/تحويل)
5. [تأكيد] → checked_out + طباعة الفاتورة
```

#### ما لا يراه الاستقبال:
- Finance reports وشرائح الضريبة
- HR وكشوف الرواتب
- Timeshare contracts (إلا لو عنده صلاحية صريحة)
- Inventory وأوامر الشراء

---

### L.2 Cashier (الكاشير)

**الأدوار:** cashier (level 40)
**الجهاز:** POS terminal (1024px landscape) + touch
**ساعات العمل:** بالوردية

#### المهام اليومية:

| # | المهمة | الـ clicks الحالية | الهدف |
|---|--------|------------------|-------|
| 1 | بيع شاطئ (Beach POS) | 6-8 clicks | ≤ 4 |
| 2 | استلام أوردر دايننج | 8-10 clicks | ≤ 5 |
| 3 | تطبيق خصم (بـ PIN) | 5 clicks | 3 |
| 4 | Void بضغط المدير | 4 clicks | 3 |
| 5 | X-Report وسط الوردية | 4 clicks | 2 |
| 6 | إغلاق الوردية + عدّ كاش | 8-10 clicks | 5 |

#### شاشة الكاشير (FieldLayout) — القواعد الذهبية:
```
✅ دايماً ظاهر:
   - الإجمالي الحالي للوردية (top bar)
   - حالة الـ online/offline
   - الساعة الحالية (arabic numerals)
   - زرار X-Report سريع

✅ في متناول إيد واحدة (≥ 48px):
   - أزرار +/- للكميات
   - أزرار طرق الدفع
   - زرار "تأكيد البيع"

❌ مخفي عن الكاشير:
   - سجل وردية غيره
   - تقارير الإدارة
   - إعدادات النظام
   - صلاحيات الخصم بدون PIN
```

#### Beach POS — الـ workflow المحسّن:
```
قبل (الحالي):        بعد (المقترح):
① فتح الشاشة         ① فتح الشاشة → الأسعار ظاهرة فوراً
② انتظار تحميل        ② اختيار الكميات (بطاقات كبيرة 100px+)
③ + للبالغين          ③ [تأكيد] → شاشة الدفع
④ + للأطفال           ④ [بطاقة/كاش] → مكتمل ✅
⑤ + للمناشف
⑥ اختيار طريقة دفع
⑦ تأكيد
⑧ انتظار response
```

#### Discount Flow — بـ PIN إجباري:
```
الكاشير يضغط [خصم]
    ↓
PinGuardModal (min_level=60 — مدير/محاسب)
    ↓
إدخال PIN
    ↓
[رفض: خطأ واضح] أو [قبول: اختيار نوع الخصم + نسبة]
    ↓
AuditLog تلقائي: من طلب + من وافق + الوقت + القيمة
```

---

### L.3 Waiter (النادل)

**الأدوار:** waiter (level 30)
**الجهاز:** tablet أو هاتف (768px portrait)
**ساعات العمل:** وردية مطعم

#### المهام اليومية:

| # | المهمة | الأهمية |
|---|--------|---------|
| 1 | أخذ طلب جديد على طاولة | حرجة — يومية مئات المرات |
| 2 | إضافة صنف لطلب قائم | يومية |
| 3 | نقل طلب لطاولة أخرى | أسبوعية |
| 4 | طباعة فاتورة مؤقتة | يومية |
| 5 | استدعاء المدير (Void/خصم) | أسبوعية |

#### شاشة النادل (UnifiedPOS — waiter mode):
```
النادل يرى فقط:
  ✅ طاولاته الحالية (مش كل الطاولات)
  ✅ الطلبات الجارية على طاولاته
  ✅ المنيو كامل + search
  ✅ زرار "طلب مساعدة/مدير"

  ❌ لا يرى: الكاش، الوردية، التقارير
  ❌ لا يقدر: يطبق خصم، يلغي أوردر
```

#### Order Taking Workflow — الهدف ≤ 5 clicks:
```
① اختيار الطاولة (visual map — الطاولات اللي عليه ملوّنة)
② اختيار category (sidebar)
③ اختيار الأصناف (ضغط = +1، ضغط طويل = extras)
④ ملاحظة اختيارية (text field صغير)
⑤ [إرسال للمطبخ] ✅
```

#### Touch Optimization:
```
كل زرار: min 48px × 48px
Item cards في المنيو: min 80px × 80px
Category chips: scroll أفقي، min 44px ارتفاع
Back button: دايماً في الـ top-start (RTL: يمين)
Swipe gestures:
  - swipe right على item → حذفه من الأوردر
  - swipe left على طاولة → عرض الطلب
```

---

### L.4 Kitchen / KDS (المطبخ)

**الأدوار:** chef, kitchen (level 30)
**الجهاز:** tablet landscape ثابت على المطبخ (KioskLayout)
**المتطلب:** يشتغل 24/7 بدون تدخل IT

#### المهام:
```
① مشاهدة التذاكر الجديدة فور وصولها
② Bump صنف بصنف (item-level confirmation)
③ أو Bump التذكرة كلها دفعة واحدة
④ عرض الوقت المنقضي لكل تذكرة
⑤ تنبيه بصري + صوتي للطلبات المتأخرة
```

#### KDS الجديد — التحسينات المطلوبة:
```
الحالي:           المطلوب:
بطاقات بيضاء      بطاقات dark (pos-theme)
لا timer ظاهر     timer كبير على كل تذكرة (MM:SS)
لا ألوان urgency  أخضر < 5 دقائق، أصفر 5-10، أحمر > 10
لا صوت            صوت تنبيه للتذاكر الجديدة + للمتأخرة
Bump كامل فقط     Bump صنف بصنف متاح

Ticket card:
┌──────────────────────┐
│ 🍽️ صالة  •  ط.5     │
│ 00:07:32  🟡          │  ← timer + urgency color
│ ─────────────────── │
│ ✅ بيتزا مرغريتا     │  ← اضغط للـ bump
│ ⬜ باستا بولونيز ×2  │
│ ⬜ سيزر سلاد         │
│ ─────────────────── │
│ [Bump الكل ✓]        │
└──────────────────────┘
```

---

### L.5 Housekeeping (التنظيف)

**الأدوار:** employee (level 20) مع permission housekeeping.tasks/update
**الجهاز:** هاتف (375px portrait) — يمشي في الممرات

#### المهام:
```
① رؤية الغرف المطلوب تنظيفها اليوم
② تحديث حالة الغرفة (قيد التنظيف / تم / تحتاج صيانة)
③ الإبلاغ عن مفقودات أو أعطال
```

#### Housekeeping Mobile View:
```
الأولويات للعرض على الهاتف:

①  قائمة الغرف (مرتبة حسب الأولوية):
   ┌─────────────────────────────┐
   │ 🔴 غرفة 101  •  Check-out   │
   │ تنظيف شامل  •  VIP غرفة   │
   │ [بدء التنظيف]               │
   ├─────────────────────────────┤
   │ 🟡 غرفة 203  •  Stayover   │
   │ تنظيف روتيني                │
   │ [بدء التنظيف]               │
   └─────────────────────────────┘

② تحديث الحالة — زرار واحد كبير:
   [قيد التنظيف 🧹] → [تم ✅] → [تحتاج مراجعة ⚠️]

③ الإبلاغ عن عطل:
   زرار [بلّغ عن مشكلة] → يفتح maintenance work order
   تلقائياً بغرقة الغرفة مُعبّأة
```

#### ما لا يراه Housekeeping:
```
❌ بيانات الضيوف (اسم، جنسية، باسبور)
❌ أسعار الغرف
❌ تقارير المبيعات
❌ أي شاشة خارج نطاق مهمته
```

---

### L.6 HR Manager

**الأدوار:** hr_manager (level 70)
**الجهاز:** desktop
**المهام الأسبوعية الحرجة:**

```
① مراجعة طلبات الإجازة (approve/reject)
② متابعة الحضور والغياب
③ إعداد كشف الرواتب الشهري
④ Rota/جدول المناوبات
⑤ متابعة العقوبات والمكافآت
```

#### HRView — إعادة تنظيم الـ tabs حسب التكرار:
```
الحالي (مرتبة عشوائياً تقريباً):
  Employees | Payroll | Attendance | Leaves | ...

المقترح (مرتبة حسب التكرار اليومي):
  اليوم | الحضور | الإجازات | الرواتب | الموظفين | الإعدادات

"اليوم" tab جديدة تجمع:
  - من حضر ومن غاب النهاردة (live)
  - طلبات الإجازة المعلقة (رقم badge)
  - الوردية الجارية
  - تنبيهات عاجلة (رصيد إجازة منتهٍ، عقد منتهٍ)
```

#### Payroll Workflow — الأكثر تعقيداً:
```
① إنشاء payroll run للشهر (زرار واحد)
② مراجعة الـ lines (جدول — بيظهر كل موظف وصافي راتبه)
③ تعديل يدوي اختياري (بدل/حسم)
④ [موافقة المحاسب] → PIN
⑤ [تصدير Excel] أو [طباعة]

الجدول ده لازم يكون VirtualTable (48+ موظف حالياً، هيكبر)
```

---

### L.7 Accountant (المحاسب)

**الأدوار:** accountant (level 70)
**الجهاز:** desktop
**2FA إجباري**

#### المهام الأسبوعية:

```
① مراجعة ورديات الكاشيرية (فروقات الكاش)
② مراجعة الفواتير والقيود المحاسبية
③ إعداد التقارير الشهرية (P&L، Balance Sheet)
④ متابعة الشيكات والبنك
⑤ موافقة كشوف الرواتب
⑥ مراقبة سجل الكاشير (Audit Log)
```

#### FinanceView — إعادة تنظيم:
```
الحالي: tabs مبعثرة بدون ترتيب واضح

المقترح (مرتبة حسب الاستخدام):
  الورديات | الفواتير | البنك | التقارير | الأصول | الإعدادات

"الورديات" tab — الأهم يومياً:
  - قائمة ورديات اليوم مع حالة كل واحدة
  - فروقات الكاش بـ color coding (أخضر=صفر، أحمر=فرق)
  - زرار Void فاتورة بـ PIN
  - زرار تصدير تقرير الوردية

المحاسب يرى سجل الكاشير كاملاً
الكاشير لا يرى سجل نفسه
```

---

### L.8 Manager (المدير)

**الأدوار:** manager (level 60)
**الجهاز:** desktop + tablet (يمشي في المنتجع)

#### Dashboard المدير — المعلومة الحرجة فوراً:

```
┌────────────────────────────────────────────────────┐
│  الإيراد اليوم    الإشغال    الشاطئ    المطعم      │
│  32,500 ج ↑12%   78%        156 ضيف   89 غلاف    │
├────────────────────────────────────────────────────┤
│  🚨 تنبيهات عاجلة (4)                              │
│  • مخزون منخفض: 3 منتج                             │
│  • صيانة متأخرة: 2 أمر                             │
│  • أقساط متأخرة: 5 عقد                             │
│  • شيكات مرتجعة: 1                                 │
├──────────────────────┬─────────────────────────────┤
│  آخر 7 أيام (chart)  │  الموظفون اليوم             │
│                      │  حضر: 24 / غاب: 3           │
│                      │  في الوردية: 12              │
└──────────────────────┴─────────────────────────────┘
```

#### المدير يحتاج بشكل خاص:
```
✅ مراقبة الكاشير live (خصومات/فتح درج/void)
✅ الموافقة على الخصومات بـ PIN من أي شاشة
✅ تقارير سريعة بدون navigation عميق
✅ إشعارات Fraud Detection فورية

Widget مقترح في topbar:
  [🔔 3] → يفتح panel:
    - خصم طلبه كاشير A (موافق/رفض)
    - Void طلبه كاشير B
    - تنبيه fraud: 8 void في ساعة من cashier C
```

---

### L.9 Timeshare Agent

**الأدوار:** timeshare_agent (level 25) + UserPermission صريح
**الجهاز:** desktop
**المهام الأساسية:**

```
① عرض العقود الحالية وحالتها
② تحصيل قسط من عميل
③ جدولة زيارة
④ إنشاء عقد جديد (Wizard 4 خطوات)
⑤ متابعة قائمة الانتظار
```

#### Timeshare Wizard — الأولوية القصوى للـ Wizard component:
```
الخطوة 1 — بيانات العميل:
  Combobox: بحث في CRM customers أو إنشاء جديد
  الحقول: اسم + هاتف + هوية

الخطوة 2 — تفاصيل العقد:
  اختيار الوحدة (visual grid بالوحدات المتاحة)
  اختيار الأسبوع (calendar picker)
  عدد السنوات

الخطوة 3 — خطة الأقساط:
  عدد الأقساط + تواريخها (تُحسب تلقائياً)
  المقدّم المطلوب

الخطوة 4 — مراجعة وتأكيد:
  ملخص كامل
  [تأكيد + توليد العقد PDF]
```

---

### L.10 قواعد Operational UX العامة

```
① كل دور يرى فقط ما يحتاجه
   - Nav links مفلترة بـ hasRole() — موجود ✅
   - محتوى الشاشة مفلتر بـ v-if="auth.hasRole()" — يُراجع
   - Tabs غير المتاحة تُخفى لا تُعطَّل

② كل مهمة حرجة ≤ 5 clicks
   - Check-in: 4 clicks
   - Beach sale: 4 clicks
   - Order taking (waiter): 5 clicks
   - Payroll approve: 4 clicks

③ لا شاشة فارغة بدون توجيه
   - EmptyState دايماً مع "ماذا تفعل الآن؟"
   - مثال: لا توجد حجوزات اليوم → [إنشاء حجز جديد +]

④ الأخطاء واضحة وقابلة للإصلاح
   - رسالة الخطأ تشرح السبب بالعربي
   - دايماً في زرار Retry أو action للإصلاح
   - لا silent failures

⑤ الحالة محفوظة دايماً
   - Sidebar state: localStorage ✅
   - Active tab: يُحفظ في URL query param
   - Form drafts: للـ forms الطويلة (Timeshare Wizard)

⑥ Feedback فوري لكل action
   - بعد Save: toast.success() ✅
   - أثناء loading: زرار disabled + spinner ✅
   - Optimistic UI للـ actions المتوقع نجاحها

⑦ Mobile/Touch للأدوار الميدانية
   - Housekeeping: هاتف portrait فقط
   - Waiter: tablet portrait أو هاتف
   - Cashier: POS landscape + touch
   - كل الأدوار الإدارية: desktop أساساً
```

---

### L.11 Role → Layout → Primary Screen Mapping

| الدور | الـ Layout | الشاشة الأولى بعد Login |
|-------|-----------|------------------------|
| receptionist | BackOfficeLayout | ReceptionView (جديدة) |
| cashier | FieldLayout | BeachPOSView أو UnifiedPOSView |
| waiter | FieldLayout | UnifiedPOSView (dine_in) |
| chef / kitchen | KioskLayout | DiningKDSView |
| employee | BackOfficeLayout | AttendanceView (portal) |
| supervisor | BackOfficeLayout | HousekeepingView |
| hr_manager | BackOfficeLayout | HRView |
| accountant | BackOfficeLayout | FinanceView |
| manager | BackOfficeLayout | DashboardView |
| admin | BackOfficeLayout | DashboardView |
| super_admin | BackOfficeLayout | PermissionsView |
| timeshare_agent | BackOfficeLayout | TimeshareView |

**ملاحظة:** الـ redirect بعد login موجود في `router/index.ts` — يُحدَّث ليوجّه كل دور لشاشته الأساسية بدل `/admin/dashboard` للجميع.
