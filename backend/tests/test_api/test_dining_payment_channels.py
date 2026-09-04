"""
tests/test_api/test_dining_payment_channels.py
Dining × PaymentChannel integration: single-tender and split-bill channel
selection, historical snapshot in tender_breakdown, and legacy fallback for
branches with no configured channels.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.dining import services
from app.modules.finance import services as finance_services
from app.modules.finance.schemas import PaymentChannelCreate
from tests.conftest import open_cashier_shift
from tests.test_api.test_dining import (
    make_branch, make_finance_accounts, make_item, make_order, make_outlet,
)


def get_account(db, branch, code):
    from app.modules.finance.models import Account
    return db.query(Account).filter(Account.branch_id == branch.id, Account.code == code).first()


def make_card_account(db, branch):
    from app.modules.finance.models import Account
    existing = get_account(db, branch, "1120")
    if existing:
        return existing
    acc = Account(branch_id=branch.id, code="1120", name="Card Clearing", account_type="asset")
    db.add(acc)
    db.commit()
    return acc


class TestDiningSingleTenderChannel:
    def test_single_payment_with_explicit_channel_snapshots_it(self, db):
        branch = make_branch(db)
        make_finance_accounts(db, branch)
        card_gl = make_card_account(db, branch)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item)
        cashier_id = 501
        open_cashier_shift(db, branch.id, cashier_id)

        channel = finance_services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="VISA-D", name="Visa", method="card",
            gl_account_id=card_gl.id,
        ))

        updated = services.update_order_status(
            db, order.id, "paid",
            payment_method="card", payment_channel_id=channel.id,
            settled_by=cashier_id,
        )
        assert updated.status == "paid"

        from app.modules.dining.crud import get_settlement_by_order
        settlement = get_settlement_by_order(db, order.id)
        assert settlement is not None
        assert settlement.tender_breakdown[0]["payment_channel_id"] == channel.id
        assert settlement.tender_breakdown[0]["payment_channel_code"] == "VISA-D"

        from app.modules.finance import crud as finance_crud
        payment = finance_crud.get_direct_payment_by_reference(db, branch.id, f"ORD-{order.order_number}")
        assert payment is not None
        assert payment.payment_channel_id == channel.id
        assert payment.settlement_account_code == "1120"

    def test_single_payment_without_channels_configured_falls_back(self, db):
        branch = make_branch(db)
        make_finance_accounts(db, branch)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        order = make_order(db, branch, outlet, item)
        cashier_id = 502
        open_cashier_shift(db, branch.id, cashier_id)

        updated = services.update_order_status(
            db, order.id, "paid", payment_method="cash", settled_by=cashier_id,
        )
        assert updated.status == "paid"

        from app.modules.finance import crud as finance_crud
        payment = finance_crud.get_direct_payment_by_reference(db, branch.id, f"ORD-{order.order_number}")
        assert payment.payment_channel_id is None
        assert payment.settlement_account_code is None  # legacy — resolve_direct_tender_account("cash")


class TestDiningSplitBillChannels:
    def test_split_bill_rows_can_use_different_channels(self, db):
        branch = make_branch(db)
        make_finance_accounts(db, branch)
        cash_gl = get_account(db, branch, "1100")
        card_gl = make_card_account(db, branch)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, price=Decimal("100.00"))
        order = make_order(db, branch, outlet, item, quantity=1)
        cashier_id = 503
        open_cashier_shift(db, branch.id, cashier_id)

        cash_channel = finance_services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-SPLIT", name="Cash", method="cash", gl_account_id=cash_gl.id,
        ))
        card_channel = finance_services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CARD-SPLIT", name="Card", method="card", gl_account_id=card_gl.id,
        ))

        # order.total شامل VAT/service — نقسم نص/نص من غير ما نفترض قيمة ثابتة
        db.refresh(order)
        half = (order.total / 2).quantize(Decimal("0.01"))
        remainder = order.total - half

        updated = services.split_bill(
            db, order.id,
            payments=[
                {"payment_method": "cash", "amount": str(half), "payment_channel_id": cash_channel.id},
                {"payment_method": "card", "amount": str(remainder), "payment_channel_id": card_channel.id},
            ],
            settled_by=cashier_id,
        )
        assert updated.status == "paid"

        from app.modules.dining.crud import get_settlement_by_order
        settlement = get_settlement_by_order(db, order.id)
        by_method = {t["method"]: t for t in settlement.tender_breakdown}
        assert by_method["cash"]["payment_channel_code"] == "CASH-SPLIT"
        assert by_method["card"]["payment_channel_code"] == "CARD-SPLIT"

        from app.modules.finance.models import Payment
        payments = db.query(Payment).filter(
            Payment.branch_id == branch.id, Payment.ref_order_id == order.id,
        ).all()
        codes = {p.method: p.settlement_account_code for p in payments}
        assert codes["cash"] == "1100"
        assert codes["card"] == "1120"
