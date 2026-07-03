"""
app/core/kernel/models/user.py
User, RefreshToken, TokenBlacklist — owned by resort-os.

Column layout is unchanged from the previous wego_core-backed models (this
maps onto the existing `users` / `refresh_tokens` / `token_blacklist` tables
— no migration needed, this is the same schema, just no longer imported
from an external package).
"""

import enum
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, Numeric, ForeignKey
from sqlalchemy.sql import func

from app.core.kernel.database import Base


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

    # 2FA
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String(255), nullable=True)

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


class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    expires_at = Column(TIMESTAMP, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
