"""app/core/me_router.py

GET /api/v1/auth/me — resort-os-specific addition, mounted alongside wego-core's
shared `build_auth_router()` at the same prefix. wego-core's base User model has
no project-specific fields, so this stays local rather than touching the shared
auth router (which is installed across 5 other wego-core products, one of them
live in production) for a single-project need.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import get_current_active_user
from app.modules.core.schemas import UserRead

router = APIRouter()


@router.get("/me", response_model=UserRead)
def me(user=Depends(get_current_active_user)):
    return UserRead.model_validate(user)
