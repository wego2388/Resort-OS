"""
tests/test_api/test_analytics_http.py
HTTP-level tests for the analytics module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

Task B audit (2026-07-01): the analytics module's `UtilityReading` model and
its Alembic migration existed, but there was no schema/service/router at all
to ever create one (grep for `UtilityReading(` outside models.py returned
nothing) — same "model exists, zero wiring" pattern as PMS housekeeping and
CRM leads in Task A, and TenantCashLog in leasing (Task B). Similarly,
`ReviewCategory` rows were being written on every guest-survey submission but
never read/aggregated anywhere. Both gaps were fixed; these tests cover the
new endpoints end-to-end.

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Analytics HTTP Branch", name_ar="فرع تحليلات",
               code=f"ANL-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def seed_utility_accounts(db, branch):
    from app.modules.finance.models import Account
    db.add_all([
        Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset"),
        Account(branch_id=branch.id, code="5300", name="Utilities Expense", account_type="expense"),
    ])
    db.commit()


def make_booking_committed(db, branch):
    from app.modules.pms.models import Booking
    booking = Booking(
        branch_id=branch.id, booking_number=f"BK-{uuid.uuid4().hex[:8].upper()}",
        guest_name="ضيف اختبار",
        check_in=date.today(), check_out=date.today() + timedelta(days=2),
        status="checked_out", adults=1, children=0,
    )
    db.add(booking)
    db.commit()
    return booking


class TestUtilityReadingFlow:
    def test_create_reading_computes_total_cost_and_posts_journal(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        seed_utility_accounts(db, branch)

        resp = client.post(
            "/api/v1/analytics/utilities",
            json={
                "branch_id": branch.id, "reading_date": str(date.today()),
                "utility_type": "electricity", "reading_value": "500.000",
                "unit": "kWh", "unit_cost": "2.50",
            },
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        reading = resp.json()
        assert Decimal(str(reading["total_cost"])) == Decimal("1250.00")

        from app.modules.finance.models import JournalEntry
        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "analytics", JournalEntry.source_id == reading["id"])
            .first()
        )
        assert entry is not None
        lines = {l.account.code: (l.debit, l.credit) for l in entry.lines}
        assert lines["5300"] == (Decimal("1250.00"), Decimal("0.00"))
        assert lines["1100"] == (Decimal("0.00"), Decimal("1250.00"))

    def test_list_utilities_filters_by_period(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        client.post(
            "/api/v1/analytics/utilities",
            json={
                "branch_id": branch.id, "reading_date": "2026-01-15",
                "utility_type": "water", "reading_value": "10.000", "unit_cost": "5.00",
            },
            headers=manager_headers,
        )
        client.post(
            "/api/v1/analytics/utilities",
            json={
                "branch_id": branch.id, "reading_date": "2026-02-15",
                "utility_type": "water", "reading_value": "12.000", "unit_cost": "5.00",
            },
            headers=manager_headers,
        )

        resp = client.get(
            "/api/v1/analytics/utilities",
            params={"branch_id": branch.id, "period": "2026-01"},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) == 1
        assert resp.json()[0]["reading_date"] == "2026-01-15"

    def test_energy_kpi_computes_cost_per_guest_night(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        from app.modules.analytics.models import DailyStats
        db.add(DailyStats(branch_id=branch.id, stat_date=date(2026, 3, 10), occupied_rooms=10, total_rooms=20))
        db.commit()

        client.post(
            "/api/v1/analytics/utilities",
            json={
                "branch_id": branch.id, "reading_date": "2026-03-10",
                "utility_type": "electricity", "reading_value": "100.000", "unit_cost": "3.00",
            },
            headers=manager_headers,
        )

        resp = client.get(
            "/api/v1/analytics/energy",
            params={"branch_id": branch.id, "period": "2026-03"},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["guest_nights"] == 10
        assert Decimal(str(body["electricity_cost_per_guest_night"])) == Decimal("30.00")

    def test_energy_trend_includes_reading_month_and_is_chronological(self, client: TestClient, db, manager_headers):
        """wagdy.md #18: اتجاه شهري بدل لقطة شهر واحد فقط."""
        branch = make_branch_committed(db)
        client.post(
            "/api/v1/analytics/utilities",
            json={
                "branch_id": branch.id, "reading_date": "2026-02-10",
                "utility_type": "electricity", "reading_value": "50.000", "unit_cost": "3.00",
            },
            headers=manager_headers,
        )

        resp = client.get(
            "/api/v1/analytics/energy/trend",
            params={"branch_id": branch.id, "end_period": "2026-03", "months": 4},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        periods = [row["period"] for row in body]
        assert periods == ["2025-12", "2026-01", "2026-02", "2026-03"]
        feb = next(row for row in body if row["period"] == "2026-02")
        assert feb["by_type"]["electricity"] == 150.0

    def test_energy_trend_export_returns_valid_excel(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/analytics/energy/trend/export",
            params={"branch_id": branch.id, "end_period": "2026-03", "months": 3},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert len(resp.content) > 0

    def test_energy_trend_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/analytics/energy/trend",
            params={"branch_id": branch.id}, headers=waiter_headers,
        )
        assert resp.status_code == 403


class TestUtilityReadingPermissions:
    def test_create_utility_reading_requires_manager(self, client: TestClient, db, cashier_headers):
        """cashier (40) must not record utility readings — manager (60) required."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/analytics/utilities",
            json={
                "branch_id": branch.id, "reading_date": str(date.today()),
                "utility_type": "electricity", "reading_value": "100.000", "unit_cost": "2.00",
            },
            headers=cashier_headers,
        )
        assert resp.status_code == 403


class TestUtilityReadingValidation:
    def test_create_reading_rejects_invalid_utility_type(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/analytics/utilities",
            json={
                "branch_id": branch.id, "reading_date": str(date.today()),
                "utility_type": "solar_wind", "reading_value": "10.000", "unit_cost": "1.00",
            },
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_create_reading_rejects_zero_consumption(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/analytics/utilities",
            json={
                "branch_id": branch.id, "reading_date": str(date.today()),
                "utility_type": "gas", "reading_value": "0", "unit_cost": "1.00",
            },
            headers=manager_headers,
        )
        assert resp.status_code == 422


class TestGuestReviewInsights:
    def test_review_insights_surfaces_category_breakdown(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        booking = make_booking_committed(db, branch)

        token_resp = client.get(
            f"/api/v1/analytics/reviews/survey-token/{booking.id}",
            params={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert token_resp.status_code == 200, token_resp.text
        token = token_resp.json()["token"]

        submit_resp = client.post(
            "/api/v1/analytics/reviews/submit",
            params={"token": token},
            json={
                "guest_name": "سلمى فتحي", "overall_rating": 5,
                "comment": "إقامة رائعة",
                "categories": [
                    {"category": "cleanliness", "rating": 5},
                    {"category": "service", "rating": 4},
                ],
            },
        )
        assert submit_resp.status_code == 200, submit_resp.text

        insights_resp = client.get(
            "/api/v1/analytics/reviews/insights", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert insights_resp.status_code == 200, insights_resp.text
        body = insights_resp.json()
        assert body["overall_avg"] == 5.0
        assert body["gss_score"] == 5.0
        cats = {c["category"]: c for c in body["category_breakdown"]}
        assert cats["cleanliness"]["avg_rating"] == 5.0
        assert cats["service"]["avg_rating"] == 4.0

    def test_review_insights_empty_when_no_reviews(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/analytics/reviews/insights", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["overall_avg"] is None
        assert resp.json()["category_breakdown"] == []

    def test_timeshare_visit_survey_token_and_submit(self, client: TestClient, db, manager_headers):
        """مسار مواز لـ survey-token/{booking_id} — لكن لزيارة تايم شير بدل
        حجز فندقي (GET /analytics/reviews/survey-token/timeshare/{visit_id}).
        نفس شكل الاستجابة بالظبط، ونفس POST /analytics/reviews/submit."""
        from decimal import Decimal
        from app.modules.timeshare.models import TimeshareUnit
        from app.modules.timeshare.schemas import TimeshareContractCreate, TimeshareVisitCreate
        from app.modules.timeshare import services as ts_services

        branch = make_branch_committed(db)
        unit = TimeshareUnit(branch_id=branch.id, unit_number="A-101", unit_type="2R")
        db.add(unit); db.commit()

        contract = ts_services.create_contract(db, TimeshareContractCreate(
            branch_id=branch.id, customer_name="عميل تايم شير", room_type="2R",
            total_value=Decimal("120000"), down_payment=Decimal("20000"),
            installments=12, installment_period=1,
            first_installment_date=date(2026, 8, 1),
            partner_share_pct=Decimal("0"), start_date=date(2026, 7, 1),
        ), signed_by=1)
        visit = ts_services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 1), check_out=date(2026, 8, 8),
        ))

        token_resp = client.get(
            f"/api/v1/analytics/reviews/survey-token/timeshare/{visit.id}",
            params={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert token_resp.status_code == 200, token_resp.text
        assert "token" in token_resp.json() and "expires_in_days" in token_resp.json()
        token = token_resp.json()["token"]

        submit_resp = client.post(
            "/api/v1/analytics/reviews/submit",
            params={"token": token},
            json={"guest_name": "عميل تايم شير", "overall_rating": 5, "comment": "ممتاز"},
        )
        assert submit_resp.status_code == 200, submit_resp.text

        from app.modules.analytics.models import GuestReview
        review = db.query(GuestReview).filter(GuestReview.id == submit_resp.json()["id"]).first()
        assert review.booking_id is None
        assert review.timeshare_visit_id == visit.id

    def test_send_timeshare_survey_queues_whatsapp(self, client: TestClient, db, manager_headers):
        """POST .../survey-token/timeshare/{visit_id}/send — قبل ده، مفيش أي
        طريقة حقيقية توصّل التوكن للضيف (GET .../survey-token/timeshare بس
        كان بيولّد التوكن من غير إرسال). Celery task_always_eager في التستات
        (conftest.py) يخلي .delay() يشتغل مباشرة، فبس بنتأكد من الاستجابة —
        الإرسال الفعلي (send_whatsapp_message) بيرجع True في dev بدون
        Twilio credentials (راجع core/kernel/whatsapp.py)."""
        from decimal import Decimal
        from app.modules.timeshare.models import TimeshareUnit
        from app.modules.timeshare.schemas import TimeshareContractCreate, TimeshareVisitCreate
        from app.modules.timeshare import services as ts_services

        branch = make_branch_committed(db)
        unit = TimeshareUnit(branch_id=branch.id, unit_number="A-102", unit_type="2R")
        db.add(unit); db.commit()

        contract = ts_services.create_contract(db, TimeshareContractCreate(
            branch_id=branch.id, customer_name="عميل تايم شير", room_type="2R",
            customer_phone="+201001234567",
            total_value=Decimal("120000"), down_payment=Decimal("20000"),
            installments=12, installment_period=1,
            first_installment_date=date(2026, 8, 1),
            partner_share_pct=Decimal("0"), start_date=date(2026, 7, 1),
        ), signed_by=1)
        visit = ts_services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 1), check_out=date(2026, 8, 8),
        ))

        resp = client.post(
            f"/api/v1/analytics/reviews/survey-token/timeshare/{visit.id}/send",
            params={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert resp.status_code == 202, resp.text
        assert resp.json()["queued"] is True

    def test_send_timeshare_survey_requires_auth(self, client: TestClient, db):
        resp = client.post(
            "/api/v1/analytics/reviews/survey-token/timeshare/999/send",
            params={"branch_id": 1},
        )
        assert resp.status_code == 401

    def test_send_timeshare_survey_nonexistent_visit_404(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/analytics/reviews/survey-token/timeshare/999999/send",
            params={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert resp.status_code == 404
