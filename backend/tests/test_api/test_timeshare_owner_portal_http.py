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
        room_type="Studio",
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


def make_unit(db, branch, *, unit_type="Studio"):
    from app.modules.timeshare.models import TimeshareUnit
    unit = TimeshareUnit(
        branch_id=branch.id, unit_number=f"U-{uuid.uuid4().hex[:6].upper()}",
        unit_type=unit_type, status="available",
    )
    db.add(unit)
    db.commit()
    return unit


def owner_token(contract_id: int) -> str:
    from app.modules.timeshare.services import _issue_owner_portal_token
    return _issue_owner_portal_token(contract_id)


def branch_scoped_admin_headers(branch) -> dict[str, str]:
    """timeshare_admin_headers (fixture) بيصدر توكن من غير claim فرع صريح —
    بيشتغل بس لما يبقى فيه فرع "افتراضي" واحد بلا لبس في الداتابيز، وده
    مش مضمون هنا (كل تست في الملف ده بيعمل make_branch_committed خاص بيه).
    super_admin (level≥100) بيتخطى فحص العضوية بالكامل (راجع
    core.services._can_enter_branch) لكن لازم claim ``bid`` صريح في
    التوكن نفسه — نفس نمط test_crm_endpoints_http.py's
    super_admin_headers_for_branch بالظبط."""
    from tests.conftest import _fresh_super_admin
    _, headers, _ = _fresh_super_admin(branch_id=branch.id)
    return headers


class TestVisitRequestNotifications:
    """2026-08-04: طلب زيارة من بوابة العميل مالهوش أي تنبيه لحد — لا للموظف
    وقت التقديم، ولا للعميل وقت الموافقة/الرفض. العميل مالوش جلسة دائمة
    (بوابة OTP بس)، فبدون واتساب الطريقة الوحيدة إنه يعرف نتيجة طلبه هي
    إنه يرجع بنفسه يعمل OTP تاني ويشيك — نفس فجوة تذاكر الدعم تحت."""

    def test_create_visit_request_notifies_admin(self, client: TestClient, db, fake_redis, monkeypatch):
        import app.core.kernel.whatsapp as wa_module
        captured: dict = {}
        monkeypatch.setattr(wa_module, "notify_admin", lambda msg: captured.update(msg=msg) or True)

        branch = make_branch_committed(db)
        contract = make_owner_contract(db, branch)
        resp = client.post(
            "/api/v1/timeshare/public/visit-requests",
            json={"preferred_start": "2027-01-10", "preferred_end": "2027-01-17"},
            headers={"X-Timeshare-Owner-Token": owner_token(contract.id)},
        )
        assert resp.status_code == 201, resp.text
        assert contract.customer_name in captured.get("msg", "")
        assert contract.contract_number in captured["msg"]

    def test_approve_visit_request_notifies_customer(
        self, client: TestClient, db, fake_redis, monkeypatch,
    ):
        import app.core.kernel.whatsapp as wa_module
        captured: dict = {}
        monkeypatch.setattr(wa_module, "notify_admin", lambda msg: True)
        monkeypatch.setattr(
            wa_module, "send_whatsapp_message",
            lambda phone, msg: captured.update(phone=phone, msg=msg) or True,
        )

        branch = make_branch_committed(db)
        contract = make_owner_contract(db, branch)
        make_unit(db, branch, unit_type=contract.room_type)
        create_resp = client.post(
            "/api/v1/timeshare/public/visit-requests",
            json={"preferred_start": "2027-01-10", "preferred_end": "2027-01-17"},
            headers={"X-Timeshare-Owner-Token": owner_token(contract.id)},
        )
        request_id = create_resp.json()["id"]

        approve = client.post(
            f"/api/v1/timeshare/visit-requests/{request_id}/approve",
            json={"check_in": "2027-01-10", "check_out": "2027-01-17"},
            headers=branch_scoped_admin_headers(branch),
        )
        assert approve.status_code == 200, approve.text
        assert captured.get("phone") == contract.customer_phone
        assert "2027-01-10" in captured["msg"]

    def test_reject_visit_request_notifies_customer(
        self, client: TestClient, db, fake_redis, monkeypatch,
    ):
        import app.core.kernel.whatsapp as wa_module
        captured: dict = {}
        monkeypatch.setattr(wa_module, "notify_admin", lambda msg: True)
        monkeypatch.setattr(
            wa_module, "send_whatsapp_message",
            lambda phone, msg: captured.update(phone=phone, msg=msg) or True,
        )

        branch = make_branch_committed(db)
        contract = make_owner_contract(db, branch)
        create_resp = client.post(
            "/api/v1/timeshare/public/visit-requests",
            json={"preferred_start": "2027-01-10", "preferred_end": "2027-01-17"},
            headers={"X-Timeshare-Owner-Token": owner_token(contract.id)},
        )
        request_id = create_resp.json()["id"]

        reject = client.post(
            f"/api/v1/timeshare/visit-requests/{request_id}/reject",
            json={"reason": "الفترة دي محجوزة بالكامل"},
            headers=branch_scoped_admin_headers(branch),
        )
        assert reject.status_code == 200, reject.text
        assert captured.get("phone") == contract.customer_phone
        assert "الفترة دي محجوزة بالكامل" in captured["msg"]


class TestSupportTicketNotifications:
    """2026-08-04: نفس الفجوة — تذكرة دعم جديدة مالهاش تنبيه للموظف، ورد
    الموظف مالوش تنبيه للعميل."""

    def test_create_ticket_notifies_admin(self, client: TestClient, db, fake_redis, monkeypatch):
        import app.core.kernel.whatsapp as wa_module
        captured: dict = {}
        monkeypatch.setattr(wa_module, "notify_admin", lambda msg: captured.update(msg=msg) or True)

        branch = make_branch_committed(db)
        contract = make_owner_contract(db, branch)
        resp = client.post(
            "/api/v1/timeshare/public/support-tickets",
            json={"subject": "استفسار عن موعد الزيارة", "message": "عايز أعرف تفاصيل أكتر"},
            headers={"X-Timeshare-Owner-Token": owner_token(contract.id)},
        )
        assert resp.status_code == 201, resp.text
        assert "استفسار عن موعد الزيارة" in captured.get("msg", "")
        assert contract.contract_number in captured["msg"]

    def test_staff_reply_notifies_customer(
        self, client: TestClient, db, fake_redis, monkeypatch,
    ):
        import app.core.kernel.whatsapp as wa_module
        monkeypatch.setattr(wa_module, "notify_admin", lambda msg: True)
        captured: dict = {}
        monkeypatch.setattr(
            wa_module, "send_whatsapp_message",
            lambda phone, msg: captured.update(phone=phone, msg=msg) or True,
        )

        branch = make_branch_committed(db)
        contract = make_owner_contract(db, branch)
        create_resp = client.post(
            "/api/v1/timeshare/public/support-tickets",
            json={"subject": "استفسار عن موعد الزيارة", "message": "عايز أعرف تفاصيل أكتر"},
            headers={"X-Timeshare-Owner-Token": owner_token(contract.id)},
        )
        ticket_id = create_resp.json()["id"]

        reply = client.post(
            f"/api/v1/timeshare/support-tickets/{ticket_id}/reply",
            json={"message": "أهلًا بيك، الزيارة متاحة الأسبوع الجاي"},
            headers=branch_scoped_admin_headers(branch),
        )
        assert reply.status_code == 200, reply.text
        assert captured.get("phone") == contract.customer_phone
        assert "استفسار عن موعد الزيارة" in captured["msg"]
        # رد الموظف على تذكرة مفتوحة يحوّلها "قيد المعالجة" تلقائيًا
        assert reply.json()["status"] == "in_progress"

    def test_owner_followup_reply_notifies_admin(
        self, client: TestClient, db, fake_redis, monkeypatch, timeshare_admin_headers,
    ):
        import app.core.kernel.whatsapp as wa_module
        captured: list = []
        monkeypatch.setattr(wa_module, "notify_admin", lambda msg: captured.append(msg) or True)
        monkeypatch.setattr(wa_module, "send_whatsapp_message", lambda *a, **kw: True)

        branch = make_branch_committed(db)
        contract = make_owner_contract(db, branch)
        create_resp = client.post(
            "/api/v1/timeshare/public/support-tickets",
            json={"subject": "استفسار عن موعد الزيارة", "message": "عايز أعرف تفاصيل أكتر"},
            headers={"X-Timeshare-Owner-Token": owner_token(contract.id)},
        )
        ticket_id = create_resp.json()["id"]
        assert len(captured) == 1  # التذكرة الجديدة نفسها

        followup = client.post(
            f"/api/v1/timeshare/public/support-tickets/{ticket_id}/reply",
            json={"message": "لسه مستني رد"},
            headers={"X-Timeshare-Owner-Token": owner_token(contract.id)},
        )
        assert followup.status_code == 200, followup.text
        assert len(captured) == 2  # المتابعة كمان بلّغت الموظف
        assert "لسه مستني رد" not in captured[1]  # نص الرسالة نفسه مش بيتسرب للتنبيه، الموضوع بس
        assert "استفسار عن موعد الزيارة" in captured[1]


class TestCsSummaryPendingCounts:
    """2026-08-04: مفيش أي مؤشر في اللوحة لعدد طلبات الزيارة/تذاكر الدعم
    المعلّقة — الموظف كان لازم يفتح التابين يدويًا كل مرة."""

    def test_includes_pending_visit_requests_and_open_tickets(
        self, client: TestClient, db, fake_redis, monkeypatch,
    ):
        import app.core.kernel.whatsapp as wa_module
        monkeypatch.setattr(wa_module, "notify_admin", lambda msg: True)

        branch = make_branch_committed(db)
        contract = make_owner_contract(db, branch)
        client.post(
            "/api/v1/timeshare/public/visit-requests",
            json={"preferred_start": "2027-01-10", "preferred_end": "2027-01-17"},
            headers={"X-Timeshare-Owner-Token": owner_token(contract.id)},
        )
        client.post(
            "/api/v1/timeshare/public/support-tickets",
            json={"subject": "استفسار", "message": "تفاصيل"},
            headers={"X-Timeshare-Owner-Token": owner_token(contract.id)},
        )

        resp = client.get(
            "/api/v1/timeshare/cs-summary", params={"branch_id": branch.id},
            headers=branch_scoped_admin_headers(branch),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["pending_visit_requests"] >= 1
        assert data["open_support_tickets"] >= 1
