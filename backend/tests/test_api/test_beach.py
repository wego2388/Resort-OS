"""
tests/test_api/test_beach.py
Integration tests for beach module — sell tickets, B2B, reservations, surge.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.modules.beach import crud, services
from app.modules.beach.schemas import (
    B2BCheckinRequest,
    B2BContractCreate,
    BeachLocationCheckinRequest,
    BeachReservationCreate,
    BeachSellRequest,
)


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"Beach Branch {uuid.uuid4().hex[:6]}",
        name_ar="شاطئ",
        code=f"BCH-{uuid.uuid4().hex[:8].upper()}",
    )
    db.add(b)
    db.commit()
    return b


def make_branch_linked_cashier(db, branch):
    """Gate 1 containment (جولة مراجعة Codex الثالثة): check_in_reservation
    بقى بيطلب requesting_user حقيقي دايمًا (اتشال internal_call — مفيش أي
    caller إنتاجي حقيقي كان محتاجه، كان بس باب اختبارات). تستات الوحدة هنا
    لازم تستخدم كاشير حقيقي مرتبط بالفرع بدل أي bypass، حتى وهي بتختبر
    قواعد تجارية تانية غير الصلاحيات نفسها."""
    from app.core.kernel.models.user import User
    from app.modules.hr.models import Employee
    from tests.conftest import _create_test_user

    email = f"cashier-{uuid.uuid4().hex[:10]}@test.local"
    user_id = _create_test_user(email, "cashier")
    user = db.query(User).get(user_id)
    emp = Employee(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name="كاشير اختبار الوحدة", position="Cashier", department="Beach",
        basic_salary=Decimal("4000.00"), hire_date=date.today() - timedelta(days=365),
        user_id=user_id,
    )
    db.add(emp)
    db.commit()
    db.refresh(user)
    return user


def make_contract(
    db, branch, quota=10, entry_price=Decimal("80"), towel_price=Decimal("30"),
    valid_from=None, valid_until=None, is_active=True,
    credit_limit=None, payment_terms_days=30,
):
    today = date.today()
    data = B2BContractCreate(
        branch_id=branch.id,
        hotel_name=f"Hotel {uuid.uuid4().hex[:6]}",
        daily_quota=quota,
        entry_price=entry_price,
        towel_price=towel_price,
        valid_from=valid_from or (today - timedelta(days=1)),
        valid_until=valid_until or (today + timedelta(days=30)),
        is_active=is_active,
        credit_limit=credit_limit,
        payment_terms_days=payment_terms_days,
    )
    obj = crud.create_b2b_contract(db, data)
    db.commit()
    return obj


class TestBeachInventory:

    def test_get_or_create_inventory(self, db):
        branch = make_branch(db)
        inv = crud.get_or_create_inventory(db, branch.id, date.today())
        db.commit()
        assert inv.id is not None
        assert inv.capacity_max == 200
        assert inv.towels_available == 200

    def test_idempotent_inventory_creation(self, db):
        branch = make_branch(db)
        today = date.today()
        inv1 = crud.get_or_create_inventory(db, branch.id, today)
        db.commit()
        inv2 = crud.get_or_create_inventory(db, branch.id, today)
        db.commit()
        assert inv1.id == inv2.id

    def test_auto_surge_at_80_pct(self, db):
        branch = make_branch(db)
        today = date.today()
        inv = crud.get_or_create_inventory(db, branch.id, today, capacity_max=10, towels_total=20)
        # فعّل capacity_used إلى 8 (80%)
        inv.capacity_used = 8
        db.flush()
        # استهلك مقعداً واحداً آخر — يجب أن يُفعَّل surge تلقائياً
        crud.apply_inventory_delta(db, inv, capacity_delta=-1, towel_delta=0)
        db.commit()
        assert inv.surge_pct > 0

    def test_no_surge_below_80_pct(self, db):
        branch = make_branch(db)
        today = date.today()
        inv = crud.get_or_create_inventory(db, branch.id, today, capacity_max=10, towels_total=20)
        inv.capacity_used = 5
        db.flush()
        crud.apply_inventory_delta(db, inv, capacity_delta=-1, towel_delta=0)
        db.commit()
        assert inv.surge_pct == Decimal("0")


class TestSellTicket:

    def test_sell_adult_entry(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.id is not None
        assert tx.tx_type == "entry"
        assert tx.quantity == 1
        assert tx.unit_price > 0
        assert tx.total_amount > 0

    def test_sell_uses_branch_configured_price_not_hardcoded_default(self, db):
        """باج حقيقي اتصلح 2026-07-03: _get_base_prices كانت بتحاول تبني
        Decimal من صف Setting كامل (ORM object) مباشرة بدل .value بتاعه —
        ده كان بيرمي استثناء دايمًا لما فيه إعداد فعلي محفوظ، والـ
        `except Exception` كان بيبلعه ويرجّع القيم الافتراضية الجاهزة
        (200/100/150/50) دايمًا. يعني أي سعر شاطئ يتظبط من الإعدادات كان
        بيتجاهل تمامًا وقت البيع الحقيقي."""
        from app.modules.core.crud import upsert_setting
        branch = make_branch(db)
        upsert_setting(db, "beach.price.adult", "999", branch_id=branch.id)
        db.commit()

        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.unit_price == Decimal("999")

    def test_sell_child_entry(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry_child", quantity=2)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.tx_type == "entry_child"
        assert tx.quantity == 2

    def test_sell_resident_entry(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry_resident", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.tx_type == "entry_resident"

    def test_sell_entry_with_towel(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry_towel", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.tx_type == "entry_towel"
        # يجب أن السعر أعلى من entry عادي
        req_entry = BeachSellRequest(tx_type="entry", quantity=1)
        tx_entry = services.sell_ticket(db, branch.id, req_entry)
        assert tx.unit_price > tx_entry.unit_price

    def test_sell_towel_rent(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="towel_rent", quantity=3)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.tx_type == "towel_rent"
        assert tx.quantity == 3

    def test_inventory_updated_after_sale(self, db):
        branch = make_branch(db)
        inv_before = crud.get_or_create_inventory(db, branch.id, date.today())
        db.commit()
        used_before = inv_before.capacity_used

        req = BeachSellRequest(tx_type="entry", quantity=2)
        services.sell_ticket(db, branch.id, req)

        db.refresh(inv_before)
        assert inv_before.capacity_used == used_before + 2

    def test_towel_inventory_decreases(self, db):
        branch = make_branch(db)
        inv = crud.get_or_create_inventory(db, branch.id, date.today())
        db.commit()
        towels_before = inv.towels_available

        req = BeachSellRequest(tx_type="entry_towel", quantity=1)
        services.sell_ticket(db, branch.id, req)

        db.refresh(inv)
        assert inv.towels_available == towels_before - 1

    def test_vat_applied(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.vat_amount >= Decimal("0")

    def test_full_capacity_raises(self, db):
        branch = make_branch(db)
        today = date.today()
        inv = crud.get_or_create_inventory(db, branch.id, today, capacity_max=2, towels_total=10)
        inv.capacity_used = 2
        db.commit()

        req = BeachSellRequest(tx_type="entry", quantity=1)
        with pytest.raises(ValueError, match="ممتلئ"):
            services.sell_ticket(db, branch.id, req, tx_date=today)

    def test_no_towels_raises(self, db):
        branch = make_branch(db)
        today = date.today()
        inv = crud.get_or_create_inventory(db, branch.id, today, capacity_max=50, towels_total=2)
        inv.towels_available = 0
        inv.towels_used = 2
        db.commit()

        req = BeachSellRequest(tx_type="entry_towel", quantity=1)
        with pytest.raises(ValueError, match="فوط"):
            services.sell_ticket(db, branch.id, req, tx_date=today)

    def test_concurrent_sale_raises_concurrency_error(self, db, monkeypatch):
        """باج حقيقي كان هنا: sell_ticket كان بيقرا/يعدّل capacity_used من غير
        أي قفل صف (عكس pms.crud.lock_room_for_booking للغرف) — تحت حمل متزامن
        حقيقي (كذا كاشير بيبيعوا في نفس اللحظة والسعة قريبة من الحد)، عمليتين
        كانوا ممكن يعدّوا validate_entry بنفس القيمة القديمة ويتسبب تجاوز
        فعلي للسعة. اتصلح بقفل صف BeachInventory (SELECT FOR UPDATE NOWAIT)
        قبل أي تحقق/تعديل — هنا بنحاكي عملية تانية ماسكة الصف بمحاكاة
        OperationalError من الـ lock نفسه."""
        from sqlalchemy.exc import OperationalError

        branch = make_branch(db)

        def _raise_locked(*_args, **_kwargs):
            raise OperationalError("SELECT ... FOR UPDATE NOWAIT", {}, Exception("could not obtain lock"))

        monkeypatch.setattr(crud, "lock_inventory_for_update", _raise_locked)

        req = BeachSellRequest(tx_type="entry", quantity=1)
        with pytest.raises(services.BeachConcurrencyError, match="مشغولة"):
            services.sell_ticket(db, branch.id, req)

    def test_lock_refreshes_stale_in_memory_capacity_not_just_db_lock(self, db):
        """باج حقيقي حي كان هنا (اتكشف بتجربة فعلية على Postgres حقيقي بعمليتين
        متزامنتين — مش النوع اللي تستات monkeypatch فوق بتغطيه، لأن تستات
        الوحدة شغالة على SQLite واللي أصلاً بيتجاهل with_for_update):
        sell_ticket بيعمل قراءة أولى غير مقفولة (get_or_create_inventory) قبل
        القفل، فالصف بيتسجّل في identity map الخاصة بالـ Session بقيمته
        وقتها. لما القفل نفسه يتاخد بعد كده (lock_inventory_for_update)،
        SQLAlchemy من غير .populate_existing() مكانش بيحدّث الـ object
        الموجود بالفعل في identity map من نتيجة استعلام القفل الجديد — فلو
        Session تانية كانت خلصت وعدّلت الصف فعليًا في اللحظة بين القراءتين،
        الكود بيكمل بقيمة capacity_used **قديمة** رغم إن القفل نفسه اتاخد
        بنجاح. النتيجة الفعلية اللي لوحظت لايف: عمليتا بيع ناجحتين (201/201،
        تذكرتين حقيقيتين) بس capacity_used اتزاد مرة واحدة بس (lost update) —
        سعة الشاطئ المسجّلة تفضل أقل من العدد الحقيقي اللي دخل فعلاً.

        هنا بنحاكي نفس السيناريو بالظبط بجلستين حقيقيتين منفصلتين (نفس الـ
        StaticPool engine المشترك في conftest، فالاتنين بيشوفوا نفس الصفوف
        المُلتزَمة فعليًا زي عمليتين حقيقيتين على Postgres)، من غير الحاجة
        لقفل صف حقيقي متزامن (SQLite بيتجاهله على أي حال) — المهم هنا إثبات
        إن القراءة بعد القفل بترجّع القيمة الحالية الصحيحة، مش القديمة."""
        from tests.conftest import TestingSessionLocal

        branch = make_branch(db)
        dbA = TestingSessionLocal()
        dbB = TestingSessionLocal()
        try:
            today = date.today()
            inv_seed = crud.get_or_create_inventory(dbA, branch.id, today, capacity_max=200)
            inv_seed.capacity_used = 195
            dbA.commit()

            # جلسة A وجلسة B الاتنين بيعملوا القراءة الأولى الغير مقفولة —
            # نفس ترتيب sell_ticket بالظبط — الاتنين بيشوفوا 195 دلوقتي.
            invA = crud.get_or_create_inventory(dbA, branch.id, today)
            invB = crud.get_or_create_inventory(dbB, branch.id, today)
            assert invA.capacity_used == 195
            assert invB.capacity_used == 195

            # A تقفل، تبيع 3، تعتمد (commit) — القيمة الحقيقية في الداتابيز
            # بقت 198 دلوقتي.
            lockedA = crud.lock_inventory_for_update(dbA, invA.id)
            crud.apply_inventory_delta(dbA, lockedA, -3, 0)
            dbA.commit()

            # B تقفل بعد كده — لازم تشوف القيمة الحقيقية الجديدة (198)، مش
            # القيمة القديمة المخزّنة في identity map بتاعتها (195) — وإلا
            # حساب apply_inventory_delta التالي هيبني على أساس غلط ويمسح
            # أثر بيع A (lost update).
            lockedB = crud.lock_inventory_for_update(dbB, invB.id)
            assert lockedB.capacity_used == 198, (
                "lock_inventory_for_update رجّع قيمة capacity_used قديمة من "
                "identity map الجلسة (195) بدل القيمة الحقيقية المُعتمدة "
                "حديثاً (198) — القفل نفسه اتاخد بنجاح بس بيانات validate_entry "
                "التالية هتكون غلط، وده بالظبط الباج اللي كان بيسبب lost update."
            )
        finally:
            dbB.rollback()
            dbA.close()
            dbB.close()


class TestCustomerGroupDiscount:
    """خصم مجموعة العميل الدائم على معاملة شاطئ — تلقائي بالكامل، بيتحسب
    على السعر الأصلي قبل الـ VAT وبيتخصم من total_amount (اللي بقى صافي
    من دلوقتي، مش unit_price × quantity زي قبل كده). الشاطئ مفيهوش خصم
    شرطي منافس (زي dining) فمفيش سيناريو "أفضل يفوز" هنا."""

    def _make_customer_with_group(self, db, branch, pct=Decimal("10")):
        from app.modules.crm import services as crm_services
        from app.modules.crm.schemas import CustomerCreate, CustomerGroupCreate

        group = crm_services.create_customer_group(
            db, CustomerGroupCreate(branch_id=branch.id, name="Staff", discount_percentage=pct),
        )
        customer = crm_services.create_customer(
            db, CustomerCreate(branch_id=branch.id, full_name="Staff Member"),
        )
        crm_services.assign_customer_group(db, customer.id, group.id)
        return customer

    def test_sell_ticket_applies_group_discount_automatically(self, db):
        from app.modules.core.crud import upsert_setting

        branch = make_branch(db)
        upsert_setting(db, "beach.price.adult", "200", branch_id=branch.id)
        db.commit()
        customer = self._make_customer_with_group(db, branch, pct=Decimal("10"))

        req = BeachSellRequest(tx_type="entry", quantity=1, customer_id=customer.id)
        tx = services.sell_ticket(db, branch.id, req)

        assert tx.unit_price == Decimal("200")
        assert tx.discount_amount == Decimal("20.00")  # 10% of 200
        assert tx.total_amount == Decimal("180.00")  # صافي بعد الخصم

    def test_sell_ticket_no_customer_no_discount(self, db):
        from app.modules.core.crud import upsert_setting

        branch = make_branch(db)
        upsert_setting(db, "beach.price.adult", "200", branch_id=branch.id)
        db.commit()

        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.discount_amount == Decimal("0")
        assert tx.total_amount == Decimal("200.00")

    def test_sell_ticket_discount_scales_with_quantity(self, db):
        from app.modules.core.crud import upsert_setting

        branch = make_branch(db)
        upsert_setting(db, "beach.price.adult", "200", branch_id=branch.id)
        db.commit()
        customer = self._make_customer_with_group(db, branch, pct=Decimal("25"))

        req = BeachSellRequest(tx_type="entry", quantity=3, customer_id=customer.id)
        tx = services.sell_ticket(db, branch.id, req)
        # gross = 200*3=600 → discount 25% = 150 → net = 450
        assert tx.discount_amount == Decimal("150.00")
        assert tx.total_amount == Decimal("450.00")


class TestVoidTransaction:

    def test_void_transaction(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)

        voided = services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")
        assert voided.voided_at is not None
        assert voided.voided_by == 1

    def test_void_reverses_inventory(self, db):
        branch = make_branch(db)
        today = date.today()
        inv = crud.get_or_create_inventory(db, branch.id, today)
        db.commit()

        req = BeachSellRequest(tx_type="entry", quantity=3)
        tx = services.sell_ticket(db, branch.id, req, tx_date=today)
        db.refresh(inv)
        used_after_sale = inv.capacity_used

        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")
        db.refresh(inv)
        assert inv.capacity_used == used_after_sale - 3

    def test_double_void_raises(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")

        with pytest.raises(ValueError, match="ملغاة"):
            services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")

    def test_void_nonexistent_raises(self, db):
        with pytest.raises(ValueError):
            services.void_transaction(db, 9999, voided_by=1, reason="اختبار")

    def test_void_records_reason(self, db):
        """التبرير إجباري — نفس منطق المطعم (void بسبب موثّق)."""
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)

        voided = services.void_transaction(db, tx.id, voided_by=1, reason="غلط في الكمية")
        assert voided.voided_reason == "غلط في الكمية"

    def test_void_b2b_checkin_reverses_outstanding_balance(self, db):
        """⚠️ باج حقيقي كان هنا قبل إضافة حد الائتمان: إلغاء عملية تشيك-إن
        B2B كان بيعكس الـ inventory والقيد المحاسبي، بس مايلمسش
        B2BContractDay.checked_in_count/total_amount خالص — يعني الرصيد
        المستحق على الفندق (المستخدم دلوقتي في حساب حد الائتمان والتأخر)
        كان هيفضل متضخّم للأبد حتى بعد الإلغاء الفعلي."""
        branch = make_branch(db)
        contract = make_contract(db, branch, entry_price=Decimal("100"))
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=4)
        tx = services.b2b_checkin(db, branch.id, req)

        balance_after_checkin = crud.get_b2b_outstanding_balance(db, contract.id)
        assert balance_after_checkin == Decimal("400")

        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")

        balance_after_void = crud.get_b2b_outstanding_balance(db, contract.id)
        assert balance_after_void == Decimal("0")
        day = crud.get_or_create_contract_day(db, contract.id, date.today())
        assert day.checked_in_count == 0


class TestShiftAttachment:

    def test_sale_attaches_open_shift(self, db):
        """بيع الشاطئ بيتربط بوردية الكاشير المفتوحة — عشان يظهر في تقرير
        نهاية الوردية، نفس الباترن المستخدم في finance.services.add_payment."""
        from app.modules.finance import services as finance_services
        from app.modules.finance.schemas import CashierShiftOpen

        branch = make_branch(db)
        shift = finance_services.open_shift(
            db, cashier_id=42, opened_by=42,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        req = BeachSellRequest(tx_type="entry", quantity=1, cashier_id=42)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.shift_id == shift.id

    def test_sale_without_open_shift_has_no_shift_id(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1, cashier_id=999)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.shift_id is None

    def test_sale_without_cashier_id_has_no_shift_id(self, db):
        branch = make_branch(db)
        req = BeachSellRequest(tx_type="entry", quantity=1)
        tx = services.sell_ticket(db, branch.id, req)
        assert tx.shift_id is None

    def test_direct_sale_appears_in_shift_end_report(self, db):
        """⚠️ باج حقيقي اتصلح: BeachTransaction.shift_id كان بيتسجّل (التست
        فوق)، بس finance.services.build_shift_end_report/list_shift_invoices
        (تقرير X/Z نهاية الوردية) بيقروا Payment.shift_id بس — مفيش أي كود
        كان بيكتب Payment فعليًا لبيع شاطئ مباشر (migration 504f42d2c755
        جهّزت folio_id nullable لنفس السبب ده بالظبط، بس عمرها ما اتنفّذت).
        يعني مبيعات الشاطئ المباشرة (كاش فوري، مش محمّلة على غرفة) كانت
        غايبة تمامًا عن تقرير نهاية وردية الكاشير رغم ظهورها صح في
        BeachTransaction نفسها."""
        from app.modules.finance import services as finance_services
        from app.modules.finance.schemas import CashierShiftOpen

        branch = make_branch(db)
        shift = finance_services.open_shift(
            db, cashier_id=43, opened_by=43,
            data=CashierShiftOpen(branch_id=branch.id, opening_float=Decimal("0")),
        )
        req = BeachSellRequest(tx_type="entry", quantity=2, cashier_id=43)
        tx = services.sell_ticket(db, branch.id, req)

        report = finance_services.build_shift_end_report(db, shift.id)
        assert report.invoice_count == 1
        assert report.total_cash == tx.total_amount + tx.vat_amount
        assert report.total_sales == tx.total_amount + tx.vat_amount

        invoices = finance_services.list_shift_invoices(db, shift.id, requesting_user=_FakeManager())
        assert len(invoices) == 1
        assert invoices[0].folio_id is None
        assert invoices[0].amount == tx.total_amount + tx.vat_amount

        # إلغاء البيع لازم يعكس الدفعة من تقرير الوردية برضو، مش بس القيد المحاسبي
        services.void_transaction(db, tx.id, voided_by=43, reason="اختبار")
        report_after_void = finance_services.build_shift_end_report(db, shift.id)
        assert report_after_void.total_sales == Decimal("0")
        assert report_after_void.voided_count == 1


class _FakeManager:
    id = 999
    role = "manager"


class TestSurgeToggle:

    def test_set_surge_manual(self, db):
        branch = make_branch(db)
        inv = services.set_surge(db, branch.id, Decimal("50"))
        assert inv.surge_pct == Decimal("50")

    def test_disable_surge(self, db):
        branch = make_branch(db)
        services.set_surge(db, branch.id, Decimal("50"))
        inv = services.set_surge(db, branch.id, Decimal("0"))
        assert inv.surge_pct == Decimal("0")

    def test_invalid_surge_pct_raises(self, db):
        branch = make_branch(db)
        with pytest.raises(ValueError):
            services.set_surge(db, branch.id, Decimal("201"))

    def test_surge_affects_price(self, db):
        branch = make_branch(db)
        today = date.today()

        req_no_surge = BeachSellRequest(tx_type="entry", quantity=1)
        tx_no_surge = services.sell_ticket(db, branch.id, req_no_surge, tx_date=today)

        services.set_surge(db, branch.id, Decimal("50"), inv_date=today)
        req_surge = BeachSellRequest(tx_type="entry", quantity=1)
        tx_surge = services.sell_ticket(db, branch.id, req_surge, tx_date=today)

        assert tx_surge.unit_price > tx_no_surge.unit_price
        assert tx_surge.surge_applied is True


class TestB2BCheckin:

    def test_b2b_checkin_basic(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=3)
        tx = services.b2b_checkin(db, branch.id, req)
        assert tx.id is not None
        assert tx.b2b_contract_id == contract.id
        assert tx.quantity == 3

    def test_b2b_checkin_with_towel(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=2, with_towel=True)
        tx = services.b2b_checkin(db, branch.id, req)
        assert tx.tx_type == "entry_towel"
        assert tx.total_amount == (contract.entry_price + contract.towel_price) * 2

    def test_b2b_quota_tracking(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=5)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=3)
        services.b2b_checkin(db, branch.id, req)

        day = crud.get_or_create_contract_day(db, contract.id, date.today())
        assert day.checked_in_count == 3

    def test_b2b_quota_exceeded_raises(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=2)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=3)
        with pytest.raises(ValueError, match="حصة"):
            services.b2b_checkin(db, branch.id, req)

    def test_b2b_nonexistent_contract_raises(self, db):
        branch = make_branch(db)
        req = B2BCheckinRequest(contract_id=9999, guests_count=1)
        with pytest.raises(ValueError):
            services.b2b_checkin(db, branch.id, req)

    def test_b2b_expired_contract_blocks_checkin(self, db):
        """باج حقيقي كان هنا: عقد فندق منتهي (valid_until فات من شهور) بس
        لسه is_active=True في الداتابيز (محدش قفله يدويًا) كان يعدّي تسجيل
        الدخول عادي — يستهلك سعة/فوط حقيقية ويتحاسب الفندق عليه رغم إن العقد
        انتهى. اتصلح بالتحقق من نافذة الصلاحية (valid_from/valid_until) في
        beach_engine.validate_b2b_checkin."""
        branch = make_branch(db)
        today = date.today()
        expired = make_contract(
            db, branch,
            valid_from=today - timedelta(days=400),
            valid_until=today - timedelta(days=30),
        )
        req = B2BCheckinRequest(contract_id=expired.id, guests_count=1)
        with pytest.raises(ValueError, match="غير سارٍ"):
            services.b2b_checkin(db, branch.id, req)

    def test_b2b_not_yet_started_contract_blocks_checkin(self, db):
        branch = make_branch(db)
        today = date.today()
        future = make_contract(
            db, branch,
            valid_from=today + timedelta(days=10),
            valid_until=today + timedelta(days=100),
        )
        req = B2BCheckinRequest(contract_id=future.id, guests_count=1)
        with pytest.raises(ValueError, match="غير سارٍ"):
            services.b2b_checkin(db, branch.id, req)

    def test_b2b_price_calculation(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, entry_price=Decimal("100"), towel_price=Decimal("40"))
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=4, with_towel=False)
        tx = services.b2b_checkin(db, branch.id, req)
        assert tx.total_amount == Decimal("400")

    def test_concurrent_checkin_raises_concurrency_error(self, db, monkeypatch):
        """باج حقيقي كان هنا: b2b_checkin كان بيقرا/يعدّل
        B2BContractDay.checked_in_count من غير أي قفل صف — تحت حمل متزامن
        حقيقي (كذا كاشير بيسجّلوا دخول لنفس العقد في نفس اللحظة والحصة قريبة
        من الحد)، عمليتين كانوا ممكن يعدّوا validate_b2b_checkin بنفس القيمة
        القديمة ويتسبب تجاوز فعلي لحصة الفندق الشريك اليومية. اتصلح بقفل صف
        B2BContractDay (SELECT FOR UPDATE NOWAIT) قبل أي تحقق/تعديل — هنا
        بنحاكي عملية تانية ماسكة الصف بمحاكاة OperationalError من القفل نفسه
        (نفس أسلوب test_concurrent_sale_raises_concurrency_error فوق)."""
        from sqlalchemy.exc import OperationalError

        branch = make_branch(db)
        contract = make_contract(db, branch)

        def _raise_locked(*_args, **_kwargs):
            raise OperationalError("SELECT ... FOR UPDATE NOWAIT", {}, Exception("could not obtain lock"))

        monkeypatch.setattr(crud, "lock_contract_day_for_update", _raise_locked)

        req = B2BCheckinRequest(contract_id=contract.id, guests_count=1)
        with pytest.raises(services.BeachConcurrencyError, match="مشغولة"):
            services.b2b_checkin(db, branch.id, req)

    def test_contract_day_lock_refreshes_stale_checked_in_count(self, db):
        """نفس فئة باج lock_inventory_for_update (شوف
        test_lock_refreshes_stale_in_memory_capacity_not_just_db_lock فوق) —
        هنا بنفس السيناريو لكن على B2BContractDay.checked_in_count: جلستين
        منفصلتين بيعملوا القراءة الأولى الغير مقفولة، جلسة A تقفل وتزوّد
        العدد وتعتمد، جلسة B لازم تشوف العدد الجديد لما تقفل هي كمان — مش
        العدد القديم من identity map بتاعتها."""
        from tests.conftest import TestingSessionLocal

        branch = make_branch(db)
        contract = make_contract(db, branch, quota=10)
        today = date.today()
        dbA = TestingSessionLocal()
        dbB = TestingSessionLocal()
        try:
            dayA = crud.get_or_create_contract_day(dbA, contract.id, today)
            dayB = crud.get_or_create_contract_day(dbB, contract.id, today)
            assert dayA.checked_in_count == 0
            assert dayB.checked_in_count == 0

            lockedA = crud.lock_contract_day_for_update(dbA, dayA.id)
            crud.increment_b2b_checkins(dbA, contract.id, today, 4, Decimal("320"))
            dbA.commit()

            lockedB = crud.lock_contract_day_for_update(dbB, dayB.id)
            assert lockedB.checked_in_count == 4, (
                "lock_contract_day_for_update رجّع checked_in_count قديم (0) "
                "بدل القيمة الحقيقية المُعتمدة حديثاً (4) — نفس باج identity "
                "map staleness."
            )
        finally:
            dbB.rollback()
            dbA.close()
            dbB.close()


class TestB2BQuotaStatus:
    """حالة حصة B2B اليوم — للوحة الحيّة (quota_warning ≤5 متبقين)."""

    def test_no_usage_yet_shows_full_quota(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=10)
        status = services.get_b2b_quota_status(db, branch.id)
        assert len(status) == 1
        assert status[0]["checked_in_today"] == 0
        assert status[0]["remaining_quota"] == 10
        assert status[0]["quota_warning"] is False

    def test_quota_warning_triggers_at_5_or_fewer_remaining(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=8)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=4)
        services.b2b_checkin(db, branch.id, req)  # remaining = 4

        status = services.get_b2b_quota_status(db, branch.id)
        assert status[0]["checked_in_today"] == 4
        assert status[0]["remaining_quota"] == 4
        assert status[0]["quota_warning"] is True

    def test_quota_warning_sends_whatsapp_to_contract_contact(self, db):
        from unittest.mock import patch
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=8)
        contract.contact_phone = "01055555555"
        db.commit()

        req = B2BCheckinRequest(contract_id=contract.id, guests_count=4)  # remaining = 4 → warning
        with patch("app.core.kernel.whatsapp.send_whatsapp_message", return_value=True) as mock_send:
            services.b2b_checkin(db, branch.id, req)

        mock_send.assert_called_once()
        phone_arg, message_arg = mock_send.call_args[0]
        assert phone_arg == "01055555555"
        assert contract.hotel_name in message_arg

    def test_quota_exhausted(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, quota=3)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=3)
        services.b2b_checkin(db, branch.id, req)

        status = services.get_b2b_quota_status(db, branch.id)
        assert status[0]["is_quota_exhausted"] is True
        assert status[0]["remaining_quota"] == 0

    def test_inactive_contracts_excluded(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch)
        contract.is_active = False
        db.flush()
        status = services.get_b2b_quota_status(db, branch.id)
        assert status == []


class TestB2BCredit:
    """حد ائتمان + تأخر سداد عقود B2B — أول ضبط ائتماني حقيقي في المشروع
    (راجع ملحوظة B2BContract في models.py). B2BContract هو أول/الوحيد علاقة
    ائتمانية متكررة حقيقية في resort-os اليوم — الفوليوهات بتتسوّى فورًا
    عند الخروج، وCRM.total_spent مجرد إحصائية تاريخية مش رصيد مستحق."""

    def test_checkin_within_limit_succeeds(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, entry_price=Decimal("100"), credit_limit=Decimal("1000"))
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=5)  # 500 ج.م
        tx = services.b2b_checkin(db, branch.id, req)
        assert tx.id is not None

    def test_checkin_exceeding_limit_rejected(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, entry_price=Decimal("100"), credit_limit=Decimal("300"))
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=5)  # 500 ج.م > 300 حد
        with pytest.raises(ValueError, match="حد الائتمان"):
            services.b2b_checkin(db, branch.id, req)

        # العملية المرفوضة ميستهلكش أي سعة/حصة فعليًا — لا شيء اتغيّر.
        day = crud.get_or_create_contract_day(db, contract.id, date.today())
        assert day.checked_in_count == 0

    def test_no_credit_limit_means_unrestricted(self, db):
        """credit_limit=None (الافتراضي) — مفيش أي تحقق ائتماني خالص، زي
        سلوك النظام قبل هذه الإضافة تمامًا."""
        branch = make_branch(db)
        contract = make_contract(db, branch, entry_price=Decimal("1000"), quota=100)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=50)
        tx = services.b2b_checkin(db, branch.id, req)
        assert tx.id is not None

    def test_second_checkin_accumulates_toward_limit(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, entry_price=Decimal("100"), credit_limit=Decimal("450"), quota=100)
        services.b2b_checkin(db, branch.id, B2BCheckinRequest(contract_id=contract.id, guests_count=4))  # 400

        with pytest.raises(ValueError, match="حد الائتمان"):
            services.b2b_checkin(db, branch.id, B2BCheckinRequest(contract_id=contract.id, guests_count=1))  # +100 = 500 > 450

    def test_settle_resets_outstanding_balance(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, entry_price=Decimal("100"), credit_limit=Decimal("300"))
        services.b2b_checkin(db, branch.id, B2BCheckinRequest(contract_id=contract.id, guests_count=2))  # 200

        settled = services.settle_b2b_contract(db, contract.id, date.today())
        assert settled.last_settled_at == date.today()
        assert crud.get_b2b_outstanding_balance(db, contract.id, settled.last_settled_at) == Decimal("0")

        # بعد التسوية، فيه مساحة ائتمان تانية.
        tx = services.b2b_checkin(db, branch.id, B2BCheckinRequest(contract_id=contract.id, guests_count=2))
        assert tx.id is not None

    def test_settle_nonexistent_contract_raises(self, db):
        with pytest.raises(ValueError):
            services.settle_b2b_contract(db, 9999)

    def test_mark_overdue_flags_old_unsettled_balance(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, payment_terms_days=30)
        old_day = date.today() - timedelta(days=45)
        crud.increment_b2b_checkins(db, contract.id, old_day, 3, Decimal("300"))
        db.commit()

        changed = services.mark_b2b_contracts_overdue(db, date.today())
        db.commit()
        db.refresh(contract)
        assert changed == 1
        assert contract.is_overdue is True

    def test_mark_overdue_ignores_recent_balance(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, payment_terms_days=30)
        recent_day = date.today() - timedelta(days=5)
        crud.increment_b2b_checkins(db, contract.id, recent_day, 3, Decimal("300"))
        db.commit()

        services.mark_b2b_contracts_overdue(db, date.today())
        db.commit()
        db.refresh(contract)
        assert contract.is_overdue is False

    def test_mark_overdue_clears_flag_after_settlement(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, payment_terms_days=30)
        old_day = date.today() - timedelta(days=45)
        crud.increment_b2b_checkins(db, contract.id, old_day, 3, Decimal("300"))
        db.commit()
        services.mark_b2b_contracts_overdue(db, date.today())
        db.commit()
        db.refresh(contract)
        assert contract.is_overdue is True

        services.settle_b2b_contract(db, contract.id, date.today())
        services.mark_b2b_contracts_overdue(db, date.today())
        db.commit()
        db.refresh(contract)
        assert contract.is_overdue is False

    def test_mark_overdue_sends_whatsapp_once(self, db):
        from unittest.mock import patch
        branch = make_branch(db)
        contract = make_contract(db, branch, payment_terms_days=30)
        contract.contact_phone = "01099999999"
        db.commit()
        old_day = date.today() - timedelta(days=45)
        crud.increment_b2b_checkins(db, contract.id, old_day, 3, Decimal("300"))
        db.commit()

        with patch("app.core.kernel.whatsapp.send_whatsapp_message", return_value=True) as mock_send:
            services.mark_b2b_contracts_overdue(db, date.today())
            db.commit()
            # تشغيل تاني لنفس اليوم — العقد لسه متأخر، بس محدش يتبعتله رسالة تانية.
            services.mark_b2b_contracts_overdue(db, date.today())
            db.commit()

        mock_send.assert_called_once()

    def test_quota_status_includes_credit_and_overdue_fields(self, db):
        branch = make_branch(db)
        contract = make_contract(db, branch, entry_price=Decimal("100"), credit_limit=Decimal("150"))
        services.b2b_checkin(db, branch.id, B2BCheckinRequest(contract_id=contract.id, guests_count=1))

        status = services.get_b2b_quota_status(db, branch.id)
        entry = status[0]
        assert entry["credit_limit"] == Decimal("150")
        assert entry["outstanding_balance"] == Decimal("100")
        assert entry["credit_exceeded"] is False
        assert entry["is_overdue"] is False


class TestBeachReservation:

    def test_create_reservation(self, db):
        branch = make_branch(db)
        tomorrow = date.today() + timedelta(days=1)
        data = BeachReservationCreate(
            branch_id=branch.id,
            guest_name="أحمد محمد",
            guest_phone="01012345678",
            reservation_date=tomorrow,
            guests_count=2,
            with_towel=False,
        )
        res = services.create_reservation(db, data)
        assert res.id is not None
        assert res.status == "pending"
        assert res.guests_count == 2
        assert res.total_amount > 0

    def test_reservation_with_towel_costs_more(self, db):
        branch = make_branch(db)
        tomorrow = date.today() + timedelta(days=1)
        base = BeachReservationCreate(
            branch_id=branch.id,
            guest_name="نادية",
            reservation_date=tomorrow,
            guests_count=1,
            with_towel=False,
        )
        with_towel = BeachReservationCreate(
            branch_id=branch.id,
            guest_name="نادية",
            reservation_date=tomorrow,
            guests_count=1,
            with_towel=True,
        )
        res_base = services.create_reservation(db, base)
        res_towel = services.create_reservation(db, with_towel)
        assert res_towel.total_amount > res_base.total_amount

    def test_list_reservations(self, db):
        branch = make_branch(db)
        tomorrow = date.today() + timedelta(days=1)
        for i in range(3):
            data = BeachReservationCreate(
                branch_id=branch.id,
                guest_name=f"Guest {i}",
                reservation_date=tomorrow,
                guests_count=1,
            )
            services.create_reservation(db, data)

        items, total = crud.list_reservations(db, branch.id, res_date=tomorrow)
        assert total >= 3


class TestQRCheckin:
    """تسجيل دخول فوري عبر QR — يحوّل الحجز لعملية بيع حقيقية (يستهلك capacity/فوط)."""

    def test_checkin_creates_transaction_and_consumes_capacity(self, db):
        branch = make_branch(db)
        cashier = make_branch_linked_cashier(db, branch)
        today = date.today()
        data = BeachReservationCreate(
            branch_id=branch.id, guest_name="Ahmed", guest_phone="01001234567",
            reservation_date=today, guests_count=3, with_towel=True,
        )
        res = services.create_reservation(db, data)
        assert res.status == "pending"

        checked_in = services.check_in_reservation(db, res.id, requesting_user=cashier, cashier_id=cashier.id)
        assert checked_in.status == "checked_in"
        assert checked_in.tx_id is not None

        tx = crud.get_transaction(db, checked_in.tx_id)
        assert tx.tx_type == "entry_towel"
        assert tx.quantity == 3

        inv = crud.get_or_create_inventory(db, branch.id, today)
        db.commit()
        assert inv.capacity_used == 3
        assert inv.towels_used == 3

    def test_checkin_without_towel(self, db):
        branch = make_branch(db)
        cashier = make_branch_linked_cashier(db, branch)
        data = BeachReservationCreate(
            branch_id=branch.id, guest_name="Sara", reservation_date=date.today(),
            guests_count=2, with_towel=False,
        )
        res = services.create_reservation(db, data)
        checked_in = services.check_in_reservation(db, res.id, requesting_user=cashier)
        tx = crud.get_transaction(db, checked_in.tx_id)
        assert tx.tx_type == "entry"

    def test_double_checkin_raises(self, db):
        branch = make_branch(db)
        cashier = make_branch_linked_cashier(db, branch)
        data = BeachReservationCreate(
            branch_id=branch.id, guest_name="Omar", reservation_date=date.today(),
            guests_count=1,
        )
        res = services.create_reservation(db, data)
        services.check_in_reservation(db, res.id, requesting_user=cashier)
        with pytest.raises(ValueError, match="بالفعل"):
            services.check_in_reservation(db, res.id, requesting_user=cashier)

    def test_checkin_nonexistent_reservation_raises(self, db):
        branch = make_branch(db)
        cashier = make_branch_linked_cashier(db, branch)
        with pytest.raises(ValueError):
            services.check_in_reservation(db, 999999, requesting_user=cashier)

    def test_checkin_cancelled_reservation_raises(self, db):
        branch = make_branch(db)
        cashier = make_branch_linked_cashier(db, branch)
        data = BeachReservationCreate(
            branch_id=branch.id, guest_name="Laila", reservation_date=date.today(),
            guests_count=1,
        )
        res = services.create_reservation(db, data)
        res = crud.update_reservation_status(db, res, "cancelled")
        db.commit()
        with pytest.raises(ValueError, match="ملغى"):
            services.check_in_reservation(db, res.id, requesting_user=cashier)

    def test_checkin_respects_capacity_limit(self, db):
        branch = make_branch(db)
        cashier = make_branch_linked_cashier(db, branch)
        today = date.today()
        # عمّر السعة تقريباً بالكامل
        inv = crud.get_or_create_inventory(db, branch.id, today, capacity_max=5)
        db.commit()
        data = BeachReservationCreate(
            branch_id=branch.id, guest_name="Big Group", reservation_date=today,
            guests_count=10,
        )
        res = services.create_reservation(db, data)
        with pytest.raises(ValueError, match="ممتلئ"):
            services.check_in_reservation(db, res.id, requesting_user=cashier)


class TestDailySummary:

    def test_daily_summary_empty(self, db):
        branch = make_branch(db)
        today = date.today()
        summary = crud.get_daily_summary(db, branch.id, today)
        assert summary["total_entries"] == 0
        assert summary["total_revenue"] == 0

    def test_daily_summary_after_sales(self, db):
        branch = make_branch(db)
        today = date.today()

        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=3), tx_date=today)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="towel_rent", quantity=2), tx_date=today)

        summary = crud.get_daily_summary(db, branch.id, today)
        assert summary["total_entries"] == 3
        assert summary["towels_rented"] == 2
        assert summary["total_revenue"] > 0

    def test_voided_not_in_summary(self, db):
        branch = make_branch(db)
        today = date.today()

        tx = services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=1), tx_date=today)
        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")

        summary = crud.get_daily_summary(db, branch.id, today)
        assert summary["total_entries"] == 0

    def test_b2b_tracked_separately(self, db):
        branch = make_branch(db)
        today = date.today()
        contract = make_contract(db, branch)

        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=2), tx_date=today)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=5)
        services.b2b_checkin(db, branch.id, req, tx_date=today)

        summary = crud.get_daily_summary(db, branch.id, today)
        assert summary["b2b_entries"] == 5
        assert summary["total_entries"] >= 7


class TestEODReport:
    """تقرير نهاية اليوم — تفصيل حسب النوع، إيرادات الفوط، مقارنة بالأمس/الأسبوع الماضي."""

    def test_empty_day_report(self, db):
        branch = make_branch(db)
        report = services.get_eod_report(db, branch.id, date.today())
        assert report["total_entries"] == 0
        assert report["total_revenue"] == 0
        assert report["by_type"] == []
        assert report["vs_yesterday_pct"] is None

    def test_breakdown_by_type(self, db):
        branch = make_branch(db)
        today = date.today()
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=3), tx_date=today)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry_towel", quantity=2), tx_date=today)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="towel_rent", quantity=1), tx_date=today)

        report = services.get_eod_report(db, branch.id, today)
        types = {r["tx_type"]: r for r in report["by_type"]}
        assert types["entry"]["quantity"] == 3
        assert types["entry_towel"]["quantity"] == 2
        assert types["towel_rent"]["quantity"] == 1
        assert report["total_entries"] == 5  # entry(3) + entry_towel(2), not towel_rent

    def test_towel_revenue_combines_standalone_and_bundled(self, db):
        branch = make_branch(db)
        today = date.today()
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="towel_rent", quantity=2), tx_date=today)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry_towel", quantity=3), tx_date=today)

        report = services.get_eod_report(db, branch.id, today)
        # towel_rent (2 * 50) + entry_towel's bundled towel portion (3 * 50) = 250
        assert report["towel_revenue"] == Decimal("250")

    def test_voided_excluded_from_report(self, db):
        branch = make_branch(db)
        today = date.today()
        tx = services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=1), tx_date=today)
        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")

        report = services.get_eod_report(db, branch.id, today)
        assert report["total_entries"] == 0
        assert report["voided_count"] == 1

    def test_comparison_vs_yesterday(self, db):
        branch = make_branch(db)
        today = date.today()
        yesterday = today - timedelta(days=1)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=1), tx_date=yesterday)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=2), tx_date=today)

        report = services.get_eod_report(db, branch.id, today)
        assert report["yesterday"]["total_entries"] == 1
        assert report["vs_yesterday_pct"] == 100.0  # ضعف الإيراد (2x)

    def test_b2b_tracked_in_report(self, db):
        branch = make_branch(db)
        today = date.today()
        contract = make_contract(db, branch)
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=4)
        services.b2b_checkin(db, branch.id, req, tx_date=today)

        report = services.get_eod_report(db, branch.id, today)
        assert report["b2b_entries"] == 4
        assert report["b2b_revenue"] > 0

    def test_generate_eod_pdf(self, db):
        branch = make_branch(db)
        today = date.today()
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=1), tx_date=today)
        pdf = services.generate_eod_report_pdf(db, branch.id, today)
        assert pdf[:4] == b"%PDF"


def make_finance_accounts(db, branch):
    """يزرع 1100 (نقدية) و4300 (إيرادات الشاطئ) و1150 (ذمم الفوليو) —
    الحسابات اللي beach.services بيدوّر عليها بالكود عند ترحيل قيد الإيراد
    (كاش فوري أو محمّل على فوليو غرفة)."""
    from app.modules.finance.models import Account
    cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
    revenue = Account(branch_id=branch.id, code="4300", name="Beach Revenue", account_type="revenue")
    guest_ledger = Account(branch_id=branch.id, code="1150", name="ذمم الفوليو", account_type="asset")
    db.add_all([cash, revenue, guest_ledger])
    db.commit()
    return cash, revenue


class TestBeachRevenueJournalPosting:
    """Gap حقيقي: beach لم يكن يرحّل أي شيء لدفتر اليومية — كل بيع كان
    يُنشئ BeachTransaction بس من غير أي أثر محاسبي (حساب 4300 كان صفر دايماً)."""

    def test_sell_ticket_posts_balanced_journal_entry(self, db):
        from app.modules.finance import crud as finance_crud
        branch = make_branch(db)
        cash, revenue = make_finance_accounts(db, branch)

        tx = services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=2))

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="beach")
        assert total == 1
        entry = entries[0]
        assert entry.source_id == tx.id
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit
        expected_amount = tx.total_amount + tx.vat_amount
        assert total_debit == expected_amount

        db.refresh(cash)
        db.refresh(revenue)
        cash_line = next(l for l in entry.lines if l.account_id == cash.id)
        revenue_line = next(l for l in entry.lines if l.account_id == revenue.id)
        assert cash_line.debit == expected_amount
        assert revenue_line.credit == expected_amount

    def test_sell_ticket_updates_linked_customer_stats(self, db):
        from app.modules.crm import services as crm_services
        from app.modules.crm.schemas import CustomerCreate

        branch = make_branch(db)
        customer = crm_services.create_customer(db, CustomerCreate(
            branch_id=branch.id, full_name="عميل شاطئ دائم",
        ))
        tx = services.sell_ticket(db, branch.id, BeachSellRequest(
            tx_type="entry", quantity=2, customer_id=customer.id,
        ))
        db.refresh(customer)
        assert customer.visits_count == 1
        assert customer.total_spent == tx.total_amount + tx.vat_amount

    def test_b2b_checkin_posts_journal_entry(self, db):
        from app.modules.finance import crud as finance_crud
        branch = make_branch(db)
        make_finance_accounts(db, branch)
        contract = make_contract(db, branch)

        tx = services.b2b_checkin(db, branch.id, B2BCheckinRequest(contract_id=contract.id, guests_count=3))

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="beach")
        assert total == 1
        assert entries[0].source_id == tx.id

    def test_missing_accounts_does_not_block_sale(self, db):
        """لو الحسابات مش موجودة في الفرع، البيع لازم ينجح عادي (نفس فلسفة
        pms._post_checkout_journal — الفشل المحاسبي ميوقفش العملية الأساسية)."""
        branch = make_branch(db)
        tx = services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=1))
        assert tx.id is not None

        from app.modules.finance import crud as finance_crud
        _, total = finance_crud.list_journal_entries(db, branch.id, source="beach")
        assert total == 0

    def test_towel_return_zero_amount_does_not_post(self, db):
        """towel_return مفهوش قيمة مالية (إعادة فوطة) — من غير المفروض
        يرحّل أي قيد إيراد."""
        from app.modules.finance import crud as finance_crud
        branch = make_branch(db)
        make_finance_accounts(db, branch)

        # لازم فوطة مستأجرة الأول عشان نقدر نرجّعها
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="towel_rent", quantity=1))
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="towel_return", quantity=1))

        _, total = finance_crud.list_journal_entries(db, branch.id, source="beach")
        assert total == 1  # بس من towel_rent، مش من towel_return


class TestBeachVoidReversesFinancials:
    """⚠️ باج محاسبي حقيقي كان هنا (اتصلح 2026-07-04): void_transaction كانت
    بتعكس المخزون بس — الإيراد المسجّل في دفتر اليومية (كاش فوري) أو الشحنة
    على فاتورة الغرفة (Charge to Room) كانت تفضل زي ما هي حتى بعد الإلغاء،
    يعني مبالغة دائمة في الإيرادات/فاتورة الضيف لأي عملية اتلغت."""

    def test_void_cash_sale_posts_reversal_journal_entry(self, db):
        from app.modules.finance import crud as finance_crud
        branch = make_branch(db)
        cash, revenue = make_finance_accounts(db, branch)

        tx = services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=2))
        expected_amount = tx.total_amount + tx.vat_amount

        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار عكس القيد")

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="beach_void")
        assert total == 1
        entry = entries[0]
        assert entry.source_id == tx.id
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit == expected_amount

        db.refresh(cash)
        db.refresh(revenue)
        cash_line = next(l for l in entry.lines if l.account_id == cash.id)
        revenue_line = next(l for l in entry.lines if l.account_id == revenue.id)
        assert cash_line.credit == expected_amount  # عكس البيع: دلوقتي دائن مش مدين
        assert revenue_line.debit == expected_amount  # عكس البيع: دلوقتي مدين مش دائن

    def test_void_room_charged_ticket_removes_folio_charge(self, db):
        from app.modules.finance import crud as finance_crud
        from app.modules.finance.models import Folio
        from app.modules.pms.models import Room, Booking
        from datetime import datetime, timedelta

        branch = make_branch(db)
        make_finance_accounts(db, branch)
        folio = Folio(
            branch_id=branch.id, guest_name="نزيل شاطئ", status="open",
            check_in=datetime.utcnow(), check_out=datetime.utcnow() + timedelta(days=2),
        )
        db.add(folio)
        db.commit()

        tx = services.sell_ticket(
            db, branch.id, BeachSellRequest(tx_type="entry", quantity=1, folio_id=folio.id),
        )
        charge = finance_crud.get_charge_by_ref_beach_tx(db, tx.id)
        assert charge is not None
        db.refresh(folio)
        assert folio.total == tx.total_amount + tx.vat_amount

        # ⚠️ باج حقيقي اتصلح 2026-07-07 (CLAUDE.md §18): بيع شاطئ محمّل على
        # غرفة كان بيضيف FolioCharge بس من غير أي قيد يومية — إيراد الشاطئ
        # الحقيقي كان غايب عن دفتر الأستاذ. دلوقتي بيترحّل Dr ذمم الفوليو
        # (1150)/Cr إيراد الشاطئ (4300) فورًا.
        expected_amount = tx.total_amount + tx.vat_amount
        charge_entries, charge_total = finance_crud.list_journal_entries(
            db, branch.id, source="beach_folio_charge",
        )
        assert charge_total == 1
        charge_lines = charge_entries[0].lines
        charge_debit = next(l for l in charge_lines if l.debit > 0)
        charge_credit = next(l for l in charge_lines if l.credit > 0)
        assert finance_crud.get_account_by_code(db, branch.id, "1150").id == charge_debit.account_id
        assert finance_crud.get_account_by_code(db, branch.id, "4300").id == charge_credit.account_id
        assert charge_debit.debit == expected_amount

        services.void_transaction(db, tx.id, voided_by=1, reason="اختبار إلغاء شحنة الغرفة")

        assert finance_crud.get_charge_by_ref_beach_tx(db, tx.id) is None
        db.refresh(folio)
        assert folio.total == Decimal("0")

        # الإلغاء لازم يعكس قيد الإيراد الأصلي بالكامل كمان
        void_entries, void_total = finance_crud.list_journal_entries(
            db, branch.id, source="beach_folio_void",
        )
        assert void_total == 1
        void_lines = void_entries[0].lines
        void_debit = next(l for l in void_lines if l.debit > 0)
        void_credit = next(l for l in void_lines if l.credit > 0)
        assert finance_crud.get_account_by_code(db, branch.id, "4300").id == void_debit.account_id
        assert finance_crud.get_account_by_code(db, branch.id, "1150").id == void_credit.account_id
        assert void_debit.debit == expected_amount

    def test_void_rejected_on_closed_folio(self, db):
        from app.modules.finance.models import Folio
        from datetime import datetime, timedelta

        branch = make_branch(db)
        folio = Folio(
            branch_id=branch.id, guest_name="نزيل شاطئ", status="open",
            check_in=datetime.utcnow(), check_out=datetime.utcnow() + timedelta(days=2),
        )
        db.add(folio)
        db.commit()

        tx = services.sell_ticket(
            db, branch.id, BeachSellRequest(tx_type="entry", quantity=1, folio_id=folio.id),
        )
        folio.status = "closed"
        db.commit()

        with pytest.raises(ValueError, match="مقفولة"):
            services.void_transaction(db, tx.id, voided_by=1, reason="اختبار")


class TestTimezoneBugFixes:
    """باج توقيت حقيقي: نفس فئة الباج اللي اتكشفت واتصلحت قبل كده في
    HR/PMS/Timeshare (سجل حضور/تسوية ليلية/قيد إيراد كان بيتسجّل بتاريخ
    UTC السيرفر بدل تاريخ القاهرة). الشاطئ كان الموديول الوحيد الباقي لسه
    بيستخدم date.today() الخام في كل حدود اليوم (إعادة ضبط السعة اليومية،
    تصفير حصة B2B، تقرير نهاية اليوم) — لو السيرفر شغّال UTC، أي عملية بين
    منتصف ليل القاهرة والساعة 3 صباحًا كانت بتتسجّل على يوم غلط (اليوم اللي
    فات بدل النهاردة فعليًا)."""

    def test_sell_ticket_uses_resort_local_date_not_server_utc(self, db, monkeypatch):
        """لو UTC السيرفر لسه فاتح على تاريخ الأمس بس توقيت القاهرة دخل يوم
        جديد، تذكرة البيع لازم تتسجّل على inventory_date بتاريخ القاهرة
        (اليوم الجديد) — مش على صف الأمس اللي كان ممكن يكون قريب من الامتلاء."""
        import app.resort_os.timezone_utils as tzutils

        forced_date = date(2026, 7, 6)  # "اليوم" بتوقيت القاهرة
        monkeypatch.setattr(tzutils, "local_today", lambda tz_name: forced_date)

        branch = make_branch(db)
        tx = services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=1))
        assert tx.tx_date == forced_date

        inv = crud.get_or_create_inventory(db, branch.id, forced_date)
        assert inv.capacity_used == 1

    def test_b2b_checkin_uses_resort_local_date_for_quota_day(self, db, monkeypatch):
        """حصة الفندق اليومية لازم تتصفّر/تتحسب على يوم القاهرة، مش يوم
        UTC السيرفر — وإلا تسجيل دخول الساعة 1 صباحًا بتوقيت القاهرة كان
        هيتحسب لسه على حصة "أمس" اللي ممكن تكون خلصت بالفعل.

        ⚠️ باج حقيقي في التست ده نفسه اتكشف 2026-07-08 (منتصف الجلسة دي
        بالظبط): forced_date كان تاريخ حرفي ثابت (2026-07-06)، وmake_contract
        الافتراضي بيحسب valid_from من date.today() *الحقيقي* وقت تشغيل
        التست — يعني التست كان بيعدّي بالصدفة بس لما التاريخ الحقيقي يقع
        قبل 2026-07-07، وبيفشل تلقائيًا أي يوم بعد كده. الحل: valid_from
        صريح مبني على forced_date نفسه، مش تاريخ حرفي منفصل عن أي مرجع."""
        import app.resort_os.timezone_utils as tzutils

        forced_date = date(2026, 7, 6)
        monkeypatch.setattr(tzutils, "local_today", lambda tz_name: forced_date)

        branch = make_branch(db)
        contract = make_contract(
            db, branch, quota=5,
            valid_from=forced_date - timedelta(days=1),
            valid_until=forced_date + timedelta(days=30),
        )
        req = B2BCheckinRequest(contract_id=contract.id, guests_count=3)
        services.b2b_checkin(db, branch.id, req)

        day = crud.get_or_create_contract_day(db, contract.id, forced_date)
        assert day.checked_in_count == 3

    def test_eod_report_uses_resort_local_date_by_default(self, db, monkeypatch):
        import app.resort_os.timezone_utils as tzutils

        forced_date = date(2026, 7, 6)
        monkeypatch.setattr(tzutils, "local_today", lambda tz_name: forced_date)

        branch = make_branch(db)
        services.sell_ticket(db, branch.id, BeachSellRequest(tx_type="entry", quantity=2))

        report = services.get_eod_report(db, branch.id)
        assert report["date"] == forced_date
        assert report["total_entries"] == 2


class TestBeachLocations:
    """خريطة الشاطئ الحية — BeachLocation. تسجيل دخول لموقع فعلي لازم يكون
    عملية بيع حقيقية (services.sell_ticket الداخلي)، مش مجرد تعليم status."""

    def test_bulk_add_locations_sequential_numbering(self, db):
        branch = make_branch(db)
        created = services.bulk_add_locations(db, branch.id, "umbrella", 5)
        assert [loc.number for loc in created] == ["1", "2", "3", "4", "5"]
        assert all(loc.status == "available" for loc in created)

        more = services.bulk_add_locations(db, branch.id, "umbrella", 3)
        assert [loc.number for loc in more] == ["6", "7", "8"]

    def test_bulk_remove_rejects_when_not_enough_available(self, db):
        branch = make_branch(db)
        locs = services.bulk_add_locations(db, branch.id, "pergola", 3)
        services.checkin_location(
            db, branch.id, locs[0].id,
            BeachLocationCheckinRequest(guest_name="ضيف", guests_count=1),
        )
        with pytest.raises(ValueError, match="متاح"):
            services.bulk_remove_locations(db, branch.id, "pergola", 3)

    def test_checkin_creates_real_transaction_and_occupies_location(self, db):
        branch = make_branch(db)
        loc = services.bulk_add_locations(db, branch.id, "umbrella", 1)[0]

        updated = services.checkin_location(
            db, branch.id, loc.id,
            BeachLocationCheckinRequest(
                guest_name="أحمد سامي", guest_phone="01011122233",
                guests_count=2, with_towel=True,
            ),
            cashier_id=7,
        )

        assert updated.status == "occupied"
        assert updated.guest_name == "أحمد سامي"
        assert updated.guests_count == 2
        assert updated.towels_given == 2
        assert updated.current_transaction_id is not None

        tx = crud.get_transaction(db, updated.current_transaction_id)
        assert tx is not None
        assert tx.tx_type == "entry_towel"
        assert tx.quantity == 2
        assert tx.location_id == loc.id
        assert tx.total_amount > 0

        # الإشغال اليومي المجمّع اتأثر زي أي تذكرة عادية
        inv = crud.get_or_create_inventory(db, branch.id, date.today())
        assert inv.capacity_used == 2

    def test_checkin_occupied_location_rejected(self, db):
        branch = make_branch(db)
        loc = services.bulk_add_locations(db, branch.id, "umbrella", 1)[0]
        services.checkin_location(
            db, branch.id, loc.id, BeachLocationCheckinRequest(guests_count=1),
        )
        with pytest.raises(services.BeachConcurrencyError, match="مشغول"):
            services.checkin_location(
                db, branch.id, loc.id, BeachLocationCheckinRequest(guests_count=1),
            )

    def test_checkin_out_of_service_location_rejected(self, db):
        branch = make_branch(db)
        loc = services.bulk_add_locations(db, branch.id, "umbrella", 1)[0]
        services.update_location(db, loc.id, status="out_of_service")
        with pytest.raises(ValueError, match="خارج الخدمة"):
            services.checkin_location(
                db, branch.id, loc.id, BeachLocationCheckinRequest(guests_count=1),
            )

    def test_checkout_frees_location_and_returns_towels_without_touching_capacity(self, db):
        branch = make_branch(db)
        loc = services.bulk_add_locations(db, branch.id, "umbrella", 1)[0]
        services.checkin_location(
            db, branch.id, loc.id,
            BeachLocationCheckinRequest(guest_name="سلمى", guests_count=1, with_towel=True),
        )
        inv_before = crud.get_or_create_inventory(db, branch.id, date.today())
        towels_before = inv_before.towels_available
        capacity_before = inv_before.capacity_used

        freed = services.checkout_location(db, branch.id, loc.id)

        assert freed.status == "available"
        assert freed.guest_name is None
        assert freed.current_transaction_id is None
        assert freed.towels_given == 0

        inv_after = crud.get_or_create_inventory(db, branch.id, date.today())
        assert inv_after.towels_available == towels_before + 1  # الفوطة رجعت
        assert inv_after.capacity_used == capacity_before        # الإشغال اليومي متأثرش

    def test_checkout_not_occupied_rejected(self, db):
        branch = make_branch(db)
        loc = services.bulk_add_locations(db, branch.id, "umbrella", 1)[0]
        with pytest.raises(ValueError, match="مش مشغول"):
            services.checkout_location(db, branch.id, loc.id)

    def test_update_location_rejects_disabling_occupied_spot(self, db):
        branch = make_branch(db)
        loc = services.bulk_add_locations(db, branch.id, "umbrella", 1)[0]
        services.checkin_location(
            db, branch.id, loc.id, BeachLocationCheckinRequest(guests_count=1),
        )
        with pytest.raises(ValueError, match="مشغول"):
            services.update_location(db, loc.id, status="out_of_service")

    def test_concurrent_checkin_raises_concurrency_error_on_lock_busy(self, db, monkeypatch):
        """باج حقيقي كان ممكن يحصل هنا لولا القفل: لو كاشيرين مختلفين ضغطوا
        تشيك-إن على نفس الموقع في نفس اللحظة، من غير SELECT FOR UPDATE
        NOWAIT الاتنين كانوا ممكن يعدّوا فحص status=='available' بنفس القيمة
        القديمة، ويتسبب double check-in فعلي (تذكرتين حقيقيتين على نفس
        الشمسية). هنا بنحاكي عملية تانية ماسكة القفل دلوقتي بمحاكاة
        OperationalError من الـ lock نفسه (نفس أسلوب test_concurrent_sale_
        raises_concurrency_error فوق)."""
        from sqlalchemy.exc import OperationalError

        branch = make_branch(db)
        loc = services.bulk_add_locations(db, branch.id, "umbrella", 1)[0]

        def _raise_locked(*_args, **_kwargs):
            raise OperationalError("SELECT ... FOR UPDATE NOWAIT", {}, Exception("could not obtain lock"))

        monkeypatch.setattr(crud, "lock_location_for_update", _raise_locked)

        with pytest.raises(services.BeachConcurrencyError, match="مشغول"):
            services.checkin_location(
                db, branch.id, loc.id, BeachLocationCheckinRequest(guests_count=1),
            )

    def test_lock_refreshes_stale_in_memory_status_not_just_db_lock(self, db):
        """نفس فئة test_lock_refreshes_stale_in_memory_capacity_not_just_db_lock
        فوق، بس على BeachLocation.status بدل BeachInventory.capacity_used —
        بيثبت إن lock_location_for_update بيرجّع الحالة الحقيقية المُعتمدة
        حديثًا (من جلسة تانية)، مش القيمة القديمة المخزّنة في identity map
        الجلسة الحالية. لولا .populate_existing() هنا، جلسة B كانت ممكن تشوف
        الموقع لسه 'available' بعد ما جلسة A خلصت شغلها فعليًا وعمِلت commit،
        وتتسبب في double check-in حقيقي رغم إن القفل نفسه اتاخد بنجاح."""
        from tests.conftest import TestingSessionLocal

        branch = make_branch(db)
        loc = services.bulk_add_locations(db, branch.id, "umbrella", 1)[0]
        location_id = loc.id

        dbA = TestingSessionLocal()
        dbB = TestingSessionLocal()
        try:
            locA = crud.get_location(dbA, location_id)
            locB = crud.get_location(dbB, location_id)
            assert locA.status == "available"
            assert locB.status == "available"

            # جلسة A تقفل، تسجّل دخول ضيف، تعتمد (commit) — الحالة الحقيقية
            # في الداتابيز بقت 'occupied' دلوقتي.
            lockedA = crud.lock_location_for_update(dbA, location_id)
            lockedA.status = "occupied"
            dbA.commit()

            # جلسة B تقفل بعد كده — لازم تشوف 'occupied' الحقيقية، مش
            # 'available' المخزّنة في identity map بتاعتها.
            lockedB = crud.lock_location_for_update(dbB, location_id)
            assert lockedB.status == "occupied", (
                "lock_location_for_update رجّع حالة قديمة من identity map "
                "الجلسة ('available') بدل الحالة الحقيقية المُعتمدة حديثًا "
                "('occupied') — القفل نفسه اتاخد بنجاح بس التحقق التالي هيكون "
                "غلط، وده بالظبط الباج اللي كان بيسمح بـ double check-in."
            )
        finally:
            dbB.rollback()
            dbA.close()
            dbB.close()
