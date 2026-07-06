"""
tests/test_api/test_maintenance.py
Integration tests for maintenance module.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.modules.maintenance.models import Asset, WorkOrder
from app.modules.maintenance.schemas import AssetCreate, WorkOrderCreate
from app.modules.maintenance import crud, services


@pytest.fixture
def branch(db: Session):
    import uuid
    from app.modules.core.models import Branch
    b = Branch(name="Test", name_ar="اختبار", code=f"MNT-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.flush()
    return b


@pytest.fixture
def employee(db: Session, branch):
    """موظف حقيقي — لاختبار تكليف أوامر/جداول الصيانة لموظف موجود فعلاً."""
    import uuid
    from datetime import date
    from app.modules.hr.models import Employee
    emp = Employee(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name="فني صيانة اختباري", position="فني صيانة", department="الصيانة",
        basic_salary=5000, hire_date=date.today(), status="active",
    )
    db.add(emp)
    db.flush()
    return emp


@pytest.fixture
def asset(db: Session, branch):
    import uuid
    data = AssetCreate(
        branch_id=branch.id, name="مكيف رقم 101",
        code=f"AST-{uuid.uuid4().hex[:6].upper()}", category="hvac", location="الطابق الأول",
    )
    return services.create_asset(db, data)


class TestAsset:

    def test_create_asset(self, db, branch):
        import uuid
        data = AssetCreate(
            branch_id=branch.id, name="مضخة مياه",
            code=f"AST-{uuid.uuid4().hex[:6].upper()}", category="plumbing",
        )
        asset = services.create_asset(db, data)
        assert asset.id is not None
        assert asset.status == "operational"
        assert asset.category == "plumbing"

    def test_duplicate_code_raises(self, db, branch, asset):
        data = AssetCreate(
            branch_id=branch.id, name="أصل مكرر",
            code=asset.code, category="other",  # نفس كود الـ fixture
        )
        with pytest.raises(ValueError, match="مستخدم مسبقاً"):
            services.create_asset(db, data)

    def test_dispose_asset(self, db, asset):
        disposed = services.dispose_asset(db, asset.id)
        assert disposed.status == "disposed"

    def test_get_asset_404(self, db):
        with pytest.raises(ValueError):
            services.get_asset_or_404(db, 9999)


class TestWorkOrder:

    def test_create_work_order(self, db, branch, asset):
        data = WorkOrderCreate(
            branch_id=branch.id, asset_id=asset.id,
            title="تسريب مياه في الحمام",
            order_type="corrective", priority="high",
        )
        wo = services.create_work_order(db, data, reported_by=1)
        assert wo.id is not None
        assert wo.status == "open"
        assert wo.order_number.startswith("WO-")

    def test_critical_work_order_freezes_asset(self, db, branch, asset):
        data = WorkOrderCreate(
            branch_id=branch.id, asset_id=asset.id,
            title="عطل كامل", order_type="corrective", priority="critical",
        )
        services.create_work_order(db, data, reported_by=1)
        db.refresh(asset)
        assert asset.status == "under_maintenance"

    def test_complete_work_order_restores_asset(self, db, branch, asset):
        wo_data = WorkOrderCreate(
            branch_id=branch.id, asset_id=asset.id,
            title="صيانة", order_type="corrective", priority="critical",
        )
        wo = services.create_work_order(db, wo_data, reported_by=1)
        services.complete_work_order(db, wo.id)
        db.refresh(asset)
        assert asset.status == "operational"

    def test_cannot_complete_twice(self, db, branch, asset):
        wo_data = WorkOrderCreate(
            branch_id=branch.id, title="اختبار",
            order_type="corrective", priority="low",
        )
        wo = services.create_work_order(db, wo_data, reported_by=1)
        services.complete_work_order(db, wo.id)
        with pytest.raises(ValueError, match="مكتمل"):
            services.complete_work_order(db, wo.id)


class TestAssignedToValidation:
    """⚠️ باج حقيقي كان هنا: WorkOrder.assigned_to عمود Integer عادي من غير
    أي FK (بعكس PreventiveSchedule.assigned_to اللي عليه FK حقيقي) — تعيين
    أمر صيانة لموظف رقمه غير موجود كان ينجح بهدوء (200) من غير أي تحذير.
    وفي المقابل، PreventiveSchedule كان بيطيح IntegrityError خام (500) بدل
    رسالة واضحة. services._validate_assigned_to وحّدت السلوك: ValueError
    (→ 400 في الراوتر) في الحالتين، ونجاح طبيعي لو الموظف حقيقي."""

    def test_create_work_order_rejects_nonexistent_employee(self, db, branch, asset):
        data = WorkOrderCreate(
            branch_id=branch.id, asset_id=asset.id, title="تسريب مياه",
            assigned_to=999999,
        )
        with pytest.raises(ValueError, match="غير موجود"):
            services.create_work_order(db, data, reported_by=1)

    def test_create_work_order_accepts_real_employee(self, db, branch, asset, employee):
        data = WorkOrderCreate(
            branch_id=branch.id, asset_id=asset.id, title="تسريب مياه",
            assigned_to=employee.id,
        )
        wo = services.create_work_order(db, data, reported_by=1)
        assert wo.assigned_to == employee.id

    def test_update_work_order_rejects_nonexistent_employee(self, db, branch, asset):
        from app.modules.maintenance.schemas import WorkOrderUpdate
        wo = services.create_work_order(
            db, WorkOrderCreate(branch_id=branch.id, asset_id=asset.id, title="عطل"), reported_by=1,
        )
        with pytest.raises(ValueError, match="غير موجود"):
            services.update_work_order(db, wo.id, WorkOrderUpdate(assigned_to=999999))

    def test_create_schedule_rejects_nonexistent_employee_cleanly(self, db, branch, asset):
        """قبل الإصلاح، ده كان بيطيح IntegrityError خام (500) لأن الـ FK بيتحقق
        على مستوى الداتابيز بس من غير تحقق قبله في service layer."""
        from app.modules.maintenance.schemas import PreventiveScheduleCreate
        from datetime import date, timedelta
        data = PreventiveScheduleCreate(
            branch_id=branch.id, asset_id=asset.id, title="صيانة دورية",
            frequency_days=30, next_due=date.today() + timedelta(days=30),
            assigned_to=999999,
        )
        with pytest.raises(ValueError, match="غير موجود"):
            services.create_schedule(db, data)

    def test_create_schedule_accepts_real_employee(self, db, branch, asset, employee):
        from app.modules.maintenance.schemas import PreventiveScheduleCreate
        from datetime import date, timedelta
        data = PreventiveScheduleCreate(
            branch_id=branch.id, asset_id=asset.id, title="صيانة دورية",
            frequency_days=30, next_due=date.today() + timedelta(days=30),
            assigned_to=employee.id,
        )
        schedule = services.create_schedule(db, data)
        assert schedule.assigned_to == employee.id


class TestPreventiveSchedule:

    def test_generate_preventive_work_orders(self, db, branch, asset):
        from datetime import date, timedelta
        from app.modules.maintenance.schemas import PreventiveScheduleCreate

        sched_data = PreventiveScheduleCreate(
            branch_id=branch.id, asset_id=asset.id,
            title="تنظيف دوري", frequency_days=30,
            next_due=date.today() - timedelta(days=1),  # مستحق بالأمس
        )
        services.create_schedule(db, sched_data)
        count = services.generate_preventive_work_orders(db, branch.id)
        assert count == 1

    def test_no_duplicate_preventive_orders(self, db, branch, asset):
        from datetime import date, timedelta
        from app.modules.maintenance.schemas import PreventiveScheduleCreate

        sched_data = PreventiveScheduleCreate(
            branch_id=branch.id, asset_id=asset.id,
            title="تنظيف", frequency_days=30,
            next_due=date.today() - timedelta(days=1),
        )
        services.create_schedule(db, sched_data)
        first  = services.generate_preventive_work_orders(db, branch.id)
        second = services.generate_preventive_work_orders(db, branch.id)
        assert first == 1
        assert second == 0  # موجود مسبقاً

    def test_completing_preventive_wo_advances_schedule(self, db, branch, asset):
        """لو خلّصنا أمر الصيانة الوقائي من غير ما نقدّم next_due، اليوم اللي بعده
        هيتعمل أمر جديد لنفس الجدول من الأول — ده الباج اللي كان موجود واتصلح."""
        from datetime import date, timedelta
        from app.modules.maintenance.schemas import PreventiveScheduleCreate

        sched_data = PreventiveScheduleCreate(
            branch_id=branch.id, asset_id=asset.id,
            title="فحص دوري", frequency_days=30,
            next_due=date.today() - timedelta(days=1),
        )
        schedule = services.create_schedule(db, sched_data)

        count = services.generate_preventive_work_orders(db, branch.id)
        assert count == 1
        wo = db.query(WorkOrder).filter(WorkOrder.branch_id == branch.id).first()
        assert wo.schedule_id == schedule.id

        services.complete_work_order(db, wo.id)
        db.refresh(schedule)
        assert schedule.last_done == date.today()
        assert schedule.next_due == date.today() + timedelta(days=30)

        # مفيش تكرار: next_due بقى في المستقبل، فمفروض معاد إنشاء أوامر جديدة
        again = services.generate_preventive_work_orders(db, branch.id)
        assert again == 0
