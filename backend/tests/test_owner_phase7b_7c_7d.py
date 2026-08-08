"""
tests/test_owner_phase7b_7c_7d.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — Tests للمراحل 7b + 7c + 7d + 7e
Decision 0004 §7b: shift history, date range params
Decision 0004 §7c: HR summary — schema لا يحتوي بيانات محظورة
Decision 0004 §7d: discount analytics — لا هاتف/email لأعضاء المجموعات
Decision 0004 §7e: performance breakdown field
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.owner.schemas import (
    DiscountAnalyticsResponse,
    HREmployeeRow,
    HRSummaryResponse,
    PeriodComparison,
    PeriodSnapshot,
    PerformanceBreakdown,
    ShiftHistoryResponse,
)


# ══════════════════════════════════════════════════════════════════════
# Phase 7b — Shift History schema
# ══════════════════════════════════════════════════════════════════════

class TestShiftHistorySchema:
    def test_shift_history_response_shape(self):
        """ShiftHistoryResponse يحتوي الحقول المطلوبة."""
        resp = ShiftHistoryResponse(
            branch_id=1,
            days=7,
            shifts=[],
            computed_at=datetime.utcnow(),
        )
        assert resp.branch_id == 1
        assert resp.days == 7
        assert resp.shifts == []

    def test_shift_history_only_closed(self):
        """الـ endpoint يُعيد ورديات مغلقة فقط — is_closed يجب أن تكون True
        في ShiftHistoryItem (لا ShiftMonitorItem التي تتضمن مفتوحة)."""
        # نتحقق إن ShiftHistoryItem ليست لها is_closed field —
        # لأن بطبيعتها كلها مغلقة
        from app.modules.owner.schemas import ShiftHistoryItem
        fields = ShiftHistoryItem.model_fields
        # ShiftHistoryItem لازم يكون فيها closed_at وليس is_closed (لأنها دائماً مغلقة)
        assert "closed_at" in fields
        assert "is_closed" not in fields

    def test_date_range_params_accepted_by_router(self):
        """الـ endpoints التي تقبل date_from/date_to تشتغل بدون params."""
        from app.modules.owner.api.router import router
        routes_with_date = [
            "owner_sales",
            "owner_beach_performance",
            "owner_channel_analytics",
            "owner_expense_analytics",
            "owner_procurement_analytics",
            "owner_discount_analytics",
        ]
        route_names = {r.name for r in router.routes if hasattr(r, "name")}
        for name in routes_with_date:
            assert name in route_names, f"Route {name!r} غير موجود"

    def test_shift_history_route_exists(self):
        """owner_shifts_history route موجود."""
        from app.modules.owner.api.router import router
        names = {r.name for r in router.routes if hasattr(r, "name")}
        assert "owner_shifts_history" in names

    def test_shift_history_is_not_in_write_allowlist(self):
        """owner_shifts_history هو GET — لا يحتاج allowlist (يُمرَّر تلقائياً)."""
        from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST
        # GET endpoints لا تُضاف للـ allowlist — الـ policy تسمح بكل GETs
        assert "owner_shifts_history" not in OWNER_WRITE_ALLOWLIST


# ══════════════════════════════════════════════════════════════════════
# Phase 7c — HR Summary schema
# ══════════════════════════════════════════════════════════════════════

class TestHRSummarySchema:
    def test_hr_employee_row_forbidden_fields(self):
        """HREmployeeRow لا يحتوي أي من الحقول المحظورة (Decision 0004 §7c)."""
        forbidden = {"national_id", "employee_si", "monthly_tax", "phone", "email", "basic_salary"}
        fields = set(HREmployeeRow.model_fields.keys())
        overlap = forbidden & fields
        assert not overlap, f"حقول محظورة موجودة في HREmployeeRow: {overlap}"

    def test_hr_summary_response_shape(self):
        """HRSummaryResponse يحتوي الحقول المطلوبة."""
        resp = HRSummaryResponse(
            branch_id=1,
            employees=[],
            active_count=0,
            on_leave_count=0,
            total_net_payroll=Decimal("0"),
            period_year=2026,
            period_month=8,
            computed_at=datetime.utcnow(),
        )
        assert resp.branch_id == 1
        assert resp.total_net_payroll == Decimal("0")

    def test_employee_payroll_summary_forbidden_fields(self):
        """EmployeePayrollSummary لا يحتوي employee_si أو monthly_tax."""
        from app.modules.owner.schemas import EmployeePayrollSummary
        forbidden = {"employee_si", "monthly_tax", "national_id"}
        fields = set(EmployeePayrollSummary.model_fields.keys())
        overlap = forbidden & fields
        assert not overlap, f"حقول محظورة في EmployeePayrollSummary: {overlap}"

    def test_employee_payroll_required_fields(self):
        """EmployeePayrollSummary يحتوي الحقول المطلوبة."""
        from app.modules.owner.schemas import EmployeePayrollSummary
        required = {"gross_salary", "net_salary", "penalty_deduction", "advance_deduction"}
        fields = set(EmployeePayrollSummary.model_fields.keys())
        missing = required - fields
        assert not missing, f"حقول مطلوبة مفقودة: {missing}"

    def test_hr_route_exists(self):
        """owner_hr_summary route موجود."""
        from app.modules.owner.api.router import router
        names = {r.name for r in router.routes if hasattr(r, "name")}
        assert "owner_hr_summary" in names


# ══════════════════════════════════════════════════════════════════════
# Phase 7d — Discount Analytics schema
# ══════════════════════════════════════════════════════════════════════

class TestDiscountAnalyticsSchema:
    def test_customer_group_member_forbidden_fields(self):
        """CustomerGroupMember لا يحتوي هاتف/email/national_id (Decision 0004 §7d)."""
        from app.modules.owner.schemas import CustomerGroupMember
        forbidden = {"phone", "email", "national_id", "birthday", "notes", "blacklisted"}
        fields = set(CustomerGroupMember.model_fields.keys())
        overlap = forbidden & fields
        assert not overlap, f"حقول محظورة في CustomerGroupMember: {overlap}"

    def test_customer_group_member_allowed_fields(self):
        """CustomerGroupMember يحتوي الاسم + الفواتير + المبيعات فقط."""
        from app.modules.owner.schemas import CustomerGroupMember
        required = {"customer_id", "full_name", "invoice_count", "total_sales"}
        fields = set(CustomerGroupMember.model_fields.keys())
        missing = required - fields
        assert not missing, f"حقول مطلوبة مفقودة: {missing}"

    def test_discount_analytics_response_shape(self):
        """DiscountAnalyticsResponse يحتوي الحقول المطلوبة."""
        resp = DiscountAnalyticsResponse(
            period_from="2026-08-01",
            period_to="2026-08-08",
            total_revenue=Decimal("10000"),
            total_discount=Decimal("500"),
            discount_pct_of_revenue=Decimal("5.0"),
            discount_types=[],
            manual_per_cashier=[],
            customer_groups=[],
            computed_at=datetime.utcnow(),
        )
        assert resp.total_discount == Decimal("500")
        assert resp.customer_groups == []

    def test_discount_route_exists(self):
        """owner_discount_analytics route موجود."""
        from app.modules.owner.api.router import router
        names = {r.name for r in router.routes if hasattr(r, "name")}
        assert "owner_discount_analytics" in names

    def test_no_walk_in_customers_in_schema(self):
        """CustomerGroupDiscountRow يحتوي group_id — لا يمكن إنشاء row بدون group."""
        from app.modules.owner.schemas import CustomerGroupDiscountRow
        fields = set(CustomerGroupDiscountRow.model_fields.keys())
        assert "group_id" in fields
        assert "group_name" in fields
        # تأكد إن customer_id الـ standalone مش في الـ row (فقط في members)
        assert "customer_id" not in fields

    def test_manual_discount_per_cashier_is_aggregate(self):
        """ManualDiscountPerCashier تحتوي aggregate وليس raw transactions."""
        from app.modules.owner.schemas import ManualDiscountPerCashier
        fields = set(ManualDiscountPerCashier.model_fields.keys())
        # aggregate fields
        assert "total_manual_discount" in fields
        assert "order_count" in fields
        # لا raw transaction details
        assert "order_id" not in fields
        assert "created_at" not in fields


# ══════════════════════════════════════════════════════════════════════
# Phase 7e — Performance Breakdown schema
# ══════════════════════════════════════════════════════════════════════

class TestPerformanceBreakdown:
    def test_breakdown_all_nullable(self):
        """PerformanceBreakdown كل fields اختيارية — None لو البيانات مش متاحة."""
        bd = PerformanceBreakdown()
        assert bd.dining_revenue is None
        assert bd.beach_revenue is None
        assert bd.rooms_revenue is None
        assert bd.other_revenue is None

    def test_breakdown_with_values(self):
        """PerformanceBreakdown يقبل Decimal values."""
        bd = PerformanceBreakdown(
            dining_revenue=Decimal("5000"),
            beach_revenue=Decimal("3000"),
            rooms_revenue=None,
            other_revenue=Decimal("200"),
        )
        assert bd.dining_revenue == Decimal("5000")
        assert bd.rooms_revenue is None

    def test_period_comparison_has_breakdown(self):
        """PeriodComparison يحتوي breakdown field اختياري."""
        fields = PeriodComparison.model_fields
        assert "breakdown" in fields
        # اختياري — default None
        snap = PeriodSnapshot(
            date_from=date.today(),
            date_to=date.today(),
            label="اليوم",
            total_revenue=Decimal("0"),
            total_expense=Decimal("0"),
            net_income=Decimal("0"),
            is_provisional=True,
            computed_at=datetime.utcnow(),
        )
        comp = PeriodComparison(
            current=snap, prior=snap,
            revenue_delta=Decimal("0"), revenue_pct=None,
            expense_delta=Decimal("0"), expense_pct=None,
            net_income_delta=Decimal("0"), net_income_pct=None,
        )
        assert comp.breakdown is None  # default

    def test_period_comparison_with_breakdown(self):
        """PeriodComparison يقبل breakdown غير None."""
        snap = PeriodSnapshot(
            date_from=date.today(),
            date_to=date.today(),
            label="الشهر",
            total_revenue=Decimal("8000"),
            total_expense=Decimal("3000"),
            net_income=Decimal("5000"),
            is_provisional=False,
            computed_at=datetime.utcnow(),
        )
        bd = PerformanceBreakdown(
            dining_revenue=Decimal("5000"),
            beach_revenue=Decimal("3000"),
        )
        comp = PeriodComparison(
            current=snap, prior=snap,
            revenue_delta=Decimal("0"), revenue_pct=Decimal("0"),
            expense_delta=Decimal("0"), expense_pct=Decimal("0"),
            net_income_delta=Decimal("0"), net_income_pct=Decimal("0"),
            breakdown=bd,
        )
        assert comp.breakdown is not None
        assert comp.breakdown.dining_revenue == Decimal("5000")
        assert comp.breakdown.rooms_revenue is None


# ══════════════════════════════════════════════════════════════════════
# Logout في OWNER_WRITE_ALLOWLIST
# ══════════════════════════════════════════════════════════════════════

class TestLogoutInAllowlist:
    def test_logout_in_write_allowlist(self):
        """logout موجود في OWNER_WRITE_ALLOWLIST (Decision 0004 §7e)."""
        from app.modules.owner.owner_policy import OWNER_WRITE_ALLOWLIST
        assert "logout" in OWNER_WRITE_ALLOWLIST


# ══════════════════════════════════════════════════════════════════════
# No AI — تأكيد إن owner module لا يستدعي أي LLM
# ══════════════════════════════════════════════════════════════════════

class TestNoAIInOwnerModule:
    def test_no_ai_calls_in_owner_services(self):
        """services.py لا يحتوي أي import أو استدعاء فعلي لـ Gemini أو LLM."""
        import re
        with open("app/modules/owner/services.py", "r") as f:
            content = f.read()
        # نبحث عن import statements أو API calls فعلية — ليس تعليقات
        ai_import_patterns = [
            r"^import\s+.*gemini",
            r"^from\s+.*gemini",
            r"^import\s+.*openai",
            r"^from\s+.*openai",
            r"^import\s+.*anthropic",
            r"^from\s+.*anthropic",
            r"^import\s+.*langchain",
            r"^from\s+.*langchain",
            r"GenerativeModel\s*\(",
            r"openai\.ChatCompletion",
            r"anthropic\.Anthropic",
        ]
        for pattern in ai_import_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
            assert not matches, f"وُجد استدعاء AI فعلي '{pattern}' في services.py"

    def test_no_ai_calls_in_owner_router(self):
        """router.py لا يحتوي أي import لـ AI."""
        import re
        with open("app/modules/owner/api/router.py", "r") as f:
            content = f.read()
        ai_import_patterns = [
            r"^import\s+.*gemini",
            r"^from\s+.*gemini",
            r"^import\s+.*openai",
            r"^from\s+.*openai",
            r"GenerativeModel\s*\(",
        ]
        for pattern in ai_import_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
            assert not matches, f"وُجد AI import في router.py: '{pattern}'"
