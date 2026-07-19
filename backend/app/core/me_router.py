"""app/core/me_router.py

Current-user self-service surface, mounted alongside
app.core.kernel.auth.router's build_auth_router() at the same prefix
(``{API_PREFIX}/auth``). The kernel's base User model has no project-specific
fields, so this stays a small separate router rather than growing the generic
auth router with resort-os-only response fields.

Endpoints:
  GET   /auth/me              — current-user DTO (UserRead)
  PATCH /auth/me/preferences  — update own personal preferences (Gate 3A)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.core.rate_limit import _client_ip
from app.modules.core import services as core_services
from app.modules.core.schemas import (
    UserPreferencesUpdate,
    UserRead,
)

router = APIRouter()


@router.get("/me", response_model=UserRead)
def me(user=Depends(get_current_active_user)):
    return UserRead.model_validate(user)


@router.patch("/me/preferences", response_model=UserRead)
def update_my_preferences(
    payload: UserPreferencesUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """Update the authenticated user's own personal preferences.

    - The target user is derived from the auth token; no ``user_id`` is
      accepted, so a user can only change their own preference (Decision
      0002 §4).
    - No administrative permission is required — language is a personal
      display choice, not an authorization or business setting.
    - Changing language never touches currency, prices, tax, or any financial
      configuration; only ``preferred_language`` is written here.
    - Real-change guard: a no-op (same canonical value already stored) neither
      writes nor emits an audit event, keeping the audit log free of noise.
    """
    updated = core_services.update_user_preferences(
        db,
        user=user,
        preferred_language=payload.preferred_language,
        ip_address=_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
    )
    return UserRead.model_validate(updated)
