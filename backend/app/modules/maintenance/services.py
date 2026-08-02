"""app/modules/maintenance/services.py — Business logic"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.inventory.services import InventoryConcurrencyError
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


def _release_asset_if_no_open_orders(db: Session, asset_id: int | None) -> None:
    """لو مفيش أوامر صيانة مفتوحة تانية على نفس الأصل، رجّعه operational.
    مُستخدمة من أي مسار بيقفل أمر صيانة نهائيًا (completed أو cancelled) —
    ⚠️ باج حقيقي اتصلح (2026-08-02): كانت الدالة دي جوه complete_work_order
    بس، يعني أمر صيانة critical لو اتلغى (cancelled) بدل ما يتقفل (completed)
    عبر PATCH العادي، الأصل كان يفضل under_maintenance للأبد — مفيش أي مسار
    تاني بيعيد فحص الأوامر المفتوحة غير complete_work_order نفسها."""
    if not asset_id:
        return
    open_count = db.query(WorkOrder).filter(
        WorkOrder.asset_id == asset_id,
        WorkOrder.status.in_(["open", "in_progress", "pending_parts"]),
    ).count()
    if open_count == 0:
        asset = crud.get_asset(db, asset_id)
        if asset and asset.status == "under_maintenance":
            asset.status = "operational"


def update_work_order(db: Session, order_id: int, data: WorkOrderUpdate) -> WorkOrder:
    """⚠️ باج حقيقي اتصلح (2026-08-02): PATCH العادي (get_employee_user،
    مستوى 20) كان بيقبل status="completed" مباشرة من غير أي فحص — بيتخطى
    صلاحية POST .../complete المخصصة (مدير+، مستوى 60) وكل الأثر الجانبي
    اللي complete_work_order() بيعمله (تحرير الأصل من under_maintenance،
    تقديم next_due لجدول الصيانة الوقائية، تسجيل completed_at). أمر
    الصيانة كان يفضل "مكتمل" شكليًا بس من غير أي من ده أبدًا."""
    wo = get_wo_or_404(db, order_id)
    if wo.status in ("completed", "cancelled"):
        raise ValueError("لا يمكن تعديل أمر صيانة مكتمل أو ملغى")
    if data.status == "completed":
        raise ValueError("استخدم POST /work-orders/{id}/complete لإنهاء الأمر — مش التعديل العادي")
    if data.assigned_to is not None:
        _validate_assigned_to(db, data.assigned_to)
    obj = crud.update_work_order(db, wo, data)
    if data.status == "cancelled":
        _release_asset_if_no_open_orders(db, obj.asset_id)
    db.commit()
    db.refresh(obj)
    return obj


def complete_work_order(db: Session, order_id: int) -> WorkOrder:
    wo = get_wo_or_404(db, order_id)
    if wo.status == "completed":
        raise ValueError("أمر الصيانة مكتمل مسبقاً")
    wo = crud.complete_work_order(db, wo)
    _release_asset_if_no_open_orders(db, wo.asset_id)
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


def add_part_to_wo(db: Session, order_id: int, data: WorkOrderPartCreate, added_by: int = 0) -> WorkOrder:
    """إضافة قطعة غيار لأمر الصيانة.

    لو data.product_id محدد:
      - بيجيب المنتج من inventory ويملأ part_name + unit_cost تلقائياً
      - بيخصم الكمية من current_stock (allow_negative=True لنفس سياسة المطعم/الكافيه)
      - بيسجّل حركة مخزنية من نوع "out" مع reference = رقم أمر الصيانة
    لو مفيش product_id: قطعة خارجية — part_name + unit_cost يدوي بدون خصم.
    """
    wo = get_wo_or_404(db, order_id)
    if wo.status in ("completed", "cancelled"):
        raise ValueError("لا يمكن إضافة قطع لأمر صيانة مكتمل أو ملغى")

    if data.product_id:
        # ⚠️ باج حقيقي كان هنا (اتصلح 2026-07-28، اتأكد بريبرو حي: الميزة دي
        # كانت 400 دايمًا في كل مرة تُستخدم): (١) product.unit_cost مش عمود
        # موجود على Product خالص (الاسم الصح cost_price)، (٢) StockMovementCreate
        # كانت بتتبنى بـmovement_type="out" (غير موجود في الـpattern المسموح)
        # ومن غير warehouse_id/moved_at الإجباريين، و"reference" مش حقل
        # حقيقي (reference_type/reference_id هما الصح). الحل: استخدام
        # inv_svc.consume_stock — نفس الدالة اللي dining بيستخدمها لخصم
        # مكوّنات الوصفات، بتعمل القفل الصحيح وتقرا cost_price من النسخة
        # المقفولة، وترحّل قيد COGS تلقائيًا (كان مفقود هنا تمامًا من الأول).
        try:
            from app.modules.inventory import crud as inv_crud   # noqa: PLC0415
            from app.modules.inventory import services as inv_svc  # noqa: PLC0415

            product = inv_crud.get_product(db, data.product_id)
            if not product:
                raise ValueError(f"المنتج {data.product_id} غير موجود في المخزن")
            if product.branch_id != wo.branch_id:
                raise ValueError("المنتج يعود لفرع مختلف عن أمر الصيانة")
            if not product.warehouse_id:
                raise ValueError(f"المنتج {data.product_id} من غير مخزن مرتبط")
            warehouse = inv_crud.get_warehouse(db, product.warehouse_id)
            if not warehouse or warehouse.branch_id != wo.branch_id:
                raise ValueError(f"مخزن المنتج {data.product_id} غير صالح لفرع أمر الصيانة")

            # اجلب part_name + unit_cost من المنتج لو مش محدد يدوياً
            resolved_name = data.part_name or product.name
            resolved_cost = data.unit_cost if data.unit_cost > 0 else (product.cost_price or Decimal("0"))

            # اخصم من المخزن (نفس دالة استهلاك وصفات dining بالظبط)
            inv_svc.consume_stock(
                db,
                branch_id=wo.branch_id,
                product_id=data.product_id,
                warehouse_id=product.warehouse_id,
                quantity=data.quantity,
                reference_type="maintenance_work_order",
                reference_id=wo.id,
                moved_by=added_by,
                allow_negative=True,   # نفس سياسة المطعم: رصيد سالب مؤقت أفضل من إيقاف العمل
                commit=False,          # نفس commit موحّد واحد في نهاية الدالة تحت
            )

            # أنشئ النسخة المعدّلة من data
            from app.modules.maintenance.schemas import WorkOrderPartCreate as WPC  # noqa: PLC0415
            data = WPC(
                product_id=data.product_id,
                part_name=resolved_name,
                part_number=data.part_number or product.sku,
                quantity=data.quantity,
                unit_cost=resolved_cost,
            )
        except ValueError:
            raise
        except InventoryConcurrencyError:
            raise
        except Exception as exc:
            raise ValueError(f"فشل خصم المخزن للمنتج {data.product_id}: {exc}") from exc

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
