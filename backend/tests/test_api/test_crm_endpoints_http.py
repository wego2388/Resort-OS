"""
tests/test_api/test_crm_endpoints_http.py
HTTP-level tests for CRM router endpoints not already covered by
test_crm_http.py (leads flow) or test_crm.py/test_crm_leads.py (service
layer): customers CRUD, interactions listing, opportunities listing,
activities listing — all at the real HTTP layer (status codes, pagination,
role gates, 404s).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="CRM Endpoints Branch", name_ar="فرع عملاء",
               code=f"CRME-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    # Gate 4B: عمليات CRM بقت تفرض branch isolation server-side (2026-07-28)
    # — نفس نمط test_timeshare_http.py's make_branch_committed. waiter هنا
    # (عكس beach/timeshare) بيستخدم لعمليات حقيقية مش رفض بس، لأن أوسع
    # بوابة CRM (get_current_active_user) بتسمح له.
    _link_shared_users_to_branch(db, b.id)
    return b


def _link_shared_users_to_branch(db, branch_id: int) -> None:
    from app.core.kernel.models.user import User
    from tests.conftest import assign_test_user_to_branch

    for email in ("waiter@test.local", "cashier@test.local", "manager@test.local"):
        user = db.query(User).filter(User.email == email).first()
        if user:
            assign_test_user_to_branch(db, user.id, branch_id)
    db.commit()


def super_admin_headers_for_branch(db, branch) -> dict[str, str]:
    """super_admin (level≥100) بيتخطى فحص العضوية تمامًا لكن لازم يختار
    سياق فرع صريح في التوكن نفسه (claim bid) — راجع نفس الدالة في
    test_beach_http.py لتفاصيل السبب."""
    from app.core.kernel.models.user import User
    from tests.conftest import _make_token
    user = db.query(User).filter(User.email == "super_admin@test.local").first()
    return {"Authorization": f"Bearer {_make_token(user.email, branch_id=branch.id)}"}


def create_customer(client: TestClient, branch_id: int, headers: dict, **overrides) -> dict:
    payload = {"branch_id": branch_id, "full_name": "عميل اختبار", "segment": "regular", "source": "walk_in"}
    payload.update(overrides)
    resp = client.post("/api/v1/crm/customers", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestGuestProfileEndpoints:
    """GuestProfile كان model + crud كاملين بدون أي schema/router — نفس فئة
    باج 'الموديل موجود، الـ API صفر'. اتوصل بـ pms.services.checkout_booking
    (تكامل حقيقي مُختبَر في test_pms_http.py) + endpoints قراءة هنا."""

    def test_list_and_get_by_phone_empty(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.get("/api/v1/crm/guest-profiles", params={"branch_id": branch.id}, headers=waiter_headers)
        assert resp.status_code == 200
        assert resp.json() == []

        missing = client.get(
            "/api/v1/crm/guest-profiles/by-phone/01000000000",
            params={"branch_id": branch.id}, headers=waiter_headers,
        )
        assert missing.status_code == 404

    def test_get_by_phone_returns_seeded_profile(self, client: TestClient, db, waiter_headers):
        from app.modules.crm.models import GuestProfile
        from decimal import Decimal
        branch = make_branch_committed(db)
        profile = GuestProfile(
            branch_id=branch.id, full_name="ضيف دائم", phone="01011112222",
            total_visits=3, avg_spend=Decimal("450.00"), vip_flag=True,
        )
        db.add(profile)
        db.commit()

        resp = client.get(
            "/api/v1/crm/guest-profiles/by-phone/01011112222",
            params={"branch_id": branch.id}, headers=waiter_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_visits"] == 3
        assert body["vip_flag"] is True


class TestCustomersEndpoints:
    def test_create_list_get_and_update(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers, full_name="نورا حسن")

        list_resp = client.get("/api/v1/crm/customers", params={"branch_id": branch.id}, headers=waiter_headers)
        assert list_resp.status_code == 200
        assert any(c["id"] == customer["id"] for c in list_resp.json()["items"])

        get_resp = client.get(f"/api/v1/crm/customers/{customer['id']}", headers=waiter_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["full_name"] == "نورا حسن"

        update_resp = client.patch(
            f"/api/v1/crm/customers/{customer['id']}", json={"segment": "vip"}, headers=waiter_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["segment"] == "vip"

    def test_get_missing_customer_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/crm/customers/999999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_search_filters_by_name(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        create_customer(client, branch.id, waiter_headers, full_name="أحمد الششتاوي")
        create_customer(client, branch.id, waiter_headers, full_name="مريم عادل")

        resp = client.get(
            "/api/v1/crm/customers", params={"branch_id": branch.id, "search": "ششتاوي"}, headers=waiter_headers,
        )
        names = [c["full_name"] for c in resp.json()["items"]]
        assert "أحمد الششتاوي" in names
        assert "مريم عادل" not in names

    def test_blacklist_requires_manager_not_just_active_user(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)
        resp = client.post(
            f"/api/v1/crm/customers/{customer['id']}/blacklist",
            json={"reason": "شيك مرتد"}, headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_blacklist_and_unblacklist_round_trip(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)

        bl_resp = client.post(
            f"/api/v1/crm/customers/{customer['id']}/blacklist",
            json={"reason": "سلوك غير لائق"}, headers=manager_headers,
        )
        assert bl_resp.status_code == 200
        assert bl_resp.json()["blacklisted"] is True

        unbl_resp = client.delete(f"/api/v1/crm/customers/{customer['id']}/blacklist", headers=manager_headers)
        assert unbl_resp.status_code == 200
        assert unbl_resp.json()["blacklisted"] is False


def create_customer_group(client: TestClient, branch_id: int, headers: dict, **overrides) -> dict:
    payload = {"branch_id": branch_id, "name": f"Group {uuid.uuid4().hex[:6]}", "discount_percentage": "10"}
    payload.update(overrides)
    resp = client.post("/api/v1/crm/customer-groups", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCustomerGroupEndpoints:
    """مجموعات عملاء بخصم دائم — نفس نمط /finance/discounts بالظبط (قراءة
    لمدير+، إنشاء/تعديل لـ admin+ فقط)."""

    def test_create_requires_admin_not_just_manager(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/crm/customer-groups",
            json={"branch_id": branch.id, "name": "موظفين", "discount_percentage": "15"},
            headers=manager_headers,
        )
        assert resp.status_code == 403

    def test_create_list_and_update(self, client: TestClient, db, manager_headers, super_admin_headers):
        branch = make_branch_committed(db)
        branch_super_admin_headers = super_admin_headers_for_branch(db, branch)
        group = create_customer_group(
            client, branch.id, branch_super_admin_headers, name="موظفين", name_ar="موظفين", discount_percentage="15",
        )
        assert group["discount_percentage"] == "15.00" or float(group["discount_percentage"]) == 15
        assert group["is_active"] is True

        list_resp = client.get("/api/v1/crm/customer-groups", params={"branch_id": branch.id}, headers=manager_headers)
        assert list_resp.status_code == 200
        assert any(g["id"] == group["id"] for g in list_resp.json())

        update_resp = client.patch(
            f"/api/v1/crm/customer-groups/{group['id']}",
            json={"discount_percentage": "20", "is_active": False},
            headers=branch_super_admin_headers,
        )
        assert update_resp.status_code == 200, update_resp.text
        assert float(update_resp.json()["discount_percentage"]) == 20
        assert update_resp.json()["is_active"] is False

    def test_list_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.get("/api/v1/crm/customer-groups", params={"branch_id": branch.id}, headers=waiter_headers)
        assert resp.status_code == 403


class TestAssignCustomerGroup:
    """PATCH /crm/customers/{id}/group — مقفول على مدير+ عمدًا (مش
    get_current_active_user زي باقي حقول CustomerUpdate)، لأن تعيين مجموعة
    يمنح خصم دائم تلقائي فعلي."""

    def test_assign_requires_manager_not_just_active_user(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)
        resp = client.patch(
            f"/api/v1/crm/customers/{customer['id']}/group",
            json={"customer_group_id": 1}, headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_assign_and_unassign_round_trip(self, client: TestClient, db, waiter_headers, manager_headers, super_admin_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)
        group = create_customer_group(client, branch.id, super_admin_headers_for_branch(db, branch))

        assign_resp = client.patch(
            f"/api/v1/crm/customers/{customer['id']}/group",
            json={"customer_group_id": group["id"]}, headers=manager_headers,
        )
        assert assign_resp.status_code == 200, assign_resp.text
        assert assign_resp.json()["customer_group_id"] == group["id"]

        unassign_resp = client.patch(
            f"/api/v1/crm/customers/{customer['id']}/group",
            json={"customer_group_id": None}, headers=manager_headers,
        )
        assert unassign_resp.status_code == 200
        assert unassign_resp.json()["customer_group_id"] is None

    def test_assign_rejects_group_from_other_branch(self, client: TestClient, db, waiter_headers, manager_headers, super_admin_headers):
        branch_a = make_branch_committed(db)
        branch_b = make_branch_committed(db)
        # make_branch_committed بتربط waiter_headers تلقائيًا بأحدث فرع
        # (branch_b) — هنا محتاجينه ينشئ عميل على branch_a تحديدًا فبنرجّع
        # الربط له صراحةً.
        _link_shared_users_to_branch(db, branch_a.id)
        customer = create_customer(client, branch_a.id, waiter_headers)
        other_group = create_customer_group(client, branch_b.id, super_admin_headers_for_branch(db, branch_b))

        resp = client.patch(
            f"/api/v1/crm/customers/{customer['id']}/group",
            json={"customer_group_id": other_group["id"]}, headers=manager_headers,
        )
        assert resp.status_code == 400


class TestListCustomersGroupDiscountEnrichment:
    """2026-08-04: GET /crm/customers (اللي شاشة اختيار العميل في POS
    بتناديها) كانت بترجّع customer_group_id (رقم خام بس) من غير الاسم
    أو النسبة — يعني الكاشير مالوش أي طريقة يشوف "العميل ده عنده خصم
    دائم" وقت الاختيار، الخصم كان بيظهر في الإجمالي بس في الآخر."""

    def test_customer_with_active_group_shows_name_and_percentage(
        self, client: TestClient, db, waiter_headers, manager_headers, super_admin_headers,
    ):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)
        group = create_customer_group(
            client, branch.id, super_admin_headers_for_branch(db, branch),
            name="VIP", name_ar="ضيوف مميزون", discount_percentage="15",
        )
        client.patch(
            f"/api/v1/crm/customers/{customer['id']}/group",
            json={"customer_group_id": group["id"]}, headers=manager_headers,
        )

        resp = client.get("/api/v1/crm/customers", params={"branch_id": branch.id}, headers=waiter_headers)
        assert resp.status_code == 200, resp.text
        row = next(c for c in resp.json()["items"] if c["id"] == customer["id"])
        assert row["group_name"] == "ضيوف مميزون"
        assert float(row["group_discount_percentage"]) == 15.0

    def test_customer_with_inactive_group_shows_no_discount(
        self, client: TestClient, db, waiter_headers, manager_headers, super_admin_headers,
    ):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)
        admin_headers = super_admin_headers_for_branch(db, branch)
        group = create_customer_group(client, branch.id, admin_headers, discount_percentage="20")
        client.patch(
            f"/api/v1/crm/customers/{customer['id']}/group",
            json={"customer_group_id": group["id"]}, headers=manager_headers,
        )
        client.patch(f"/api/v1/crm/customer-groups/{group['id']}", json={"is_active": False}, headers=admin_headers)

        resp = client.get("/api/v1/crm/customers", params={"branch_id": branch.id}, headers=waiter_headers)
        row = next(c for c in resp.json()["items"] if c["id"] == customer["id"])
        assert row["group_discount_percentage"] is None
        assert row["group_name"] is None

    def test_customer_without_group_shows_no_discount(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)

        resp = client.get("/api/v1/crm/customers", params={"branch_id": branch.id}, headers=waiter_headers)
        row = next(c for c in resp.json()["items"] if c["id"] == customer["id"])
        assert row["group_discount_percentage"] is None


class TestInteractionsEndpoints:
    def test_log_and_list_interactions(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)

        log_resp = client.post(
            "/api/v1/crm/interactions",
            json={
                "customer_id": customer["id"], "branch_id": branch.id,
                "interaction_type": "call", "direction": "outbound",
                "summary": "تأكيد الحجز", "occurred_at": datetime.utcnow().isoformat(),
            },
            headers=waiter_headers,
        )
        assert log_resp.status_code == 201, log_resp.text

        list_resp = client.get(f"/api/v1/crm/customers/{customer['id']}/interactions", headers=waiter_headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] == 1

    def test_log_interaction_for_missing_customer_returns_400(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/crm/interactions",
            json={
                "customer_id": 999999999, "branch_id": branch.id,
                "interaction_type": "call", "summary": "test",
                "occurred_at": datetime.utcnow().isoformat(),
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 400


class TestOpportunitiesEndpoints:
    def test_create_and_list(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)

        create_resp = client.post(
            "/api/v1/crm/opportunities",
            json={
                "branch_id": branch.id, "customer_id": customer["id"], "title": "بيع وحدة ملكية جزئية",
                "product_type": "timeshare", "expected_value": "50000.00",
            },
            headers=waiter_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        opp = create_resp.json()

        list_resp = client.get("/api/v1/crm/opportunities", params={"branch_id": branch.id}, headers=waiter_headers)
        assert any(o["id"] == opp["id"] for o in list_resp.json()["items"])

    def test_filter_by_stage(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)
        client.post(
            "/api/v1/crm/opportunities",
            json={
                "branch_id": branch.id, "customer_id": customer["id"], "title": "فرصة 1",
                "product_type": "leasing", "expected_value": "1000",
            },
            headers=waiter_headers,
        )
        resp = client.get(
            "/api/v1/crm/opportunities", params={"branch_id": branch.id, "stage": "won"}, headers=waiter_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0  # لسه في lead، مش won


class TestActivitiesEndpoints:
    def test_create_and_list(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)

        create_resp = client.post(
            "/api/v1/crm/activities",
            json={
                "branch_id": branch.id, "customer_id": customer["id"], "activity_type": "follow_up",
                "title": "متابعة بعد أسبوع", "due_date": str(date.today() + timedelta(days=7)),
            },
            headers=waiter_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        activity = create_resp.json()

        list_resp = client.get(
            "/api/v1/crm/activities", params={"branch_id": branch.id, "customer_id": customer["id"]},
            headers=waiter_headers,
        )
        assert any(a["id"] == activity["id"] for a in list_resp.json()["items"])

    def test_filter_by_due_before(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        customer = create_customer(client, branch.id, waiter_headers)
        client.post(
            "/api/v1/crm/activities",
            json={
                "branch_id": branch.id, "customer_id": customer["id"], "activity_type": "meeting",
                "title": "اجتماع بعيد", "due_date": str(date.today() + timedelta(days=60)),
            },
            headers=waiter_headers,
        )
        resp = client.get(
            "/api/v1/crm/activities",
            params={"branch_id": branch.id, "due_before": str(date.today() + timedelta(days=10))},
            headers=waiter_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
