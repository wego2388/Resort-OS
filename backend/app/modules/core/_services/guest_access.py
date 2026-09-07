"""
app/modules/core/_services/guest_access.py
Extracted from app/modules/core/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.modules.core import crud
from app.modules.core.models import GuestAlert, GuestSession, ServiceLocationToken
from app.modules.core.schemas import (
    AuditLogCreate,
    GuestAlertRead,
    GuestAlertPublicStatus,
    GuestServiceOutletRead,
    GuestSessionRead,
    ServiceLocationRead,
)
from app.modules.core._services.settings import (
    get_setting_value,
)
from app.modules.core._services.authorization import (
    assert_branch_access,
)


def list_guest_alerts(
    db: Session, branch_id: int, requesting_user, skip: int = 0, limit: int = 20,
) -> tuple[list[GuestAlert], int]:
    """راجع docstring GET /alerts (core/api/router.py) — كانت بتنادي
    crud.list_active_alerts مباشرة من الـ router (تجاوز طبقة service)، وكانت
    بتثق في branch_id من العميل من غير أي تحقق ملكية. اتصلح الاتنين مع بعض."""
    assert_branch_access(db, requesting_user, branch_id, "عرض تنبيهات")
    from app.core.config import settings  # noqa: PLC0415
    expired = crud.expire_stale_guest_alerts(
        db, datetime.utcnow() - timedelta(minutes=settings.GUEST_REQUEST_TTL_MINUTES),
        branch_id=branch_id,
    )
    if expired:
        db.commit()
    return crud.list_active_alerts(db, branch_id, skip=skip, limit=limit)


def guest_alert_read(db: Session, alert: GuestAlert) -> GuestAlertRead:
    payload = GuestAlertRead.model_validate(alert).model_dump()
    payload["location_label"] = _location_label(db, alert.context_type, alert.context_id)
    if alert.outlet_id is not None:
        from app.modules.dining import crud as dining_crud  # noqa: PLC0415
        outlet = dining_crud.get_outlet(db, alert.outlet_id)
        if outlet:
            payload["outlet_name"] = outlet.name
            payload["outlet_name_ar"] = outlet.name_ar
    return GuestAlertRead(**payload)




# ─────────────────────── GuestAlert ──────────────────────────────────
# راجع app/modules/core/models.py::GuestAlert — قناة تنبيه يبدأها الضيف
# بدون auth (نادِ الجرسون/هات الفاتورة)، وطاقم الخدمة بيتابعها لحظيًا عبر
# WebSocket (app/modules/core/api/router.py::alerts_manager).

def assert_guest_alerts_enabled(db: Session, branch_id: int) -> None:
    """Gate 1 containment (جولة مراجعة Codex الثانية، 2026-07-17): هذا
    الـ endpoint عام تمامًا بدون auth، context_id مش FK حقيقي (راجع
    GuestAlert docstring)، ومفيش أي تحقق إن context_id ينتمي فعليًا
    لـbranch_id. الـcontext_type mismatch (`dining_table` مش ضمن الـenum
    الحالي) بيوقف مسار المطعم/الكافيه بالصدفة بس — context_type زي
    `room`/`beach_location`/`other` لسه شغالين اليوم بلا أي تحقق حقيقي.
    عمدًا **لا نصلح** الـenum mismatch هنا (ده يفتح باب Gate 8 قبل وقته)
    — بدل كده نقفل الـendpoint كله.

    **تصحيح (جولة مراجعة Codex الثالثة):** AGENTS.md بيمنع الاعتماد على
    core.Setting (حر، قابل للتعديل عبر API الإعدادات) كبوابة أمان لوحدها.
    لازم الاتنين معًا: settings.GUEST_ALERTS_ENABLED (typed،
    deployment-level) + core.Setting الخاص بالفرع (core.guest_alerts_enabled)."""
    from app.core.config import settings  # noqa: PLC0415

    if not settings.GUEST_ALERTS_ENABLED:
        raise ValueError("نداء الضيف غير متاح حاليًا")

    raw_value = get_setting_value(
        db, "core.guest_alerts_enabled", branch_id=branch_id, default="false",
    )
    enabled = str(raw_value).strip().lower() in ("1", "true", "yes", "y", "نعم")
    if not enabled:
        raise ValueError("نداء الضيف غير متاح حاليًا")


def assert_location_belongs_to_branch(
    db: Session, branch_id: int, location_type: str, location_id: int,
) -> None:
    """Gate 8 Phase 1 (2026-07-21): تحقق مشترك يستخدمه أي كود بيتعامل مع
    "موقع خدمة" عام (dining_table|beach_location|room|other) بدون FK حقيقي
    — GuestAlert وServiceLocationToken الاتنين. قبل كده مفيش أي تحقق إن
    location_id ينتمي فعليًا لـbranch_id — ضيف/طلب يقدر يشاور على طاولة/
    موقع شاطئ/غرفة تابعة لفرع تاني تمامًا. نفس فئة الثغرة اللي اتصلحت في
    beach check-in (core_services.assert_branch_access)، بس هنا مفيش
    "مستخدم" نتحقق من فرعه (context عام مش مستخدم مصادَق عليه بالضرورة)؛
    التحقق إن الموقع المُدَّعى حقيقي وتابع لنفس الفرع المُدَّعى، مش أكتر."""
    if location_type == "dining_table":
        from app.modules.dining.models import VenueTable  # noqa: PLC0415
        location = (
            db.query(VenueTable)
            .filter(VenueTable.id == location_id, VenueTable.branch_id == branch_id)
            .first()
        )
        if not location:
            raise ValueError("الطاولة المحدّدة لا تنتمي لهذا الفرع")
        if location.status == "out_of_service":
            raise ValueError("الطاولة المحدّدة خارج الخدمة")
    elif location_type == "beach_location":
        from app.modules.beach.models import BeachLocation  # noqa: PLC0415
        location = (
            db.query(BeachLocation)
            .filter(BeachLocation.id == location_id, BeachLocation.branch_id == branch_id)
            .first()
        )
        if not location:
            raise ValueError("موقع الشاطئ المحدّد لا ينتمي لهذا الفرع")
        if location.status == "out_of_service":
            raise ValueError("موقع الشاطئ المحدّد خارج الخدمة")
    elif location_type == "room":
        from app.modules.pms.models import Room  # noqa: PLC0415
        location = (
            db.query(Room)
            .filter(Room.id == location_id, Room.branch_id == branch_id)
            .first()
        )
        if not location:
            raise ValueError("الغرفة المحدّدة لا تنتمي لهذا الفرع")
        if location.status == "maintenance":
            raise ValueError("الغرفة المحدّدة خارج الخدمة")
    else:
        raise ValueError("نوع موقع الخدمة غير مدعوم")


def create_guest_alert(
    db: Session, session_token: str, alert_type: str,
    message: Optional[str] = None, outlet_id: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> tuple[GuestAlert, bool]:
    """Create a location-bound request and report whether it was new.

    The bearer guest session is the only source of branch/location.  A
    partial unique index is the final concurrency guard for double taps.
    """
    session, location = resolve_guest_session(db, session_token)
    assert_guest_alerts_enabled(db, location.branch_id)
    from app.core.config import settings  # noqa: PLC0415
    crud.expire_stale_guest_alerts(
        db, datetime.utcnow() - timedelta(minutes=settings.GUEST_REQUEST_TTL_MINUTES),
        branch_id=location.branch_id,
    )

    outlet = None
    if outlet_id is not None:
        from app.modules.dining import crud as dining_crud  # noqa: PLC0415
        outlet = dining_crud.get_outlet(db, outlet_id)
        if not outlet or not outlet.is_active or outlet.branch_id != location.branch_id:
            raise ValueError("منفذ الخدمة غير صالح لهذا الموقع")

    existing = crud.get_active_guest_alert(
        db, branch_id=location.branch_id, context_type=location.location_type,
        context_id=location.location_id, alert_type=alert_type,
    )
    if existing:
        return existing, False

    linked_order_id = None
    if outlet_id is not None:
        from app.modules.dining.models import DiningOrder  # noqa: PLC0415
        linked = (
            db.query(DiningOrder)
            .filter(
                DiningOrder.guest_session_id == session.id,
                DiningOrder.outlet_id == outlet_id,
                DiningOrder.status.in_(("held", "open", "in_kitchen", "served")),
            )
            .order_by(DiningOrder.created_at.desc())
            .first()
        )
        linked_order_id = linked.id if linked else None

    alert = crud.create_guest_alert(
        db, branch_id=location.branch_id, context_type=location.location_type,
        context_id=location.location_id, alert_type=alert_type, message=message,
        public_reference=f"req_{secrets.token_urlsafe(18)}",
        guest_session_id=session.id, outlet_id=outlet_id,
        order_id=linked_order_id, idempotency_key=idempotency_key,
    )
    crud.create_audit_log(db, AuditLogCreate(
        branch_id=location.branch_id,
        action="guest_request_created",
        entity_type="guest_alert",
        entity_id=alert.id,
        new_data=json.dumps({
            "public_reference": alert.public_reference,
            "location_type": location.location_type,
            "alert_type": alert_type,
            "outlet_id": outlet_id,
        }, ensure_ascii=False, sort_keys=True),
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            replay = crud.get_guest_alert_by_idempotency_key(
                db, session.id, idempotency_key,
            )
            if replay:
                return replay, False
        existing = crud.get_active_guest_alert(
            db, branch_id=location.branch_id, context_type=location.location_type,
            context_id=location.location_id, alert_type=alert_type,
        )
        if existing:
            return existing, False
        raise
    db.refresh(alert)
    return alert, True


def get_guest_alert_public_status(
    db: Session, public_reference: str, session_token: str,
) -> GuestAlertPublicStatus:
    _session, location = resolve_guest_session(db, session_token)
    alert = crud.get_guest_alert_by_public_reference(db, public_reference)
    if (
        not alert
        or alert.branch_id != location.branch_id
        or alert.context_type != location.location_type
        or alert.context_id != location.location_id
    ):
        raise ValueError("طلب الخدمة غير موجود")
    from app.core.config import settings  # noqa: PLC0415
    if (
        alert.status in ("open", "acknowledged", "arrived")
        and alert.created_at < datetime.utcnow() - timedelta(minutes=settings.GUEST_REQUEST_TTL_MINUTES)
    ):
        alert.status = "expired"
        db.commit()
        db.refresh(alert)
    return GuestAlertPublicStatus.model_validate(alert, from_attributes=True)


def update_alert_status(
    db: Session,
    alert_id: int,
    new_status: str,
    resolved_by: int,
    requesting_user,
) -> GuestAlert:
    """Gate 1 containment (جولة تصحيح ثانية، 2026-07-17): كان بيقبل
    alert_id من أي نادل+ من غير أي تحقق فرع، تمامًا زي باج GET /alerts
    الأصلي — نادل من فرع تاني كان يقدر يقفل/يأكد تنبيه فرع مختلف تمامًا.
    requesting_user إجباري (مش Optional) عمدًا — الـ caller الوحيد هو
    الـ router ومعاه دايمًا مستخدم مصادَق عليه حقيقي؛ مفيش سبب مشروع
    يسمح بتخطي الفحص هنا (نفس نمط check_in_reservation بعد جولة مراجعة
    Codex الثالثة، اللي شالت أي باب تخطٍ اختباري منها بالكامل برضو)."""
    alert = crud.get_guest_alert_for_update(db, alert_id)
    if not alert:
        raise ValueError(f"التنبيه {alert_id} غير موجود")
    assert_branch_access(db, requesting_user, alert.branch_id, "تحديث حالة تنبيه")
    if alert.status not in ("open", "acknowledged", "arrived"):
        raise ValueError("التنبيه مُتعامَل معه بالفعل")

    from app.core.deps import user_level  # noqa: PLC0415
    if (
        alert.assigned_to is not None
        and alert.assigned_to != resolved_by
        and user_level(requesting_user) < 60
    ):
        raise PermissionError("طلب الخدمة مُسند بالفعل لزميل آخر")

    allowed_transitions = {
        "open": {"acknowledged", "arrived", "resolved"},
        "acknowledged": {"arrived", "resolved"},
        "arrived": {"resolved"},
    }
    if new_status not in allowed_transitions[alert.status]:
        raise ValueError(f"لا يمكن نقل الطلب من {alert.status} إلى {new_status}")

    alert = crud.update_alert_status(db, alert, new_status, resolved_by=resolved_by)
    crud.create_audit_log(db, AuditLogCreate(
        user_id=resolved_by,
        branch_id=alert.branch_id,
        action=f"guest_request_{new_status}",
        entity_type="guest_alert",
        entity_id=alert.id,
        new_data=json.dumps({
            "public_reference": alert.public_reference,
            "status": new_status,
            "assigned_to": alert.assigned_to,
        }, ensure_ascii=False, sort_keys=True),
    ))
    db.commit()
    db.refresh(alert)
    return alert


def resolve_bill_requests_for_paid_order(db: Session, order, resolved_by: int | None) -> list[GuestAlert]:
    """Resolve linked bill requests inside Dining's payment transaction."""
    alerts = crud.list_active_bill_alerts_for_order(
        db,
        order_id=order.id,
        branch_id=order.branch_id,
        context_id=order.table_id,
        guest_session_id=order.guest_session_id,
        outlet_id=order.outlet_id,
    )
    for alert in alerts:
        crud.update_alert_status(db, alert, "resolved", resolved_by=resolved_by)
        crud.create_audit_log(db, AuditLogCreate(
            user_id=resolved_by,
            branch_id=alert.branch_id,
            action="guest_request_auto_resolved_on_payment",
            entity_type="guest_alert",
            entity_id=alert.id,
            new_data=json.dumps({
                "public_reference": alert.public_reference,
                "order_id": order.id,
            }, ensure_ascii=False, sort_keys=True),
        ))
    return alerts


# ─────────────────────── ServiceLocationToken ──────────────────────────
# راجع app/modules/core/models.py::ServiceLocationToken — رمز عام لموقع
# خدمة (طاولة/موقع شاطئ/غرفة)، Gate 8 Phase 1.

def _location_label(db: Session, location_type: str, location_id: int) -> str:
    """وصف بشري بسيط للموقع — الضيف يشوفه بدل رقم ID خام (راجع
    ServiceLocationRead's docstring)."""
    if location_type == "dining_table":
        from app.modules.dining.models import VenueTable  # noqa: PLC0415
        table = db.query(VenueTable).filter(VenueTable.id == location_id).first()
        return f"طاولة {table.table_number}" if table else "طاولة"
    if location_type == "beach_location":
        from app.modules.beach.models import BeachLocation  # noqa: PLC0415
        loc = db.query(BeachLocation).filter(BeachLocation.id == location_id).first()
        return f"{loc.location_type} {loc.number}" if loc else "موقع شاطئ"
    if location_type == "room":
        from app.modules.pms.models import Room  # noqa: PLC0415
        room = db.query(Room).filter(Room.id == location_id).first()
        return f"غرفة {room.name}" if room else "غرفة"
    return "موقع"


def _lock_service_location(
    db: Session, location_type: str, location_id: int,
) -> None:
    """Serialize QR rotations on the physical resource row."""
    if location_type == "dining_table":
        from app.modules.dining.models import VenueTable  # noqa: PLC0415
        db.query(VenueTable).filter(VenueTable.id == location_id).with_for_update().one()
    elif location_type == "beach_location":
        from app.modules.beach.models import BeachLocation  # noqa: PLC0415
        db.query(BeachLocation).filter(BeachLocation.id == location_id).with_for_update().one()
    elif location_type == "room":
        from app.modules.pms.models import Room  # noqa: PLC0415
        db.query(Room).filter(Room.id == location_id).with_for_update().one()


def _guest_service_outlets(db: Session, location: ServiceLocationToken) -> list[GuestServiceOutletRead]:
    """⚠️ باج حقيقي اتصلح (2026-08-02): كان محصور على dining_table بس —
    يعني ضيف في أوضة (location_type="room") كان بيوصله من GET
    /public/service-location قايمة outlets فاضية تمامًا، فمنيو الأكل في
    DigitalHub.vue (تاب "روم سيرفس") كان بيفضل فاضي من غير أي طريقة يعرض
    بيها صنف واحد — قبل حتى ما يوصل لخطوة الطلب نفسها (اللي كانت مرفوضة
    هي كمان، راجع create_guest_order في dining/api/router.py). أوضة
    الضيف بتطلب من نفس منافذ المطعم/الكافيه النشطة في الفرع بالظبط زي
    طاولة الدايننج — "روم سيرفس" مفهوميًا هو نفس المنيو، بس التسليم
    للأوضة بدل الطاولة."""
    if location.location_type not in ("dining_table", "room"):
        return []
    from app.modules.dining import crud as dining_crud  # noqa: PLC0415
    return [
        GuestServiceOutletRead(
            id=o.id, name=o.name, name_ar=o.name_ar, outlet_type=o.outlet_type,
        )
        for o in dining_crud.list_outlets(db, location.branch_id, active_only=True)
    ]


def _guest_capabilities(db: Session, branch_id: int) -> tuple[bool, bool]:
    try:
        assert_guest_alerts_enabled(db, branch_id)
        alerts_enabled = True
    except ValueError:
        alerts_enabled = False
    try:
        from app.modules.dining.services import assert_guest_self_order_enabled  # noqa: PLC0415
        assert_guest_self_order_enabled(db, branch_id)
        self_order_enabled = True
    except ValueError:
        self_order_enabled = False
    return alerts_enabled, self_order_enabled


def _service_location_read(db: Session, location: ServiceLocationToken) -> ServiceLocationRead:
    alerts_enabled, self_order_enabled = _guest_capabilities(db, location.branch_id)
    return ServiceLocationRead(
        location_type=location.location_type,
        location_label=_location_label(db, location.location_type, location.location_id),
        service_mode="self_order" if self_order_enabled else "view_and_call",
        alerts_enabled=alerts_enabled,
        self_order_enabled=self_order_enabled,
        outlets=_guest_service_outlets(db, location),
    )


def _assert_active_location(db: Session, location: ServiceLocationToken | None) -> ServiceLocationToken:
    if not location or not location.is_active:
        raise ValueError("الرمز غير صالح أو منتهي")
    branch = crud.get_branch(db, location.branch_id)
    if not branch or not branch.is_active:
        raise ValueError("موقع الخدمة غير متاح حاليًا")
    # Revalidate current operational state on every public resolution; the
    # row may have been placed out of service after the QR was generated.
    assert_location_belongs_to_branch(
        db, location.branch_id, location.location_type, location.location_id,
    )
    return location


def create_guest_session(
    db: Session, qr_token: str, guest_name: str, guest_phone: str | None = None,
) -> GuestSessionRead:
    location = _assert_active_location(db, crud.get_active_service_location_token(db, qr_token))
    from app.core.config import settings  # noqa: PLC0415

    raw_session_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=settings.GUEST_SESSION_TTL_MINUTES)
    crud.create_guest_session(
        db,
        public_reference=f"gst_{secrets.token_urlsafe(16)}",
        token_hash=hashlib.sha256(raw_session_token.encode("utf-8")).hexdigest(),
        service_location_token_id=location.id,
        expires_at=expires_at,
        guest_name=guest_name,
        guest_phone=guest_phone,
    )
    db.commit()
    context = _service_location_read(db, location)
    return GuestSessionRead(
        **context.model_dump(), session_token=raw_session_token, expires_at=expires_at,
    )


def resolve_guest_session(
    db: Session, raw_session_token: str,
) -> tuple[GuestSession, ServiceLocationToken]:
    if not raw_session_token or len(raw_session_token) > 128:
        raise ValueError("جلسة الضيف غير صالحة أو منتهية")
    digest = hashlib.sha256(raw_session_token.encode("utf-8")).hexdigest()
    session = crud.get_guest_session_by_hash(db, digest)
    if not session or session.expires_at <= datetime.utcnow():
        raise ValueError("جلسة الضيف غير صالحة أو منتهية")
    location = crud.get_service_location_token_by_id(db, session.service_location_token_id)
    return session, _assert_active_location(db, location)


def create_or_rotate_service_location_token(
    db: Session, branch_id: int, location_type: str, location_id: int, requesting_user,
) -> ServiceLocationToken:
    """يولّد رمز جديد لموقع خدمة، ويُلغي أي رمز نشط سابق لنفس الموقع فورًا
    (is_active=False) — "قابل للتدوير" زي ما Decision 0001 طالب: QR قديم
    مطبوع لنفس الطاولة بيبطل تلقائيًا لحظة توليد رمز جديد ليها، من غير أي
    خطوة إلغاء منفصلة. يتحقق إن الموقع حقيقي وتابع لنفس الفرع الأول (نفس
    فحص GuestAlert بالظبط — راجع assert_location_belongs_to_branch)، وإن
    المدير المنفّذ فعلاً مرتبط بنفس الفرع (assert_branch_access — نفس قيد
    GET /alerts بالظبط، مدير فرع تاني ميقدرش يولّد رموز لطاولات مش بتاعته)."""
    branch = crud.get_branch(db, branch_id)
    if not branch:
        raise ValueError(f"الفرع {branch_id} غير موجود")
    if not branch.is_active:
        raise ValueError("لا يمكن توليد QR لفرع غير نشط")
    assert_branch_access(db, requesting_user, branch_id, "توليد رمز موقع خدمة")
    assert_location_belongs_to_branch(db, branch_id, location_type, location_id)

    _lock_service_location(db, location_type, location_id)
    assert_location_belongs_to_branch(db, branch_id, location_type, location_id)
    crud.deactivate_service_location_tokens(db, branch_id, location_type, location_id)
    token = crud.create_service_location_token(
        db, token=secrets.token_urlsafe(32), branch_id=branch_id,
        location_type=location_type, location_id=location_id, created_by=requesting_user.id,
    )
    crud.create_audit_log(db, AuditLogCreate(
        user_id=requesting_user.id,
        branch_id=branch_id,
        action="rotate_service_location_qr",
        entity_type="service_location_token",
        entity_id=token.id,
        new_data=json.dumps({
            "location_type": location_type,
            "location_id": location_id,
        }, ensure_ascii=False, sort_keys=True),
    ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("تعذر تدوير الرمز بسبب عملية متزامنة — أعد المحاولة") from exc
    db.refresh(token)
    return token


def list_service_location_tokens(
    db: Session, branch_id: int, requesting_user,
) -> list[ServiceLocationToken]:
    """مدير+ فقط، نفس قيد الفرع بتاع mint (assert_branch_access) — يستخدمه
    admin/QRGeneratorView.vue عشان يعرف أي طاولة عندها رمز فعّال بالفعل
    قبل ما يعرض زرار "توليد" أو الـQR مباشرة."""
    assert_branch_access(db, requesting_user, branch_id, "عرض رموز مواقع الخدمة")
    return crud.list_active_service_location_tokens(db, branch_id)


def resolve_service_location_token(db: Session, token: str) -> ServiceLocationRead:
    """Public — بدون auth. Decision 0001 بند 6: "the backend derives the
    trusted branch/outlet/service-location context — it does not trust
    those IDs from the public client." كل استخدام تاني للموقع (قائمة
    الطعام، تنبيه الضيف) لازم يمرّ من هنا الأول، مش ياخد IDs مباشرة من
    الرابط/الـquery params."""
    row = _assert_active_location(db, crud.get_active_service_location_token(db, token))
    return _service_location_read(db, row)
