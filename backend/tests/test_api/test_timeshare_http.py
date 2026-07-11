"""
tests/test_api/test_timeshare_http.py
HTTP-level tests for the timeshare module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Timeshare HTTP Branch", name_ar="فرع تايم شير",
               code=f"TS-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def contract_payload(branch_id: int) -> dict:
    return {
        "branch_id": branch_id,
        "customer_name": "منى عبد الله",
        "room_type": "2R",
        "nights_per_year": 7,
        "season": "high",
        "total_value": "100000.00",
        "down_payment": "20000.00",
        "installments": 4,
        "installment_period": 1,
        "first_installment_date": str(date.today() + timedelta(days=30)),
        "start_date": str(date.today()),
    }


class TestTimeshareContractFlow:
    def test_create_contract_generates_installment_schedule(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)

        resp = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        contract = resp.json()
        assert contract["status"] == "active" or contract["status"] == "draft"
        assert contract["contract_number"]

        get_resp = client.get(f"/api/v1/timeshare/contracts/{contract['id']}", headers=manager_headers)
        assert get_resp.status_code == 200
        assert len(get_resp.json()["installments_list"]) == 4

    def test_pay_installment_updates_status(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        inst_id = contract["installments_list"][0]["id"]
        inst_amount = contract["installments_list"][0]["amount"]

        pay_resp = client.post(
            f"/api/v1/timeshare/installments/{inst_id}/pay",
            json={"paid_amount": inst_amount, "payment_method": "cash"},
            headers=manager_headers,
        )
        assert pay_resp.status_code == 200, pay_resp.text
        assert pay_resp.json()["status"] == "paid"
        assert Decimal(str(pay_resp.json()["paid_amount"])) == Decimal(str(inst_amount))

    def test_cancel_contract_via_http(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        cancel_resp = client.post(
            f"/api/v1/timeshare/contracts/{contract['id']}/cancel",
            json={"cancel_amount": "5000.00"},
            headers=manager_headers,
        )
        assert cancel_resp.status_code == 200, cancel_resp.text
        assert cancel_resp.json()["status"] == "cancelled"


class TestTimesharePermissions:
    def test_create_contract_requires_manager(self, client: TestClient, db, fake_redis, cashier_headers):
        """cashier (40) must not be able to create timeshare contracts (manager=60 required)."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_cancel_contract_requires_manager(self, client: TestClient, db, fake_redis, manager_headers, cashier_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            f"/api/v1/timeshare/contracts/{contract['id']}/cancel",
            json={"cancel_amount": "0"},
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_pay_installment_requires_cashier_not_just_active_user(
        self, client: TestClient, db, fake_redis, manager_headers, waiter_headers,
    ):
        """باج صلاحيات حقيقي كان هنا: /timeshare/installments/{id}/pay كان
        مفتوح لأي مستخدم نشط (get_current_active_user، حتى level 0) بدل
        get_cashier_user زي finance.add_payment المكافئة بالظبط. نادل
        (level 30) لازم يترفض دلوقتي."""
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        inst_id = contract["installments_list"][0]["id"]

        resp = client.post(
            f"/api/v1/timeshare/installments/{inst_id}/pay",
            json={"paid_amount": "100.00", "payment_method": "cash"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403


class TestTimeshareVisitAndUnitsHttp:
    """HTTP-level: تخصيص وحدة فعلية + منع تعارض حجز حقيقي عبر الـ API
    الحقيقي (مش نداء مباشر على services)."""

    def test_create_visit_allocates_real_unit(self, client: TestClient, db, fake_redis, manager_headers):
        from app.modules.timeshare.models import TimeshareUnit
        branch = make_branch_committed(db)
        unit = TimeshareUnit(branch_id=branch.id, unit_number="A-101", unit_type="2R")
        db.add(unit); db.commit()

        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            "/api/v1/timeshare/visits",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "check_in": str(date.today() + timedelta(days=10)),
                "check_out": str(date.today() + timedelta(days=17)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["unit_id"] == unit.id

    def test_create_visit_without_available_unit_returns_400(self, client: TestClient, db, fake_redis, manager_headers):
        """مفيش أي وحدة من نوع 2R في الفرع ده — لازم 400 وليس نجاح صامت."""
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            "/api/v1/timeshare/visits",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "check_in": str(date.today() + timedelta(days=10)),
                "check_out": str(date.today() + timedelta(days=17)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400
        assert "وحدة متاحة" in resp.json()["detail"]

    def test_double_booking_same_unit_rejected_via_http(self, client: TestClient, db, fake_redis, manager_headers):
        """عقدين مختلفين على نفس الوحدة المخصَّصة دائمًا وفترة متقاطعة —
        الزيارة الثانية لازم ترفض بـ 400 حقيقي عبر الـ API."""
        from app.modules.timeshare.models import TimeshareUnit
        branch = make_branch_committed(db)
        unit = TimeshareUnit(branch_id=branch.id, unit_number="A-101", unit_type="2R")
        db.add(unit); db.commit()

        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        client.patch(
            f"/api/v1/timeshare/contracts/{contract['id']}",
            json={"unit_id": unit.id}, headers=manager_headers,
        )

        check_in = date.today() + timedelta(days=10)
        first = client.post(
            "/api/v1/timeshare/visits",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "check_in": str(check_in), "check_out": str(check_in + timedelta(days=7)),
            },
            headers=manager_headers,
        )
        assert first.status_code == 201, first.text

        second = client.post(
            "/api/v1/timeshare/visits",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "check_in": str(check_in + timedelta(days=3)), "check_out": str(check_in + timedelta(days=10)),
            },
            headers=manager_headers,
        )
        assert second.status_code == 400
        assert "محجوزة بالفعل" in second.json()["detail"]

    def test_list_units_endpoint(self, client: TestClient, db, fake_redis, manager_headers):
        from app.modules.timeshare.models import TimeshareUnit
        branch = make_branch_committed(db)
        db.add(TimeshareUnit(branch_id=branch.id, unit_number="B-201", unit_type="4R"))
        db.commit()

        resp = client.get(f"/api/v1/timeshare/units?branch_id={branch.id}", headers=manager_headers)
        assert resp.status_code == 200
        numbers = [u["unit_number"] for u in resp.json()]
        assert "B-201" in numbers


class TestTimeshareValidation:
    def test_create_contract_rejects_invalid_room_type(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        payload = contract_payload(branch.id)
        payload["room_type"] = "10R"
        resp = client.post("/api/v1/timeshare/contracts", json=payload, headers=manager_headers)
        assert resp.status_code == 422

    def test_create_contract_rejects_down_payment_exceeding_total(self, client: TestClient, db, fake_redis, manager_headers):
        """down_payment > total_value is a business rule (ValueError -> 400), not a schema constraint."""
        branch = make_branch_committed(db)
        payload = contract_payload(branch.id)
        payload["down_payment"] = "200000.00"
        resp = client.post("/api/v1/timeshare/contracts", json=payload, headers=manager_headers)
        assert resp.status_code == 400

    def test_pay_installment_rejects_invalid_method(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        inst_id = contract["installments_list"][0]["id"]

        resp = client.post(
            f"/api/v1/timeshare/installments/{inst_id}/pay",
            json={"paid_amount": "1000.00", "payment_method": "crypto"},
            headers=manager_headers,
        )
        assert resp.status_code == 422


def _set_installment_status(db, inst_id: int, status: str) -> None:
    """يضبط حالة قسط مباشرةً في نفس الـ session بتاعة الـ app (get_test_db)
    ثم commit — عشان endpoints التقارير تشوف الحالة الحقيقية."""
    from app.modules.timeshare.models import TimeshareInstallment
    inst = db.query(TimeshareInstallment).filter(TimeshareInstallment.id == inst_id).first()
    inst.status = status
    db.commit()


class TestTimeshareReportingHttp:
    """الـ 5 endpoints بتوع لوحات التايم شير (cs-summary / sales-dashboard /
    calendar / upcoming-visits / stats) — بتتنادى من TimeshareView.vue كل تحميل.
    تُختبر HTTP-level حقيقي مع تأكيد القيم المحسوبة الفعلية (مش مجرد 200 OK)."""

    def test_cs_summary_reflects_real_aggregates(self, client: TestClient, db, fake_redis, manager_headers):
        """عقد نشط 100000 / دفعة 20000 / 4 أقساط (20000 لكل قسط). ادفع القسط
        الأول كامل → collected=20000، خلّي القسط التاني overdue → متأخرات=20000."""
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        insts = contract["installments_list"]
        assert len(insts) == 4

        # ادفع القسط الأول بالكامل (20000)
        pay = client.post(
            f"/api/v1/timeshare/installments/{insts[0]['id']}/pay",
            json={"paid_amount": insts[0]["amount"], "payment_method": "cash"},
            headers=manager_headers,
        )
        assert pay.status_code == 200, pay.text
        # اجعل القسط الثاني متأخّراً
        _set_installment_status(db, insts[1]["id"], "overdue")

        resp = client.get(f"/api/v1/timeshare/cs-summary?branch_id={branch.id}", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["active_contracts"] == 1
        assert data["total_value"] == 100000.0
        assert data["total_collected"] == 20000.0
        assert data["collection_rate_pct"] == 20.0
        assert data["total_overdue"] == 20000.0
        assert data["overdue_contracts_count"] == 1
        # العميل المتأخر ظاهر برقم تليفونه جاهز للاتصال
        assert len(data["overdue_clients"]) == 1
        oc = data["overdue_clients"][0]
        assert oc["overdue_amount"] == 20000.0
        assert oc["id"] == contract["id"]

    def test_sales_dashboard_pipeline_counts_by_status(self, client: TestClient, db, fake_redis, manager_headers):
        """عقدين نشطين + واحد ملغى → pipeline: active=2, cancelled=1، والمفاتيح
        الأساسية (draft/suspended/expired) موجودة بصفر."""
        branch = make_branch_committed(db)
        c1 = client.post("/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers).json()
        client.post("/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers)
        to_cancel = client.post("/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers).json()
        cancel = client.post(
            f"/api/v1/timeshare/contracts/{to_cancel['id']}/cancel",
            json={"cancel_amount": "5000.00"}, headers=manager_headers,
        )
        assert cancel.status_code == 200, cancel.text

        resp = client.get(f"/api/v1/timeshare/sales-dashboard?branch_id={branch.id}", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["pipeline"]["active"] == 2
        assert data["pipeline"]["cancelled"] == 1
        for k in ("draft", "suspended", "expired"):
            assert k in data["pipeline"]
        assert data["active_contracts"] == 2  # cs-summary يعدّ النشطة فقط
        assert data["total_value"] == 200000.0  # عقدين نشطين × 100000 (الملغى مستبعَد)
        assert c1["id"] != to_cancel["id"]

    def test_sales_dashboard_export_returns_valid_excel_for_manager(
        self, client: TestClient, db, fake_redis, manager_headers,
    ):
        """wagdy.md #12: export Excel للوحة مبيعات التايم شير — مدير+ بس."""
        branch = make_branch_committed(db)
        client.post("/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers)

        resp = client.get(
            f"/api/v1/timeshare/sales-dashboard/export?branch_id={branch.id}", headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert "attachment" in resp.headers["content-disposition"]
        assert len(resp.content) > 0

    def test_sales_dashboard_export_requires_manager(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            f"/api/v1/timeshare/sales-dashboard/export?branch_id={branch.id}", headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_calendar_shows_booked_week_with_contract(self, client: TestClient, db, fake_redis, manager_headers):
        """عقد بأسبوع ثابت 28 → total_booked_weeks=1 والعقد يظهر تحت أسبوع 28."""
        branch = make_branch_committed(db)
        payload = contract_payload(branch.id)
        payload["week_number"] = 28
        contract = client.post("/api/v1/timeshare/contracts", json=payload, headers=manager_headers).json()

        resp = client.get(f"/api/v1/timeshare/calendar?branch_id={branch.id}&year=2026", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["year"] == 2026
        assert data["total_booked_weeks"] == 1
        week28 = [wk for month in data["calendar"] for wk in month["weeks"] if wk["week"] == 28]
        assert len(week28) == 1
        assert len(week28[0]["contracts"]) == 1
        assert week28[0]["contracts"][0]["contract_number"] == contract["contract_number"]

    def test_upcoming_visits_lists_active_contract_in_window(self, client: TestClient, db, fake_redis, manager_headers):
        """عقد نشط بأسبوع مستقبلي → يظهر في upcoming-visits ضمن نافذة 365 يوم
        مع days_until >= 0 وكل حقول العرض اللي الفرونت محتاجها."""
        from datetime import date as _date, timedelta as _td
        branch = make_branch_committed(db)
        future_week = min(52, (_date.today() + _td(days=14)).isocalendar()[1])
        payload = contract_payload(branch.id)
        payload["week_number"] = future_week
        contract = client.post("/api/v1/timeshare/contracts", json=payload, headers=manager_headers).json()

        resp = client.get(f"/api/v1/timeshare/upcoming-visits?branch_id={branch.id}&days=365", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        visits = resp.json()
        mine = [v for v in visits if v["contract_number"] == contract["contract_number"]]
        assert len(mine) == 1
        v = mine[0]
        assert v["days_until"] >= 0
        assert v["week_number"] == future_week
        assert v["room_type"] == "2R"
        assert "visit_start" in v and "visit_end" in v

    def test_upcoming_visits_excludes_cancelled_contract(self, client: TestClient, db, fake_redis, manager_headers):
        from datetime import date as _date, timedelta as _td
        branch = make_branch_committed(db)
        future_week = min(52, (_date.today() + _td(days=14)).isocalendar()[1])
        payload = contract_payload(branch.id)
        payload["week_number"] = future_week
        contract = client.post("/api/v1/timeshare/contracts", json=payload, headers=manager_headers).json()
        client.post(
            f"/api/v1/timeshare/contracts/{contract['id']}/cancel",
            json={"cancel_amount": "0"}, headers=manager_headers,
        )
        resp = client.get(f"/api/v1/timeshare/upcoming-visits?branch_id={branch.id}&days=365", headers=manager_headers)
        assert resp.status_code == 200
        assert not any(v["contract_number"] == contract["contract_number"] for v in resp.json())

    def test_stats_partner_share_room_and_collection(self, client: TestClient, db, fake_redis, manager_headers):
        """stats: resort_share الصافي (بعد نصيب الشريك)، by_batch، وتحصيل فعلي."""
        branch = make_branch_committed(db)
        payload = contract_payload(branch.id)
        payload.update({
            "partner_company": "شركة الشريك التجارية",
            "partner_share_pct": "30",
            "batch_number": 7,
        })
        contract = client.post("/api/v1/timeshare/contracts", json=payload, headers=manager_headers).json()
        # ادفع أول قسط عشان التحصيل يبقى > 0
        first_inst = contract["installments_list"][0]
        client.post(
            f"/api/v1/timeshare/installments/{first_inst['id']}/pay",
            json={"paid_amount": first_inst["amount"], "payment_method": "cash"},
            headers=manager_headers,
        )

        resp = client.get(f"/api/v1/timeshare/stats?branch_id={branch.id}", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        partner = next(r for r in data["by_partner"] if r["partner_company"] == "شركة الشريك التجارية")
        assert partner["total_down"] == 20000.0
        # 20000 * (1 - 30/100) = 14000
        assert partner["resort_share"] == 14000.0
        assert any(r["room_type"] == "2R" for r in data["by_room_type"])
        assert any(b["batch_number"] == 7 for b in data["by_batch"])
        assert data["collection"]["collected"] == float(first_inst["amount"])
        assert data["collection"]["rate"] > 0


class TestTimeshareRouterMiscHttp:
    """تغطية باقي مسارات الـ router غير المغطّاة HTTP-level (list/404/error paths/
    waitlist/pdf/installments/visits/import) — عشان router.py يقفل فجوات التغطية."""

    def test_list_contracts_paginated(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        client.post("/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers)
        resp = client.get(f"/api/v1/timeshare/contracts?branch_id={branch.id}&page=1&size=20", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1

    def test_get_contract_404(self, client: TestClient, db, fake_redis, manager_headers):
        make_branch_committed(db)
        resp = client.get("/api/v1/timeshare/contracts/999999", headers=manager_headers)
        assert resp.status_code == 404

    def test_update_nonexistent_contract_returns_400(self, client: TestClient, db, fake_redis, manager_headers):
        make_branch_committed(db)
        resp = client.patch(
            "/api/v1/timeshare/contracts/999999", json={"notes": "x"}, headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_pay_already_paid_installment_returns_400(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        inst = contract["installments_list"][0]
        first = client.post(
            f"/api/v1/timeshare/installments/{inst['id']}/pay",
            json={"paid_amount": inst["amount"], "payment_method": "cash"}, headers=manager_headers,
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/v1/timeshare/installments/{inst['id']}/pay",
            json={"paid_amount": inst["amount"], "payment_method": "cash"}, headers=manager_headers,
        )
        assert second.status_code == 400

    def test_waitlist_add_then_list(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        add = client.post(
            "/api/v1/timeshare/waitlist",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "requested_start": str(date.today() + timedelta(days=40)),
                "requested_end": str(date.today() + timedelta(days=47)),
            },
            headers=manager_headers,
        )
        assert add.status_code == 201, add.text
        assert add.json()["position"] == 1
        lst = client.get(f"/api/v1/timeshare/waitlist?branch_id={branch.id}", headers=manager_headers)
        assert lst.status_code == 200
        assert len(lst.json()) == 1

    def test_waitlist_invalid_dates_returns_400(self, client: TestClient, db, fake_redis, manager_headers):
        """requested_end <= requested_start قاعدة عمل (ValueError→400) مش قيد schema."""
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        resp = client.post(
            "/api/v1/timeshare/waitlist",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "requested_start": str(date.today() + timedelta(days=47)),
                "requested_end": str(date.today() + timedelta(days=40)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_download_contract_pdf(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        resp = client.get(f"/api/v1/timeshare/contracts/{contract['id']}/pdf", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"

    def test_download_pdf_nonexistent_returns_404(self, client: TestClient, db, fake_redis, manager_headers):
        make_branch_committed(db)
        resp = client.get("/api/v1/timeshare/contracts/999999/pdf", headers=manager_headers)
        assert resp.status_code == 404

    def test_list_installments_http(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        client.post("/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers)
        resp = client.get(f"/api/v1/timeshare/installments?branch_id={branch.id}", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 4
        assert "overdue_total" in body["summary"]
        assert "pending_total" in body["summary"]

    def test_list_installments_includes_customer_for_frontend_table(
        self, client: TestClient, db, fake_redis, manager_headers,
    ):
        """Regression: جدول الأقساط في TimeshareView.vue بيعرض p.customer_name و
        p.customer_phone — لكن InstallmentRead كان بيرجّعهم فاضيين (مش موجودين
        في الـ schema أصلاً)، فعمود العميل كان بيظهر فاضي في لوحة متابعة
        المتأخرات. لازم الـ endpoint يرجّع اسم/هاتف/نوع غرفة العميل مع كل قسط."""
        branch = make_branch_committed(db)
        payload = contract_payload(branch.id)  # customer_name="منى عبد الله", phone default None
        payload["customer_phone"] = "01099887766"
        client.post("/api/v1/timeshare/contracts", json=payload, headers=manager_headers)
        resp = client.get(f"/api/v1/timeshare/installments?branch_id={branch.id}", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        first = resp.json()["installments"][0]
        assert first["customer_name"] == "منى عبد الله"
        assert first["customer_phone"] == "01099887766"
        assert first["room_type"] == "2R"

    def test_cancel_already_cancelled_returns_400(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        client.post(
            f"/api/v1/timeshare/contracts/{contract['id']}/cancel",
            json={"cancel_amount": "0"}, headers=manager_headers,
        )
        again = client.post(
            f"/api/v1/timeshare/contracts/{contract['id']}/cancel",
            json={"cancel_amount": "0"}, headers=manager_headers,
        )
        assert again.status_code == 400

    def test_list_visits_http(self, client: TestClient, db, fake_redis, manager_headers):
        from app.modules.timeshare.models import TimeshareUnit
        branch = make_branch_committed(db)
        unit = TimeshareUnit(branch_id=branch.id, unit_number="A-301", unit_type="2R")
        db.add(unit); db.commit()
        contract = client.post(
            "/api/v1/timeshare/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        client.post(
            "/api/v1/timeshare/visits",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "check_in": str(date.today() + timedelta(days=10)),
                "check_out": str(date.today() + timedelta(days=17)),
            },
            headers=manager_headers,
        )
        resp = client.get(f"/api/v1/timeshare/visits?branch_id={branch.id}", headers=manager_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_update_nonexistent_visit_returns_404(self, client: TestClient, db, fake_redis, manager_headers):
        make_branch_committed(db)
        resp = client.patch(
            "/api/v1/timeshare/visits/999999", json={"status": "completed"}, headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_import_contracts_excel(self, client: TestClient, db, fake_redis, manager_headers):
        import io
        import openpyxl
        branch = make_branch_committed(db)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append([
            "customer_name", "room_type", "total_value", "down_payment",
            "installments", "start_date", "first_installment_date",
        ])
        ws.append([
            "سميرة فؤاد", "4R", 80000, 16000, 6,
            str(date.today()), str(date.today() + timedelta(days=30)),
        ])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        resp = client.post(
            f"/api/v1/timeshare/contracts/import-excel?branch_id={branch.id}",
            files={"file": ("contracts.xlsx", buf.read(),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["imported"] == 1

    def test_import_excel_missing_columns_returns_400(self, client: TestClient, db, fake_redis, manager_headers):
        import io
        import openpyxl
        branch = make_branch_committed(db)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["customer_name", "room_type"])  # أعمدة إلزامية ناقصة
        ws.append(["ناقص", "2R"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = client.post(
            f"/api/v1/timeshare/contracts/import-excel?branch_id={branch.id}",
            files={"file": ("bad.xlsx", buf.read(),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers=manager_headers,
        )
        assert resp.status_code == 400
