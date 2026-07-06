"""app/modules/maintenance/services.py — Business logic"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.maintenance import crud
from app.modules.maintenance.models import Asset, PreventiveSchedule, WorkOrder
from app.modules.maintenance.schemas import (
    AssetCreate, AssetUpdate,
    WorkOrderCreate, WorkOrderUpdate, WorkOrderPartCreate,
    PreventiveScheduleCreate, PreventiveScheduleUpdate,
)
from app.resort_os.timezone_utils import local_today


def _validate_assigned_to(db: Session, employee_id: int | None) -> None:
    """لو تم تحديد موظف مكلّف، لازم يكون موجود فعليًا في جدول employees.

    ⚠️ باج حقيقي كان هنا: WorkOrder.assigned_to عمود Integer عادي من غير أي
    FK (على عكس PreventiveSchedule.assigned_to اللي عليه FK حقيقي) — فتعيين
    أمر صيانة لموظف رقمه غير موجود كان بينجح بهدوء (200) من غير أي تحذير،
    والأمر يفضل "معلّق" فعليًا لأن محدّش هيشوفه في قائمة مهامه. وعلى الجانب
    التاني، PreventiveSchedule.assigned_to عليه FK فعلاً بس من غير أي تحقق
    قبله في الـ service layer — نفس الغلطة كانت بتطلع 500 خام
    ("Database operation failed") بدل رسالة واضحة. التحقق ده بيوحّد السلوك:
    رسالة عربية واضحة (400) في الحالتين، مش نجاح وهمي ولا كراش."""
    if employee_id is None:
        return
    from app.modules.hr import crud as hr_crud  # noqa: PLC0415 — تجنّب استيراد دائري

    if not hr_crud.get_employee(db, employee_id):
        raise ValueError(f"الموظف رقم {employee_id} غير موجود — لا يمكن التكليف له")


# ── Asset ─────────────────────────────────────────────────────────────

def get_asset_or_404(db: Session, asset_id: int) -> Asset:
    asset = crud.get_asset(db, asset_id)
    if not asset:
        raise ValueError(f"الأصل {asset_id} غير موجود")
    return asset


def create_asset(db: Session, data: AssetCreate) -> Asset:
    existing = crud.get_asset_by_code(db, data.code)
    if existing:
        raise ValueError(f"الكود '{data.code}' مستخدم مسبقاً")
    obj = crud.create_asset(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_asset(db: Session, asset_id: int, data: AssetUpdate) -> Asset:
    asset = get_asset_or_404(db, asset_id)
    obj = crud.update_asset(db, asset, data)
    db.commit()
    db.refresh(obj)
    return obj


def dispose_asset(db: Session, asset_id: int) -> Asset:
    asset = get_asset_or_404(db, asset_id)
    # تعطيل جميع الجداول الوقائية المرتبطة
    schedules = db.query(PreventiveSchedule).filter(
        PreventiveSchedule.asset_id == asset_id,
        PreventiveSchedule.is_active.is_(True),
    ).all()
    for s in schedules:
        s.is_active = False
    asset.status = "disposed"
    db.commit()
    db.refresh(asset)
    return asset


# ── WorkOrder ─────────────────────────────────────────────────────────

def get_wo_or_404(db: Session, order_id: int) -> WorkOrder:
    wo = crud.get_work_order(db, order_id)
    if not wo:
        raise ValueError(f"أمر الصيانة {order_id} غير موجود")
    return wo


def create_work_order(db: Session, data: WorkOrderCreate, reported_by: int) -> WorkOrder:
    if data.asset_id:
        get_asset_or_404(db, data.asset_id)
    _validate_assigned_to(db, data.assigned_to)
    wo = crud.create_work_order(db, data, reported_by)
    # تحديث حالة الأصل إلى under_maintenance إذا كانت critical
    if data.asset_id and data.priority == "critical":
        asset = crud.get_asset(db, data.asset_id)
        if asset and asset.status == "operational":
            asset.status = "under_maintenance"
    db.commit()
    db.refresh(wo)
    return wo


def update_work_order(db: Session, order_id: int, data: WorkOrderUpdate) -> WorkOrder:
    wo = get_wo_or_404(db, order_id)
    if wo.status in ("completed", "cancelled"):
        raise ValueError("لا يمكن تعديل أمر صيانة مكتمل أو ملغى")
    if data.assigned_to is not None:
        _validate_assigned_to(db, data.assigned_to)
    obj = crud.update_work_order(db, wo, data)
    db.commit()
    db.refresh(obj)
    return obj


def complete_work_order(db: Session, order_id: int) -> WorkOrder:
    wo = get_wo_or_404(db, order_id)
    if wo.status == "completed":
        raise ValueError("أمر الصيانة مكتمل مسبقاً")
    wo = crud.complete_work_order(db, wo)
    # إعادة الأصل للتشغيل إن لم يكن هناك أوامر مفتوحة أخرى
    if wo.asset_id:
        open_count = db.query(WorkOrder).filter(
            WorkOrder.asset_id == wo.asset_id,
            WorkOrder.status.in_(["open", "in_progress", "pending_parts"]),
        ).count()
        if open_count == 0:
            asset = crud.get_asset(db, wo.asset_id)
            if asset and asset.status == "under_maintenance":
                asset.status = "operational"
    # لو الأمر ده وقائي وجاي من جدول دوري، لازم نقدّم next_due — وإلا
    # generate_preventive_work_orders هيفضل يعمل أمر جديد لنفس الجدول كل يوم للأبد
    # ⚠️ local_today (مش date.today() الخام) — نفس فئة الباج المتكررة في
    # HR/PMS/KDS: date.today() بيثق في توقيت نظام تشغيل السيرفر (UTC غالبًا)
    # مش توقيت المنتجع (Africa/Cairo)، فإكمال أمر وقائي قرب منتصف الليل
    # بتوقيت القاهرة كان ممكن يسجّل last_done بتاريخ *أمس* ويزوّد next_due
    # بنفس الغلط.
    if wo.order_type == "preventive" and wo.schedule_id:
        schedule = crud.get_schedule(db, wo.schedule_id)
        if schedule:
            crud.mark_schedule_done(db, schedule, done_date=local_today(settings.TIMEZONE))
    db.commit()
    db.refresh(wo)
    return wo


def add_part_to_wo(db: Session, order_id: int, data: WorkOrderPartCreate) -> WorkOrder:
    wo = get_wo_or_404(db, order_id)
    if wo.status in ("completed", "cancelled"):
        raise ValueError("لا يمكن إضافة قطع لأمر صيانة مكتمل أو ملغى")
    crud.add_part(db, order_id, data)
    crud.recalculate_parts_cost(db, wo)
    db.commit()
    db.refresh(wo)
    return wo


# ── PreventiveSchedule ────────────────────────────────────────────────

def get_schedule_or_404(db: Session, schedule_id: int) -> PreventiveSchedule:
    s = crud.get_schedule(db, schedule_id)
    if not s:
        raise ValueError(f"الجدول الوقائي {schedule_id} غير موجود")
    return s


def create_schedule(db: Session, data: PreventiveScheduleCreate) -> PreventiveSchedule:
    get_asset_or_404(db, data.asset_id)
    _validate_assigned_to(db, data.assigned_to)
    obj = crud.create_schedule(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_schedule(db: Session, schedule_id: int, data: PreventiveScheduleUpdate) -> PreventiveSchedule:
    schedule = get_schedule_or_404(db, schedule_id)
    if data.assigned_to is not None:
        _validate_assigned_to(db, data.assigned_to)
    obj = crud.update_schedule(db, schedule, data)
    db.commit()
    db.refresh(obj)
    return obj


def generate_preventive_work_orders(db: Session, branch_id: int) -> int:
    """
    يُستدعى من Celery task — ينشئ أوامر صيانة للجداول المستحقة اليوم.
    يُرجع عدد الأوامر المُنشأة.
    """
    today = local_today(settings.TIMEZONE)
    due_schedules, _ = crud.list_schedules(
        db, branch_id, active_only=True, due_before=today, limit=500
    )
    created = 0
    for schedule in due_schedules:
        # تجنّب التكرار — تحقق من عدم وجود WO مفتوح لنفس الجدول اليوم
        existing = db.query(WorkOrder).filter(
            WorkOrder.branch_id == branch_id,
            WorkOrder.asset_id == schedule.asset_id,
            WorkOrder.order_type == "preventive",
            WorkOrder.status.in_(["open", "in_progress"]),
        ).first()
        if existing:
            continue

        wo_data = WorkOrderCreate(
            branch_id=branch_id,
            asset_id=schedule.asset_id,
            title=f"صيانة وقائية: {schedule.title}",
            order_type="preventive",
            priority="medium",
            assigned_to=schedule.assigned_to,
            scheduled_date=today,
            schedule_id=schedule.id,
        )
        crud.create_work_order(db, wo_data, reported_by=0)
        created += 1

    db.commit()
    return created
