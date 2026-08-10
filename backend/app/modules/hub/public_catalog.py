"""hub/public_catalog.py — public room+bundle pricing catalog and quote engine.

OPS-DATA-02 §7.2/§7.3: single source of truth for the base/VAT/service/total
math shown to the public and used to compute a persisted quote snapshot for
online booking requests — the catalog endpoint and the booking-request
endpoint must never drift from each other.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.config import settings

# OPS-DATA-02 §3: السعر يسري من 2026-07-01 بلا تاريخ نهاية حتى إنشاء
# version جديدة — قيمة صريحة، مش من الداتابيز (لا يوجد عمود effective_from
# على RoomType/RoomBundle اليوم؛ إضافة واحد لمجرد رقم ثابت واحد غير مبررة
# دلوقتي — راجع CLAUDE.md §3.4/عدم إضافة تجريد بلا حاجة فعلية).
PUBLISHED_PRICING_EFFECTIVE_FROM = date(2026, 7, 1)
QUOTE_VERSION = "EG-TRIAL-2026-07-v1"
PRICE_UNIT = "night"
INCLUDES_BREAKFAST = False


def _vat_and_service(base: Decimal) -> tuple[Decimal, Decimal]:
    vat = (base * Decimal(str(settings.VAT_PERCENTAGE)) / Decimal("100")).quantize(
        Decimal("0.01"), ROUND_HALF_UP,
    )
    service = (base * Decimal(str(settings.SERVICE_CHARGE_PERCENTAGE)) / Decimal("100")).quantize(
        Decimal("0.01"), ROUND_HALF_UP,
    )
    return vat, service


@dataclass(frozen=True)
class CatalogEntry:
    entry_type: str  # "room_type" | "bundle"
    id: int
    name: str
    name_ar: str | None
    capacity: int
    base_price: Decimal
    vat_amount: Decimal
    service_amount: Decimal
    total: Decimal
    currency: str
    price_unit: str
    effective_from: date
    includes_breakfast: bool


def get_public_catalog(db: Session, branch_id: int) -> list[CatalogEntry]:
    """أنواع الغرف + الباقات المعتمدة تجاريًا فقط (base_rate/max_occupancy
    مش None) — نفس شرط "معتمد" المستخدم في pms.services.create_booking's
    fail-closed check."""
    from app.modules.pms.models import RoomBundle, RoomType

    entries: list[CatalogEntry] = []
    room_types = (
        db.query(RoomType)
        .filter(RoomType.branch_id == branch_id, RoomType.is_active.is_(True))
        .order_by(RoomType.base_rate.asc().nullslast())
        .all()
    )
    for rt in room_types:
        if rt.base_rate is None or rt.max_occupancy is None:
            continue
        vat, service = _vat_and_service(rt.base_rate)
        entries.append(CatalogEntry(
            entry_type="room_type", id=rt.id, name=rt.name, name_ar=rt.name_ar,
            capacity=rt.max_occupancy, base_price=rt.base_rate,
            vat_amount=vat, service_amount=service, total=rt.base_rate + vat + service,
            currency=settings.DEFAULT_CURRENCY, price_unit=PRICE_UNIT,
            effective_from=PUBLISHED_PRICING_EFFECTIVE_FROM, includes_breakfast=INCLUDES_BREAKFAST,
        ))

    bundles = (
        db.query(RoomBundle)
        .filter(RoomBundle.branch_id == branch_id, RoomBundle.is_active.is_(True))
        .order_by(RoomBundle.name)
        .all()
    )
    for b in bundles:
        vat, service = _vat_and_service(b.price)
        entries.append(CatalogEntry(
            entry_type="bundle", id=b.id, name=b.name, name_ar=b.name_ar,
            capacity=b.max_occupancy, base_price=b.price,
            vat_amount=vat, service_amount=service, total=b.price + vat + service,
            currency=settings.DEFAULT_CURRENCY, price_unit=PRICE_UNIT,
            effective_from=PUBLISHED_PRICING_EFFECTIVE_FROM, includes_breakfast=INCLUDES_BREAKFAST,
        ))
    return entries


@dataclass(frozen=True)
class QuoteResult:
    entry_type: str
    room_type_id: int | None
    bundle_id: int | None
    nightly_rate: Decimal
    nights: int
    subtotal: Decimal
    vat_amount: Decimal
    service_amount: Decimal
    total: Decimal
    currency: str
    capacity: int


def compute_quote(
    db: Session,
    branch_id: int,
    *,
    room_type_id: int | None,
    bundle_id: int | None,
    check_in: date,
    check_out: date,
    adults: int,
    children: int,
) -> QuoteResult:
    """يحسب لقطة سعر واحدة، سواء لعرض عام (catalog) أو لطلب حجز حقيقي —
    نفس الدالة تمامًا في الحالتين عشان الرقم المعروض للضيف والرقم المحفوظ
    في quote snapshot (HubOnlineBooking) ميختلفوش أبدًا."""
    from app.modules.pms.models import RoomBundle, RoomType

    if bool(room_type_id) == bool(bundle_id):
        raise ValueError("حدد إما room_type_id أو bundle_id، وليس الاثنين معًا ولا بلا أي منهما")
    if check_out <= check_in:
        raise ValueError("check_out يجب أن يكون بعد check_in")
    nights = (check_out - check_in).days

    if room_type_id:
        rt = (
            db.query(RoomType)
            .filter(RoomType.id == room_type_id, RoomType.branch_id == branch_id, RoomType.is_active.is_(True))
            .first()
        )
        if not rt or rt.base_rate is None or rt.max_occupancy is None:
            raise ValueError("نوع الغرفة المطلوب غير متاح للحجز العام حاليًا")
        nightly, capacity, entry_type = rt.base_rate, rt.max_occupancy, "room_type"
    else:
        bundle = (
            db.query(RoomBundle)
            .filter(RoomBundle.id == bundle_id, RoomBundle.branch_id == branch_id, RoomBundle.is_active.is_(True))
            .first()
        )
        if not bundle:
            raise ValueError("الباقة المطلوبة غير متاحة للحجز العام حاليًا")
        nightly, capacity, entry_type = bundle.price, bundle.max_occupancy, "bundle"

    if (adults + children) > capacity:
        raise ValueError(f"عدد الأفراد ({adults + children}) أكبر من سعة الوحدة ({capacity})")

    subtotal = nightly * nights
    vat, service = _vat_and_service(subtotal)
    return QuoteResult(
        entry_type=entry_type, room_type_id=room_type_id, bundle_id=bundle_id,
        nightly_rate=nightly, nights=nights, subtotal=subtotal,
        vat_amount=vat, service_amount=service, total=subtotal + vat + service,
        currency=settings.DEFAULT_CURRENCY, capacity=capacity,
    )
