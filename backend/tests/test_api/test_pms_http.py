"""
tests/test_api/test_pms_http.py
HTTP-level tests for the PMS module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

Regression coverage for a real routing bug found+fixed this session:
`GET /pms/housekeeping/tasks` + `PATCH /pms/housekeeping/tasks/{id}` were used
by frontend/apps/ops/src/views/HousekeepingView.vue and backed by working
crud.py functions (list_housekeeping_tasks/update_housekeeping_task) and a
real model (HousekeepingTask, auto-created by checkout_booking) — but had
ZERO route wired in api/router.py. Same class of bug as the
GET /restaurant/menu/categories 404 documented in CLAUDE.md § 11.6.

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="PMS HTTP Branch", name_ar="فرع فندقي",
               code=f"PMS-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_room_type_committed(db, branch):
    from app.modules.pms.models import RoomType
    rt = RoomType(branch_id=branch.id, name="Standard", name_ar="عادية",
                  base_rate=Decimal("500.00"), max_occupancy=2)
    db.add(rt)
    db.commit()
    return rt


def make_room_committed(db, branch, room_type, name="101"):
    from app.modules.pms.models import Room
    room = Room(branch_id=branch.id, room_type_id=room_type.id, name=name, floor=1, status="available")
    db.add(room)
    db.commit()
    return room


class TestBookingLifecycleHTTP:
    def test_full_booking_checkin_checkout_creates_housekeeping_task(
        self, client: TestClient, db, fake_redis, manager_headers,
    ):
        branch = make_branch_committed(db)
        room_type = make_room_type_committed(db, branch)
        room = make_room_committed(db, branch, room_type)

        create_resp = client.post(
            "/api/v1/pms/bookings",
            json={
                "branch_id": branch.id, "guest_name": "خالد إبراهيم",
                "check_in": str(date.today()), "check_out": str(date.today() + timedelta(days=2)),
                "adults": 2, "children": 0, "room_ids": [room.id],
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        booking = create_resp.json()
        assert booking["status"] == "confirmed"

        checkin_resp = client.post(f"/api/v1/pms/bookings/{booking['id']}/checkin", headers=manager_headers)
        assert checkin_resp.status_code == 200, checkin_resp.text
        assert checkin_resp.json()["status"] == "checked_in"

        checkout_resp = client.post(f"/api/v1/pms/bookings/{booking['id']}/checkout", headers=manager_headers)
        assert checkout_resp.status_code == 200, checkout_resp.text
        assert checkout_resp.json()["status"] == "checked_out"

        # regression: housekeeping task must be listable via HTTP (route was missing)
        hk_resp = client.get(
            "/api/v1/pms/housekeeping/tasks",
            params={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert hk_resp.status_code == 200, hk_resp.text
        tasks = hk_resp.json()
        assert len(tasks) == 1
        assert tasks[0]["room_id"] == room.id
        assert tasks[0]["status"] == "dirty"

        # advance dirty -> cleaning -> inspecting -> available, then confirm the
        # room itself flips back to available (checkout_pending -> available)
        task_id = tasks[0]["id"]
        for next_status in ("cleaning", "inspecting", "available"):
            patch_resp = client.patch(
                f"/api/v1/pms/housekeeping/tasks/{task_id}",
                json={"status": next_status},
                headers=manager_headers,
            )
            assert patch_resp.status_code == 200, patch_resp.text
            assert patch_resp.json()["status"] == next_status

        rooms_resp = client.get(
            "/api/v1/pms/rooms", params={"branch_id": branch.id}, headers=manager_headers,
        )
        found = next(r for r in rooms_resp.json() if r["id"] == room.id)
        assert found["status"] == "available"

    def test_double_checkin_conflict_returns_409(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        room_type = make_room_type_committed(db, branch)
        room_a = make_room_committed(db, branch, room_type, "201")
        room_b = make_room_committed(db, branch, room_type, "202")

        booking = client.post(
            "/api/v1/pms/bookings",
            json={
                "branch_id": branch.id, "guest_name": "ضيف 1",
                "check_in": str(date.today()), "check_out": str(date.today() + timedelta(days=1)),
                "room_ids": [room_a.id],
            },
            headers=manager_headers,
        ).json()

        conflict_resp = client.post(
            "/api/v1/pms/bookings",
            json={
                "branch_id": branch.id, "guest_name": "ضيف 2",
                "check_in": str(date.today()), "check_out": str(date.today() + timedelta(days=1)),
                "room_ids": [room_a.id],
            },
            headers=manager_headers,
        )
        assert conflict_resp.status_code == 409

        # sanity: a genuinely free room in the same request works fine
        ok_resp = client.post(
            "/api/v1/pms/bookings",
            json={
                "branch_id": branch.id, "guest_name": "ضيف 3",
                "check_in": str(date.today()), "check_out": str(date.today() + timedelta(days=1)),
                "room_ids": [room_b.id],
            },
            headers=manager_headers,
        )
        assert ok_resp.status_code == 201


class TestPMSPermissions:
    def test_create_room_type_requires_admin(self, client: TestClient, db, fake_redis, manager_headers):
        """manager (60) must not create room types — admin (80) required."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/pms/room-types",
            json={"branch_id": branch.id, "name": "Suite", "base_rate": "1000.00", "max_occupancy": 4},
            headers=manager_headers,
        )
        assert resp.status_code == 403

    def test_create_booking_requires_manager(self, client: TestClient, db, fake_redis, cashier_headers):
        """cashier (40) must not create bookings — manager (60) required."""
        branch = make_branch_committed(db)
        room_type = make_room_type_committed(db, branch)
        room = make_room_committed(db, branch, room_type)
        resp = client.post(
            "/api/v1/pms/bookings",
            json={
                "branch_id": branch.id, "guest_name": "ضيف",
                "check_in": str(date.today()), "check_out": str(date.today() + timedelta(days=1)),
                "room_ids": [room.id],
            },
            headers=cashier_headers,
        )
        assert resp.status_code == 403


class TestPMSValidation:
    def test_create_booking_rejects_empty_room_ids(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/pms/bookings",
            json={
                "branch_id": branch.id, "guest_name": "ضيف",
                "check_in": str(date.today()), "check_out": str(date.today() + timedelta(days=1)),
                "room_ids": [],
            },
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_housekeeping_status_update_rejects_invalid_status(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        room_type = make_room_type_committed(db, branch)
        room = make_room_committed(db, branch, room_type)
        from app.modules.pms.models import HousekeepingTask
        task = HousekeepingTask(branch_id=branch.id, room_id=room.id, task_type="checkout_clean", status="dirty")
        db.add(task)
        db.commit()

        resp = client.patch(
            f"/api/v1/pms/housekeeping/tasks/{task.id}",
            json={"status": "sparkling_clean"},
            headers=manager_headers,
        )
        assert resp.status_code == 422


class TestRatePlans:
    """RatePlan كان عنده model + crud كاملين بدون أي schema/route متوصّل —
    نفس فئة باج 'الموديل موجود، الـ API صفر' (CallNote/RotaTemplate/
    RevenueAuditLog)."""

    def test_create_and_list_rate_plan(self, client: TestClient, db, fake_redis, super_admin_headers, manager_headers):
        branch = make_branch_committed(db)
        room_type = make_room_type_committed(db, branch)

        create_resp = client.post(
            "/api/v1/pms/rate-plans",
            json={
                "branch_id": branch.id, "room_type_id": room_type.id,
                "name": "High Season", "name_ar": "الموسم المرتفع",
                "rate_multiplier": "1.5000",
                "valid_from": str(date.today()), "valid_until": str(date.today() + timedelta(days=90)),
                "min_nights": 3,
            },
            headers=super_admin_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        plan = create_resp.json()
        assert plan["name"] == "High Season"
        assert Decimal(str(plan["rate_multiplier"])) == Decimal("1.5000")

        list_resp = client.get(
            "/api/v1/pms/rate-plans", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        get_resp = client.get(f"/api/v1/pms/rate-plans/{plan['id']}", headers=manager_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == plan["id"]

    def test_create_rate_plan_requires_admin(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/pms/rate-plans",
            json={
                "branch_id": branch.id, "name": "Low Season",
                "valid_from": str(date.today()), "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 403

    def test_create_rate_plan_rejects_invalid_date_range(self, client: TestClient, db, fake_redis, super_admin_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/pms/rate-plans",
            json={
                "branch_id": branch.id, "name": "Bad Range",
                "valid_from": str(date.today()), "valid_until": str(date.today() - timedelta(days=1)),
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 400

    def test_get_rate_plan_404(self, client: TestClient, db, fake_redis, manager_headers):
        resp = client.get("/api/v1/pms/rate-plans/999999", headers=manager_headers)
        assert resp.status_code == 404


class TestPublicRoomTypes:
    """للموقع العام — بدون تسجيل دخول، نفس نمط restaurant/public/menu."""

    def test_no_auth_required(self, client: TestClient, db, fake_redis):
        branch = make_branch_committed(db)
        make_room_type_committed(db, branch)

        resp = client.get("/api/v1/pms/public/room-types", params={"branch_id": branch.id})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["name"] == "Standard"
        assert Decimal(str(body[0]["base_rate"])) == Decimal("500.00")

    def test_excludes_inactive_room_types(self, client: TestClient, db, fake_redis, manager_headers):
        from app.modules.pms.models import RoomType
        branch = make_branch_committed(db)
        make_room_type_committed(db, branch)
        inactive = RoomType(branch_id=branch.id, name="Discontinued", base_rate=Decimal("300.00"), is_active=False)
        db.add(inactive)
        db.commit()

        resp = client.get("/api/v1/pms/public/room-types", params={"branch_id": branch.id})
        names = [rt["name"] for rt in resp.json()]
        assert "Standard" in names
        assert "Discontinued" not in names

    def test_empty_branch_returns_empty_list(self, client: TestClient, db, fake_redis):
        branch = make_branch_committed(db)
        resp = client.get("/api/v1/pms/public/room-types", params={"branch_id": branch.id})
        assert resp.status_code == 200
        assert resp.json() == []
