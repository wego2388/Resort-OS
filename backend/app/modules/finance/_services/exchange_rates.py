"""
app/modules/finance/_services/exchange_rates.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.finance import crud
from app.resort_os.timezone_utils import local_today
from app.modules.finance.models import ExchangeRate
from app.modules.finance.schemas import (
    ExchangeRateCreate,
)




# ── Exchange Rates (Multi-Currency) ───────────────────────────────────
# ⚠️ ensure_default_exchange_rates() بيزرع أسعار dummy للتطوير/العرض بس (مش
# حية/رسمية) — أي استخدام إنتاجي حقيقي محتاج ربط بمصدر رسمي (البنك المركزي
# المصري مثلاً) واستبدال هذه الدالة أو تعطيلها.

_DEFAULT_SEED_RATES: list[tuple[str, str, Decimal]] = [
    ("USD", "EGP", Decimal("48.00")),
    ("EUR", "EGP", Decimal("52.00")),
]


def ensure_default_exchange_rates(db: Session, created_by: int = 0) -> list[ExchangeRate]:
    """يزرع سعر صرف افتراضي (dummy/dev) لـ USD وEUR مقابل EGP أول مرة بس —
    idempotent زي ensure_default_cost_centers: لو أي زوج عملة عنده سعر
    مسجّل بالفعل (أي تاريخ) منزرعش فوقه. لا تُستخدم كمصدر حقيقي في إنتاج."""
    created: list[ExchangeRate] = []
    for from_cur, to_cur, rate in _DEFAULT_SEED_RATES:
        _, existing_count = crud.list_exchange_rates(db, from_cur, to_cur, limit=1)
        if existing_count == 0:
            obj = crud.create_exchange_rate(
                db,
                ExchangeRateCreate(
                    from_currency=from_cur, to_currency=to_cur,
                    rate=rate, effective_date=local_today(settings.TIMEZONE),
                ),
                created_by=created_by,
            )
            created.append(obj)
    if created:
        db.commit()
    return created


def get_rate(db: Session, from_currency: str, to_currency: str, as_of: date) -> Decimal:
    """سعر الصرف من from_currency لـ to_currency بتاريخ as_of — بيرجّع أحدث
    سعر مسجّل في as_of أو قبله (fallback منطقي، مش أحدث سعر مطلق). لو مفيش
    سعر مباشر بيجرّب المعكوس (to→from) ويقلبه. لو مفيش أي سعر خالص بيرمي
    ValueError واضح — من غير ما يفترض 1.0 بصمت (ده كان ممكن يطلع رقم غلط
    تماماً في تقرير مالي حقيقي)."""
    if from_currency == to_currency:
        return Decimal("1")

    ensure_default_exchange_rates(db)

    direct = crud.get_latest_exchange_rate(db, from_currency, to_currency, as_of)
    if direct:
        return direct.rate

    inverse = crud.get_latest_exchange_rate(db, to_currency, from_currency, as_of)
    if inverse and inverse.rate != 0:
        return Decimal("1") / inverse.rate

    raise ValueError(
        f"لا يوجد سعر صرف مسجّل من {from_currency} إلى {to_currency} "
        f"بتاريخ {as_of} أو قبله — أضف سعر صرف عبر POST /finance/exchange-rates"
    )


def convert_to_egp(db: Session, amount: Decimal, currency: str, as_of: date) -> Decimal:
    """اختصار شائع: تحويل مبلغ لـ EGP equivalent بسعر الصرف في تاريخ as_of."""
    if currency == "EGP":
        return amount
    rate = get_rate(db, currency, "EGP", as_of)
    return (amount * rate).quantize(Decimal("0.01"))


def create_exchange_rate(db: Session, data: ExchangeRateCreate, created_by: int) -> ExchangeRate:
    if data.from_currency == data.to_currency:
        raise ValueError("from_currency و to_currency لازم يكونوا مختلفين")
    existing = crud.get_exchange_rate_exact(db, data.from_currency, data.to_currency, data.effective_date)
    if existing:
        raise ValueError(
            f"يوجد سعر صرف مسجّل بالفعل من {data.from_currency} إلى {data.to_currency} "
            f"بتاريخ {data.effective_date} — عدّل السعر عن طريق تسجيل سعر جديد بتاريخ مختلف"
        )
    obj = crud.create_exchange_rate(db, data, created_by)
    db.commit()
    db.refresh(obj)
    return obj


def list_exchange_rates(
    db: Session,
    from_currency: Optional[str] = None,
    to_currency: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
):
    return crud.list_exchange_rates(db, from_currency, to_currency, skip, limit)


# ── Cost Centers ─────────────────────────────────────────────────────
