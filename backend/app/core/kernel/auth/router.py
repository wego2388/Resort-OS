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

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Body, Form, Header, Path, Query, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
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


# Gate 2B3A — purposes the control plane currently issues step-up grants
# for. Each one has a matching scope-builder function in
# app.core.kernel.auth.step_up that both this endpoint and the consuming
# endpoint call, so the two sides can never define "same operation"
# differently.
_STEP_UP_PURPOSES = frozenset({
    "user_role_update",
    "permission_override_upsert",
    "permission_override_revoke",
    "setting_upsert",
    # Gate 2B3B — self-service session revocation (reuses the exact same
    # step-up proof mechanism, not a parallel one). These two carry no
    # free-text reason: revoking your own session is a personal security
    # action, not an admin control-plane mutation that needs justification.
    "session_revoke",
    "other_sessions_revoke",
    # Gate 4 (جولة مراجعة Codex الأولى — M5a): أعلى-خطورة من إلغاء صنف قبل
    # الدفع (لسه محمي بـPIN موافقة مدير بس، مقصود) — عكس دفعة مسجّلة فعليًا
    # أو مرتجع بعد الدفع، الاتنين آثار مالية حقيقية على دفاتر مقفولة جزئيًا.
    "payment_void",
    "dining_refund",
})


class _StepUpRequest(BaseModel):
    """``intent`` carries only the non-secret identifiers of the operation
    the caller is about to perform (e.g. target user_id, new role, setting
    key) — never a password/TOTP/recovery code, and never the full setting
    value or reason in the clear beyond what the scope builder hashes.
    Exactly one of totp_code/recovery_code may be supplied, and only when
    the account has 2FA enabled.

    ``intent`` stays an untyped dict at this outer layer only because its
    real shape depends on ``purpose``, which isn't known until this model
    is already parsed — the endpoint immediately re-validates it against
    one of the purpose-specific typed models below before touching
    anything else. Never read ``payload.intent`` directly for a field
    value; go through the typed model instead."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=1024)
    purpose: str = Field(min_length=1, max_length=64)
    intent: dict = Field(default_factory=dict)
    totp_code: Optional[str] = Field(default=None, min_length=6, max_length=8)
    recovery_code: Optional[str] = Field(default=None, min_length=1, max_length=64)


# Gate 2B3A — purpose-specific typed intent contracts (مراجعة Codex
# المستقلة، 2026-07-18، Medium): كانت `intent` بتتقرا كـdict حر عبر
# .get()/[] وbool()/int()/str() يدوي — يعني قيمة زي "allowed": "false"
# (نص، مش JSON boolean) كانت بتعدّي bool("false") == True بصمت، وأي
# حقل زيادة غير متوقع كان بيتقبل من غير أي رفض. كل عقد هنا extra="forbid"
# ونفس نوع الحقل المطلوب فعليًا في العملية الأصلية (مش تحويل يدوي)."""

class _UserRoleUpdateIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: int = Field(gt=0, strict=True)
    role: Optional[str] = Field(default=None, max_length=30)
    is_active: Optional[bool] = Field(default=None, strict=True)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("role")
    @classmethod
    def _role_must_be_known(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            from app.core.deps import ROLE_LEVELS  # noqa: PLC0415

            if value not in ROLE_LEVELS:
                raise ValueError(f"Unknown role: {value}")
        return value

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Reason must contain at least 3 non-whitespace characters")
        return normalized


class _PermissionOverrideUpsertIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: int = Field(gt=0, strict=True)
    resource: str = Field(min_length=1, max_length=100)
    action: str = Field(
        pattern=r"^(view|create|edit|delete|void|approve|execute)$",
        max_length=30,
    )
    allowed: bool = Field(strict=True)
    branch_id: Optional[int] = Field(default=None, gt=0, strict=True)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Reason must contain at least 3 non-whitespace characters")
        return normalized


class _PermissionOverrideRevokeIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    permission_id: int = Field(gt=0, strict=True)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Reason must contain at least 3 non-whitespace characters")
        return normalized


class _SettingUpsertIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=100)
    branch_id: Optional[int] = Field(default=None, gt=0, strict=True)
    value: str
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Reason must contain at least 3 non-whitespace characters")
        return normalized


class _SessionRevokeIntent(BaseModel):
    """Gate 2B3B — revoke one session (family) by its public reference."""
    model_config = ConfigDict(extra="forbid")
    session_ref: str = Field(min_length=1, max_length=32)


class _OtherSessionsRevokeIntent(BaseModel):
    """Gate 2B3B — revoke every session except the caller's current one. The
    proof is bound to the current session's public reference so it cannot be
    reused after the current session itself changed. The server re-derives the
    real current session from the refresh cookie at consumption time — this is
    the value the client *claims* is current, and a mismatch fails closed."""
    model_config = ConfigDict(extra="forbid")
    keep_session_ref: str = Field(min_length=1, max_length=32)


class _PaymentVoidIntent(BaseModel):
    """Gate 4 (جولة مراجعة Codex الأولى — M5a): عكس دفعة مسجّلة فعليًا."""
    model_config = ConfigDict(extra="forbid")
    payment_id: int = Field(gt=0, strict=True)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Reason must contain at least 3 non-whitespace characters")
        return normalized


class _DiningRefundIntent(BaseModel):
    """Gate 4 (جولة مراجعة Codex الأولى — M5a): مرتجع صنف بعد الدفع."""
    model_config = ConfigDict(extra="forbid")
    order_id: int = Field(gt=0, strict=True)
    item_id: int = Field(gt=0, strict=True)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 3:
            raise ValueError("Reason must contain at least 3 non-whitespace characters")
        return normalized


_STEP_UP_INTENT_MODELS: dict[str, type[BaseModel]] = {
    "user_role_update": _UserRoleUpdateIntent,
    "permission_override_upsert": _PermissionOverrideUpsertIntent,
    "permission_override_revoke": _PermissionOverrideRevokeIntent,
    "setting_upsert": _SettingUpsertIntent,
    "session_revoke": _SessionRevokeIntent,
    "other_sessions_revoke": _OtherSessionsRevokeIntent,
    "payment_void": _PaymentVoidIntent,
    "dining_refund": _DiningRefundIntent,
}


def build_auth_router(
    user_model,
    settings,
    get_current_user: Optional[Callable] = None,
) -> APIRouter:
    router = APIRouter()

    def get_auth_service(request: Request, db: Session = Depends(get_db)) -> AuthService:
        # Gate 2B3B — attach the trusted client IP (resolved with the app's
        # proxy policy, never a raw X-Forwarded-For) and the request's
        # User-Agent so the unified auth audit can record them. request_id is
        # read ambiently from the correlation context var inside the service.
        from app.core.rate_limit import _client_ip  # noqa: PLC0415

        service = AuthService(db, user_model, settings)
        service.attach_request_context(
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        return service

    def _no_auth():
        from fastapi import HTTPException
        raise HTTPException(501, "get_current_user not configured for this router")

    _get_current_user = get_current_user or _no_auth

    def _session_bound_access_token(user, session_ref: Optional[str] = None) -> str:
        """Mint an access token for the authenticated HTTP session.

        ``sid`` is a non-secret public session reference. The shared auth
        dependency resolves it against a still-live refresh family on every
        request, so revoking one session invalidates that session's access
        token immediately without logging every other device out.
        """
        from app.core.kernel.security import create_access_token  # noqa: PLC0415

        claims = {"sub": user.email}
        if session_ref:
            claims["sid"] = session_ref
        return create_access_token(
            data=claims,
            secret_key=settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )

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
            current = auth.current_session(refresh, expected_user_id=user.id)
            if current is None:
                # A refresh family was just committed; failure to resolve it
                # is an internal invariant violation. Fail closed rather than
                # issuing an access token that cannot be revoked by session.
                raise RuntimeError("New refresh session could not be resolved")
            result["access_token"] = _session_bound_access_token(user, current[1])
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
        current = auth.current_session(new_refresh_token, expected_user_id=user.id)
        if current is None:
            raise RuntimeError("Rotated refresh session could not be resolved")
        access = _session_bound_access_token(user, current[1])
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

    @router.post("/step-up")
    def issue_step_up(
        response: Response,
        request: Request,
        payload: _StepUpRequest,
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        """Gate 2B3A — issue a short-lived, one-time, hashed proof that the
        current session holder just re-confirmed their password (and TOTP/
        recovery code where 2FA is enabled) for one exact operation. This
        is not itself an authorization decision; the consuming endpoint
        still enforces its own role/ownership checks independently."""
        from fastapi import HTTPException  # noqa: PLC0415
        from app.core.kernel.auth import step_up as step_up_scopes  # noqa: PLC0415

        _mark_sensitive_response(response)

        if payload.purpose not in _STEP_UP_PURPOSES:
            raise HTTPException(422, f"Unknown step-up purpose: {payload.purpose}")

        # Gate 2B3A (مراجعة Codex المستقلة، 2026-07-18): intent بيتحقق منه
        # عبر عقد Pydantic مخصص لنفس الـpurpose قبل أي حاجة تانية — بما
        # فيها استهلاك TOTP/recovery code تحت. intent مشوّه = 422 فورًا،
        # قبل ما نلمس أي سر خالص. extra="forbid" بيرفض أي حقل زيادة، ونوع
        # كل حقل (زي allowed: bool) بيتفرض فعليًا بدل تحويل يدوي بـbool()/
        # int()/str() كان بيقبل قيم غلط بصمت (مثال حقيقي: "allowed":
        # "false" كنص كان بيعدّي bool("false") == True).
        try:
            intent = _STEP_UP_INTENT_MODELS[payload.purpose].model_validate(payload.intent)
        except ValidationError as exc:
            raise HTTPException(422, f"Invalid intent for purpose '{payload.purpose}': {exc}")

        if payload.purpose == "user_role_update":
            scope_hash = step_up_scopes.user_role_update_scope(
                user_id=intent.user_id, role=intent.role, is_active=intent.is_active, reason=intent.reason,
            )
        elif payload.purpose == "permission_override_upsert":
            scope_hash = step_up_scopes.permission_override_upsert_scope(
                user_id=intent.user_id, resource=intent.resource, action=intent.action,
                allowed=intent.allowed, branch_id=intent.branch_id, reason=intent.reason,
            )
        elif payload.purpose == "permission_override_revoke":
            scope_hash = step_up_scopes.permission_override_revoke_scope(
                permission_id=intent.permission_id, reason=intent.reason,
            )
        elif payload.purpose == "setting_upsert":
            scope_hash = step_up_scopes.setting_upsert_scope(
                key=intent.key, branch_id=intent.branch_id, value=intent.value, reason=intent.reason,
            )
        elif payload.purpose == "session_revoke":
            scope_hash = step_up_scopes.session_revoke_scope(session_ref=intent.session_ref)
        elif payload.purpose == "other_sessions_revoke":
            scope_hash = step_up_scopes.other_sessions_revoke_scope(
                keep_session_ref=intent.keep_session_ref,
            )
        elif payload.purpose == "payment_void":
            scope_hash = step_up_scopes.payment_void_scope(
                payment_id=intent.payment_id, reason=intent.reason,
            )
        else:  # dining_refund
            scope_hash = step_up_scopes.dining_refund_scope(
                order_id=intent.order_id, item_id=intent.item_id, reason=intent.reason,
            )

        access_token_hash = step_up_scopes.access_token_hash_from_request(request)
        result = auth.issue_step_up(
            current_user,
            current_password=payload.current_password,
            purpose=payload.purpose,
            scope_hash=scope_hash,
            access_token_hash=access_token_hash,
            totp_code=payload.totp_code,
            recovery_code=payload.recovery_code,
        )
        return {
            "step_up_token": result["step_up_token"],
            "expires_at": result["expires_at"],
            "assurance_method": result["assurance_method"],
        }

    # ── Self-service session management (Gate 2B3B) ──────────────────────

    def _consume_session_step_up_or_raise(
        auth: AuthService,
        request: Request,
        current_user,
        *,
        purpose: str,
        scope_hash: str,
        x_step_up_token: Optional[str],
    ) -> None:
        """Reuse Gate 2B3A's proof mechanism for a session-revoke operation.
        Missing header → 428; any other failure (invalid/expired/replayed/
        wrong-user/wrong-session/wrong-purpose/wrong-scope) → identical
        generic 403, so the caller cannot tell why it was rejected."""
        from fastapi import HTTPException  # noqa: PLC0415
        from app.core.kernel.auth.step_up import access_token_hash_from_request  # noqa: PLC0415

        if not x_step_up_token:
            raise HTTPException(428, {
                "error_code": "STEP_UP_REQUIRED",
                "message": "يلزم إثبات هوية حديث (كلمة السر + التحقق بخطوتين) قبل إنهاء الجلسة",
            })
        result = auth.consume_step_up(
            user_id=current_user.id,
            purpose=purpose,
            scope_hash=scope_hash,
            access_token_hash=access_token_hash_from_request(request),
            token=x_step_up_token,
        )
        if result is None:
            raise HTTPException(403, {
                "error_code": "STEP_UP_INVALID",
                "message": "إثبات الهوية غير صالح أو منتهي أو مُستخدَم بالفعل — أعد التأكيد وحاول تاني",
            })

    @router.get("/sessions")
    def list_sessions(
        request: Request,
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
    ):
        """List the current user's own active sessions (refresh-token
        families). Non-secret DTOs only — never a token/hash or the internal
        family id. The session that presented the current refresh cookie is
        flagged ``current``."""
        current = auth.current_session(
            request.cookies.get(_REFRESH_COOKIE_NAME),
            expected_user_id=current_user.id,
        )
        current_family_id = current[0] if current else None
        return {"sessions": auth.list_active_sessions(current_user.id, current_family_id=current_family_id)}

    @router.post("/sessions/revoke-others")
    def revoke_other_sessions(
        request: Request,
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
        x_step_up_token: Optional[str] = Header(default=None, alias="X-Step-Up-Token"),
    ):
        """Revoke every session the user owns except the current one. The
        current session is proven server-side from the refresh cookie — the
        step-up proof is bound to that public reference, so a proof cannot be
        replayed after the current session changed."""
        from fastapi import HTTPException  # noqa: PLC0415
        from app.core.kernel.auth import step_up as step_up_scopes  # noqa: PLC0415

        current = auth.current_session(
            request.cookies.get(_REFRESH_COOKIE_NAME),
            expected_user_id=current_user.id,
        )
        if current is None:
            # Without a live current session there is no "others vs current"
            # distinction to make safely — the client must be on a real
            # refreshable session to use this.
            raise HTTPException(400, {
                "error_code": "NO_CURRENT_SESSION",
                "message": "لا توجد جلسة حالية صالحة لتنفيذ هذا الإجراء",
            })
        current_family_id, current_public_id = current
        scope_hash = step_up_scopes.other_sessions_revoke_scope(keep_session_ref=current_public_id)
        _consume_session_step_up_or_raise(
            auth, request, current_user,
            purpose="other_sessions_revoke", scope_hash=scope_hash,
            x_step_up_token=x_step_up_token,
        )
        revoked = auth.revoke_other_sessions(current_user.id, keep_family_id=current_family_id)
        return {"revoked_count": revoked, "message": "تم إنهاء الجلسات الأخرى بنجاح."}

    @router.delete("/sessions/{session_ref}")
    def revoke_session(
        request: Request,
        session_ref: str = Path(..., min_length=1, max_length=32),
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
        x_step_up_token: Optional[str] = Header(default=None, alias="X-Step-Up-Token"),
    ):
        """Revoke exactly one session the user owns, by its public reference.
        Step-up bound to that specific reference. A reference not owned by the
        caller returns 404 — a user cannot probe another user's sessions."""
        from fastapi import HTTPException  # noqa: PLC0415
        from app.core.kernel.auth import step_up as step_up_scopes  # noqa: PLC0415

        scope_hash = step_up_scopes.session_revoke_scope(session_ref=session_ref)
        _consume_session_step_up_or_raise(
            auth, request, current_user,
            purpose="session_revoke", scope_hash=scope_hash,
            x_step_up_token=x_step_up_token,
        )
        if not auth.revoke_session_by_ref(current_user.id, session_ref):
            raise HTTPException(404, {
                "error_code": "SESSION_NOT_FOUND",
                "message": "الجلسة غير موجودة أو تم إنهاؤها بالفعل",
            })
        return {"message": "تم إنهاء الجلسة بنجاح."}

    @router.get("/security-activity")
    def security_activity(
        current_user=Depends(_get_current_user),
        auth: AuthService = Depends(get_auth_service),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ):
        """Paginated, allow-listed view of the current user's OWN
        authentication activity. Whitelisted fields only — never the raw audit
        payload, another user's rows, or any secret."""
        rows, total = auth.list_security_activity(current_user.id, limit=limit, offset=offset)
        items = []
        for row in rows:
            meta = {}
            if row.new_data:
                try:
                    meta = json.loads(row.new_data)
                except (ValueError, TypeError):
                    meta = {}
            items.append({
                "id": row.id,
                "action": row.action,
                "at": row.created_at,
                "ip_address": row.ip_address,
                "device": row.user_agent,
                "request_id": meta.get("request_id"),
            })
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    return router
