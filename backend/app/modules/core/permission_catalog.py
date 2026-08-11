"""
app/modules/core/permission_catalog.py
═══════════════════════════════════════════════════════════════════════
كتالوج الصلاحيات التفصيلية — مصدر الحقيقة الوحيد لكل (resource, action) اللي
ممكن تُمنح/تُمنع بشكل صريح لمستخدم معيّن (فوق نظام role level العادي).

**قاعدة مهمة**: كل صف هنا لازم يطابق بالظبط endpoint حقيقي فعليًا مُطبَّق عليه
`Depends(require_permission(resource, action, min_role_level))` — مفيش صفوف
"للمستقبل" أو زينة، عشان الكتالوج يفضل مطابق 100% لما بيتفرض فعليًا. لو ضفت
صلاحية جديدة هنا، لازم تضيف الـ dependency على الـ endpoint المقابل في نفس
الـ commit (وعكسيًا).

**ليه الاستثناءات دي بالذات**: كل واحدة فيها منطق تشغيلي حقيقي لمنح استثناء —
مثلاً "امنح جرسون تقيل ثقة صلاحية إلغاء صنف" أو "امنع مدير معيّن من اعتماد
الرواتب لحد ما يتدرب أكتر" — مش كل endpoint في المشروع (295 endpoint) يستاهل
override، غالبيتهم role level العادي كافي وواضح. الاستثناءات دي بالذات هي
اللي فعلاً بتحصل فيها حالات استثنائية حقيقية في تشغيل منتجع.

min_role_level هنا **لازم يطابق بالظبط** الـ role dependency الأساسية على نفس
الـ endpoint (get_manager_user=60، get_cashier_user=40، get_admin_user=80) —
عشان مستخدم من غير أي UserPermission صريح يفضل سلوكه **مطابق تمامًا** لقبل
ما نضيف الطبقة دي، مفيش أي تغيير سلوك ضمني.
"""

from __future__ import annotations

from typing import TypedDict


class PermissionCatalogEntry(TypedDict):
    resource: str
    action: str
    label_ar: str
    label_en: str
    module: str
    min_role_level: int
    endpoint: str


PERMISSION_CATALOG: list[PermissionCatalogEntry] = [
    {
        "resource": "credit.accounts",
        "action": "view",
        "label_ar": "عرض الحسابات الآجلة الشخصية وكشوفها",
        "label_en": "View personal credit accounts and statements",
        "module": "credit",
        "min_role_level": 60,
        "endpoint": "GET /credit/accounts; GET /credit/accounts/{account_id}; GET /credit/accounts/{account_id}/statement",
    },
    {
        "resource": "credit.accounts",
        "action": "lookup",
        "label_ar": "البحث عن حساب آجل عند نقطة البيع",
        "label_en": "Look up a personal credit account at POS",
        "module": "credit",
        "min_role_level": 40,
        "endpoint": "GET /credit/accounts/lookup",
    },
    {
        "resource": "credit.accounts",
        "action": "create",
        "label_ar": "فتح حساب آجل شخصي",
        "label_en": "Open a personal credit account",
        "module": "credit",
        "min_role_level": 60,
        "endpoint": "POST /credit/accounts",
    },
    {
        "resource": "credit.accounts",
        "action": "change_status",
        "label_ar": "تغيير حالة حساب آجل شخصي",
        "label_en": "Change personal credit account status",
        "module": "credit",
        "min_role_level": 60,
        "endpoint": "PATCH /credit/accounts/{account_id}/status",
    },
    {
        "resource": "credit.accounts",
        "action": "change_limit",
        "label_ar": "تغيير حد حساب آجل شخصي",
        "label_en": "Change a personal credit limit",
        "module": "credit",
        "min_role_level": 80,
        "endpoint": "PATCH /credit/accounts/{account_id}/limit",
    },
    {
        "resource": "credit.transactions",
        "action": "charge",
        "label_ar": "الترحيل على حساب آجل شخصي",
        "label_en": "Charge a personal credit account",
        "module": "credit",
        "min_role_level": 40,
        "endpoint": "POST /credit/accounts/{account_id}/charge",
    },
    {
        "resource": "credit.transactions",
        "action": "collect",
        "label_ar": "تحصيل دفعة حساب آجل شخصي",
        "label_en": "Collect a personal credit payment",
        "module": "credit",
        "min_role_level": 60,
        "endpoint": "POST /credit/accounts/{account_id}/payment",
    },
    {
        "resource": "credit.transactions",
        "action": "reverse",
        "label_ar": "عكس حركة حساب آجل شخصي",
        "label_en": "Reverse a personal credit transaction",
        "module": "credit",
        "min_role_level": 60,
        "endpoint": "POST /credit/accounts/{account_id}/reverse",
    },
    {
        "resource": "finance.close_period",
        "action": "execute",
        "label_ar": "قفل الفترة المحاسبية",
        "label_en": "Close accounting period",
        "module": "finance",
        "min_role_level": 60,
        "endpoint": "POST /finance/periods/{year}/{month}/close",
    },
    {
        "resource": "dining.void_order_item",
        "action": "execute",
        "label_ar": "إلغاء صنف من طلب (دايننج موحّد)",
        "label_en": "Void an order item (unified dining)",
        "module": "dining",
        "min_role_level": 40,
        "endpoint": "PATCH /dining/orders/{order_id}/items/{item_id}/void",
    },
    {
        "resource": "dining.refund_order_item",
        "action": "execute",
        "label_ar": "مرتجع صنف بعد الدفع (دايننج موحّد)",
        "label_en": "Refund an order item after payment (unified dining)",
        "module": "dining",
        "min_role_level": 60,
        "endpoint": "PATCH /dining/orders/{order_id}/items/{item_id}/refund",
    },
    {
        "resource": "beach.void_transaction",
        "action": "execute",
        "label_ar": "إلغاء معاملة شاطئ",
        "label_en": "Void a beach transaction",
        "module": "beach",
        "min_role_level": 60,
        "endpoint": "POST /beach/transactions/{tx_id}/void",
    },
    {
        "resource": "hr.approve_payroll_run",
        "action": "approve",
        "label_ar": "اعتماد صرف الرواتب",
        "label_en": "Approve a payroll run",
        "module": "hr",
        "min_role_level": 80,
        "endpoint": "POST /hr/payroll-runs/{run_id}/approve",
    },
    {
        "resource": "hr.approve_leave",
        "action": "approve",
        "label_ar": "اعتماد طلب إجازة",
        "label_en": "Approve a leave request",
        "module": "hr",
        "min_role_level": 60,
        "endpoint": "PATCH /hr/leave-requests/{request_id}/approve",
    },
    {
        "resource": "timeshare.cancel_contract",
        "action": "execute",
        "label_ar": "إلغاء عقد ملكية جزئية",
        "label_en": "Cancel a fractional ownership contract",
        "module": "timeshare",
        # min_role_level=55 عمدًا (مش 60) — طلب Mohamed 2026-08-03: عمليات
        # الملكية الجزئية الإدارية بقت gated بـget_timeshare_admin_user
        # (role='timeshare_admin'، level=55 عمدًا) مش get_manager_user
        # العام؛ لازم الرقم هنا يطابق عشان مدير الملكية الجزئية الفعلي (55) يعدي
        # من الـrequire_permission fallback زي ما يعدي من بوابة الـrole.
        "min_role_level": 55,
        "endpoint": "POST /timeshare/contracts/{contract_id}/cancel",
    },
    {
        "resource": "pms.cancel_booking",
        "action": "execute",
        "label_ar": "إلغاء حجز غرفة",
        "label_en": "Cancel a room booking",
        "module": "pms",
        "min_role_level": 60,
        "endpoint": "POST /pms/bookings/{booking_id}/cancel",
    },
    # ── PMS ──────────────────────────────────────────────────────────────────
    # PMS reads contain guest identity/stay details and operational room state.
    # They must not fall back to "any active account". Explicit grants allow a
    # narrowly-scoped employee (for example housekeeping) without inventing a
    # broad role that also opens unrelated modules.
    {
        "resource": "pms.rooms",
        "action": "view",
        "label_ar": "عرض أنواع الغرف والغرف المتاحة",
        "label_en": "View room types, rooms, and availability",
        "module": "pms",
        "min_role_level": 40,
        "endpoint": "GET /pms/room-types; GET /pms/rooms; GET /pms/rooms/available",
    },
    {
        "resource": "pms.room_configuration",
        "action": "manage",
        "label_ar": "إدارة أنواع الغرف والغرف",
        "label_en": "Manage room types and rooms",
        "module": "pms",
        "min_role_level": 80,
        "endpoint": "POST /pms/room-types; POST /pms/rooms",
    },
    {
        "resource": "pms.rooms",
        "action": "update_status",
        "label_ar": "تغيير حالة الغرفة",
        "label_en": "Update room status",
        "module": "pms",
        "min_role_level": 60,
        "endpoint": "PATCH /pms/rooms/{room_id}/status",
    },
    {
        "resource": "pms.bookings",
        "action": "view",
        "label_ar": "عرض الحجوزات وبيانات الإقامة",
        "label_en": "View bookings and stay details",
        "module": "pms",
        "min_role_level": 40,
        "endpoint": "GET /pms/bookings; GET /pms/bookings/{booking_id}",
    },
    {
        "resource": "pms.bookings",
        "action": "create",
        "label_ar": "إنشاء حجز غرفة",
        "label_en": "Create a room booking",
        "module": "pms",
        "min_role_level": 40,
        "endpoint": "POST /pms/bookings",
    },
    {
        "resource": "pms.bookings",
        "action": "check_in",
        "label_ar": "تسجيل وصول الضيف",
        "label_en": "Check a guest in",
        "module": "pms",
        "min_role_level": 40,
        "endpoint": "POST /pms/bookings/{booking_id}/checkin",
    },
    {
        "resource": "pms.bookings",
        "action": "check_out",
        "label_ar": "تسجيل مغادرة الضيف",
        "label_en": "Check a guest out",
        "module": "pms",
        "min_role_level": 40,
        "endpoint": "POST /pms/bookings/{booking_id}/checkout",
    },
    {
        "resource": "pms.bookings",
        "action": "early_late",
        "label_ar": "تسجيل وصول مبكر أو مغادرة متأخرة",
        "label_en": "Record early arrival or late departure",
        "module": "pms",
        "min_role_level": 40,
        "endpoint": "POST /pms/bookings/{booking_id}/early-late",
    },
    {
        "resource": "pms.housekeeping",
        "action": "view",
        "label_ar": "عرض مهام الإشراف الداخلي",
        "label_en": "View housekeeping tasks",
        "module": "pms",
        "min_role_level": 40,
        "endpoint": "GET /pms/housekeeping/tasks",
    },
    {
        "resource": "pms.housekeeping",
        "action": "update",
        "label_ar": "تحديث مهام الإشراف الداخلي",
        "label_en": "Update housekeeping tasks",
        "module": "pms",
        "min_role_level": 40,
        "endpoint": "PATCH /pms/housekeeping/tasks/{task_id}",
    },
    {
        "resource": "pms.rate_plans",
        "action": "view",
        "label_ar": "عرض خطط أسعار الغرف",
        "label_en": "View room rate plans",
        "module": "pms",
        "min_role_level": 40,
        "endpoint": "GET /pms/rate-plans; GET /pms/rate-plans/{plan_id}",
    },
    {
        "resource": "pms.rate_plans",
        "action": "manage",
        "label_ar": "إدارة خطط أسعار الغرف",
        "label_en": "Manage room rate plans",
        "module": "pms",
        "min_role_level": 80,
        "endpoint": "POST /pms/rate-plans; PATCH /pms/rate-plans/{plan_id}",
    },
    {
        "resource": "pms.night_audit",
        "action": "view",
        "label_ar": "عرض سجل المراجعة الليلية",
        "label_en": "View night audit history",
        "module": "pms",
        "min_role_level": 60,
        "endpoint": "GET /pms/night-audit",
    },
    {
        "resource": "pms.night_audit",
        "action": "run",
        "label_ar": "تشغيل المراجعة الليلية",
        "label_en": "Run the night audit",
        "module": "pms",
        "min_role_level": 80,
        "endpoint": "POST /pms/night-audit/run",
    },
    {
        "resource": "inventory.approve_stock_count",
        "action": "approve",
        "label_ar": "اعتماد جرد مخزون",
        "label_en": "Approve a stock count",
        "module": "inventory",
        "min_role_level": 60,
        "endpoint": "PATCH /inventory/stock-counts/{count_id}/approve",
    },
    {
        "resource": "crm.unblacklist_customer",
        "action": "execute",
        "label_ar": "رفع حظر عن عميل",
        "label_en": "Remove a customer from the blacklist",
        "module": "crm",
        "min_role_level": 60,
        "endpoint": "DELETE /crm/customers/{customer_id}/blacklist",
    },
    {
        "resource": "finance.void_payment",
        "action": "execute",
        "label_ar": "إلغاء دفعة",
        "label_en": "Void a payment",
        "module": "finance",
        "min_role_level": 60,
        "endpoint": "POST /finance/payments/{payment_id}/void",
    },
    # ── Fractional Ownership ────────────────────────────────────────────────────────────
    # الصلاحيات دي بتسمح بمنح timeshare_agent (level=25) وصول محدود للملكية جزئية
    # بشكل صريح، بدون أي وصول لباقي الموديولات.
    {
        "resource": "timeshare.access",
        "action": "view",
        "label_ar": "عرض وحدة الملكية الجزئية (الوصول الأساسي)",
        "label_en": "View the fractional ownership module (base access)",
        "module": "timeshare",
        "min_role_level": 40,
        "endpoint": "GET /timeshare/* (الوصول العام للوحدة)",
    },
    {
        "resource": "timeshare.contracts",
        "action": "view",
        "label_ar": "عرض عقود الملكية الجزئية",
        "label_en": "View fractional ownership contracts",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/contracts",
    },
    {
        "resource": "timeshare.contracts",
        "action": "create",
        "label_ar": "إنشاء عقد ملكية جزئية",
        "label_en": "Create a fractional ownership contract",
        "module": "timeshare",
        "min_role_level": 55,  # يطابق get_timeshare_admin_user — راجع تعليق timeshare.cancel_contract فوق
        "endpoint": "POST /timeshare/contracts",
    },
    {
        "resource": "timeshare.contracts",
        "action": "edit",
        "label_ar": "تعديل بيانات عقد ملكية جزئية",
        "label_en": "Edit a fractional ownership contract",
        "module": "timeshare",
        "min_role_level": 55,
        "endpoint": "PATCH /timeshare/contracts/{contract_id}",
    },
    {
        "resource": "timeshare.installments",
        "action": "view",
        "label_ar": "عرض الأقساط",
        "label_en": "View installments",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/installments",
    },
    {
        "resource": "timeshare.installments",
        "action": "collect",
        "label_ar": "تحصيل قسط ملكية جزئية",
        "label_en": "Collect a fractional ownership installment",
        "module": "timeshare",
        "min_role_level": 40,
        "endpoint": "POST /timeshare/installments/{inst_id}/pay",
    },
    {
        "resource": "timeshare.maintenance_dues",
        "action": "view",
        "label_ar": "عرض مستحقات الصيانة",
        "label_en": "View maintenance dues",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/contracts/{contract_id}/maintenance-dues",
    },
    {
        "resource": "timeshare.maintenance_dues",
        "action": "collect",
        "label_ar": "تحصيل رسم صيانة ملكية جزئية",
        "label_en": "Collect a fractional ownership maintenance due",
        "module": "timeshare",
        "min_role_level": 40,
        "endpoint": "POST /timeshare/maintenance-dues/{due_id}/pay",
    },
    {
        "resource": "timeshare.maintenance_dues",
        "action": "generate",
        "label_ar": "توليد مستحقات الصيانة السنوية",
        "label_en": "Generate annual maintenance dues",
        "module": "timeshare",
        "min_role_level": 55,  # يطابق get_timeshare_admin_user — راجع تعليق timeshare.cancel_contract
        "endpoint": "POST /timeshare/maintenance-dues/generate",
    },
    {
        "resource": "timeshare.visits",
        "action": "view",
        "label_ar": "عرض زيارات الملكية الجزئية",
        "label_en": "View fractional ownership visits",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/visits",
    },
    {
        "resource": "timeshare.visits",
        "action": "create",
        "label_ar": "جدولة زيارة ملكية جزئية",
        "label_en": "Schedule a fractional ownership visit",
        "module": "timeshare",
        "min_role_level": 40,
        "endpoint": "POST /timeshare/visits",
    },
    {
        "resource": "timeshare.visits",
        "action": "edit",
        "label_ar": "تحديث حالة زيارة ملكية جزئية",
        "label_en": "Update a fractional ownership visit's status",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "PATCH /timeshare/visits/{visit_id}",
    },
    {
        "resource": "timeshare.calendar",
        "action": "view",
        "label_ar": "عرض كالندر الملكية الجزئية",
        "label_en": "View the fractional ownership calendar",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/calendar",
    },
    {
        "resource": "timeshare.waitlist",
        "action": "view",
        "label_ar": "عرض قائمة الانتظار",
        "label_en": "View the waitlist",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/waitlist",
    },
    {
        "resource": "timeshare.waitlist",
        "action": "create",
        "label_ar": "إضافة لقائمة الانتظار",
        "label_en": "Add to the waitlist",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "POST /timeshare/waitlist",
    },
    # ── Fractional Ownership — بوابة العميل (طلبات الزيارة + خدمة العملاء، 2026-08-03) ──
    {
        "resource": "timeshare.visit_requests",
        "action": "view",
        "label_ar": "عرض طلبات زيارة العملاء",
        "label_en": "View customer visit requests",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/visit-requests",
    },
    {
        "resource": "timeshare.visit_requests",
        "action": "approve",
        "label_ar": "الموافقة/رفض طلب زيارة",
        "label_en": "Approve or reject a visit request",
        "module": "timeshare",
        "min_role_level": 55,  # يطابق get_timeshare_admin_user — راجع تعليق timeshare.cancel_contract
        "endpoint": "POST /timeshare/visit-requests/{id}/approve|reject",
    },
    {
        "resource": "timeshare.support_tickets",
        "action": "view",
        "label_ar": "عرض تذاكر دعم عملاء الملكية الجزئية",
        "label_en": "View fractional ownership customer-service tickets",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/support-tickets",
    },
    {
        "resource": "timeshare.support_tickets",
        "action": "respond",
        "label_ar": "الرد على تذكرة دعم / تغيير حالتها",
        "label_en": "Reply to a support ticket / change its status",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "POST /timeshare/support-tickets/{id}/reply",
    },
]


def get_catalog_entry(resource: str, action: str) -> PermissionCatalogEntry | None:
    for entry in PERMISSION_CATALOG:
        if entry["resource"] == resource and entry["action"] == action:
            return entry
    return None
