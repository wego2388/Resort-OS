"""tests/test_api/test_crm_leads.py"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from tests.test_api.test_pms import make_branch


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
