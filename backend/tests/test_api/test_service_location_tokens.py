"""
tests/test_api/test_service_location_tokens.py
HTTP-level tests for the Service Location token feature (Gate 8 Phase 1
Batch B) — راجع docs/decisions/0001-qr-guest-service-mode.md بند 5/6 و
app/modules/core/models.py::ServiceLocationToken.

POST /service-location-tokens (مدير+، branch-scoped) يولّد/يدوّر رمز.
GET  /public/service-location (بدون auth) يحلّل الرمز لسياق حقيقي — الرابط
المطبوع على QR ميحملش أي outlet_id/table_id خام أبدًا.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Service Location Branch", name_ar="فرع اختبار الرموز",
               code=f"SLOC-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.commit()
    return b


def make_dining_table(db, branch):
    from app.modules.dining.models import VenueTable
    t = VenueTable(branch_id=branch.id, table_number=f"T-{uuid.uuid4().hex[:6].upper()}", capacity=4)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def make_branch_linked_headers(db, branch, role="manager") -> dict[str, str]:
    """نفس نمط test_guest_alerts.py's make_branch_linked_waiter_headers —
    مستخدم Employee-linked جديد لكل تست بدل الـ fixture المشترك، عشان
    assert_branch_access يقدر يحدد فرع المستخدم فعليًا."""
    from tests.conftest import _create_test_user, _make_token
    from app.modules.hr.models import Employee

    email = f"{role}-{uuid.uuid4().hex[:10]}@test.local"
    user_id = _create_test_user(email, role)
    emp = Employee(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name=f"{role} اختبار الرموز", national_id="29001011234567",
        position=role, department="F&B", basic_salary=Decimal("4000.00"),
        hire_date=date.today() - timedelta(days=365), user_id=user_id,
    )
    db.add(emp)
    db.commit()
    return {"Authorization": f"Bearer {_make_token(email)}"}


class TestCreateServiceLocationToken:
    def test_manager_mints_token_for_own_branch(self, client: TestClient, db):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        headers = make_branch_linked_headers(db, branch, role="manager")

        resp = client.post(
            "/api/v1/service-location-tokens",
            json={"branch_id": branch.id, "location_type": "dining_table", "location_id": table.id},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["branch_id"] == branch.id
        assert body["location_type"] == "dining_table"
        assert body["location_id"] == table.id
        assert body["is_active"] is True
        assert len(body["token"]) > 20

    def test_waiter_forbidden(self, client: TestClient, db):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        headers = make_branch_linked_headers(db, branch, role="waiter")

        resp = client.post(
            "/api/v1/service-location-tokens",
            json={"branch_id": branch.id, "location_type": "dining_table", "location_id": table.id},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_manager_from_different_branch_forbidden(self, client: TestClient, db):
        branch = make_branch(db)
        other_branch = make_branch(db)
        table = make_dining_table(db, branch)
        headers = make_branch_linked_headers(db, other_branch, role="manager")

        resp = client.post(
            "/api/v1/service-location-tokens",
            json={"branch_id": branch.id, "location_type": "dining_table", "location_id": table.id},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_rejects_table_from_different_branch(self, client: TestClient, db):
        branch = make_branch(db)
        other_branch = make_branch(db)
        table = make_dining_table(db, other_branch)
        headers = make_branch_linked_headers(db, branch, role="manager")

        resp = client.post(
            "/api/v1/service-location-tokens",
            json={"branch_id": branch.id, "location_type": "dining_table", "location_id": table.id},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_rotate_deactivates_previous_token(self, client: TestClient, db):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        headers = make_branch_linked_headers(db, branch, role="manager")

        first = client.post(
            "/api/v1/service-location-tokens",
            json={"branch_id": branch.id, "location_type": "dining_table", "location_id": table.id},
            headers=headers,
        ).json()
        second = client.post(
            "/api/v1/service-location-tokens",
            json={"branch_id": branch.id, "location_type": "dining_table", "location_id": table.id},
            headers=headers,
        ).json()
        assert first["token"] != second["token"]

        resolve_old = client.get(
            "/api/v1/public/service-location", params={"token": first["token"]},
        )
        assert resolve_old.status_code == 404

        resolve_new = client.get(
            "/api/v1/public/service-location", params={"token": second["token"]},
        )
        assert resolve_new.status_code == 200


class TestResolveServiceLocationPublic:
    def test_resolve_valid_token_no_auth(self, client: TestClient, db):
        branch = make_branch(db)
        table = make_dining_table(db, branch)
        headers = make_branch_linked_headers(db, branch, role="manager")
        minted = client.post(
            "/api/v1/service-location-tokens",
            json={"branch_id": branch.id, "location_type": "dining_table", "location_id": table.id},
            headers=headers,
        ).json()

        resp = client.get("/api/v1/public/service-location", params={"token": minted["token"]})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["branch_id"] == branch.id
        assert body["location_type"] == "dining_table"
        assert body["location_id"] == table.id
        assert table.table_number in body["location_label"]
        assert "token" not in body

    def test_resolve_unknown_token_404(self, client: TestClient):
        resp = client.get("/api/v1/public/service-location", params={"token": "does-not-exist"})
        assert resp.status_code == 404
