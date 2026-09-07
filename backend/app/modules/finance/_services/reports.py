"""
app/modules/finance/_services/reports.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional, TYPE_CHECKING
from sqlalchemy.orm import Session
from app.modules.finance import crud

if TYPE_CHECKING:
    from app.modules.finance.models import Account  # noqa: F401
from app.modules.finance.schemas import (
    BalanceSheetLine,
    BalanceSheetReport,
    AccountLedgerLine,
    AccountLedgerReport,
    AgingBucket,
    AgingReport,
    PayableAgingLine,
    ReceivableAgingLine,
    IncomeStatementLine,
    IncomeStatementReport,
    TrialBalanceLine,
    TrialBalanceReport,
)


def get_account_ledger(
    db: Session, branch_id: int, account_id: int, date_from: date, date_to: date,
) -> AccountLedgerReport:
    """كشف حساب (2026-08-19، طلب Mohamed) — كل حركات حساب واحد خلال مدى
    تاريخي، برصيد متحرّك. بدون pagination عمدًا (راجع crud.list_account_
    ledger_lines) — لازم الرصيد المتحرّك يتحسب على التسلسل الكامل، والمدى
    التاريخي بطبيعته بيحصر حجم البيانات (شهر/فترة، مش كل تاريخ الحساب)."""
    account = crud.get_account(db, account_id)
    if not account or account.branch_id != branch_id:
        raise ValueError(f"الحساب {account_id} غير موجود في هذا الفرع")
    if date_from > date_to:
        raise ValueError("تاريخ البداية لازم يكون قبل تاريخ النهاية")

    debit_normal = account.account_type in ("asset", "expense")

    opening_debit, opening_credit = crud.sum_account_before_date(db, account_id, date_from)
    opening_balance = (opening_debit - opening_credit) if debit_normal else (opening_credit - opening_debit)

    rows = crud.list_account_ledger_lines(db, account_id, date_from, date_to)

    lines: list[AccountLedgerLine] = []
    running = opening_balance
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for line, entry in rows:
        delta = (line.debit - line.credit) if debit_normal else (line.credit - line.debit)
        running += delta
        total_debit += line.debit
        total_credit += line.credit
        lines.append(AccountLedgerLine(
            entry_id=entry.id, entry_date=entry.entry_date,
            reference=entry.reference, description=line.description or entry.description,
            debit=line.debit, credit=line.credit, running_balance=running,
        ))

    return AccountLedgerReport(
        account_id=account.id, account_code=account.code, account_name=account.name,
        account_type=account.account_type, date_from=date_from, date_to=date_to,
        opening_balance=opening_balance, closing_balance=running,
        total_debit=total_debit, total_credit=total_credit, lines=lines,
    )


_AGING_BUCKETS = (
    ("0-30", 0, 30),
    ("31-60", 31, 60),
    ("61-90", 61, 90),
    ("90+", 91, None),
)


def _aging_bucket_label(days: int) -> str:
    for label, lo, hi in _AGING_BUCKETS:
        if days >= lo and (hi is None or days <= hi):
            return label
    return "90+"


def get_aging_report(db: Session, branch_id: int, as_of: Optional[date] = None) -> AgingReport:
    """تقرير أعمار الديون (2026-08-19، طلب Mohamed) — مين مديون لنا (فوليوهات
    مفتوحة برصيد مستحق، عمرها من check_in) ومين إحنا مديونين له (أوامر شراء
    + مصروفات آجلة لسه من غير سداد كامل، عمرها من تاريخ الأمر/المصروف).
    مفيش منطق مالي جديد هنا — بس تجميع وترتيب بيانات موجودة أصلاً."""
    if as_of is None:
        as_of = date.today()

    receivables: list[ReceivableAgingLine] = []
    receivables_total = Decimal("0")
    for folio in crud.list_open_folios_for_aging(db, branch_id):
        paid = sum((p.amount for p in folio.payments if p.voided_at is None), Decimal("0"))
        balance_due = folio.total - paid
        if balance_due <= Decimal("0.01"):
            continue
        days = (as_of - folio.check_in.date()).days
        receivables_total += balance_due
        receivables.append(ReceivableAgingLine(
            folio_id=folio.id, guest_name=folio.guest_name, check_in=folio.check_in.date(),
            days_outstanding=days, balance_due=balance_due, bucket=_aging_bucket_label(days),
        ))

    payables: list[PayableAgingLine] = []
    payables_total = Decimal("0")

    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415
    for po in inventory_crud.list_unpaid_purchase_orders_for_aging(db, branch_id):
        remaining = po.total_amount - po.amount_paid
        if remaining <= Decimal("0.01"):
            continue
        days = (as_of - po.ordered_at).days
        payables_total += remaining
        payables.append(PayableAgingLine(
            source_type="purchase_order", source_id=po.id, reference=po.order_number,
            counterparty=po.supplier.name if po.supplier else (po.supplier_name or "—"),
            due_date=po.ordered_at, days_outstanding=days, remaining=remaining,
            bucket=_aging_bucket_label(days),
        ))

    for exp in crud.list_unpaid_expenses_for_aging(db, branch_id):
        remaining = exp.amount - exp.amount_paid
        if remaining <= Decimal("0.01"):
            continue
        days = (as_of - exp.expense_date).days
        payables_total += remaining
        payables.append(PayableAgingLine(
            source_type="expense", source_id=exp.id, reference=exp.reference or f"EXP-{exp.id}",
            counterparty=exp.description, due_date=exp.expense_date,
            days_outstanding=days, remaining=remaining, bucket=_aging_bucket_label(days),
        ))

    def _bucketize(lines, amount_attr) -> list[AgingBucket]:
        result = []
        for label, _lo, _hi in _AGING_BUCKETS:
            matching = [l for l in lines if l.bucket == label]
            result.append(AgingBucket(
                label=label, count=len(matching),
                amount=sum((getattr(l, amount_attr) for l in matching), Decimal("0")),
            ))
        return result

    return AgingReport(
        branch_id=branch_id, as_of=as_of,
        receivables=receivables, receivables_total=receivables_total,
        receivables_buckets=_bucketize(receivables, "balance_due"),
        payables=payables, payables_total=payables_total,
        payables_buckets=_bucketize(payables, "remaining"),
    )


def get_trial_balance(
    db: Session, branch_id: int, as_of: date, group_by_parent: bool = False,
) -> TrialBalanceReport:
    """ميزان المراجعة — كل حساب له نشاط حتى تاريخ as_of، برصيده الختامي في
    عمود المدين أو الدائن حسب طبيعته. إجمالي المدين لازم يساوي إجمالي الدائن.

    group_by_parent=True (Batch 3): بدل سطر لكل حساب فردي، كل سطر بيمثّل
    حساب أب (Account.parent_id — راجع seed.py's PARENT_HEADERS، 1-2 مستوى
    بس) برصيده المجمّع من كل حساباته الفرعية. حساب من غير أب (نادر، أي
    حساب مستقبلي يتضاف من غير ما يتحدد له parent_id) بيتعامل معاه كأب
    لنفسه — عشان ميختفيش من التقرير المجمّع بصمت."""
    accounts, _ = crud.list_accounts(db, branch_id, active_only=False, limit=1000)
    sums = crud.sum_journal_lines_by_account(db, branch_id, None, as_of)

    if not group_by_parent:
        lines: list[TrialBalanceLine] = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")
        for acc in accounts:
            debit_sum, credit_sum = sums.get(acc.id, (Decimal("0"), Decimal("0")))
            if debit_sum == 0 and credit_sum == 0:
                continue
            net = debit_sum - credit_sum
            if net >= 0:
                debit_display, credit_display = net, Decimal("0")
            else:
                debit_display, credit_display = Decimal("0"), -net
            total_debit += debit_display
            total_credit += credit_display
            lines.append(TrialBalanceLine(
                account_code=acc.code, account_name=acc.name, account_type=acc.account_type,
                debit=debit_display, credit=credit_display,
            ))

        return TrialBalanceReport(
            branch_id=branch_id, as_of=as_of, lines=lines,
            total_debit=total_debit, total_credit=total_credit,
            is_balanced=abs(total_debit - total_credit) <= Decimal("0.01"),
        )

    # ── وضع التجميع بالحساب الأب ──────────────────────────────────────
    accounts_by_id = {a.id: a for a in accounts}
    parent_net: dict[int, Decimal] = {}
    parent_account: dict[int, "Account"] = {}
    for acc in accounts:
        debit_sum, credit_sum = sums.get(acc.id, (Decimal("0"), Decimal("0")))
        if debit_sum == 0 and credit_sum == 0:
            continue
        parent = accounts_by_id.get(acc.parent_id) if acc.parent_id else None
        parent_id = parent.id if parent else acc.id  # حساب من غير أب = أب لنفسه
        parent_account.setdefault(parent_id, parent or acc)
        parent_net[parent_id] = parent_net.get(parent_id, Decimal("0")) + (debit_sum - credit_sum)

    lines = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for parent_id, net in parent_net.items():
        header = parent_account[parent_id]
        if net >= 0:
            debit_display, credit_display = net, Decimal("0")
        else:
            debit_display, credit_display = Decimal("0"), -net
        total_debit += debit_display
        total_credit += credit_display
        lines.append(TrialBalanceLine(
            account_code=header.code, account_name=header.name, account_type=header.account_type,
            debit=debit_display, credit=credit_display,
        ))
    lines.sort(key=lambda ln: ln.account_code)

    return TrialBalanceReport(
        branch_id=branch_id, as_of=as_of, lines=lines,
        total_debit=total_debit, total_credit=total_credit,
        is_balanced=abs(total_debit - total_credit) <= Decimal("0.01"),
        grouped_by_parent=True,
    )


def get_income_statement(
    db: Session, branch_id: int, date_from: date, date_to: date,
) -> IncomeStatementReport:
    """قائمة الدخل — الإيرادات (حسابات revenue) ناقص المصروفات (حسابات
    expense) خلال المدى المطلوب، وصافي الربح/الخسارة."""
    accounts, _ = crud.list_accounts(db, branch_id, active_only=False, limit=1000)
    sums = crud.sum_journal_lines_by_account(db, branch_id, date_from, date_to)

    revenue_lines: list[IncomeStatementLine] = []
    expense_lines: list[IncomeStatementLine] = []
    total_revenue = Decimal("0")
    total_expense = Decimal("0")
    for acc in accounts:
        debit_sum, credit_sum = sums.get(acc.id, (Decimal("0"), Decimal("0")))
        if debit_sum == 0 and credit_sum == 0:
            continue
        if acc.account_type == "revenue":
            amount = credit_sum - debit_sum
            total_revenue += amount
            revenue_lines.append(IncomeStatementLine(account_code=acc.code, account_name=acc.name, amount=amount))
        elif acc.account_type == "expense":
            amount = debit_sum - credit_sum
            total_expense += amount
            expense_lines.append(IncomeStatementLine(account_code=acc.code, account_name=acc.name, amount=amount))

    return IncomeStatementReport(
        branch_id=branch_id, date_from=date_from, date_to=date_to,
        revenue_lines=revenue_lines, expense_lines=expense_lines,
        total_revenue=total_revenue, total_expense=total_expense,
        net_income=total_revenue - total_expense,
    )


def get_balance_sheet(db: Session, branch_id: int, as_of: date) -> BalanceSheetReport:
    """الميزانية العمومية — الأصول = الخصوم + حقوق الملكية + الأرباح
    المحتجزة (صافي الإيرادات-المصروفات التراكمي حتى as_of، لعدم وجود قيد
    إقفال فعلي في هذا المشروع)."""
    accounts, _ = crud.list_accounts(db, branch_id, active_only=False, limit=1000)
    sums = crud.sum_journal_lines_by_account(db, branch_id, None, as_of)

    asset_lines: list[BalanceSheetLine] = []
    liability_lines: list[BalanceSheetLine] = []
    equity_lines: list[BalanceSheetLine] = []
    total_assets = Decimal("0")
    total_liabilities = Decimal("0")
    total_equity = Decimal("0")
    total_revenue = Decimal("0")
    total_expense = Decimal("0")

    for acc in accounts:
        debit_sum, credit_sum = sums.get(acc.id, (Decimal("0"), Decimal("0")))
        if debit_sum == 0 and credit_sum == 0:
            continue
        if acc.account_type == "asset":
            amount = debit_sum - credit_sum
            total_assets += amount
            asset_lines.append(BalanceSheetLine(account_code=acc.code, account_name=acc.name, amount=amount))
        elif acc.account_type == "liability":
            amount = credit_sum - debit_sum
            total_liabilities += amount
            liability_lines.append(BalanceSheetLine(account_code=acc.code, account_name=acc.name, amount=amount))
        elif acc.account_type == "equity":
            amount = credit_sum - debit_sum
            total_equity += amount
            equity_lines.append(BalanceSheetLine(account_code=acc.code, account_name=acc.name, amount=amount))
        elif acc.account_type == "revenue":
            total_revenue += credit_sum - debit_sum
        elif acc.account_type == "expense":
            total_expense += debit_sum - credit_sum

    retained_earnings = total_revenue - total_expense
    total_liabilities_and_equity = total_liabilities + total_equity + retained_earnings

    return BalanceSheetReport(
        branch_id=branch_id, as_of=as_of,
        asset_lines=asset_lines, liability_lines=liability_lines, equity_lines=equity_lines,
        retained_earnings=retained_earnings,
        total_assets=total_assets, total_liabilities=total_liabilities, total_equity=total_equity,
        total_liabilities_and_equity=total_liabilities_and_equity,
        is_balanced=abs(total_assets - total_liabilities_and_equity) <= Decimal("0.01"),
    )


# ── تصدير التقارير المالية الرئيسية PDF/Excel (2026-08-19، طلب Mohamed) ──
# ميزان المراجعة/قائمة الدخل/الميزانية العمومية كانت شاشة/JSON بس، مفيش
# ملف قابل للتنزيل يتسلّم لمحاسب خارجي أو بنك. نفس نمط generate_folios_
# report_excel فوق بالظبط — بيعيد استخدام get_trial_balance/get_income_
# statement/get_balance_sheet المحسوبة أصلاً، صفر منطق مالي جديد هنا.

def generate_trial_balance_pdf(
    db: Session, branch_id: int, as_of: date, group_by_parent: bool = False,
) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_trial_balance(db, branch_id, as_of, group_by_parent)
    headers = ["الكود", "الحساب", "النوع", "مدين", "دائن"]
    rows = [
        [l.account_code, l.account_name, l.account_type,
         f"{l.debit:,.2f}" if l.debit else "—", f"{l.credit:,.2f}" if l.credit else "—"]
        for l in report.lines
    ]
    summary = [
        ("إجمالي المدين", f"{report.total_debit:,.2f} EGP"),
        ("إجمالي الدائن", f"{report.total_credit:,.2f} EGP"),
        ("متوازن؟", "نعم ✓" if report.is_balanced else "لا ✗"),
    ]
    return builder.table_pdf(
        title="ميزان المراجعة", subtitle=f"حتى تاريخ {as_of:%Y-%m-%d}",
        headers=headers, rows=rows, summary=summary,
    )


def generate_trial_balance_excel(
    db: Session, branch_id: int, as_of: date, group_by_parent: bool = False,
) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_trial_balance(db, branch_id, as_of, group_by_parent)
    rows = [[l.account_code, l.account_name, l.account_type, float(l.debit), float(l.credit)] for l in report.lines]
    return builder.excel(
        sheets=[{
            "name": "ميزان المراجعة",
            "headers": ["الكود", "الحساب", "النوع", "مدين", "دائن"],
            "rows": rows,
            "col_types": ["text", "text", "text", "currency", "currency"],
            "summary": {
                "إجمالي المدين": float(report.total_debit),
                "إجمالي الدائن": float(report.total_credit),
            },
        }],
        title=f"ميزان المراجعة حتى {as_of:%Y-%m-%d}",
    )


def generate_income_statement_pdf(db: Session, branch_id: int, date_from: date, date_to: date) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_income_statement(db, branch_id, date_from, date_to)
    headers = ["الكود", "الحساب", "المبلغ"]
    rows = [["", "— الإيرادات —", ""]]
    rows += [[l.account_code, l.account_name, f"{l.amount:,.2f}"] for l in report.revenue_lines]
    rows += [["", "— المصروفات —", ""]]
    rows += [[l.account_code, l.account_name, f"{l.amount:,.2f}"] for l in report.expense_lines]
    summary = [
        ("إجمالي الإيرادات", f"{report.total_revenue:,.2f} EGP"),
        ("إجمالي المصروفات", f"{report.total_expense:,.2f} EGP"),
        ("صافي الربح/الخسارة", f"{report.net_income:,.2f} EGP"),
    ]
    return builder.table_pdf(
        title="قائمة الدخل", subtitle=f"من {date_from:%Y-%m-%d} إلى {date_to:%Y-%m-%d}",
        headers=headers, rows=rows, summary=summary,
    )


def generate_income_statement_excel(db: Session, branch_id: int, date_from: date, date_to: date) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_income_statement(db, branch_id, date_from, date_to)
    rev_rows = [[l.account_code, l.account_name, float(l.amount)] for l in report.revenue_lines]
    exp_rows = [[l.account_code, l.account_name, float(l.amount)] for l in report.expense_lines]
    return builder.excel(
        sheets=[
            {
                "name": "الإيرادات",
                "headers": ["الكود", "الحساب", "المبلغ"],
                "rows": rev_rows, "col_types": ["text", "text", "currency"],
                "summary": {"إجمالي الإيرادات": float(report.total_revenue)},
            },
            {
                "name": "المصروفات",
                "headers": ["الكود", "الحساب", "المبلغ"],
                "rows": exp_rows, "col_types": ["text", "text", "currency"],
                "summary": {
                    "إجمالي المصروفات": float(report.total_expense),
                    "صافي الربح/الخسارة": float(report.net_income),
                },
            },
        ],
        title=f"قائمة الدخل {date_from:%Y-%m-%d} — {date_to:%Y-%m-%d}",
    )


def generate_balance_sheet_pdf(db: Session, branch_id: int, as_of: date) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_balance_sheet(db, branch_id, as_of)
    headers = ["الكود", "الحساب", "المبلغ"]
    rows = [["", "— الأصول —", ""]]
    rows += [[l.account_code, l.account_name, f"{l.amount:,.2f}"] for l in report.asset_lines]
    rows += [["", "— الخصوم —", ""]]
    rows += [[l.account_code, l.account_name, f"{l.amount:,.2f}"] for l in report.liability_lines]
    rows += [["", "— حقوق الملكية —", ""]]
    rows += [[l.account_code, l.account_name, f"{l.amount:,.2f}"] for l in report.equity_lines]
    summary = [
        ("إجمالي الأصول", f"{report.total_assets:,.2f} EGP"),
        ("إجمالي الخصوم", f"{report.total_liabilities:,.2f} EGP"),
        ("إجمالي حقوق الملكية", f"{report.total_equity:,.2f} EGP"),
        ("الأرباح المحتجزة", f"{report.retained_earnings:,.2f} EGP"),
        ("متوازنة؟", "نعم ✓" if report.is_balanced else "لا ✗"),
    ]
    return builder.table_pdf(
        title="الميزانية العمومية", subtitle=f"حتى تاريخ {as_of:%Y-%m-%d}",
        headers=headers, rows=rows, summary=summary,
    )


def generate_balance_sheet_excel(db: Session, branch_id: int, as_of: date) -> bytes:
    from app.resort_os.report_builder import builder  # noqa: PLC0415

    report = get_balance_sheet(db, branch_id, as_of)
    asset_rows = [[l.account_code, l.account_name, float(l.amount)] for l in report.asset_lines]
    liability_rows = [[l.account_code, l.account_name, float(l.amount)] for l in report.liability_lines]
    equity_rows = [[l.account_code, l.account_name, float(l.amount)] for l in report.equity_lines]
    return builder.excel(
        sheets=[
            {
                "name": "الأصول", "headers": ["الكود", "الحساب", "المبلغ"],
                "rows": asset_rows, "col_types": ["text", "text", "currency"],
                "summary": {"إجمالي الأصول": float(report.total_assets)},
            },
            {
                "name": "الخصوم", "headers": ["الكود", "الحساب", "المبلغ"],
                "rows": liability_rows, "col_types": ["text", "text", "currency"],
                "summary": {"إجمالي الخصوم": float(report.total_liabilities)},
            },
            {
                "name": "حقوق الملكية", "headers": ["الكود", "الحساب", "المبلغ"],
                "rows": equity_rows, "col_types": ["text", "text", "currency"],
                "summary": {
                    "إجمالي حقوق الملكية": float(report.total_equity),
                    "الأرباح المحتجزة": float(report.retained_earnings),
                },
            },
        ],
        title=f"الميزانية العمومية حتى {as_of:%Y-%m-%d}",
    )


# ── Fixed-Asset Depreciation (straight-line MVP) ────────────────────────
