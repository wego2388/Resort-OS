"""
app/modules/dining/_services/kds.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from app.modules.dining import crud
from app.modules.dining.models import DiningKitchenTicket
from app.modules.dining._services._helpers import (
    _lock_order_or_conflict,
)


def _order_item_statuses(db: Session, item_ids: set[int]) -> dict[int, str]:
    """(order_item_id → status) لمجموعة أصناف — استعلام واحد بدل N+1 لكل
    تذكرة عند تجميع عدة تذاكر مع بعض. راجع
    restaurant.services._order_item_statuses — نفس المنطق بالظبط."""
    if not item_ids:
        return {}
    from app.modules.dining.models import DiningOrderItem  # noqa: PLC0415
    return dict(db.query(DiningOrderItem.id, DiningOrderItem.status).filter(DiningOrderItem.id.in_(item_ids)).all())


def _ticket_read_dict(ticket: DiningKitchenTicket, status_by_item_id: dict[int, str]) -> dict:
    """يبني dict متوافق مع KitchenTicketRead — بيضيف حالة كل صنف اللحظية
    (status) جوه items_snapshot من DiningOrderItem.status الحقيقي، بدل ما
    يفضل items_snapshot (JSON ثابت وقت إنشاء التذكرة) بيقول 'pending'
    للأبد حتى لو الصنف اتأكد فعليًا (bump فردي — راجع bump_order_item_status).
    راجع restaurant.services._ticket_read_dict — نفس المنطق بالظبط."""
    items_snapshot = [
        {**entry, "status": status_by_item_id.get(entry.get("order_item_id"), "pending")}
        for entry in ticket.items_snapshot
    ]
    return {
        "id": ticket.id,
        "branch_id": ticket.branch_id,
        "outlet_id": ticket.outlet_id,
        "order_id": ticket.order_id,
        "station": ticket.station,
        "items_snapshot": items_snapshot,
        "status": ticket.status,
        "created_at": ticket.created_at,
    }


def get_kds_tickets(
    db: Session,
    branch_id: int,
    outlet_id: Optional[int] = None,
    stations: Optional[list[str]] = None,
) -> list[dict]:
    """يرجّع تذاكر الـ KDS المعلقة لفرع معيّن — كل تذكرة بترجع مع حالة كل
    صنف اللحظية (راجع _ticket_read_dict)، استعلام واحد لكل الأصناف عبر كل
    التذاكر المرجّعة، مش N+1 لكل تذكرة. راجع restaurant.services.get_kds_tickets."""
    tickets = crud.list_pending_tickets(db, branch_id, outlet_id=outlet_id, stations=stations)
    item_ids = {
        entry.get("order_item_id")
        for t in tickets
        for entry in t.items_snapshot
        if entry.get("order_item_id") is not None
    }
    status_by_item_id = _order_item_statuses(db, item_ids)
    return [_ticket_read_dict(t, status_by_item_id) for t in tickets]


def update_kitchen_ticket_status(db: Session, ticket_id: int, new_status: str) -> dict:
    """يحدّث حالة تذكرة كاملة يدويًا (pending/in_progress/done) — تأكيد
    دفعة واحدة، بدل صنف بصنف (راجع bump_order_item_status). لو التذكرة
    اتأكدت كاملة (done)، أي صنف لسه pending/in_kitchen جواها بيترقّى لـ
    'ready' تلقائيًا — عشان DiningOrderItem.status وحالة التذكرة يفضلوا
    متسقين. راجع restaurant.services.update_kitchen_ticket_status."""
    from app.modules.dining.models import DiningOrderItem  # noqa: PLC0415

    ticket = db.query(DiningKitchenTicket).filter(DiningKitchenTicket.id == ticket_id).first()
    if not ticket:
        raise ValueError(f"التذكرة {ticket_id} غير موجودة")
    order = _lock_order_or_conflict(db, ticket.order_id)
    if order.status not in ("held", "open", "in_kitchen", "served"):
        raise ValueError(
            f"لا يمكن تحديث تذكرة مطبخ لطلب بحالة '{order.status}'"
        )

    ticket = crud.update_ticket_status(db, ticket_id, new_status)
    if not ticket:
        raise ValueError(f"التذكرة {ticket_id} غير موجودة")

    if new_status == "done" and ticket.items_snapshot:
        item_ids = {
            entry.get("order_item_id") for entry in ticket.items_snapshot
            if entry.get("order_item_id") is not None
        }
        if item_ids:
            db.query(DiningOrderItem).filter(
                DiningOrderItem.id.in_(item_ids),
                DiningOrderItem.status.in_(("pending", "in_kitchen")),
            ).update({"status": "ready"}, synchronize_session=False)

    db.commit()
    db.refresh(ticket)

    item_ids = {e.get("order_item_id") for e in ticket.items_snapshot if e.get("order_item_id") is not None}
    return _ticket_read_dict(ticket, _order_item_statuses(db, item_ids))
