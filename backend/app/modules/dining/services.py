"""
app/modules/dining/services.py

This file is the stable façade for every dining service function —
every existing caller (`from app.modules.dining import services`,
`services.<name>(...)`, `patch("app.modules.dining.services.X", ...)`)
keeps working completely unchanged. The actual implementations were
extracted by capability into app/modules/dining/_services/ (2026-09-07
oversized-file split — see PROJECT_STATUS.md) to keep each file a
manageable, single-purpose size.

⚠️ IMPORTANT — patchability contract: tests patch `services._service_
charge_pct` and `services.local_now` directly (`unittest.mock.patch`
with the string path `app.modules.dining.services.X`). Every call site
of these two names — regardless of which _services/*.py submodule it
physically lives in — MUST look them up dynamically via this façade
(`from app.modules.dining import services as _dining_services; ...
_dining_services._service_charge_pct(...)`) rather than a bare name
bound by a static cross-module import — a static import binds its own
private copy of the name in that submodule's globals, which a patch on
this façade module would never reach. Do not "simplify" those call
sites back to a plain cross-import without re-verifying every test that
patches these two names still exercises the real mocked behavior.
"""
from __future__ import annotations

from app.modules.dining import crud
from app.resort_os.timezone_utils import local_now

from app.modules.dining._services._exceptions import (
    OrderPaymentConcurrencyError,
    OrderAlreadyPaidError,
    InvalidOrderTotalError,
    InvalidPaymentMethodError,
    IdempotencyConflictError,
    NoOpenShiftError,
    PaymentAllocationError,
)
from app.modules.dining._services._helpers import (
    assert_order_transition,
    _get_order_or_404,
    _lock_order_or_conflict,
    _get_outlet_or_404,
    _service_charge_pct,
    _order_price_components,
    _snapshot_selected_extras,
    _outlet_cost_center_code,
    _build_outlet_revenue_splits,
    _resolve_extras,
    _resolve_variant,
    _is_item_available_now,
    _check_item_available_now,
    _effective_recipe,
    compute_item_cost,
    ORDER_TRANSITIONS,
    _ORDER_TYPE_SVC_OVERRIDE_ATTR,
    _OUTLET_TYPE_TO_COST_CENTER,
)
from app.modules.dining._services.recipes_variants import (
    build_recipe_line_read,
    add_recipe_line,
    update_recipe_line,
    remove_recipe_line,
    compute_variant_cost,
    build_variant_recipe_line_read,
    build_variant_read,
    add_variant,
    update_variant,
    remove_variant,
    add_variant_recipe_line,
    update_variant_recipe_line,
    remove_variant_recipe_line,
)
from app.modules.dining._services.orders import (
    assert_guest_self_order_enabled,
    create_order,
    _raise_order_integrity_error,
    _create_kitchen_tickets_for_items,
    _ensure_kitchen_tickets_for_order,
    add_items_to_order,
    sync_offline_order,
    update_order_status,
)
from app.modules.dining._services.settlement import (
    _settlement_intent_hash,
    settle_order,
    _settle_room_tender,
    _post_folio_revenue_splits,
    _post_complimentary_expense_if_applicable,
    _settle_direct_tender,
    _settle_credit_tender,
    _mark_order_paid,
    _deduct_inventory_for_order,
)
from app.modules.dining._services.order_ops import (
    void_order_item,
    transfer_order_table,
    transfer_order_waiter,
    merge_orders,
    split_bill,
    bump_order_item_status,
)
from app.modules.dining._services.discounts import (
    _recompute_order_totals,
    _sync_kitchen_tickets_for_order,
    _order_local_date_and_time,
    _normalize_order_date,
    _build_discount_line_items,
    _recompute_discount_for_rule,
    _customer_group_discount_amount,
    _resolve_order_discount,
    apply_order_discount,
)
from app.modules.dining._services.refunds import (
    refund_order_item,
    _refund_order_item_locked,
    _post_refund_reversals,
    _reduce_folio_charge_for_refund,
    _post_order_folio_refund_reversal_journal,
)
from app.modules.dining._services.kds import (
    _order_item_statuses,
    _ticket_read_dict,
    get_kds_tickets,
    update_kitchen_ticket_status,
)
from app.modules.dining._services.receipts import (
    generate_receipt_pdf,
    _ORDER_TYPE_LABELS_AR,
)
from app.modules.dining._services.reports import (
    get_shift_sold_items,
    get_shift_category_summary,
    get_food_cost_report,
    generate_food_cost_excel,
)
from app.modules.dining._services.outlets import (
    create_outlet,
    update_outlet,
)

__all__ = [
    "crud", "local_now",
    "OrderPaymentConcurrencyError",
    "OrderAlreadyPaidError",
    "InvalidOrderTotalError",
    "InvalidPaymentMethodError",
    "IdempotencyConflictError",
    "NoOpenShiftError",
    "PaymentAllocationError",
    "assert_order_transition",
    "_get_order_or_404",
    "_lock_order_or_conflict",
    "_get_outlet_or_404",
    "_service_charge_pct",
    "_order_price_components",
    "_snapshot_selected_extras",
    "_outlet_cost_center_code",
    "_build_outlet_revenue_splits",
    "_resolve_extras",
    "_resolve_variant",
    "_is_item_available_now",
    "_check_item_available_now",
    "_effective_recipe",
    "compute_item_cost",
    "ORDER_TRANSITIONS",
    "_ORDER_TYPE_SVC_OVERRIDE_ATTR",
    "_OUTLET_TYPE_TO_COST_CENTER",
    "build_recipe_line_read",
    "add_recipe_line",
    "update_recipe_line",
    "remove_recipe_line",
    "compute_variant_cost",
    "build_variant_recipe_line_read",
    "build_variant_read",
    "add_variant",
    "update_variant",
    "remove_variant",
    "add_variant_recipe_line",
    "update_variant_recipe_line",
    "remove_variant_recipe_line",
    "assert_guest_self_order_enabled",
    "create_order",
    "_raise_order_integrity_error",
    "_create_kitchen_tickets_for_items",
    "_ensure_kitchen_tickets_for_order",
    "add_items_to_order",
    "sync_offline_order",
    "update_order_status",
    "_settlement_intent_hash",
    "settle_order",
    "_settle_room_tender",
    "_post_folio_revenue_splits",
    "_post_complimentary_expense_if_applicable",
    "_settle_direct_tender",
    "_settle_credit_tender",
    "_mark_order_paid",
    "_deduct_inventory_for_order",
    "void_order_item",
    "transfer_order_table",
    "transfer_order_waiter",
    "merge_orders",
    "split_bill",
    "bump_order_item_status",
    "_recompute_order_totals",
    "_sync_kitchen_tickets_for_order",
    "_order_local_date_and_time",
    "_normalize_order_date",
    "_build_discount_line_items",
    "_recompute_discount_for_rule",
    "_customer_group_discount_amount",
    "_resolve_order_discount",
    "apply_order_discount",
    "refund_order_item",
    "_refund_order_item_locked",
    "_post_refund_reversals",
    "_reduce_folio_charge_for_refund",
    "_post_order_folio_refund_reversal_journal",
    "_order_item_statuses",
    "_ticket_read_dict",
    "get_kds_tickets",
    "update_kitchen_ticket_status",
    "generate_receipt_pdf",
    "_ORDER_TYPE_LABELS_AR",
    "get_shift_sold_items",
    "get_shift_category_summary",
    "get_food_cost_report",
    "generate_food_cost_excel",
    "create_outlet",
    "update_outlet",
]
