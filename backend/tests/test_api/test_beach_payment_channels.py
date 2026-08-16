"""
tests/test_api/test_beach_payment_channels.py
Beach × PaymentChannel integration: channel resolution, historical snapshot
on BeachTransaction/Payment, void reversal against the original settlement
account (not a hardcoded 1100), the atomic multi-item cart endpoint
(sell_cart), and the shift-open guard on direct tenders.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.modules.beach import crud, services
from app.modules.beach.schemas import BeachCartLineItem, BeachCartSellRequest, BeachSellRequest
from app.modules.finance import services as finance_services
from app.modules.finance.schemas import PaymentChannelCreate


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name=f"PayChan Beach {uuid.uuid4().hex[:6]}", name_ar="شاطئ",
               code=f"PCB-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    make_finance_accounts(db, b)
    return b


def make_finance_accounts(db, branch):
    from app.modules.finance.models import Account
    existing = {a.code for a in db.query(Account).filter(Account.branch_id == branch.id).all()}
    wanted = [
        ("1100", "Cash", "asset"),
        ("1120", "Card Clearing", "asset"),
        ("4300", "Beach Revenue", "revenue"),
        ("1150", "ذمم الفوليو", "asset"),
    ]
    added = [Account(branch_id=branch.id, code=c, name=n, account_type=t)
             for c, n, t in wanted if c not in existing]
    if added:
        db.add_all(added)
        db.commit()


def get_account(db, branch, code):
    from app.modules.finance.models import Account
    return db.query(Account).filter(Account.branch_id == branch.id, Account.code == code).first()


def make_cashier(db, branch):
    from app.modules.core.models import UserBranchMembership
    from app.modules.hr.models import Employee
    from tests.conftest import _create_test_user

    email = f"cashier-{uuid.uuid4().hex[:10]}@test.local"
    user_id = _create_test_user(email, "cashier")
    db.add_all([
        Employee(
            branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
            full_name="كاشير اختبار", national_id=f"2900101{uuid.uuid4().hex[:7]}",
            position="Cashier", department="Beach", basic_salary=Decimal("4000.00"),
            hire_date=date.today() - timedelta(days=365), user_id=user_id,
        ),
        UserBranchMembership(user_id=user_id, branch_id=branch.id, is_default=True, is_active=True),
    ])
    db.commit()
    return user_id


def open_shift(db, branch, cashier_id):
    from tests.conftest import open_cashier_shift
    return open_cashier_shift(db, branch.id, cashier_id)


class TestBeachPaymentChannelSnapshot:
    def test_sell_with_explicit_channel_snapshots_settlement_account(self, db):
        branch = make_branch(db)
        cashier_id = make_cashier(db, branch)
        open_shift(db, branch, cashier_id)
        card_gl = get_account(db, branch, "1120")
        channel = finance_services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="VISA-CIB", name="Visa CIB", name_ar="فيزا CIB",
            method="card", gl_account_id=card_gl.id,
        ))

        tx = services.sell_ticket(db, branch.id, BeachSellRequest(
            tx_type="entry", quantity=1, cashier_id=cashier_id,
            payment_method="card", payment_channel_id=channel.id,
        ))

        assert tx.payment_channel_id == channel.id
        assert tx.payment_channel_code == "VISA-CIB"
        assert tx.settlement_account_code == "1120"

        from app.modules.finance import crud as finance_crud
        payment = finance_crud.get_direct_payment_by_reference(db, branch.id, f"BCH-{tx.id:06d}")
        assert payment is not None
        assert payment.payment_channel_id == channel.id
        assert payment.settlement_account_code == "1120"

    def test_sell_without_channel_id_uses_default(self, db):
        branch = make_branch(db)
        cashier_id = make_cashier(db, branch)
        open_shift(db, branch, cashier_id)
        cash_gl = get_account(db, branch, "1100")
        default_channel = finance_services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-DEFAULT", name="Cash", method="cash",
            gl_account_id=cash_gl.id, is_default=True,
        ))

        tx = services.sell_ticket(db, branch.id, BeachSellRequest(
            tx_type="entry", quantity=1, cashier_id=cashier_id, payment_method="cash",
        ))
        assert tx.payment_channel_id == default_channel.id
        assert tx.settlement_account_code == "1100"

    def test_sell_with_no_channels_configured_falls_back_to_legacy(self, db):
        """فرع بلا أي payment_channels — يفضل يشتغل زي الأول (fallback env
        القديم)، بلا لقطة قناة."""
        branch = make_branch(db)
        cashier_id = make_cashier(db, branch)
        open_shift(db, branch, cashier_id)

        tx = services.sell_ticket(db, branch.id, BeachSellRequest(
            tx_type="entry", quantity=1, cashier_id=cashier_id, payment_method="cash",
        ))
        # مفيش قناة تتلقّط — اللقطة فاضية بالكامل، لكن القيد المحاسبي والإلغاء
        # لاحقًا لسه بيستخدموا نفس resolve_direct_tender_account("cash") = "1100".
        assert tx.payment_channel_id is None
        assert tx.settlement_account_code is None
        from app.modules.finance.models import JournalLine
        line = db.query(JournalLine).filter(JournalLine.account_id == get_account(db, branch, "1100").id).first()
        assert line is not None and line.debit == tx.total_amount

    def test_channel_change_after_sale_does_not_alter_historical_snapshot(self, db):
        branch = make_branch(db)
        cashier_id = make_cashier(db, branch)
        open_shift(db, branch, cashier_id)
        cash_gl = get_account(db, branch, "1100")
        channel = finance_services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-X", name="Cash X", method="cash",
            gl_account_id=cash_gl.id, is_default=True,
        ))
        tx = services.sell_ticket(db, branch.id, BeachSellRequest(
            tx_type="entry", quantity=1, cashier_id=cashier_id, payment_method="cash",
        ))
        assert tx.settlement_account_code == "1100"

        from app.modules.finance.schemas import PaymentChannelUpdate
        finance_services.update_payment_channel(db, channel.id, PaymentChannelUpdate(name="Renamed Cash"))

        db.refresh(tx)
        assert tx.payment_channel_name == "Cash X"  # لقطة قديمة، مش الاسم الجديد
        assert tx.settlement_account_code == "1100"


class TestBeachVoidUsesOriginalSettlementAccount:
    def test_void_reverses_to_snapshot_account_not_hardcoded_cash(self, db):
        """باج حقيقي كان موجود: الإلغاء كان بيرجع دايمًا لحساب 1100 (كاش)
        حتى لو البيع الأصلي كان بالكارت — دلوقتي لازم يرجع لنفس حساب
        الاستلام الأصلي (1120 هنا) بدل الكاش."""
        branch = make_branch(db)
        cashier_id = make_cashier(db, branch)
        open_shift(db, branch, cashier_id)
        card_gl = get_account(db, branch, "1120")
        channel = finance_services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="VISA-VOID", name="Visa", method="card",
            gl_account_id=card_gl.id,
        ))
        tx = services.sell_ticket(db, branch.id, BeachSellRequest(
            tx_type="entry", quantity=1, cashier_id=cashier_id,
            payment_method="card", payment_channel_id=channel.id,
        ))
        assert tx.settlement_account_code == "1120"

        services.void_transaction(db, tx.id, voided_by=cashier_id, reason="اختبار الإلغاء")

        from app.modules.finance.models import JournalEntry, JournalLine
        entries = (
            db.query(JournalEntry)
            .filter(JournalEntry.branch_id == branch.id, JournalEntry.reference == f"BCH-VOID-{tx.id:06d}")
            .all()
        )
        assert len(entries) == 1
        lines = db.query(JournalLine).filter(JournalLine.entry_id == entries[0].id).all()
        card_line = next(l for l in lines if l.account_id == card_gl.id)
        cash_gl = get_account(db, branch, "1100")
        # مفيش أي سطر بيلمس حساب الكاش أصلاً — الإلغاء رجع لحساب الكارت بس
        assert not any(l.account_id == cash_gl.id for l in lines)
        assert card_line.credit > 0  # عكس المدين الأصلي (استلام الكارت) بائتمان


class TestBeachSellCartAtomicity:
    def test_cart_creates_all_items_in_one_transaction(self, db):
        branch = make_branch(db)
        cashier_id = make_cashier(db, branch)
        open_shift(db, branch, cashier_id)

        cart = BeachCartSellRequest(
            items=[
                BeachCartLineItem(tx_type="entry", quantity=2),
                BeachCartLineItem(tx_type="towel_rent", quantity=2),
            ],
            cashier_id=cashier_id, payment_method="cash",
        )
        transactions = services.sell_cart(db, branch.id, cart)
        assert len(transactions) == 2
        assert {t.tx_type for t in transactions} == {"entry", "towel_rent"}

        inv = crud.get_or_create_inventory(db, branch.id, date.today())
        db.commit()
        assert inv.capacity_used == 2
        assert inv.towels_used == 2

    def test_cart_retry_with_same_cart_local_id_is_idempotent(self, db):
        branch = make_branch(db)
        cashier_id = make_cashier(db, branch)
        open_shift(db, branch, cashier_id)
        cart_local_id = str(uuid.uuid4())

        cart = BeachCartSellRequest(
            items=[BeachCartLineItem(tx_type="entry", quantity=1)],
            cashier_id=cashier_id, payment_method="cash", cart_local_id=cart_local_id,
        )
        first = services.sell_cart(db, branch.id, cart)
        second = services.sell_cart(db, branch.id, cart)
        assert [t.id for t in first] == [t.id for t in second]

        inv = crud.get_or_create_inventory(db, branch.id, date.today())
        db.commit()
        assert inv.capacity_used == 1  # لا خصم مزدوج

    def test_cart_partial_failure_rolls_back_entirely(self, db):
        """صنف تاني في السلة بيتخطى السعة المتاحة — لازم الصنف الأول (اللي
        كان هينجح لوحده) يترد بالكامل برضو، مفيش بيع جزئي."""
        branch = make_branch(db)
        cashier_id = make_cashier(db, branch)
        open_shift(db, branch, cashier_id)
        crud.get_or_create_inventory(db, branch.id, date.today(), capacity_max=1)
        db.commit()

        cart = BeachCartSellRequest(
            items=[
                BeachCartLineItem(tx_type="entry", quantity=1),
                BeachCartLineItem(tx_type="entry", quantity=1),  # ده هيفشل — السعة خلصت
            ],
            cashier_id=cashier_id, payment_method="cash",
        )
        with pytest.raises(ValueError, match="ممتلئ"):
            services.sell_cart(db, branch.id, cart)

        # صفر تذاكر اتسجّلت — الصنف الأول اللي كان هينجح لوحده اترد كمان
        tx_count = crud.list_transactions(db, branch.id, date.today())[1]
        assert tx_count == 0
        inv = crud.get_or_create_inventory(db, branch.id, date.today())
        db.commit()
        assert inv.capacity_used == 0

    def test_cart_requires_open_shift_for_direct_tender(self, db):
        branch = make_branch(db)
        cashier_id = make_cashier(db, branch)  # لا وردية مفتوحة

        cart = BeachCartSellRequest(
            items=[BeachCartLineItem(tx_type="entry", quantity=1)],
            cashier_id=cashier_id, payment_method="cash",
        )
        with pytest.raises(services.NoOpenShiftError):
            services.sell_cart(db, branch.id, cart)


class TestBeachInventoryRowRace:
    def test_get_or_create_inventory_survives_concurrent_first_insert(self, db, monkeypatch):
        """باج حقيقي اتصلح: أول بيعتين في نفس اليوم بالظبط كانوا ممكن الاتنين
        يقروا row=None، فالتاني يرمي IntegrityError خام (500) بدل ما يرجّع
        صف اليوم اللي اتعمل بالفعل من الأولى. بنحاكي السباق بمونكي باتش
        get_inventory عشان يرجّع None *مرة واحدة* حتى لو الصف اتعمل فعليًا
        قبل ما الـinsert التاني يوصل — نفس شكل TOCTOU حقيقي."""
        branch = make_branch(db)
        real_get_inventory = crud.get_inventory
        call_count = {"n": 0}

        def flaky_get_inventory(db_, branch_id, inv_date):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # أول قراءة — تحاكي إن الصف لسه معمول
            return real_get_inventory(db_, branch_id, inv_date)

        # صف حقيقي موجود بالفعل (زي لو عملية تانية سبقت بالميلي ثانية)
        real_get_inventory(db, branch.id, date.today())  # no-op query
        crud.get_or_create_inventory(db, branch.id, date.today(), capacity_max=200)
        db.commit()

        monkeypatch.setattr(crud, "get_inventory", flaky_get_inventory)
        # النداء ده هيحاول يعمل INSERT تاني لصف موجود بالفعل — المفروض
        # يترجم لـIntegrityError ممسوكة، مش استثناء خام يوصل للراوتر.
        row = crud.get_or_create_inventory(db, branch.id, date.today(), capacity_max=200)
        assert row.branch_id == branch.id
        assert row.capacity_max == 200

        # الجلسة لسه صالحة للاستخدام بعد كده (مفيش transaction متعطّلة)
        db.commit()
        count = db.query(crud.BeachInventory).filter(
            crud.BeachInventory.branch_id == branch.id,
        ).count()
        assert count == 1  # صف واحد بس، مش تكرار


class TestShiftReportChannelBreakdown:
    def test_shift_report_groups_sales_by_channel(self, db):
        from app.modules.finance import services as finance_services

        branch = make_branch(db)
        cashier_id = make_cashier(db, branch)
        open_shift(db, branch, cashier_id)
        card_gl = get_account(db, branch, "1120")
        card_channel = finance_services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CARD-SHIFT", name="Card", method="card", gl_account_id=card_gl.id,
        ))

        services.sell_ticket(db, branch.id, BeachSellRequest(
            tx_type="entry", quantity=1, cashier_id=cashier_id, payment_method="cash",
        ))
        services.sell_ticket(db, branch.id, BeachSellRequest(
            tx_type="entry", quantity=1, cashier_id=cashier_id,
            payment_method="card", payment_channel_id=card_channel.id,
        ))

        from app.modules.finance import crud as finance_crud
        shift = finance_crud.get_open_shift(db, branch.id, cashier_id)
        report = finance_services.build_shift_end_report(db, shift.id)

        by_code = {c.payment_channel_code: c for c in report.channel_breakdown}
        assert "CARD-SHIFT" in by_code
        assert by_code["CARD-SHIFT"].count == 1
        # بيع كاش legacy (بلا قناة) لسه بيظهر تحت الطريقة الخام، مش بيختفي
        assert "cash" in {c.label for c in report.channel_breakdown}
