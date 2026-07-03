"""
app/core/kernel/auth/service.py
BaseService + AuthService — complete auth logic (login lockout, JWT issuance,
refresh token rotation, 2FA, password reset, token revocation).
"""

import hashlib
import secrets
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
from app.core.kernel.auth.repository import UserRepository


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

    def login(self, email: str, password: str) -> dict:
        max_attempts = getattr(self.settings, "MAX_LOGIN_ATTEMPTS", 5)
        lockout_minutes = getattr(self.settings, "LOCKOUT_MINUTES", 30)

        user = self.repo.get_by_email(email)
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

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
            remaining_attempts = max_attempts - attempts
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                f"Incorrect password. {remaining_attempts} attempt(s) remaining.",
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

    def change_password(self, user, old_password: str, new_password: str) -> bool:
        valid, msg = validate_password_strength(new_password)
        if not valid:
            raise HTTPException(400, msg)
        if user.role not in ("admin", "super_admin"):
            if not verify_password(old_password, user.password_hash):
                raise HTTPException(400, "Current password is incorrect")
        user.password_hash = get_password_hash(new_password)
        self.db.commit()
        return True

    def update_user(self, user_id: int, data: dict, actor) -> object:
        user = self.repo.get(user_id)
        if not user:
            raise HTTPException(404, "User not found")
        if "role" in data and actor.role != "super_admin":
            raise HTTPException(403, "Only super_admin can change roles")
        if "password" in data and data["password"]:
            data["password_hash"] = get_password_hash(data.pop("password"))
        return self.repo.update(user_id, data)

    # ── Refresh tokens ────────────────────────────────────────────────────

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create_refresh_token(self, user_id: int, device_fingerprint: Optional[str] = None) -> str:
        from app.core.kernel.models.user import RefreshToken
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS)
        self.db.add(RefreshToken(
            user_id=user_id,
            token_hash=self._hash_token(token),
            device_fingerprint=device_fingerprint,
            expires_at=expires_at,
        ))
        self.db.commit()
        return token

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
            logger.warning(f"Device fingerprint mismatch for user {rt.user_id}")
            return None
        user = self.repo.get(rt.user_id)
        if user and hasattr(user, "deleted_at") and user.deleted_at is not None:
            return None
        return user

    def rotate_refresh_token(self, old_token: str, device_fingerprint: Optional[str] = None) -> Optional[tuple]:
        """Verify old token, delete it, issue new one (rotation)."""
        from app.core.kernel.models.user import RefreshToken
        token_hash = self._hash_token(old_token)
        rt = (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.token_hash == token_hash,
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
            .first()
        )
        if not rt:
            return None
        if device_fingerprint and rt.device_fingerprint != device_fingerprint:
            logger.warning(f"Device fingerprint mismatch for user {rt.user_id}")
            return None
        user = self.repo.get(rt.user_id)
        if not user:
            return None
        self.db.delete(rt)
        self.db.commit()
        new_token = self.create_refresh_token(user.id, device_fingerprint)
        return user, new_token

    # ── 2FA ───────────────────────────────────────────────────────────────

    def setup_2fa(self, user) -> dict:
        if user.two_factor_enabled:
            raise HTTPException(400, "2FA already enabled")
        secret = pyotp.random_base32()
        user.two_factor_secret = secret
        self.db.commit()
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=getattr(self.settings, "APP_NAME", "Resort OS"),
        )
        return {
            "secret": secret,
            "provisioning_uri": uri,
            "qr_url": f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={uri}",
        }

    def enable_2fa(self, user, code: str) -> bool:
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

    def revoke_token(self, token: str, user_id: int) -> None:
        token_hash = self._hash_token(token)
        self.db.execute(
            text("""
                INSERT INTO token_blacklist (token_hash, user_id, expires_at)
                VALUES (:h, :uid, :exp) ON CONFLICT DO NOTHING
            """),
            {"h": token_hash, "uid": user_id,
             "exp": datetime.now(timezone.utc) + timedelta(days=8)},
        )
        self.db.commit()

    def is_token_revoked(self, token_hash: str) -> bool:
        row = self.db.execute(
            text("SELECT 1 FROM token_blacklist WHERE token_hash=:h AND expires_at > NOW()"),
            {"h": token_hash},
        ).fetchone()
        return row is not None

    # ── Password reset ────────────────────────────────────────────────────

    def create_password_reset_token(self, email: str) -> Optional[str]:
        user = self.repo.get_by_email(email)
        if not user:
            return None
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=2)
        self.db.execute(
            text("""
                INSERT INTO token_blacklist (token_hash, user_id, expires_at)
                VALUES (:h, :uid, :exp)
                ON CONFLICT (token_hash) DO UPDATE SET expires_at=:exp
            """),
            {"h": f"reset_{token}", "uid": user.id, "exp": expires},
        )
        self.db.commit()
        return token

    def confirm_password_reset(self, token: str, new_password: str) -> bool:
        valid, msg = validate_password_strength(new_password)
        if not valid:
            raise HTTPException(400, msg)
        row = self.db.execute(
            text("SELECT user_id FROM token_blacklist WHERE token_hash=:h AND expires_at > NOW()"),
            {"h": f"reset_{token}"},
        ).fetchone()
        if not row:
            raise HTTPException(400, "Token expired or invalid")
        user = self.repo.get(row.user_id)
        if not user:
            raise HTTPException(404, "User not found")
        user.password_hash = get_password_hash(new_password)
        self.db.execute(
            text("DELETE FROM token_blacklist WHERE token_hash=:h"),
            {"h": f"reset_{token}"},
        )
        self.db.commit()
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
