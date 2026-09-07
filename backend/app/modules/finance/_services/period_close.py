"""
app/modules/finance/_services/period_close.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.finance import crud
from app.modules.finance.models import AccountingPeriod, AccountingYearClose
from app.modules.finance.schemas import (
    JournalEntryCreate,
    JournalLineCreate,
)
from app.modules.finance._services._exceptions import (
    FinancialConfigurationError,
)


def close_accounting_period(
    db: Session,
    branch_id: int,
    year: int,
    month: int,
    closed_by: int,
) -> AccountingPeriod:
    """يقفل فترة محاسبية — إجراء تدقيقي (audited) لازم يحصل مرة واحدة بس، زي
    قفل الوردية بالظبط. لو الفترة مقفولة بالفعل بنرفض (بدل ما نسمح لأي حد
    يعيد قفلها ويغيّر closed_by/closed_at بصمت فوق سجل التدقيق الأصلي)."""
    existing = crud.get_period_status(db, branch_id, year, month)
    if existing and existing.status in ("closed", "locked"):
        raise ValueError(f"الفترة المحاسبية {year}-{month:02d} مقفولة بالفعل")

    period = crud.close_period(db, branch_id, year, month, closed_by)

    from app.modules.core.crud import create_audit_log  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
    create_audit_log(db, AuditLogCreate(
        user_id=closed_by, branch_id=branch_id, action="close_period",
        entity_type="accounting_period", entity_id=period.id,
        new_data=f'{{"year": {year}, "month": {month}, "status": "{period.status}"}}',
    ))

    db.commit()
    db.refresh(period)
    return period


def close_accounting_year(db: Session, branch_id: int, year: int, closed_by: int) -> AccountingYearClose:
    """إقفال سنة محاسبية (2026-08-19، طلب Mohamed صراحةً) — يترحّل قيد
    إقفال حقيقي يصفّر كل حسابات الإيرادات/المصروفات في 3200 (أرباح
    مرحّلة)، بعد التأكد إن الاتناشر شهر كلهم مقفولين الأول. عملية لمرة
    واحدة بس لكل (فرع، سنة) — مفيش "إعادة فتح سنة" في النطاق الحالي.

    بيستخدم crud.create_journal_entry مباشرة (مش post_journal_entry) —
    نفس سبب settle_custody بالظبط: القيد نفسه لازم يترحّل بتاريخ آخر يوم
    في السنة (31 ديسمبر)، وهو تاريخ جوه شهر لازم يكون *مقفول بالفعل*
    كشرط مسبق — لو استخدمنا post_journal_entry (بينادي validate_period_
    open داخليًا) كان هيرفض القيد على أساس إن الفترة مقفولة، بينما إقفال
    الفترة دي هو بالظبط سبب وجود القيد ده."""
    if crud.get_year_close(db, branch_id, year):
        raise ValueError(f"السنة المحاسبية {year} مقفولة بالفعل")

    closed_months = crud.count_closed_months(db, branch_id, year)
    if closed_months < 12:
        raise ValueError(
            f"لازم تقفل كل شهور سنة {year} الاتناشر الأول قبل إقفال السنة "
            f"(مقفول حاليًا {closed_months}/12)"
        )

    retained_earnings_account = crud.get_account_by_code(db, branch_id, "3200")
    if not retained_earnings_account:
        raise FinancialConfigurationError("حساب الأرباح المحتجزة (3200) غير معرَّف لهذا الفرع")

    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    accounts, _total = crud.list_accounts(db, branch_id, active_only=False, limit=1000)
    sums = crud.sum_journal_lines_by_account(db, branch_id, year_start, year_end)

    lines: list[JournalLineCreate] = []
    total_revenue = Decimal("0")
    total_expense = Decimal("0")
    for acc in accounts:
        debit_sum, credit_sum = sums.get(acc.id, (Decimal("0"), Decimal("0")))
        if acc.account_type == "revenue":
            balance = credit_sum - debit_sum
            if balance != 0:
                lines.append(JournalLineCreate(
                    account_id=acc.id, debit=balance, credit=Decimal("0"),
                    description=f"إقفال سنة {year}",
                ))
                total_revenue += balance
        elif acc.account_type == "expense":
            balance = debit_sum - credit_sum
            if balance != 0:
                lines.append(JournalLineCreate(
                    account_id=acc.id, debit=Decimal("0"), credit=balance,
                    description=f"إقفال سنة {year}",
                ))
                total_expense += balance

    if not lines:
        raise ValueError(f"لا يوجد نشاط مالي (إيرادات/مصروفات) لسنة {year} — لا يوجد ما يُقفل")

    net_income = total_revenue - total_expense
    if net_income > 0:
        lines.append(JournalLineCreate(
            account_id=retained_earnings_account.id, debit=Decimal("0"), credit=net_income,
            description=f"صافي ربح سنة {year}",
        ))
    elif net_income < 0:
        lines.append(JournalLineCreate(
            account_id=retained_earnings_account.id, debit=abs(net_income), credit=Decimal("0"),
            description=f"صافي خسارة سنة {year}",
        ))

    total_debit = sum((ln.debit for ln in lines), Decimal("0"))
    total_credit = sum((ln.credit for ln in lines), Decimal("0"))
    if abs(total_debit - total_credit) > Decimal("0.01"):
        raise ValueError(f"قيد الإقفال غير متوازن: مدين={total_debit}, دائن={total_credit}")

    entry_data = JournalEntryCreate(
        branch_id=branch_id, entry_date=year_end,
        reference=f"YEAR-CLOSE-{year}", description=f"قيد إقفال سنة {year}",
        source="year_close", source_id=None, lines=lines,
    )

    try:
        entry = crud.create_journal_entry(db, entry_data, closed_by)
        year_close = crud.create_year_close(db, branch_id, year, entry.id, net_income, closed_by)
        db.commit()
        db.refresh(year_close)
        return year_close
    except Exception:
        db.rollback()
        raise
