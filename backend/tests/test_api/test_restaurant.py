"""
tests/test_api/test_restaurant.py
Integration tests for restaurant module.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.restaurant.schemas import OrderCreate, OrderItemCreate
from app.modules.restaurant import services, crud


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Restaurant Branch", name_ar="مطعم",
               code=f"RST-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_menu_item(db, branch, available=True, station="hot"):
    from app.modules.restaurant.models import MenuItem
    item = MenuItem(
        branch_id=branch.id,
        name="شاورما دجاج",
        price=Decimal("55.00"),
        is_available=available,
        station=station,
    )
    db.add(item)
    db.commit()
    return item


def make_table(db, branch, status="available"):
    from app.modules.restaurant.models import DiningTable
    t = DiningTable(
        branch_id=branch.id,
        table_number=f"T-{uuid.uuid4().hex[:6].upper()}",
        capacity=4,
        status=status,
    )
    db.add(t)
    db.commit()
    return t


def make_order(db, branch, item, table=None):
    data = OrderCreate(
        table_id=table.id if table else None,
        order_type="dine_in" if table else "takeaway",
        guests_count=2,
        items=[OrderItemCreate(menu_item_id=item.id, quantity=2)],
    )
    return services.create_order(db, branch.id, data, waiter_id=1)


def make_order_items(db, branch, items, table=None):
    """items: list of MenuItem — بيعمل طلب فيه صنف واحد من كل واحد فيهم."""
    data = OrderCreate(
        table_id=table.id if table else None,
        order_type="dine_in" if table else "takeaway",
        guests_count=2,
        items=[OrderItemCreate(menu_item_id=item.id, quantity=1) for item in items],
    )
    return services.create_order(db, branch.id, data, waiter_id=1)


class TestMenuItem:

    def test_create_menu_item(self, db):
        branch = make_branch(db)
        from app.modules.restaurant.models import MenuItem
        item = MenuItem(branch_id=branch.id, name="كوكاكولا",
                        price=Decimal("15.00"), is_available=True)
        db.add(item)
        db.flush()
        assert item.id is not None
        assert item.is_available is True

    def test_unavailable_item_raises(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch, available=False)
        data = OrderCreate(
            order_type="takeaway",
            items=[OrderItemCreate(menu_item_id=item.id, quantity=1)],
        )
        with pytest.raises(ValueError, match="غير متاح"):
            services.create_order(db, branch.id, data)

    def test_nonexistent_item_raises(self, db):
        branch = make_branch(db)
        data = OrderCreate(
            order_type="takeaway",
            items=[OrderItemCreate(menu_item_id=9999, quantity=1)],
        )
        with pytest.raises(ValueError):
            services.create_order(db, branch.id, data)


class TestOrder:

    def test_create_dine_in_order(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        table = make_table(db, branch)
        order = make_order(db, branch, item, table)
        assert order.order_number.startswith("ORD-")
        assert order.status == "open"
        assert order.order_type == "dine_in"
        assert order.subtotal > Decimal("0")
        assert order.vat_amount > Decimal("0")
        assert order.total > order.subtotal

    def test_create_dine_in_sets_table_occupied(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        table = make_table(db, branch)
        make_order(db, branch, item, table)
        db.refresh(table)
        assert table.status == "occupied"

    def test_create_takeaway_order(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        data = OrderCreate(
            order_type="takeaway",
            items=[OrderItemCreate(menu_item_id=item.id, quantity=1)],
        )
        order = services.create_order(db, branch.id, data)
        assert order.table_id is None
        assert order.order_type == "takeaway"

    def test_order_with_out_of_service_table_raises(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        table = make_table(db, branch, status="out_of_service")
        data = OrderCreate(
            table_id=table.id,
            order_type="dine_in",
            items=[OrderItemCreate(menu_item_id=item.id, quantity=1)],
        )
        with pytest.raises(ValueError, match="خارج الخدمة"):
            services.create_order(db, branch.id, data)

    def test_subtotal_correct(self, db):
        """subtotal = price * qty = 55 * 2 = 110"""
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        table = make_table(db, branch)
        order = make_order(db, branch, item, table)
        assert order.subtotal == Decimal("110.00")


class TestOrderStatus:

    def test_update_status_to_in_kitchen(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        order = make_order(db, branch, item)
        updated = services.update_order_status(db, order.id, "in_kitchen")
        assert updated.status == "in_kitchen"

    def test_pay_order_frees_table(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        table = make_table(db, branch)
        order = make_order(db, branch, item, table)
        services.update_order_status(db, order.id, "paid")
        db.refresh(table)
        assert table.status == "available"

    def test_pay_order_updates_linked_customer_stats(self, db):
        from app.modules.crm import services as crm_services
        from app.modules.crm.schemas import CustomerCreate

        branch = make_branch(db)
        customer = crm_services.create_customer(db, CustomerCreate(
            branch_id=branch.id, full_name="عميل مطعم دائم",
        ))
        assert customer.visits_count == 0
        assert customer.total_spent == Decimal("0")

        item = make_menu_item(db, branch)
        data = OrderCreate(
            order_type="takeaway", guests_count=1,
            items=[OrderItemCreate(menu_item_id=item.id, quantity=2)],
            customer_id=customer.id,
        )
        order = services.create_order(db, branch.id, data, waiter_id=1)
        services.update_order_status(db, order.id, "paid")

        db.refresh(customer)
        assert customer.visits_count == 1
        assert customer.total_spent == order.total

    def test_cancel_order_frees_table(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        table = make_table(db, branch)
        order = make_order(db, branch, item, table)
        services.update_order_status(db, order.id, "cancelled")
        db.refresh(table)
        assert table.status == "available"

    def test_cannot_change_paid_order_status(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        order = make_order(db, branch, item)
        services.update_order_status(db, order.id, "paid")
        with pytest.raises(ValueError, match="paid"):
            services.update_order_status(db, order.id, "in_kitchen")

    def test_cannot_change_cancelled_order_status(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        order = make_order(db, branch, item)
        services.update_order_status(db, order.id, "cancelled")
        with pytest.raises(ValueError, match="cancelled"):
            services.update_order_status(db, order.id, "open")

    def test_order_not_found_raises(self, db):
        with pytest.raises(ValueError):
            services.update_order_status(db, 9999, "paid")


def make_finance_accounts(db, branch):
    """يزرع 1100 (نقدية) و4200 (إيرادات المطعم) — الحسابين اللي
    restaurant.services بيدوّر عليهم بالكود عند ترحيل قيد الإيراد."""
    from app.modules.finance.models import Account
    cash = Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset")
    revenue = Account(branch_id=branch.id, code="4200", name="Restaurant Revenue", account_type="revenue")
    db.add_all([cash, revenue])
    db.commit()
    return cash, revenue


class TestRestaurantRevenueJournalPosting:
    """Gap حقيقي: دفع طلب مطعم كان يُنشئ FolioCharge(charge_type='restaurant')
    بس — من غير أي قيد يومية، فحساب 4200 كان صفر دايماً (حتى لو المطعم بيبيع
    فعلاً)."""

    def test_paying_order_posts_balanced_journal_entry(self, db):
        from app.modules.finance import crud as finance_crud
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        cash, revenue = make_finance_accounts(db, branch)
        order = make_order(db, branch, item)

        services.update_order_status(db, order.id, "paid")

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="restaurant")
        assert total == 1
        entry = entries[0]
        assert entry.source_id == order.id
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit == order.total

        db.refresh(cash)
        db.refresh(revenue)
        cash_line = next(l for l in entry.lines if l.account_id == cash.id)
        revenue_line = next(l for l in entry.lines if l.account_id == revenue.id)
        assert cash_line.debit == order.total
        assert revenue_line.credit == order.total

    def test_in_kitchen_transition_does_not_post_journal(self, db):
        """القيد لازم يترحّل بس عند الدفع، مش عند أي تغيير حالة تاني."""
        from app.modules.finance import crud as finance_crud
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        make_finance_accounts(db, branch)
        order = make_order(db, branch, item)

        services.update_order_status(db, order.id, "in_kitchen")

        _, total = finance_crud.list_journal_entries(db, branch.id, source="restaurant")
        assert total == 0

    def test_missing_accounts_does_not_block_payment(self, db):
        """لو الحسابات مش موجودة، الدفع لازم ينجح عادي — نفس فلسفة
        pms._post_checkout_journal (الفشل المحاسبي ميوقفش العملية الأساسية)."""
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        order = make_order(db, branch, item)

        paid = services.update_order_status(db, order.id, "paid")
        assert paid.status == "paid"

        from app.modules.finance import crud as finance_crud
        _, total = finance_crud.list_journal_entries(db, branch.id, source="restaurant")
        assert total == 0


def make_linked_product(db, branch, initial_stock=Decimal("50")):
    """يزرع warehouse + product ويربطهم بصنف قائمة جديد، مع تخزين ابتدائي
    (StockMovement نوع purchase_in) — عشان نقدر نتحقق من الخصم عند الدفع."""
    from app.modules.inventory.schemas import ProductCreate, StockMovementCreate, WarehouseCreate
    from app.modules.inventory import services as inventory_services
    from datetime import datetime as _dt

    warehouse = inventory_services.create_warehouse(
        db, WarehouseCreate(branch_id=branch.id, name="Main WH", code=f"WH-{uuid.uuid4().hex[:6].upper()}"),
    )
    product = inventory_services.create_product(
        db, ProductCreate(
            branch_id=branch.id, warehouse_id=warehouse.id,
            name="لحم برجر", sku=f"BRG-{uuid.uuid4().hex[:6].upper()}", unit="piece",
            cost_price=Decimal("10"),
        ),
    )
    if initial_stock > 0:
        inventory_services.record_movement(
            db, StockMovementCreate(
                branch_id=branch.id, product_id=product.id, warehouse_id=warehouse.id,
                movement_type="purchase_in", quantity=initial_stock, unit_cost=Decimal("10"),
                moved_at=_dt.utcnow(),
            ), moved_by=1,
        )
    db.refresh(product)

    from app.modules.restaurant.models import MenuItem
    item = MenuItem(
        branch_id=branch.id, name="برجر لحم", price=Decimal("120.00"),
        is_available=True, linked_product_id=product.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item, product


class TestRestaurantInventoryDeduction:
    """Gap حقيقي: دفع طلب مطعم كان لا يخصم أي حاجة من المخزون أبداً — حتى لو
    الصنف بيستهلك مكونات حقيقية (لحم/خضار/إلخ). MenuItem مكانش فيه أي ربط
    بـ inventory.Product خالص قبل كده."""

    def test_paying_order_deducts_linked_product_stock(self, db):
        branch = make_branch(db)
        item, product = make_linked_product(db, branch, initial_stock=Decimal("50"))
        order = make_order(db, branch, item)  # quantity=2 (see make_order helper)

        services.update_order_status(db, order.id, "paid")

        db.refresh(product)
        assert product.current_stock == Decimal("48.000")

    def test_paying_order_with_unlinked_item_does_not_touch_inventory(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)  # no linked_product_id
        order = make_order(db, branch, item)

        paid = services.update_order_status(db, order.id, "paid")
        assert paid.status == "paid"  # لا استثناء، والصنف بيتجاوز بصمت

    def test_insufficient_stock_does_not_block_payment(self, db):
        """رصيد غير كافٍ لازم يتجاوز بصمت — الدفع لازم ينجح عادي (نفس فلسفة
        عدم إيقاف العملية الأساسية بسبب فشل جانبي)."""
        branch = make_branch(db)
        item, product = make_linked_product(db, branch, initial_stock=Decimal("1"))
        order = make_order(db, branch, item)  # quantity=2 > stock (1)

        paid = services.update_order_status(db, order.id, "paid")
        assert paid.status == "paid"

        db.refresh(product)
        assert product.current_stock == Decimal("1.000")  # لم يتغيّر — رُفض الخصم بصمت

    def test_cancelled_item_is_skipped(self, db):
        branch = make_branch(db)
        item, product = make_linked_product(db, branch, initial_stock=Decimal("50"))
        order = make_order(db, branch, item)
        order_item = order.items[0]
        crud.void_order_item(db, order_item, "طلب العميل", voided_by=1)
        db.commit()

        services.update_order_status(db, order.id, "paid")

        db.refresh(product)
        assert product.current_stock == Decimal("50.000")  # الصنف الملغى ميتخصمش


class TestKDS:

    def test_order_in_kitchen_creates_ticket(self, db):
        """لما الطلب يتحول لـ in_kitchen، لازم يتعمل KitchenTicket بمحطة الصنف الحقيقية."""
        from app.modules.restaurant.models import KitchenTicket
        branch = make_branch(db)
        item = make_menu_item(db, branch, station="grill")
        order = make_order(db, branch, item)
        services.update_order_status(db, order.id, "in_kitchen")
        tickets = db.query(KitchenTicket).filter(KitchenTicket.order_id == order.id).all()
        assert len(tickets) == 1
        assert tickets[0].station == "grill"
        assert tickets[0].module == "restaurant"
        assert tickets[0].status == "pending"
        assert isinstance(tickets[0].items_snapshot, list)
        assert len(tickets[0].items_snapshot) > 0

    def test_order_splits_into_one_ticket_per_station(self, db):
        """طلب فيه أصناف من محطات مختلفة (hot/grill/bar) لازم يتقسم لتذكرة منفصلة لكل محطة."""
        from app.modules.restaurant.models import KitchenTicket
        branch = make_branch(db)
        hot_item = make_menu_item(db, branch, station="hot")
        grill_item = make_menu_item(db, branch, station="grill")
        bar_item = make_menu_item(db, branch, station="bar")
        order = make_order_items(db, branch, [hot_item, grill_item, bar_item])
        services.update_order_status(db, order.id, "in_kitchen")

        tickets = db.query(KitchenTicket).filter(KitchenTicket.order_id == order.id).all()
        stations = {t.station for t in tickets}
        assert stations == {"hot", "grill", "bar"}
        for ticket in tickets:
            assert len(ticket.items_snapshot) == 1  # صنف واحد بس لكل تذكرة محطة

    def test_cancelled_item_excluded_from_kitchen_ticket(self, db):
        """صنف ملغى قبل ما الطلب يروح للمطبخ ميظهرش في تذكرة الـ KDS."""
        from app.modules.restaurant.models import KitchenTicket
        branch = make_branch(db)
        hot_item = make_menu_item(db, branch, station="hot")
        grill_item = make_menu_item(db, branch, station="grill")
        order = make_order_items(db, branch, [hot_item, grill_item])
        crud.void_order_item(db, order.items[1], "غلط في الطلب", voided_by=1)
        db.commit()

        services.update_order_status(db, order.id, "in_kitchen")
        tickets = db.query(KitchenTicket).filter(KitchenTicket.order_id == order.id).all()
        assert len(tickets) == 1
        assert tickets[0].station == "hot"

    def test_update_ticket_status(self, db):
        """يحدّث حالة التذكرة من pending إلى done."""
        from app.modules.restaurant.models import KitchenTicket
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        order = make_order(db, branch, item)
        services.update_order_status(db, order.id, "in_kitchen")
        ticket = db.query(KitchenTicket).filter(KitchenTicket.order_id == order.id).first()
        assert ticket is not None
        updated = crud.update_ticket_status(db, ticket.id, "done")
        db.commit()
        assert updated.status == "done"
        # verifica che il ticket non sia più nelle pending list
        pending = crud.list_pending_tickets(db, branch.id, module="restaurant")
        assert not any(t.id == ticket.id for t in pending)

    def test_get_kds_tickets_module_isolation(self, db):
        """services.get_kds_tickets بموديول 'cafe' لازم ميرجّعش تذاكر المطعم، والعكس."""
        from app.modules.restaurant.models import KitchenTicket
        branch = make_branch(db)
        item = make_menu_item(db, branch, station="hot")
        order = make_order(db, branch, item)
        services.update_order_status(db, order.id, "in_kitchen")

        cafe_ticket = KitchenTicket(
            branch_id=branch.id, order_id=999, module="cafe",
            station="bar", items_snapshot=[], status="pending",
        )
        db.add(cafe_ticket)
        db.commit()

        restaurant_only = services.get_kds_tickets(db, branch.id, module="restaurant")
        assert all(t.module == "restaurant" for t in restaurant_only)
        assert any(t.order_id == order.id for t in restaurant_only)

        cafe_only = services.get_kds_tickets(db, branch.id, module="cafe")
        assert all(t.module == "cafe" for t in cafe_only)
        assert any(t.id == cafe_ticket.id for t in cafe_only)
        assert not any(t.order_id == order.id for t in cafe_only)


class TestChargeToRoom:
    """الدفع على حساب الغرفة — طلب مطعم لضيف مقيم بيتحمّل على فوليو الحجز
    بدل ما ياخد كاش فوري، ويتحاسب مع باقي مشترياته وقت خروجه."""

    def _make_checked_in_booking(self, db, branch):
        import uuid as _uuid
        from datetime import date as _date, timedelta as _td
        from app.modules.pms.models import Room, RoomType
        from app.modules.pms.schemas import BookingCreate
        from app.modules.pms import services as pms_services

        rt = RoomType(branch_id=branch.id, name="Standard", base_rate=Decimal("500.00"), max_occupancy=2)
        db.add(rt); db.flush()
        room = Room(branch_id=branch.id, room_type_id=rt.id, name=f"R-{_uuid.uuid4().hex[:6].upper()}",
                    floor=1, status="available")
        db.add(room); db.flush()

        data = BookingCreate(
            branch_id=branch.id, guest_name="ضيف مقيم", guest_phone="01000000001",
            check_in=_date.today(), check_out=_date.today() + _td(days=2),
            adults=2, children=0, room_ids=[room.id],
        )
        booking = pms_services.create_booking(db, data)
        booking = pms_services.checkin_booking(db, booking.id)
        return booking, room

    def test_checkin_opens_a_folio(self, db):
        branch = make_branch(db)
        booking, _ = self._make_checked_in_booking(db, branch)
        assert booking.folio_id is not None

    def test_charge_order_to_room_adds_folio_charge_not_cash(self, db):
        from app.modules.finance import crud as finance_crud

        branch = make_branch(db)
        booking, room = self._make_checked_in_booking(db, branch)
        item = make_menu_item(db, branch)
        order = make_order(db, branch, item)

        paid = services.update_order_status(db, order.id, "paid", charge_to_room_id=room.id)
        assert paid.folio_id == booking.folio_id

        folio = finance_crud.get_folio(db, booking.folio_id)
        charges = folio.charges
        assert any(c.ref_order_id == order.id for c in charges)
        matching = next(c for c in charges if c.ref_order_id == order.id)
        assert matching.amount == order.subtotal

        # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-04): folio.total (العمود
        # المخزّن اللي GET /finance/folios بيرجّعه مباشرة) كان بيفضل صفر —
        # add_charge لوحدها كانت بتضيف صف الشحنة بس من غير ما تعيد حساب
        # الإجمالي المخزّن على الفوليو نفسه.
        # ⚠️ باج تاني اتصلح كمان: matching.service_charge كان دايمًا صفر
        # (order.service_charge كان بيضيع قبل ما يوصل للفوليو خالص) — بقى
        # جزء أساسي من إجمالي الفوليو زي المفروض.
        db.refresh(folio)
        assert matching.service_charge == order.service_charge
        assert folio.total == matching.amount + matching.vat_amount + matching.service_charge

        # مفيش قيد كاش فوري اتسجل لأوردر اتحمّل على الغرفة
        entries, total = finance_crud.list_journal_entries(db, branch.id, source="restaurant")
        assert total == 0

    def test_charge_to_room_fails_for_empty_room(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)
        order = make_order(db, branch, item)
        with pytest.raises(ValueError, match="مفيش ضيف مسجّل دخول"):
            services.update_order_status(db, order.id, "paid", charge_to_room_id=99999)


class TestVoidItemDiscountRecompute:
    """باج حقيقي (اتصلح 2026-07-05، اتلقى أثناء اختبار حي لسير عمل الكاشير):
    لو خصم اتطبّق على الطلب الأول وبعدين اتلغى صنف، discount_amount كان
    بيفضل نفس المبلغ الثابت القديم (محسوب على subtotal الأكبر) بدل ما يتحسب
    تاني على subtotal الجديد الأصغر — يعني نسبة الخصم الفعلية بعد الإلغاء
    كانت بتكبر عن اللي القاعدة سمحت بيه (تسريب إيراد بسيط)، وأي شرط أهلية
    (زي total_amount>=500) كان ممكن يفضل متحقق بالغلط."""

    def _make_order_with_percentage_discount(self, db, branch, item):
        from app.modules.finance.models import ConditionalDiscount

        rule = ConditionalDiscount(
            branch_id=branch.id, condition_type="total_amount", condition_value=">=0",
            discount_type="percentage", discount_value=Decimal("10"),
            valid_from=date(2020, 1, 1), valid_until=date(2099, 12, 31),
        )
        db.add(rule)
        db.commit()

        order = make_order_items(db, branch, [item, item])  # 2 قطع من نفس الصنف، كل واحدة سطر منفصل
        return services.apply_order_discount(db, order.id)

    def test_discount_recomputed_on_new_lower_subtotal_after_void(self, db):
        branch = make_branch(db)
        item = make_menu_item(db, branch)  # 55.00 EGP لكل قطعة (make_menu_item default)
        order = self._make_order_with_percentage_discount(db, branch, item)

        # قبل الإلغاء: subtotal = 55*2*2(quantity لكل سطر) — نتأكد إن الخصم 10% فعليًا
        expected_discount_before = (order.subtotal * Decimal("10") / Decimal("100")).quantize(Decimal("0.01"))
        assert order.discount_amount == expected_discount_before
        assert order.applied_discount_rule_id is not None

        # نلغي أول صنف في الطلب — الـ subtotal المفروض يصغر
        first_item_id = order.items[0].id
        updated = services.void_order_item(db, order.id, first_item_id, "غلط في الطلب", voided_by=1)

        # الخصم لازم يتحسب تاني على الـ subtotal الجديد الأصغر — مش يفضل
        # الرقم القديم زي ما هو
        expected_discount_after = (updated.subtotal * Decimal("10") / Decimal("100")).quantize(Decimal("0.01"))
        assert updated.discount_amount == expected_discount_after
        assert updated.discount_amount < expected_discount_before
        assert updated.total == max(
            Decimal("0"),
            updated.subtotal + updated.vat_amount + updated.service_charge - updated.discount_amount,
        )

    def test_discount_zeroed_when_no_longer_eligible_after_void(self, db):
        from app.modules.finance.models import ConditionalDiscount

        branch = make_branch(db)
        item = make_menu_item(db, branch)  # 55.00 EGP

        # قاعدة بتتطلب subtotal >= 100 — منطبقة على طلب فيه صنفين (110) بس
        # مش هتفضل منطبقة بعد إلغاء واحد (55 < 100)
        rule = ConditionalDiscount(
            branch_id=branch.id, condition_type="total_amount", condition_value=">=100",
            discount_type="percentage", discount_value=Decimal("10"),
            valid_from=date(2020, 1, 1), valid_until=date(2099, 12, 31),
        )
        db.add(rule)
        db.commit()

        order = make_order_items(db, branch, [item, item])
        order = services.apply_order_discount(db, order.id)
        assert order.discount_amount > 0

        updated = services.void_order_item(db, order.id, order.items[0].id, "غلط", voided_by=1)

        assert updated.discount_amount == Decimal("0")
        assert updated.applied_discount_rule_id is None
