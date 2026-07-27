"""PMS fine-grained authorization regression tests.

The PMS previously used ``get_current_active_user`` for guest/booking/room
reads and housekeeping writes, so any active waiter/employee/customer account
could reach operational or personal data. These tests exercise the real HTTP
dependencies and explicit UserPermission override behavior.
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.modules.core.permission_catalog import PERMISSION_CATALOG
from tests.conftest import _create_test_user, _make_token
from tests.test_api.test_pms_http import (
    link_user_to_branch,
    make_branch_committed,
    make_room_committed,
    make_room_type_committed,
)


def _headers_for_new_user(role: str) -> tuple[int, dict[str, str]]:
    email = f"pms-perm-{role}-{uuid.uuid4().hex[:8]}@test.local"
    user_id = _create_test_user(email, role)
    return user_id, {"Authorization": f"Bearer {_make_token(email)}"}


def _permission(
    db,
    user_id: int,
    resource: str,
    action: str,
    *,
    allowed: bool,
    branch_id: int | None = None,
):
    from app.modules.core.models import UserPermission

    db.add(UserPermission(
        user_id=user_id,
        resource=resource,
        action=action,
        allowed=allowed,
        branch_id=branch_id,
        granted_by=None,
    ))
    db.commit()


def _housekeeping_task(db, branch, room):
    from app.modules.pms.models import HousekeepingTask

    task = HousekeepingTask(
        branch_id=branch.id,
        room_id=room.id,
        task_type="checkout_clean",
        status="dirty",
    )
    db.add(task)
    db.commit()
    return task


class TestPMSRoleFallback:
    def test_waiter_cannot_read_internal_pms_surfaces(
        self,
        client: TestClient,
        db,
        fake_redis,
        waiter_headers,
    ):
        branch = make_branch_committed(db)
        requests = [
            ("/api/v1/pms/room-types", {"branch_id": branch.id}),
            ("/api/v1/pms/rooms", {"branch_id": branch.id}),
            ("/api/v1/pms/bookings", {"branch_id": branch.id}),
            ("/api/v1/pms/housekeeping/tasks", {"branch_id": branch.id}),
            ("/api/v1/pms/rate-plans", {"branch_id": branch.id}),
        ]

        for path, params in requests:
            response = client.get(path, params=params, headers=waiter_headers)
            assert response.status_code == 403, (path, response.text)
            assert response.json()["detail"]["code"] == "PERMISSION_DENIED"

    def test_cashier_keeps_operational_read_access(
        self,
        client: TestClient,
        db,
        fake_redis,
        cashier_headers,
    ):
        branch = make_branch_committed(db)
        requests = [
            ("/api/v1/pms/room-types", {"branch_id": branch.id}),
            ("/api/v1/pms/rooms", {"branch_id": branch.id}),
            ("/api/v1/pms/bookings", {"branch_id": branch.id}),
            ("/api/v1/pms/housekeeping/tasks", {"branch_id": branch.id}),
            ("/api/v1/pms/rate-plans", {"branch_id": branch.id}),
        ]

        for path, params in requests:
            response = client.get(path, params=params, headers=cashier_headers)
            assert response.status_code == 200, (path, response.text)

    def test_waiter_cannot_update_housekeeping_by_being_active(
        self,
        client: TestClient,
        db,
        fake_redis,
        waiter_headers,
    ):
        branch = make_branch_committed(db)
        room_type = make_room_type_committed(db, branch)
        room = make_room_committed(db, branch, room_type)
        task = _housekeeping_task(db, branch, room)

        response = client.patch(
            f"/api/v1/pms/housekeeping/tasks/{task.id}",
            json={"status": "cleaning"},
            headers=waiter_headers,
        )

        assert response.status_code == 403
        db.refresh(task)
        assert task.status == "dirty"


class TestPMSExplicitOverrides:
    def test_explicit_grants_allow_narrow_housekeeping_employee(
        self,
        client: TestClient,
        db,
        fake_redis,
    ):
        employee_id, employee_headers = _headers_for_new_user("employee")
        _permission(db, employee_id, "pms.housekeeping", "view", allowed=True)
        _permission(db, employee_id, "pms.housekeeping", "update", allowed=True)

        branch = make_branch_committed(db)
        link_user_to_branch(db, employee_id, branch)
        room_type = make_room_type_committed(db, branch)
        room = make_room_committed(db, branch, room_type)
        task = _housekeeping_task(db, branch, room)

        listed = client.get(
            "/api/v1/pms/housekeeping/tasks",
            params={"branch_id": branch.id},
            headers=employee_headers,
        )
        assert listed.status_code == 200, listed.text
        assert [row["id"] for row in listed.json()] == [task.id]

        updated = client.patch(
            f"/api/v1/pms/housekeeping/tasks/{task.id}",
            json={"status": "cleaning"},
            headers=employee_headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["status"] == "cleaning"

        # The narrow grant does not leak booking/guest access.
        bookings = client.get(
            "/api/v1/pms/bookings",
            params={"branch_id": branch.id},
            headers=employee_headers,
        )
        assert bookings.status_code == 403

    def test_explicit_deny_blocks_manager_booking_read(
        self,
        client: TestClient,
        db,
        fake_redis,
    ):
        manager_id, manager_headers = _headers_for_new_user("manager")
        _permission(db, manager_id, "pms.bookings", "view", allowed=False)
        branch = make_branch_committed(db)
        link_user_to_branch(db, manager_id, branch)

        response = client.get(
            "/api/v1/pms/bookings",
            params={"branch_id": branch.id},
            headers=manager_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"]["resource"] == "pms.bookings"

    def test_branch_scoped_deny_is_applied_to_linked_manager(
        self,
        client: TestClient,
        db,
        fake_redis,
    ):
        manager_id, manager_headers = _headers_for_new_user("manager")
        branch = make_branch_committed(db)
        link_user_to_branch(db, manager_id, branch)
        _permission(
            db,
            manager_id,
            "pms.bookings",
            "view",
            allowed=False,
            branch_id=branch.id,
        )

        response = client.get(
            "/api/v1/pms/bookings",
            params={"branch_id": branch.id},
            headers=manager_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"]["resource"] == "pms.bookings"


class TestPMSPermissionCatalog:
    def test_pms_catalog_pairs_are_unique_and_complete(self):
        pms_entries = [entry for entry in PERMISSION_CATALOG if entry["module"] == "pms"]
        pairs = {(entry["resource"], entry["action"]) for entry in pms_entries}

        assert len(pairs) == len(pms_entries)
        assert {
            ("pms.rooms", "view"),
            ("pms.rooms", "update_status"),
            ("pms.room_configuration", "manage"),
            ("pms.bookings", "view"),
            ("pms.bookings", "create"),
            ("pms.bookings", "check_in"),
            ("pms.bookings", "check_out"),
            ("pms.bookings", "early_late"),
            ("pms.cancel_booking", "execute"),
            ("pms.housekeeping", "view"),
            ("pms.housekeeping", "update"),
            ("pms.rate_plans", "view"),
            ("pms.rate_plans", "manage"),
            ("pms.night_audit", "view"),
            ("pms.night_audit", "run"),
        } == pairs

    def test_every_catalog_action_is_accepted_by_permission_schema(self):
        from app.modules.core.schemas import UserPermissionCreate

        for entry in PERMISSION_CATALOG:
            parsed = UserPermissionCreate(
                resource=entry["resource"],
                action=entry["action"],
                allowed=True,
            )
            assert parsed.action == entry["action"]
