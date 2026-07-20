"""
app/modules/core/api/step_up_utils.py
═══════════════════════════════════════════════════════════════════════
Shared router-layer helper for consuming a Gate 2B3A step-up proof and
translating the result into HTTP responses. Deliberately lives at the API
layer (not core.services) because it raises HTTPException directly — per
CLAUDE.md §4 that belongs in api/router.py, not services.py.

Every module whose router protects a mutation with a step-up proof
(core, and now finance/dining for Gate 4's payment_void/dining_refund)
imports this single function instead of hand-rolling its own copy — the
original private version of this lived only inside core/api/router.py,
duplicating it per-module would have violated CLAUDE.md §3.5 (no repeated
logic) the moment a second module needed it.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session


def consume_step_up_or_raise(
    db: Session,
    user,
    request: Request,
    *,
    purpose: str,
    scope_hash: str,
    x_step_up_token: Optional[str],
) -> dict:
    """Consumes a one-time step-up grant bound to ``purpose``/``scope_hash``
    for the current user's access token/session. Raises 428 if no token was
    presented, 403 if the token is missing/expired/replayed/wrong-purpose/
    wrong-scope/wrong-user/wrong-session (deliberately indistinguishable —
    see consume_step_up's own docstring). Returns the grant's
    ``public_reference``/``assurance_method`` on success."""
    if not x_step_up_token:
        raise HTTPException(
            status.HTTP_428_PRECONDITION_REQUIRED,
            {
                "error_code": "STEP_UP_REQUIRED",
                "message": "يلزم إثبات هوية حديث (كلمة السر + التحقق بخطوتين) قبل تنفيذ هذا الإجراء",
            },
        )

    from app.core.config import settings as app_settings  # noqa: PLC0415
    from app.core.kernel.auth.service import AuthService  # noqa: PLC0415
    from app.core.kernel.auth.step_up import access_token_hash_from_request  # noqa: PLC0415
    from app.core.kernel.models.user import User as _KernelUser  # noqa: PLC0415

    auth_service = AuthService(db, _KernelUser, app_settings)
    result = auth_service.consume_step_up(
        user_id=user.id,
        purpose=purpose,
        scope_hash=scope_hash,
        access_token_hash=access_token_hash_from_request(request),
        token=x_step_up_token,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {
                "error_code": "STEP_UP_INVALID",
                "message": "إثبات الهوية غير صالح أو منتهي أو مُستخدَم بالفعل — أعد التأكيد وحاول تاني",
            },
        )
    return result
