"""
tests/test_hub_public_catalog.py
hub.public_catalog.get_public_catalog لم يكن له أي تست مخصص خالص قبل كده
(فجوة حقيقية اتكشفت 2026-09-09 وقت إضافة usd_* fields). يغطي هنا: حساب
usd_total الصحيح (نفس نسبة VAT/service بالظبط بس على list_price_usd)،
وNone لأي نوع غرفة من غير سعر دولار معلَن.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.modules.hub.public_catalog import get_public_catalog


def _make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(
        name=f"Catalog-Branch-{uuid.uuid4().hex[:6]}",
        code=f"CB{uuid.uuid4().hex[:4].upper()}",
        is_active=True,
    )
    db.add(b)
    db.commit()
    return b


def _make_room_type(db, branch, *, base_rate, list_price_usd=None, max_occupancy=2, is_active=True):
    from app.modules.pms.models import RoomType
    rt = RoomType(
        branch_id=branch.id,
        name=f"Type-{uuid.uuid4().hex[:6]}",
        name_ar="نوع تجريبي",
        base_rate=base_rate,
        list_price_usd=list_price_usd,
        max_occupancy=max_occupancy,
        is_active=is_active,
    )
    db.add(rt)
    db.commit()
    return rt


class TestGetPublicCatalogUsdPricing:
    def test_room_type_with_usd_price_returns_usd_total(self, db, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "VAT_PERCENTAGE", 14.0)
        monkeypatch.setattr(settings, "SERVICE_CHARGE_PERCENTAGE", 12.0)

        branch = _make_branch(db)
        _make_room_type(db, branch, base_rate=Decimal("8400.00"), list_price_usd=Decimal("165.00"))

        entries = get_public_catalog(db, branch.id)
        assert len(entries) == 1
        entry = entries[0]

        assert entry.usd_base_price == Decimal("165.00")
        assert entry.usd_vat_amount == Decimal("23.10")       # 165 * 14%
        assert entry.usd_service_amount == Decimal("19.80")   # 165 * 12%
        assert entry.usd_total == Decimal("207.90")
        # EGP fields stay computed from base_rate, unaffected by USD fields.
        assert entry.total == Decimal("8400.00") + Decimal("1176.00") + Decimal("1008.00")

    def test_room_type_without_usd_price_has_none_usd_fields(self, db):
        branch = _make_branch(db)
        _make_room_type(db, branch, base_rate=Decimal("3500.00"), list_price_usd=None)

        entries = get_public_catalog(db, branch.id)
        assert len(entries) == 1
        entry = entries[0]

        assert entry.usd_base_price is None
        assert entry.usd_vat_amount is None
        assert entry.usd_service_amount is None
        assert entry.usd_total is None
        # EGP pricing is still computed normally.
        assert entry.base_price == Decimal("3500.00")

    def test_inactive_room_type_excluded(self, db):
        branch = _make_branch(db)
        _make_room_type(db, branch, base_rate=Decimal("1000.00"), is_active=False)

        entries = get_public_catalog(db, branch.id)
        assert entries == []

    def test_unapproved_room_type_excluded(self, db):
        """base_rate=None = غير معتمد تجاريًا بعد — مستبعد من الكتالوج العام."""
        branch = _make_branch(db)
        _make_room_type(db, branch, base_rate=None)

        entries = get_public_catalog(db, branch.id)
        assert entries == []
