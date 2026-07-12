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
        "resource": "restaurant.void_order_item",
        "action": "execute",
        "label_ar": "إلغاء صنف من طلب (مطعم)",
        "module": "restaurant",
        "min_role_level": 40,
        "endpoint": "PATCH /restaurant/orders/{order_id}/items/{item_id}/void",
    },
    {
        "resource": "cafe.void_order_item",
        "action": "execute",
        "label_ar": "إلغاء صنف من طلب (كافيه)",
        "module": "cafe",
        "min_role_level": 40,
        "endpoint": "PATCH /cafe/orders/{order_id}/items/{item_id}/void",
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
        "resource": "restaurant.refund_order_item",
        "action": "execute",
        "label_ar": "مرتجع صنف بعد الدفع (مطعم)",
        "module": "restaurant",
        "min_role_level": 60,
        "endpoint": "PATCH /restaurant/orders/{order_id}/items/{item_id}/refund",
    },
    {
        "resource": "cafe.refund_order_item",
        "action": "execute",
        "label_ar": "مرتجع صنف بعد الدفع (كافيه)",
        "module": "cafe",
        "min_role_level": 60,
        "endpoint": "PATCH /cafe/orders/{order_id}/items/{item_id}/refund",
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
]


def get_catalog_entry(resource: str, action: str) -> PermissionCatalogEntry | None:
    for entry in PERMISSION_CATALOG:
        if entry["resource"] == resource and entry["action"] == action:
            return entry
    return None
