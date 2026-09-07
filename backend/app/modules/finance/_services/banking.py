"""
app/modules/finance/_services/banking.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.finance import crud
from app.modules.finance.models import BankAccount, BankStatementLine
from app.modules.finance.schemas import (
    BankAccountCreate,
    BankAccountUpdate,
    BankReconciliationSummary,
    BankStatementImportRequest,
)


def get_bank_account_or_404(db: Session, bank_account_id: int) -> BankAccount:
    account = crud.get_bank_account(db, bank_account_id)
    if not account:
        raise ValueError(f"الحساب البنكي {bank_account_id} غير موجود")
    return account


def create_bank_account(db: Session, data: BankAccountCreate) -> BankAccount:
    account = crud.create_bank_account(db, data)
    db.commit()
    db.refresh(account)
    return account


def update_bank_account(db: Session, bank_account_id: int, data: BankAccountUpdate) -> BankAccount:
    account = get_bank_account_or_404(db, bank_account_id)
    account = crud.update_bank_account(db, account, data)
    db.commit()
    db.refresh(account)
    return account


def import_bank_statement_lines(
    db: Session, bank_account_id: int, uploaded_by: int, data: BankStatementImportRequest,
) -> list[BankStatementLine]:
    account = get_bank_account_or_404(db, bank_account_id)
    lines = crud.create_bank_statement_lines(db, account.id, account.branch_id, uploaded_by, data.lines)
    db.commit()
    for line in lines:
        db.refresh(line)
    return lines


def auto_match_bank_statement_lines(db: Session, bank_account_id: int, matched_by: int) -> int:
    """محافظ (مش تخميني): يطابق تلقائيًا بس لو فيه مرشح دفعة واحد بالظبط
    (نفس المبلغ ± قرش، وتاريخ قريب، غير مرتبط بسطر تاني) — أي غموض (صفر أو
    أكتر من مرشح) بيتسيب للمطابقة اليدوية بدل ما يخمّن ويغلط."""
    account = get_bank_account_or_404(db, bank_account_id)
    lines, _ = crud.list_bank_statement_lines(db, account.id, status="unmatched", limit=1000)
    matched_count = 0
    for line in lines:
        if line.amount <= 0:
            continue  # مطابقة السحوبات/العمولات البنكية يدوية دايمًا (مفيش Payment مقابل)
        candidates = crud.find_matching_payment_candidates(
            db, account.branch_id, line.amount, line.line_date, bank_account_id=account.id,
        )
        if len(candidates) == 1:
            crud.match_statement_line(db, line, candidates[0].id, matched_by)
            matched_count += 1
    db.commit()
    return matched_count


def match_bank_statement_line(
    db: Session, bank_account_id: int, line_id: int, payment_id: int, matched_by: int,
) -> BankStatementLine:
    account = get_bank_account_or_404(db, bank_account_id)
    line = crud.get_bank_statement_line(db, line_id)
    if not line or line.bank_account_id != account.id:
        raise ValueError(f"سطر كشف الحساب {line_id} غير موجود")
    if line.status == "matched":
        raise ValueError("السطر ده متطابق بالفعل — ألغِ المطابقة أولاً لو عايز تغيّرها")
    payment = crud.get_payment(db, payment_id)
    if not payment or payment.branch_id != account.branch_id:
        raise ValueError(f"الدفعة {payment_id} غير موجودة")
    if payment.voided_at is not None:
        raise ValueError("الدفعة ملغاة — لا يمكن مطابقتها بسطر كشف حساب")
    line = crud.match_statement_line(db, line, payment_id, matched_by)
    db.commit()
    db.refresh(line)
    return line


def unmatch_bank_statement_line(db: Session, bank_account_id: int, line_id: int) -> BankStatementLine:
    account = get_bank_account_or_404(db, bank_account_id)
    line = crud.get_bank_statement_line(db, line_id)
    if not line or line.bank_account_id != account.id:
        raise ValueError(f"سطر كشف الحساب {line_id} غير موجود")
    if line.status != "matched":
        raise ValueError("السطر ده مش متطابق أصلاً")
    line = crud.unmatch_statement_line(db, line)
    db.commit()
    db.refresh(line)
    return line


def get_bank_reconciliation_summary(db: Session, bank_account_id: int, as_of: date) -> BankReconciliationSummary:
    """رصيد الدفاتر (من دفتر اليومية لو الحساب مربوط بـ gl_account_id، وإلا
    من الدفعات المطابقة فقط) مقابل رصيد كشف الحساب (كل السطور غير المتجاهلة)
    — الفرق بينهم + عدد السطور/الدفعات غير المطابقة هو تقرير المطابقة."""
    account = get_bank_account_or_404(db, bank_account_id)

    if account.gl_account_id:
        sums = crud.sum_journal_lines_by_account(db, account.branch_id, None, as_of)
        debit_sum, credit_sum = sums.get(account.gl_account_id, (Decimal("0"), Decimal("0")))
        book_balance = account.opening_balance + (debit_sum - credit_sum)
    else:
        book_balance = account.opening_balance + crud.sum_matched_payments(db, account.id, as_of)

    statement_balance = account.opening_balance + crud.sum_statement_lines(db, account.id, as_of)
    unmatched_lines = crud.count_unmatched_statement_lines(db, account.id)
    unmatched_pay_count, unmatched_pay_total = crud.unmatched_payments_summary(db, account.branch_id, as_of)
    difference = statement_balance - book_balance

    return BankReconciliationSummary(
        bank_account_id=account.id, as_of=as_of,
        opening_balance=account.opening_balance,
        book_balance=book_balance, statement_balance=statement_balance,
        difference=difference,
        is_reconciled=(abs(difference) <= Decimal("0.01") and unmatched_lines == 0),
        unmatched_statement_lines=unmatched_lines,
        unmatched_payments_count=unmatched_pay_count,
        unmatched_payments_total=unmatched_pay_total,
    )


# ── Payment Channels ─────────────────────────────────────────────────────
#
# قناة تحصيل = وجهة GL حقيقية يختارها الكاشير (صندوق/Visa CIB/Vodafone
# Cash...). التصميم بالكامل مبني على قاعدتين لا يجوز كسرهما:
#   1. لا حذف أبدًا — تعطيل فقط (is_active=False)، عشان أي بيع/قيد تاريخي
#      يفضل يقدر يرجع لنفس القناة اللي استُخدمت وقته.
#   2. أي بيع بيسجّل *لقطة* (snapshot) من القناة وقت الحركة (id/code/name +
#      حساب GL) — مش مرجع حي بيتغيّر لو القناة اتعدّلت بعد كده. المرتجع/الـ
#      void لازم يستخدم اللقطة المحفوظة وقت البيع، مش إعداد القناة الحالي.
