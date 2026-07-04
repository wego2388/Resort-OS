"""
tests/test_api/test_analytics_endpoints_http.py
HTTP-level tests for the analytics read-endpoints that aggregate data from
other modules: /analytics/revenue, /occupancy, /hr, /maintenance, /crm,
/inventory, /daily-stats, /reviews (list), and /dashboard.

test_analytics_http.py already covers utilities/energy-kpi/review-insights/
survey-token+submit-review — this file covers the remaining, previously
untested cross-module aggregation endpoints.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Analytics HTTP Branch", name_ar="فرع تحليلات",
               code=f"AN-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


class TestRevenueSummary:
    def test_empty_branch_totals_zero(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get("/api/v1/analytics/revenue", params={"branch_id": branch.id}, headers=manager_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["branch_id"] == branch.id
        assert Decimal(str(body["total"])) == Decimal("0")
        assert body["restaurant"]["total"] == 0
        assert body["restaurant"]["orders"] == 0

    def test_paid_restaurant_order_counted_in_total(self, client: TestClient, db, manager_headers):
        from app.modules.restaurant.models import Order
        branch = make_branch_committed(db)
        order = Order(
            branch_id=branch.id, order_number=f"O-{uuid.uuid4().hex[:8]}", order_type="takeaway",
            status="paid", subtotal=Decimal("200.00"), total=Decimal("200.00"),
        )
        db.add(order)
        db.commit()

        resp = client.get("/api/v1/analytics/revenue", params={"branch_id": branch.id}, headers=manager_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["restaurant"]["orders"] == 1
        assert Decimal(str(body["restaurant"]["total"])) == Decimal("200.00")
        assert Decimal(str(body["total"])) == Decimal("200.00")

    def test_beach_revenue_counted_and_excludes_voided(self, client: TestClient, db, manager_headers):
        """Regression test: the beach aggregation used to reference
        BeachTransaction.visit_date/total_paid, neither of which exist on the
        model (real fields are tx_date/total_amount+vat_amount) — _safe_query
        silently swallowed the AttributeError forever, so /analytics/revenue's
        beach section (and /analytics/dashboard's) always returned None."""
        from app.modules.beach.models import BeachTransaction
        branch = make_branch_committed(db)
        db.add_all([
            BeachTransaction(branch_id=branch.id, tx_type="entry_adult", quantity=2,
                             unit_price=Decimal("100.00"), total_amount=Decimal("200.00"),
                             vat_amount=Decimal("28.00"), tx_date=date.today()),
            BeachTransaction(branch_id=branch.id, tx_type="entry_adult", quantity=1,
                             unit_price=Decimal("100.00"), total_amount=Decimal("100.00"),
                             vat_amount=Decimal("14.00"), tx_date=date.today(),
                             voided_at=datetime.utcnow(), voided_reason="test"),
        ])
        db.commit()

        resp = client.get("/api/v1/analytics/revenue", params={"branch_id": branch.id}, headers=manager_headers)
        body = resp.json()
        assert body["beach"] is not None, "beach section should never silently be None for a real branch"
        assert body["beach"]["visits"] == 1  # الملغاة مستثناة
        assert Decimal(str(body["beach"]["total"])) == Decimal("228.00")  # 200 + 28 فقط، مش الملغاة
        assert Decimal(str(body["total"])) == Decimal("228.00")

    def test_unpaid_order_excluded_from_total(self, client: TestClient, db, manager_headers):
        from app.modules.restaurant.models import Order
        branch = make_branch_committed(db)
        order = Order(
            branch_id=branch.id, order_number=f"O-{uuid.uuid4().hex[:8]}", order_type="takeaway",
            status="open", subtotal=Decimal("500.00"), total=Decimal("500.00"),
        )
        db.add(order)
        db.commit()

        resp = client.get("/api/v1/analytics/revenue", params={"branch_id": branch.id}, headers=manager_headers)
        assert resp.json()["restaurant"]["orders"] == 0

    def test_requires_manager_level(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.get("/api/v1/analytics/revenue", params={"branch_id": branch.id}, headers=waiter_headers)
        assert resp.status_code == 403


class TestOccupancySummary:
    def test_no_audit_logs_returns_none(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/analytics/occupancy",
            params={"branch_id": branch.id, "month": 6, "year": 2026},
            headers=manager_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["pms"] is None

    def test_completed_audits_average_occupancy(self, client: TestClient, db, manager_headers):
        from app.modules.pms.models import NightAuditLog
        branch = make_branch_committed(db)
        db.add_all([
            NightAuditLog(branch_id=branch.id, audit_date=date(2026, 6, 10), status="completed",
                          occupancy_pct=Decimal("80.0"), room_revenue=Decimal("1000.00")),
            NightAuditLog(branch_id=branch.id, audit_date=date(2026, 6, 11), status="completed",
                          occupancy_pct=Decimal("60.0"), room_revenue=Decimal("500.00")),
        ])
        db.commit()

        resp = client.get(
            "/api/v1/analytics/occupancy",
            params={"branch_id": branch.id, "month": 6, "year": 2026},
            headers=manager_headers,
        )
        body = resp.json()["pms"]
        assert body["nights_audited"] == 2
        assert body["avg_occupancy_pct"] == 70.0
        assert Decimal(str(body["total_room_revenue"])) == Decimal("1500.00")


class TestHRSummary:
    def test_counts_active_employees_and_last_payroll(self, client: TestClient, db, manager_headers):
        from app.modules.hr.models import Employee, PayrollRun
        branch = make_branch_committed(db)
        db.add_all([
            Employee(branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6]}", full_name="أحمد علي",
                     position="كاشير", basic_salary=Decimal("5000"), hire_date=date(2025, 1, 1), status="active"),
            Employee(branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6]}", full_name="سارة محمد",
                     position="نادل", basic_salary=Decimal("4000"), hire_date=date(2025, 1, 1), status="terminated"),
        ])
        db.add(PayrollRun(branch_id=branch.id, period_year=2026, period_month=5, status="paid",
                          total_net=Decimal("9000.00")))
        db.commit()

        resp = client.get("/api/v1/analytics/hr", params={"branch_id": branch.id}, headers=manager_headers)
        body = resp.json()
        assert body["active_employees"] == 1
        assert body["last_payroll"]["period"] == "2026-05"
        assert Decimal(str(body["last_payroll"]["total_net"])) == Decimal("9000.00")


class TestMaintenanceSummary:
    def test_counts_open_and_critical_work_orders(self, client: TestClient, db, manager_headers):
        from app.modules.maintenance.models import WorkOrder
        branch = make_branch_committed(db)
        db.add_all([
            WorkOrder(branch_id=branch.id, order_number=f"WO-{uuid.uuid4().hex[:6]}", title="تسريب مياه",
                     status="open", priority="critical"),
            WorkOrder(branch_id=branch.id, order_number=f"WO-{uuid.uuid4().hex[:6]}", title="تكييف",
                     status="in_progress", priority="medium"),
            WorkOrder(branch_id=branch.id, order_number=f"WO-{uuid.uuid4().hex[:6]}", title="دهان",
                     status="completed", priority="low"),
        ])
        db.commit()

        resp = client.get("/api/v1/analytics/maintenance", params={"branch_id": branch.id}, headers=manager_headers)
        body = resp.json()
        assert body["open_work_orders"] == 2
        assert body["critical_work_orders"] == 1


class TestCRMSummaryEndpoint:
    def test_pipeline_grouped_by_stage_excludes_won_lost(self, client: TestClient, db, manager_headers):
        from app.modules.crm.models import Customer, Opportunity
        branch = make_branch_committed(db)
        customer = Customer(branch_id=branch.id, full_name="ضيف دائم", segment="vip", source="walk_in")
        db.add(customer)
        db.commit()
        db.add_all([
            Opportunity(branch_id=branch.id, customer_id=customer.id, title="تجديد عضوية",
                       product_type="timeshare", stage="proposal", expected_value=Decimal("10000")),
            Opportunity(branch_id=branch.id, customer_id=customer.id, title="ترقية وحدة",
                       product_type="timeshare", stage="proposal", expected_value=Decimal("5000")),
            Opportunity(branch_id=branch.id, customer_id=customer.id, title="صفقة مغلقة",
                       product_type="timeshare", stage="won", expected_value=Decimal("20000")),
        ])
        db.commit()

        resp = client.get("/api/v1/analytics/crm", params={"branch_id": branch.id}, headers=manager_headers)
        body = resp.json()
        assert body["total_customers"] == 1
        proposal_stage = next(p for p in body["pipeline"] if p["stage"] == "proposal")
        assert proposal_stage["count"] == 2
        assert Decimal(str(proposal_stage["value"])) == Decimal("15000")
        assert not any(p["stage"] == "won" for p in body["pipeline"])


class TestInventoryAlerts:
    def test_low_and_out_of_stock_counts(self, client: TestClient, db, manager_headers):
        from app.modules.inventory.models import Product
        branch = make_branch_committed(db)
        db.add_all([
            Product(branch_id=branch.id, name="نافد", sku=f"SKU-{uuid.uuid4().hex[:6]}", unit="kg",
                   cost_price=Decimal("10"), current_stock=Decimal("0"), reorder_point=Decimal("5"), is_active=True),
            Product(branch_id=branch.id, name="منخفض", sku=f"SKU-{uuid.uuid4().hex[:6]}", unit="kg",
                   cost_price=Decimal("10"), current_stock=Decimal("3"), reorder_point=Decimal("5"), is_active=True),
            Product(branch_id=branch.id, name="متاح", sku=f"SKU-{uuid.uuid4().hex[:6]}", unit="kg",
                   cost_price=Decimal("10"), current_stock=Decimal("50"), reorder_point=Decimal("5"), is_active=True),
        ])
        db.commit()

        resp = client.get("/api/v1/analytics/inventory", params={"branch_id": branch.id}, headers=manager_headers)
        body = resp.json()
        assert body["out_of_stock_count"] == 1
        assert body["low_stock_count"] == 2  # نافد + منخفض (كلاهما current_stock <= reorder_point)


class TestDailyStatsEndpoint:
    def test_no_row_returns_message(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/analytics/daily-stats",
            params={"branch_id": branch.id, "stat_date": "2026-01-01"},
            headers=manager_headers,
        )
        body = resp.json()
        assert body["stat_date"] == "2026-01-01"
        assert "message" in body

    def test_existing_row_returns_full_stats(self, client: TestClient, db, manager_headers):
        from app.modules.analytics.models import DailyStats
        branch = make_branch_committed(db)
        db.add(DailyStats(
            branch_id=branch.id, stat_date=date(2026, 6, 15),
            occupancy_pct=Decimal("75.5"), adr=Decimal("450.00"), revpar=Decimal("340.00"),
            room_revenue=Decimal("9000.00"), beach_visitors=42, beach_revenue=Decimal("3000.00"),
            restaurant_covers=80, restaurant_revenue=Decimal("6000.00"), cafe_revenue=Decimal("1200.00"),
            total_revenue=Decimal("19200.00"),
        ))
        db.commit()

        resp = client.get(
            "/api/v1/analytics/daily-stats",
            params={"branch_id": branch.id, "stat_date": "2026-06-15"},
            headers=manager_headers,
        )
        body = resp.json()
        assert body["occupancy_pct"] == 75.5
        assert body["beach_visitors"] == 42
        assert body["total_revenue"] == 19200.00


class TestReviewsListEndpoint:
    def test_lists_only_published_with_avg_rating(self, client: TestClient, db, manager_headers):
        from app.modules.analytics.models import GuestReview
        branch = make_branch_committed(db)
        db.add_all([
            GuestReview(branch_id=branch.id, guest_name="نورا", overall_rating=5, source="direct",
                       is_published=True, reviewed_at=date(2026, 6, 1)),
            GuestReview(branch_id=branch.id, guest_name="كريم", overall_rating=3, source="google",
                       is_published=True, reviewed_at=date(2026, 6, 2)),
            GuestReview(branch_id=branch.id, guest_name="مخفي", overall_rating=1, source="direct",
                       is_published=False, reviewed_at=date(2026, 6, 3)),
        ])
        db.commit()

        resp = client.get("/api/v1/analytics/reviews", params={"branch_id": branch.id}, headers=manager_headers)
        body = resp.json()
        assert body["total"] == 2
        assert body["avg_rating"] == 4.0
        assert all(r["guest_name"] != "مخفي" for r in body["items"])

    def test_filters_by_source(self, client: TestClient, db, manager_headers):
        from app.modules.analytics.models import GuestReview
        branch = make_branch_committed(db)
        db.add_all([
            GuestReview(branch_id=branch.id, guest_name="أ", overall_rating=5, source="direct",
                       is_published=True, reviewed_at=date(2026, 6, 1)),
            GuestReview(branch_id=branch.id, guest_name="ب", overall_rating=4, source="google",
                       is_published=True, reviewed_at=date(2026, 6, 2)),
        ])
        db.commit()

        resp = client.get(
            "/api/v1/analytics/reviews",
            params={"branch_id": branch.id, "source": "google"},
            headers=manager_headers,
        )
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["guest_name"] == "ب"

    def test_filters_by_timeshare_visit_id_includes_unpublished(self, client: TestClient, db, manager_headers):
        """بروفايل عميل تايم شير محتاج يشوف كل تقييمات الزيارة (حتى الغير
        منشورة، rating <= 2) — الفلترة العامة (من غير فلتر) لسه بتفلتر
        is_published فقط، فده لازم يكون سلوك إضافي مش تغيير كاسر."""
        from decimal import Decimal as _D
        from app.modules.analytics.models import GuestReview
        from app.modules.timeshare.models import TimeshareUnit
        from app.modules.timeshare.schemas import TimeshareContractCreate, TimeshareVisitCreate
        from app.modules.timeshare import services as ts_services

        branch = make_branch_committed(db)
        unit1 = TimeshareUnit(branch_id=branch.id, unit_number="A-101", unit_type="2R")
        unit2 = TimeshareUnit(branch_id=branch.id, unit_number="A-102", unit_type="2R")
        db.add_all([unit1, unit2]); db.commit()

        contract = ts_services.create_contract(db, TimeshareContractCreate(
            branch_id=branch.id, customer_name="عميل تايم شير", room_type="2R",
            total_value=_D("120000"), down_payment=_D("20000"),
            installments=12, installment_period=1,
            first_installment_date=date(2026, 8, 1),
            partner_share_pct=_D("0"), start_date=date(2026, 7, 1),
        ), signed_by=1)
        visit1 = ts_services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 8, 1), check_out=date(2026, 8, 8),
        ))
        visit2 = ts_services.create_visit(db, TimeshareVisitCreate(
            branch_id=branch.id, contract_id=contract.id,
            check_in=date(2026, 9, 1), check_out=date(2026, 9, 8),
        ))

        db.add_all([
            GuestReview(branch_id=branch.id, guest_name="سيف", overall_rating=1, source="checkout_survey",
                       is_published=False, reviewed_at=date(2026, 6, 1), timeshare_visit_id=visit1.id),
            GuestReview(branch_id=branch.id, guest_name="آخر", overall_rating=5, source="direct",
                       is_published=True, reviewed_at=date(2026, 6, 2), timeshare_visit_id=visit2.id),
        ])
        db.commit()

        resp = client.get(
            "/api/v1/analytics/reviews",
            params={"branch_id": branch.id, "timeshare_visit_id": visit1.id},
            headers=manager_headers,
        )
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["guest_name"] == "سيف"  # غير منشور لكن ظهر لأنه فلتر محدد


class TestFullDashboard:
    def test_dashboard_aggregates_all_sections(self, client: TestClient, db, manager_headers):
        from app.modules.hr.models import Employee
        branch = make_branch_committed(db)
        db.add(Employee(branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6]}", full_name="محمد",
                        position="مدير", basic_salary=Decimal("8000"), hire_date=date(2025, 1, 1), status="active"))
        db.commit()

        resp = client.get("/api/v1/analytics/dashboard", params={"branch_id": branch.id}, headers=manager_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["branch_id"] == branch.id
        assert body["as_of"] == str(date.today())
        assert body["hr"]["active_employees"] == 1
        assert body["revenue_30d"] is not None
        assert body["revenue_30d"]["total"] == 0.0
        assert body["revenue_30d"]["beach"] == 0.0  # ثبت إن قسم الشاطئ مش None (راجع باج visit_date)
