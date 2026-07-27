"""PMS branch/object isolation through the real HTTP and WebSocket stack.

These tests use two branches with real linked users. They verify both halves
of authorization: a permission decides *what* the user may do, while the
Employee link decides *where* it may be done. Cross-branch attempts must fail
before any PMS row changes.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import _create_test_user, _make_token, ws_url
from tests.test_api.test_pms_http import (
    link_user_to_branch,
    make_branch_committed,
    make_room_committed,
    make_room_type_committed,
)
from tests.test_api.test_pms_permissions_http import _permission


def _headers_for_user(role: str) -> tuple[int, dict[str, str]]:
    email = f"pms-branch-{role}-{uuid.uuid4().hex[:10]}@test.local"
    user_id = _create_test_user(email, role)
    return user_id, {"Authorization": f"Bearer {_make_token(email)}"}


def _super_admin_headers_for_branch(db, branch) -> dict[str, str]:
    from app.core.kernel.models.user import User

    user = db.query(User).filter(
        User.role == "super_admin",
        User.two_factor_enabled.is_(True),
    ).first()
    assert user is not None
    return {
        "Authorization": f"Bearer {_make_token(user.email, branch_id=branch.id)}"
    }


def _two_branches_with_rooms(db):
    branch_a = make_branch_committed(db)
    branch_b = make_branch_committed(db, link_fixture_users=False)
    room_type_a = make_room_type_committed(db, branch_a)
    room_type_b = make_room_type_committed(db, branch_b)
    room_a = make_room_committed(db, branch_a, room_type_a, f"A-{uuid.uuid4().hex[:6]}")
    room_b = make_room_committed(db, branch_b, room_type_b, f"B-{uuid.uuid4().hex[:6]}")
    return branch_a, branch_b, room_type_a, room_type_b, room_a, room_b


def _booking_payload(branch, room, guest_name: str = "ضيف اختبار") -> dict:
    return {
        "branch_id": branch.id,
        "guest_name": guest_name,
        "check_in": str(date.today()),
        "check_out": str(date.today() + timedelta(days=2)),
        "room_ids": [room.id],
    }


def _rate_plan(db, branch, room_type, name: str):
    from app.modules.pms.models import RatePlan

    plan = RatePlan(
        branch_id=branch.id,
        room_type_id=room_type.id,
        name=name,
        rate_multiplier=Decimal("1.1000"),
        valid_from=date.today(),
        valid_until=date.today() + timedelta(days=30),
        min_nights=1,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    return plan


class TestPMSBranchReadIsolation:
    def test_foreign_branch_queries_and_booking_id_are_denied(
        self,
        client: TestClient,
        db,
        fake_redis,
        manager_headers,
        super_admin_headers,
    ):
        branch_a, branch_b, *_rest, room_b = _two_branches_with_rooms(db)
        branch_b_super_admin = _super_admin_headers_for_branch(db, branch_b)
        booking_response = client.post(
            "/api/v1/pms/bookings",
            json=_booking_payload(branch_b, room_b, "ضيف الفرع ب"),
            headers=branch_b_super_admin,
        )
        assert booking_response.status_code == 201, booking_response.text
        booking_id = booking_response.json()["id"]

        own = client.get(
            "/api/v1/pms/rooms",
            params={"branch_id": branch_a.id},
            headers=manager_headers,
        )
        assert own.status_code == 200, own.text

        foreign_queries = (
            ("/api/v1/pms/room-types", {"branch_id": branch_b.id}),
            ("/api/v1/pms/rooms", {"branch_id": branch_b.id}),
            (
                "/api/v1/pms/rooms/available",
                {
                    "branch_id": branch_b.id,
                    "check_in": str(date.today()),
                    "check_out": str(date.today() + timedelta(days=1)),
                },
            ),
            ("/api/v1/pms/bookings", {"branch_id": branch_b.id}),
            ("/api/v1/pms/housekeeping/tasks", {"branch_id": branch_b.id}),
            ("/api/v1/pms/rate-plans", {"branch_id": branch_b.id}),
            ("/api/v1/pms/night-audit", {"branch_id": branch_b.id}),
        )
        for path, params in foreign_queries:
            response = client.get(path, params=params, headers=manager_headers)
            assert response.status_code == 403, (path, response.text)

        by_id = client.get(
            f"/api/v1/pms/bookings/{booking_id}",
            headers=manager_headers,
        )
        assert by_id.status_code == 403

        # The sole intended global control-plane exception remains explicit.
        global_read = client.get(
            f"/api/v1/pms/bookings/{booking_id}",
            headers=branch_b_super_admin,
        )
        assert global_read.status_code == 200, global_read.text

    def test_unlinked_staff_fails_closed_but_super_admin_is_global(
        self,
        client: TestClient,
        db,
        fake_redis,
        super_admin_headers,
    ):
        branch = make_branch_committed(db, link_fixture_users=False)
        selected_super_admin = _super_admin_headers_for_branch(db, branch)
        _user_id, unlinked_headers = _headers_for_user("manager")

        denied = client.get(
            "/api/v1/pms/rooms",
            params={"branch_id": branch.id},
            headers=unlinked_headers,
        )
        assert denied.status_code == 403
        assert "اختر فرعًا نشطًا" in denied.json()["detail"]

        allowed = client.get(
            "/api/v1/pms/rooms",
            params={"branch_id": branch.id},
            headers=selected_super_admin,
        )
        assert allowed.status_code == 200, allowed.text

    def test_narrow_branch_grant_does_not_expand_to_another_branch(
        self,
        client: TestClient,
        db,
        fake_redis,
    ):
        branch_a, branch_b, *_ = _two_branches_with_rooms(db)
        employee_id, employee_headers = _headers_for_user("employee")
        link_user_to_branch(db, employee_id, branch_a)
        _permission(
            db,
            employee_id,
            "pms.rooms",
            "view",
            allowed=True,
            branch_id=branch_a.id,
        )

        own = client.get(
            "/api/v1/pms/rooms",
            params={"branch_id": branch_a.id},
            headers=employee_headers,
        )
        assert own.status_code == 200, own.text

        foreign = client.get(
            "/api/v1/pms/rooms",
            params={"branch_id": branch_b.id},
            headers=employee_headers,
        )
        assert foreign.status_code == 403


class TestPMSBranchMutationIsolation:
    def test_foreign_object_mutations_are_denied_and_leave_rows_unchanged(
        self,
        client: TestClient,
        db,
        fake_redis,
        super_admin_headers,
    ):
        from app.modules.pms.models import HousekeepingTask, NightAuditLog, RatePlan

        branch_a, branch_b, _rt_a, rt_b, _room_a, room_b = _two_branches_with_rooms(db)
        branch_b_super_admin = _super_admin_headers_for_branch(db, branch_b)
        admin_id, admin_headers = _headers_for_user("admin")
        link_user_to_branch(db, admin_id, branch_a)

        booking_response = client.post(
            "/api/v1/pms/bookings",
            json=_booking_payload(branch_b, room_b, "ضيف ممنوع"),
            headers=branch_b_super_admin,
        )
        assert booking_response.status_code == 201, booking_response.text
        booking_id = booking_response.json()["id"]

        task = HousekeepingTask(
            branch_id=branch_b.id,
            room_id=room_b.id,
            task_type="checkout_clean",
            status="dirty",
        )
        db.add(task)
        db.commit()
        plan = _rate_plan(db, branch_b, rt_b, "Foreign plan")

        room_update = client.patch(
            f"/api/v1/pms/rooms/{room_b.id}/status",
            json={"status": "maintenance"},
            headers=admin_headers,
        )
        assert room_update.status_code == 403

        booking_mutations = (
            (f"/api/v1/pms/bookings/{booking_id}/checkin", None),
            (f"/api/v1/pms/bookings/{booking_id}/checkout", None),
            (f"/api/v1/pms/bookings/{booking_id}/cancel", None),
            (
                f"/api/v1/pms/bookings/{booking_id}/early-late",
                {"charge": "25.00"},
            ),
        )
        for path, payload in booking_mutations:
            response = client.post(path, json=payload, headers=admin_headers)
            assert response.status_code == 403, (path, response.text)

        housekeeping_update = client.patch(
            f"/api/v1/pms/housekeeping/tasks/{task.id}",
            json={"status": "cleaning"},
            headers=admin_headers,
        )
        assert housekeeping_update.status_code == 403

        plan_read = client.get(
            f"/api/v1/pms/rate-plans/{plan.id}",
            headers=admin_headers,
        )
        assert plan_read.status_code == 403
        plan_update = client.patch(
            f"/api/v1/pms/rate-plans/{plan.id}",
            json={"name": "Leaked update"},
            headers=admin_headers,
        )
        assert plan_update.status_code == 403

        audit_date = date.today() - timedelta(days=1)
        audit_run = client.post(
            "/api/v1/pms/night-audit/run",
            params={"branch_id": branch_b.id, "audit_date": str(audit_date)},
            headers=admin_headers,
        )
        assert audit_run.status_code == 403

        db.expire_all()
        from app.modules.pms.models import Booking, Room

        assert db.get(Room, room_b.id).status == "reserved"
        assert db.get(Booking, booking_id).status == "confirmed"
        assert db.get(HousekeepingTask, task.id).status == "dirty"
        assert db.get(RatePlan, plan.id).name == "Foreign plan"
        assert (
            db.query(NightAuditLog)
            .filter(
                NightAuditLog.branch_id == branch_b.id,
                NightAuditLog.audit_date == audit_date,
            )
            .count()
            == 0
        )

    def test_cross_branch_relationships_are_rejected_before_write(
        self,
        client: TestClient,
        db,
        fake_redis,
        manager_headers,
    ):
        from app.modules.crm.models import Customer
        from app.modules.hr.models import Employee
        from app.modules.pms.models import Booking, HousekeepingTask, RatePlan, Room

        branch_a, branch_b, rt_a, rt_b, room_a, room_b = _two_branches_with_rooms(db)
        admin_id, admin_headers = _headers_for_user("admin")
        link_user_to_branch(db, admin_id, branch_a)

        foreign_room_type = client.post(
            "/api/v1/pms/rooms",
            json={
                "branch_id": branch_a.id,
                "room_type_id": rt_b.id,
                "name": f"X-{uuid.uuid4().hex[:6]}",
            },
            headers=admin_headers,
        )
        assert foreign_room_type.status_code == 400

        foreign_plan_create = client.post(
            "/api/v1/pms/rate-plans",
            json={
                "branch_id": branch_a.id,
                "room_type_id": rt_b.id,
                "name": "Invalid cross-branch plan",
                "valid_from": str(date.today()),
                "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=admin_headers,
        )
        assert foreign_plan_create.status_code == 400

        local_plan = _rate_plan(db, branch_a, rt_a, "Local plan")
        foreign_plan = _rate_plan(db, branch_b, rt_b, "Branch B plan")
        plan_update = client.patch(
            f"/api/v1/pms/rate-plans/{local_plan.id}",
            json={"room_type_id": rt_b.id},
            headers=admin_headers,
        )
        assert plan_update.status_code == 400

        customer_b = Customer(branch_id=branch_b.id, full_name="عميل الفرع ب")
        employee_b = Employee(
            branch_id=branch_b.id,
            employee_code=f"FOREIGN-{uuid.uuid4().hex[:8].upper()}",
            full_name="عامل الفرع ب",
            position="housekeeping",
            basic_salary=Decimal("0"),
            hire_date=date.today(),
            status="active",
        )
        task_a = HousekeepingTask(
            branch_id=branch_a.id,
            room_id=room_a.id,
            task_type="checkout_clean",
            status="dirty",
        )
        db.add_all([customer_b, employee_b, task_a])
        db.commit()

        invalid_bookings = (
            {
                **_booking_payload(branch_a, room_b, "غرفة أجنبية"),
            },
            {
                **_booking_payload(branch_a, room_a, "عميل أجنبي"),
                "customer_id": customer_b.id,
            },
            {
                **_booking_payload(branch_a, room_a, "خطة أجنبية"),
                "rate_plan_id": foreign_plan.id,
            },
        )
        for payload in invalid_bookings:
            response = client.post(
                "/api/v1/pms/bookings",
                json=payload,
                headers=manager_headers,
            )
            assert response.status_code == 400, response.text

        invalid_assignment = client.patch(
            f"/api/v1/pms/housekeeping/tasks/{task_a.id}",
            json={"status": "cleaning", "assigned_to": employee_b.id},
            headers=manager_headers,
        )
        assert invalid_assignment.status_code == 400

        db.expire_all()
        assert db.get(RatePlan, local_plan.id).room_type_id == rt_a.id
        assert db.get(HousekeepingTask, task_a.id).status == "dirty"
        assert db.get(HousekeepingTask, task_a.id).assigned_to is None
        assert (
            db.query(Room)
            .filter(
                Room.branch_id == branch_a.id,
                Room.room_type_id == rt_b.id,
            )
            .count()
            == 0
        )
        assert db.query(Booking).filter(Booking.branch_id == branch_a.id).count() == 0


class TestPMSBranchWebSocketIsolation:
    def test_manager_cannot_subscribe_to_foreign_room_stream(
        self,
        client: TestClient,
        db,
        fake_redis,
        manager_headers,
    ):
        branch_a = make_branch_committed(db)
        branch_b = make_branch_committed(db, link_fixture_users=False)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                ws_url(f"/api/v1/pms/ws/rooms/{branch_b.id}", manager_headers)
            ):
                pass
        assert exc_info.value.code == 4403

        with client.websocket_connect(
            ws_url(f"/api/v1/pms/ws/rooms/{branch_a.id}", manager_headers)
        ) as ws:
            ws.send_text("ping")
            assert ws.receive_json()["type"] == "pong"
