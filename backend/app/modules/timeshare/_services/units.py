"""app/modules/timeshare/_services/units.py — physical unit inventory
(create/update/maintenance-flag) + Family Compound chalet+studio pairs.

2026-08-03: TimeshareUnit (مخزون الوحدات الفعلي) كان بدون أي مسار
إنشاء/تعديل خالص — إضافة وحدة جديدة أو تعليمها "تحت الصيانة" مكان
ممكن غير عن طريق الداتابيز مباشرة أو app.seed. مفيش DELETE عمدًا (زي
باقي الكيانات المرجعية في المشروع — Outlet مثلاً) — تعطيل وحدة بيتم عبر
status="maintenance"، مش حذف صف عليه FK حقيقية (عقود/زيارات)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.timeshare import crud
from app.modules.timeshare.models import TimeshareUnit, TimeshareUnitPair
from app.modules.timeshare.schemas import TimeshareUnitCreate, TimeshareUnitPairCreate, TimeshareUnitUpdate


def create_unit(db: Session, data: TimeshareUnitCreate) -> TimeshareUnit:
    if crud.get_unit_by_number(db, data.branch_id, data.unit_number):
        raise ValueError(f"الوحدة '{data.unit_number}' موجودة بالفعل في هذا الفرع")
    unit = crud.create_unit(db, data)
    db.commit()
    db.refresh(unit)
    return unit


def update_unit(db: Session, unit_id: int, data: TimeshareUnitUpdate) -> TimeshareUnit:
    unit = crud.get_unit(db, unit_id)
    if not unit:
        raise ValueError(f"الوحدة {unit_id} غير موجودة")
    changes = data.model_dump(exclude_unset=True)
    new_number = changes.get("unit_number")
    if new_number and new_number != unit.unit_number:
        existing = crud.get_unit_by_number(db, unit.branch_id, new_number)
        if existing and existing.id != unit.id:
            raise ValueError(f"الوحدة '{new_number}' موجودة بالفعل في هذا الفرع")
    unit = crud.update_unit(db, unit, data)
    db.commit()
    db.refresh(unit)
    return unit


def create_unit_pair(db: Session, data: TimeshareUnitPairCreate) -> TimeshareUnitPair:
    """ربط شاليه+استوديو كزوج Family Compound معتمد — لازم قبل أي زيارة
    استحقاق فعلية لعقد سعة 6 (راجع visits._create_entitlement_pair_visit)."""
    chalet = crud.get_unit(db, data.chalet_unit_id)
    if not chalet or chalet.branch_id != data.branch_id:
        raise ValueError(f"chalet_unit_id {data.chalet_unit_id} غير موجود في هذا الفرع")
    if chalet.unit_type != "Chalet":
        raise ValueError(f"الوحدة {chalet.unit_number} ليست من نوع Chalet")
    studio = crud.get_unit(db, data.studio_unit_id)
    if not studio or studio.branch_id != data.branch_id:
        raise ValueError(f"studio_unit_id {data.studio_unit_id} غير موجود في هذا الفرع")
    if studio.unit_type != "Studio":
        raise ValueError(f"الوحدة {studio.unit_number} ليست من نوع Studio")
    if crud.get_unit_pair_by_chalet_unit_id(db, data.chalet_unit_id):
        raise ValueError(f"الوحدة {chalet.unit_number} مرتبطة بالفعل بزوج معتمد آخر")
    pair = crud.create_unit_pair(db, data)
    db.commit()
    db.refresh(pair)
    return pair


def deactivate_unit_pair(db: Session, pair_id: int) -> TimeshareUnitPair:
    """soft فقط — لا حذف حقيقي (نفس نمط TimesharePeakSeason/TimeshareMaintenanceFeeRule)."""
    pair = crud.get_unit_pair(db, pair_id)
    if not pair:
        raise ValueError(f"زوج الوحدات {pair_id} غير موجود")
    crud.deactivate_unit_pair(db, pair)
    db.commit()
    db.refresh(pair)
    return pair
