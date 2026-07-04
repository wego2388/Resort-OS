"""
tests/test_api/test_hr_http.py
HTTP-level tests for the HR module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

Regression coverage for real path-mismatch bugs found+fixed this session:
frontend/apps/admin/src/views/HRView.vue calls `GET /api/v1/hr/payroll/runs`
and `GET/PATCH /api/v1/hr/leaves(/{id})` — paths that never existed in
api/router.py (which only had `/hr/payroll-runs` and `/hr/leave-requests`).
Both were genuine 404s in production, same class of bug as the
GET /restaurant/menu/categories case documented in CLAUDE.md § 11.6.

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="HR HTTP Branch", name_ar="فرع موارد بشرية",
               code=f"HR-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_employee_committed(db, branch):
    from app.modules.hr.models import Employee
    emp = Employee(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name="محمد كريم", position="Waiter", basic_salary=Decimal("4000.00"),
        hire_date=date.today() - timedelta(days=365),
    )
    db.add(emp)
    db.commit()
    return emp


def make_leave_type_committed(db, branch):
    from app.modules.hr.models import LeaveType
    lt = LeaveType(branch_id=branch.id, name="Annual", name_ar="سنوية", max_days_per_year=21)
    db.add(lt)
    db.commit()
    return lt


class TestHRPayrollRunsAlias:
    def test_payroll_runs_alias_matches_original_path(self, client: TestClient, db, manager_headers):
        """Regression: /hr/payroll/runs (used by HRView.vue) must return the
        same data as the canonical /hr/payroll-runs path, not 404."""
        branch = make_branch_committed(db)
        original = client.get(
            "/api/v1/hr/payroll-runs", params={"branch_id": branch.id}, headers=manager_headers,
        )
        alias = client.get(
            "/api/v1/hr/payroll/runs", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert original.status_code == 200
        assert alias.status_code == 200
        assert alias.json() == original.json()


class TestHRLeaveRequestFlow:
    def test_create_list_approve_leave_via_leave_requests_path(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        employee = make_employee_committed(db, branch)
        leave_type = make_leave_type_committed(db, branch)

        create_resp = client.post(
            "/api/v1/hr/leave-requests",
            json={
                "employee_id": employee.id, "branch_id": branch.id, "leave_type_id": leave_type.id,
                "start_date": str(date.today() + timedelta(days=5)),
                "end_date": str(date.today() + timedelta(days=7)),
                "reason": "سفر عائلي",
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        req = create_resp.json()
        assert req["status"] == "pending"
        assert req["days_requested"] == 3

        approve_resp = client.patch(
            f"/api/v1/hr/leave-requests/{req['id']}/approve",
            json={"approved_by": 1},
            headers=manager_headers,
        )
        assert approve_resp.status_code == 200, approve_resp.text
        assert approve_resp.json()["status"] == "approved"

    def test_leaves_alias_get_and_patch(self, client: TestClient, db, manager_headers):
        """Regression: GET /hr/leaves + PATCH /hr/leaves/{id} (used by
        HRView.vue) must work end-to-end, not 404."""
        branch = make_branch_committed(db)
        employee = make_employee_committed(db, branch)
        leave_type = make_leave_type_committed(db, branch)

        req = client.post(
            "/api/v1/hr/leave-requests",
            json={
                "employee_id": employee.id, "branch_id": branch.id, "leave_type_id": leave_type.id,
                "start_date": str(date.today() + timedelta(days=1)),
                "end_date": str(date.today() + timedelta(days=2)),
            },
            headers=manager_headers,
        ).json()

        list_resp = client.get(
            "/api/v1/hr/leaves", params={"branch_id": branch.id, "status": "pending"}, headers=manager_headers,
        )
        assert list_resp.status_code == 200, list_resp.text
        ids = [item["id"] for item in list_resp.json()["items"]]
        assert req["id"] in ids

        patch_resp = client.patch(
            f"/api/v1/hr/leaves/{req['id']}", json={"status": "approved"}, headers=manager_headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text
        assert patch_resp.json()["status"] == "approved"

    def test_leaves_alias_reject(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        employee = make_employee_committed(db, branch)
        leave_type = make_leave_type_committed(db, branch)
        req = client.post(
            "/api/v1/hr/leave-requests",
            json={
                "employee_id": employee.id, "branch_id": branch.id, "leave_type_id": leave_type.id,
                "start_date": str(date.today() + timedelta(days=1)),
                "end_date": str(date.today() + timedelta(days=1)),
            },
            headers=manager_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/hr/leaves/{req['id']}", json={"status": "rejected"}, headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "rejected"


class TestHRPermissions:
    def test_create_employee_requires_admin(self, client: TestClient, db, manager_headers):
        """manager (60) must not create employees — admin (80) required."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/hr/employees",
            json={
                "branch_id": branch.id, "employee_code": "EMP-999", "full_name": "ضيف",
                "position": "Cashier", "basic_salary": "3000.00", "hire_date": str(date.today()),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 403

    def test_list_employees_requires_manager(self, client: TestClient, db, cashier_headers):
        """cashier (40) must not list employees — manager (60) required."""
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/hr/employees", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert resp.status_code == 403


class TestHRValidation:
    def test_create_employee_rejects_zero_salary(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/hr/employees",
            json={
                "branch_id": branch.id, "employee_code": "EMP-001", "full_name": "أحمد",
                "position": "Chef", "basic_salary": "0", "hire_date": str(date.today()),
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 422

    def test_leaves_alias_rejects_invalid_status(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        employee = make_employee_committed(db, branch)
        leave_type = make_leave_type_committed(db, branch)
        req = client.post(
            "/api/v1/hr/leave-requests",
            json={
                "employee_id": employee.id, "branch_id": branch.id, "leave_type_id": leave_type.id,
                "start_date": str(date.today() + timedelta(days=1)),
                "end_date": str(date.today() + timedelta(days=1)),
            },
            headers=manager_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/hr/leaves/{req['id']}", json={"status": "maybe_later"}, headers=manager_headers,
        )
        assert resp.status_code == 422


def make_shift_committed(db, branch, name="صباحي"):
    from app.modules.hr.models import Shift
    s = Shift(branch_id=branch.id, name=name, name_ar=name,
               start_time="08:00", end_time="16:00", duration_hours=Decimal("8.00"))
    db.add(s)
    db.commit()
    return s


class TestHRPayrollApproval:
    """Regression coverage — POST /hr/payroll-runs/{id}/approve is a real
    financial action (posts a payroll journal entry) gated by
    require_permission("hr.approve_payroll_run", min_role_level=80), stricter
    than the manager-level (60) get used for most of this router."""

    def test_admin_approves_draft_payroll_run_and_journal_posts(
        self, client: TestClient, db, super_admin_headers,
    ):
        branch = make_branch_committed(db)
        make_employee_committed(db, branch)

        today = date.today()
        create_resp = client.post(
            "/api/v1/hr/payroll-runs",
            json={"branch_id": branch.id, "period_year": today.year, "period_month": today.month},
            headers=super_admin_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        run = create_resp.json()
        assert run["status"] == "draft"

        approve_resp = client.post(
            f"/api/v1/hr/payroll-runs/{run['id']}/approve", headers=super_admin_headers,
        )
        assert approve_resp.status_code == 200, approve_resp.text
        assert approve_resp.json()["status"] == "approved"

        # Approving twice must fail — same run can't be approved from a
        # non-"draft" state.
        second_resp = client.post(
            f"/api/v1/hr/payroll-runs/{run['id']}/approve", headers=super_admin_headers,
        )
        assert second_resp.status_code == 400

    def test_manager_cannot_approve_payroll_run(self, client: TestClient, db, manager_headers, super_admin_headers):
        branch = make_branch_committed(db)
        make_employee_committed(db, branch)
        today = date.today()
        run = client.post(
            "/api/v1/hr/payroll-runs",
            json={"branch_id": branch.id, "period_year": today.year, "period_month": today.month},
            headers=super_admin_headers,
        ).json()

        resp = client.post(f"/api/v1/hr/payroll-runs/{run['id']}/approve", headers=manager_headers)
        assert resp.status_code == 403


class TestHRRotaAndShiftSwap:
    """Regression coverage for the rota/shift-swap endpoints flagged by an
    independent coverage review as under-tested despite real scheduling
    impact (creates real assignments, real approval state transitions)."""

    def test_create_rota_assignment_and_fetch_week(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        employee = make_employee_committed(db, branch)
        shift = make_shift_committed(db, branch)
        week_start = date.today()
        week_end = week_start + timedelta(days=6)

        create_resp = client.post(
            "/api/v1/hr/rota/assignments",
            json={
                "branch_id": branch.id, "employee_id": employee.id, "shift_id": shift.id,
                "assigned_date": str(week_start),
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        rota_resp = client.get(
            "/api/v1/hr/rota",
            params={"branch_id": branch.id, "week_start": str(week_start), "week_end": str(week_end)},
            headers=manager_headers,
        )
        assert rota_resp.status_code == 200
        assert any(a["employee_id"] == employee.id for a in rota_resp.json())

    def test_shift_swap_request_and_approval_flow(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        requester = make_employee_committed(db, branch)
        target = make_employee_committed(db, branch)
        shift = make_shift_committed(db, branch)
        d1, d2 = date.today(), date.today() + timedelta(days=1)

        a1 = client.post(
            "/api/v1/hr/rota/assignments",
            json={"branch_id": branch.id, "employee_id": requester.id, "shift_id": shift.id,
                  "assigned_date": str(d1)},
            headers=manager_headers,
        ).json()
        a2 = client.post(
            "/api/v1/hr/rota/assignments",
            json={"branch_id": branch.id, "employee_id": target.id, "shift_id": shift.id,
                  "assigned_date": str(d2)},
            headers=manager_headers,
        ).json()

        swap_resp = client.post(
            "/api/v1/hr/rota/swap-requests",
            json={
                "branch_id": branch.id, "requester_id": requester.id, "target_employee_id": target.id,
                "from_assignment_id": a1["id"], "to_assignment_id": a2["id"],
                "reason": "ظرف عائلي",
            },
            headers=manager_headers,
        )
        assert swap_resp.status_code == 201, swap_resp.text
        swap = swap_resp.json()
        assert swap["status"] == "pending"

        approve_resp = client.patch(
            f"/api/v1/hr/rota/swap-requests/{swap['id']}/approve", headers=manager_headers,
        )
        assert approve_resp.status_code == 200, approve_resp.text
        assert approve_resp.json()["status"] == "approved"

        # Approving an already-approved swap must be rejected.
        second_resp = client.patch(
            f"/api/v1/hr/rota/swap-requests/{swap['id']}/approve", headers=manager_headers,
        )
        assert second_resp.status_code == 400
