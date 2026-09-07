"""
app/modules/core/_services/_audit_helpers.py
Extracted from app/modules/core/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

import json
from typing import Optional
from sqlalchemy.orm import Session
from app.modules.core import crud
from app.modules.core.schemas import (
    AuditLogCreate,
)


def _step_up_audit_context(
    *,
    reason: Optional[str] = None,
    step_up_public_reference: Optional[str] = None,
    assurance_method: Optional[str] = None,
) -> dict:
    from app.core.kernel.correlation import get_request_id  # noqa: PLC0415

    context: dict = {}
    if reason is not None:
        context["reason"] = reason
    if step_up_public_reference is not None:
        context["step_up_public_reference"] = step_up_public_reference
    if assurance_method is not None:
        context["assurance_method"] = assurance_method
    request_id = get_request_id()
    if request_id:
        context["request_id"] = request_id
    return context


def _commit_rejected_control_plane_audit(
    db: Session,
    *,
    actor_id: int,
    action: str,
    target_user_id: Optional[int],
    reason_code: str,
    reason: Optional[str] = None,
    step_up_public_reference: Optional[str] = None,
    assurance_method: Optional[str] = None,
    branch_id: Optional[int] = None,
    details: Optional[dict] = None,
) -> None:
    """Persist an attributable, secret-free audit row for a rejected
    super-admin control-plane mutation before raising its domain exception.

    Gate 2A deliberately logged these attempts only to the process logger;
    Gate 2B3B closes that deferred gap in the existing unified ``AuditLog``.
    No business mutation has happened at these call sites, so the commit
    contains only the rejection record and releases any ordered row locks.
    """
    payload = {
        "reason_code": reason_code,
        **(details or {}),
        **_step_up_audit_context(
            reason=reason,
            step_up_public_reference=step_up_public_reference,
            assurance_method=assurance_method,
        ),
    }
    crud.create_audit_log(db, AuditLogCreate(
        user_id=actor_id,
        branch_id=branch_id,
        action=action,
        entity_type="user" if target_user_id is not None else "security_control_plane",
        entity_id=target_user_id,
        new_data=json.dumps(payload, ensure_ascii=False, sort_keys=True),
    ))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
