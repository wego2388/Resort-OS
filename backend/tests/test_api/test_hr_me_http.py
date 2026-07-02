"""
tests/test_api/test_hr_me_http.py
HTTP-level tests for HR self-service endpoints (/hr/me/*) and the
Employee.user_id link that makes them possible.

Context: Employee (HR module) previously had no way to point back to the
wego_core User a staff member logs in with — so a logged-in waiter/cashier/
whoever had no way to see their own attendance/leave/payslip data. Fixed by
adding Employee.user_id (nullable, unique FK → users.id) plus:
  - PATCH /hr/employees/{id}/link-user   (manager+, links an existing Employee
    to an existing User)
  - GET  /hr/me/profile
  - GET  /hr/me/attendance
  - GET  /hr/me/leaves + POST /hr/me/leaves/request
  - GET  /hr/me/payslips
All /hr/me/* endpoints are get_current_active_user-gated (no role floor) —
self-service works at any role. Each raises a real 404 (not 500, not a
silent empty list) when the current user has no linked Employee at all.

⚠️ hr is always_on=True — no module-enable step needed.
⚠️ Setup data here must be db.commit()-ed, not .flush()-ed (HTTP requests use
a separate DB session via app.dependency_overrides[get_db]).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import _create_test_user, _make_token


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="HR Me Branch", name_ar="فرع سيلف سيرفس",
               code=f"HRME-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_employee_committed(db, branch, **overrides):
    from app.modules.hr.models import Employee
    defaults = dict(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name="سيلف سيرفس موظف", national_id="29001011234567",
        position="Waiter", department="F&B", basic_salary=Decimal("4000.00"),
        hire_date=date.today() - timedelta(days=365),
    )
    defaults.update(overrides)
    emp = Employee(**defaults)
    db.add(emp)
    db.commit()
    return emp


def make_leave_type_committed(db, branch):
    from app.modules.hr.models import LeaveType
    lt = LeaveType(branch_id=branch.id, name="Annual", name_ar="سنوية", max_days_per_year=21)
    db.add(lt)
    db.commit()
    return lt


def make_linked_user_headers(db, role: str = "waiter") -> tuple[int, dict[str, str]]:
    """ينشئ User جديد (بدون ربط بعد) ويرجّع (user_id, headers)."""
    email = f"portal-{uuid.uuid4().hex[:10]}@test.local"
    user_id = _create_test_user(email, role)
    headers = {"Authorization": f"Bearer {_make_token(email)}"}
    return user_id, headers


def link(db, emp, user_id: int):
    emp.user_id = user_id
    db.commit()
    db.refresh(emp)
    return emp


def make_payroll_run_and_line(db, branch, employee, *, status: str, year: int, month: int):
    from app.modules.hr.models import PayrollRun, PayrollLine
    run = PayrollRun(
        branch_id=branch.id, period_year=year, period_month=month, status=status,
        total_gross=Decimal("5000.00"), total_net=Decimal("4300.00"),
        total_tax=Decimal("300.00"), total_si=Decimal("400.00"),
    )
    db.add(run)
    db.flush()
    line = PayrollLine(
        payroll_run_id=run.id, employee_id=employee.id,
        basic_salary=Decimal("5000.00"), gross_salary=Decimal("5000.00"),
        net_salary=Decimal("4300.00"), employee_si=Decimal("400.00"),
        employer_si=Decimal("600.00"), monthly_tax=Decimal("300.00"),
    )
    db.add(line)
    db.commit()
    return run, line


# ── PATCH /hr/employees/{id}/link-user ────────────────────────────────

class TestEmployeeLinkUser:
    def test_manager_links_employee_to_user(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        user_id, _ = make_linked_user_headers(db)

        resp = client.patch(
            f"/api/v1/hr/employees/{emp.id}/link-user",
            json={"user_id": user_id},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["user_id"] == user_id

    def test_link_user_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        user_id, _ = make_linked_user_headers(db)

        resp = client.patch(
            f"/api/v1/hr/employees/{emp.id}/link-user",
            json={"user_id": user_id},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_link_user_404_when_employee_missing(self, client: TestClient, db, manager_headers):
        user_id, _ = make_linked_user_headers(db)
        resp = client.patch(
            "/api/v1/hr/employees/999999/link-user",
            json={"user_id": user_id},
            headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_link_user_400_when_user_missing(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        resp = client.patch(
            f"/api/v1/hr/employees/{emp.id}/link-user",
            json={"user_id": 999999},
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_link_user_400_when_already_linked_to_other_employee(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        emp1 = make_employee_committed(db, branch)
        emp2 = make_employee_committed(db, branch)
        user_id, _ = make_linked_user_headers(db)
        link(db, emp1, user_id)

        resp = client.patch(
            f"/api/v1/hr/employees/{emp2.id}/link-user",
            json={"user_id": user_id},
            headers=manager_headers,
        )
        assert resp.status_code == 400


# ── GET /hr/me/profile ─────────────────────────────────────────────────

class TestMyProfile:
    def test_profile_happy_path(self, client: TestClient, db):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch, full_name="كريم الأمير")
        user_id, headers = make_linked_user_headers(db)
        link(db, emp, user_id)

        resp = client.get("/api/v1/hr/me/profile", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["full_name"] == "كريم الأمير"
        assert body["id"] == emp.id
        assert body["employee_code"] == emp.employee_code
        # موظف بيشوف national_id بتاعه هو نفسه (مش موظف تاني)
        assert body["national_id"] == "29001011234567"

    def test_profile_404_when_no_linked_employee(self, client: TestClient, db, super_admin_headers):
        """super_admin مش بالضرورة موظف حقيقي — لازم 404 واضح مش 500 ولا فاضي."""
        resp = client.get("/api/v1/hr/me/profile", headers=super_admin_headers)
        assert resp.status_code == 404


# ── GET /hr/me/attendance ──────────────────────────────────────────────

class TestMyAttendance:
    def test_attendance_happy_path_and_date_filter(self, client: TestClient, db):
        from app.modules.hr.models import AttendanceRecord

        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        user_id, headers = make_linked_user_headers(db)
        link(db, emp, user_id)

        today = date.today()
        old_day = today - timedelta(days=40)
        db.add_all([
            AttendanceRecord(employee_id=emp.id, branch_id=branch.id, record_date=today, status="present"),
            AttendanceRecord(employee_id=emp.id, branch_id=branch.id, record_date=old_day, status="absent"),
        ])
        db.commit()

        resp = client.get("/api/v1/hr/me/attendance", headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 2

        filtered = client.get(
            "/api/v1/hr/me/attendance",
            params={"date_from": str(today - timedelta(days=1))},
            headers=headers,
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["status"] == "present"

    def test_attendance_never_leaks_other_employees(self, client: TestClient, db):
        from app.modules.hr.models import AttendanceRecord

        branch = make_branch_committed(db)
        me = make_employee_committed(db, branch)
        other = make_employee_committed(db, branch)
        user_id, headers = make_linked_user_headers(db)
        link(db, me, user_id)

        db.add_all([
            AttendanceRecord(employee_id=me.id, branch_id=branch.id, record_date=date.today(), status="present"),
            AttendanceRecord(employee_id=other.id, branch_id=branch.id, record_date=date.today(), status="present"),
        ])
        db.commit()

        resp = client.get("/api/v1/hr/me/attendance", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_attendance_404_when_no_linked_employee(self, client: TestClient, db, super_admin_headers):
        resp = client.get("/api/v1/hr/me/attendance", headers=super_admin_headers)
        assert resp.status_code == 404


# ── GET/POST /hr/me/leaves ──────────────────────────────────────────────

class TestMyLeaves:
    def test_get_my_leaves_excludes_other_employees(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        me = make_employee_committed(db, branch)
        other = make_employee_committed(db, branch)
        leave_type = make_leave_type_committed(db, branch)
        user_id, headers = make_linked_user_headers(db)
        link(db, me, user_id)

        # طلب لموظف تاني عن طريق المسار الإداري
        client.post(
            "/api/v1/hr/leave-requests",
            json={
                "employee_id": other.id, "branch_id": branch.id, "leave_type_id": leave_type.id,
                "start_date": str(date.today() + timedelta(days=1)),
                "end_date": str(date.today() + timedelta(days=2)),
            },
            headers=manager_headers,
        )
        # طلب self-service لنفسي
        mine = client.post(
            "/api/v1/hr/me/leaves/request",
            json={
                "leave_type_id": leave_type.id,
                "start_date": str(date.today() + timedelta(days=5)),
                "end_date": str(date.today() + timedelta(days=6)),
                "reason": "سفر",
            },
            headers=headers,
        )
        assert mine.status_code == 201, mine.text

        resp = client.get("/api/v1/hr/me/leaves", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["employee_id"] == me.id
        assert body["items"][0]["status"] == "pending"

    def test_request_my_leave_derives_employee_from_current_user(self, client: TestClient, db):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        leave_type = make_leave_type_committed(db, branch)
        user_id, headers = make_linked_user_headers(db)
        link(db, emp, user_id)

        resp = client.post(
            "/api/v1/hr/me/leaves/request",
            json={
                "leave_type_id": leave_type.id,
                "start_date": str(date.today() + timedelta(days=10)),
                "end_date": str(date.today() + timedelta(days=12)),
                "reason": "إجازة شخصية",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["employee_id"] == emp.id
        assert body["branch_id"] == branch.id
        assert body["days_requested"] == 3

    def test_request_my_leave_404_when_no_linked_employee(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        leave_type = make_leave_type_committed(db, branch)
        resp = client.post(
            "/api/v1/hr/me/leaves/request",
            json={
                "leave_type_id": leave_type.id,
                "start_date": str(date.today() + timedelta(days=1)),
                "end_date": str(date.today() + timedelta(days=2)),
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 404

    def test_get_my_leaves_404_when_no_linked_employee(self, client: TestClient, db, super_admin_headers):
        resp = client.get("/api/v1/hr/me/leaves", headers=super_admin_headers)
        assert resp.status_code == 404

    def test_leave_types_accessible_to_any_active_user(self, client: TestClient, db, waiter_headers):
        """Regression: self-service leave request needs to pick a leave_type_id
        from a dropdown — GET /hr/leave-types must not be manager-only anymore."""
        branch = make_branch_committed(db)
        make_leave_type_committed(db, branch)
        resp = client.get(
            "/api/v1/hr/leave-types", params={"branch_id": branch.id}, headers=waiter_headers,
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) >= 1


# ── GET /hr/me/payslips ─────────────────────────────────────────────────

class TestMyPayslips:
    def test_payslips_returns_only_non_draft_runs(self, client: TestClient, db):
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch)
        user_id, headers = make_linked_user_headers(db)
        link(db, emp, user_id)

        make_payroll_run_and_line(db, branch, emp, status="draft", year=2026, month=1)
        make_payroll_run_and_line(db, branch, emp, status="approved", year=2026, month=2)

        resp = client.get("/api/v1/hr/me/payslips", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["period_month"] == 2
        assert body["items"][0]["status"] == "approved"
        assert Decimal(str(body["items"][0]["net_salary"])) == Decimal("4300.00")

    def test_payslips_never_leaks_other_employees(self, client: TestClient, db):
        branch = make_branch_committed(db)
        me = make_employee_committed(db, branch)
        other = make_employee_committed(db, branch)
        user_id, headers = make_linked_user_headers(db)
        link(db, me, user_id)

        make_payroll_run_and_line(db, branch, other, status="approved", year=2026, month=3)

        resp = client.get("/api/v1/hr/me/payslips", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_payslips_404_when_no_linked_employee(self, client: TestClient, db, super_admin_headers):
        resp = client.get("/api/v1/hr/me/payslips", headers=super_admin_headers)
        assert resp.status_code == 404
