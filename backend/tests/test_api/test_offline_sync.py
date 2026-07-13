"""
tests/test_api/test_offline_sync.py
Offline POS sync — fulfilled / partial / rejected / idempotent retry.
Contract: 07-BUSINESS-RULES.md § 9.

راجع DINING_CUTOVER_PLAN.md Batch 6 — بورتت لـ dining.services.sync_offline_order
بدل restaurant.services.sync_offline_order القديمة اللي اتحذفت. dining هو
الـ backend الحقيقي لـ UnifiedPOSView.vue's useOfflineQueue('dining') من
Batch 1 — كانت فجوة تغطية حقيقية (صفر تست) قبل البورت ده.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.modules.dining import services
from app.modules.dining.schemas import OrderItemCreate, OrderSyncRequest, OutletCreate


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Sync Branch", name_ar="فرع",
               code=f"SYN-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_outlet(db, branch):
    return services.create_outlet(db, OutletCreate(
        branch_id=branch.id, name="مطعم مزامنة", outlet_type="restaurant",
        revenue_account_code="4200",
    ))


def make_item(db, branch, outlet, available=True, name="صنف"):
    from app.modules.dining.models import DiningItem
    item = DiningItem(branch_id=branch.id, outlet_id=outlet.id, name=name,
                       price=Decimal("55.00"), is_available=available)
    db.add(item)
    db.commit()
    return item


class TestOfflineSync:
    def test_fulfilled_when_all_items_available(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        data = OrderSyncRequest(
            local_id=str(uuid.uuid4()), outlet_id=outlet.id,
            items=[OrderItemCreate(item_id=item.id, quantity=2)],
        )
        result = services.sync_offline_order(db, branch.id, data)
        assert result["status"] == "fulfilled"
        assert result["order_id"] is not None
        assert result["rejected_items"] == []

    def test_partial_when_some_items_unavailable(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        available_item = make_item(db, branch, outlet, available=True, name="متاح")
        unavailable_item = make_item(db, branch, outlet, available=False, name="غير متاح")
        data = OrderSyncRequest(
            local_id=str(uuid.uuid4()), outlet_id=outlet.id,
            items=[
                OrderItemCreate(item_id=available_item.id, quantity=1),
                OrderItemCreate(item_id=unavailable_item.id, quantity=3),
            ],
        )
        result = services.sync_offline_order(db, branch.id, data)
        assert result["status"] == "partial"
        assert result["order_id"] is not None
        assert len(result["rejected_items"]) == 1
        assert result["rejected_items"][0]["item_id"] == unavailable_item.id
        assert result["rejected_items"][0]["requested_qty"] == 3
        assert result["rejected_items"][0]["reason"] == "out_of_stock"

    def test_rejected_when_all_items_unavailable(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet, available=False)
        data = OrderSyncRequest(
            local_id=str(uuid.uuid4()), outlet_id=outlet.id,
            items=[OrderItemCreate(item_id=item.id, quantity=1)],
        )
        result = services.sync_offline_order(db, branch.id, data)
        assert result["status"] == "rejected"
        assert result["order_id"] is None
        assert len(result["rejected_items"]) == 1

    def test_idempotent_retry_does_not_duplicate_order(self, db):
        branch = make_branch(db)
        outlet = make_outlet(db, branch)
        item = make_item(db, branch, outlet)
        local_id = str(uuid.uuid4())
        data = OrderSyncRequest(local_id=local_id, outlet_id=outlet.id,
                                 items=[OrderItemCreate(item_id=item.id, quantity=1)])

        first = services.sync_offline_order(db, branch.id, data)
        second = services.sync_offline_order(db, branch.id, data)

        assert first["order_id"] == second["order_id"]
        assert second["message"] != first["message"]  # second is the "already recorded" path

        from app.modules.dining.models import DiningOrder
        count = db.query(DiningOrder).filter(DiningOrder.client_local_id == local_id).count()
        assert count == 1
