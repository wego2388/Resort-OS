"""
tests/test_api/test_maintenance_http.py
HTTP-level tests for the maintenance router — test_maintenance.py already
covers services.py business rules directly; this file covers what only a
real HTTP request exercises: role gates, status codes, pagination, and 404s.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Maintenance HTTP Branch", name_ar="فرع الصيانة",
               code=f"MNT-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_employee_committed(db, branch, phone: str | None = None):
    from datetime import date as _date
    from decimal import Decimal
    from app.modules.hr.models import Employee
    emp = Employee(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name="فني صيانة", position="Technician", basic_salary=Decimal("4000.00"),
        hire_date=_date.today(), phone=phone,
    )
    db.add(emp)
    db.commit()
    return emp


def create_asset(client: TestClient, branch_id: int, headers: dict) -> dict:
    resp = client.post(
        "/api/v1/maintenance/assets",
        json={"branch_id": branch_id, "name": "مكيف اللوبي", "code": f"AST-{uuid.uuid4().hex[:6]}", "category": "hvac"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestAssetsEndpoints:
    def test_create_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/maintenance/assets",
            json={"branch_id": branch.id, "name": "أصل", "code": "AST-1", "category": "hvac"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_create_list_and_get(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)

        list_resp = client.get("/api/v1/maintenance/assets", params={"branch_id": branch.id}, headers=waiter_headers)
        assert list_resp.status_code == 200
        assert any(a["id"] == asset["id"] for a in list_resp.json()["items"])

        get_resp = client.get(f"/api/v1/maintenance/assets/{asset['id']}", headers=waiter_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["code"] == asset["code"]

    def test_get_missing_asset_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/maintenance/assets/999999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_update_asset(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        resp = client.patch(
            f"/api/v1/maintenance/assets/{asset['id']}", json={"location": "الدور الثاني"}, headers=manager_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["location"] == "الدور الثاني"

    def test_dispose_requires_admin_not_just_manager(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        resp = client.post(f"/api/v1/maintenance/assets/{asset['id']}/dispose", headers=manager_headers)
        assert resp.status_code == 403

    def test_dispose_as_admin_succeeds(self, client: TestClient, db, manager_headers):
        from tests.conftest import _create_test_user, _make_token
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        email = f"maint-admin-{uuid.uuid4().hex[:6]}@test.local"
        _create_test_user(email, "admin")
        headers = {"Authorization": f"Bearer {_make_token(email)}"}

        resp = client.post(f"/api/v1/maintenance/assets/{asset['id']}/dispose", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "disposed"


class TestWorkOrdersEndpoints:
    def test_any_active_user_can_report_a_work_order(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "تسريب مياه في الحمام", "priority": "high"},
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "open"

    def test_list_get_and_update(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "عطل كهربائي", "priority": "critical"},
            headers=waiter_headers,
        ).json()

        list_resp = client.get("/api/v1/maintenance/work-orders", params={"branch_id": branch.id}, headers=waiter_headers)
        assert any(w["id"] == wo["id"] for w in list_resp.json()["items"])

        get_resp = client.get(f"/api/v1/maintenance/work-orders/{wo['id']}", headers=waiter_headers)
        assert get_resp.status_code == 200

        update_resp = client.patch(
            f"/api/v1/maintenance/work-orders/{wo['id']}", json={"status": "in_progress"}, headers=waiter_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "in_progress"

    def test_get_missing_work_order_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/maintenance/work-orders/999999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_critical_work_order_creation_queues_notification_task(
        self, client: TestClient, db, waiter_headers,
    ):
        """wagdy.md #7: priority=critical لازم يطلق notify_critical_work_order
        عبر .delay() من غير ما يعطّل رد الـ API. الـ task نفسه (بحثه عن الـ WO
        عبر SessionLocal منفصلة + استدعاء send_whatsapp_message الفعلي) مُختبَر
        بشكل مباشر ومعزول في test_tasks/test_maintenance_tasks.py — هنا بس
        بنتأكد إن إنشاء أمر عاجل بينجح ومبيتأخرش (الإرسال async مش sync)."""
        from unittest.mock import patch
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch, phone="01098765432")

        with patch("app.tasks.maintenance_tasks.notify_critical_work_order.delay") as mock_delay:
            resp = client.post(
                "/api/v1/maintenance/work-orders",
                json={
                    "branch_id": branch.id, "title": "تسريب غاز مطبخ",
                    "priority": "critical", "assigned_to": emp.id,
                },
                headers=waiter_headers,
            )
        assert resp.status_code == 201, resp.text
        mock_delay.assert_called_once_with(resp.json()["id"])

    def test_non_critical_work_order_does_not_queue_notification(self, client: TestClient, db, waiter_headers):
        from unittest.mock import patch
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch, phone="01098765432")

        with patch("app.tasks.maintenance_tasks.notify_critical_work_order.delay") as mock_delay:
            resp = client.post(
                "/api/v1/maintenance/work-orders",
                json={
                    "branch_id": branch.id, "title": "لمبة محروقة",
                    "priority": "low", "assigned_to": emp.id,
                },
                headers=waiter_headers,
            )
        assert resp.status_code == 201, resp.text
        mock_delay.assert_not_called()

    def test_update_and_add_part_reject_customer_role(self, client: TestClient, db, waiter_headers):
        """Regression: PATCH .../work-orders/{id} and POST .../parts used to
        accept *any* authenticated user (get_current_active_user, level 0) —
        including a self-registered "customer" account — with no ownership
        check, letting them reassign/reprioritize/cost real maintenance work
        orders. Both now require get_employee_user (level >= 20)."""
        from tests.conftest import _create_test_user, _make_token
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "تسريب مياه"},
            headers=waiter_headers,
        ).json()

        email = f"maint-customer-{uuid.uuid4().hex[:6]}@test.local"
        _create_test_user(email, "customer")
        customer_headers = {"Authorization": f"Bearer {_make_token(email)}"}

        update_resp = client.patch(
            f"/api/v1/maintenance/work-orders/{wo['id']}",
            json={"status": "in_progress"},
            headers=customer_headers,
        )
        assert update_resp.status_code == 403

        part_resp = client.post(
            f"/api/v1/maintenance/work-orders/{wo['id']}/parts",
            json={"part_name": "مضخة", "quantity": 1, "unit_cost": 500},
            headers=customer_headers,
        )
        assert part_resp.status_code == 403

    def test_complete_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "صيانة مصعد"},
            headers=waiter_headers,
        ).json()
        resp = client.post(f"/api/v1/maintenance/work-orders/{wo['id']}/complete", headers=waiter_headers)
        assert resp.status_code == 403

    def test_complete_as_manager_succeeds(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "صيانة مصعد"},
            headers=waiter_headers,
        ).json()
        resp = client.post(f"/api/v1/maintenance/work-orders/{wo['id']}/complete", headers=manager_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_assign_to_nonexistent_employee_rejected_cleanly(self, client: TestClient, db, waiter_headers):
        """Regression: assigned_to had zero validation against the employees
        table — assigning a work order to a made-up employee id used to
        return 200 OK with no warning at all. Now a clean 400."""
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "عطل كهربائي"},
            headers=waiter_headers,
        ).json()
        resp = client.patch(
            f"/api/v1/maintenance/work-orders/{wo['id']}",
            json={"assigned_to": 999999},
            headers=waiter_headers,
        )
        assert resp.status_code == 400
        assert "غير موجود" in resp.json()["detail"]

    def test_add_part_increases_cost(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "تغيير فلتر"},
            headers=waiter_headers,
        ).json()
        resp = client.post(
            f"/api/v1/maintenance/work-orders/{wo['id']}/parts",
            json={"part_name": "فلتر هواء", "quantity": "2", "unit_cost": "50.00"},
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text


class TestPreventiveSchedulesEndpoints:
    def test_create_list_and_update(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)

        create_resp = client.post(
            "/api/v1/maintenance/preventive-schedules",
            json={
                "branch_id": branch.id, "asset_id": asset["id"], "title": "صيانة دورية شهرية",
                "frequency_days": 30, "next_due": str(date.today() + timedelta(days=30)),
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        schedule = create_resp.json()

        list_resp = client.get(
            "/api/v1/maintenance/preventive-schedules", params={"branch_id": branch.id}, headers=waiter_headers,
        )
        assert any(s["id"] == schedule["id"] for s in list_resp.json()["items"])

        update_resp = client.patch(
            f"/api/v1/maintenance/preventive-schedules/{schedule['id']}",
            json={"frequency_days": 60}, headers=manager_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["frequency_days"] == 60

    def test_create_with_nonexistent_employee_rejected_cleanly(self, client: TestClient, db, manager_headers):
        """Regression: PreventiveSchedule.assigned_to has a real DB-level FK to
        employees, but nothing validated it beforehand — assigning a schedule
        to a made-up employee id used to bubble up as a raw 500
        ("Database operation failed") instead of a clear 400."""
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        resp = client.post(
            "/api/v1/maintenance/preventive-schedules",
            json={
                "branch_id": branch.id, "asset_id": asset["id"], "title": "صيانة دورية",
                "frequency_days": 30, "next_due": str(date.today() + timedelta(days=30)),
                "assigned_to": 999999,
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400
        assert "غير موجود" in resp.json()["detail"]

    def test_create_by_waiter_rejected(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        resp = client.post(
            "/api/v1/maintenance/preventive-schedules",
            json={
                "branch_id": branch.id, "asset_id": asset["id"], "title": "صيانة",
                "frequency_days": 30, "next_due": str(date.today() + timedelta(days=30)),
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 403
