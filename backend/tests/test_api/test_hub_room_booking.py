"""OPS-DATA-02 §7.3 — public online room/bundle booking request + confirm.

Mandatory scenarios from the brief: quote drift, price change after
request, double confirmation, concurrent double-booking, retry with the
same idempotency key, room unavailable, branch tampering, over-capacity,
PII encryption, atomic bundle booking, and bundle-vs-individual-unit
conflicts.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.test_api.test_pms import make_branch


@pytest.fixture(autouse=True)
def _reset_room_booking_limits(monkeypatch):
    from app.core.kernel.cache import invalidate_pattern

    invalidate_pattern("public-room-booking")
    invalidate_pattern("rl:public")
    monkeypatch.setattr(settings, "CHAT_PUBLIC_HOST_BRANCH_MAP", {})


def _link_manager_to_branch(db, branch_id: int) -> None:
    from app.core.kernel.models.user import User
    from tests.conftest import assign_test_user_to_branch

    user = db.query(User).filter(User.email == "manager@test.local").first()
    if user:
        assign_test_user_to_branch(db, user.id, branch_id)
    db.commit()


def _site(monkeypatch, db, host: str = "room-booking.test"):
    branch = make_branch(db)
    db.commit()
    _link_manager_to_branch(db, branch.id)
    monkeypatch.setattr(settings, "CHAT_PUBLIC_HOST_BRANCH_MAP", {host: branch.id})
    return branch, host


def _priced_room_type(db, branch, *, base_rate="2500.00", max_occupancy=2, name="Studio"):
    from app.modules.pms.models import RoomType
    rt = RoomType(branch_id=branch.id, name=name, name_ar=name,
                  base_rate=Decimal(base_rate), max_occupancy=max_occupancy)
    db.add(rt)
    db.commit()
    return rt


def _room(db, branch, room_type, name):
    from app.modules.pms.models import Room
    room = Room(branch_id=branch.id, room_type_id=room_type.id, name=name, status="available")
    db.add(room)
    db.commit()
    return room


def _bundle(db, branch, chalet_room, studio_room, *, price="4500.00", max_occupancy=6):
    from app.modules.pms.models import RoomBundle
    b = RoomBundle(
        branch_id=branch.id, name="Family Compound 6P", name_ar="كومباوند عائلي",
        chalet_room_id=chalet_room.id, studio_room_id=studio_room.id,
        max_occupancy=max_occupancy, price=Decimal(price), is_active=True,
    )
    db.add(b)
    db.commit()
    return b


def _headers(host: str, key: str = "room-booking-req-00000001") -> dict[str, str]:
    return {"host": host, "Idempotency-Key": key}


def _payload(**overrides) -> dict:
    payload = {
        "guest_name": "ضيف اختبار",
        "guest_phone": "0100 123 4567",
        "guest_email": "guest@example.com",
        "check_in": str(date.today() + timedelta(days=10)),
        "check_out": str(date.today() + timedelta(days=12)),
        "adults": 2,
        "children": 0,
        "language": "ar",
        "service_contact_authorized": True,
        "service_disclosure_version": "service-contact-2026-07-26.v1",
    }
    payload.update(overrides)
    return payload


class TestPublicRoomCatalog:
    def test_lists_priced_room_types_and_bundles_with_vat_service_total(
        self, client: TestClient, db, monkeypatch,
    ):
        branch, host = _site(monkeypatch, db)
        studio = _priced_room_type(db, branch, base_rate="2500.00", max_occupancy=2, name="Studio")
        chalet = _priced_room_type(db, branch, base_rate="3500.00", max_occupancy=4, name="Chalet")
        studio_room = _room(db, branch, studio, "102S")
        chalet_room = _room(db, branch, chalet, "102A")
        _bundle(db, branch, chalet_room, studio_room)

        resp = client.get("/api/v1/hub/public/room-catalog", headers={"host": host})
        assert resp.status_code == 200, resp.text
        entries = {e["name"]: e for e in resp.json()}

        studio_entry = entries["Studio"]
        assert studio_entry["entry_type"] == "room_type"
        assert Decimal(str(studio_entry["base_price"])) == Decimal("2500.00")
        assert Decimal(str(studio_entry["vat_amount"])) == Decimal("350.00")
        assert Decimal(str(studio_entry["service_amount"])) == Decimal("300.00")
        assert Decimal(str(studio_entry["total"])) == Decimal("3150.00")
        assert studio_entry["includes_breakfast"] is False
        assert studio_entry["price_unit"] == "night"

        bundle_entry = entries["Family Compound 6P"]
        assert bundle_entry["entry_type"] == "bundle"
        assert Decimal(str(bundle_entry["total"])) == Decimal("5670.00")
        assert bundle_entry["capacity"] == 6

    def test_unconfigured_host_returns_404(self, client: TestClient, db, monkeypatch):
        resp = client.get("/api/v1/hub/public/room-catalog", headers={"host": "unknown.test"})
        assert resp.status_code == 404


class TestSubmitPublicRoomBooking:
    def test_submits_and_persists_quote_snapshot(self, client: TestClient, db, monkeypatch):
        branch, host = _site(monkeypatch, db)
        rt = _priced_room_type(db, branch)

        resp = client.post(
            "/api/v1/hub/public/room-bookings",
            headers=_headers(host),
            json=_payload(room_type_id=rt.id),
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["reference"].startswith("roombkg_")
        assert Decimal(str(body["quote"]["nightly_rate"])) == Decimal("2500.00")
        assert body["quote"]["nights"] == 2
        assert Decimal(str(body["quote"]["total"])) == Decimal("6300.00")  # 3150*2

        from app.modules.hub.models import HubOnlineBooking
        booking = db.query(HubOnlineBooking).filter_by(public_reference=body["reference"]).one()
        assert booking.status == "pending"
        assert booking.room_type_id == rt.id
        assert booking.quoted_total == Decimal("6300.00")

    def test_retry_with_same_idempotency_key_returns_same_reference_no_duplicate_row(
        self, client: TestClient, db, monkeypatch,
    ):
        branch, host = _site(monkeypatch, db)
        rt = _priced_room_type(db, branch)
        payload = _payload(room_type_id=rt.id)

        first = client.post("/api/v1/hub/public/room-bookings", headers=_headers(host), json=payload)
        second = client.post("/api/v1/hub/public/room-bookings", headers=_headers(host), json=payload)

        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json()["reference"] == second.json()["reference"]

        from app.modules.hub.models import HubOnlineBooking
        assert db.query(HubOnlineBooking).filter_by(branch_id=branch.id).count() == 1

    def test_same_key_different_payload_is_a_conflict(self, client: TestClient, db, monkeypatch):
        branch, host = _site(monkeypatch, db)
        rt = _priced_room_type(db, branch)

        client.post(
            "/api/v1/hub/public/room-bookings", headers=_headers(host),
            json=_payload(room_type_id=rt.id, adults=2),
        )
        resp = client.post(
            "/api/v1/hub/public/room-bookings", headers=_headers(host),
            json=_payload(room_type_id=rt.id, adults=1),
        )
        assert resp.status_code == 409

    def test_over_capacity_rejected(self, client: TestClient, db, monkeypatch):
        branch, host = _site(monkeypatch, db)
        rt = _priced_room_type(db, branch, max_occupancy=2)

        resp = client.post(
            "/api/v1/hub/public/room-bookings", headers=_headers(host),
            json=_payload(room_type_id=rt.id, adults=5, children=2),
        )
        assert resp.status_code == 400

    def test_branch_tampering_room_type_from_other_branch_rejected(
        self, client: TestClient, db, monkeypatch,
    ):
        branch, host = _site(monkeypatch, db)
        other_branch = make_branch(db)
        db.commit()
        foreign_rt = _priced_room_type(db, other_branch)

        resp = client.post(
            "/api/v1/hub/public/room-bookings", headers=_headers(host),
            json=_payload(room_type_id=foreign_rt.id),
        )
        assert resp.status_code == 400  # الفرع محسوم من Host، مش من ids العميل

    def test_unpriced_room_type_rejected(self, client: TestClient, db, monkeypatch):
        from app.modules.pms.models import RoomType
        branch, host = _site(monkeypatch, db)
        rt = RoomType(branch_id=branch.id, name="Unpriced", base_rate=None, max_occupancy=None)
        db.add(rt)
        db.commit()

        resp = client.post(
            "/api/v1/hub/public/room-bookings", headers=_headers(host),
            json=_payload(room_type_id=rt.id),
        )
        assert resp.status_code == 400

    def test_honeypot_field_silently_suppressed(self, client: TestClient, db, monkeypatch):
        branch, host = _site(monkeypatch, db)
        rt = _priced_room_type(db, branch)

        resp = client.post(
            "/api/v1/hub/public/room-bookings", headers=_headers(host),
            json=_payload(room_type_id=rt.id, website="http://spam.example"),
        )
        assert resp.status_code == 202
        assert resp.json()["quote"] is None

        from app.modules.hub.models import HubOnlineBooking
        assert db.query(HubOnlineBooking).filter_by(branch_id=branch.id).count() == 0

    def test_guest_pii_encrypted_at_rest(self, client: TestClient, db, monkeypatch):
        branch, host = _site(monkeypatch, db)
        rt = _priced_room_type(db, branch)

        resp = client.post(
            "/api/v1/hub/public/room-bookings", headers=_headers(host),
            json=_payload(room_type_id=rt.id, guest_phone="+201009998888"),
        )
        assert resp.status_code == 202
        from app.modules.hub.models import HubOnlineBooking
        booking = db.query(HubOnlineBooking).filter_by(
            public_reference=resp.json()["reference"]
        ).one()

        raw = db.execute(sa.text(
            "SELECT guest_name, guest_phone, guest_email FROM hub_online_bookings WHERE id = :id"
        ), {"id": booking.id}).mappings().one()
        assert raw["guest_phone"] != "+201009998888"
        assert raw["guest_name"] != "ضيف اختبار"
        assert raw["guest_email"] != "guest@example.com"
        # لازم يتقروا صح لما يتفكوا عن طريق الـORM (نفس الـEncryptedString)
        assert booking.guest_phone == "+201009998888"


class TestConfirmPublicRoomBooking:
    def _submit(self, client, host, **overrides):
        return client.post(
            "/api/v1/hub/public/room-bookings",
            headers=_headers(host, overrides.pop("key", "confirm-req-0000001")),
            json=_payload(**overrides),
        )

    def test_quote_drift_confirm_charges_original_quoted_rate_not_live_rate(
        self, client: TestClient, db, monkeypatch, manager_headers,
    ):
        branch, host = _site(monkeypatch, db)
        rt = _priced_room_type(db, branch, base_rate="2500.00")
        _room(db, branch, rt, "101")

        resp = self._submit(client, host, room_type_id=rt.id)
        assert resp.status_code == 202
        reference = resp.json()["reference"]

        # السعر المعتمد اتغيّر بعد الطلب، قبل ما الفريق يأكّد
        rt.base_rate = Decimal("9999.00")
        db.commit()

        from app.modules.hub.models import HubOnlineBooking
        booking = db.query(HubOnlineBooking).filter_by(public_reference=reference).one()
        confirm_resp = client.post(
            f"/api/v1/hub/online-bookings/{booking.id}/confirm", headers=manager_headers,
        )
        assert confirm_resp.status_code == 200, confirm_resp.text
        confirmed = confirm_resp.json()
        assert confirmed["pms_booking_id"] is not None

        from app.modules.pms.models import Booking
        pms_booking = db.query(Booking).filter_by(id=confirmed["pms_booking_id"]).one()
        assert pms_booking.rooms[0].daily_rate == Decimal("2500.00")  # مش 9999 الجديد
        assert pms_booking.total_rate == Decimal("5000.00")  # 2500 * 2 ليلة، مطابق للـquote الأصلي

    def test_double_confirmation_is_idempotent(self, client: TestClient, db, monkeypatch, manager_headers):
        """⚠️ 2026-08-11: كان بيترفض بـ400 — لكن إعادة نفس طلب التأكيد بعد
        نجاح فعلي (retry بعد شبكة قطعت الرد، مثلاً) لازم ترجع نفس الحجز
        بدل ما تترفض. راجع hub.services.confirm_booking's docstring."""
        branch, host = _site(monkeypatch, db)
        rt = _priced_room_type(db, branch)
        _room(db, branch, rt, "101")

        resp = self._submit(client, host, room_type_id=rt.id)
        from app.modules.hub.models import HubOnlineBooking
        booking = db.query(HubOnlineBooking).filter_by(public_reference=resp.json()["reference"]).one()

        first = client.post(f"/api/v1/hub/online-bookings/{booking.id}/confirm", headers=manager_headers)
        second = client.post(f"/api/v1/hub/online-bookings/{booking.id}/confirm", headers=manager_headers)
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["pms_booking_id"] == first.json()["pms_booking_id"]

    def test_concurrent_double_booking_confirm_conflicts_stays_pending(
        self, client: TestClient, db, monkeypatch, manager_headers,
    ):
        branch, host = _site(monkeypatch, db)
        rt = _priced_room_type(db, branch)
        room = _room(db, branch, rt, "101")  # الغرفة الوحيدة من هذا النوع

        resp = self._submit(client, host, room_type_id=rt.id)
        from app.modules.hub.models import HubOnlineBooking
        booking = db.query(HubOnlineBooking).filter_by(public_reference=resp.json()["reference"]).one()

        # حجز مباشر تاني ياخد الغرفة الوحيدة قبل ما الفريق يأكّد
        from app.modules.pms.schemas import BookingCreate
        from app.modules.pms.services import create_booking as pms_create_booking
        pms_create_booking(db, BookingCreate(
            branch_id=branch.id, guest_name="ضيف تاني",
            check_in=booking.check_in, check_out=booking.check_out,
            room_ids=[room.id],
        ))

        confirm_resp = client.post(
            f"/api/v1/hub/online-bookings/{booking.id}/confirm", headers=manager_headers,
        )
        assert confirm_resp.status_code == 400  # صفر مرشحين متاحين — الطلب يفضل pending
        db.refresh(booking)
        assert booking.status == "pending"
        assert booking.pms_booking_id is None

    def test_room_unavailable_at_confirm_time_stays_pending(
        self, client: TestClient, db, monkeypatch, manager_headers,
    ):
        branch, host = _site(monkeypatch, db)
        rt = _priced_room_type(db, branch)
        # مفيش أي غرفة فعلية من هذا النوع خالص

        resp = self._submit(client, host, room_type_id=rt.id)
        from app.modules.hub.models import HubOnlineBooking
        booking = db.query(HubOnlineBooking).filter_by(public_reference=resp.json()["reference"]).one()

        confirm_resp = client.post(
            f"/api/v1/hub/online-bookings/{booking.id}/confirm", headers=manager_headers,
        )
        assert confirm_resp.status_code == 400
        db.refresh(booking)
        assert booking.status == "pending"

    def test_bundle_booking_confirm_reserves_both_units_atomically(
        self, client: TestClient, db, monkeypatch, manager_headers,
    ):
        branch, host = _site(monkeypatch, db)
        chalet_type = _priced_room_type(db, branch, base_rate="3500.00", max_occupancy=4, name="Chalet")
        studio_type = _priced_room_type(db, branch, base_rate="2500.00", max_occupancy=2, name="Studio")
        chalet_room = _room(db, branch, chalet_type, "102A")
        studio_room = _room(db, branch, studio_type, "102S")
        bundle = _bundle(db, branch, chalet_room, studio_room)

        resp = self._submit(client, host, bundle_id=bundle.id, adults=6)
        assert resp.status_code == 202, resp.text
        from app.modules.hub.models import HubOnlineBooking
        booking = db.query(HubOnlineBooking).filter_by(public_reference=resp.json()["reference"]).one()

        confirm_resp = client.post(
            f"/api/v1/hub/online-bookings/{booking.id}/confirm", headers=manager_headers,
        )
        assert confirm_resp.status_code == 200, confirm_resp.text
        pms_booking_id = confirm_resp.json()["pms_booking_id"]
        assert pms_booking_id is not None

        from app.modules.pms.models import Booking
        pms_booking = db.query(Booking).filter_by(id=pms_booking_id).one()
        assert len(pms_booking.rooms) == 2
        assert pms_booking.room_bundle_id == bundle.id
        assert pms_booking.total_rate == Decimal("9000.00")  # 4500 * 2 ليلة

    def test_bundle_confirm_conflicts_when_one_unit_already_booked_individually(
        self, client: TestClient, db, monkeypatch, manager_headers,
    ):
        branch, host = _site(monkeypatch, db)
        chalet_type = _priced_room_type(db, branch, base_rate="3500.00", max_occupancy=4, name="Chalet")
        studio_type = _priced_room_type(db, branch, base_rate="2500.00", max_occupancy=2, name="Studio")
        chalet_room = _room(db, branch, chalet_type, "111A")
        studio_room = _room(db, branch, studio_type, "111S")
        bundle = _bundle(db, branch, chalet_room, studio_room)

        resp = self._submit(client, host, bundle_id=bundle.id, adults=6)
        from app.modules.hub.models import HubOnlineBooking
        booking = db.query(HubOnlineBooking).filter_by(public_reference=resp.json()["reference"]).one()

        # حد تاني يحجز نص الزوج (الاستوديو بس) قبل ما الفريق يأكّد الباقة
        from app.modules.pms.schemas import BookingCreate
        from app.modules.pms.services import create_booking as pms_create_booking
        pms_create_booking(db, BookingCreate(
            branch_id=branch.id, guest_name="ضيف استوديو منفرد",
            check_in=booking.check_in, check_out=booking.check_out,
            room_ids=[studio_room.id],
        ))

        confirm_resp = client.post(
            f"/api/v1/hub/online-bookings/{booking.id}/confirm", headers=manager_headers,
        )
        assert confirm_resp.status_code == 409
        db.refresh(booking)
        assert booking.status == "pending"
        # الشاليه (اللي كان متاح فعليًا) لازم يفضل غير محجوز — مفيش حجز نص باقة
        db.refresh(chalet_room)
        assert chalet_room.status == "available"
