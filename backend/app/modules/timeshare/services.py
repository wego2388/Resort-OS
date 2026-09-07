"""
app/modules/timeshare/services.py

This file is the stable façade for every timeshare service function —
every existing caller (`from app.modules.timeshare import services`,
`services.<name>(...)`, `from app.modules.timeshare.services import <name>`)
keeps working completely unchanged. The actual implementations were
extracted by capability into app/modules/timeshare/_services/ (2026-09-07
oversized-file split — see PROJECT_STATUS.md) to keep each file a
manageable, single-purpose size. Add new capabilities as a new
_services/<name>.py module + a re-export line below — never grow this
file or any _services/*.py back into a monolith.
"""
from __future__ import annotations

from app.modules.timeshare import crud

from app.modules.timeshare._services._exceptions import (
    VisitConflictError,
    PaymentConflictError,
)
from app.modules.timeshare._services.contracts import (
    get_contract_or_404,
    create_contract,
    _generate_maintenance_due_for_new_contract,
    _post_deferred_revenue_journal,
    update_contract,
    _REFUND_METHOD_CREDIT_ACCOUNT,
    _contract_refundable_amount,
    cancel_contract,
    _post_contract_cancellation_refund_journal,
    _audit_contract_cancellation,
    transfer_unit,
)
from app.modules.timeshare._services.installments import (
    _lock_installment_or_raise,
    pay_installment,
    _has_any_overdue_balance,
    _PAYMENT_METHOD_DEBIT_ACCOUNT,
    _post_installment_payment_journal,
    _audit_installment_payment,
    list_installments,
)
from app.modules.timeshare._services.maintenance import (
    _lock_maintenance_due_or_raise,
    pay_maintenance_due,
    _post_maintenance_payment_journal,
    _audit_maintenance_payment,
    list_maintenance_dues_for_branch,
    generate_annual_maintenance_dues,
    MAINTENANCE_FEES_2026_VERSION,
    seed_2026_maintenance_fee_rules,
    get_recommended_maintenance_fee,
)
from app.modules.timeshare._services.waitlist import (
    add_to_waitlist,
    update_waitlist_status,
)
from app.modules.timeshare._services.dashboard import (
    generate_monthly_collection_report,
    generate_contract_pdf,
    get_cs_summary,
    get_sales_dashboard,
    generate_sales_dashboard_excel,
    get_stats,
)
from app.modules.timeshare._services.calendar_availability import (
    get_calendar,
    get_available_weeks,
    get_units_availability,
    get_upcoming_visits,
)
from app.modules.timeshare._services.units import (
    create_unit,
    update_unit,
    create_unit_pair,
    deactivate_unit_pair,
)
from app.modules.timeshare._services.visits import (
    create_visit,
    _create_entitlement_pair_visit,
    update_visit,
)
from app.modules.timeshare._services.import_excel import (
    _coerce_cell,
    import_contracts_excel,
)
from app.modules.timeshare._services.owner_portal import (
    OwnerVerificationError,
    _hash_otp,
    _normalize_phone_for_match,
    request_owner_otp,
    _issue_owner_portal_token,
    confirm_owner_otp,
    verify_owner_portal_token,
)
from app.modules.timeshare._services.visit_requests_support import (
    HOLIDAY_COOLDOWN_YEARS,
    HOLIDAY_COOLDOWN_VERSION,
    _peak_event_years_for_contract,
    _check_peak_rules,
    request_visit,
    approve_visit_request,
    reject_visit_request,
    submit_support_ticket,
    reply_to_ticket,
    update_ticket_status,
)
from app.modules.timeshare._services.staff import (
    provision_timeshare_agent,
    list_eligible_timeshare_employees,
    list_timeshare_staff,
    set_timeshare_staff_active,
)

__all__ = [
    "crud",
    "VisitConflictError",
    "PaymentConflictError",
    "get_contract_or_404",
    "create_contract",
    "_generate_maintenance_due_for_new_contract",
    "_post_deferred_revenue_journal",
    "update_contract",
    "_REFUND_METHOD_CREDIT_ACCOUNT",
    "_contract_refundable_amount",
    "cancel_contract",
    "_post_contract_cancellation_refund_journal",
    "_audit_contract_cancellation",
    "transfer_unit",
    "_lock_installment_or_raise",
    "pay_installment",
    "_has_any_overdue_balance",
    "_PAYMENT_METHOD_DEBIT_ACCOUNT",
    "_post_installment_payment_journal",
    "_audit_installment_payment",
    "list_installments",
    "_lock_maintenance_due_or_raise",
    "pay_maintenance_due",
    "_post_maintenance_payment_journal",
    "_audit_maintenance_payment",
    "list_maintenance_dues_for_branch",
    "generate_annual_maintenance_dues",
    "MAINTENANCE_FEES_2026_VERSION",
    "seed_2026_maintenance_fee_rules",
    "get_recommended_maintenance_fee",
    "add_to_waitlist",
    "update_waitlist_status",
    "generate_monthly_collection_report",
    "generate_contract_pdf",
    "get_cs_summary",
    "get_sales_dashboard",
    "generate_sales_dashboard_excel",
    "get_stats",
    "get_calendar",
    "get_available_weeks",
    "get_units_availability",
    "get_upcoming_visits",
    "create_unit",
    "update_unit",
    "create_unit_pair",
    "deactivate_unit_pair",
    "create_visit",
    "_create_entitlement_pair_visit",
    "update_visit",
    "_coerce_cell",
    "import_contracts_excel",
    "OwnerVerificationError",
    "_hash_otp",
    "_normalize_phone_for_match",
    "request_owner_otp",
    "_issue_owner_portal_token",
    "confirm_owner_otp",
    "verify_owner_portal_token",
    "HOLIDAY_COOLDOWN_YEARS",
    "HOLIDAY_COOLDOWN_VERSION",
    "_peak_event_years_for_contract",
    "_check_peak_rules",
    "request_visit",
    "approve_visit_request",
    "reject_visit_request",
    "submit_support_ticket",
    "reply_to_ticket",
    "update_ticket_status",
    "provision_timeshare_agent",
    "list_eligible_timeshare_employees",
    "list_timeshare_staff",
    "set_timeshare_staff_active",
]
