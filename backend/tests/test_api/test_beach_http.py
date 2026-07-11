"""
tests/test_api/test_beach_http.py
HTTP-level tests for the beach module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed — the
HTTP request goes through a different DB session (app.dependency_overrides
[get_db]) than the `db` fixture injected directly into the test function.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Beach HTTP Branch", name_ar="فرع شاطئ",
               code=f"BCH-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


class TestBeachReservationFlow:
    def test_reservation_checkin_consumes_inventory(self, client: TestClient, db, fake_redis, cashier_headers):
        """Full round-trip: create reservation -> checkin -> capacity_used goes up."""
        branch = make_branch_committed(db)

        before = client.get(
            "/api/v1/beach/inventory", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert before.status_code == 200, before.text
        cap_before = before.json()["capacity_used"]

        create_resp = client.post(
            "/api/v1/beach/reservations",
            json={
                "branch_id": branch.id,
                "guest_name": "أحمد محمود",
                "reservation_date": str(date.today()),
                "guests_count": 2,
                "with_towel": False,
            },
            headers=cashier_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        reservation = create_resp.json()
        assert reservation["status"] == "pending"
        assert Decimal(str(reservation["total_amount"])) > 0

        checkin_resp = client.post(
            f"/api/v1/beach/reservations/{reservation['id']}/checkin",
            headers=cashier_headers,
        )
        assert checkin_resp.status_code == 200, checkin_resp.text
        checked_in = checkin_resp.json()
        assert checked_in["status"] == "checked_in"
        assert checked_in["tx_id"] is not None

        after = client.get(
            "/api/v1/beach/inventory", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert after.json()["capacity_used"] == cap_before + 2

    def test_double_checkin_rejected(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        reservation = client.post(
            "/api/v1/beach/reservations",
            json={
                "branch_id": branch.id, "guest_name": "سارة علي",
                "reservation_date": str(date.today()), "guests_count": 1,
            },
            headers=cashier_headers,
        ).json()

        client.post(f"/api/v1/beach/reservations/{reservation['id']}/checkin", headers=cashier_headers)
        second = client.post(f"/api/v1/beach/reservations/{reservation['id']}/checkin", headers=cashier_headers)
        assert second.status_code == 400

    def test_reservation_public_view_no_auth(self, client: TestClient, db, fake_redis):
        """QR page reads reservation info without login."""
        branch = make_branch_committed(db)
        from app.modules.beach.models import BeachReservation
        res = BeachReservation(
            branch_id=branch.id, guest_name="ضيف QR", reservation_date=date.today(),
            guests_count=1, with_towel=False, status="pending", total_amount=Decimal("200.00"),
        )
        db.add(res)
        db.commit()

        resp = client.get(f"/api/v1/beach/reservations/{res.id}/public")
        assert resp.status_code == 200
        assert resp.json()["guest_name"] == "ضيف QR"


class TestBeachInventoryPricing:
    """باج حقيقي اتصلح 2026-07-03 (QA pass): GET /beach/inventory كان بيرجّع
    الـ capacity/towels بس من غير أي سعر (adult_price/child_price/...) —
    الأسعار الحقيقية متخزنة في جدول settings ومحسوبة سيرفر-سايد وقت البيع بس
    (services._get_base_prices)، فمفيش endpoint كان بيرجّعها للفرونت إند خالص.
    شاشة POS الشاطئ كانت مبنية على افتراض إنها موجودة في نفس الرد، فكل سعر كان
    بيظهر "NaN" في الواجهة. اتصلح بدمج services.get_base_prices() (نسخة عامة
    من الدالة الخاصة) في رد GET /beach/inventory."""

    def test_inventory_includes_configured_prices(self, client: TestClient, db, fake_redis, cashier_headers):
        from app.modules.core.crud import upsert_setting
        branch = make_branch_committed(db)
        upsert_setting(db, "beach.price.adult", "250", branch_id=branch.id)
        upsert_setting(db, "beach.price.child", "120", branch_id=branch.id)
        upsert_setting(db, "beach.price.resident", "180", branch_id=branch.id)
        upsert_setting(db, "beach.price.towel", "60", branch_id=branch.id)
        db.commit()

        resp = client.get(
            "/api/v1/beach/inventory", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert Decimal(str(body["adult_price"])) == Decimal("250")
        assert Decimal(str(body["child_price"])) == Decimal("120")
        assert Decimal(str(body["resident_price"])) == Decimal("180")
        assert Decimal(str(body["towel_price"])) == Decimal("60")

    def test_inventory_surge_multiplier_reflects_surge_pct(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        surge_resp = client.patch(
            "/api/v1/beach/surge", params={"branch_id": branch.id},
            json={"surge_pct": 50}, headers=manager_headers,
        )
        assert surge_resp.status_code == 200, surge_resp.text
        assert surge_resp.json()["surge_active"] is True
        assert surge_resp.json()["surge_multiplier"] == 1.5


class TestBeachSellPermissions:
    def test_sell_requires_cashier_level(self, client: TestClient, db, fake_redis):
        """A waiter-level token must not be able to sell beach tickets (cashier+ required)."""
        from tests.conftest import _create_test_user, _make_token
        branch = make_branch_committed(db)
        _create_test_user("beach-waiter@test.local", "waiter")
        headers = {"Authorization": f"Bearer {_make_token('beach-waiter@test.local')}"}

        resp = client.post(
            "/api/v1/beach/sell",
            params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 1},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_surge_set_requires_manager(self, client: TestClient, db, fake_redis, cashier_headers):
        """Cashier-level token must not be allowed to set surge pricing (manager+ only)."""
        branch = make_branch_committed(db)
        resp = client.patch(
            "/api/v1/beach/surge",
            params={"branch_id": branch.id},
            json={"surge_pct": "50"},
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_surge_set_by_manager_reflected_in_price(self, client: TestClient, db, fake_redis, manager_headers, cashier_headers):
        branch = make_branch_committed(db)
        surge_resp = client.patch(
            "/api/v1/beach/surge",
            params={"branch_id": branch.id},
            json={"surge_pct": "50"},
            headers=manager_headers,
        )
        assert surge_resp.status_code == 200, surge_resp.text
        assert Decimal(str(surge_resp.json()["surge_pct"])) == Decimal("50")

        sell_resp = client.post(
            "/api/v1/beach/sell",
            params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 1},
            headers=cashier_headers,
        )
        assert sell_resp.status_code == 201, sell_resp.text
        assert sell_resp.json()["surge_applied"] is True


class TestBeachValidation:
    def test_sell_rejects_invalid_tx_type(self, client: TestClient, db, fake_redis, cashier_headers):
        """tx_type outside the allowed pattern must 422, not 500 or a silent pass."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/beach/sell",
            params={"branch_id": branch.id},
            json={"tx_type": "free_beer", "quantity": 1},
            headers=cashier_headers,
        )
        assert resp.status_code == 422

    def test_sell_rejects_zero_quantity(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/beach/sell",
            params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 0},
            headers=cashier_headers,
        )
        assert resp.status_code == 422

    def test_sell_exceeding_capacity_rejected(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/beach/sell",
            params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 999999},
            headers=cashier_headers,
        )
        assert resp.status_code == 400

    def test_sell_with_local_id_is_idempotent_on_retry(self, client: TestClient, db, fake_redis, cashier_headers):
        """wagdy.md #13/#37: BeachPOSView's offline-queue retry (useOfflineQueue)
        must not double-sell (double capacity deduction) if the same request is
        replayed after a lost response — same local_id must return the exact
        same transaction, not create a second one."""
        branch = make_branch_committed(db)
        payload = {"tx_type": "entry", "quantity": 2, "local_id": "offline-retry-abc123"}

        first = client.post(
            "/api/v1/beach/sell", params={"branch_id": branch.id}, json=payload, headers=cashier_headers,
        )
        assert first.status_code == 201, first.text

        retry = client.post(
            "/api/v1/beach/sell", params={"branch_id": branch.id}, json=payload, headers=cashier_headers,
        )
        assert retry.status_code == 201, retry.text
        assert retry.json()["id"] == first.json()["id"]

        list_resp = client.get(
            "/api/v1/beach/transactions", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert list_resp.json()["total"] == 1  # مش 2 — الـ retry مارجعش يعمل بيع جديد


class TestBeachB2BContracts:
    def test_b2b_checkin_and_quota_status_via_http(self, client: TestClient, db, fake_redis, super_admin_headers, cashier_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/beach/b2b-contracts",
            json={
                "branch_id": branch.id,
                "hotel_name": "Grand Resort Hotel",
                "daily_quota": 10,
                "entry_price": "150.00",
                "valid_from": str(date.today()),
                "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=super_admin_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        contract = create_resp.json()

        checkin_resp = client.post(
            "/api/v1/beach/b2b-checkin",
            params={"branch_id": branch.id},
            json={"contract_id": contract["id"], "guests_count": 3, "with_towel": False},
            headers=cashier_headers,
        )
        assert checkin_resp.status_code == 201, checkin_resp.text

        status_resp = client.get(
            "/api/v1/beach/b2b-contracts/status",
            params={"branch_id": branch.id},
            headers=cashier_headers,
        )
        assert status_resp.status_code == 200
        entry = next(s for s in status_resp.json() if s["contract_id"] == contract["id"])
        assert entry["checked_in_today"] == 3
        assert entry["remaining_quota"] == 7

    def test_b2b_contract_create_requires_admin(self, client: TestClient, db, fake_redis, manager_headers):
        """manager-level (60) must not be allowed to create a B2B contract (admin=80 required)."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/beach/b2b-contracts",
            json={
                "branch_id": branch.id,
                "hotel_name": "Some Hotel",
                "daily_quota": 10,
                "entry_price": "150.00",
                "valid_from": str(date.today()),
                "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 403

    def test_b2b_checkin_rejected_when_exceeding_daily_quota(
        self, client: TestClient, db, fake_redis, super_admin_headers, cashier_headers,
    ):
        """Real business-rule coverage flagged by an independent review as
        under-tested: B2B is external-hotel-contract revenue with a fixed
        daily quota — overselling it means checking in guests the resort
        never agreed/priced capacity for."""
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/beach/b2b-contracts",
            json={
                "branch_id": branch.id, "hotel_name": "Small Quota Hotel",
                "daily_quota": 5, "entry_price": "150.00",
                "valid_from": str(date.today()), "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=super_admin_headers,
        ).json()

        # Uses 4 of the 5-guest quota — should succeed.
        first = client.post(
            "/api/v1/beach/b2b-checkin", params={"branch_id": branch.id},
            json={"contract_id": contract["id"], "guests_count": 4},
            headers=cashier_headers,
        )
        assert first.status_code == 201, first.text

        # Only 1 guest of quota remains — asking for 2 must be rejected, not
        # silently allowed past the contracted daily cap.
        over_resp = client.post(
            "/api/v1/beach/b2b-checkin", params={"branch_id": branch.id},
            json={"contract_id": contract["id"], "guests_count": 2},
            headers=cashier_headers,
        )
        assert over_resp.status_code == 400
        assert "الحصة" in over_resp.json()["detail"]

        # Confirm quota status reflects only the successful check-in, not
        # the rejected attempt.
        status_resp = client.get(
            "/api/v1/beach/b2b-contracts/status",
            params={"branch_id": branch.id}, headers=cashier_headers,
        )
        entry = next(s for s in status_resp.json() if s["contract_id"] == contract["id"])
        assert entry["checked_in_today"] == 4
        assert entry["remaining_quota"] == 1

    def test_list_b2b_contracts(self, client: TestClient, db, fake_redis, super_admin_headers, manager_headers):
        branch = make_branch_committed(db)
        client.post(
            "/api/v1/beach/b2b-contracts",
            json={
                "branch_id": branch.id, "hotel_name": "Listed Hotel",
                "daily_quota": 20, "entry_price": "100.00",
                "valid_from": str(date.today()), "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=super_admin_headers,
        )
        resp = client.get(
            "/api/v1/beach/b2b-contracts", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert resp.status_code == 200
        assert any(c["hotel_name"] == "Listed Hotel" for c in resp.json())


class TestB2BCredit:
    """حد ائتمان + تسوية + تأخر سداد عبر الـ API الحقيقي (permissions،
    validation، الرد الفعلي) — راجع services/beach_engine للاختبارات
    الأدق على منطق العمل نفسه."""

    def _create_contract(self, client, branch, headers, **overrides):
        payload = {
            "branch_id": branch.id, "hotel_name": "Credit Test Hotel",
            "daily_quota": 50, "entry_price": "100.00",
            "valid_from": str(date.today()), "valid_until": str(date.today() + timedelta(days=30)),
        }
        payload.update(overrides)
        resp = client.post("/api/v1/beach/b2b-contracts", json=payload, headers=headers)
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_b2b_checkin_rejected_when_exceeding_credit_limit(
        self, client: TestClient, db, fake_redis, super_admin_headers, cashier_headers,
    ):
        branch = make_branch_committed(db)
        contract = self._create_contract(client, branch, super_admin_headers, credit_limit="300.00")

        over_resp = client.post(
            "/api/v1/beach/b2b-checkin", params={"branch_id": branch.id},
            json={"contract_id": contract["id"], "guests_count": 5},  # 500 ج.م > 300 حد
            headers=cashier_headers,
        )
        assert over_resp.status_code == 400
        assert "حد الائتمان" in over_resp.json()["detail"]

    def test_b2b_checkin_within_credit_limit_succeeds(
        self, client: TestClient, db, fake_redis, super_admin_headers, cashier_headers,
    ):
        branch = make_branch_committed(db)
        contract = self._create_contract(client, branch, super_admin_headers, credit_limit="1000.00")

        resp = client.post(
            "/api/v1/beach/b2b-checkin", params={"branch_id": branch.id},
            json={"contract_id": contract["id"], "guests_count": 3},
            headers=cashier_headers,
        )
        assert resp.status_code == 201, resp.text

    def test_update_contract_credit_requires_admin(
        self, client: TestClient, db, fake_redis, super_admin_headers, manager_headers,
    ):
        branch = make_branch_committed(db)
        contract = self._create_contract(client, branch, super_admin_headers)

        resp = client.patch(
            f"/api/v1/beach/b2b-contracts/{contract['id']}",
            json={"credit_limit": "2000.00"},
            headers=manager_headers,
        )
        assert resp.status_code == 403

    def test_update_contract_credit_via_http(
        self, client: TestClient, db, fake_redis, super_admin_headers,
    ):
        branch = make_branch_committed(db)
        contract = self._create_contract(client, branch, super_admin_headers)

        resp = client.patch(
            f"/api/v1/beach/b2b-contracts/{contract['id']}",
            json={"credit_limit": "2500.00", "payment_terms_days": 15},
            headers=super_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert Decimal(str(body["credit_limit"])) == Decimal("2500.00")
        assert body["payment_terms_days"] == 15

    def test_update_contract_credit_can_clear_limit(
        self, client: TestClient, db, fake_redis, super_admin_headers,
    ):
        """بعت credit_limit=None صراحةً لازم يمسح الحد (مش يتجاهله) — نفس
        الفرق بين "الحقل اتبعت بقيمة None" و"الحقل ما اتبعتش خالص"."""
        branch = make_branch_committed(db)
        contract = self._create_contract(client, branch, super_admin_headers, credit_limit="1000.00")

        resp = client.patch(
            f"/api/v1/beach/b2b-contracts/{contract['id']}",
            json={"credit_limit": None},
            headers=super_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["credit_limit"] is None

    def test_settle_contract_requires_manager(
        self, client: TestClient, db, fake_redis, super_admin_headers, cashier_headers,
    ):
        branch = make_branch_committed(db)
        contract = self._create_contract(client, branch, super_admin_headers)

        resp = client.post(
            f"/api/v1/beach/b2b-contracts/{contract['id']}/settle", json={},
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_settle_contract_via_http_resets_balance(
        self, client: TestClient, db, fake_redis, super_admin_headers, cashier_headers, manager_headers,
    ):
        branch = make_branch_committed(db)
        contract = self._create_contract(client, branch, super_admin_headers, credit_limit="300.00")
        client.post(
            "/api/v1/beach/b2b-checkin", params={"branch_id": branch.id},
            json={"contract_id": contract["id"], "guests_count": 2},  # 200 ج.م
            headers=cashier_headers,
        )

        settle_resp = client.post(
            f"/api/v1/beach/b2b-contracts/{contract['id']}/settle", json={},
            headers=manager_headers,
        )
        assert settle_resp.status_code == 200, settle_resp.text
        assert settle_resp.json()["last_settled_at"] == str(date.today())

        # بعد التسوية، الرصيد اتصفّر فعليًا — عملية جديدة لحد الحد الكامل تعدي تاني.
        second = client.post(
            "/api/v1/beach/b2b-checkin", params={"branch_id": branch.id},
            json={"contract_id": contract["id"], "guests_count": 2},
            headers=cashier_headers,
        )
        assert second.status_code == 201, second.text

    def test_live_dashboard_includes_overdue_alerts_key(
        self, client: TestClient, db, fake_redis, cashier_headers,
    ):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/beach/live-dashboard", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "overdue_alerts" in body
        assert body["overdue_alerts"] == []


class TestBeachTicketPdf:
    """قبل الإصلاح: generate_ticket_pdf كانت بتستخدم receipt_pdf العادي (مقاس A4 كامل، رغم
    إن الـ docstring كان بيدّعي إنها thermal) — مش المناسب لطابعة رول حراري 80mm الحقيقية
    المستخدمة في شبابيك دخول الشاطئ. اتصلحت لاستخدام receipt_pdf_thermal فعليًا."""

    def test_ticket_pdf_is_thermal_sized_not_a4(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)

        sell_resp = client.post(
            "/api/v1/beach/sell",
            params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 2},
            headers=cashier_headers,
        )
        assert sell_resp.status_code == 201, sell_resp.text
        tx = sell_resp.json()

        resp = client.get(f"/api/v1/beach/transactions/{tx['id']}/ticket", headers=cashier_headers)
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"

        import re
        match = re.search(rb"/MediaBox\s*\[([^\]]+)\]", resp.content)
        assert match is not None
        media_box = [float(v) for v in match.group(1).split()]
        pdf_width = media_box[2] - media_box[0]
        assert pdf_width < 300, f"expected thermal-width PDF, got width={pdf_width}pt (A4 is ~595pt)"


class TestBeachTransactionsListAndVoidHTTP:
    """void_transaction's financial-reversal logic was already covered
    extensively at the service layer (test_beach.py) -- but never through
    the actual HTTP router endpoint itself (require_permission dependency,
    HTTPException translation, response model validation). Same gap class
    found repeatedly in this project: a service being correct doesn't prove
    the router wiring to it is correct."""

    def test_list_transactions_via_http(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        sell_resp = client.post(
            "/api/v1/beach/sell", params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 2}, headers=cashier_headers,
        )
        assert sell_resp.status_code == 201, sell_resp.text

        list_resp = client.get(
            "/api/v1/beach/transactions", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] >= 1

    def test_download_ticket_404_for_nonexistent_transaction(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/beach/transactions/999999/ticket", headers=cashier_headers,
        )
        assert resp.status_code == 404

    def test_void_transaction_via_http_requires_manager_level(
        self, client: TestClient, db, fake_redis, cashier_headers,
    ):
        """require_permission("beach.void_transaction", min_role_level=60) —
        a plain cashier (level 40) must be rejected even though cashier can
        sell/list."""
        branch = make_branch_committed(db)
        sell_resp = client.post(
            "/api/v1/beach/sell", params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 1}, headers=cashier_headers,
        )
        tx_id = sell_resp.json()["id"]

        resp = client.post(
            f"/api/v1/beach/transactions/{tx_id}/void",
            json={"reason": "غلط في الإدخال"}, headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_void_transaction_via_http_succeeds_for_manager(
        self, client: TestClient, db, fake_redis, cashier_headers, manager_headers,
    ):
        branch = make_branch_committed(db)
        sell_resp = client.post(
            "/api/v1/beach/sell", params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 1}, headers=cashier_headers,
        )
        tx_id = sell_resp.json()["id"]

        resp = client.post(
            f"/api/v1/beach/transactions/{tx_id}/void",
            json={"reason": "طلب الضيف الإلغاء"}, headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["voided_at"] is not None

        # Double-void via the real HTTP endpoint must be rejected, not just
        # at the service layer.
        second = client.post(
            f"/api/v1/beach/transactions/{tx_id}/void",
            json={"reason": "تاني"}, headers=manager_headers,
        )
        assert second.status_code == 400


class TestBeachReportsHTTP:
    """daily_summary/eod-report/eod-report-pdf/live-dashboard had zero HTTP
    coverage — only ever exercised indirectly, never asserted on directly."""

    def test_daily_summary_reflects_real_sale(self, client: TestClient, db, fake_redis, cashier_headers, manager_headers):
        branch = make_branch_committed(db)
        client.post(
            "/api/v1/beach/sell", params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 3}, headers=cashier_headers,
        )
        resp = client.get(
            "/api/v1/beach/summary",
            params={"branch_id": branch.id, "tx_date": str(date.today())},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total_entries"] >= 3

    def test_eod_report_via_http(self, client: TestClient, db, fake_redis, cashier_headers, manager_headers):
        branch = make_branch_committed(db)
        client.post(
            "/api/v1/beach/sell", params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 1}, headers=cashier_headers,
        )
        resp = client.get(
            "/api/v1/beach/eod-report", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert resp.status_code == 200

    def test_eod_report_pdf_via_http(self, client: TestClient, db, fake_redis, cashier_headers, manager_headers):
        branch = make_branch_committed(db)
        client.post(
            "/api/v1/beach/sell", params={"branch_id": branch.id},
            json={"tx_type": "entry", "quantity": 1}, headers=cashier_headers,
        )
        resp = client.get(
            "/api/v1/beach/eod-report/pdf", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"

    def test_live_dashboard_via_http(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/beach/live-dashboard", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "capacity_used" in body
        assert "capacity_max" in body


class TestBeachReservationsListHTTP:
    def test_list_reservations_via_http(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        client.post(
            "/api/v1/beach/reservations",
            json={"branch_id": branch.id, "guest_name": "ضيف اختبار القائمة",
                  "reservation_date": str(date.today()), "guests_count": 2},
            headers=cashier_headers,
        )
        resp = client.get(
            "/api/v1/beach/reservations", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert resp.status_code == 200
        names = [r["guest_name"] for r in resp.json()["items"]]
        assert "ضيف اختبار القائمة" in names


class TestBeachLocationsHTTP:
    """خريطة الشاطئ الحية — عبر TestClient حقيقي (routing + permission
    dependencies + Pydantic validation)، مش نداء services مباشر."""

    def test_bulk_add_requires_manager(self, client: TestClient, db, fake_redis, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/beach/locations/bulk",
            json={"branch_id": branch.id, "location_type": "umbrella", "count": 5},
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_bulk_add_then_list_then_checkin_checkout_flow(
        self, client: TestClient, db, fake_redis, manager_headers, cashier_headers,
    ):
        branch = make_branch_committed(db)

        add_resp = client.post(
            "/api/v1/beach/locations/bulk",
            json={"branch_id": branch.id, "location_type": "umbrella", "count": 4},
            headers=manager_headers,
        )
        assert add_resp.status_code == 201, add_resp.text
        created = add_resp.json()
        assert [loc["number"] for loc in created] == ["1", "2", "3", "4"]
        assert all(loc["status"] == "available" for loc in created)

        list_resp = client.get(
            "/api/v1/beach/locations", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 4

        loc_id = created[0]["id"]
        checkin_resp = client.post(
            f"/api/v1/beach/locations/{loc_id}/checkin",
            params={"branch_id": branch.id},
            json={"guest_name": "هدى كمال", "guests_count": 2, "with_towel": True},
            headers=cashier_headers,
        )
        assert checkin_resp.status_code == 201, checkin_resp.text
        occupied = checkin_resp.json()
        assert occupied["status"] == "occupied"
        assert occupied["guest_name"] == "هدى كمال"
        assert occupied["current_transaction_id"] is not None

        # موقع مشغول لا يمكن تسجيل دخول عليه تاني — 409
        second_checkin = client.post(
            f"/api/v1/beach/locations/{loc_id}/checkin",
            params={"branch_id": branch.id},
            json={"guests_count": 1},
            headers=cashier_headers,
        )
        assert second_checkin.status_code == 409

        checkout_resp = client.post(
            f"/api/v1/beach/locations/{loc_id}/checkout",
            params={"branch_id": branch.id},
            headers=cashier_headers,
        )
        assert checkout_resp.status_code == 200, checkout_resp.text
        freed = checkout_resp.json()
        assert freed["status"] == "available"
        assert freed["guest_name"] is None

    def test_reduce_rejects_when_locations_occupied(
        self, client: TestClient, db, fake_redis, manager_headers, cashier_headers,
    ):
        branch = make_branch_committed(db)
        add_resp = client.post(
            "/api/v1/beach/locations/bulk",
            json={"branch_id": branch.id, "location_type": "pergola", "count": 2},
            headers=manager_headers,
        )
        loc_id = add_resp.json()[0]["id"]
        client.post(
            f"/api/v1/beach/locations/{loc_id}/checkin",
            params={"branch_id": branch.id}, json={"guests_count": 1}, headers=cashier_headers,
        )

        reduce_resp = client.post(
            "/api/v1/beach/locations/reduce",
            json={"branch_id": branch.id, "location_type": "pergola", "count": 2},
            headers=manager_headers,
        )
        assert reduce_resp.status_code == 409

    def test_update_location_requires_manager(self, client: TestClient, db, fake_redis, manager_headers, cashier_headers):
        branch = make_branch_committed(db)
        add_resp = client.post(
            "/api/v1/beach/locations/bulk",
            json={"branch_id": branch.id, "location_type": "cabana", "count": 1},
            headers=manager_headers,
        )
        loc_id = add_resp.json()[0]["id"]

        forbidden = client.patch(
            f"/api/v1/beach/locations/{loc_id}",
            params={"branch_id": branch.id}, json={"status": "out_of_service"},
            headers=cashier_headers,
        )
        assert forbidden.status_code == 403

        allowed = client.patch(
            f"/api/v1/beach/locations/{loc_id}",
            params={"branch_id": branch.id}, json={"status": "out_of_service"},
            headers=manager_headers,
        )
        assert allowed.status_code == 200
        assert allowed.json()["status"] == "out_of_service"
