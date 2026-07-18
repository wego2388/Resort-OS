"""
app/core/kernel/auth/service.py
BaseService + AuthService — complete auth logic (login lockout, JWT issuance,
refresh token rotation, 2FA, password reset, token revocation).
"""

import base64
import hashlib
import secrets
from io import BytesIO
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.kernel.security import (
    verify_password, get_password_hash, create_access_token,
    validate_password_strength, validate_email_format,
)
from app.core.kernel.auth.repository import (
    UserRepository,
    delete_refresh_tokens_for_user,
)


# A real bcrypt hash computed once at import. When an email doesn't exist we
# still run verify_password against this so the failure path takes the same
# ~300ms as a wrong-password path — otherwise the timing gap (email-not-found
# returns in <1ms vs bcrypt-compare ~300ms) leaks which emails are registered.
_DUMMY_PASSWORD_HASH = get_password_hash("timing-equalizer-not-a-real-password")

# Single generic message for every bad-credentials outcome (unknown email OR
# wrong password) — distinct messages are a user-enumeration oracle just like
# the timing gap. Lockout/inactive keep their own messages on purpose: those
# are post-authentication states a legitimate user needs to see.
_GENERIC_AUTH_ERROR = "Incorrect email or password"
_RESET_TOKEN_PREFIX = "reset_"


class BaseService:
    def __init__(self, db: Session):
        self.db = db
        self.logger = logger

    def _table_exists(self, table: str) -> bool:
        row = self.db.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :t AND table_schema = 'public'"
            ),
            {"t": table},
        ).fetchone()
        return row is not None


class AuthService(BaseService):
    def __init__(self, db: Session, user_model, settings):
        super().__init__(db)
        self.repo = UserRepository(user_model, db)
        self.settings = settings

    # ── Registration ──────────────────────────────────────────────────────

    def register(self, email: str, password: str, full_name: str, phone: Optional[str] = None):
        if not validate_email_format(email):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid email format")
        if self.repo.get_by_email(email):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")
        valid, msg = validate_password_strength(password)
        if not valid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
        return self.repo.create({
            "email": email,
            "password_hash": get_password_hash(password),
            "full_name": full_name,
            "phone": phone,
        })

    # ── Login (with lockout) ──────────────────────────────────────────────

    def login(self, email: str, password: str, otp_code: Optional[str] = None) -> dict:
        max_attempts = getattr(self.settings, "MAX_LOGIN_ATTEMPTS", 5)
        lockout_minutes = getattr(self.settings, "LOCKOUT_MINUTES", 30)

        # trim whitespace — يمنع فشل الـ login بسبب space زيادة من autofill أو paste
        email = email.strip()
        password = password.strip()

        user = self.repo.get_by_email(email)
        if not user:
            # Equalize timing with the wrong-password path (bcrypt ~300ms) and
            # return the exact same message — no user-enumeration oracle.
            verify_password(password, _DUMMY_PASSWORD_HASH)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC_AUTH_ERROR)

        if user.account_locked_until:
            locked_until = user.account_locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until > datetime.now(timezone.utc):
                remaining = int((locked_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
                raise HTTPException(
                    status.HTTP_423_LOCKED,
                    f"Account locked after too many failed attempts. Try again in {remaining} minutes.",
                )
            user.account_locked_until = None
            user.failed_login_attempts = 0
            self.db.commit()

        if not user.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Inactive account")

        if not verify_password(password, user.password_hash):
            attempts = (user.failed_login_attempts or 0) + 1
            user.failed_login_attempts = attempts
            if attempts >= max_attempts:
                user.account_locked_until = datetime.now(timezone.utc) + timedelta(minutes=lockout_minutes)
                self.db.commit()
                raise HTTPException(
                    status.HTTP_423_LOCKED,
                    f"Account locked after {max_attempts} failed attempts. Try again in {lockout_minutes} minutes.",
                )
            self.db.commit()
            # No "N attempts remaining" — that both confirms the email exists and
            # hands the attacker the lockout threshold. Same message as unknown email.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC_AUTH_ERROR)

        # ── Second factor (TOTP) ──────────────────────────────────────────
        # Password alone is not enough for a 2FA-enabled account: verify the
        # TOTP code here so 2FA is a real login-time second factor, not just an
        # enrollment flag. Gated by LOGIN_2FA_ENFORCED so it can be switched on
        # in lockstep with the frontend collecting the code (default off keeps
        # the current password-only client working).
        if getattr(self.settings, "LOGIN_2FA_ENFORCED", False) and user.two_factor_enabled:
            if not otp_code:
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED,
                    {"code": "2FA_CODE_REQUIRED", "message": "التحقق بخطوتين مطلوب — أدخل الرمز"},
                )
            if not pyotp.TOTP(user.two_factor_secret).verify(otp_code, valid_window=1):
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED,
                    {"code": "2FA_CODE_INVALID", "message": "رمز التحقق بخطوتين غير صحيح"},
                )

        if user.failed_login_attempts:
            user.failed_login_attempts = 0
            user.account_locked_until = None

        token = create_access_token(
            data={"sub": user.email},
            secret_key=self.settings.SECRET_KEY,
            algorithm=self.settings.ALGORITHM,
            expires_delta=timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        self.db.commit()
        return {"access_token": token, "token_type": "bearer", "_user": user}

    @staticmethod
    def _require_active_user(user) -> None:
        if (
            not user
            or not getattr(user, "is_active", False)
            or getattr(user, "deleted_at", None) is not None
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Inactive account")

    @staticmethod
    def _revoke_access_tokens(user_id: int) -> None:
        # Local import keeps the owned kernel auth package usable without a
        # module-level dependency cycle through app.core.deps.
        from app.core.deps import revoke_user_tokens  # noqa: PLC0415

        revoke_user_tokens(user_id)

    def change_password(self, user, current_password: str, new_password: str) -> bool:
        """Change the current user's password and terminate every session.

        Every role follows the same current-password verification rule. The
        old admin/super_admin exemption turned a stolen 15-minute access token
        into a permanent account takeover. Refresh-token deletion is part of
        the password transaction; the access-token cutoff is published only
        after that transaction succeeds.
        """
        self._require_active_user(user)
        valid, msg = validate_password_strength(new_password)
        if not valid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
        if verify_password(new_password, user.password_hash):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "New password must be different from the current password",
            )

        user.password_hash = get_password_hash(new_password)
        delete_refresh_tokens_for_user(self.db, user.id)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self._revoke_access_tokens(user.id)
        return True

    def update_user(self, user_id: int, data: dict, actor) -> object:
        """Gate 2A (2026-07-18): role/is_active mutations are refused
        unconditionally here, not gated by actor.role like the old code did.
        This generic repo.update() path bypasses every super_admin invariant
        in app.modules.core.services.update_user_role() — no row locking
        (ordered or otherwise), no self-lockout check, no last-active-
        super-admin check, and no AuditLog entry, just a bare
        revoke_user_tokens() call. No confirmed caller exists in this
        codebase today (grep found none), but the reason to keep it
        fail-closed is exactly that: an unreachable path that silently does
        the wrong thing is a backdoor waiting for its first caller, not a
        safe no-op. Any client that needs to change role/is_active must go
        through PATCH /users/{id}/role, which enforces those invariants."""
        user = self.repo.get(user_id)
        if not user:
            raise HTTPException(404, "User not found")
        if "role" in data or "is_active" in data:
            raise HTTPException(
                403,
                {
                    "error_code": "USE_SUPER_ADMIN_CONTROL_PLANE",
                    "message": (
                        "Changing role or is_active through this path is not allowed. "
                        "Use PATCH /users/{id}/role, which enforces the super_admin "
                        "safeguards (Gate 2A)."
                    ),
                },
            )
        if "password" in data and data["password"]:
            data["password_hash"] = get_password_hash(data.pop("password"))
        return self.repo.update(user_id, data)

    # ── Refresh tokens ────────────────────────────────────────────────────

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create_refresh_token(self, user_id: int, device_fingerprint: Optional[str] = None) -> str:
        from app.core.kernel.models.user import RefreshToken
        user = self.repo.get(user_id)
        self._require_active_user(user)
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS)
        self.db.add(RefreshToken(
            user_id=user_id,
            token_hash=self._hash_token(token),
            device_fingerprint=device_fingerprint,
            expires_at=expires_at,
            created_at=now,
        ))
        self.db.commit()
        return token

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _refresh_token_predates_revocation(self, refresh_token) -> bool:
        """Honor the existing access-token cutoff for legacy refresh rows.

        Gate 2A published a cache cutoff on role/status changes but did not
        delete the corresponding database refresh rows. New Gate 2B writes do
        both; this check safely retires any legacy rows still present.
        """
        from app.core.deps import REVOKED_CACHE_PREFIX  # noqa: PLC0415
        from app.core.kernel.cache import get_cache  # noqa: PLC0415

        revoked_at = get_cache(f"{REVOKED_CACHE_PREFIX}:{refresh_token.user_id}")
        if not revoked_at or not refresh_token.created_at:
            return False
        created_at = self._as_utc(refresh_token.created_at).timestamp()
        return created_at < float(revoked_at)

    def verify_refresh_token(self, token: str, device_fingerprint: Optional[str] = None):
        from app.core.kernel.models.user import RefreshToken
        rt = (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.token_hash == self._hash_token(token),
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
            .first()
        )
        if not rt:
            return None
        if device_fingerprint and rt.device_fingerprint != device_fingerprint:
            logger.warning("Device fingerprint mismatch for user {}", rt.user_id)
            return None
        user = self.repo.get(rt.user_id)
        if (
            not user
            or not user.is_active
            or getattr(user, "deleted_at", None) is not None
            or self._refresh_token_predates_revocation(rt)
        ):
            return None
        return user

    def rotate_refresh_token(self, old_token: str, device_fingerprint: Optional[str] = None) -> Optional[tuple]:
        """Consume one refresh token and issue its replacement atomically.

        The conditional DELETE is the concurrency boundary: two requests may
        read the same row, but only one can delete it. The loser observes a
        zero row-count after the winner commits and cannot mint another token.
        """
        from app.core.kernel.models.user import RefreshToken
        if not old_token:
            return None
        token_hash = self._hash_token(old_token)
        now = datetime.now(timezone.utc)
        rt = (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.token_hash == token_hash,
                RefreshToken.expires_at > now,
            )
            .first()
        )
        if not rt:
            return None
        if device_fingerprint and rt.device_fingerprint != device_fingerprint:
            logger.warning("Device fingerprint mismatch for user {}", rt.user_id)
            return None
        user = self.repo.get(rt.user_id)
        if (
            not user
            or not user.is_active
            or getattr(user, "deleted_at", None) is not None
            or self._refresh_token_predates_revocation(rt)
        ):
            delete_refresh_tokens_for_user(self.db, rt.user_id)
            self.db.commit()
            return None

        consumed = (
            self.db.query(RefreshToken)
            .filter(RefreshToken.id == rt.id, RefreshToken.token_hash == token_hash)
            .delete(synchronize_session=False)
        )
        if consumed != 1:
            self.db.rollback()
            return None
        # Bulk DELETE intentionally bypasses ORM synchronization. Remove the
        # consumed instance from the identity map before adding its successor;
        # SQLite may reuse the same integer primary key immediately, otherwise
        # SQLAlchemy warns and can replace the tracked identity unexpectedly.
        self.db.expunge(rt)

        new_token = secrets.token_urlsafe(32)
        self.db.add(RefreshToken(
            user_id=user.id,
            token_hash=self._hash_token(new_token),
            device_fingerprint=device_fingerprint,
            expires_at=now + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS),
            created_at=now,
        ))
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return user, new_token

    # ── 2FA ───────────────────────────────────────────────────────────────

    def setup_2fa(self, user) -> dict:
        self._require_active_user(user)
        if user.two_factor_enabled:
            raise HTTPException(400, "2FA already enabled")
        secret = pyotp.random_base32()
        user.two_factor_secret = secret
        self.db.commit()
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=getattr(self.settings, "APP_NAME", "Resort OS"),
        )
        # Never send an otpauth URI to a third-party QR service. The previous
        # api.qrserver.com image URL disclosed the permanent TOTP seed to that
        # provider as soon as the browser rendered it. qrcode[pil] is already
        # a pinned project dependency, so generate a self-contained PNG.
        import qrcode  # noqa: PLC0415

        image = qrcode.make(uri)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        qr_data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        return {
            "secret": secret,
            "provisioning_uri": uri,
            "qr_url": qr_data_url,
        }

    def enable_2fa(self, user, code: str) -> bool:
        self._require_active_user(user)
        if user.two_factor_enabled:
            raise HTTPException(400, "2FA already enabled")
        if not user.two_factor_secret:
            raise HTTPException(400, "Setup 2FA first")
        if not pyotp.TOTP(user.two_factor_secret).verify(code, valid_window=1):
            raise HTTPException(400, "Invalid 2FA code")
        user.two_factor_enabled = True
        self.db.commit()
        return True

    def disable_2fa(self, user, code: str) -> bool:
        self._require_active_user(user)
        if not user.two_factor_enabled:
            raise HTTPException(400, "2FA not enabled")
        if not pyotp.TOTP(user.two_factor_secret).verify(code, valid_window=1):
            raise HTTPException(400, "Invalid 2FA code")
        # app.core.deps.get_current_active_user blocks *access* for
        # MANDATORY_2FA_ROLES (super_admin/accountant) while 2FA is off, but
        # nothing stopped one of those users from turning it back off right
        # here — this endpoint had no idea the role-level mandate existed.
        # Local import: kernel/ must stay importable standalone (no hard
        # dependency on app.core.deps at module load time).
        from app.core.deps import MANDATORY_2FA_ROLES  # noqa: PLC0415
        if getattr(user, "role", None) in MANDATORY_2FA_ROLES:
            raise HTTPException(400, "التحقق بخطوتين إجباري لهذا الدور — لا يمكن تعطيله")
        user.two_factor_enabled = False
        user.two_factor_secret = None
        self.db.commit()
        return True

    # ── Token blacklist / revocation ────────────────────────────────────

    def revoke_token(self, token: str, user_id: int, *, commit: bool = True) -> None:
        if not token:
            return
        token_hash = self._hash_token(token)
        # Both supported databases implement ON CONFLICT. Keeping this as one
        # statement avoids a check-then-insert race between duplicate logout
        # requests while still allowing the caller to own the final commit.
        self.db.execute(
            text("""
                INSERT INTO token_blacklist (token_hash, user_id, expires_at)
                VALUES (:h, :uid, :exp) ON CONFLICT DO NOTHING
            """),
            {
                "h": token_hash,
                "uid": user_id,
                "exp": datetime.now(timezone.utc) + timedelta(days=8),
            },
        )
        if commit:
            self.db.commit()

    def revoke_session(
        self,
        *,
        access_token: str,
        refresh_token: str,
        user_id: int,
    ) -> None:
        """Revoke both credentials belonging to the current browser session."""
        from app.core.kernel.models.user import RefreshToken  # noqa: PLC0415

        self.revoke_token(access_token, user_id, commit=False)
        if refresh_token:
            self.db.query(RefreshToken).filter(
                RefreshToken.user_id == user_id,
                RefreshToken.token_hash == self._hash_token(refresh_token),
            ).delete(synchronize_session=False)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def is_token_revoked(self, token_hash: str) -> bool:
        from app.core.kernel.models.user import TokenBlacklist  # noqa: PLC0415

        return self.db.query(TokenBlacklist.id).filter(
            TokenBlacklist.token_hash == token_hash,
            TokenBlacklist.expires_at > datetime.now(timezone.utc),
        ).first() is not None

    # ── Password reset ────────────────────────────────────────────────────

    def create_password_reset_token(self, email: str) -> Optional[str]:
        from app.core.kernel.models.user import TokenBlacklist  # noqa: PLC0415
        from app.core.kernel.cache import rate_limit  # noqa: PLC0415

        email = email.strip()
        email_bucket = self._hash_token(email.casefold())
        if not rate_limit(
            f"password-reset-account:{email_bucket}",
            max_requests=self.settings.PASSWORD_RESET_ACCOUNT_RATE_LIMIT_MAX,
            window_seconds=self.settings.PASSWORD_RESET_ACCOUNT_RATE_LIMIT_WINDOW_SECONDS,
        ):
            # Keep the public response indistinguishable from an unknown email
            # while preventing distributed email bombing of one account.
            return None

        user = self.repo.get_by_email(email)
        if (
            not user
            or not user.is_active
            or getattr(user, "deleted_at", None) is not None
        ):
            return None
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=2)
        # One live recovery link per account. A newer request invalidates any
        # older email so a previously stolen link cannot reset the password
        # after the legitimate user has already requested another one.
        self.db.query(TokenBlacklist).filter(
            TokenBlacklist.user_id == user.id,
            TokenBlacklist.token_hash.startswith(_RESET_TOKEN_PREFIX, autoescape=True),
        ).delete(synchronize_session=False)
        self.db.add(TokenBlacklist(
            token_hash=self._password_reset_token_hash(token),
            user_id=user.id,
            expires_at=expires,
        ))
        self.db.commit()
        return token

    @classmethod
    def _password_reset_token_hash(cls, token: str) -> str:
        return f"{_RESET_TOKEN_PREFIX}{cls._hash_token(token)}"

    def confirm_password_reset(self, token: str, new_password: str) -> bool:
        from sqlalchemy import or_  # noqa: PLC0415
        from app.core.kernel.models.user import TokenBlacklist  # noqa: PLC0415

        valid, msg = validate_password_strength(new_password)
        if not valid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
        # Accept the legacy raw-token key only during its original two-hour
        # lifetime, preserving links issued just before deployment. All newly
        # issued rows are SHA-256 hashes and never expose the bearer token.
        row = self.db.query(TokenBlacklist).filter(
            or_(
                TokenBlacklist.token_hash == self._password_reset_token_hash(token),
                TokenBlacklist.token_hash == f"{_RESET_TOKEN_PREFIX}{token}",
            ),
            TokenBlacklist.expires_at > datetime.now(timezone.utc),
        ).first()
        if not row:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token expired or invalid")
        user = self.repo.get(row.user_id)
        if (
            not user
            or not user.is_active
            or getattr(user, "deleted_at", None) is not None
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token expired or invalid")

        user.password_hash = get_password_hash(new_password)
        self.db.query(TokenBlacklist).filter(
            TokenBlacklist.user_id == user.id,
            TokenBlacklist.token_hash.startswith(_RESET_TOKEN_PREFIX, autoescape=True),
        ).delete(synchronize_session=False)
        delete_refresh_tokens_for_user(self.db, user.id)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self._revoke_access_tokens(user.id)
        return True

    # ── Admin helpers ────────────────────────────────────────────────────

    def unlock_account(self, user_id: int) -> bool:
        user = self.repo.get(user_id)
        if not user:
            raise HTTPException(404, "User not found")
        user.account_locked_until = None
        user.failed_login_attempts = 0
        self.db.commit()
        return True
