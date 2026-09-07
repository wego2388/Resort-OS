"""app/modules/timeshare/_services/visits.py — real physical-unit
allocation for a contract's stay (dedicated Studio/Chalet, or a Family
Compound chalet+studio pair for capacity-6 contracts)."""
from __future__ import annotations

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.timeshare import crud
from app.modules.timeshare.models import TimeshareVisit
from app.modules.timeshare.schemas import TimeshareVisitCreate, TimeshareVisitUpdate

from ._exceptions import VisitConflictError
from .contracts import get_contract_or_404


def create_visit(db: Session, data: TimeshareVisitCreate) -> TimeshareVisit:
    """يخصّص وحدة ملكية جزئية فعلية للزيارة (real allocation، مش مجرد سطر تاريخ
    بلا أي حجز حقيقي) — مع منع تعارض حجز حقيقي (double-booking) على نفس
    الوحدة، بنفس منطق date-overlap المستخدم في pms.crud.get_available_rooms.

    ⚠️ باج تزامن حقيقي كان هنا: التحقق من التعارض (has_overlapping_visit/
    find_available_unit) وعملية الـ INSERT ما كانوش محميين بأي SELECT FOR
    UPDATE NOWAIT — يعني لو حصلت محاولتين حقيقيتين متزامنتين لتخصيص نفس
    الوحدة لنفس الفترة (نفس race condition اللي pms.services.create_booking
    بيمنعها بالظبط بقفل صف الغرفة)، الاتنين كانوا ممكن يعدّوا التحقق قبل ما
    أي واحدة تعمل commit ويتم تخصيص نفس الوحدة مرتين فعليًا. اتصلح بقفل صف
    الوحدة (with_for_update(nowait=True)) قبل إعادة التحقق من التعارض،
    بنفس نمط lock_room_for_booking بالظبط.

    ⚠️ باجان حقيقيان تانيان اتكشفوا واتصلحوا هنا (اختبار حي كمدير خدمة عملاء
    ملكية جزئية): كان ممكن تخصيص وحدة فعلية لزيارة على عقد **ملغي بالفعل** (صفر
    تحقق من contract.status)، وكان ممكن كمان تحجز زيارة بتاريخ بعد
    contract.end_date (انتهاء مدة العقد) بدون أي رفض — يعني عميل عقده انتهى
    كان لسه يقدر ياخد وحدة فعلية من مخزون المنتجع."""
    contract = get_contract_or_404(db, data.contract_id)
    if data.check_out <= data.check_in:
        raise ValueError("check_out يجب أن يكون بعد check_in")
    if contract.status == "cancelled":
        raise ValueError(f"العقد {contract.contract_number} ملغي — لا يمكن حجز زيارة عليه")
    if contract.status == "expired":
        raise ValueError(f"العقد {contract.contract_number} منتهي — لا يمكن حجز زيارة عليه")
    if contract.end_date and data.check_in > contract.end_date:
        raise ValueError(
            f"تاريخ الزيارة بعد نهاية مدة العقد {contract.contract_number} "
            f"({contract.end_date.isoformat()}) — العقد منتهي لهذه الفترة"
        )
    if contract.booking_frozen:
        # سبب التجميد بيتحدد فعليًا وقت الرفض (أقساط/صيانة/الاتنين) — بدون
        # أي تغيير في البنية (booking_frozen يفضل flag واحد على العقد).
        reasons = []
        if any(i.status in ("overdue", "partial") for i in contract.installments_list):
            reasons.append("أقساط متأخرة")
        if any(d.status in ("overdue", "partial") for d in contract.maintenance_dues_list):
            reasons.append("رسوم صيانة متأخرة")
        reason_text = " و".join(reasons) if reasons else "متأخرات"
        raise ValueError(f"الحجز مجمَّد لوجود {reason_text} — سدِّد المتأخرات أولاً")
    nights = (data.check_out - data.check_in).days

    if contract.unit_capacity == 6:
        # Family Compound entitlement — راجع _create_entitlement_pair_visit
        # ومداخل contract.unit_capacity/TimeshareUnitPair (OPS-DATA-02 §8
        # نقطة 11): شاليه+استوديو مقترنين في عملية ذرّية واحدة، مش وحدة
        # واحدة عادية.
        return _create_entitlement_pair_visit(db, contract, data, nights)

    if contract.unit_id:
        # عقد بوحدة ثابتة (متعاقد عليها بالاسم) — الاختيار اليدوي ميتجاهلش
        # هنا، ده مش اختيار حر زي العقد العائم. تغيير وحدة عقد ثابت عملية
        # مقصودة منفصلة (contracts.transfer_unit)، مش جزء من تأكيد زيارة.
        if data.unit_id and data.unit_id != contract.unit_id:
            raise ValueError(
                f"العقد {contract.contract_number} مربوط بوحدة ثابتة — "
                "لتغييرها استخدم إعادة تخصيص الوحدة على العقد نفسه، مش تأكيد الزيارة"
            )
        candidate_id = contract.unit_id
    elif data.unit_id:
        # عقد عائم واختار الموظف وحدة معيّنة من خريطة الوحدات (2026-08-16)
        # بدل الاختيار الأوتوماتيكي — نوع/فرع الوحدة يتأكدوا هنا، وباقي
        # الفحوصات (تعارض/صيانة) بتحصل بعد القفل تحت زي أي مسار تاني بالظبط.
        manual_unit = crud.get_unit(db, data.unit_id)
        if not manual_unit or manual_unit.branch_id != contract.branch_id:
            raise ValueError(f"الوحدة {data.unit_id} غير موجودة في هذا الفرع")
        if manual_unit.unit_type != contract.room_type:
            raise ValueError(
                f"الوحدة {manual_unit.unit_number} نوعها {manual_unit.unit_type} "
                f"لا يطابق نوع عقد {contract.contract_number} ({contract.room_type})"
            )
        candidate_id = manual_unit.id
    else:
        # عقد عائم بدون اختيار يدوي — ابحث عن أي وحدة متاحة من نفس نوع
        # الغرفة (قبل القفل، مجرد ترشيح أولي) ثم اقفلها وأعد التحقق تحت
        # الحماية فعليًا تحت.
        found = crud.find_available_unit(db, contract.branch_id, contract.room_type, data.check_in, data.check_out)
        if not found:
            raise ValueError(f"لا توجد وحدة متاحة من نوع {contract.room_type} في الفترة المطلوبة")
        candidate_id = found.id

    try:
        unit = crud.lock_unit_for_visit(db, candidate_id)
    except OperationalError:
        db.rollback()
        raise VisitConflictError(f"الوحدة {candidate_id} مقفولة الآن من عملية حجز أخرى — حاول مرة أخرى")

    if not unit:
        raise ValueError("الوحدة المخصَّصة لهذا العقد لم تعد موجودة")
    if unit.status == "maintenance":
        raise ValueError(f"الوحدة {unit.unit_number} تحت الصيانة حاليًا")
    # إعادة التحقق من التعارض بعد القفل — مفيش حد تاني يقدر يخصص نفس الوحدة
    # لنفس الفترة لحد ما الـ transaction دي تخلص (commit/rollback)
    if crud.has_overlapping_visit(db, unit.id, data.check_in, data.check_out):
        raise ValueError(f"الوحدة {unit.unit_number} محجوزة بالفعل في هذه الفترة")

    visit = crud.create_visit(db, data, nights, unit_id=unit.id)
    db.commit()
    db.refresh(visit)
    return visit


def _create_entitlement_pair_visit(
    db: Session, contract: "TimeshareContract", data: TimeshareVisitCreate, nights: int,
) -> TimeshareVisit:
    """زيارة استحقاق Family Compound — عقد سعة 6 بياخد شاليه + استوديو
    مقترنين معًا (نفس رقم الوحدة فعليًا، راجع TimeshareUnitPair) في عملية
    ذرّية واحدة (كل الوحدتين أو ولا واحدة)، مش زيارتين منفصلتين ممكن ينجح
    نص العملية ويفشل النص التاني. entitlement_visit=True دايمًا هنا — مفيش
    رسم ليلة جديد (العقد مسدد بالكامل بقيمته، راجع OPS-DATA-02 §8 نقطة 11
    وdocstring TimeshareVisit.entitlement_visit). قفل الوحدتين بترتيب ثابت
    (crud.lock_unit_pair_for_visit) بنفس نمط pms.services._lock_and_price_rooms
    لمنع deadlock بين محاولتين متزامنتين."""
    if contract.unit_id:
        pair = crud.get_unit_pair_by_chalet_unit_id(db, contract.unit_id)
        if not pair:
            raise ValueError(
                f"الوحدة الثابتة للعقد {contract.contract_number} مالهاش زوج "
                "معتمد (شاليه+استوديو) — سجّل الزوج أولاً عبر إدارة وحدات الملكية الجزئية"
            )
    else:
        pair = crud.find_available_unit_pair(db, contract.branch_id, data.check_in, data.check_out)
        if not pair:
            raise ValueError("لا يوجد زوج وحدات (شاليه+استوديو) متاح في الفترة المطلوبة")

    try:
        crud.lock_unit_pair_for_visit(db, pair)
    except OperationalError:
        db.rollback()
        raise VisitConflictError(f"زوج الوحدات {pair.id} مقفول الآن من عملية حجز أخرى — حاول مرة أخرى")

    chalet = crud.get_unit(db, pair.chalet_unit_id)
    studio = crud.get_unit(db, pair.studio_unit_id)
    if not chalet or not studio:
        raise ValueError("إحدى وحدتي الزوج لم تعد موجودة")
    if chalet.status == "maintenance":
        raise ValueError(f"الوحدة {chalet.unit_number} تحت الصيانة حاليًا")
    if studio.status == "maintenance":
        raise ValueError(f"الوحدة {studio.unit_number} تحت الصيانة حاليًا")

    # إعادة التحقق من التعارض بعد القفل — نفس سبب create_visit العادية فوق
    if crud.has_overlapping_visit(db, chalet.id, data.check_in, data.check_out):
        raise ValueError(f"الوحدة {chalet.unit_number} محجوزة بالفعل في هذه الفترة")
    if crud.has_overlapping_visit(db, studio.id, data.check_in, data.check_out):
        raise ValueError(f"الوحدة {studio.unit_number} محجوزة بالفعل في هذه الفترة")

    visit = crud.create_visit(
        db, data, nights, unit_id=chalet.id, paired_unit_id=studio.id, entitlement_visit=True,
    )
    db.commit()
    db.refresh(visit)
    return visit


def update_visit(db: Session, visit_id: int, data: TimeshareVisitUpdate) -> TimeshareVisit:
    visit = crud.get_visit(db, visit_id)
    if not visit:
        raise ValueError(f"الزيارة {visit_id} غير موجودة")
    obj = crud.update_visit(db, visit, data)
    db.commit()
    db.refresh(obj)
    return obj
