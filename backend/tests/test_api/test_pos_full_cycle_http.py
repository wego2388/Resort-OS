"""
tests/test_api/test_pos_full_cycle_http.py
End-to-end HTTP-level order-to-payment cycle for the unified dining POS —
written originally during a QA pass that could not complete a live browser
walkthrough (restaurant/cafe at the time). These tests exercise the exact
same request shapes the frontend POS (UnifiedPOSView.vue) sends, end to end
through real routing/permission dependencies:

  create order → send to kitchen (KitchenTicket created, routed by station)
  → advance KDS ticket → complete payment (cashier+) → verify table freed +
  VAT/service-charge totals math (14% / 12%, per app/core/config.py defaults).

Two real bugs found+fixed originally in restaurant/cafe, still exercised
here against the now-unified dining implementation:
  1. The old CafePOSView.vue posted a payload shape that didn't match
     CafeOrderCreate (needs items[].item_id, not menu_item_id/unit_price/
     outlet_type/payment_method) — every cafe order from the POS screen
     422'd. test_dining_full_cycle_matches_frontend_payload uses the
     correct dining shape end to end (item_id, outlet_id).
  2. update_order_status allowed ANY waiter (role level 30) to transition an
     order straight to "paid" — a real financial action (folio charge,
     revenue journal, inventory deduction) with no cashier-level gate.
     Fixed to require cashier+ for the "paid" transition specifically;
     exercised again here as part of the full cycle.

راجع DINING_CUTOVER_PLAN.md Batch 6 — بورتت من restaurant/cafe (اللي
اتحذفوا) لـ dining الموحّد.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Full Cycle Branch", name_ar="فرع اختبار كامل",
               code=f"FC-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_outlet(db, branch, outlet_type="restaurant", revenue_account_code="4200"):
    from app.modules.dining import services as dining_services
    from app.modules.dining.schemas import OutletCreate
    return dining_services.create_outlet(db, OutletCreate(
        branch_id=branch.id, name=f"منفذ-{outlet_type}-{uuid.uuid4().hex[:6]}",
        outlet_type=outlet_type, revenue_account_code=revenue_account_code,
    ))


def make_table(db, branch, outlet):
    from app.modules.dining.models import VenueTable
    t = VenueTable(branch_id=branch.id, table_number="F1", capacity=4, status="available")
    db.add(t)
    db.commit()
    return t


def make_finance_accounts(db, branch, revenue_code="4200"):
    """حسابات الأستاذ اللي معاملة الدفع الصارمة (Gate 1B) محتاجاها فعليًا —
    زي seed.py الحقيقي بالظبط. من غيرها post_simple_revenue_journal بيرفع
    FinancialConfigurationError (503) بدل ما يبتلع الفشل بصمت زي قبل."""
    from app.modules.finance.models import Account
    wanted = {
        "1100": ("Cash", "asset"),
        "1150": ("ذمم الفوليو", "asset"),
        "1200": ("مخزون البضاعة", "asset"),
        "5200": ("تكلفة البضاعة المباعة (COGS)", "expense"),
        revenue_code: ("Dining Revenue", "revenue"),
    }
    for code, (name, acc_type) in wanted.items():
        if not db.query(Account).filter_by(branch_id=branch.id, code=code).first():
            db.add(Account(branch_id=branch.id, code=code, name=name, account_type=acc_type))
    db.commit()


def make_branch_linked_headers(db, branch, role="waiter") -> dict[str, str]:
    """Gate 1B: PATCH /dining/orders/{id}/status بقى بيفرض assert_branch_access
    على كل تحويل حالة — waiter_headers/cashier_headers المشتركة (conftest.py)
    بلا Employee/فرع خالص، فمحتاجين مستخدم Employee-linked جديد لكل تست."""
    from datetime import date, timedelta
    from decimal import Decimal as _D
    from tests.conftest import _create_test_user, _make_token, open_cashier_shift
    from app.modules.hr.models import Employee

    email = f"{role}-{uuid.uuid4().hex[:10]}@test.local"
    user_id = _create_test_user(email, role)
    emp = Employee(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name=f"{role} اختبار POS", national_id="29001011234567",
        position=role, department="F&B", basic_salary=_D("4000.00"),
        hire_date=date.today() - timedelta(days=365), user_id=user_id,
    )
    db.add(emp)
    db.commit()
    # Gate 4A: أي مشغّل POS بيحصّل دفع مباشر لازم يكون له وردية مفتوحة.
    open_cashier_shift(db, branch.id, user_id)
    return {"Authorization": f"Bearer {_make_token(email)}"}


class TestDiningFullCycle:
    def test_order_to_payment_cycle_with_real_vat_and_service_charge(
        self, client: TestClient, db, waiter_headers,
    ):
        from app.modules.dining.models import DiningItem

        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        make_finance_accounts(db, branch)
        table = make_table(db, branch, outlet)
        waiter_linked = make_branch_linked_headers(db, branch, "waiter")
        cashier_linked = make_branch_linked_headers(db, branch, "cashier")
        fish = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="Grilled Sea Bass",
                          price=Decimal("85.00"), station="grill")
        pasta = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="Seafood Pasta",
                           price=Decimal("75.00"), station="hot")
        db.add_all([fish, pasta])
        db.commit()

        # 1) واحد ياخد الطلب (نادل)
        order = client.post(
            f"/api/v1/dining/outlets/{outlet.id}/orders",
            json={
                "outlet_id": outlet.id, "table_id": table.id, "order_type": "dine_in", "guests_count": 2,
                "items": [
                    {"item_id": fish.id, "quantity": 1},
                    {"item_id": pasta.id, "quantity": 2},
                ],
            },
            headers=waiter_headers,
        ).json()
        assert order["status"] == "open"

        subtotal = Decimal("85.00") + Decimal("75.00") * 2  # 235.00
        assert Decimal(str(order["subtotal"])) == subtotal
        assert Decimal(str(order["vat_amount"])) == (subtotal * Decimal("0.14")).quantize(Decimal("0.01"))
        assert Decimal(str(order["service_charge"])) == (subtotal * Decimal("0.12")).quantize(Decimal("0.01"))
        expected_total = subtotal + Decimal(str(order["vat_amount"])) + Decimal(str(order["service_charge"]))
        assert Decimal(str(order["total"])) == expected_total

        # 2) يتبعت للمطبخ — لازم تذكرتين منفصلتين (grill + hot)
        resp = client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "in_kitchen"}, headers=waiter_linked,
        )
        assert resp.status_code == 200, resp.text

        tickets_resp = client.get(
            "/api/v1/dining/kitchen/tickets",
            params={"branch_id": branch.id, "outlet_id": outlet.id},
            headers=waiter_headers,
        )
        tickets = tickets_resp.json()
        stations = {t["station"] for t in tickets if t["order_id"] == order["id"]}
        assert stations == {"grill", "hot"}

        # 3) كل تذكرة تتقدّم على شاشة الـ KDS بتاعتها لحد "done"
        for ticket in tickets:
            if ticket["order_id"] != order["id"]:
                continue
            r1 = client.patch(
                f"/api/v1/dining/kitchen/tickets/{ticket['id']}/status",
                json={"status": "in_progress"}, headers=waiter_headers,
            )
            assert r1.status_code == 200
            r2 = client.patch(
                f"/api/v1/dining/kitchen/tickets/{ticket['id']}/status",
                json={"status": "done"}, headers=waiter_headers,
            )
            assert r2.status_code == 200

        # 4) نادل ملوش صلاحية يقفل الحساب
        denied = client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "paid"}, headers=waiter_linked,
        )
        assert denied.status_code == 403

        # 5) الكاشير بيقفل الحساب فعليًا
        paid = client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "paid"}, headers=cashier_linked,
        )
        assert paid.status_code == 200, paid.text
        assert paid.json()["status"] == "paid"
        assert Decimal(str(paid.json()["total"])) == expected_total

        # 6) الطاولة اترجعت متاحة
        tables_resp = client.get(
            f"/api/v1/dining/branches/{branch.id}/tables", headers=waiter_headers,
        )
        found = next(t for t in tables_resp.json() if t["id"] == table.id)
        assert found["status"] == "available"

    def test_dining_full_cycle_matches_frontend_payload(
        self, client: TestClient, db, waiter_headers,
    ):
        """نفس الـ shape اللي UnifiedPOSView.vue بيبعته فعليًا —
        item_id (مش menu_item_id)، outlet_id، من غير unit_price/payment_method."""
        from app.modules.dining.models import DiningItem

        branch = make_branch(db)
        outlet = make_outlet(db, branch, outlet_type="cafe", revenue_account_code="4400")
        make_finance_accounts(db, branch, revenue_code="4400")
        waiter_linked = make_branch_linked_headers(db, branch, "waiter")
        cashier_linked = make_branch_linked_headers(db, branch, "cashier")
        pizza = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name="Margherita",
                           price=Decimal("220.00"), is_available=True)
        db.add(pizza)
        db.commit()

        payload = {
            "outlet_id": outlet.id,
            "order_type": "takeaway",
            "items": [{"item_id": pizza.id, "quantity": 2, "notes": None}],
        }
        order = client.post(f"/api/v1/dining/outlets/{outlet.id}/orders", json=payload, headers=waiter_headers).json()
        assert order["status"] == "open"
        subtotal = Decimal("220.00") * 2
        assert Decimal(str(order["subtotal"])) == subtotal

        # in_kitchen (بار) — نفس اللي UnifiedPOSView.submitOrder() بيعمله فعليًا
        r1 = client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "in_kitchen"}, headers=waiter_linked,
        )
        assert r1.status_code == 200, r1.text

        # الدفع فوري عند الكاونتر — كاشير بس
        denied = client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "paid"}, headers=waiter_linked,
        )
        assert denied.status_code == 403

        paid = client.patch(
            f"/api/v1/dining/orders/{order['id']}/status",
            json={"status": "paid"}, headers=cashier_linked,
        )
        assert paid.status_code == 200, paid.text
        assert paid.json()["status"] == "paid"
        expected_total = subtotal + (subtotal * Decimal("0.14")).quantize(Decimal("0.01")) + (subtotal * Decimal("0.12")).quantize(Decimal("0.01"))
        assert Decimal(str(paid.json()["total"])) == expected_total
