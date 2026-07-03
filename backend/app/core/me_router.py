"""app/core/me_router.py

GET /api/v1/auth/me — mounted alongside app.core.kernel.auth.router's
build_auth_router() at the same prefix. The kernel's base User model has no
project-specific fields, so this stays a small separate router rather than
growing the generic auth router with resort-os-only response fields.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_active_user
from app.modules.core.schemas import UserRead

router = APIRouter()


@router.get("/me", response_model=UserRead)
def me(user=Depends(get_current_active_user)):
    return UserRead.model_validate(user)
