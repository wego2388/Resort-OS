"""
app/modules/finance/services.py

This file is the stable façade for every finance service function —
every existing caller (`from app.modules.finance import services`,
`services.<name>(...)`, `from app.modules.finance.services import <name>`)
keeps working completely unchanged. The actual implementations were
extracted by capability into app/modules/finance/_services/ (2026-09-07
oversized-file split — see PROJECT_STATUS.md) to keep each file a
manageable, single-purpose size. Add new capabilities as a new
_services/<name>.py module + a re-export line below — never grow this
file or any _services/*.py back into a monolith.
"""
from __future__ import annotations

from app.modules.finance import crud
from app.modules.finance.models import JournalEntry

from app.modules.finance._services._exceptions import (
    FinancialConfigurationError,
    FolioClosedError,
)
from app.modules.finance._services.folios import (
    get_folio_or_404,
    add_folio_charge,
    _to_folio_summary,
    create_folio,
    post_charge,
    settle_folio,
    generate_folio_statement_pdf,
    generate_folios_report_excel,
)
from app.modules.finance._services.payments import (
    add_payment,
    void_payment,
)
from app.modules.finance._services.checks import (
    create_check,
    CheckStatusTransitionError,
    move_check_status,
    CHECK_STATUS_TRANSITIONS,
)
from app.modules.finance._services.shifts import (
    OpenShiftConflictError,
    ShiftCloseInProgressError,
    _lock_open_shift_or_conflict,
    OpenCashierShiftRequiredError,
    record_external_payment,
    open_shift,
    record_cash_movement,
    list_cash_movements,
    _cash_movement_expected_effect,
    build_shift_end_report,
    generate_shift_end_report_pdf,
    close_shift,
    get_latest_handover_note,
    build_active_shifts_response,
    list_shift_invoices,
)
from app.modules.finance._services.discounts import (
    create_discount,
    calculate_order_discount,
    discount_rule_from_orm,
)
from app.modules.finance._services.posting import (
    validate_period_open,
    post_journal_entry,
    post_simple_revenue_journal,
    _build_taxed_sale_entry,
    post_taxed_sale_journal,
    reverse_taxed_sale_journal,
)
from app.modules.finance._services.vouchers import (
    record_expense,
    void_expense,
    pay_expense,
    disburse_custody,
    settle_custody,
    void_custody,
    record_cash_receipt,
    void_cash_receipt,
    list_expenses,
)
from app.modules.finance._services.period_close import (
    close_accounting_period,
    close_accounting_year,
)
from app.modules.finance._services.eta_invoicing import (
    submit_eta_invoice,
)
from app.modules.finance._services.exchange_rates import (
    ensure_default_exchange_rates,
    get_rate,
    convert_to_egp,
    create_exchange_rate,
    list_exchange_rates,
)
from app.modules.finance._services.cost_centers import (
    ensure_default_cost_centers,
    get_cost_center_report,
    DEFAULT_COST_CENTERS,
)
from app.modules.finance._services.reports import (
    get_account_ledger,
    _aging_bucket_label,
    get_aging_report,
    get_trial_balance,
    get_income_statement,
    get_balance_sheet,
    generate_trial_balance_pdf,
    generate_trial_balance_excel,
    generate_income_statement_pdf,
    generate_income_statement_excel,
    generate_balance_sheet_pdf,
    generate_balance_sheet_excel,
)
from app.modules.finance._services.depreciation import (
    _get_or_create_account,
    run_depreciation,
    list_depreciation_entries,
    DEPRECIATION_EXPENSE_ACCOUNT_CODE,
    ACCUMULATED_DEPRECIATION_ACCOUNT_CODE,
)
from app.modules.finance._services.banking import (
    get_bank_account_or_404,
    create_bank_account,
    update_bank_account,
    import_bank_statement_lines,
    auto_match_bank_statement_lines,
    match_bank_statement_line,
    unmatch_bank_statement_line,
    get_bank_reconciliation_summary,
)
from app.modules.finance._services.payment_channels import (
    get_payment_channel_or_404,
    _validate_payment_channel_accounts,
    list_payment_channels,
    create_payment_channel,
    update_payment_channel,
    resolve_payment_channel,
    payment_channel_snapshot,
)

__all__ = [
    "crud", "JournalEntry",
    "FinancialConfigurationError",
    "FolioClosedError",
    "get_folio_or_404",
    "add_folio_charge",
    "_to_folio_summary",
    "create_folio",
    "post_charge",
    "settle_folio",
    "generate_folio_statement_pdf",
    "generate_folios_report_excel",
    "add_payment",
    "void_payment",
    "create_check",
    "CheckStatusTransitionError",
    "move_check_status",
    "CHECK_STATUS_TRANSITIONS",
    "OpenShiftConflictError",
    "ShiftCloseInProgressError",
    "_lock_open_shift_or_conflict",
    "OpenCashierShiftRequiredError",
    "record_external_payment",
    "open_shift",
    "record_cash_movement",
    "list_cash_movements",
    "_cash_movement_expected_effect",
    "build_shift_end_report",
    "generate_shift_end_report_pdf",
    "close_shift",
    "get_latest_handover_note",
    "build_active_shifts_response",
    "list_shift_invoices",
    "create_discount",
    "calculate_order_discount",
    "discount_rule_from_orm",
    "validate_period_open",
    "post_journal_entry",
    "post_simple_revenue_journal",
    "_build_taxed_sale_entry",
    "post_taxed_sale_journal",
    "reverse_taxed_sale_journal",
    "record_expense",
    "void_expense",
    "pay_expense",
    "disburse_custody",
    "settle_custody",
    "void_custody",
    "record_cash_receipt",
    "void_cash_receipt",
    "list_expenses",
    "close_accounting_period",
    "close_accounting_year",
    "submit_eta_invoice",
    "ensure_default_exchange_rates",
    "get_rate",
    "convert_to_egp",
    "create_exchange_rate",
    "list_exchange_rates",
    "ensure_default_cost_centers",
    "get_cost_center_report",
    "DEFAULT_COST_CENTERS",
    "get_account_ledger",
    "_aging_bucket_label",
    "get_aging_report",
    "get_trial_balance",
    "get_income_statement",
    "get_balance_sheet",
    "generate_trial_balance_pdf",
    "generate_trial_balance_excel",
    "generate_income_statement_pdf",
    "generate_income_statement_excel",
    "generate_balance_sheet_pdf",
    "generate_balance_sheet_excel",
    "_get_or_create_account",
    "run_depreciation",
    "list_depreciation_entries",
    "DEPRECIATION_EXPENSE_ACCOUNT_CODE",
    "ACCUMULATED_DEPRECIATION_ACCOUNT_CODE",
    "get_bank_account_or_404",
    "create_bank_account",
    "update_bank_account",
    "import_bank_statement_lines",
    "auto_match_bank_statement_lines",
    "match_bank_statement_line",
    "unmatch_bank_statement_line",
    "get_bank_reconciliation_summary",
    "get_payment_channel_or_404",
    "_validate_payment_channel_accounts",
    "list_payment_channels",
    "create_payment_channel",
    "update_payment_channel",
    "resolve_payment_channel",
    "payment_channel_snapshot",
]
