"""
tests/test_api/test_crm.py
Integration tests for CRM module.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.crm.schemas import (
    ActivityCreate, BlacklistRequest, CustomerCreate,
    InteractionCreate, OpportunityCreate, OpportunityUpdate,
)
from app.modules.crm import services, crud


@pytest.fixture
def branch(db: Session):
    import uuid
    from app.modules.core.models import Branch
    b = Branch(name="Test", name_ar="اختبار", code=f"CRM-{uuid.uuid4().hex[:6].upper()}")
    db.add(b); db.flush()
    return b


@pytest.fixture
def customer(db: Session, branch):
    data = CustomerCreate(
        branch_id=branch.id,
        full_name="سارة عبدالله",
        phone="01002000000",
        segment="vip",
    )
    return services.create_customer(db, data)


class TestCustomer:

    def test_create_customer(self, db, branch):
        data = CustomerCreate(branch_id=branch.id, full_name="عميل جديد")
        c = services.create_customer(db, data)
        assert c.id is not None
        assert c.segment == "regular"
        assert not c.blacklisted

    def test_blacklist_customer(self, db, customer):
        req = BlacklistRequest(reason="عدم السداد المتكرر")
        bl = services.blacklist_customer(db, customer.id, req)
        assert bl.blacklisted
        assert bl.blacklist_reason == "عدم السداد المتكرر"

    def test_cannot_blacklist_twice(self, db, customer):
        req = BlacklistRequest(reason="سبب ما")
        services.blacklist_customer(db, customer.id, req)
        with pytest.raises(ValueError, match="مسبقاً"):
            services.blacklist_customer(db, customer.id, req)

    def test_unblacklist(self, db, customer):
        req = BlacklistRequest(reason="سبب مقبول للتجميد")
        services.blacklist_customer(db, customer.id, req)
        restored = services.unblacklist_customer(db, customer.id)
        assert not restored.blacklisted
        assert restored.blacklist_reason is None

    def test_customer_not_found(self, db):
        with pytest.raises(ValueError):
            services.get_customer_or_404(db, 9999)


class TestInteraction:

    def test_log_interaction(self, db, branch, customer):
        data = InteractionCreate(
            customer_id=customer.id,
            branch_id=branch.id,
            interaction_type="whatsapp",
            direction="outbound",
            summary="اتصلنا لتأكيد الحجز",
            occurred_at=datetime.utcnow(),
        )
        interaction = services.log_interaction(db, data, handled_by=1)
        assert interaction.id is not None
        assert interaction.handled_by == 1

    def test_interaction_invalid_customer_raises(self, db, branch):
        data = InteractionCreate(
            customer_id=9999,
            branch_id=branch.id,
            interaction_type="call",
            direction="inbound",
            summary="مكالمة مجهولة",
            occurred_at=datetime.utcnow(),
        )
        with pytest.raises(ValueError):
            services.log_interaction(db, data, handled_by=1)


class TestOpportunity:

    def test_create_opportunity(self, db, branch, customer):
        data = OpportunityCreate(
            branch_id=branch.id,
            customer_id=customer.id,
            title="بيع وحدة تايم شير 2R",
            product_type="timeshare",
            expected_value=Decimal("120000"),
            probability=60,
        )
        opp = services.create_opportunity(db, data)
        assert opp.stage == "lead"
        assert opp.closed_at is None

    def test_close_won(self, db, branch, customer):
        data = OpportunityCreate(
            branch_id=branch.id, customer_id=customer.id,
            title="فرصة", product_type="leasing",
        )
        opp = services.create_opportunity(db, data)
        update = OpportunityUpdate(stage="won")
        closed = services.update_opportunity(db, opp.id, update)
        assert closed.stage == "won"
        assert closed.closed_at is not None

    def test_close_lost_requires_reason(self, db, branch, customer):
        data = OpportunityCreate(
            branch_id=branch.id, customer_id=customer.id,
            title="فرصة", product_type="other",
        )
        opp = services.create_opportunity(db, data)
        update = OpportunityUpdate(stage="lost")  # بدون lost_reason
        with pytest.raises(ValueError, match="سبب الخسارة"):
            services.update_opportunity(db, opp.id, update)

    def test_cannot_update_closed_opportunity(self, db, branch, customer):
        data = OpportunityCreate(
            branch_id=branch.id, customer_id=customer.id,
            title="فرصة", product_type="other",
        )
        opp = services.create_opportunity(db, data)
        services.update_opportunity(db, opp.id, OpportunityUpdate(stage="won"))
        with pytest.raises(ValueError, match="مغلقة"):
            services.update_opportunity(db, opp.id, OpportunityUpdate(stage="proposal"))


class TestActivity:

    def test_create_activity(self, db, branch, customer):
        data = ActivityCreate(
            branch_id=branch.id, customer_id=customer.id,
            activity_type="follow_up",
            title="متابعة العرض",
            due_date=date(2026, 8, 1),
        )
        act = services.create_activity(db, data)
        assert act.status == "pending"

    def test_mark_done(self, db, branch, customer):
        from app.modules.crm.schemas import ActivityUpdate
        data = ActivityCreate(
            branch_id=branch.id, customer_id=customer.id,
            activity_type="meeting", title="اجتماع",
            due_date=date(2026, 8, 1),
        )
        act = services.create_activity(db, data)
        done = services.update_activity(db, act.id, ActivityUpdate(status="done"))
        assert done.status == "done"
        assert done.done_at is not None

    def test_cannot_update_done_activity(self, db, branch, customer):
        from app.modules.crm.schemas import ActivityUpdate
        data = ActivityCreate(
            branch_id=branch.id, customer_id=customer.id,
            activity_type="follow_up", title="متابعة",
            due_date=date(2026, 8, 1),
        )
        act = services.create_activity(db, data)
        services.update_activity(db, act.id, ActivityUpdate(status="done"))
        with pytest.raises(ValueError, match="منتهٍ"):
            services.update_activity(db, act.id, ActivityUpdate(title="تعديل"))
