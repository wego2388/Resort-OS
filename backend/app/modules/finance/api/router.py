"""app/modules/finance/api/router.py"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import (
    DbDep, get_admin_user, get_cashier_user,
    get_current_active_user, get_db, get_manager_user, rate_limit_dep, require_permission,
)
from app.modules.finance import crud, services
from app.modules.finance.schemas import (
    AccountCreate, AccountRead,
    AccountingPeriodRead, AssetDepreciationEntryRead, BalanceSheetReport,
    BankAccountCreate, BankAccountRead, BankAccountUpdate, BankReconciliationSummary,
    BankStatementImportRequest, BankStatementLineRead, BankStatementMatchRequest,
    CashierShiftClose, CashierShiftOpen,
    CashierShiftRead, CheckCreate, CheckMoveStatus, CheckRead, ClosePeriodRequest,
    ConditionalDiscountCreate, ConditionalDiscountRead, ConditionalDiscountUpdate,
    CostCenterCreate, CostCenterRead, CostCenterReport,
    DepreciationRunRequest, DepreciationRunResult,
    DiscountCalculateRequest, ETAInvoiceRead, ETAInvoiceSubmitRequest,
    ExchangeRateCreate, ExchangeRateRead,
    FolioChargeCreate, FolioChargeRead,
    FolioCreate, FolioRead, IncomeStatementReport, JournalEntryCreate, JournalEntryRead,
    PaymentCreate, PaymentRead,
    RevenueAuditLogRead,
    ShiftEndReport, TrialBalanceReport, VoidPaymentRequest,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["finance"])


# ── Folios ────────────────────────────────────────────────────────────

@router.get("/finance/folios", response_model=PaginatedResponse)
def list_folios(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    status: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date]   = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_folios(db, branch_id, status, date_from, date_to,
                                    skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[FolioRead.model_validate(f) for f in items])


@router.post("/finance/folios", response_model=FolioRead,
             status_code=status.HTTP_201_CREATED)
def create_folio(data: FolioCreate, db: DbDep, _=Depends(get_cashier_user)):
    return services.create_folio(db, data)


@router.get("/finance/folios/{folio_id}", response_model=FolioRead)
def get_folio(folio_id: int, db: DbDep, _=Depends(get_current_active_user)):
    folio = crud.get_folio(db, folio_id)
    if not folio:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الفوليو {folio_id} غير موجود")
    return FolioRead.model_validate(folio)


@router.post("/finance/folios/{folio_id}/charges",
             response_model=FolioChargeRead,
             status_code=status.HTTP_201_CREATED)
def post_charge(folio_id: int, data: FolioChargeCreate, db: DbDep, _=Depends(get_cashier_user)):
    try:
        return services.post_charge(db, folio_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/finance/folios/{folio_id}/settle",
             response_model=FolioRead)
def settle_folio(folio_id: int, db: DbDep, _=Depends(get_cashier_user)):
    try:
        return services.settle_folio(db, folio_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/finance/folios/{folio_id}/payments",
             response_model=PaymentRead,
             status_code=status.HTTP_201_CREATED)
def add_payment(folio_id: int, data: PaymentCreate, db: DbDep, user=Depends(get_cashier_user)):
    try:
        return services.add_payment(db, folio_id, data, cashier_id=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post("/finance/payments/{payment_id}/void", response_model=PaymentRead,
             dependencies=[Depends(require_permission("finance.void_payment", "execute", min_role_level=60))])
def void_payment(payment_id: int, data: VoidPaymentRequest, db: DbDep,
                 user=Depends(get_manager_user)):
    try:
        return services.void_payment(db, payment_id, voided_by=user.id, reason=data.reason)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/finance/folios/{folio_id}/statement/pdf")
def download_folio_statement_pdf(folio_id: int, db: DbDep, _=Depends(get_cashier_user)):
    try:
        pdf = services.generate_folio_statement_pdf(db, folio_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=statement-{folio_id}.pdf"},
    )


@router.get("/finance/folios/report/export")
def download_folios_report_excel(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    xlsx = services.generate_folios_report_excel(db, branch_id, date_from, date_to, status_filter)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=all-invoices.xlsx"},
    )


# ── Cashier Shift / Safe (POS Day) ──────────────────────────────────────

@router.post("/finance/shifts/open", response_model=CashierShiftRead,
             status_code=status.HTTP_201_CREATED)
def open_shift(data: CashierShiftOpen, db: DbDep, user=Depends(get_cashier_user)):
    try:
        return services.open_shift(db, user.id, user.id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/finance/shifts/handover-note")
def get_handover_note(db: DbDep, _=Depends(get_cashier_user), branch_id: int = Query(...)):
    """آخر ملاحظة تسليم من آخر وردية مقفولة في الفرع — يشوفها الكاشير قبل
    ما يفتح ورديته الجديدة."""
    return {"handover_note": services.get_latest_handover_note(db, branch_id)}


@router.get("/finance/shifts/current", response_model=CashierShiftRead)
def get_current_shift(db: DbDep, user=Depends(get_cashier_user), branch_id: int = Query(...)):
    shift = crud.get_open_shift(db, branch_id, user.id)
    if not shift:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "لا توجد وردية مفتوحة")
    return CashierShiftRead.model_validate(shift)


@router.get("/finance/shifts", response_model=PaginatedResponse)
def list_shifts(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    cashier_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    items, total = crud.list_shifts(db, branch_id, cashier_id, status_filter,
                                     (page - 1) * size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[CashierShiftRead.model_validate(s) for s in items])


@router.get("/finance/shifts/{shift_id}/report", response_model=ShiftEndReport)
def shift_end_report(shift_id: int, db: DbDep, _=Depends(get_cashier_user)):
    try:
        return services.build_shift_end_report(db, shift_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get("/finance/shifts/{shift_id}/report/pdf")
def download_shift_end_report_pdf(shift_id: int, db: DbDep, _=Depends(get_cashier_user)):
    try:
        pdf = services.generate_shift_end_report_pdf(db, shift_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=shift-end-{shift_id}.pdf"},
    )


@router.post("/finance/shifts/{shift_id}/close", response_model=CashierShiftRead)
def close_shift(shift_id: int, data: CashierShiftClose, db: DbDep, user=Depends(get_cashier_user)):
    try:
        return services.close_shift(db, shift_id, user.id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Discounts ─────────────────────────────────────────────────────────

@router.get("/finance/discounts", response_model=PaginatedResponse)
def list_discounts(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    active_only: bool = Query(True),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    items, total = crud.list_discounts(db, branch_id, active_only,
                                       skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[ConditionalDiscountRead.model_validate(d) for d in items])


@router.post("/finance/discounts", response_model=ConditionalDiscountRead,
             status_code=status.HTTP_201_CREATED)
def create_discount(data: ConditionalDiscountCreate, db: DbDep, _=Depends(get_admin_user)):
    try:
        return services.create_discount(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/finance/discounts/{discount_id}",
              response_model=ConditionalDiscountRead)
def update_discount(
    discount_id: int, data: ConditionalDiscountUpdate,
    db: DbDep, _=Depends(get_admin_user),
):
    discount = crud.get_discount(db, discount_id)
    if not discount:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الخصم غير موجود")
    obj = crud.update_discount(db, discount, data)
    db.commit()
    db.refresh(obj)
    return ConditionalDiscountRead.model_validate(obj)


@router.delete("/finance/discounts/{discount_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_discount(discount_id: int, db: DbDep, _=Depends(get_admin_user)):
    discount = crud.get_discount(db, discount_id)
    if not discount:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "الخصم غير موجود")
    crud.delete_discount(db, discount)
    db.commit()


@router.post("/finance/calculate-discount")
def calculate_discount_endpoint(
    data: DiscountCalculateRequest, db: DbDep, _=Depends(get_current_active_user)
):
    result = services.calculate_order_discount(
        db, data.branch_id, data.order_total,
        data.item_count, data.customer_group, data.order_date,
    )
    return {
        "applied":        result.applied,
        "rule_id":        result.rule_id,
        "discount_type":  result.discount_type,
        "discount_value": result.discount_value,
        "amount_saved":   result.amount_saved,
        "final_amount":   result.final_amount,
        "reason":         result.reason,
    }


# ── Accounts (Chart of Accounts) ─────────────────────────────────────

@router.get("/finance/accounts", response_model=PaginatedResponse)
def list_accounts(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    active_only: bool = Query(True),
    as_of: Optional[date] = Query(None, description="تاريخ حساب الرصيد — افتراضيًا اليوم"),
    page: int = Query(1, ge=1),
    size: int = Query(200, ge=1, le=500),
):
    items, total = crud.list_accounts(db, branch_id, active_only,
                                      skip=(page - 1) * size, limit=size)
    # رصيد كل حساب من دفتر اليومية حتى as_of — نفس منطق trial balance
    # (مدين صافي للأصول/المصروفات، دائن صافي للخصوم/حقوق الملكية/الإيرادات).
    # كان الحقل ده مفقود بالكامل من الـ response (AccountRead ملوش balance
    # خالص)، والفرونت إند (FinanceView.vue) كان بيقرأ acc.balance المش موجود
    # أصلاً — تاب "الحسابات" كان بيطيح فعليًا (undefined.toLocaleString()).
    sums = crud.sum_journal_lines_by_account(db, branch_id, None, as_of or date.today())
    credit_normal_types = {"liability", "equity", "revenue"}
    for acc in items:
        debit_sum, credit_sum = sums.get(acc.id, (Decimal("0"), Decimal("0")))
        acc.balance = (
            (credit_sum - debit_sum) if acc.account_type in credit_normal_types
            else (debit_sum - credit_sum)
        )
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[AccountRead.model_validate(a) for a in items])


@router.post("/finance/accounts", response_model=AccountRead,
             status_code=status.HTTP_201_CREATED)
def create_account(data: AccountCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        account = crud.create_account(db, data)
        db.commit()
        db.refresh(account)
        return AccountRead.model_validate(account)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Journal Entries ───────────────────────────────────────────────────

@router.post("/finance/journal-entries", response_model=JournalEntryRead,
             status_code=status.HTTP_201_CREATED)
def post_journal_entry(
    data: JournalEntryCreate,
    db: DbDep,
    user=Depends(get_manager_user),
):
    try:
        entry = services.post_journal_entry(db, data, user_id=user.id)
        return JournalEntryRead.model_validate(entry)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/finance/journal-entries", response_model=PaginatedResponse)
def list_journal_entries(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    source: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    items, total = crud.list_journal_entries(
        db, branch_id, date_from, date_to, source,
        skip=(page - 1) * size, limit=size,
    )
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[JournalEntryRead.model_validate(e) for e in items])


@router.get("/finance/journal-entries/{entry_id}", response_model=JournalEntryRead)
def get_journal_entry(entry_id: int, db: DbDep, _=Depends(get_manager_user)):
    entry = crud.get_journal_entry(db, entry_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Journal entry {entry_id} not found")
    return JournalEntryRead.model_validate(entry)


# ── Revenue Audit Log ────────────────────────────────────────────────
# سجل تدقيق للتغييرات الفعلية في سعر/قيمة (زي إلغاء دفعة) — للعرض فقط،
# بيتسجّل تلقائيًا من الـ services (services.void_payment مثلًا)، مش عن طريق
# create endpoint مباشر للمستخدم.

@router.get("/finance/revenue-audit-logs", response_model=list[RevenueAuditLogRead])
def list_revenue_audit_logs(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    entity_type: Optional[str] = Query(None, pattern=r"^(booking|folio|invoice|payment)$"),
    entity_id: Optional[int] = Query(None),
):
    items = crud.list_revenue_audit_logs(db, branch_id, entity_type, entity_id)
    return [RevenueAuditLogRead.model_validate(l) for l in items]


# ── Accounting Periods ────────────────────────────────────────────────

@router.get("/finance/periods", response_model=PaginatedResponse)
def list_periods(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    items, total = crud.list_periods(db, branch_id, skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[AccountingPeriodRead.model_validate(p) for p in items])


@router.post("/finance/periods/{year}/{month}/close", response_model=AccountingPeriodRead,
             dependencies=[Depends(require_permission("finance.close_period", "execute", min_role_level=60))])
def close_period(
    year: int,
    month: int,
    data: ClosePeriodRequest,
    db: DbDep,
    user=Depends(get_current_active_user),
):
    try:
        period = services.close_accounting_period(
            db, data.branch_id, year, month, closed_by=user.id
        )
        return AccountingPeriodRead.model_validate(period)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Checks ────────────────────────────────────────────────────────────
# شيكات بنكية (أدوات مالية حقيقية مستلمة من عملاء/موردين) — كانت الثلاثة
# endpoints دي على get_current_active_user (أي موظف مسجّل دخول، حتى مستوى
# waiter/kitchen=20/30) بينما باقي كل endpoint مالي حساس في نفس الملف
# (folios/accounts/journal-entries/periods) على get_cashier_user (40+) أو
# get_manager_user (60+) — باج صلاحيات حقيقي: أي موظف كان يقدر يسجّل شيك
# جديد أو ينقله received→deposited→cleared/bounced (قرار محاسبي/بنكي).

@router.get("/finance/checks", response_model=list[CheckRead])
def list_checks_endpoint(
    branch_id: int = Query(...),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_cashier_user),
):
    checks = crud.list_checks(db, branch_id, status)
    return [CheckRead.model_validate(c) for c in checks]

@router.post("/finance/checks", response_model=CheckRead,
             status_code=status.HTTP_201_CREATED)
def create_check_endpoint(
    data: CheckCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_cashier_user),
):
    payload = data.model_dump()
    payload["created_by"] = current_user.id
    check = crud.create_check(db, payload)
    return CheckRead.model_validate(check)

@router.patch("/finance/checks/{check_id}/status", response_model=CheckRead)
def move_check_status_endpoint(
    check_id: int,
    body: CheckMoveStatus,
    db: Session = Depends(get_db),
    current_user=Depends(get_manager_user),
):
    check_obj = crud.get_check(db, check_id)
    if not check_obj:
        raise HTTPException(404, "Check not found")
    updated = crud.move_check_status(db, check_obj, body.to_status, current_user.id, body.notes)
    return CheckRead.model_validate(updated)


# ── Cost Centers ─────────────────────────────────────────────────────

@router.get("/finance/cost-centers", response_model=list[CostCenterRead])
def list_cost_centers(db: DbDep, _=Depends(get_manager_user),
                      branch_id: int = Query(...), active_only: bool = Query(True)):
    return [CostCenterRead.model_validate(c)
            for c in crud.list_cost_centers(db, branch_id, active_only)]


@router.post("/finance/cost-centers", response_model=CostCenterRead,
             status_code=status.HTTP_201_CREATED)
def create_cost_center(data: CostCenterCreate, db: DbDep, _=Depends(get_admin_user)):
    obj = crud.create_cost_center(db, data)
    db.commit(); db.refresh(obj)
    return CostCenterRead.model_validate(obj)


@router.get("/finance/cost-centers/report", response_model=CostCenterReport)
def cost_center_report(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    date_from: date = Query(...), date_to: date = Query(...),
):
    """إيراد كل مركز تكلفة (فندق/مطعم/كافيه/شاطئ/تايم شير) كسطر منفصل."""
    return services.get_cost_center_report(db, branch_id, date_from, date_to)


# ── Exchange Rates (Multi-Currency) ──────────────────────────────────

@router.get("/finance/exchange-rates", response_model=PaginatedResponse)
def list_exchange_rates(
    db: DbDep, _=Depends(get_current_active_user),
    from_currency: Optional[str] = Query(None),
    to_currency: Optional[str] = Query(None),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
):
    items, total = services.list_exchange_rates(db, from_currency, to_currency, (page - 1) * size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[ExchangeRateRead.model_validate(r) for r in items])


@router.post("/finance/exchange-rates", response_model=ExchangeRateRead,
             status_code=status.HTTP_201_CREATED)
def create_exchange_rate(data: ExchangeRateCreate, db: DbDep, user=Depends(get_manager_user)):
    try:
        obj = services.create_exchange_rate(db, data, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return ExchangeRateRead.model_validate(obj)


# ── Financial Reports ─────────────────────────────────────────────────

@router.get("/finance/reports/trial-balance", response_model=TrialBalanceReport)
def trial_balance_report(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    as_of: date = Query(...),
):
    """ميزان المراجعة — كل حساب برصيده حتى تاريخ as_of، إجمالي المدين
    لازم يساوي إجمالي الدائن (is_balanced)."""
    return services.get_trial_balance(db, branch_id, as_of)


@router.get("/finance/reports/income-statement", response_model=IncomeStatementReport)
def income_statement_report(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
):
    """قائمة الدخل — الإيرادات ناقص المصروفات خلال المدى، وصافي الربح."""
    return services.get_income_statement(db, branch_id, date_from, date_to)


@router.get("/finance/reports/balance-sheet", response_model=BalanceSheetReport)
def balance_sheet_report(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    as_of: date = Query(...),
):
    """الميزانية العمومية — الأصول = الخصوم + حقوق الملكية + الأرباح
    المحتجزة حتى تاريخ as_of (is_balanced)."""
    return services.get_balance_sheet(db, branch_id, as_of)


# ── ETA E-Invoice ────────────────────────────────────────────────────
# rate-limited 100/60s per user per 08-SECURITY.md's eta:{} limit — protects
# against retry storms against ETA's own (also rate-limited) submission API.

@router.post(
    "/finance/eta/invoices",
    response_model=ETAInvoiceRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_dep("eta", 100, 60))],
)
async def submit_eta_invoice(
    data: ETAInvoiceSubmitRequest,
    db: DbDep,
    _user=Depends(get_manager_user),
):
    try:
        invoice = await services.submit_eta_invoice(db, settings, data)
        return ETAInvoiceRead.model_validate(invoice)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get(
    "/finance/eta/invoices",
    response_model=PaginatedResponse,
)
def list_eta_invoices(
    db: DbDep, _user=Depends(get_manager_user),
    branch_id: int = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_eta_invoices(db, branch_id, status_filter, (page - 1) * size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[ETAInvoiceRead.model_validate(i) for i in items])


@router.get(
    "/finance/eta/invoices/{invoice_id}",
    response_model=ETAInvoiceRead,
)
def get_eta_invoice(invoice_id: int, db: DbDep, _user=Depends(get_manager_user)):
    invoice = crud.get_eta_invoice(db, invoice_id)
    if not invoice:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الفاتورة {invoice_id} غير موجودة")
    return ETAInvoiceRead.model_validate(invoice)


# ── Fixed-Asset Depreciation ─────────────────────────────────────────

@router.post("/finance/depreciation/run", response_model=DepreciationRunResult)
def run_depreciation(data: DepreciationRunRequest, db: DbDep, user=Depends(get_manager_user)):
    """يشغّل دورة إهلاك خطي شهرية لكل الأصول المؤهّلة في الفرع — آمن لإعادة
    التشغيل (أي أصل اتّرحّل له نفس الشهر قبل كده بيتخطّى تلقائيًا)."""
    try:
        return services.run_depreciation(db, data.branch_id, data.year, data.month, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/finance/depreciation/entries", response_model=PaginatedResponse)
def list_depreciation_entries(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    asset_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = services.list_depreciation_entries(db, branch_id, asset_id, page, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[AssetDepreciationEntryRead.model_validate(e) for e in items])


# ── Bank Accounts ──────────────────────────────────────────────────────

@router.post("/finance/bank-accounts", response_model=BankAccountRead,
             status_code=status.HTTP_201_CREATED)
def create_bank_account(data: BankAccountCreate, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.create_bank_account(db, data)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/finance/bank-accounts", response_model=list[BankAccountRead])
def list_bank_accounts(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    active_only: bool = Query(True),
):
    return [BankAccountRead.model_validate(a) for a in crud.list_bank_accounts(db, branch_id, active_only)]


@router.patch("/finance/bank-accounts/{bank_account_id}", response_model=BankAccountRead)
def update_bank_account(bank_account_id: int, data: BankAccountUpdate, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.update_bank_account(db, bank_account_id, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


# ── Bank Statement Lines / Reconciliation ───────────────────────────────

@router.post(
    "/finance/bank-accounts/{bank_account_id}/statement-lines",
    response_model=list[BankStatementLineRead],
    status_code=status.HTTP_201_CREATED,
)
def import_bank_statement_lines(
    bank_account_id: int, data: BankStatementImportRequest, db: DbDep, user=Depends(get_manager_user),
):
    """استيراد سطور كشف حساب بنكي (يدوي/من ملف اتحوّل JSON على الفرونت
    إند) — كل سطر بيدخل الحالة unmatched لحد ما يتطابق (أوتوماتيك أو يدوي)."""
    try:
        return [
            BankStatementLineRead.model_validate(l)
            for l in services.import_bank_statement_lines(db, bank_account_id, user.id, data)
        ]
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get(
    "/finance/bank-accounts/{bank_account_id}/statement-lines",
    response_model=PaginatedResponse,
)
def list_bank_statement_lines(
    bank_account_id: int, db: DbDep, _=Depends(get_manager_user),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_bank_statement_lines(
        db, bank_account_id, status_filter, skip=(page - 1) * size, limit=size,
    )
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[BankStatementLineRead.model_validate(l) for l in items])


@router.post("/finance/bank-accounts/{bank_account_id}/statement-lines/auto-match")
def auto_match_bank_statement_lines(bank_account_id: int, db: DbDep, user=Depends(get_manager_user)):
    """مطابقة أوتوماتيكية محافظة — بس لو مرشح دفعة واحد بالظبط لكل سطر،
    غير كده بيسيبه للمطابقة اليدوية. يرجّع عدد السطور اللي اتطابقت."""
    try:
        matched = services.auto_match_bank_statement_lines(db, bank_account_id, user.id)
        return {"matched_count": matched}
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post(
    "/finance/bank-accounts/{bank_account_id}/statement-lines/{line_id}/match",
    response_model=BankStatementLineRead,
)
def match_bank_statement_line(
    bank_account_id: int, line_id: int, data: BankStatementMatchRequest, db: DbDep,
    user=Depends(get_manager_user),
):
    try:
        return services.match_bank_statement_line(db, bank_account_id, line_id, data.payment_id, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.post(
    "/finance/bank-accounts/{bank_account_id}/statement-lines/{line_id}/unmatch",
    response_model=BankStatementLineRead,
)
def unmatch_bank_statement_line(bank_account_id: int, line_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        return services.unmatch_bank_statement_line(db, bank_account_id, line_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get(
    "/finance/bank-accounts/{bank_account_id}/reconciliation-summary",
    response_model=BankReconciliationSummary,
)
def get_bank_reconciliation_summary(
    bank_account_id: int, db: DbDep, _=Depends(get_manager_user),
    as_of: date = Query(...),
):
    try:
        return services.get_bank_reconciliation_summary(db, bank_account_id, as_of)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
