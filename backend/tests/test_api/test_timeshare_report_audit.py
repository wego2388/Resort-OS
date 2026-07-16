"""
tests/test_api/test_timeshare_report_audit.py
اختبارات لـ:
- GET /timeshare/installments/monthly-report — تقرير التحصيل الشهري
- AuditLog عند تحصيل قسط (services.pay_installment)
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


# ── helpers ─────────────────────────────────────────────────────────────────

def _make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"Rpt-Branch-{uuid.uuid4().hex[:6]}",
        code=f"RP{uuid.uuid4().hex[:4].upper()}",
    )
    db.add(b)
    db.commit()
    return b


def _make_manager(db):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    u = User(
        email=f"mgr_{uuid.uuid4().hex[:6]}@rpt.test",
        password_hash=get_password_hash("Test@12345"),
        full_name="Report Manager",
        role="manager",
        is_active=True,
    )
    db.add(u)
    db.commit()
    return u


def _make_cashier(db):
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    u = User(
        email=f"cash_{uuid.uuid4().hex[:6]}@rpt.test",
        password_hash=get_password_hash("Test@12345"),
        full_name="Cashier",
        role="cashier",
        is_active=True,
    )
    db.add(u)
    db.commit()
    return u


def _make_contract(db, branch_id, manager_id):
    from app.modules.timeshare import crud as ts_crud
    from app.modules.timeshare.schemas import TimeshareContractCreate
    today = date.today()
    data = TimeshareContractCreate(
        branch_id=branch_id,
        customer_name=f"عميل-{uuid.uuid4().hex[:4]}",
        customer_phone=f"010{uuid.uuid4().int % 100000000:08d}",
        room_type="2R",
        total_value=Decimal("60000"),
        down_payment=Decimal("10000"),
        installments=6,
        installment_period=1,
        first_installment_date=today + timedelta(days=30),
        start_date=today,
        season="high",
        week_number=20,
    )
    c = ts_crud.create_contract(db, data, signed_by=manager_id)
    db.commit()
    return c


def _make_installment(db, contract_id, due_date, amount=Decimal("5000"), status="pending"):
    from app.modules.timeshare.models import TimeshareInstallment
    inst = TimeshareInstallment(
        contract_id=contract_id,
        installment_no=99,
        due_date=due_date,
        amount=amount,
        status=status,
    )
    db.add(inst)
    db.commit()
    return inst


# ── GET /timeshare/installments/monthly-report ────────────────────────────

class TestMonthlyCollectionReport:
    """اختبارات تقرير التحصيل الشهري."""

    def test_returns_excel_content_type(self, client: TestClient, db, fake_redis, manager_headers):
        """الـ endpoint يُرجع ملف Excel."""
        branch = _make_branch(db)
        month = date.today().strftime("%Y-%m")

        resp = client.get(
            "/api/v1/timeshare/installments/monthly-report",
            params={"branch_id": branch.id, "month": month},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]
        assert len(resp.content) > 0

    def test_correct_filename_in_header(self, client: TestClient, db, fake_redis, manager_headers):
        """اسم الملف في الـ header يحتوي على الشهر."""
        branch = _make_branch(db)
        month = "2026-07"

        resp = client.get(
            "/api/v1/timeshare/installments/monthly-report",
            params={"branch_id": branch.id, "month": month},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        assert "2026-07" in resp.headers.get("content-disposition", "")

    def test_invalid_month_format_rejected(self, client: TestClient, db, fake_redis, manager_headers):
        """صيغة شهر خاطئة تُرفض بـ 422."""
        branch = _make_branch(db)
        resp = client.get(
            "/api/v1/timeshare/installments/monthly-report",
            params={"branch_id": branch.id, "month": "07-2026"},
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_invalid_month_number_rejected(self, client: TestClient, db, fake_redis, manager_headers):
        """شهر 13 أو 00 يُرفض بـ 400."""
        branch = _make_branch(db)
        resp = client.get(
            "/api/v1/timeshare/installments/monthly-report",
            params={"branch_id": branch.id, "month": "2026-13"},
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_non_manager_rejected(self, client: TestClient, db, fake_redis, cashier_headers):
        """cashier لا يمكنه تصدير التقرير — 403."""
        branch = _make_branch(db)
        resp = client.get(
            "/api/v1/timeshare/installments/monthly-report",
            params={"branch_id": branch.id, "month": "2026-07"},
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_empty_month_returns_excel_not_error(self, client: TestClient, db, fake_redis, manager_headers):
        """شهر بدون أقساط يُرجع Excel فارغ (مش 404 أو error)."""
        branch = _make_branch(db)
        resp = client.get(
            "/api/v1/timeshare/installments/monthly-report",
            params={"branch_id": branch.id, "month": "2010-01"},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]

    def test_report_includes_installments_for_month(self, client: TestClient, db, fake_redis, manager_headers):
        """التقرير يشمل أقساط الشهر المطلوب — الـ Excel أكبر من التقرير الفارغ."""
        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_contract(db, branch.id, manager.id)
        today = date.today()
        _make_installment(db, contract.id, due_date=today.replace(day=15))

        month = today.strftime("%Y-%m")

        resp_with_data = client.get(
            "/api/v1/timeshare/installments/monthly-report",
            params={"branch_id": branch.id, "month": month},
            headers=manager_headers,
        )
        empty_branch = _make_branch(db)
        resp_empty = client.get(
            "/api/v1/timeshare/installments/monthly-report",
            params={"branch_id": empty_branch.id, "month": month},
            headers=manager_headers,
        )
        assert resp_with_data.status_code == 200
        assert resp_empty.status_code == 200
        # التقرير الذي فيه بيانات أكبر حجماً من الفارغ
        assert len(resp_with_data.content) > len(resp_empty.content)


# ── AuditLog عند تحصيل قسط ───────────────────────────────────────────────

class TestInstallmentPaymentAuditLog:
    """تحصيل قسط يُسجّل AuditLog."""

    def test_pay_installment_creates_audit_log(self, client: TestClient, db, fake_redis, cashier_headers):
        """POST /timeshare/installments/{id}/pay يُنشئ سجل AuditLog."""
        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_contract(db, branch.id, manager.id)
        inst = _make_installment(db, contract.id, due_date=date.today() + timedelta(days=30))

        resp = client.post(
            f"/api/v1/timeshare/installments/{inst.id}/pay",
            json={"paid_amount": "2500.00", "payment_method": "cash"},
            headers=cashier_headers,
        )
        assert resp.status_code == 200

        from app.modules.core.models import AuditLog
        logs = db.query(AuditLog).filter(
            AuditLog.entity_type == "timeshare_installment",
            AuditLog.entity_id == inst.id,
            AuditLog.action == "pay_installment",
        ).all()
        assert len(logs) >= 1, "لم يُنشأ AuditLog بعد تحصيل القسط"

    def test_audit_log_has_correct_data(self, client: TestClient, db, fake_redis, cashier_headers):
        """AuditLog يحتوي على new_data صحيحة (paid_amount + payment_method)."""
        import json
        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_contract(db, branch.id, manager.id)
        inst = _make_installment(db, contract.id, due_date=date.today() + timedelta(days=30))

        client.post(
            f"/api/v1/timeshare/installments/{inst.id}/pay",
            json={"paid_amount": "3000.00", "payment_method": "card", "receipt_number": "RCP-001"},
            headers=cashier_headers,
        )

        from app.modules.core.models import AuditLog
        log = db.query(AuditLog).filter(
            AuditLog.entity_type == "timeshare_installment",
            AuditLog.entity_id == inst.id,
        ).first()
        assert log is not None
        new_data = json.loads(log.new_data)
        assert new_data["payment_method"] == "card"
        assert new_data["receipt_number"] == "RCP-001"
        assert float(new_data["amount_paid_now"]) == 3000.0

    def test_multiple_payments_create_multiple_logs(self, client: TestClient, db, fake_redis, cashier_headers):
        """دفعتان على نفس القسط تُنشئان سجلّين منفصلَين."""
        from app.modules.core.models import AuditLog
        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_contract(db, branch.id, manager.id)
        inst = _make_installment(db, contract.id, due_date=date.today() + timedelta(days=30), amount=Decimal("6000"))

        client.post(
            f"/api/v1/timeshare/installments/{inst.id}/pay",
            json={"paid_amount": "2000.00", "payment_method": "cash"},
            headers=cashier_headers,
        )
        client.post(
            f"/api/v1/timeshare/installments/{inst.id}/pay",
            json={"paid_amount": "2000.00", "payment_method": "bank_transfer"},
            headers=cashier_headers,
        )

        logs = db.query(AuditLog).filter(
            AuditLog.entity_type == "timeshare_installment",
            AuditLog.entity_id == inst.id,
            AuditLog.action == "pay_installment",
        ).all()
        assert len(logs) == 2

    def test_audit_log_has_branch_id(self, client: TestClient, db, fake_redis, cashier_headers):
        """AuditLog يحتوي على branch_id الصحيح."""
        from app.modules.core.models import AuditLog
        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_contract(db, branch.id, manager.id)
        inst = _make_installment(db, contract.id, due_date=date.today() + timedelta(days=30))

        client.post(
            f"/api/v1/timeshare/installments/{inst.id}/pay",
            json={"paid_amount": "1000.00", "payment_method": "cash"},
            headers=cashier_headers,
        )

        log = db.query(AuditLog).filter(
            AuditLog.entity_type == "timeshare_installment",
            AuditLog.entity_id == inst.id,
        ).first()
        assert log is not None
        assert log.branch_id == branch.id

    def test_service_direct_audit_log(self, db):
        """اختبار وحدة مباشر لـ services.pay_installment — يُنشئ AuditLog."""
        from app.modules.core.models import AuditLog
        from app.modules.timeshare import services as ts_services
        from app.modules.timeshare.schemas import PayInstallmentRequest

        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_contract(db, branch.id, manager.id)
        inst = _make_installment(db, contract.id, due_date=date.today() + timedelta(days=30))

        req = PayInstallmentRequest(paid_amount=Decimal("1500"), payment_method="cash")
        ts_services.pay_installment(db, inst.id, req)

        logs = db.query(AuditLog).filter(
            AuditLog.entity_type == "timeshare_installment",
            AuditLog.entity_id == inst.id,
            AuditLog.action == "pay_installment",
        ).all()
        assert len(logs) == 1

    def test_generate_monthly_report_service(self, db):
        """اختبار وحدة مباشر لـ services.generate_monthly_collection_report."""
        branch = _make_branch(db)
        manager = _make_manager(db)
        contract = _make_contract(db, branch.id, manager.id)
        today = date.today()
        _make_installment(db, contract.id, due_date=today.replace(day=15))

        from app.modules.timeshare import services as ts_services
        month = today.strftime("%Y-%m")
        result = ts_services.generate_monthly_collection_report(db, branch.id, month)

        assert isinstance(result, bytes)
        assert len(result) > 1000  # Excel file يكون أكبر من 1KB على الأقل
