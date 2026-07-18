"""
app/core/kernel/models/user.py
User, RefreshToken, TokenBlacklist, TwoFactorRecoveryCode — owned by resort-os.

The original columns still map onto the former wego_core-backed tables. Gate
2B2 adds explicit bootstrap state and hashed one-time recovery codes through
the forward Alembic migration ``a7c2e91f4b6d``.
"""

import enum
from sqlalchemy import (
    Boolean,
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    Numeric,
    String,
    TIMESTAMP,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.core.kernel.database import Base
from app.core.encryption import EncryptedString


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MANAGER = "manager"
    SUPERVISOR = "supervisor"
    ACCOUNTANT = "accountant"
    HR_MANAGER = "hr_manager"
    RECEPTIONIST = "receptionist"
    CASHIER = "cashier"
    WAITER = "waiter"
    CHEF = "chef"
    KITCHEN = "kitchen"
    EMPLOYEE = "employee"
    CUSTOMER = "customer"
    GUEST = "guest"


class UserMixin:
    """Pure SQLAlchemy column mixin — no __tablename__, no Base."""

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    role = Column(String(30), default=UserRole.CUSTOMER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Security
    failed_login_attempts = Column(Integer, server_default="0")
    account_locked_until = Column(TIMESTAMP, nullable=True)

    # 2FA — the TOTP shared secret is PII-grade: whoever reads it can mint
    # valid codes forever, so it's encrypted at rest (Fernet). Legacy plaintext
    # rows still decode: EncryptedString falls back to the raw value on
    # InvalidToken, so this is transparent with no migration/backfill required.
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(EncryptedString(255), nullable=True)
    # Gate 2B2: privileged/bootstrap accounts cannot be claimed by whoever
    # happens to know a seeded or temporary password first.  The operator
    # must also present a separate, short-lived enrollment token issued by
    # the local bootstrap command.  Only its SHA-256 hash is persisted.
    two_factor_bootstrap_required = Column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )
    two_factor_enrollment_token_hash = Column(String(64), nullable=True)
    two_factor_enrollment_expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Highest accepted TOTP counter. Conditional updates make a six-digit code
    # one-time even when two login requests race inside the same 30s window.
    two_factor_last_used_step = Column(BigInteger, nullable=True)

    # A temporary/bootstrap credential is not considered an operational
    # password.  get_current_active_user keeps the account inside /auth/*
    # until the user replaces it successfully.
    must_change_password = Column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
    )

    # Profile
    email_verified = Column(Boolean, default=False)
    profile_photo_url = Column(String(500), nullable=True)
    preferred_language = Column(String(10), default="ar")

    # Staff fields (nullable — only populated for staff roles)
    job_title = Column(String(100), nullable=True)
    department = Column(String(50), nullable=True)
    national_id = Column(String(30), nullable=True)
    hire_date = Column(TIMESTAMP, nullable=True)
    contract_type = Column(String(20), nullable=True)   # full_time | part_time | seasonal
    base_salary = Column(Numeric(10, 2), nullable=True)
    emergency_phone = Column(String(50), nullable=True)

    # Gamification / loyalty
    loyalty_points = Column(Integer, default=0, nullable=False)
    visit_count = Column(Integer, default=0, nullable=False)
    last_visit_at = Column(TIMESTAMP, nullable=True)

    # Soft delete
    deleted_at = Column(TIMESTAMP, nullable=True)

    @property
    def is_staff(self) -> bool:
        return self.role not in (UserRole.CUSTOMER, UserRole.GUEST)

    @property
    def is_admin(self) -> bool:
        return self.role in (UserRole.SUPER_ADMIN, UserRole.ADMIN)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class User(Base, UserMixin):
    __tablename__ = "users"


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(255), nullable=False, index=True)
    device_fingerprint = Column(String(255), nullable=True)
    expires_at = Column(TIMESTAMP, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())


class TwoFactorRecoveryCode(Base):
    """One-time, high-entropy recovery codes for an enrolled 2FA account.

    The plaintext code is returned once at enrollment/regeneration time.  A
    SHA-256 digest is sufficient here because generated codes carry 120 bits
    of entropy; the database never stores a reusable bearer secret.
    """

    __tablename__ = "two_factor_recovery_codes"
    __table_args__ = (
        UniqueConstraint("user_id", "code_hash", name="uq_2fa_recovery_user_code"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash = Column(String(64), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at = Column(TIMESTAMP, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
