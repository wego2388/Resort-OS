"""app/modules/timeshare/_services/waitlist.py — waitlist entries for
contracts wanting a not-currently-available week/unit."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.timeshare import crud
from app.modules.timeshare.schemas import WaitlistCreate

from .contracts import get_contract_or_404


def add_to_waitlist(db: Session, data: WaitlistCreate) -> object:
    get_contract_or_404(db, data.contract_id)
    if data.requested_end <= data.requested_start:
        raise ValueError("تاريخ النهاية يجب أن يكون بعد تاريخ البداية")
    obj = crud.create_waitlist_entry(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def update_waitlist_status(db: Session, waitlist_id: int, new_status: str) -> object:
    """تحكم يدوي من الموظف — confirmed (اتحجزله فعليًا خارج هذا المسار عبر
    visits.create_visit العادية) أو cancelled (العميل ملوش نية تاني). راجع
    app.tasks.timeshare_tasks.process_waitlist للانتقالات النظامية
    (waiting→notified، notified→expired)."""
    entry = crud.get_waitlist_entry(db, waitlist_id)
    if not entry:
        raise ValueError(f"عنصر قائمة الانتظار {waitlist_id} غير موجود")
    if entry.status not in ("waiting", "notified"):
        raise ValueError(f"عنصر قائمة الانتظار ده حالته '{entry.status}' بالفعل — مينفعش يتغيّر")
    entry.status = new_status
    db.commit()
    db.refresh(entry)
    return entry
