"""
tests/test_engines/test_encryption.py
EncryptedString TypeDecorator — encrypted at rest, transparent in Python.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import sqlalchemy as sa

from app.modules.hr.models import Employee


class TestEncryptedString:
    def test_national_id_encrypted_at_rest(self, db, sample_branch):
        employee = Employee(
            branch_id=sample_branch.id,
            employee_code="EMP-ENC-001",
            full_name="Test Employee",
            national_id="29001011234567",
            position="Tester",
            basic_salary=Decimal("1000"),
            hire_date=date.today(),
        )
        db.add(employee)
        db.flush()

        # Python-side: transparently decrypted
        assert employee.national_id == "29001011234567"

        # raw DB value must NOT be the plaintext national_id
        raw = db.execute(
            sa.text("SELECT national_id FROM employees WHERE id = :id"),
            {"id": employee.id},
        ).scalar()
        assert raw != "29001011234567"
        assert raw is not None

    def test_national_id_none_passthrough(self, db, sample_branch):
        employee = Employee(
            branch_id=sample_branch.id,
            employee_code="EMP-ENC-002",
            full_name="No National ID",
            national_id=None,
            position="Tester",
            basic_salary=Decimal("1000"),
            hire_date=date.today(),
        )
        db.add(employee)
        db.flush()
        assert employee.national_id is None

    def test_round_trip_after_reload(self, db, sample_branch):
        employee = Employee(
            branch_id=sample_branch.id,
            employee_code="EMP-ENC-003",
            full_name="Reload Test",
            national_id="30005051234567",
            position="Tester",
            basic_salary=Decimal("1000"),
            hire_date=date.today(),
        )
        db.add(employee)
        db.flush()
        emp_id = employee.id
        db.expire_all()

        reloaded = db.query(Employee).filter(Employee.id == emp_id).first()
        assert reloaded.national_id == "30005051234567"
