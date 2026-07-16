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
    module: str
    min_role_level: int
    endpoint: str


PERMISSION_CATALOG: list[PermissionCatalogEntry] = [
    {
        "resource": "finance.close_period",
        "action": "execute",
        "label_ar": "قفل الفترة المحاسبية",
        "module": "finance",
        "min_role_level": 60,
        "endpoint": "POST /finance/periods/{year}/{month}/close",
    },
    {
        "resource": "dining.void_order_item",
        "action": "execute",
        "label_ar": "إلغاء صنف من طلب (دايننج موحّد)",
        "module": "dining",
        "min_role_level": 40,
        "endpoint": "PATCH /dining/orders/{order_id}/items/{item_id}/void",
    },
    {
        "resource": "dining.refund_order_item",
        "action": "execute",
        "label_ar": "مرتجع صنف بعد الدفع (دايننج موحّد)",
        "module": "dining",
        "min_role_level": 60,
        "endpoint": "PATCH /dining/orders/{order_id}/items/{item_id}/refund",
    },
    {
        "resource": "beach.void_transaction",
        "action": "execute",
        "label_ar": "إلغاء معاملة شاطئ",
        "module": "beach",
        "min_role_level": 60,
        "endpoint": "POST /beach/transactions/{tx_id}/void",
    },
    {
        "resource": "hr.approve_payroll_run",
        "action": "approve",
        "label_ar": "اعتماد صرف الرواتب",
        "module": "hr",
        "min_role_level": 80,
        "endpoint": "POST /hr/payroll-runs/{run_id}/approve",
    },
    {
        "resource": "hr.approve_leave",
        "action": "approve",
        "label_ar": "اعتماد طلب إجازة",
        "module": "hr",
        "min_role_level": 60,
        "endpoint": "PATCH /hr/leave-requests/{request_id}/approve",
    },
    {
        "resource": "timeshare.cancel_contract",
        "action": "execute",
        "label_ar": "إلغاء عقد تايم شير",
        "module": "timeshare",
        "min_role_level": 60,
        "endpoint": "POST /timeshare/contracts/{contract_id}/cancel",
    },
    {
        "resource": "pms.cancel_booking",
        "action": "execute",
        "label_ar": "إلغاء حجز غرفة",
        "module": "pms",
        "min_role_level": 60,
        "endpoint": "POST /pms/bookings/{booking_id}/cancel",
    },
    {
        "resource": "inventory.approve_stock_count",
        "action": "approve",
        "label_ar": "اعتماد جرد مخزون",
        "module": "inventory",
        "min_role_level": 60,
        "endpoint": "PATCH /inventory/stock-counts/{count_id}/approve",
    },
    {
        "resource": "crm.unblacklist_customer",
        "action": "execute",
        "label_ar": "رفع حظر عن عميل",
        "module": "crm",
        "min_role_level": 60,
        "endpoint": "DELETE /crm/customers/{customer_id}/blacklist",
    },
    {
        "resource": "finance.void_payment",
        "action": "execute",
        "label_ar": "إلغاء دفعة",
        "module": "finance",
        "min_role_level": 60,
        "endpoint": "POST /finance/payments/{payment_id}/void",
    },
    # ── Timeshare ────────────────────────────────────────────────────────────
    # الصلاحيات دي بتسمح بمنح timeshare_agent (level=25) وصول محدود للتايم شير
    # بشكل صريح، بدون أي وصول لباقي الموديولات.
    {
        "resource": "timeshare.access",
        "action": "view",
        "label_ar": "عرض وحدة التايم شير (الوصول الأساسي)",
        "module": "timeshare",
        "min_role_level": 40,
        "endpoint": "GET /timeshare/* (الوصول العام للوحدة)",
    },
    {
        "resource": "timeshare.contracts",
        "action": "view",
        "label_ar": "عرض عقود التايم شير",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/contracts",
    },
    {
        "resource": "timeshare.contracts",
        "action": "create",
        "label_ar": "إنشاء عقد تايم شير",
        "module": "timeshare",
        "min_role_level": 60,
        "endpoint": "POST /timeshare/contracts",
    },
    {
        "resource": "timeshare.contracts",
        "action": "edit",
        "label_ar": "تعديل بيانات عقد تايم شير",
        "module": "timeshare",
        "min_role_level": 60,
        "endpoint": "PATCH /timeshare/contracts/{contract_id}",
    },
    {
        "resource": "timeshare.installments",
        "action": "view",
        "label_ar": "عرض الأقساط",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/installments",
    },
    {
        "resource": "timeshare.installments",
        "action": "collect",
        "label_ar": "تحصيل قسط تايم شير",
        "module": "timeshare",
        "min_role_level": 40,
        "endpoint": "POST /timeshare/installments/{inst_id}/pay",
    },
    {
        "resource": "timeshare.visits",
        "action": "view",
        "label_ar": "عرض زيارات التايم شير",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/visits",
    },
    {
        "resource": "timeshare.visits",
        "action": "create",
        "label_ar": "جدولة زيارة تايم شير",
        "module": "timeshare",
        "min_role_level": 40,
        "endpoint": "POST /timeshare/visits",
    },
    {
        "resource": "timeshare.visits",
        "action": "edit",
        "label_ar": "تحديث حالة زيارة تايم شير",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "PATCH /timeshare/visits/{visit_id}",
    },
    {
        "resource": "timeshare.calendar",
        "action": "view",
        "label_ar": "عرض كالندر التايم شير",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/calendar",
    },
    {
        "resource": "timeshare.waitlist",
        "action": "view",
        "label_ar": "عرض قائمة الانتظار",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "GET /timeshare/waitlist",
    },
    {
        "resource": "timeshare.waitlist",
        "action": "create",
        "label_ar": "إضافة لقائمة الانتظار",
        "module": "timeshare",
        "min_role_level": 25,
        "endpoint": "POST /timeshare/waitlist",
    },
]


def get_catalog_entry(resource: str, action: str) -> PermissionCatalogEntry | None:
    for entry in PERMISSION_CATALOG:
        if entry["resource"] == resource and entry["action"] == action:
            return entry
    return None
