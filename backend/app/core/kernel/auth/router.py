"""
app/core/kernel/auth/router.py
Pluggable auth router — mounted in app/main.py.

Endpoints:
    POST /login                    → access_token
    POST /register                 → user object
    POST /refresh                  → new access_token
    POST /logout                   → revokes token
    POST /change-password          → bool
    POST /2fa/setup                → secret + qr_url
    POST /2fa/enable               → bool
    POST /2fa/disable              → bool
    POST /password-reset/request   → sends reset email
    POST /password-reset/confirm   → updates password
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Body, Form, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from typing import Callable, Optional

from app.core.kernel.auth.service import AuthService
from app.core.kernel.database import get_db

# ── Cookie helpers ────────────────────────────────────────────────────────────
# refresh_token يُخزَّن في httpOnly SameSite=Strict cookie (T-01).
# access_token يبقى قصير العمر في memory الفرونت إند (Pinia store) فقط.
#
# Dev vs Production:
#   production: SameSite=Strict + Secure=True  (HTTPS + same domain)
#   development: SameSite=Lax  + Secure=False  (HTTP + cross-origin dev access
#                via IP أو localhost من جهاز تاني على الشبكة المحلية)
_REFRESH_COOKIE_NAME = "refresh_token"

import os as _os
_IS_DEV = _os.environ.get("ENVIRONMENT", "development") != "production"


def _set_refresh_cookie(response: Response, token: str, max_age_days: int) -> None:
    """يحط refresh_token في httpOnly cookie — Strict+Secure في production، Lax في dev."""
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=token,
        max_age=max_age_days * 86_400,
        httponly=True,
        samesite="lax" if _IS_DEV else "strict",
        secure=not _IS_DEV,   # False في dev (HTTP) — True في production (HTTPS)
        path="/api/v1/auth",  # مش /api/v1/ كاملة — الـ cookie ميتبعتش مع كل request
    )


def _clear_refresh_cookie(response: Response) -> None:
    """يمسح refresh_token cookie عند logout."""
    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME,
        path="/api/v1/auth",
        httponly=True,
        samesite="lax" if _IS_DEV else "strict",
        secure=not _IS_DEV,
    )


class _PublicUserOut(BaseModel):
    """Safe subset of the User columns for /register's response.

    Without an explicit response_model, FastAPI's jsonable_encoder falls back
    to vars(obj) for a plain ORM instance — that serializes *every* mapped
    column, including `password_hash` (bcrypt hash) and `two_factor_secret`.
    Confirmed live: POST /register was returning password_hash in plaintext
    JSON. This whitelist is the fix — only ever add fields here that are
    genuinely safe to hand back to the caller who just registered.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[datetime] = None


def build_auth_router(
    user_model,
    settings,
    get_current_user: Optional[Callable] = None,
) -> APIRouter:
    router = APIRouter()

    def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
        return AuthService(db, user_model, settings)

    def _no_auth():
        from fastapi import HTTPException
        raise HTTPException(501, "get_current_user not configured for this router")

    _get_current_user = get_current_user or _no_auth

    # ── Public routes ─────────────────────────────────────────────────────

    @router.post("/login")
    def login(
        response: Response,
        form_data: OAuth2PasswordRequestForm = Depends(),
        otp_code: Optional[str] = Form(None),
        auth: AuthService = Depends(get_auth_service),
    ):
        result = auth.login(form_data.username, form_data.password, otp_code=otp_code)
        user = result.pop("_user", None)
        if user:
            refresh = auth.create_refresh_token(user.id)
            _set_refresh_cookie(response, refresh, auth.settings.REFRESH_TOKEN_EXPIRE_DAYS)
        # refresh_token لا يرجع في الـ body — في httpOnly cookie فقط (T-01)
        result.pop("refresh_token", None)
        return result

    @router.post("/register", response_model=_PublicUserOut)
    def register(
        payload: dict = Body(...),
        auth: AuthService = Depends(get_auth_service),
    ):
        try:
            return auth.register(
                email=payload["email"],
                password=payload["password"],
                full_name=payload["full_name"],
                phone=payload.get("phone"),
            )
        except KeyError as e:
            from fastapi import HTTPException
            raise HTTPException(422, f"Missing required field: {e.args[0]}")

    @router.post("/refresh")
    def refresh(
        response: Response,
        request: Request,
        payload: dict = Body(default={}),
        auth: AuthService = Depends(get_auth_service),
    ):
        """يستبدل refresh_token بـ access_token جديد (rotation).
        الـ refresh_token يُقرأ من httpOnly cookie أولاً (T-01)؛
        fallback لـ body للتوافق مع clients قديمة."""
        from fastapi import HTTPException  # noqa: PLC0415
        from datetime import timedelta  # noqa: PLC0415
        from app.core.kernel.security import create_access_token  # noqa: PLC0415

        # httpOnly cookie هو المصدر الأساسي (T-01) — body كـ fallback
        token = request.cookies.get(_REFRESH_COOKIE_NAME) or payload.get("refresh_token", "")
        fingerprint = payload.get("device_fingerprint")
        result = auth.rotate_refresh_token(token, fingerprint)
        if not result:
            raise HTTPException(401, "Invalid or expired refresh token")
        user, new_refresh_token = result
        access = create_access_token(
            data={"sub": user.email},
            secret_key=settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        # refresh_token الجديد في cookie (T-01) — لا يُعاد في body
        _set_refresh_cookie(response, new_refresh_token, settings.REFRESH_TOKEN_EXPIRE_DAYS)
        return {
            "access_token": access,
            "token_type": "bearer",
        }

    @router.post("/password-reset/request")
    async def password_reset_request(
        payload: dict = Body(...),
        auth: AuthService = Depends(get_auth_service),
    ):
        """Generate a reset token and (optionally) send it via email."""
        email = payload.get("email", "")
        token = auth.create_password_reset_token(email)
        if token:
            try:
                from app.core.kernel.email_service import send_password_reset_email
                await send_password_reset_email(email, token, app_name=getattr(settings, "APP_NAME", "Resort OS"))
            except Exception:
                pass
        return {"message": "If that email exists, a reset link has been sent."}

    @router.post("/password-reset/confirm")
    def password_reset_confirm(
        payload: dict = Body(...),
        auth: AuthService = Depends(get_auth_service),
    ):
        auth.confirm_password_reset(payload["token"], payload["new_password"])
        return {"message": "Password updated successfully."}

    # ── Authenticated routes ───────────────────────────────────────────────

    @router.post("/logout")
    def logout(
        response: Response,
        request: Request,
        payload: dict = Body(default={}),
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        token = payload.get("token", "")
        auth.revoke_token(token, current_user.id)
        # امسح الـ refresh_token cookie (T-01)
        _clear_refresh_cookie(response)
        return {"message": "Logged out successfully."}

    @router.post("/change-password")
    def change_password(
        payload: dict = Body(...),
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        auth.change_password(
            current_user,
            payload["old_password"],
            payload["new_password"],
        )
        return {"message": "Password changed successfully."}

    @router.post("/2fa/setup")
    def setup_2fa(
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        return auth.setup_2fa(current_user)

    @router.post("/2fa/enable")
    def enable_2fa(
        payload: dict = Body(...),
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        auth.enable_2fa(current_user, payload["code"])
        return {"message": "2FA enabled successfully."}

    @router.post("/2fa/disable")
    def disable_2fa(
        payload: dict = Body(...),
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        auth.disable_2fa(current_user, payload["code"])
        return {"message": "2FA disabled successfully."}

    return router
