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
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, model_validator
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
_SAFE_ENVIRONMENTS = {"development", "test", "testing"}


def _is_safe_environment(environment: str) -> bool:
    return (environment or "").strip().lower() in _SAFE_ENVIRONMENTS


def _set_refresh_cookie(
    response: Response,
    token: str,
    max_age_days: int,
    *,
    environment: str,
) -> None:
    """يحط refresh_token في httpOnly cookie — Strict+Secure في production، Lax في dev."""
    is_safe_environment = _is_safe_environment(environment)
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=token,
        max_age=max_age_days * 86_400,
        httponly=True,
        samesite="lax" if is_safe_environment else "strict",
        secure=not is_safe_environment,
        path="/api/v1/auth",  # مش /api/v1/ كاملة — الـ cookie ميتبعتش مع كل request
    )


def _clear_refresh_cookie(response: Response, *, environment: str) -> None:
    """يمسح refresh_token cookie عند logout."""
    is_safe_environment = _is_safe_environment(environment)
    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME,
        path="/api/v1/auth",
        httponly=True,
        samesite="lax" if is_safe_environment else "strict",
        secure=not is_safe_environment,
    )


def _mark_sensitive_response(response: Response) -> None:
    """Prevent browser/proxy caching of credentials, TOTP seeds, or codes."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


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


class _RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(default="", max_length=512)
    device_fingerprint: Optional[str] = Field(default=None, max_length=255)


class _PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=320)


class _PasswordResetConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1, max_length=1024)


class _LogoutRequest(BaseModel):
    """Body token remains a compatibility fallback for older API clients."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(default="", max_length=4096)


class _ChangePasswordRequest(BaseModel):
    """Canonical frontend contract plus the legacy backend field alias."""

    model_config = ConfigDict(extra="forbid")

    current_password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    old_password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)
    enrollment_token: Optional[str] = Field(default=None, min_length=20, max_length=512)

    @model_validator(mode="after")
    def _validate_current_password_fields(self) -> "_ChangePasswordRequest":
        if not self.current_password and not self.old_password:
            raise ValueError("current_password is required")
        if self.current_password and self.old_password and self.current_password != self.old_password:
            raise ValueError("current_password and old_password must match when both are supplied")
        return self

    @property
    def verified_current_password(self) -> str:
        # The validator above guarantees one of these values is present.
        return self.current_password or self.old_password or ""


class _TwoFactorSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: Optional[str] = Field(default=None, min_length=1, max_length=1024)
    enrollment_token: Optional[str] = Field(default=None, min_length=20, max_length=512)


class _TwoFactorEnableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=8)
    enrollment_token: Optional[str] = Field(default=None, min_length=20, max_length=512)


class _TwoFactorDisableRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=8)
    current_password: str = Field(min_length=1, max_length=1024)


class _RecoveryCodesRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=6, max_length=8)
    current_password: str = Field(min_length=1, max_length=1024)


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
        recovery_code: Optional[str] = Form(None),
        enrollment_token: Optional[str] = Form(None),
        auth: AuthService = Depends(get_auth_service),
    ):
        _mark_sensitive_response(response)
        result = auth.login(
            form_data.username,
            form_data.password,
            otp_code=otp_code,
            recovery_code=recovery_code,
            enrollment_token=enrollment_token,
        )
        user = result.pop("_user", None)
        allow_refresh = result.pop("_allow_refresh", True)
        if user and allow_refresh:
            refresh = auth.create_refresh_token(user.id)
            _set_refresh_cookie(
                response,
                refresh,
                auth.settings.REFRESH_TOKEN_EXPIRE_DAYS,
                environment=auth.settings.ENVIRONMENT,
            )
        else:
            _clear_refresh_cookie(response, environment=auth.settings.ENVIRONMENT)
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
        payload: Optional[_RefreshRequest] = Body(default=None),
        auth: AuthService = Depends(get_auth_service),
    ):
        """يستبدل refresh_token بـ access_token جديد (rotation).
        الـ refresh_token يُقرأ من httpOnly cookie أولاً (T-01)؛
        fallback لـ body للتوافق مع clients قديمة."""
        from fastapi import HTTPException  # noqa: PLC0415
        from datetime import timedelta  # noqa: PLC0415
        from app.core.kernel.security import create_access_token  # noqa: PLC0415

        _mark_sensitive_response(response)

        # httpOnly cookie هو المصدر الأساسي (T-01) — body كـ fallback
        token = request.cookies.get(_REFRESH_COOKIE_NAME) or (
            payload.refresh_token if payload else ""
        )
        fingerprint = payload.device_fingerprint if payload else None
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
        _set_refresh_cookie(
            response,
            new_refresh_token,
            settings.REFRESH_TOKEN_EXPIRE_DAYS,
            environment=settings.ENVIRONMENT,
        )
        return {
            "access_token": access,
            "token_type": "bearer",
        }

    @router.post("/password-reset/request")
    async def password_reset_request(
        payload: _PasswordResetRequest,
        auth: AuthService = Depends(get_auth_service),
    ):
        """Generate a reset token and (optionally) send it via email."""
        email = payload.email.strip()
        token = auth.create_password_reset_token(email)
        if token:
            try:
                from app.core.kernel.email_service import send_password_reset_email
                await send_password_reset_email(email, token, app_name=getattr(settings, "APP_NAME", "Resort OS"))
            except Exception:
                # Keep the public response enumeration-safe, but never hide
                # an operational delivery failure from internal logs. Do not
                # include the address or bearer reset token in the message.
                logger.exception("Password-reset email delivery failed")
        return {"message": "If that email exists, a reset link has been sent."}

    @router.post("/password-reset/confirm")
    def password_reset_confirm(
        response: Response,
        payload: _PasswordResetConfirm,
        auth: AuthService = Depends(get_auth_service),
    ):
        _mark_sensitive_response(response)
        auth.confirm_password_reset(payload.token, payload.new_password)
        _clear_refresh_cookie(response, environment=settings.ENVIRONMENT)
        return {
            "message": "Password updated successfully.",
            "reauthentication_required": True,
        }

    # ── Authenticated routes ───────────────────────────────────────────────

    @router.post("/logout")
    def logout(
        response: Response,
        request: Request,
        payload: Optional[_LogoutRequest] = Body(default=None),
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        auth_header = request.headers.get("Authorization", "")
        access_token = (
            auth_header.removeprefix("Bearer ")
            if auth_header.startswith("Bearer ")
            else (payload.token if payload else "")
        )
        auth.revoke_session(
            access_token=access_token,
            refresh_token=request.cookies.get(_REFRESH_COOKIE_NAME, ""),
            user_id=current_user.id,
        )
        # امسح الـ refresh_token cookie (T-01)
        _clear_refresh_cookie(response, environment=settings.ENVIRONMENT)
        return {"message": "Logged out successfully."}

    @router.post("/change-password")
    def change_password(
        response: Response,
        payload: _ChangePasswordRequest,
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        _mark_sensitive_response(response)
        auth.change_password(
            current_user,
            payload.verified_current_password,
            payload.new_password,
            enrollment_token=payload.enrollment_token,
        )
        _clear_refresh_cookie(response, environment=settings.ENVIRONMENT)
        return {
            "message": "Password changed successfully.",
            "reauthentication_required": True,
        }

    @router.post("/2fa/setup")
    def setup_2fa(
        response: Response,
        payload: Optional[_TwoFactorSetupRequest] = Body(default=None),
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        _mark_sensitive_response(response)
        return auth.setup_2fa(
            current_user,
            current_password=payload.current_password if payload else None,
            enrollment_token=payload.enrollment_token if payload else None,
        )

    @router.post("/2fa/enable")
    def enable_2fa(
        response: Response,
        payload: _TwoFactorEnableRequest,
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        _mark_sensitive_response(response)
        result = auth.enable_2fa(
            current_user,
            payload.code,
            enrollment_token=payload.enrollment_token,
        )
        _clear_refresh_cookie(response, environment=settings.ENVIRONMENT)
        return {"message": "2FA enabled successfully.", **result}

    @router.post("/2fa/disable")
    def disable_2fa(
        response: Response,
        payload: _TwoFactorDisableRequest,
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        _mark_sensitive_response(response)
        auth.disable_2fa(
            current_user,
            payload.code,
            current_password=payload.current_password,
        )
        _clear_refresh_cookie(response, environment=settings.ENVIRONMENT)
        return {"message": "2FA disabled successfully.", "reauthentication_required": True}

    @router.post("/2fa/recovery-codes/regenerate")
    def regenerate_recovery_codes(
        response: Response,
        payload: _RecoveryCodesRegenerateRequest,
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        _mark_sensitive_response(response)
        result = auth.regenerate_recovery_codes(
            current_user,
            current_password=payload.current_password,
            code=payload.code,
        )
        _clear_refresh_cookie(response, environment=settings.ENVIRONMENT)
        return {"message": "Recovery codes regenerated successfully.", **result}

    return router
