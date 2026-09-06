"""
app/modules/owner/services.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Services (Decision 0004, Phase 2+3).

This file is the stable façade for every owner-cockpit service function —
every existing caller (`from app.modules.owner import services`,
`services.<name>(...)`) keeps working completely unchanged. The actual
implementations were extracted by capability into app/modules/owner/
_services/ (2026-09-07 oversized-file split — see PROJECT_STATUS.md)
to keep each file a manageable, single-purpose size. Add new capabilities
as a new _services/<name>.py module + a re-export line below — never grow
this file or any _services/*.py back into a monolith.

قواعد ثابتة (لسه سارية زي ما هي):
• كل مقياس مالي أساسي (revenue/expense/cash) يُقرأ من مصدر الحقيقة الموجود
  مباشرةً — لا يُعاد حسابه هنا (Decision 0004 §Numbers must equal the source).
• branch_id يُشتق من الـ session server-side فقط — لا يُقبل من الـ client.
• كل رقم يحمل period + is_provisional + computed_at.
• لا رقم provisional يُقدَّم كأنه نهائي.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from app.modules.owner import crud
from app.modules.owner.models import OwnerAllocationRule, OwnerWatchlist

from app.modules.owner._services.watchlist import (
    get_watchlist,
    add_watchlist_item,
    remove_watchlist_item,
    list_allocation_rules,
    create_draft,
    update_draft,
    delete_draft,
)
from app.modules.owner._services._helpers import (
    _cairo_today,
    _utc_date_bounds,
    _pagination_meta,
    _is_period_provisional,
    _safe_pct,
    _build_period_snapshot,
    _build_period_comparison,
    _build_outlet_breakdown,
    _fetch_b2b_receivables,
    _fetch_timeshare_receivables,
    _fetch_occupancy_now,
    _fetch_beach_capacity_today,
)
from app.modules.owner._services.now_dashboard import (
    get_owner_now,
    get_owner_performance,
    get_now_history,
)
from app.modules.owner._services.sales_analytics import (
    get_sales_performance,
    _fetch_recipe_costs,
    get_beach_performance,
    get_channel_analytics,
    get_expense_analytics,
    get_revenue_breakdown,
    get_procurement_analytics,
)
from app.modules.owner._services.shift_monitor import (
    get_shift_monitor,
    get_exceptions,
    get_shift_history,
    get_shift_invoices,
)
from app.modules.owner._services.hr_summary import (
    get_hr_summary,
)
from app.modules.owner._services.discounts import (
    get_discount_analytics,
)
from app.modules.owner._services.details import (
    get_dining_item_detail,
    get_beach_type_detail,
    get_expense_detail,
    get_revenue_detail,
    get_supplier_detail,
    get_product_detail,
)
from app.modules.owner._services.search import (
    search_everything,
)

__all__ = [
    "crud", "OwnerAllocationRule", "OwnerWatchlist",
    "get_watchlist",
    "add_watchlist_item",
    "remove_watchlist_item",
    "list_allocation_rules",
    "create_draft",
    "update_draft",
    "delete_draft",
    "_cairo_today",
    "_utc_date_bounds",
    "_pagination_meta",
    "_is_period_provisional",
    "_safe_pct",
    "_build_period_snapshot",
    "_build_period_comparison",
    "_build_outlet_breakdown",
    "_fetch_b2b_receivables",
    "_fetch_timeshare_receivables",
    "_fetch_occupancy_now",
    "_fetch_beach_capacity_today",
    "get_owner_now",
    "get_owner_performance",
    "get_now_history",
    "get_sales_performance",
    "_fetch_recipe_costs",
    "get_beach_performance",
    "get_channel_analytics",
    "get_expense_analytics",
    "get_revenue_breakdown",
    "get_procurement_analytics",
    "get_shift_monitor",
    "get_exceptions",
    "get_shift_history",
    "get_shift_invoices",
    "get_hr_summary",
    "get_discount_analytics",
    "get_dining_item_detail",
    "get_beach_type_detail",
    "get_expense_detail",
    "get_revenue_detail",
    "get_supplier_detail",
    "get_product_detail",
    "search_everything",
]
