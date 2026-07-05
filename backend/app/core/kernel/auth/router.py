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
from typing import Optional

from fastapi import APIRouter, Depends, Body, Form
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session


class RegisterResponse(BaseModel):
    """رد آمن لـ /register — بدون password_hash/two_factor_secret. بدون
    response_model كان FastAPI بيسلسل الـ ORM object الخام اللي `register()`
    بيرجّعه مباشرة، يعني أي حد (endpoint عام بدون تسجيل دخول) بيشوف الـ hash
    وسر الـ 2FA في رد التسجيل. self-contained هنا (بدون import من
    app.modules) لأن app/core/kernel/ بنية تحتية عامة قابلة لإعادة الاستخدام،
    مش خاصة بـ resort-os."""
    model_config = ConfigDict(from_attributes=True)
    id:        int
    email:     str
    full_name: str
    phone:     Optional[str]
    role:      str
    is_active: bool
    created_at: datetime
from typing import Callable, Optional

from app.core.kernel.auth.service import AuthService
from app.core.kernel.database import get_db


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
        form_data: OAuth2PasswordRequestForm = Depends(),
        otp_code: Optional[str] = Form(None),
        auth: AuthService = Depends(get_auth_service),
    ):
        result = auth.login(form_data.username, form_data.password, otp_code=otp_code)
        user = result.pop("_user", None)
        if user:
            result["refresh_token"] = auth.create_refresh_token(user.id)
        return result

    @router.post("/register", response_model=RegisterResponse)
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
        payload: dict = Body(...),
        auth: AuthService = Depends(get_auth_service),
    ):
        """Exchange a refresh token for a new access + refresh token (rotation)."""
        from fastapi import HTTPException
        from datetime import timedelta
        from app.core.kernel.security import create_access_token
        token = payload.get("refresh_token", "")
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
        return {
            "access_token": access,
            "refresh_token": new_refresh_token,
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
        payload: dict = Body(...),
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        token = payload.get("token", "")
        auth.revoke_token(token, current_user.id)
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
