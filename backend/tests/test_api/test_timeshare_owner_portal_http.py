"""
tests/test_api/test_timeshare_owner_portal_http.py
HTTP-level tests for the Timeshare Owner Portal (/timeshare/public/*) —
2026-08-04: كانت الميزة كلها (OTP verify → JWT قصير العمر → عرض العقد/
الدفعات/طلبات الزيارة/تذاكر الدعم) بدون أي تست دائم في الـsuite خالص —
التحقق الوحيد اللي حصل كان سكريبت تجريبي مؤقت اتحذف بعد التأكد، مش جزء
من التغطية الدائمة.

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed —
نفس ملاحظة test_timeshare_http.py (جلسة DB مختلفة عبر الطلب الفعلي).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Owner Portal Branch", name_ar="فرع بوابة العميل",
               code=f"OP-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_owner_contract(db, branch, *, phone="01055512345", status="active"):
    from app.modules.timeshare.models import TimeshareContract
    contract = TimeshareContract(
        branch_id=branch.id,
        contract_number=f"TS-OWNER-{uuid.uuid4().hex[:8].upper()}",
        customer_name="صاحب عقد اختباري",
        customer_phone=phone,
        room_type="2R",
        nights_per_year=7,
        season="high",
        total_value=Decimal("100000.00"),
        down_payment=Decimal("20000.00"),
        installments=4,
        installment_period=1,
        first_installment_date=date.today() + timedelta(days=30),
        start_date=date.today(),
        status=status,
    )
    db.add(contract)
    db.commit()
    return contract


class TestOwnerPortalOtpFlow:
    def test_full_verify_flow_issues_token_and_reaches_dashboard(self, client: TestClient, db, fake_redis):
        """OTP request → confirm → توكن حقيقي → GET /my-contract بيه ينجح."""
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        captured: dict = {}
        wa_module.send_whatsapp_message = lambda phone, msg: captured.update(phone=phone, msg=msg)
        try:
            branch = make_branch_committed(db)
            contract = make_owner_contract(db, branch, phone="01055512345")

            req = client.post(
                "/api/v1/timeshare/public/verify-request",
                json={"contract_number": contract.contract_number, "phone": contract.customer_phone},
            )
            assert req.status_code == 200, req.text
            assert captured.get("phone") == contract.customer_phone
            # الكود آخر 6 أرقام في الرسالة (نفس تنسيق request_owner_otp)
            import re
            match = re.search(r"\b(\d{6})\b", captured["msg"])
            assert match, captured["msg"]
            code = match.group(1)

            confirm = client.post(
                "/api/v1/timeshare/public/verify-confirm",
                json={"contract_number": contract.contract_number, "otp_code": code},
            )
            assert confirm.status_code == 200, confirm.text
            token = confirm.json()["token"]
            assert token

            dash = client.get(
                "/api/v1/timeshare/public/my-contract",
                headers={"X-Timeshare-Owner-Token": token},
            )
            assert dash.status_code == 200, dash.text
            assert dash.json()["contract_number"] == contract.contract_number
        finally:
            wa_module.send_whatsapp_message = original

    def test_verify_confirm_rejects_wrong_code(self, client: TestClient, db, fake_redis):
        import app.core.kernel.whatsapp as wa_module
        original = wa_module.send_whatsapp_message
        wa_module.send_whatsapp_message = lambda *a, **kw: None
        try:
            branch = make_branch_committed(db)
            contract = make_owner_contract(db, branch, phone="01055512346")
            client.post(
                "/api/v1/timeshare/public/verify-request",
                json={"contract_number": contract.contract_number, "phone": contract.customer_phone},
            )
            resp = client.post(
                "/api/v1/timeshare/public/verify-confirm",
                json={"contract_number": contract.contract_number, "otp_code": "000000"},
            )
            assert resp.status_code == 400
        finally:
            wa_module.send_whatsapp_message = original

    def test_my_contract_requires_token(self, client: TestClient):
        resp = client.get("/api/v1/timeshare/public/my-contract")
        assert resp.status_code == 422  # header إجباري مفقود

    def test_my_contract_rejects_garbage_token(self, client: TestClient):
        resp = client.get(
            "/api/v1/timeshare/public/my-contract",
            headers={"X-Timeshare-Owner-Token": "not-a-real-token"},
        )
        assert resp.status_code == 401


class TestOwnerPortalContractPdf:
    """2026-08-04: كان PDF العقد متاح للموظف بس — بوابة "تابع عقدك" اللي
    الضيف بيستخدمها مالهاش نسخة تحميل لعقده نفسه، رغم إنها أول حاجة
    متوقّعة من شاشة زي دي."""

    def _owner_token(self, contract_id: int) -> str:
        from app.modules.timeshare.services import _issue_owner_portal_token
        return _issue_owner_portal_token(contract_id)

    def test_download_contract_pdf_success(self, client: TestClient, db):
        branch = make_branch_committed(db)
        contract = make_owner_contract(db, branch)
        token = self._owner_token(contract.id)

        resp = client.get(
            "/api/v1/timeshare/public/my-contract/pdf",
            headers={"X-Timeshare-Owner-Token": token},
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"

    def test_download_contract_pdf_requires_token(self, client: TestClient):
        resp = client.get("/api/v1/timeshare/public/my-contract/pdf")
        assert resp.status_code == 422

    def test_download_contract_pdf_rejects_garbage_token(self, client: TestClient):
        resp = client.get(
            "/api/v1/timeshare/public/my-contract/pdf",
            headers={"X-Timeshare-Owner-Token": "not-a-real-token"},
        )
        assert resp.status_code == 401
