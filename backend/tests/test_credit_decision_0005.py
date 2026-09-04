"""Acceptance tests for Decision 0005 personal credit accounts."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.modules.credit import crud, services
from app.modules.credit.models import CreditTransaction
from app.modules.credit.schemas import CreditAccountCreate


def _setup(db, *, limit: str = "500.00"):
    from app.modules.beach.models import BeachTransaction
    from app.modules.core.models import Branch
    from app.modules.crm.models import Customer
    from app.modules.finance.models import Account

    suffix = uuid.uuid4().hex[:8]
    branch = Branch(name=f"Credit {suffix}", name_ar="فرع آجل", code=f"CR-{suffix}")
    db.add(branch)
    db.flush()
    customer = Customer(branch_id=branch.id, full_name="عميل حساب آجل")
    db.add(customer)
    for code, name, kind in (
        ("1000", "Assets", "asset"),
        ("1100", "Cash", "asset"),
        ("1110", "Bank", "asset"),
        ("1160", "Personal receivables", "asset"),
        ("4300", "Beach revenue", "revenue"),
    ):
        db.add(Account(branch_id=branch.id, code=code, name=name, account_type=kind))
    db.flush()
    beach_tx = BeachTransaction(
        branch_id=branch.id,
        tx_type="entry",
        quantity=1,
        unit_price=Decimal("100"),
        total_amount=Decimal("100"),
        discount_amount=Decimal("0"),
        vat_amount=Decimal("14"),
        surge_applied=False,
        tx_date=date.today(),
        cashier_id=1,
        customer_id=customer.id,
        payment_method="credit_account",
    )
    db.add(beach_tx)
    db.commit()
    account = services.open_credit_account(
        db,
        CreditAccountCreate(
            holder_type="customer", holder_id=customer.id, credit_limit=Decimal(limit),
        ),
        branch.id,
        opened_by=1,
    )
    return branch, customer, beach_tx, account


def _journal_lines(db, journal_entry_id: int):
    from app.modules.finance.models import Account, JournalLine

    return (
        db.query(Account.code, JournalLine.debit, JournalLine.credit)
        .join(JournalLine, JournalLine.account_id == Account.id)
        .filter(JournalLine.entry_id == journal_entry_id)
        .order_by(Account.code)
        .all()
    )


def test_charge_payment_and_exact_reversal_keep_ledger_and_projection_equal(db):
    branch, _, beach_tx, account_read = _setup(db)

    charge = services.charge_to_account(
        db,
        account_read.id,
        branch.id,
        Decimal("114.00"),
        1,
        ref_beach_tx_id=beach_tx.id,
        revenue_allocations=[("4300", Decimal("114.00"), "BEACH")],
    )
    assert charge.balance_delta == Decimal("114.00")
    assert _journal_lines(db, charge.journal_entry_id) == [
        ("1160", Decimal("114.00"), Decimal("0.00")),
        ("4300", Decimal("0.00"), Decimal("114.00")),
    ]

    payment = services.record_payment(
        db,
        account_read.id,
        branch.id,
        Decimal("40.00"),
        1,
        payment_method="cash",
    )
    assert _journal_lines(db, payment.journal_entry_id) == [
        ("1100", Decimal("40.00"), Decimal("0.00")),
        ("1160", Decimal("0.00"), Decimal("40.00")),
    ]

    reversal = services.reverse_transaction(
        db, payment.id, branch.id, "تصحيح تحصيل مسجل بالخطأ", 1,
        expected_account_id=account_read.id,
    )
    assert reversal.balance_delta == Decimal("40.00")
    assert _journal_lines(db, reversal.journal_entry_id) == [
        ("1100", Decimal("0.00"), Decimal("40.00")),
        ("1160", Decimal("40.00"), Decimal("0.00")),
    ]
    account = crud.get_account(db, account_read.id)
    assert account.current_balance == Decimal("114.00")
    assert crud.compute_balance_from_transactions(db, account.id) == account.current_balance


def test_limit_failure_is_fail_closed_and_has_no_financial_artifacts(db):
    branch, _, beach_tx, account = _setup(db, limit="100.00")
    from app.modules.finance.models import JournalEntry

    before = db.query(JournalEntry).count()
    with pytest.raises(services.CreditLimitExceededError):
        services.charge_to_account(
            db, account.id, branch.id, Decimal("114"), 1,
            ref_beach_tx_id=beach_tx.id, acting_user_level=40,
        )
    db.rollback()
    assert db.query(JournalEntry).count() == before
    assert db.query(CreditTransaction).filter_by(credit_account_id=account.id).count() == 0
    assert crud.get_account(db, account.id).current_balance == Decimal("0.00")


def test_suspended_account_rejects_charges_but_accepts_collection(db):
    branch, _, beach_tx, account = _setup(db)
    from app.modules.beach.models import BeachTransaction
    services.charge_to_account(
        db, account.id, branch.id, Decimal("50"), 1, ref_beach_tx_id=beach_tx.id,
    )
    services.update_account_status(db, account.id, branch.id, "suspended", None, 1)
    next_source = BeachTransaction(
        branch_id=branch.id,
        tx_type="entry",
        quantity=1,
        unit_price=Decimal("1"),
        total_amount=Decimal("1"),
        discount_amount=Decimal("0"),
        vat_amount=Decimal("0"),
        surge_applied=False,
        tx_date=date.today(),
        cashier_id=1,
        payment_method="credit_account",
    )
    db.add(next_source)
    db.commit()
    with pytest.raises(services.CreditAccountInactiveError):
        services.charge_to_account(
            db, account.id, branch.id, Decimal("1"), 1, ref_beach_tx_id=next_source.id,
        )
    db.rollback()
    payment = services.record_payment(
        db, account.id, branch.id, Decimal("50"), 1, payment_method="bank",
    )
    assert payment.payment_method == "bank"
    assert crud.get_account(db, account.id).current_balance == Decimal("0.00")


def test_source_and_idempotency_cannot_duplicate_a_charge(db):
    branch, _, beach_tx, account = _setup(db)
    first = services.charge_to_account(
        db,
        account.id,
        branch.id,
        Decimal("10"),
        1,
        ref_beach_tx_id=beach_tx.id,
        idempotency_key="same-request",
    )
    replay = services.charge_to_account(
        db,
        account.id,
        branch.id,
        Decimal("10"),
        1,
        ref_beach_tx_id=beach_tx.id,
        idempotency_key="same-request",
    )
    assert replay.id == first.id
    source_replay = services.charge_to_account(
        db,
        account.id,
        branch.id,
        Decimal("10"),
        1,
        ref_beach_tx_id=beach_tx.id,
        idempotency_key="different-retry-key",
    )
    assert source_replay.id == first.id
    with pytest.raises(services.CreditIdempotencyConflictError):
        services.charge_to_account(
            db,
            account.id,
            branch.id,
            Decimal("11"),
            1,
            ref_beach_tx_id=beach_tx.id,
            idempotency_key="same-request",
        )


def test_cash_beach_ticket_cannot_be_relabelled_as_personal_credit(db):
    branch, _, beach_tx, account = _setup(db)
    beach_tx.payment_method = "cash"
    db.commit()

    with pytest.raises(ValueError, match="ليست مسجلة"):
        services.charge_to_account(
            db, account.id, branch.id, Decimal("10"), 1,
            ref_beach_tx_id=beach_tx.id,
        )


def test_reversal_is_single_use_and_path_account_is_enforced(db):
    branch, _, beach_tx, account = _setup(db)
    charge = services.charge_to_account(
        db, account.id, branch.id, Decimal("20"), 1, ref_beach_tx_id=beach_tx.id,
    )
    services.reverse_transaction(
        db, charge.id, branch.id, "إلغاء بيع مسجل بالخطأ", 1,
        expected_account_id=account.id,
    )
    with pytest.raises(services.CreditReversalError, match="مسبق"):
        services.reverse_transaction(
            db, charge.id, branch.id, "محاولة عكس ثانية", 1,
            expected_account_id=account.id,
        )


def test_partial_sale_refunds_are_capped_and_keep_ledger_equal(db):
    branch, _, beach_tx, account = _setup(db)
    charge = services.charge_to_account(
        db, account.id, branch.id, Decimal("114"), 1, ref_beach_tx_id=beach_tx.id,
    )

    first = services.refund_charge(
        db, charge.id, branch.id, Decimal("30"), "مرتجع جزئي أول", 1,
        debit_allocations=[("4300", Decimal("30"), "BEACH")],
    )
    second = services.refund_charge(
        db, charge.id, branch.id, Decimal("84"), "استكمال المرتجع", 1,
        debit_allocations=[("4300", Decimal("84"), "BEACH")],
    )

    assert first.txn_type == second.txn_type == "refund"
    assert _journal_lines(db, first.journal_entry_id) == [
        ("1160", Decimal("0.00"), Decimal("30.00")),
        ("4300", Decimal("30.00"), Decimal("0.00")),
    ]
    persisted = crud.get_account(db, account.id)
    assert persisted.current_balance == Decimal("0.00")
    assert crud.compute_balance_from_transactions(db, account.id) == persisted.current_balance
    statement = services.get_statement(db, account.id, branch.id)
    assert statement.total_refunds == Decimal("114.00")
    with pytest.raises(services.CreditReversalError, match="المتبقي"):
        services.refund_charge(
            db, charge.id, branch.id, Decimal("1"), "مرتجع زائد", 1,
            debit_allocations=[("4300", Decimal("1"), "BEACH")],
        )
    db.rollback()
    with pytest.raises(services.CreditReversalError, match="رد جزء"):
        services.reverse_transaction(
            db, charge.id, branch.id, "محاولة عكس بعد المرتجع", 1,
        )


def test_closed_account_requires_zero_balance_and_duplicate_holder_is_blocked(db):
    branch, customer, beach_tx, account = _setup(db)
    services.charge_to_account(
        db, account.id, branch.id, Decimal("20"), 1, ref_beach_tx_id=beach_tx.id,
    )
    with pytest.raises(ValueError, match="رصيد"):
        services.update_account_status(db, account.id, branch.id, "closed", None, 1)
    db.rollback()
    with pytest.raises(ValueError, match="بالفعل"):
        services.open_credit_account(
            db,
            CreditAccountCreate(holder_type="customer", holder_id=customer.id),
            branch.id,
            opened_by=1,
        )


def test_owner_receivables_include_suspended_balances_without_transaction_n_plus_one(db):
    branch, _, beach_tx, account = _setup(db)
    services.charge_to_account(
        db, account.id, branch.id, Decimal("25"), 1, ref_beach_tx_id=beach_tx.id,
    )
    services.update_account_status(db, account.id, branch.id, "suspended", None, 1)
    result = services.get_credit_receivables_for_owner(db, branch.id)
    assert result.total_outstanding == Decimal("25.00")
    assert result.accounts[0].status == "suspended"


def test_account_list_is_paginated_and_reports_available_credit(db):
    branch, _, _, account = _setup(db, limit="500")
    result = services.list_accounts_for_branch(db, branch.id, page=1, size=1)
    assert result.total == 1
    assert result.items[0].id == account.id
    assert result.items[0].available_credit == Decimal("500.00")


def test_account_lock_contention_is_reported_as_retryable_conflict(db, monkeypatch):
    branch, _, beach_tx, account = _setup(db)
    from tests.conftest import make_lock_not_available_error

    def locked(*_args, **_kwargs):
        raise make_lock_not_available_error()

    monkeypatch.setattr(crud, "lock_account", locked)
    with pytest.raises(services.CreditConcurrencyError):
        services.charge_to_account(
            db, account.id, branch.id, Decimal("10"), 1,
            ref_beach_tx_id=beach_tx.id,
        )


def test_unrelated_database_failure_is_not_hidden_as_lock_conflict(db, monkeypatch):
    branch, _, beach_tx, account = _setup(db)
    from sqlalchemy.exc import OperationalError
    from tests.conftest import make_unrelated_operational_error

    def database_failure(*_args, **_kwargs):
        raise make_unrelated_operational_error()

    monkeypatch.setattr(crud, "lock_account", database_failure)
    with pytest.raises(OperationalError):
        services.charge_to_account(
            db, account.id, branch.id, Decimal("10"), 1,
            ref_beach_tx_id=beach_tx.id,
        )


def test_beach_credit_sale_and_void_are_atomic_without_cash_artifacts(db):
    branch, customer, _, account = _setup(db)
    from app.modules.beach import services as beach_services
    from app.modules.beach.schemas import BeachSellRequest
    from app.modules.finance.models import Payment

    sale = beach_services.sell_ticket(
        db,
        branch.id,
        BeachSellRequest(
            tx_type="entry",
            quantity=1,
            cashier_id=1,
            customer_id=customer.id,
            payment_method="credit_account",
            local_id=f"credit-beach-{uuid.uuid4().hex}",
        ),
        acting_user_level=60,
    )

    charge = db.query(CreditTransaction).filter_by(ref_beach_tx_id=sale.id).one()
    assert sale.vat_amount == Decimal("0.00")
    expected = (sale.total_amount + sale.vat_amount).quantize(Decimal("0.01"))
    assert charge.amount == expected
    assert charge.balance_delta == expected
    assert crud.get_account(db, account.id).current_balance == expected
    assert db.query(Payment).filter_by(source="beach", branch_id=branch.id).count() == 0
    lines = _journal_lines(db, charge.journal_entry_id)
    assert sum((row.debit for row in lines), Decimal("0")) == expected
    assert sum((row.credit for row in lines), Decimal("0")) == expected

    voided = beach_services.void_transaction(
        db, sale.id, voided_by=1, reason="إلغاء التذكرة الآجلة",
    )
    assert voided.voided_at is not None
    reversal = crud.get_reversal_for_transaction(db, charge.id)
    assert reversal is not None
    assert reversal.balance_delta == -expected
    assert crud.get_account(db, account.id).current_balance == Decimal("0.00")
    assert crud.compute_balance_from_transactions(db, account.id) == Decimal("0.00")
    assert db.query(Payment).filter_by(source="beach", branch_id=branch.id).count() == 0


def test_beach_credit_sale_rolls_back_capacity_and_ticket_when_gl_is_missing(db):
    branch, customer, _, account = _setup(db)
    from app.modules.beach import services as beach_services
    from app.modules.beach.models import BeachInventory, BeachTransaction
    from app.modules.beach.schemas import BeachSellRequest
    from app.modules.finance.models import Account
    from app.modules.finance.services import FinancialConfigurationError

    revenue = db.query(Account).filter_by(branch_id=branch.id, code="4300").one()
    revenue.is_active = False
    db.commit()
    existing_tickets = db.query(BeachTransaction).count()

    with pytest.raises(FinancialConfigurationError):
        beach_services.sell_ticket(
            db,
            branch.id,
            BeachSellRequest(
                tx_type="entry",
                quantity=2,
                cashier_id=1,
                customer_id=customer.id,
                payment_method="credit_account",
            ),
            acting_user_level=60,
        )

    assert db.query(BeachTransaction).count() == existing_tickets
    assert db.query(CreditTransaction).filter_by(credit_account_id=account.id).count() == 0
    assert crud.get_account(db, account.id).current_balance == Decimal("0.00")
    inventory = db.query(BeachInventory).filter_by(branch_id=branch.id).first()
    assert inventory is None or inventory.capacity_used == 0


def test_dining_credit_settlement_is_atomic_and_idempotent(db):
    from app.modules.crm.models import Customer
    from app.modules.dining import services as dining_services
    from app.modules.finance.models import Account, Payment
    from app.modules.finance import crud as finance_crud
    from tests.test_api.test_dining import (
        make_branch, make_finance_accounts, make_item, make_order, make_outlet,
    )

    branch = make_branch(db)
    outlet = make_outlet(db, branch)
    make_finance_accounts(db, branch)
    db.add(Account(
        branch_id=branch.id, code="1160", name="Personal receivables", account_type="asset",
    ))
    customer = Customer(branch_id=branch.id, full_name="عميل دايننج آجل")
    db.add(customer)
    db.commit()
    account = services.open_credit_account(
        db,
        CreditAccountCreate(
            holder_type="customer", holder_id=customer.id, credit_limit=Decimal("500"),
        ),
        branch.id,
        opened_by=1,
    )
    item = make_item(db, branch, outlet)
    order = make_order(db, branch, outlet, item)
    order.customer_id = customer.id
    db.commit()
    # ref_order_id متعدد المصادر: دفعة إيجار تحمل نفس الرقم لا يجوز أن
    # تُحسب tender للدايننج أو تُعكس مع مرتجع الصنف.
    finance_crud.create_direct_payment(
        db,
        branch_id=branch.id,
        amount=Decimal("1.00"),
        method="bank_transfer",
        posted_at=datetime(2026, 8, 1),
        reference=f"UNRELATED-{order.id}",
        ref_order_id=order.id,
        source="leasing_rent",
    )
    db.commit()
    key = f"dining-credit-{uuid.uuid4().hex}"

    paid = dining_services.settle_order(
        db,
        order.id,
        tenders=[{"method": "credit_account", "amount": None}],
        settled_by=1,
        acting_user_level=60,
        idempotency_key=key,
    )
    replay = dining_services.settle_order(
        db,
        order.id,
        tenders=[{"method": "credit_account", "amount": None}],
        settled_by=1,
        acting_user_level=60,
        idempotency_key=key,
    )

    charge = db.query(CreditTransaction).filter_by(ref_order_id=order.id).one()
    assert paid.status == replay.status == "paid"
    assert charge.amount == paid.total
    assert crud.get_account(db, account.id).current_balance == paid.total
    assert db.query(Payment).filter(
        Payment.ref_order_id == order.id, Payment.source == "dining",
    ).count() == 0

    refunded = dining_services.refund_order_item(
        db, order.id, paid.items[0].id, "مرتجع طلب آجل", refunded_by=1,
    )
    refund = db.query(CreditTransaction).filter_by(
        reversed_txn_id=charge.id, txn_type="refund",
    ).one()
    assert refunded.status == "refunded"
    assert refund.amount == paid.total
    assert crud.get_account(db, account.id).current_balance == Decimal("0.00")
    assert crud.compute_balance_from_transactions(db, account.id) == Decimal("0.00")
    assert db.query(Payment).filter(
        Payment.ref_order_id == order.id, Payment.source == "dining",
    ).count() == 0


def test_split_dining_refunds_use_cumulative_credit_rounding_target(db):
    from app.modules.crm.models import Customer
    from app.modules.dining import services as dining_services
    from app.modules.dining.schemas import OrderCreate, OrderItemCreate
    from app.modules.finance import services as finance_services
    from app.modules.finance.models import Account
    from app.modules.finance.schemas import CashierShiftOpen
    from tests.test_api.test_dining import (
        make_branch, make_finance_accounts, make_item, make_outlet,
    )

    branch = make_branch(db)
    outlet = make_outlet(db, branch)
    make_finance_accounts(db, branch)
    db.add(Account(
        branch_id=branch.id, code="1160", name="Personal receivables",
        account_type="asset",
    ))
    customer = Customer(branch_id=branch.id, full_name="عميل تقسيم ومرتجعات")
    db.add(customer)
    db.commit()
    account = services.open_credit_account(
        db,
        CreditAccountCreate(
            holder_type="customer", holder_id=customer.id, credit_limit=Decimal("100"),
        ),
        branch.id,
        opened_by=1,
    )
    item = make_item(db, branch, outlet, price=Decimal("0.03"))
    order = dining_services.create_order(
        db,
        branch.id,
        OrderCreate(
            outlet_id=outlet.id,
            order_type="takeaway",
            customer_id=customer.id,
            items=[OrderItemCreate(item_id=item.id, quantity=1) for _ in range(3)],
        ),
        waiter_id=1,
    )
    credit_amount = (order.total / Decimal("2")).quantize(Decimal("0.01"))
    cash_amount = order.total - credit_amount
    finance_services.open_shift(
        db,
        cashier_id=1,
        opened_by=1,
        data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
    )
    paid = dining_services.settle_order(
        db,
        order.id,
        tenders=[
            {"method": "credit_account", "amount": credit_amount},
            {"method": "cash", "amount": cash_amount},
        ],
        settled_by=1,
        acting_user_level=60,
        idempotency_key=f"split-rounding-{uuid.uuid4().hex}",
    )
    charge = db.query(CreditTransaction).filter_by(ref_order_id=order.id).one()

    for line_id in [line.id for line in paid.items]:
        dining_services.refund_order_item(
            db, order.id, line_id, "اختبار تقريب مرتجع split", refunded_by=1,
        )

    refunds = db.query(CreditTransaction).filter_by(
        reversed_txn_id=charge.id, txn_type="refund",
    ).all()
    assert len(refunds) == 3
    assert sum((refund.amount for refund in refunds), Decimal("0")) == charge.amount
    assert crud.get_account(db, account.id).current_balance == Decimal("0.00")
    assert crud.compute_balance_from_transactions(db, account.id) == Decimal("0.00")


def test_employee_credit_account_can_pay_dining_and_beach_sources(db):
    from app.modules.beach import services as beach_services
    from app.modules.beach.schemas import BeachSellRequest
    from app.modules.dining import services as dining_services
    from app.modules.finance.models import Account
    from app.modules.hr.models import Employee
    from tests.test_api.test_dining import (
        make_branch, make_finance_accounts, make_item, make_order, make_outlet,
    )

    branch = make_branch(db)
    outlet = make_outlet(db, branch)
    make_finance_accounts(db, branch)
    db.add_all([
        Account(
            branch_id=branch.id, code="1160", name="Personal receivables",
            account_type="asset",
        ),
        Account(
            branch_id=branch.id, code="4300", name="Beach revenue",
            account_type="revenue",
        ),
    ])
    employee = Employee(
        branch_id=branch.id,
        employee_code=f"CR-{uuid.uuid4().hex[:8]}",
        full_name="موظف حساب آجل",
        position="staff",
        department="Operations",
        basic_salary=Decimal("5000"),
        hire_date=date.today(),
    )
    db.add(employee)
    db.commit()
    account = services.open_credit_account(
        db,
        CreditAccountCreate(
            holder_type="employee", holder_id=employee.id, credit_limit=Decimal("1000"),
        ),
        branch.id,
        opened_by=1,
    )
    item = make_item(db, branch, outlet)
    order = make_order(db, branch, outlet, item, quantity=1)

    dining_services.settle_order(
        db,
        order.id,
        tenders=[{
            "method": "credit_account", "amount": None,
            "credit_account_id": account.id,
        }],
        settled_by=1,
        acting_user_level=60,
        idempotency_key=f"employee-dining-{uuid.uuid4().hex}",
    )
    beach_sale = beach_services.sell_ticket(
        db,
        branch.id,
        BeachSellRequest(
            tx_type="entry_child",
            quantity=1,
            cashier_id=1,
            payment_method="credit_account",
            credit_account_id=account.id,
        ),
        acting_user_level=60,
    )

    dining_charge = db.query(CreditTransaction).filter_by(ref_order_id=order.id).one()
    beach_charge = db.query(CreditTransaction).filter_by(ref_beach_tx_id=beach_sale.id).one()
    expected = dining_charge.amount + beach_charge.amount
    assert crud.get_account(db, account.id).current_balance == expected
    assert crud.compute_balance_from_transactions(db, account.id) == expected


@pytest.mark.parametrize("role", ["owner", "hr_manager", "cashier"])
def test_non_financial_roles_cannot_list_credit_accounts(client, db, role):
    from tests.conftest import _create_test_user, _make_token, assign_test_user_to_branch
    from app.modules.core.models import Branch

    suffix = uuid.uuid4().hex[:8]
    branch = Branch(name=f"Auth {suffix}", name_ar="فرع صلاحيات", code=f"AU-{suffix}")
    db.add(branch)
    db.commit()
    email = f"credit-{role}-{uuid.uuid4().hex[:8]}@test.local"
    user_id = _create_test_user(email, role, two_factor_enabled=(role == "owner"))
    assign_test_user_to_branch(db, user_id, branch.id)
    response = client.get(
        "/api/v1/credit/accounts",
        headers={"Authorization": f"Bearer {_make_token(email, branch_id=branch.id)}"},
    )

    assert response.status_code == 403
    assert "no-store" in response.headers["cache-control"]


def test_cashier_lookup_is_read_only_and_never_exposes_cross_branch_data(client, db):
    branch, customer, _, _ = _setup(db)
    from tests.conftest import _create_test_user, _make_token, assign_test_user_to_branch

    other_suffix = uuid.uuid4().hex[:8]
    from app.modules.core.models import Branch
    other_branch = Branch(
        name=f"Other {other_suffix}", name_ar="فرع آخر", code=f"OT-{other_suffix}",
    )
    db.add(other_branch)
    db.commit()
    email = f"credit-cashier-{uuid.uuid4().hex[:8]}@test.local"
    user_id = _create_test_user(email, "cashier")
    assign_test_user_to_branch(db, user_id, other_branch.id)
    headers = {"Authorization": f"Bearer {_make_token(email, branch_id=other_branch.id)}"}

    lookup = client.get(
        "/api/v1/credit/accounts/lookup",
        params={"holder_type": "customer", "holder_id": customer.id},
        headers=headers,
    )
    create = client.post(
        "/api/v1/credit/accounts",
        json={"holder_type": "customer", "holder_id": customer.id},
        headers=headers,
    )

    assert lookup.status_code == 200 and lookup.json() is None
    assert create.status_code == 403
    assert "no-store" in lookup.headers["cache-control"]
    assert "no-store" in create.headers["cache-control"]
