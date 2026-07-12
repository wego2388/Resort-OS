"""tests/test_api/test_crm_leads.py"""
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal

import pytest

from tests.test_api.test_pms import make_branch, make_room, make_room_type


class TestLeads:

    def test_create_lead(self, db):
        from app.modules.crm.crud import create_lead
        branch = make_branch(db)
        lead = create_lead(db, {
            "branch_id": branch.id,
            "full_name": "أحمد محمد",
            "phone": "01012345678",
            "interest": "timeshare",
            "stage": "new",
            "expected_value": Decimal("50000"),
        })
        assert lead.id is not None
        assert lead.stage == "new"

    def test_update_lead_stage(self, db):
        from app.modules.crm.crud import create_lead, update_lead, get_lead
        branch = make_branch(db)
        lead = create_lead(db, {
            "branch_id": branch.id,
            "full_name": "سارة علي",
            "stage": "new",
            "interest": "leasing",
        })
        updated = update_lead(db, lead, {"stage": "contacted"})
        assert updated.stage == "contacted"

    def test_list_leads_by_stage(self, db):
        from app.modules.crm.crud import create_lead, list_leads
        branch = make_branch(db)
        for stage in ["new", "new", "qualified"]:
            create_lead(db, {
                "branch_id": branch.id,
                "full_name": f"ضيف {stage}",
                "stage": stage,
                "interest": "other",
            })
        new_leads = list_leads(db, branch.id, stage="new")
        assert len(new_leads) >= 2

    def test_list_all_leads(self, db):
        from app.modules.crm.crud import create_lead, list_leads
        branch = make_branch(db)
        for i in range(3):
            create_lead(db, {
                "branch_id": branch.id,
                "full_name": f"عميل {i}",
                "stage": "new",
                "interest": "booking",
            })
        all_leads = list_leads(db, branch.id)
        assert len(all_leads) >= 3


class TestLeadConvert:
    """wagdy.md C-03 — POST /crm/leads/{id}/convert (services.convert_lead_to_booking)."""

    def _make_lead(self, db, branch, **overrides):
        from app.modules.crm.crud import create_lead
        data = {
            "branch_id": branch.id,
            "full_name": "خالد إبراهيم",
            "phone": "01055512345",
            "email": "khaled@example.com",
            "interest": "booking",
            "stage": "new",
            "expected_value": Decimal("0"),
        }
        data.update(overrides)
        return create_lead(db, data)

    def test_convert_creates_booking_and_marks_lead_won(self, db):
        from app.modules.crm.schemas import LeadConvertRequest
        from app.modules.crm.services import convert_lead_to_booking

        branch = make_branch(db)
        room_type = make_room_type(db, branch)
        room = make_room(db, branch, room_type)
        lead = self._make_lead(db, branch)

        check_in = date.today() + timedelta(days=5)
        check_out = check_in + timedelta(days=2)
        updated_lead, booking = convert_lead_to_booking(db, lead.id, LeadConvertRequest(
            check_in=check_in, check_out=check_out, room_ids=[room.id],
        ))

        assert updated_lead.stage == "won"
        assert updated_lead.won_at is not None
        assert updated_lead.booking_id == booking.id
        assert booking.guest_name == lead.full_name
        assert booking.guest_phone == lead.phone
        assert booking.branch_id == branch.id
        assert booking.status == "confirmed"

    def test_convert_already_won_lead_raises(self, db):
        from app.modules.crm.schemas import LeadConvertRequest
        from app.modules.crm.services import convert_lead_to_booking

        branch = make_branch(db)
        room_type = make_room_type(db, branch)
        room = make_room(db, branch, room_type)
        lead = self._make_lead(db, branch, stage="won")

        with pytest.raises(ValueError, match="حالة نهائية"):
            convert_lead_to_booking(db, lead.id, LeadConvertRequest(
                check_in=date.today() + timedelta(days=1),
                check_out=date.today() + timedelta(days=2),
                room_ids=[room.id],
            ))

    def test_convert_lost_lead_raises(self, db):
        from app.modules.crm.schemas import LeadConvertRequest
        from app.modules.crm.services import convert_lead_to_booking

        branch = make_branch(db)
        room_type = make_room_type(db, branch)
        room = make_room(db, branch, room_type)
        lead = self._make_lead(db, branch, stage="lost", lost_reason="مش مهتم")

        with pytest.raises(ValueError, match="حالة نهائية"):
            convert_lead_to_booking(db, lead.id, LeadConvertRequest(
                check_in=date.today() + timedelta(days=1),
                check_out=date.today() + timedelta(days=2),
                room_ids=[room.id],
            ))

    def test_convert_unknown_room_raises(self, db):
        from app.modules.crm.schemas import LeadConvertRequest
        from app.modules.crm.services import convert_lead_to_booking

        branch = make_branch(db)
        lead = self._make_lead(db, branch)

        with pytest.raises(ValueError):
            convert_lead_to_booking(db, lead.id, LeadConvertRequest(
                check_in=date.today() + timedelta(days=1),
                check_out=date.today() + timedelta(days=2),
                room_ids=[999999],
            ))

    def test_convert_unknown_lead_raises(self, db):
        from app.modules.crm.schemas import LeadConvertRequest
        from app.modules.crm.services import convert_lead_to_booking

        with pytest.raises(ValueError, match="غير موجود"):
            convert_lead_to_booking(db, 999999, LeadConvertRequest(
                check_in=date.today() + timedelta(days=1),
                check_out=date.today() + timedelta(days=2),
                room_ids=[1],
            ))


class TestGuestProfile:

    def test_create_guest_profile(self, db):
        from app.modules.crm.crud import get_or_create_guest_profile
        branch = make_branch(db)
        profile = get_or_create_guest_profile(db, branch.id, "01098765432", {
            "full_name": "محمود حسن",
        })
        assert profile.id is not None
        assert profile.phone == "01098765432"

    def test_idempotent_profile_creation(self, db):
        from app.modules.crm.crud import get_or_create_guest_profile
        from app.modules.crm.models import GuestProfile
        branch = make_branch(db)
        phone = "01099887766"
        get_or_create_guest_profile(db, branch.id, phone, {"full_name": "ضيف أول"})
        get_or_create_guest_profile(db, branch.id, phone, {"full_name": "ضيف ثانٍ"})
        count = db.query(GuestProfile).filter(
            GuestProfile.branch_id == branch.id,
            GuestProfile.phone == phone,
        ).count()
        assert count == 1  # لا يُنشئ اثنين

    def test_update_guest_on_checkout(self, db):
        from app.modules.crm.crud import get_or_create_guest_profile, update_guest_profile_on_checkout
        branch = make_branch(db)
        phone = "01011223344"
        get_or_create_guest_profile(db, branch.id, phone, {"full_name": "ضيف متكرر"})

        update_guest_profile_on_checkout(db, branch.id, phone, Decimal("2000"))
        profile = get_or_create_guest_profile(db, branch.id, phone, {})
        assert profile.total_visits == 1
        assert profile.last_stay is not None
