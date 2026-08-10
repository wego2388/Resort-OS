"""tests/test_hist_hub.py — HIST-01 Hub/CRM generator (OPS-DATA-02 §10.3).
يعيد استخدام نفس فيكستشر test_hist_pms_bookings.py المعزولة (SQLite
منفصل + branch مسعّر فعليًا عبر replace_room_inventory/activate_room_
pricing) عشان confirm_booking's real PMS leg يشتغل ضد أسعار حقيقية معتمدة،
مش mock."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.hist_hub import generate as generate_hub
from tests.test_hist_pms_bookings import _real_branch_with_pricing, hist_db  # noqa: F401


class _Ctx:
    def __init__(self, branch_id: int):
        self.branch_id = branch_id
        self.period_year = 2026
        self.period_month = 7
        self.tz_name = "Africa/Cairo"


class TestHistHubGenerator:
    def test_generate_creates_twelve_requests_with_correct_status_split(self, hist_db: Session):
        db = hist_db
        branch = _real_branch_with_pricing(db)

        result = generate_hub(db, _Ctx(branch.id))

        counts = result["counts"]
        assert counts["hub_requests_total"] == 12
        assert counts["hub_confirmed"] == 2
        assert counts["hub_cancelled"] == 3
        assert counts["hub_pending"] == 7
        assert counts["hub_confirmed"] + counts["hub_cancelled"] + counts["hub_pending"] == 12

    def test_confirmed_requests_actually_link_real_pms_bookings(self, hist_db: Session):
        """أول فرع HIST معزول (مفيش أي حجز تاني منافس على الغرف) — الاتنين
        المؤكدين المفروض يلاقوا غرفة فعليًا فاضية ويترحطوا بـPMS booking
        حقيقي، مش مجرد status='confirmed' فاضي."""
        from app.modules.hub.models import HubOnlineBooking

        db = hist_db
        branch = _real_branch_with_pricing(db)

        result = generate_hub(db, _Ctx(branch.id))
        db.commit()

        assert result["counts"]["hub_confirmed_with_pms_booking"] == 2
        confirmed = (
            db.query(HubOnlineBooking)
            .filter(HubOnlineBooking.branch_id == branch.id, HubOnlineBooking.status == "confirmed")
            .all()
        )
        assert len(confirmed) == 2
        assert all(b.pms_booking_id is not None for b in confirmed)

    def test_contact_forms_created_with_correct_consent_split(self, hist_db: Session):
        from app.modules.hub.models import ContactForm

        db = hist_db
        branch = _real_branch_with_pricing(db)

        generate_hub(db, _Ctx(branch.id))
        db.commit()

        forms = db.query(ContactForm).filter(ContactForm.branch_id == branch.id).all()
        assert len(forms) == 5
        assert all(f.service_contact_authorized for f in forms)
        consenting = [f for f in forms if f.marketing_consent]
        assert len(consenting) == 2
        assert all(f.marketing_consent_version == "v1" for f in consenting)
        assert all(f.lead_id is not None and f.crm_sync_status == "created" for f in consenting)
        non_consenting = [f for f in forms if not f.marketing_consent]
        assert len(non_consenting) == 3
        assert all(f.lead_id is None and f.crm_sync_status == "not_requested" for f in non_consenting)

    def test_marketing_leads_created_matching_contact_form_count(self, hist_db: Session):
        from app.modules.crm.models import Lead

        db = hist_db
        branch = _real_branch_with_pricing(db)

        result = generate_hub(db, _Ctx(branch.id))
        db.commit()

        assert result["counts"]["marketing_leads_created"] == 2
        leads = db.query(Lead).filter(Lead.branch_id == branch.id).all()
        assert len(leads) == 2
        assert all(l.marketing_consent for l in leads)

    def test_customer_and_opportunity_created_without_phone_duplication(self, hist_db: Session):
        """الهاتف 01011110001 بيتكرر عمدًا بين أول طلب Hub وأول contact form
        بموافقة تسويقية (نفس الضيف رجع تاني) — لازم عميل واحد بس، مش اتنين."""
        from app.modules.crm.models import Customer, Opportunity

        db = hist_db
        branch = _real_branch_with_pricing(db)

        generate_hub(db, _Ctx(branch.id))
        db.commit()

        customers = (
            db.query(Customer)
            .filter(Customer.branch_id == branch.id, Customer.phone == "01011110001")
            .all()
        )
        assert len(customers) == 1

        opportunities = db.query(Opportunity).filter(Opportunity.customer_id == customers[0].id).all()
        assert len(opportunities) == 1
        assert opportunities[0].expected_value == Decimal("5000.00")
