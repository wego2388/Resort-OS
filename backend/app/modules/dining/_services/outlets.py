"""
app/modules/dining/_services/outlets.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from sqlalchemy.orm import Session
from app.modules.dining import crud
from app.modules.dining.models import Outlet


def create_outlet(db: Session, data) -> Outlet:
    outlet = crud.create_outlet(db, data)
    db.commit()
    db.refresh(outlet)
    return outlet


def update_outlet(db: Session, outlet_id: int, data) -> Outlet:
    outlet = crud.get_outlet(db, outlet_id)
    if not outlet:
        raise ValueError(f"المنفذ {outlet_id} غير موجود")
    outlet = crud.update_outlet(db, outlet, data)
    db.commit()
    db.refresh(outlet)
    return outlet
