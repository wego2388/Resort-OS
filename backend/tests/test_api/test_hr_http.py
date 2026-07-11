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


def ensure_payroll_config_committed(db):
    """SocialInsuranceConfig/TaxBracketConfig مش scoped بفرع — global. Idempotent
    (بيتحقق إذا موجود قبل ما يضيف) عشان يشتغل صح مهما كان ترتيب التستات في
    الـ session-scoped DB (كل التستات هنا بتشارك نفس SQLite in-memory)."""
    from app.modules.hr.models import SocialInsuranceConfig, TaxBracketConfig
    if not db.query(SocialInsuranceConfig).filter(SocialInsuranceConfig.is_active.is_(True)).first():
        db.add(SocialInsuranceConfig(
            max_insurable_salary=Decimal("9400.00"), employee_rate=Decimal("0.1100"),
            employer_rate=Decimal("0.1800"), personal_exemption_annual=Decimal("15000.00"),
            max_penalty_days_monthly=5, effective_from=date(2024, 1, 1), is_active=True,
        ))
    if not db.query(TaxBracketConfig).filter(TaxBracketConfig.is_active.is_(True)).first():
        db.add_all([
            TaxBracketConfig(lower_bound=Decimal("0"), upper_bound=Decimal("15000"),
                              rate=Decimal("0.0000"), effective_from=date(2024, 1, 1), is_active=True),
            TaxBracketConfig(lower_bound=Decimal("15000"), upper_bound=Decimal("30000"),
                              rate=Decimal("0.1000"), effective_from=date(2024, 1, 1), is_active=True),
            TaxBracketConfig(lower_bound=Decimal("30000"), upper_bound=None,
                              rate=Decimal("0.2250"), effective_from=date(2024, 1, 1), is_active=True),
        ])
    db.commit()


def make_linked_user_headers(db, role: str = "waiter") -> tuple[int, dict[str, str]]:
    from tests.conftest import _create_test_user, _make_token
    email = f"hr-http-{uuid.uuid4().hex[:10]}@test.local"
    user_id = _create_test_user(email, role)
    headers = {"Authorization": f"Bearer {_make_token(email)}"}
    return user_id, headers


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

    def test_approve_swap_request_404_when_missing(self, client: TestClient, db, manager_headers):
        resp = client.patch(
            "/api/v1/hr/rota/swap-requests/999999/approve", headers=manager_headers,
        )
        assert resp.status_code == 404


class TestEmployeeCrudHttp:
    """GET/POST/PATCH /hr/employees — إنشاء/عرض/تعديل حقيقي عبر HTTP، مش
    service calls مباشرة (هذا موجود في test_hr.py). كانت كل هذه المسارات
    بدون أي تغطية HTTP فعلياً رغم وجودها في الراوتر."""

    def test_list_employees_returns_created_employee(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        resp = client.get(
            "/api/v1/hr/employees", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == emp.id
        assert body["items"][0]["full_name"] == emp.full_name

    def test_create_employee_success(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/hr/employees",
            json={
                "branch_id": branch.id, "employee_code": f"EMP-{uuid.uuid4().hex[:6].upper()}",
                "full_name": "سارة محمود", "position": "Receptionist",
                "basic_salary": "3500.00", "hire_date": str(date.today()),
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["full_name"] == "سارة محمود"
        assert body["status"] == "active"
        assert Decimal(str(body["basic_salary"])) == Decimal("3500.00")

    def test_create_employee_duplicate_code_returns_400(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        resp = client.post(
            "/api/v1/hr/employees",
            json={
                "branch_id": branch.id, "employee_code": emp.employee_code,
                "full_name": "نسخة مكررة", "position": "Waiter",
                "basic_salary": "3000.00", "hire_date": str(date.today()),
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 400
        assert "مستخدم مسبقاً" in resp.text

    def test_get_employee_by_id_success(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        resp = client.get(f"/api/v1/hr/employees/{emp.id}", headers=waiter_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == emp.id

    def test_get_employee_404(self, client: TestClient, db, waiter_headers):
        resp = client.get("/api/v1/hr/employees/999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_update_employee_success(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        resp = client.patch(
            f"/api/v1/hr/employees/{emp.id}",
            json={"position": "Head Waiter", "basic_salary": "4500.00"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["position"] == "Head Waiter"
        assert Decimal(str(body["basic_salary"])) == Decimal("4500.00")

    def test_update_employee_404(self, client: TestClient, db, super_admin_headers):
        resp = client.patch(
            "/api/v1/hr/employees/999999",
            json={"position": "Ghost"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 404


class TestPayslipCalculationHttp:
    """GET /hr/employees/{id}/payslip — حساب راتب فوري (مش من كشف محفوظ)."""

    def test_get_payslip_success(self, client: TestClient, db, manager_headers):
        ensure_payroll_config_committed(db)
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        resp = client.get(
            f"/api/v1/hr/employees/{emp.id}/payslip",
            params={"period_year": 2026, "period_month": 6},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["employee_id"] == emp.id
        assert Decimal(str(body["gross_salary"])) >= Decimal(str(body["basic_salary"]))
        assert Decimal(str(body["net_salary"])) < Decimal(str(body["gross_salary"]))

    def test_get_payslip_404_when_employee_missing(self, client: TestClient, db, manager_headers):
        resp = client.get(
            "/api/v1/hr/employees/999999/payslip",
            params={"period_year": 2026, "period_month": 6},
            headers=manager_headers,
        )
        assert resp.status_code == 400  # ValueError من calculate_employee_payroll يترجم 400


class TestLeaderboardHttp:
    def test_leaderboard_endpoint_returns_200(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        today = date.today()
        resp = client.get(
            "/api/v1/hr/leaderboard",
            params={
                "branch_id": branch.id,
                "date_from": str(today - timedelta(days=1)),
                "date_to": str(today + timedelta(days=1)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == []


class TestPayrollRunHttp:
    def test_create_payroll_run_duplicate_returns_400(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        make_employee_committed(db, branch)
        today = date.today()
        first = client.post(
            "/api/v1/hr/payroll-runs",
            json={"branch_id": branch.id, "period_year": today.year, "period_month": today.month},
            headers=super_admin_headers,
        )
        assert first.status_code == 201, first.text
        second = client.post(
            "/api/v1/hr/payroll-runs",
            json={"branch_id": branch.id, "period_year": today.year, "period_month": today.month},
            headers=super_admin_headers,
        )
        assert second.status_code == 400
        assert "موجود مسبقاً" in second.text

    def test_get_payroll_run_success_and_lines(self, client: TestClient, db, super_admin_headers, manager_headers):
        ensure_payroll_config_committed(db)
        branch = make_branch_committed(db)
        make_employee_committed(db, branch)
        today = date.today()
        run = client.post(
            "/api/v1/hr/payroll-runs",
            json={"branch_id": branch.id, "period_year": today.year, "period_month": today.month},
            headers=super_admin_headers,
        ).json()

        get_resp = client.get(f"/api/v1/hr/payroll-runs/{run['id']}", headers=manager_headers)
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["id"] == run["id"]

        lines_resp = client.get(f"/api/v1/hr/payroll-runs/{run['id']}/lines", headers=manager_headers)
        assert lines_resp.status_code == 200, lines_resp.text
        assert len(lines_resp.json()) == 1  # موظف واحد فقط في الفرع

    def test_get_payroll_run_404(self, client: TestClient, db, manager_headers):
        resp = client.get("/api/v1/hr/payroll-runs/999999", headers=manager_headers)
        assert resp.status_code == 404

    def test_approve_payroll_run_404_when_missing(self, client: TestClient, db, super_admin_headers):
        resp = client.post("/api/v1/hr/payroll-runs/999999/approve", headers=super_admin_headers)
        assert resp.status_code == 400  # ValueError "غير موجود" -> 400 (مش 404 — راجع الراوتر)


class TestAttendanceHttp:
    def test_record_and_list_attendance(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        create_resp = client.post(
            "/api/v1/hr/attendance",
            json={
                "employee_id": emp.id, "branch_id": branch.id,
                "record_date": str(date.today()), "status": "present",
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        list_resp = client.get(
            "/api/v1/hr/attendance",
            params={"employee_id": emp.id, "branch_id": branch.id},
            headers=manager_headers,
        )
        assert list_resp.status_code == 200, list_resp.text
        assert list_resp.json()["total"] == 1

    def test_manager_can_correct_missing_checkout(self, client: TestClient, db, manager_headers):
        """wagdy.md #8: موظف نسي يبصم انصراف — مدير يصحّح السجل يدويًا."""
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        create_resp = client.post(
            "/api/v1/hr/attendance",
            json={
                "employee_id": emp.id, "branch_id": branch.id,
                "record_date": str(date.today()), "status": "present",
                "check_in": "2026-07-09T09:00:00",
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        record_id = create_resp.json()["id"]
        assert create_resp.json()["check_out"] is None

        patch_resp = client.patch(
            f"/api/v1/hr/attendance/{record_id}",
            json={"check_out": "2026-07-09T17:00:00", "notes": "نسي يبصم انصراف — صححها المدير"},
            headers=manager_headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text
        body = patch_resp.json()
        assert body["check_out"] == "2026-07-09T17:00:00"
        assert body["notes"] == "نسي يبصم انصراف — صححها المدير"
        assert body["check_in"] == "2026-07-09T09:00:00"  # لسه زي ما هو، منعدلوش

    def test_update_missing_attendance_404(self, client: TestClient, manager_headers):
        resp = client.patch(
            "/api/v1/hr/attendance/999999999", json={"status": "absent"}, headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_update_attendance_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        resp = client.patch(
            f"/api/v1/hr/attendance/{emp.id}", json={"status": "absent"}, headers=waiter_headers,
        )
        assert resp.status_code == 403


class TestDepartmentHttp:
    def test_create_and_list_departments(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/hr/departments",
            json={"branch_id": branch.id, "name": "Kitchen", "name_ar": "مطبخ"},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        list_resp = client.get(
            "/api/v1/hr/departments", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200, list_resp.text
        assert any(d["name"] == "Kitchen" for d in list_resp.json())


class TestShiftHttp:
    def test_create_and_list_shifts(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/hr/shifts",
            json={
                "branch_id": branch.id, "name": "Evening", "name_ar": "مسائي",
                "start_time": "16:00", "end_time": "23:00", "duration_hours": "7.00",
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        list_resp = client.get(
            "/api/v1/hr/shifts", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200, list_resp.text
        assert any(s["name"] == "Evening" for s in list_resp.json())


class TestRotaTemplateHttp:
    """Regression coverage — RotaTemplate model existed in full but had zero
    schema/crud/router, same bug class as Lead/Campaign/CallNote."""

    def _make_department(self, client, branch, headers):
        return client.post(
            "/api/v1/hr/departments",
            json={"branch_id": branch.id, "name": "Front Office", "name_ar": "الاستقبال"},
            headers=headers,
        ).json()

    def test_create_list_get_and_update_rota_template(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        dept = self._make_department(client, branch, manager_headers)

        create_resp = client.post(
            "/api/v1/hr/rota/templates",
            json={
                "branch_id": branch.id, "department_id": dept["id"],
                "name": "جدول الصيف", "week_pattern": {"mon": {"morning": 3}, "tue": {"evening": 2}},
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        template = create_resp.json()
        assert template["is_active"] is True
        assert template["week_pattern"]["mon"]["morning"] == 3

        list_resp = client.get(
            "/api/v1/hr/rota/templates", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        ids = [t["id"] for t in list_resp.json()]
        assert template["id"] in ids

        filtered_resp = client.get(
            "/api/v1/hr/rota/templates",
            params={"branch_id": branch.id, "department_id": dept["id"], "is_active": True},
            headers=manager_headers,
        )
        assert filtered_resp.status_code == 200
        assert template["id"] in [t["id"] for t in filtered_resp.json()]

        get_resp = client.get(f"/api/v1/hr/rota/templates/{template['id']}", headers=manager_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "جدول الصيف"

        update_resp = client.patch(
            f"/api/v1/hr/rota/templates/{template['id']}",
            json={"week_pattern": {"wed": {"morning": 4}}, "is_active": False},
            headers=manager_headers,
        )
        assert update_resp.status_code == 200, update_resp.text
        updated = update_resp.json()
        assert updated["is_active"] is False
        assert updated["week_pattern"] == {"wed": {"morning": 4}}

    def test_get_unknown_rota_template_404(self, client: TestClient, db, manager_headers):
        resp = client.get("/api/v1/hr/rota/templates/999999", headers=manager_headers)
        assert resp.status_code == 404

    def test_update_unknown_rota_template_404(self, client: TestClient, db, manager_headers):
        resp = client.patch(
            "/api/v1/hr/rota/templates/999999", json={"is_active": False}, headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_waiter_cannot_create_rota_template(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/hr/rota/templates",
            json={"branch_id": branch.id, "department_id": 1, "name": "x", "week_pattern": {}},
            headers=waiter_headers,
        )
        assert resp.status_code == 403


class TestLeaveTypeHttp:
    def test_create_leave_type(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/hr/leave-types",
            json={"branch_id": branch.id, "name": "Sick", "name_ar": "مرضية", "max_days_per_year": 15},
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["name"] == "Sick"


class TestLeaveRequestValidationAndRejectHttp:
    def test_create_leave_request_invalid_dates_returns_400(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        employee = make_employee_committed(db, branch)
        leave_type = make_leave_type_committed(db, branch)
        resp = client.post(
            "/api/v1/hr/leave-requests",
            json={
                "employee_id": employee.id, "branch_id": branch.id, "leave_type_id": leave_type.id,
                "start_date": str(date.today() + timedelta(days=5)),
                "end_date": str(date.today() + timedelta(days=1)),  # نهاية قبل البداية
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_approve_leave_request_already_processed_returns_400(self, client: TestClient, db, manager_headers):
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
        client.patch(
            f"/api/v1/hr/leave-requests/{req['id']}/approve", json={"approved_by": 1}, headers=manager_headers,
        )
        second = client.patch(
            f"/api/v1/hr/leave-requests/{req['id']}/approve", json={"approved_by": 1}, headers=manager_headers,
        )
        assert second.status_code == 400

    def test_reject_leave_request_via_dedicated_endpoint(self, client: TestClient, db, manager_headers):
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
        resp = client.patch(
            f"/api/v1/hr/leave-requests/{req['id']}/reject",
            json={"reason": "لا يوجد بديل متاح"},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "rejected"
        assert resp.json()["rejection_reason"] == "لا يوجد بديل متاح"

        # رفض طلب اتعالج فعلاً (rejected) تاني — لازم 400 مش 500
        second = client.patch(
            f"/api/v1/hr/leave-requests/{req['id']}/reject",
            json={"reason": "محاولة تانية"},
            headers=manager_headers,
        )
        assert second.status_code == 400

    def test_leaves_alias_patch_404_underlying_value_error_returns_400(
        self, client: TestClient, db, manager_headers,
    ):
        """PATCH /hr/leaves/{id} على request_id غير موجود — الـ ValueError من
        services.approve_leave/reject_leave لازم يترجم 400 (مش 500)."""
        resp = client.patch(
            "/api/v1/hr/leaves/999999", json={"status": "approved"}, headers=manager_headers,
        )
        assert resp.status_code == 400


class TestSelfServiceAttendanceHttp:
    """POST /hr/me/attendance/punch-in|punch-out — نفس المنطق المُختبر عند
    مستوى الـ service في test_hr.py، لكن هنا عبر الراوتر الحقيقي (auth chain
    + response model + error translation)."""

    def test_punch_in_then_punch_out_flow(self, client: TestClient, db):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        user_id, headers = make_linked_user_headers(db)
        emp.user_id = user_id
        db.commit()

        in_resp = client.post("/api/v1/hr/me/attendance/punch-in", headers=headers)
        assert in_resp.status_code == 201, in_resp.text
        assert in_resp.json()["check_in"] is not None
        assert in_resp.json()["check_out"] is None

        out_resp = client.post("/api/v1/hr/me/attendance/punch-out", headers=headers)
        assert out_resp.status_code == 200, out_resp.text
        assert out_resp.json()["check_out"] is not None

    def test_punch_in_twice_returns_400(self, client: TestClient, db):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        user_id, headers = make_linked_user_headers(db)
        emp.user_id = user_id
        db.commit()

        client.post("/api/v1/hr/me/attendance/punch-in", headers=headers)
        second = client.post("/api/v1/hr/me/attendance/punch-in", headers=headers)
        assert second.status_code == 400

    def test_punch_out_without_punch_in_returns_400(self, client: TestClient, db):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        user_id, headers = make_linked_user_headers(db)
        emp.user_id = user_id
        db.commit()

        resp = client.post("/api/v1/hr/me/attendance/punch-out", headers=headers)
        assert resp.status_code == 400


class TestPenaltyHttp:
    def test_create_and_list_penalties(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        create_resp = client.post(
            "/api/v1/hr/penalties",
            json={
                "employee_id": emp.id, "branch_id": branch.id,
                "penalty_date": str(date.today()), "penalty_days": 1,
                "reason": "تأخير متكرر", "applied_by": 1,
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        list_resp = client.get(
            "/api/v1/hr/penalties", params={"branch_id": branch.id, "employee_id": emp.id},
            headers=manager_headers,
        )
        assert list_resp.status_code == 200, list_resp.text
        assert len(list_resp.json()) == 1
        assert list_resp.json()[0]["reason"] == "تأخير متكرر"


class TestEmployeeAllowanceHttp:
    """Regression: EmployeeAllowance model + crud.list_allowances_for_employee
    كانا موجودين بالكامل (وبيدخلوا فعليًا في حساب الراتب — services.
    calculate_employee_payroll) من غير أي طريقة لإضافة بدل عن طريق الـ API.
    نفس فئة الباج (Lead/Campaign/TenantCashLog/CallNote/RotaTemplate)."""

    def test_create_list_and_update_allowance(self, client: TestClient, db, super_admin_headers, manager_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)

        create_resp = client.post(
            f"/api/v1/hr/employees/{emp.id}/allowances",
            json={"employee_id": emp.id, "name": "بدل سكن", "amount": "500.00",
                  "is_taxable": True, "is_pensionable": False},
            headers=super_admin_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        allowance_id = create_resp.json()["id"]
        assert create_resp.json()["is_active"] is True

        list_resp = client.get(
            f"/api/v1/hr/employees/{emp.id}/allowances", headers=manager_headers,
        )
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1
        assert list_resp.json()[0]["name"] == "بدل سكن"

        update_resp = client.patch(
            f"/api/v1/hr/allowances/{allowance_id}",
            json={"amount": "600.00", "is_active": False},
            headers=super_admin_headers,
        )
        assert update_resp.status_code == 200, update_resp.text
        assert update_resp.json()["is_active"] is False
        assert Decimal(str(update_resp.json()["amount"])) == Decimal("600.00")

        # active_only=True (default) لازم يستبعد البدل بعد التعطيل
        list_active_resp = client.get(
            f"/api/v1/hr/employees/{emp.id}/allowances", headers=manager_headers,
        )
        assert list_active_resp.json() == []

    def test_create_allowance_employee_id_mismatch_400(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        resp = client.post(
            f"/api/v1/hr/employees/{emp.id}/allowances",
            json={"employee_id": emp.id + 999, "name": "بدل", "amount": "100.00"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 400

    def test_create_allowance_requires_admin(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        resp = client.post(
            f"/api/v1/hr/employees/{emp.id}/allowances",
            json={"employee_id": emp.id, "name": "بدل", "amount": "100.00"},
            headers=manager_headers,
        )
        assert resp.status_code == 403

    def test_allowance_feeds_into_payroll_calculation(
        self, client: TestClient, db, super_admin_headers, manager_headers,
    ):
        """بدل حقيقي مضاف عن طريق الـ endpoint الجديد لازم يظهر فعليًا في
        gross_salary وقت حساب الراتب — مش بس يتخزن."""
        ensure_payroll_config_committed(db)
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        client.post(
            f"/api/v1/hr/employees/{emp.id}/allowances",
            json={"employee_id": emp.id, "name": "بدل انتقالات", "amount": "300.00",
                  "is_taxable": True, "is_pensionable": False},
            headers=super_admin_headers,
        )
        today = date.today()
        resp = client.get(
            f"/api/v1/hr/employees/{emp.id}/payslip",
            params={"period_year": today.year, "period_month": today.month},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert Decimal(str(body["taxable_allowances"])) == Decimal("300.00")
        assert Decimal(str(body["gross_salary"])) == emp.basic_salary + Decimal("300.00")


class TestPenaltyTypeHttp:
    """Regression: PenaltyTypeCreate/Read schemas كانا موجودين من غير أي
    crud/router — نفس فئة الباج الموثّقة مرارًا في هذا المشروع."""

    def test_create_and_list_penalty_types(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/hr/penalty-types",
            json={"branch_id": branch.id, "name": "تأخير", "name_ar": "تأخير", "penalty_days": 1},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        # أي مستخدم مسجّل دخول يقدر يشوف القائمة (بيانات مرجعية للاختيار عند
        # تسجيل جزاء لموظف)، مش بس manager+.
        list_resp = client.get(
            "/api/v1/hr/penalty-types", params={"branch_id": branch.id}, headers=waiter_headers,
        )
        assert list_resp.status_code == 200, list_resp.text
        assert len(list_resp.json()) == 1
        assert list_resp.json()[0]["name_ar"] == "تأخير"

    def test_create_penalty_type_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/hr/penalty-types",
            json={"branch_id": branch.id, "name": "غياب", "penalty_days": 2},
            headers=waiter_headers,
        )
        assert resp.status_code == 403


class TestPayrollConfigHttp:
    """Regression: SocialInsuranceConfig/TaxBracketConfig models were fully
    read (hr_engine, via crud.get_active_si_config/get_active_tax_brackets)
    but had zero schema/router — the only way to add a new version when the
    law changes (e.g. annual tax bracket update) was a direct DB insert (like
    seed.py does). admin-only since it affects every employee's payroll."""

    def test_create_and_list_social_insurance_config(self, client: TestClient, db, super_admin_headers, manager_headers):
        resp = client.post(
            "/api/v1/hr/config/social-insurance",
            json={
                "max_insurable_salary": "12000.00", "employee_rate": "0.11",
                "employer_rate": "0.1875", "personal_exemption_annual": "20000.00",
                "effective_from": "2027-01-01",
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["max_insurable_salary"] == "12000.00"

        list_resp = client.get("/api/v1/hr/config/social-insurance", headers=super_admin_headers)
        assert list_resp.status_code == 200
        assert any(c["effective_from"] == "2027-01-01" for c in list_resp.json())

        # manager (level 60) لا يكفي — الإعداد ده admin-only (80+)
        forbidden = client.post(
            "/api/v1/hr/config/social-insurance",
            json={
                "max_insurable_salary": "12000.00", "employee_rate": "0.11",
                "employer_rate": "0.1875", "personal_exemption_annual": "20000.00",
                "effective_from": "2028-01-01",
            },
            headers=manager_headers,
        )
        assert forbidden.status_code == 403

    def test_create_and_list_tax_bracket_config(self, client: TestClient, db, super_admin_headers):
        resp = client.post(
            "/api/v1/hr/config/tax-brackets",
            json={"lower_bound": "0", "upper_bound": "40000", "rate": "0", "effective_from": "2027-01-01"},
            headers=super_admin_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["rate"] == "0.0000" or float(resp.json()["rate"]) == 0.0

        list_resp = client.get("/api/v1/hr/config/tax-brackets", headers=super_admin_headers)
        assert list_resp.status_code == 200
        assert any(b["effective_from"] == "2027-01-01" for b in list_resp.json())


class TestPayrollDownloadsHttp:
    """GET /hr/payroll/{run_id}/payslip/{employee_id} و
    GET /hr/payroll/{run_id}/excel — تحميلات PDF/Excel حقيقية، لازم نتأكد من
    content-type وحجم بايتات غير تافه (مش استجابة فاضية)."""

    def _make_approved_run(self, client, db, super_admin_headers):
        ensure_payroll_config_committed(db)
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        today = date.today()
        run = client.post(
            "/api/v1/hr/payroll-runs",
            json={"branch_id": branch.id, "period_year": today.year, "period_month": today.month},
            headers=super_admin_headers,
        ).json()
        return branch, emp, run

    def test_download_payslip_pdf_success(self, client: TestClient, db, super_admin_headers, manager_headers):
        _, emp, run = self._make_approved_run(client, db, super_admin_headers)
        resp = client.get(
            f"/api/v1/hr/payroll/{run['id']}/payslip/{emp.id}", headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"
        assert len(resp.content) > 500  # PDF حقيقي، مش استجابة فاضية

    def test_download_payslip_pdf_404_run_missing(self, client: TestClient, db, manager_headers):
        resp = client.get("/api/v1/hr/payroll/999999/payslip/1", headers=manager_headers)
        assert resp.status_code == 404

    def test_download_payslip_pdf_404_employee_not_in_run(
        self, client: TestClient, db, super_admin_headers, manager_headers,
    ):
        _, _, run = self._make_approved_run(client, db, super_admin_headers)
        resp = client.get(
            f"/api/v1/hr/payroll/{run['id']}/payslip/999999", headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_download_payroll_excel_success(self, client: TestClient, db, super_admin_headers, manager_headers):
        _, _, run = self._make_approved_run(client, db, super_admin_headers)
        resp = client.get(f"/api/v1/hr/payroll/{run['id']}/excel", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert len(resp.content) > 500

    def test_download_payroll_excel_404_run_missing(self, client: TestClient, db, manager_headers):
        resp = client.get("/api/v1/hr/payroll/999999/excel", headers=manager_headers)
        assert resp.status_code == 404


class TestAttendancePolicyEndpoints:
    """GET/PUT /hr/attendance-policy — إعدادات الحضور القابلة للتحكم من
    الإدارة (سماحية تأخير/انصراف مبكر، وردية افتراضية، نسب أوفرتايم/خصم)،
    اللي بتغذّي الحساب التلقائي في run_payroll_for_branch."""

    def test_get_404_when_not_configured(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get("/api/v1/hr/attendance-policy", params={"branch_id": branch.id}, headers=manager_headers)
        assert resp.status_code == 404

    def test_put_creates_then_get_returns_it(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        body = {
            "late_grace_minutes": 15,
            "early_leave_grace_minutes": 5,
            "standard_shift_start": "08:00",
            "standard_shift_end": "16:00",
            "overtime_rate_multiplier": "2.00",
            "late_penalty_rate_multiplier": "1.25",
            "is_active": True,
        }
        put_resp = client.put(
            "/api/v1/hr/attendance-policy", params={"branch_id": branch.id}, json=body, headers=manager_headers,
        )
        assert put_resp.status_code == 200, put_resp.text
        data = put_resp.json()
        assert data["late_grace_minutes"] == 15
        assert data["standard_shift_start"] == "08:00"
        assert Decimal(str(data["overtime_rate_multiplier"])) == Decimal("2.00")

        get_resp = client.get("/api/v1/hr/attendance-policy", params={"branch_id": branch.id}, headers=manager_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["late_grace_minutes"] == 15

    def test_put_is_idempotent_upsert_not_duplicate(self, client: TestClient, db, manager_headers):
        """نداء PUT مرتين لنفس الفرع لازم يحدّث نفس الصف، مش ينشئ صف تاني."""
        from app.modules.hr.models import AttendancePolicy

        branch = make_branch_committed(db)
        body = {"late_grace_minutes": 10, "standard_shift_start": "09:00", "standard_shift_end": "17:00"}
        client.put("/api/v1/hr/attendance-policy", params={"branch_id": branch.id}, json=body, headers=manager_headers)
        body["late_grace_minutes"] = 20
        client.put("/api/v1/hr/attendance-policy", params={"branch_id": branch.id}, json=body, headers=manager_headers)

        rows = db.query(AttendancePolicy).filter(AttendancePolicy.branch_id == branch.id).all()
        assert len(rows) == 1
        assert rows[0].late_grace_minutes == 20

    def test_get_requires_manager_role(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.get("/api/v1/hr/attendance-policy", params={"branch_id": branch.id}, headers=waiter_headers)
        assert resp.status_code == 403
