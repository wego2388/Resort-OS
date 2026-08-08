"""Business services for personal credit accounts (Decision 0005).

Financial invariants:
* every movement owns one posted journal entry;
* the account row is locked before status/limit/balance checks;
* integrations may request ``commit=False`` so their wider POS transaction is atomic;
* ``balance_delta`` is the immutable ledger truth and ``current_balance`` is its projection.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db_errors import is_lock_not_available
from app.modules.credit import crud
from app.modules.credit.models import CreditAccount, CreditTransaction
from app.modules.credit.schemas import (
    CreditAccountCreate,
    CreditAccountPage,
    CreditAccountRead,
    CreditReceivableItem,
    CreditReceivablesResponse,
    CreditStatementResponse,
    CreditTransactionRead,
)
from app.resort_os.timezone_utils import local_today


PERSONAL_RECEIVABLES_ACCOUNT = "1160"
_MONEY = Decimal("0.01")


class CreditLimitExceededError(ValueError):
    def __init__(self, current: Decimal, limit: Decimal, requested: Decimal):
        self.current = current
        self.limit = limit
        self.requested = requested
        super().__init__(
            f"تجاوز حد الائتمان: الرصيد الحالي {current} + المطلوب {requested} "
            f"= {current + requested} > الحد {limit}"
        )


class CreditAccountInactiveError(ValueError):
    pass


class CreditAccountNotFoundError(ValueError):
    pass


class CreditTransactionNotFoundError(ValueError):
    pass


class CreditReversalError(ValueError):
    pass


class CreditConcurrencyError(RuntimeError):
    pass


class CreditIdempotencyConflictError(ValueError):
    pass


def _utc_now() -> datetime:
    """UTC-naive timestamp, matching TimestampMixin/database storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_MONEY)


def _lock_account(db: Session, account_id: int, branch_id: int) -> CreditAccount:
    try:
        account = crud.lock_account(db, account_id, branch_id)
    except OperationalError as exc:
        if not is_lock_not_available(exc):
            raise
        db.rollback()
        raise CreditConcurrencyError(
            "الحساب الآجل مشغول الآن بحركة أخرى — حاول ثانية خلال لحظات"
        ) from exc
    if not account:
        raise CreditAccountNotFoundError(f"الحساب {account_id} غير موجود")
    return account


def _get_holder_name(db: Session, account: CreditAccount) -> str:
    if account.holder_type == "customer" and account.customer_id:
        from app.modules.crm.models import Customer  # noqa: PLC0415

        row = db.query(Customer.full_name).filter(Customer.id == account.customer_id).first()
        return row.full_name if row else f"عميل {account.customer_id}"
    if account.holder_type == "employee" and account.employee_id:
        from app.modules.hr.models import Employee  # noqa: PLC0415

        row = db.query(Employee.full_name).filter(Employee.id == account.employee_id).first()
        return row.full_name if row else f"موظف {account.employee_id}"
    return "غير معروف"


def _holder_names(db: Session, accounts: Iterable[CreditAccount]) -> dict[int, str]:
    accounts = list(accounts)
    customer_ids = [a.customer_id for a in accounts if a.customer_id is not None]
    employee_ids = [a.employee_id for a in accounts if a.employee_id is not None]
    names: dict[tuple[str, int], str] = {}
    if customer_ids:
        from app.modules.crm.models import Customer  # noqa: PLC0415

        for holder_id, name in db.query(Customer.id, Customer.full_name).filter(
            Customer.id.in_(customer_ids)
        ).all():
            names[("customer", holder_id)] = name
    if employee_ids:
        from app.modules.hr.models import Employee  # noqa: PLC0415

        for holder_id, name in db.query(Employee.id, Employee.full_name).filter(
            Employee.id.in_(employee_ids)
        ).all():
            names[("employee", holder_id)] = name
    result: dict[int, str] = {}
    for account in accounts:
        holder_id = account.customer_id if account.holder_type == "customer" else account.employee_id
        result[account.id] = names.get(
            (account.holder_type, holder_id), f"{account.holder_type} {holder_id}",
        )
    return result


def _get_user_name(db: Session, user_id: int) -> str:
    from app.core.kernel.models.user import User  # noqa: PLC0415

    row = db.query(User.full_name).filter(User.id == user_id).first()
    return row.full_name if row else f"مستخدم {user_id}"


def _build_account_read(
    db: Session, account: CreditAccount, *, holder_name: str | None = None,
) -> CreditAccountRead:
    available = None
    if account.credit_limit > 0:
        available = max(Decimal("0"), account.credit_limit - account.current_balance)
    return CreditAccountRead(
        id=account.id,
        branch_id=account.branch_id,
        holder_type=account.holder_type,
        customer_id=account.customer_id,
        employee_id=account.employee_id,
        holder_name=holder_name or _get_holder_name(db, account),
        credit_limit=account.credit_limit,
        current_balance=account.current_balance,
        available_credit=available,
        status=account.status,
        notes=account.notes,
        opened_by=account.opened_by,
        created_at=account.created_at,
        updated_at=account.updated_at,
        computed_at=_utc_now(),
    )


def _build_txn_read(db: Session, txn: CreditTransaction) -> CreditTransactionRead:
    return CreditTransactionRead(
        id=txn.id,
        credit_account_id=txn.credit_account_id,
        branch_id=txn.branch_id,
        txn_type=txn.txn_type,
        amount=txn.amount,
        balance_delta=txn.balance_delta,
        payment_method=txn.payment_method,
        ref_order_id=txn.ref_order_id,
        ref_beach_tx_id=txn.ref_beach_tx_id,
        reversed_txn_id=txn.reversed_txn_id,
        notes=txn.notes,
        recorded_by=txn.recorded_by,
        recorded_by_name=_get_user_name(db, txn.recorded_by),
        journal_entry_id=txn.journal_entry_id,
        created_at=txn.created_at,
    )


def _audit(
    db: Session,
    action: str,
    *,
    user_id: int,
    branch_id: int,
    entity_type: str,
    entity_id: int,
    approved_by: int | None = None,
    data: dict | None = None,
) -> None:
    from app.modules.core.policy_engine import record_policy_audit  # noqa: PLC0415

    record_policy_audit(
        db,
        action,
        user_id=user_id,
        approved_by=approved_by,
        branch_id=branch_id,
        entity_type=entity_type,
        entity_id=entity_id,
        data=data,
    )


def _journal_account(db: Session, branch_id: int, code: str):
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance.services import FinancialConfigurationError  # noqa: PLC0415

    account = finance_crud.get_account_by_code(db, branch_id, code)
    if not account or not account.is_active:
        raise FinancialConfigurationError(f"حساب محاسبي غير معرّف أو غير نشط للفرع: {code}")
    return account


def _cost_center_id(db: Session, branch_id: int, code: str | None) -> int | None:
    if not code:
        return None
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance import services as finance_services  # noqa: PLC0415

    center = finance_crud.get_cost_center_by_code(db, branch_id, code)
    if not center:
        finance_services.ensure_default_cost_centers(db, branch_id, commit=False)
        center = finance_crud.get_cost_center_by_code(db, branch_id, code)
    if not center:
        raise finance_services.FinancialConfigurationError(
            f"تعذّر تجهيز مركز التكلفة: {code}"
        )
    return center.id


def _create_journal(
    db: Session,
    *,
    branch_id: int,
    debit_code: str,
    credit_allocations: list[tuple[str, Decimal, str | None]],
    amount: Decimal,
    reference: str,
    description: str,
    source: str,
    source_id: int | None,
    created_by: int,
):
    """Create one balanced posted entry without committing the surrounding unit of work."""
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance import services as finance_services  # noqa: PLC0415
    from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate  # noqa: PLC0415

    amount = _money(amount)
    normalized = [(code, _money(value), center) for code, value, center in credit_allocations]
    if sum((value for _, value, _ in normalized), Decimal("0")) != amount:
        raise ValueError("توزيع الإيراد لا يساوي مبلغ حركة الحساب الآجل")
    entry_date = local_today(settings.TIMEZONE)
    finance_services.validate_period_open(db, branch_id, entry_date)
    debit = _journal_account(db, branch_id, debit_code)
    lines = [
        JournalLineCreate(account_id=debit.id, debit=amount, credit=Decimal("0")),
    ]
    for credit_code, value, center_code in normalized:
        if value <= 0:
            raise ValueError("حصة الإيراد يجب أن تكون موجبة")
        credit = _journal_account(db, branch_id, credit_code)
        lines.append(JournalLineCreate(
            account_id=credit.id,
            debit=Decimal("0"),
            credit=value,
            cost_center_id=_cost_center_id(db, branch_id, center_code),
        ))
    return finance_crud.create_journal_entry(
        db,
        JournalEntryCreate(
            branch_id=branch_id,
            entry_date=entry_date,
            reference=reference[:50],
            description=description,
            source=source,
            source_id=source_id,
            lines=lines,
        ),
        created_by,
    )


def _create_payment_journal(
    db: Session,
    *,
    branch_id: int,
    account_id: int,
    amount: Decimal,
    payment_method: str,
    description: str,
    created_by: int,
):
    debit_code = "1100" if payment_method == "cash" else "1110"
    return _create_journal(
        db,
        branch_id=branch_id,
        debit_code=debit_code,
        credit_allocations=[(PERSONAL_RECEIVABLES_ACCOUNT, amount, None)],
        amount=amount,
        reference=f"CRP-{account_id}-{created_by}",
        description=description,
        source="credit_payment",
        source_id=account_id,
        created_by=created_by,
    )


def _create_reversal_journal(
    db: Session,
    original: CreditTransaction,
    *,
    description: str,
    created_by: int,
):
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance import services as finance_services  # noqa: PLC0415
    from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate  # noqa: PLC0415

    original_entry = finance_crud.get_journal_entry(db, original.journal_entry_id)
    if not original_entry or original_entry.branch_id != original.branch_id or not original_entry.lines:
        raise CreditReversalError("القيد الأصلي غير موجود أو غير صالح للعكس")
    entry_date = local_today(settings.TIMEZONE)
    finance_services.validate_period_open(db, original.branch_id, entry_date)
    lines = [
        JournalLineCreate(
            account_id=line.account_id,
            debit=line.credit,
            credit=line.debit,
            description=f"عكس السطر #{line.id}",
            cost_center_id=line.cost_center_id,
        )
        for line in original_entry.lines
    ]
    return finance_crud.create_journal_entry(
        db,
        JournalEntryCreate(
            branch_id=original.branch_id,
            entry_date=entry_date,
            reference=f"CRR-{original.id}",
            description=description,
            source="credit_reversal",
            source_id=original.id,
            lines=lines,
        ),
        created_by,
    )


def _create_refund_journal(
    db: Session,
    original: CreditTransaction,
    *,
    amount: Decimal,
    debit_allocations: list[tuple[str, Decimal, str | None]],
    description: str,
    created_by: int,
):
    """Reduce receivables and reverse the refunded source revenue, without commit."""
    from app.modules.finance import crud as finance_crud  # noqa: PLC0415
    from app.modules.finance import services as finance_services  # noqa: PLC0415
    from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate  # noqa: PLC0415

    amount = _money(amount)
    normalized = [(code, _money(value), center) for code, value, center in debit_allocations]
    if sum((value for _, value, _ in normalized), Decimal("0")) != amount:
        raise ValueError("توزيع مرتجع الحساب الآجل لا يساوي مبلغ المرتجع")
    entry_date = local_today(settings.TIMEZONE)
    finance_services.validate_period_open(db, original.branch_id, entry_date)
    lines = []
    for debit_code, value, center_code in normalized:
        if value <= 0:
            raise ValueError("حصة المرتجع يجب أن تكون موجبة")
        debit = _journal_account(db, original.branch_id, debit_code)
        lines.append(JournalLineCreate(
            account_id=debit.id,
            debit=value,
            credit=Decimal("0"),
            cost_center_id=_cost_center_id(db, original.branch_id, center_code),
        ))
    receivables = _journal_account(db, original.branch_id, PERSONAL_RECEIVABLES_ACCOUNT)
    lines.append(JournalLineCreate(
        account_id=receivables.id,
        debit=Decimal("0"),
        credit=amount,
    ))
    return finance_crud.create_journal_entry(
        db,
        JournalEntryCreate(
            branch_id=original.branch_id,
            entry_date=entry_date,
            reference=f"CRF-{original.id}",
            description=description,
            source="credit_refund",
            source_id=original.id,
            lines=lines,
        ),
        created_by,
    )


def _validate_source_branch(
    db: Session,
    branch_id: int,
    ref_order_id: int | None,
    ref_beach_tx_id: int | None,
) -> tuple[str, int, str, str | None]:
    if (ref_order_id is None) == (ref_beach_tx_id is None):
        raise ValueError("حركة الترحيل يجب أن ترتبط بمصدر واحد فقط")
    if ref_order_id is not None:
        from app.modules.dining.models import DiningOrder  # noqa: PLC0415

        source = db.query(DiningOrder).filter(
            DiningOrder.id == ref_order_id, DiningOrder.branch_id == branch_id,
        ).first()
        if not source:
            raise ValueError(f"طلب الدايننج {ref_order_id} غير موجود في الفرع")
        if source.status != "paid" or "credit_account" not in (source.payment_method or ""):
            raise ValueError("طلب الدايننج ليس مسجلًا كبيع على حساب آجل")
        return "dining", ref_order_id, f"ORD-{source.order_number}", "REST"
    from app.modules.beach.models import BeachTransaction  # noqa: PLC0415

    source = db.query(BeachTransaction).filter(
        BeachTransaction.id == ref_beach_tx_id,
        BeachTransaction.branch_id == branch_id,
    ).first()
    if not source:
        raise ValueError(f"معاملة الشاطئ {ref_beach_tx_id} غير موجودة في الفرع")
    if source.payment_method != "credit_account":
        raise ValueError("معاملة الشاطئ ليست مسجلة كبيع على حساب آجل")
    return "beach", ref_beach_tx_id, f"BCH-{ref_beach_tx_id:06d}", "BEACH"


def open_credit_account(
    db: Session, data: CreditAccountCreate, branch_id: int, opened_by: int,
) -> CreditAccountRead:
    if data.holder_type == "customer":
        from app.modules.crm.models import Customer  # noqa: PLC0415

        holder = db.query(Customer).filter(
            Customer.id == data.holder_id, Customer.branch_id == branch_id,
        ).first()
    else:
        from app.modules.hr.models import Employee  # noqa: PLC0415

        holder = db.query(Employee).filter(
            Employee.id == data.holder_id, Employee.branch_id == branch_id,
        ).first()
    if not holder:
        label = "العميل" if data.holder_type == "customer" else "الموظف"
        raise CreditAccountNotFoundError(
            f"{label} {data.holder_id} غير موجود أو لا ينتمي لهذا الفرع"
        )
    existing = crud.get_account_for_holder(db, data.holder_type, data.holder_id, branch_id)
    if existing:
        raise ValueError(
            f"يوجد حساب آجل لهذا الشخص بالفعل (#{existing.id})؛ "
            "أعد تنشيطه بدل إنشاء حساب مكرر"
        )
    try:
        account = crud.create_account(db, CreditAccount(
            branch_id=branch_id,
            holder_type=data.holder_type,
            customer_id=data.holder_id if data.holder_type == "customer" else None,
            employee_id=data.holder_id if data.holder_type == "employee" else None,
            credit_limit=_money(data.credit_limit),
            current_balance=Decimal("0"),
            status="active",
            opened_by=opened_by,
            notes=data.notes,
        ))
    except IntegrityError as exc:
        db.rollback()
        if crud.get_account_for_holder(db, data.holder_type, data.holder_id, branch_id):
            raise ValueError("يوجد حساب آجل لهذا الشخص بالفعل") from exc
        raise
    _audit(
        db, "open_credit_account", user_id=opened_by, branch_id=branch_id,
        entity_type="credit_account", entity_id=account.id,
        data={"holder_type": data.holder_type, "holder_id": data.holder_id,
              "credit_limit": str(account.credit_limit)},
    )
    db.commit()
    db.refresh(account)
    return _build_account_read(db, account)


def update_account_status(
    db: Session,
    account_id: int,
    branch_id: int,
    new_status: str,
    notes: str | None,
    updated_by: int,
) -> CreditAccountRead:
    account = _lock_account(db, account_id, branch_id)
    if new_status == "closed" and account.current_balance != 0:
        raise ValueError("لا يمكن إغلاق حساب عليه رصيد؛ حصّل الرصيد أو اعكس الحركات أولاً")
    old_status = account.status
    account.status = new_status
    if notes is not None:
        account.notes = notes
    _audit(
        db, "update_credit_account_status", user_id=updated_by, branch_id=branch_id,
        entity_type="credit_account", entity_id=account.id,
        data={"old_status": old_status, "new_status": new_status, "notes": notes},
    )
    db.commit()
    db.refresh(account)
    return _build_account_read(db, account)


def update_credit_limit(
    db: Session,
    account_id: int,
    branch_id: int,
    new_limit: Decimal,
    notes: str | None,
    updated_by: int,
) -> CreditAccountRead:
    account = _lock_account(db, account_id, branch_id)
    new_limit = _money(new_limit)
    if new_limit > 0 and new_limit < account.current_balance:
        raise ValueError("حد الائتمان الجديد أقل من الرصيد المستحق الحالي")
    old_limit = account.credit_limit
    account.credit_limit = new_limit
    if notes is not None:
        account.notes = notes
    _audit(
        db, "update_credit_account_limit", user_id=updated_by, branch_id=branch_id,
        entity_type="credit_account", entity_id=account.id,
        data={"old_limit": str(old_limit), "new_limit": str(new_limit), "notes": notes},
    )
    db.commit()
    db.refresh(account)
    return _build_account_read(db, account)


def charge_to_account(
    db: Session,
    account_id: int,
    branch_id: int,
    amount: Decimal,
    recorded_by: int,
    *,
    ref_order_id: int | None = None,
    ref_beach_tx_id: int | None = None,
    notes: str | None = None,
    revenue_allocations: list[tuple[str, Decimal, str | None]] | None = None,
    acting_user_level: int = 100,
    approver_user_id: int | None = None,
    approver_pin: str | None = None,
    idempotency_key: str | None = None,
    commit: bool = True,
) -> CreditTransactionRead:
    amount = _money(amount)
    if amount <= 0:
        raise ValueError("مبلغ الترحيل يجب أن يكون موجبًا")
    if idempotency_key:
        existing = crud.get_transaction_by_idempotency(db, branch_id, idempotency_key)
        if existing:
            if (
                existing.credit_account_id == account_id
                and existing.txn_type == "charge"
                and existing.amount == amount
                and existing.ref_order_id == ref_order_id
                and existing.ref_beach_tx_id == ref_beach_tx_id
            ):
                return _build_txn_read(db, existing)
            raise CreditIdempotencyConflictError(
                "مفتاح idempotency مستخدم لحركة مختلفة؛ استخدم مفتاحًا جديدًا"
            )

    source, source_id, reference, default_center = _validate_source_branch(
        db, branch_id, ref_order_id, ref_beach_tx_id,
    )
    existing_source = crud.get_charge_for_source(
        db, ref_order_id=ref_order_id, ref_beach_tx_id=ref_beach_tx_id,
    )
    if existing_source:
        if existing_source.credit_account_id == account_id and existing_source.amount == amount:
            return _build_txn_read(db, existing_source)
        raise CreditIdempotencyConflictError(
            "مصدر البيع مرحّل بالفعل على حساب آجل مختلف"
        )
    account = _lock_account(db, account_id, branch_id)
    if account.status != "active":
        raise CreditAccountInactiveError(
            f"الحساب {account_id} غير نشط (status={account.status})"
        )
    approved_by = None
    if account.credit_limit > 0 and account.current_balance + amount > account.credit_limit:
        if approver_user_id is None and acting_user_level < 60:
            raise CreditLimitExceededError(account.current_balance, account.credit_limit, amount)
        from app.modules.core.policy_engine import require_approval  # noqa: PLC0415

        approved_by = require_approval(
            db,
            "override_credit_limit",
            acting_user_level=acting_user_level,
            approver_user_id=approver_user_id,
            approver_pin=approver_pin,
        )

    holder_name = _get_holder_name(db, account)
    if revenue_allocations is None:
        revenue_code = "4200" if source == "dining" else "4300"
        revenue_allocations = [(revenue_code, amount, default_center)]
    entry = _create_journal(
        db,
        branch_id=branch_id,
        debit_code=PERSONAL_RECEIVABLES_ACCOUNT,
        credit_allocations=revenue_allocations,
        amount=amount,
        reference=reference,
        description=f"ترحيل {source} على حساب آجل — {holder_name}",
        source=f"credit_{source}_charge",
        source_id=source_id,
        created_by=recorded_by,
    )
    try:
        txn = crud.create_transaction(db, CreditTransaction(
            credit_account_id=account.id,
            branch_id=branch_id,
            txn_type="charge",
            amount=amount,
            balance_delta=amount,
            payment_method=None,
            ref_order_id=ref_order_id,
            ref_beach_tx_id=ref_beach_tx_id,
            idempotency_key=idempotency_key,
            notes=notes,
            recorded_by=recorded_by,
            journal_entry_id=entry.id,
        ))
    except IntegrityError as exc:
        db.rollback()
        existing_after_race = crud.get_charge_for_source(
            db, ref_order_id=ref_order_id, ref_beach_tx_id=ref_beach_tx_id,
        )
        duplicate_key = (
            crud.get_transaction_by_idempotency(db, branch_id, idempotency_key)
            if idempotency_key else None
        )
        if existing_after_race or duplicate_key:
            raise CreditIdempotencyConflictError(
                "مصدر البيع أو مفتاح idempotency تم ترحيله بالتزامن"
            ) from exc
        raise
    account.current_balance = _money(account.current_balance + amount)
    _audit(
        db, "charge_to_credit_account", user_id=recorded_by, approved_by=approved_by,
        branch_id=branch_id, entity_type="credit_transaction", entity_id=txn.id,
        data={"account_id": account.id, "amount": str(amount), "source": source,
              "source_id": source_id, "balance_after": str(account.current_balance)},
    )
    if commit:
        db.commit()
        db.refresh(txn)
    else:
        db.flush()
    return _build_txn_read(db, txn)


def record_payment(
    db: Session,
    account_id: int,
    branch_id: int,
    amount: Decimal,
    recorded_by: int,
    *,
    payment_method: str = "cash",
    notes: str | None = None,
    idempotency_key: str | None = None,
) -> CreditTransactionRead:
    amount = _money(amount)
    if amount <= 0:
        raise ValueError("مبلغ الدفعة يجب أن يكون موجبًا")
    if payment_method not in {"cash", "bank"}:
        raise ValueError("طريقة التحصيل يجب أن تكون cash أو bank")
    if idempotency_key:
        existing = crud.get_transaction_by_idempotency(db, branch_id, idempotency_key)
        if existing:
            if (
                existing.credit_account_id == account_id
                and existing.txn_type == "payment"
                and existing.amount == amount
                and existing.payment_method == payment_method
            ):
                return _build_txn_read(db, existing)
            raise CreditIdempotencyConflictError(
                "مفتاح idempotency مستخدم لحركة مختلفة؛ استخدم مفتاحًا جديدًا"
            )
    account = _lock_account(db, account_id, branch_id)
    if account.status == "closed":
        raise CreditAccountInactiveError("الحساب مغلق")
    if amount > account.current_balance:
        raise ValueError(f"الدفعة ({amount}) أكبر من الرصيد المستحق ({account.current_balance})")
    holder_name = _get_holder_name(db, account)
    entry = _create_payment_journal(
        db,
        branch_id=branch_id,
        account_id=account.id,
        amount=amount,
        payment_method=payment_method,
        description=f"تحصيل حساب آجل — {holder_name}",
        created_by=recorded_by,
    )
    txn = crud.create_transaction(db, CreditTransaction(
        credit_account_id=account.id,
        branch_id=branch_id,
        txn_type="payment",
        amount=amount,
        balance_delta=-amount,
        payment_method=payment_method,
        idempotency_key=idempotency_key,
        notes=notes,
        recorded_by=recorded_by,
        journal_entry_id=entry.id,
    ))
    account.current_balance = _money(account.current_balance - amount)
    _audit(
        db, "record_credit_payment", user_id=recorded_by, branch_id=branch_id,
        entity_type="credit_transaction", entity_id=txn.id,
        data={"account_id": account.id, "amount": str(amount),
              "payment_method": payment_method, "balance_after": str(account.current_balance)},
    )
    db.commit()
    db.refresh(txn)
    return _build_txn_read(db, txn)


def reverse_transaction(
    db: Session,
    original_txn_id: int,
    branch_id: int,
    notes: str,
    recorded_by: int,
    *,
    expected_account_id: int | None = None,
    commit: bool = True,
) -> CreditTransactionRead:
    try:
        original = crud.lock_transaction(db, original_txn_id, branch_id)
    except OperationalError as exc:
        if not is_lock_not_available(exc):
            raise
        db.rollback()
        raise CreditConcurrencyError("الحركة مشغولة الآن بعملية عكس أخرى") from exc
    if not original:
        raise CreditTransactionNotFoundError(f"الحركة {original_txn_id} غير موجودة")
    if expected_account_id is not None and original.credit_account_id != expected_account_id:
        raise CreditTransactionNotFoundError("الحركة لا تنتمي للحساب الموجود في المسار")
    if original.txn_type not in {"charge", "payment"}:
        raise CreditReversalError("لا يمكن عكس حركة عكس أو مرتجع")
    if crud.list_adjustments_for_transaction(db, original.id):
        raise CreditReversalError("تم عكس الحركة أو رد جزء منها مسبقًا")
    account = _lock_account(db, original.credit_account_id, branch_id)
    delta = -original.balance_delta
    new_balance = _money(account.current_balance + delta)
    if new_balance < 0:
        raise CreditReversalError(
            "عكس هذه الحركة سيجعل رصيد الحساب سالبًا؛ راجع التحصيلات اللاحقة أولاً"
        )
    entry = _create_reversal_journal(
        db,
        original,
        description=f"عكس حركة حساب آجل #{original.id}",
        created_by=recorded_by,
    )
    txn = crud.create_transaction(db, CreditTransaction(
        credit_account_id=account.id,
        branch_id=branch_id,
        txn_type="reversal",
        amount=original.amount,
        balance_delta=delta,
        payment_method=None,
        reversed_txn_id=original.id,
        notes=notes,
        recorded_by=recorded_by,
        journal_entry_id=entry.id,
    ))
    account.current_balance = new_balance
    _audit(
        db, "reverse_credit_transaction", user_id=recorded_by, branch_id=branch_id,
        entity_type="credit_transaction", entity_id=txn.id,
        data={"account_id": account.id, "original_txn_id": original.id,
              "balance_delta": str(delta), "balance_after": str(new_balance), "reason": notes},
    )
    if commit:
        db.commit()
        db.refresh(txn)
    else:
        db.flush()
    return _build_txn_read(db, txn)


def refund_charge(
    db: Session,
    original_txn_id: int,
    branch_id: int,
    amount: Decimal,
    notes: str,
    recorded_by: int,
    *,
    debit_allocations: list[tuple[str, Decimal, str | None]],
    commit: bool = True,
) -> CreditTransactionRead:
    """Append a partial/full commercial refund against one original charge.

    Unlike an exact correction reversal, an order can produce several item
    refunds. Locking the original charge serializes the aggregate remaining
    refundable amount, while the account lock protects its balance projection.
    """
    amount = _money(amount)
    if amount <= 0:
        raise ValueError("مبلغ المرتجع يجب أن يكون موجبًا")
    try:
        original = crud.lock_transaction(db, original_txn_id, branch_id)
    except OperationalError as exc:
        if not is_lock_not_available(exc):
            raise
        db.rollback()
        raise CreditConcurrencyError("حركة البيع مشغولة الآن بمرتجع آخر") from exc
    if not original:
        raise CreditTransactionNotFoundError(f"الحركة {original_txn_id} غير موجودة")
    if original.txn_type != "charge":
        raise CreditReversalError("المرتجع التجاري يجب أن يرتبط بحركة ترحيل أصلية")

    adjustments = crud.list_adjustments_for_transaction(db, original.id)
    if any(txn.txn_type == "reversal" for txn in adjustments):
        raise CreditReversalError("تم عكس حركة البيع الأصلية بالكامل")
    refunded = sum(
        (txn.amount for txn in adjustments if txn.txn_type == "refund"),
        Decimal("0"),
    )
    remaining = _money(original.amount - refunded)
    if amount > remaining:
        raise CreditReversalError(
            f"المرتجع ({amount}) أكبر من المتبقي على حركة البيع ({remaining})"
        )

    account = _lock_account(db, original.credit_account_id, branch_id)
    new_balance = _money(account.current_balance - amount)
    if new_balance < 0:
        raise CreditReversalError(
            "المرتجع سيجعل رصيد الحساب سالبًا؛ توجد تحصيلات لاحقة وتلزم تسوية يدوية"
        )
    entry = _create_refund_journal(
        db,
        original,
        amount=amount,
        debit_allocations=debit_allocations,
        description=f"مرتجع بيع على حساب آجل #{original.id}",
        created_by=recorded_by,
    )
    txn = crud.create_transaction(db, CreditTransaction(
        credit_account_id=account.id,
        branch_id=branch_id,
        txn_type="refund",
        amount=amount,
        balance_delta=-amount,
        payment_method=None,
        reversed_txn_id=original.id,
        notes=notes,
        recorded_by=recorded_by,
        journal_entry_id=entry.id,
    ))
    account.current_balance = new_balance
    _audit(
        db, "refund_credit_charge", user_id=recorded_by, branch_id=branch_id,
        entity_type="credit_transaction", entity_id=txn.id,
        data={"account_id": account.id, "original_txn_id": original.id,
              "amount": str(amount), "balance_after": str(new_balance), "reason": notes},
    )
    if commit:
        db.commit()
        db.refresh(txn)
    else:
        db.flush()
    return _build_txn_read(db, txn)


def get_account_detail(db: Session, account_id: int, branch_id: int) -> CreditAccountRead:
    account = crud.get_account(db, account_id)
    if not account or account.branch_id != branch_id:
        raise CreditAccountNotFoundError(f"الحساب {account_id} غير موجود")
    return _build_account_read(db, account)


def get_statement(
    db: Session,
    account_id: int,
    branch_id: int,
    date_from: date | None = None,
    date_to: date | None = None,
) -> CreditStatementResponse:
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from يجب أن يسبق date_to")
    account = crud.get_account(db, account_id)
    if not account or account.branch_id != branch_id:
        raise CreditAccountNotFoundError(f"الحساب {account_id} غير موجود")
    txns = crud.list_transactions(db, account_id, date_from, date_to)
    charges = sum((t.amount for t in txns if t.txn_type == "charge"), Decimal("0"))
    payments = sum((t.amount for t in txns if t.txn_type == "payment"), Decimal("0"))
    refunds = sum((t.amount for t in txns if t.txn_type == "refund"), Decimal("0"))
    movement = sum((t.balance_delta for t in txns), Decimal("0"))
    now = _utc_now()
    return CreditStatementResponse(
        account=_build_account_read(db, account),
        transactions=[_build_txn_read(db, txn) for txn in txns],
        period_from=date_from.isoformat() if date_from else None,
        period_to=date_to.isoformat() if date_to else None,
        total_charges=charges,
        total_payments=payments,
        total_refunds=refunds,
        net_movement=movement,
        computed_at=now,
    )


def list_accounts_for_branch(
    db: Session,
    branch_id: int,
    status: str | None = None,
    holder_type: str | None = None,
    *,
    page: int = 1,
    size: int = 50,
) -> CreditAccountPage:
    accounts, total = crud.list_accounts(
        db, branch_id, status, holder_type, skip=(page - 1) * size, limit=size,
    )
    names = _holder_names(db, accounts)
    return CreditAccountPage(
        total=total,
        page=page,
        size=size,
        items=[_build_account_read(db, account, holder_name=names[account.id]) for account in accounts],
    )


def lookup_account_by_holder(
    db: Session, branch_id: int, holder_type: str, holder_id: int,
) -> CreditAccountRead | None:
    account = crud.get_account_for_holder(db, holder_type, holder_id, branch_id)
    return _build_account_read(db, account) if account else None


def get_branch_outstanding(db: Session, branch_id: int) -> Decimal:
    return sum(
        (account.current_balance for account in crud.get_accounts_with_balance(db, branch_id)),
        Decimal("0"),
    )


def get_credit_receivables_for_owner(
    db: Session, branch_id: int,
) -> CreditReceivablesResponse:
    accounts = crud.get_accounts_with_balance(db, branch_id)
    names = _holder_names(db, accounts)
    last_charge_times = crud.get_last_charge_times(db, [account.id for account in accounts])
    now = _utc_now()
    items: list[CreditReceivableItem] = []
    for account in accounts:
        last_charge_at = last_charge_times.get(account.id)
        days_since = (now - last_charge_at).days if last_charge_at else None
        items.append(CreditReceivableItem(
            account_id=account.id,
            holder_type=account.holder_type,
            holder_name=names[account.id],
            current_balance=account.current_balance,
            credit_limit=account.credit_limit,
            status=account.status,
            last_charge_at=last_charge_at,
            days_since_last_charge=days_since,
            is_overdue=bool(days_since is not None and days_since > 30),
        ))
    return CreditReceivablesResponse(
        branch_id=branch_id,
        accounts=items,
        total_outstanding=sum((account.current_balance for account in accounts), Decimal("0")),
        overdue_count=sum(1 for item in items if item.is_overdue),
        computed_at=now,
    )
