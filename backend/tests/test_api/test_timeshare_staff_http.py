from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient


def test_timeshare_admin_provisions_only_an_existing_hr_employee(
    client: TestClient,
    db,
):
    from app.core.kernel.models.user import User
    from app.modules.core.models import Branch, UserBranchMembership
    from app.modules.hr.models import Employee
    from tests.conftest import _fresh_super_admin

    branch = Branch(
        name="Timeshare Staff Branch",
        code=f"TSS-{uuid.uuid4().hex[:8].upper()}",
        is_active=True,
    )
    db.add(branch)
    db.commit()
    employee = Employee(
        branch_id=branch.id,
        employee_code=f"TSE-{uuid.uuid4().hex[:8].upper()}",
        full_name="موظف خدمة ملاك",
        position="Owner Services Agent",
        email=f"owner-services-{uuid.uuid4().hex}@test.local",
        phone="+201011111111",
        basic_salary=Decimal("6000"),
        hire_date=date.today(),
    )
    db.add(employee)
    db.commit()
    _, headers, _ = _fresh_super_admin(
        "timeshare-staff-http", branch_id=branch.id,
    )

    eligible = client.get(
        "/api/v1/timeshare/staff/eligible-employees",
        params={"branch_id": branch.id},
        headers=headers,
    )
    assert eligible.status_code == 200, eligible.text
    assert [item["id"] for item in eligible.json()] == [employee.id]

    response = client.post(
        "/api/v1/timeshare/staff",
        json={
            "branch_id": branch.id,
            "employee_id": employee.id,
            "email": employee.email,
            "full_name": employee.full_name,
            "phone": employee.phone,
            "preferred_language": "ar",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["employee_id"] == employee.id
    assert len(body["temporary_password"]) >= 16

    db.expire_all()
    created = db.get(User, body["id"])
    assert created.role == "timeshare_agent"
    assert db.get(Employee, employee.id).user_id == created.id
    membership = db.query(UserBranchMembership).filter_by(
        user_id=created.id,
        branch_id=branch.id,
    ).one()
    assert membership.is_active is True

    from app.modules.core.services import get_effective_permissions

    permissions = {
        f"{item.resource}:{item.action}": item.allowed
        for item in get_effective_permissions(db, created, branch_id=branch.id)
    }
    assert permissions["timeshare.visits:create"] is True
    assert permissions["timeshare.waitlist:create"] is True
    assert permissions["timeshare.support_tickets:respond"] is True
    assert permissions["timeshare.installments:collect"] is False
    assert permissions["timeshare.maintenance_dues:collect"] is False

    eligible_after = client.get(
        "/api/v1/timeshare/staff/eligible-employees",
        params={"branch_id": branch.id},
        headers=headers,
    )
    assert eligible_after.status_code == 200
    assert eligible_after.json() == []
