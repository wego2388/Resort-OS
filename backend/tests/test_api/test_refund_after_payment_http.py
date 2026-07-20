"""
tests/test_api/test_refund_after_payment_http.py
HTTP-level tests for the post-payment refund flow — dining (unified outlet).

Confirmed real gap (2026-07-04, restaurant/cafe at the time): void_order_item
raised "لا يمكن إلغاء صنف من طلب 'paid' — استخدم مرتجع بعد الدفع" (use a
refund after payment) whenever anyone tried to void an item on an
already-paid order — but no refund-after-payment feature existed anywhere
in the codebase. A real per-item refund endpoint was added that reverses
the financial impact (a reversing journal entry for cash sales, or a
reduced folio charge for Charge-to-Room orders) without mutating the
original paid order's historical totals.

راجع DINING_CUTOVER_PLAN.md Batch 6 — بورتت من restaurant/cafe (اللي
اتحذفوا) لـ dining الموحّد. restaurant/cafe كانوا موديولين منفصلين
(نفس المنطق مكرر مرتين)؛ dining بيغطي الاتنين بـ outlet_type واحد، فالكلاس
هنا واحد بدل TestRestaurantRefundAfterPayment/TestCafeRefundAfterPayment.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Refund HTTP Branch", name_ar="فرع اختبار مرتجع",
               code=f"RFD-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_outlet_committed(db, branch):
    from app.modules.dining import services as dining_services
    from app.modules.dining.schemas import OutletCreate
    return dining_services.create_outlet(db, OutletCreate(
        branch_id=branch.id, name="مطعم اختبار مرتجع", outlet_type="restaurant",
        revenue_account_code="4200",
    ))


def make_item_committed(db, branch, outlet, price=Decimal("100.00")):
    from app.modules.dining.models import DiningItem
    item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="برجر اختبار",
                       price=price, is_available=True)
    db.add(item)
    db.commit()
    return item


def make_finance_accounts(db, branch, revenue_code="4200"):
    """كل حسابات الأستاذ اللي معاملة الدفع الصارمة (Gate 1B) محتاجاها فعليًا
    (زائد 1150/1200/5200 اللي بقوا مطلوبين بعد ما post_simple_revenue_journal/
    _post_cogs_journal بقوا يرفعوا FinancialConfigurationError بدل ما
    يبتلعوا الفشل بصمت وقت الدفع الصارم) — idempotent."""
    from app.modules.finance.models import Account
    wanted = {
        "1100": ("Cash", "asset"),
        "1150": ("ذمم الفوليو", "asset"),
        "1200": ("مخزون البضاعة", "asset"),
        "5200": ("تكلفة البضاعة المباعة (COGS)", "expense"),
        revenue_code: ("Restaurant Revenue", "revenue"),
    }
    accounts = {}
    for code, (name, acc_type) in wanted.items():
        acc = db.query(Account).filter_by(branch_id=branch.id, code=code).first()
        if not acc:
            acc = Account(branch_id=branch.id, code=code, name=name, account_type=acc_type)
            db.add(acc)
        accounts[code] = acc
    db.commit()
    return accounts["1100"], accounts[revenue_code]


def make_branch_linked_headers(db, branch, role="waiter") -> dict[str, str]:
    """Gate 1B: PATCH /dining/orders/{id}/status بقى بيفرض assert_branch_access
    على كل تحويل حالة — waiter_headers/cashier_headers/manager_headers المشتركة
    (conftest.py) بلا Employee/فرع خالص، فمحتاجين مستخدم Employee-linked جديد."""
    from datetime import date, timedelta
    from decimal import Decimal as _D
    from tests.conftest import _create_test_user, _make_token, open_cashier_shift
    from app.modules.hr.models import Employee

    email = f"{role}-{uuid.uuid4().hex[:10]}@test.local"
    user_id = _create_test_user(email, role)
    emp = Employee(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name=f"{role} اختبار مرتجع", national_id="29001011234567",
        position=role, department="F&B", basic_salary=_D("4000.00"),
        hire_date=date.today() - timedelta(days=365), user_id=user_id,
    )
    db.add(emp)
    db.commit()
    # Gate 4A: أي مشغّل POS بيحصّل دفع مباشر لازم يكون له وردية مفتوحة.
    open_cashier_shift(db, branch.id, user_id)
    return {"Authorization": f"Bearer {_make_token(email)}"}


def _refund_headers(client, headers, *, order_id, item_id, reason):
    """Gate 4 (جولة مراجعة Codex الأولى — M5a): مرتجع بعد الدفع بقى محتاج
    step-up proof فوق صلاحية مدير+ العادية — راجع
    app.core.kernel.auth.step_up.dining_refund_scope. الحسابات هنا (manager،
    من _create_test_user من غير 2FA) مش محتاجة totp_code."""
    from tests.conftest import _issue_step_up
    token = _issue_step_up(
        client, headers, purpose="dining_refund",
        intent={"order_id": order_id, "item_id": item_id, "reason": reason},
    )
    return {**headers, "X-Step-Up-Token": token}


def make_room_and_folio(db, branch):
    """يعمل حجز حقيقي checked_in (booking → checkin_booking) بدل ما ينشئ
    Room/Folio منفصلين — find_active_folio_for_room بتدوّر فعليًا على
    Booking(status=checked_in) + BookingRoom، مش على Folio لوحدها."""
    from datetime import date as _date, timedelta as _td
    from app.modules.pms.models import Room, RoomType
    from app.modules.pms import services as pms_services
    from app.modules.pms.schemas import BookingCreate

    rt = RoomType(branch_id=branch.id, name=f"RT-{uuid.uuid4().hex[:6]}", base_rate=Decimal("500.00"), max_occupancy=2)
    db.add(rt); db.flush()
    room = Room(branch_id=branch.id, room_type_id=rt.id, name=f"R-{uuid.uuid4().hex[:6].upper()}",
                floor=1, status="available")
    db.add(room); db.flush()

    booking = pms_services.create_booking(db, BookingCreate(
        branch_id=branch.id, guest_name="نزيل اختبار مرتجع", guest_phone="01000000002",
        check_in=_date.today(), check_out=_date.today() + _td(days=2),
        adults=2, children=0, room_ids=[room.id],
    ))
    booking = pms_services.checkin_booking(db, booking.id)

    from app.modules.finance import crud as finance_crud
    folio = finance_crud.get_folio(db, booking.folio_id)
    return room, folio


class TestDiningRefundAfterPayment:
    def _create_paid_order(self, client, db, branch, outlet, item, headers_waiter, headers_cashier, qty=1):
        # Gate 1B: PATCH .../status بقى بيفرض assert_branch_access — الـ headers
        # المشتركة (conftest.py) بلا Employee/فرع، فمحتاجين نسخة Employee-linked
        # لهذا الفرع تحديدًا للتحويلين (in_kitchen/paid).
        linked_waiter = make_branch_linked_headers(db, branch, "waiter")
        linked_cashier = make_branch_linked_headers(db, branch, "cashier")
        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway", "guests_count": 1,
                  "items": [{"item_id": item.id, "quantity": qty}]},
            headers=headers_waiter,
        ).json()
        client.patch(f"/api/v1/dining/orders/{order['id']}/status",
                     json={"status": "in_kitchen"}, headers=linked_waiter)
        paid = client.patch(f"/api/v1/dining/orders/{order['id']}/status",
                            json={"status": "paid"}, headers=linked_cashier)
        assert paid.status_code == 200, paid.text
        return paid.json()

    def test_refund_requires_manager_level_not_cashier(self, client: TestClient, db, waiter_headers, cashier_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        make_finance_accounts(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._create_paid_order(client, db, branch, outlet, item, waiter_headers, cashier_headers)
        item_id = order["items"][0]["id"]

        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": "الأكل كان بايظ"},
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_refund_without_step_up_token_rejected(
        self, client: TestClient, db, waiter_headers, cashier_headers,
    ):
        """Gate 4 (جولة مراجعة Codex الأولى — M5a): مدير معتمد فرعيًا صح
        (يعدّي assert_branch_access) بس من غير X-Step-Up-Token → 428، مش 200
        ولا 400. يثبت الحماية الجديدة فعليًا شغالة، مش بس موجودة في الكود."""
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        make_finance_accounts(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._create_paid_order(client, db, branch, outlet, item, waiter_headers, cashier_headers)
        item_id = order["items"][0]["id"]

        linked_manager = make_branch_linked_headers(db, branch, "manager")
        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": "من غير step-up"},
            headers=linked_manager,
        )
        assert resp.status_code == 428
        assert resp.json()["detail"]["error_code"] == "STEP_UP_REQUIRED"

    def test_refund_with_step_up_token_for_different_item_rejected(
        self, client: TestClient, db, waiter_headers, cashier_headers,
    ):
        """proof مربوط بـ(order_id, item_id, reason) بالظبط — proof اتاخد
        لصنف A ما يشتغلش لصنف B، حتى لو بنفس الطلب ونفس السبب."""
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        make_finance_accounts(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._create_paid_order(client, db, branch, outlet, item, waiter_headers, cashier_headers, qty=2)
        item_id = order["items"][0]["id"]
        reason = "محاولة إعادة استخدام proof لصنف تاني"

        linked_manager = make_branch_linked_headers(db, branch, "manager")
        # proof حقيقي، بس مربوط بـitem_id مختلف (وهمي) عن اللي هنستخدمه فعليًا.
        headers_wrong_item = _refund_headers(
            client, linked_manager, order_id=order["id"], item_id=item_id + 999, reason=reason,
        )
        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": reason},
            headers=headers_wrong_item,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["error_code"] == "STEP_UP_INVALID"

    def test_refund_marks_item_refunded_and_tracks_amount(
        self, client: TestClient, db, waiter_headers, cashier_headers, manager_headers,
    ):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        make_finance_accounts(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._create_paid_order(client, db, branch, outlet, item, waiter_headers, cashier_headers)
        item_id = order["items"][0]["id"]
        original_total = Decimal(str(order["total"]))

        # High 5: المرتجع بقى بيفرض assert_branch_access — مدير مربوط بالفرع.
        linked_manager = make_branch_linked_headers(db, branch, "manager")
        reason = "الأكل كان بايظ"
        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": reason},
            headers=_refund_headers(client, linked_manager, order_id=order["id"], item_id=item_id, reason=reason),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["items"][0]["status"] == "refunded"
        assert body["items"][0]["voided_reason"] == "الأكل كان بايظ"
        # الطلب الوحيد فيه صنف واحد بس، فبمجرد ما يترجع الطلب كله بيبقى refunded
        assert body["status"] == "refunded"
        assert Decimal(str(body["refunded_amount"])) == original_total
        # totals الأصلية (subtotal/vat/service/total) لازم تفضل زي ما هي — سجل تاريخي
        assert Decimal(str(body["total"])) == original_total

    def test_refund_cross_branch_manager_rejected(
        self, client: TestClient, db, waiter_headers, cashier_headers,
    ):
        """High 5 (جولة مراجعة Codex الأولى): مدير مربوط بفرع تاني مايقدرش
        يسترجع صنف من طلب فرع مختلف (assert_branch_access → 403)، حتى لو
        عنده صلاحية refund. نفس-الفرع بيرجّع 200 (مغطّى في التستات فوق)."""
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        make_finance_accounts(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._create_paid_order(client, db, branch, outlet, item, waiter_headers, cashier_headers)
        item_id = order["items"][0]["id"]

        # مدير مربوط بفرع تاني تمامًا.
        other_branch = make_branch_committed(db)
        cross_branch_manager = make_branch_linked_headers(db, other_branch, "manager")
        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": "محاولة من فرع تاني"},
            headers=cross_branch_manager,
        )
        assert resp.status_code == 403, resp.text

    def test_refund_rejected_for_unpaid_order(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway", "guests_count": 1,
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        item_id = order["items"][0]["id"]

        linked_manager = make_branch_linked_headers(db, branch, "manager")
        reason = "اختبار"
        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": reason},
            headers=_refund_headers(client, linked_manager, order_id=order["id"], item_id=item_id, reason=reason),
        )
        assert resp.status_code == 400
        assert "مدفوعة" in resp.json()["detail"] or "المرتجع" in resp.json()["detail"]

    def test_double_refund_rejected(self, client: TestClient, db, waiter_headers, cashier_headers, manager_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        make_finance_accounts(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._create_paid_order(client, db, branch, outlet, item, waiter_headers, cashier_headers)
        item_id = order["items"][0]["id"]

        linked_manager = make_branch_linked_headers(db, branch, "manager")
        first = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": "الأول"},
            headers=_refund_headers(client, linked_manager, order_id=order["id"], item_id=item_id, reason="الأول"),
        )
        assert first.status_code == 200, first.text

        second = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": "التاني"},
            headers=_refund_headers(client, linked_manager, order_id=order["id"], item_id=item_id, reason="التاني"),
        )
        assert second.status_code == 400

    def test_refund_posts_reversal_journal_entry_for_cash_sale(
        self, client: TestClient, db, waiter_headers, cashier_headers, manager_headers,
    ):
        from app.modules.finance import crud as finance_crud
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        cash, rest_rev = make_finance_accounts(db, branch)
        item = make_item_committed(db, branch, outlet)
        order = self._create_paid_order(client, db, branch, outlet, item, waiter_headers, cashier_headers)
        item_id = order["items"][0]["id"]

        linked_manager = make_branch_linked_headers(db, branch, "manager")
        reason = "اختبار عكس القيد"
        client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": reason},
            headers=_refund_headers(client, linked_manager, order_id=order["id"], item_id=item_id, reason=reason),
        )

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="dining_refund")
        assert total == 1
        entry = entries[0]
        total_debit = sum(l.debit for l in entry.lines)
        total_credit = sum(l.credit for l in entry.lines)
        assert total_debit == total_credit
        db.refresh(cash); db.refresh(rest_rev)
        cash_line = next(l for l in entry.lines if l.account_id == cash.id)
        rev_line = next(l for l in entry.lines if l.account_id == rest_rev.id)
        assert cash_line.credit == total_debit  # كاش خرج
        assert rev_line.debit == total_debit    # إيراد اتعكس

    def test_refund_reduces_room_folio_charge(self, client: TestClient, db, waiter_headers, cashier_headers, manager_headers):
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        make_finance_accounts(db, branch)
        room, folio = make_room_and_folio(db, branch)
        item = make_item_committed(db, branch, outlet)
        linked_waiter = make_branch_linked_headers(db, branch, "waiter")
        linked_cashier = make_branch_linked_headers(db, branch, "cashier")

        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway", "guests_count": 1,
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        client.patch(f"/api/v1/dining/orders/{order['id']}/status",
                     json={"status": "in_kitchen"}, headers=linked_waiter)
        paid = client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "paid", "charge_to_room_id": room.id},
            headers=linked_cashier,
        ).json()
        item_id = paid["items"][0]["id"]

        db.refresh(folio)
        assert folio.total > Decimal("0")

        linked_manager = make_branch_linked_headers(db, branch, "manager")
        reason = "الأكل رجع"
        client.patch(
            f"/api/v1/dining/orders/{paid['id']}/items/{item_id}/refund",
            json={"reason": reason},
            headers=_refund_headers(client, linked_manager, order_id=paid["id"], item_id=item_id, reason=reason),
        )

        db.refresh(folio)
        assert folio.total == Decimal("0.00")

    def test_refund_does_not_touch_a_different_folio_charge_with_same_ref_order_id(
        self, client: TestClient, db, waiter_headers, cashier_headers, manager_headers,
    ):
        """Regression: _reduce_folio_charge_for_refund كانت بتفلتر بـ
        ref_order_id بس (في restaurant الأصلي) — رقم PK جدول Order، مش
        فريد عبر الموديولات (نفس الرقم ممكن يتكرر كـ ref_order_id على
        FolioCharge تانية جوه فوليو ضيف مختلف تمامًا). dining.services
        بتفلتر بـ charge_type='dining' + folio_id كمان — التست ده بيتأكد
        إن الفلترة دي لسه شغالة صح."""
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        make_finance_accounts(db, branch)
        room, folio = make_room_and_folio(db, branch)
        item = make_item_committed(db, branch, outlet)
        linked_cashier = make_branch_linked_headers(db, branch, "cashier")

        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway", "guests_count": 1,
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        # فوليو/شحنة تانية تمامًا بنفس ref_order_id بالظبط عمدًا، ومتعمولة
        # قبل شحنة الطلب الحقيقية (PK أصغر) — عشان لو الفلترة القديمة
        # (ref_order_id بس، من غير charge_type/folio_id) رجعت، الـ .first()
        # كان هيرجّع الـ decoy دي غلط بدل الشحنة الصح.
        from app.modules.finance import crud as finance_crud
        from app.modules.finance.schemas import FolioCreate, FolioChargeCreate
        decoy_folio = finance_crud.create_folio(db, FolioCreate(
            branch_id=branch.id, guest_name="ضيف تاني", check_in=datetime.utcnow(),
            check_out=datetime.utcnow() + timedelta(days=1),
        ))
        db.commit()
        decoy_charge = finance_crud.add_charge(db, decoy_folio.id, FolioChargeCreate(
            charge_type="dining", description="كابتشينو decoy",
            amount=Decimal("50.00"), vat_amount=Decimal("7.00"), service_charge=Decimal("6.00"),
            posted_at=datetime.utcnow(), ref_order_id=order["id"],  # نفس ref_order_id عمدًا
        ))
        finance_crud.recalculate_folio_total(db, decoy_folio)
        db.commit()
        decoy_total_before = decoy_folio.total
        assert decoy_total_before == Decimal("63.00")

        paid = client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "paid", "charge_to_room_id": room.id},
            headers=linked_cashier,
        ).json()
        item_id = paid["items"][0]["id"]

        linked_manager = make_branch_linked_headers(db, branch, "manager")
        reason = "الأكل رجع"
        client.patch(
            f"/api/v1/dining/orders/{paid['id']}/items/{item_id}/refund",
            json={"reason": reason},
            headers=_refund_headers(client, linked_manager, order_id=paid["id"], item_id=item_id, reason=reason),
        )

        db.refresh(folio)
        assert folio.total == Decimal("0.00")  # فوليو الطلب اترجع صح

        db.refresh(decoy_folio)
        db.refresh(decoy_charge)
        assert decoy_folio.total == decoy_total_before  # فوليو الضيف التاني متلمسش خالص

    # ── High 3/4 (جولة مراجعة Codex الأولى): عكس المرتجع بالـ tenders الفعلية ──

    def test_split_cash_room_refund_reverses_both_portions_proportionally(
        self, client: TestClient, db, waiter_headers,
    ):
        """High 3: طلب split (كاش + غرفة) لما يترجع لازم يعكس *الجزئين*
        بالتناسب — الباج القديم كان بيعكس حصة الغرفة بس (folio_id set) ويسيب
        الكاش من غير عكس خالص. هنا: كاش 63 + غرفة 63 لطلب إجماليه 126؛ المرتجع
        الكامل لازم يعمل (أ) Payment كاش سالب −63، و(ب) خفض شحنة الفوليو 63."""
        from app.modules.finance.models import Payment
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        make_finance_accounts(db, branch)
        room, folio = make_room_and_folio(db, branch)
        item = make_item_committed(db, branch, outlet, price=Decimal("100.00"))
        linked_cashier = make_branch_linked_headers(db, branch, "cashier")
        linked_waiter = make_branch_linked_headers(db, branch, "waiter")

        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "dine_in", "guests_count": 1,
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        client.patch(f"/api/v1/dining/orders/{order['id']}/status",
                     json={"status": "in_kitchen"}, headers=linked_waiter)
        # الإجمالي 126 (100 + 14% ضريبة + 12% خدمة) — نصفين 63/63.
        order_total = Decimal(str(order["total"]))
        assert order_total == Decimal("126.00")
        half = Decimal("63.00")
        split = client.post(
            f"/api/v1/dining/orders/{order['id']}/split-bill",
            json={"payments": [
                {"amount": float(half), "payment_method": "cash"},
                {"amount": float(half), "payment_method": "room", "charge_to_room_id": room.id},
            ]},
            headers=linked_cashier,
        )
        assert split.status_code == 200, split.text
        item_id = split.json()["items"][0]["id"]

        db.refresh(folio)
        assert folio.total == half  # حصة الغرفة اتحمّلت (63)

        linked_manager = make_branch_linked_headers(db, branch, "manager")
        refund_reason = "مرتجع طلب split"
        refund = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": refund_reason},
            headers=_refund_headers(client, linked_manager, order_id=order["id"], item_id=item_id, reason=refund_reason),
        )
        assert refund.status_code == 200, refund.text

        # (أ) عكس مباشر: Payment كاش سالب بحصته المتناسبة (−63).
        neg = (
            db.query(Payment)
            .filter(Payment.ref_order_id == order["id"], Payment.source == "dining_refund",
                    Payment.amount < 0)
            .all()
        )
        assert len(neg) == 1
        assert neg[0].method == "cash"
        assert neg[0].amount == Decimal("-63.00")
        # (ب) حصة الغرفة: شحنة الفوليو اترجعت (63 → 0).
        db.refresh(folio)
        assert folio.total == Decimal("0.00")

    def test_card_tender_refund_posts_against_card_clearing_account_not_cash(
        self, client: TestClient, db, waiter_headers, monkeypatch,
    ):
        """High 4b: مرتجع طلب مدفوع ببطاقة لازم يعكس على *حساب مقاصّة البطاقة*
        (1120 المهيّأ) مش حساب الكاش 1100 الثابت اللي كان الكود القديم بيستخدمه
        دايمًا."""
        from app.core.config import settings as app_settings
        from app.modules.finance import crud as finance_crud
        from app.modules.finance.models import Account
        monkeypatch.setattr(app_settings, "DINING_CARD_SETTLEMENT_ACCOUNT", "1120")

        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        make_finance_accounts(db, branch)
        if not db.query(Account).filter_by(branch_id=branch.id, code="1120").first():
            db.add(Account(branch_id=branch.id, code="1120", name="Card clearing", account_type="asset"))
            db.commit()
        item = make_item_committed(db, branch, outlet, price=Decimal("100.00"))
        linked_cashier = make_branch_linked_headers(db, branch, "cashier")
        linked_waiter = make_branch_linked_headers(db, branch, "waiter")

        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "takeaway", "guests_count": 1,
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        client.patch(f"/api/v1/dining/orders/{order['id']}/status",
                     json={"status": "in_kitchen"}, headers=linked_waiter)
        paid = client.patch(f"/api/v1/dining/orders/{order['id']}/status",
                            json={"status": "paid", "payment_method": "card"}, headers=linked_cashier)
        assert paid.status_code == 200, paid.text
        item_id = paid.json()["items"][0]["id"]

        linked_manager = make_branch_linked_headers(db, branch, "manager")
        refund_reason = "مرتجع بطاقة"
        refund = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": refund_reason},
            headers=_refund_headers(client, linked_manager, order_id=order["id"], item_id=item_id, reason=refund_reason),
        )
        assert refund.status_code == 200, refund.text

        entries, total = finance_crud.list_journal_entries(db, branch.id, source="dining_refund")
        assert total == 1
        card_acc = db.query(Account).filter_by(branch_id=branch.id, code="1120").first()
        cash_acc = db.query(Account).filter_by(branch_id=branch.id, code="1100").first()
        credited = {l.account_id for l in entries[0].lines if l.credit > 0}
        assert card_acc.id in credited          # العكس على حساب البطاقة
        assert cash_acc.id not in credited       # مش على الكاش

    def test_refund_fails_closed_when_folio_closed_and_rolls_back_entirely(
        self, client: TestClient, db, waiter_headers,
    ):
        """High 4a: فشل خفض شحنة الفوليو وسط المرتجع (الفوليو مقفول) لازم يعمل
        rollback كامل — الطلب/الصنف يفضلوا زي ما هم، مفيش صفوف عكس يتيمة."""
        from app.modules.finance.models import Payment
        branch = make_branch_committed(db)
        outlet = make_outlet_committed(db, branch)
        make_finance_accounts(db, branch)
        room, folio = make_room_and_folio(db, branch)
        item = make_item_committed(db, branch, outlet, price=Decimal("100.00"))
        linked_cashier = make_branch_linked_headers(db, branch, "cashier")
        linked_waiter = make_branch_linked_headers(db, branch, "waiter")

        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={"outlet_id": outlet.id, "order_type": "dine_in", "guests_count": 1,
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()
        client.patch(f"/api/v1/dining/orders/{order['id']}/status",
                     json={"status": "in_kitchen"}, headers=linked_waiter)
        paid = client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "paid", "charge_to_room_id": room.id},
            headers=linked_cashier,
        )
        assert paid.status_code == 200, paid.text
        item_id = paid.json()["items"][0]["id"]

        # نقفل الفوليو يدويًا (كأن الضيف عمل checkout) — عكس شحنة الغرفة بقى مستحيل تلقائيًا.
        db.refresh(folio)
        folio.status = "closed"
        db.commit()

        linked_manager = make_branch_linked_headers(db, branch, "manager")
        refund_reason = "مرتجع على فوليو مقفول"
        refund = client.patch(
            f"/api/v1/dining/orders/{order['id']}/items/{item_id}/refund",
            json={"reason": refund_reason},
            headers=_refund_headers(client, linked_manager, order_id=order["id"], item_id=item_id, reason=refund_reason),
        )
        assert refund.status_code == 400  # fail-closed

        # rollback كامل: الطلب لسه paid، الصنف مش refunded، مفيش أي صف عكس.
        after = client.get(f"/api/v1/dining/orders/{order['id']}", headers=linked_manager).json()
        assert after["status"] == "paid"
        assert after["items"][0]["status"] != "refunded"
        assert Decimal(str(after["refunded_amount"])) == Decimal("0.00")
        reversals = (
            db.query(Payment)
            .filter(Payment.ref_order_id == order["id"], Payment.source == "dining_refund")
            .count()
        )
        assert reversals == 0
