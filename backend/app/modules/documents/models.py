"""Database models for the private legal and HR document vault."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.encryption import EncryptedString
from app.core.kernel.models.mixins import SoftDeleteMixin, TimestampMixin


class Document(Base, TimestampMixin, SoftDeleteMixin):
    """Metadata for one encrypted file stored outside the public upload tree."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "(scope = 'branch' AND employee_id IS NULL) OR "
            "(scope = 'employee' AND employee_id IS NOT NULL)",
            name="ck_documents_subject_scope",
        ),
        CheckConstraint(
            "(scope = 'branch' AND visibility IN ('management', 'owner_visible')) OR "
            "(scope = 'employee' AND visibility IN ('hr_confidential', 'employee_visible'))",
            name="ck_documents_visibility_scope",
        ),
        CheckConstraint(
            "expiry_date IS NULL OR issue_date IS NULL OR expiry_date >= issue_date",
            name="ck_documents_expiry_after_issue",
        ),
        CheckConstraint("size_bytes > 0", name="ck_documents_positive_size"),
        CheckConstraint("version_number >= 1", name="ck_documents_positive_version"),
        Index(
            "ix_documents_branch_scope_active",
            "branch_id",
            "scope",
            "doc_type",
            postgresql_where=text("deleted_at IS NULL AND superseded_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL AND superseded_at IS NULL"),
        ),
        Index(
            "ix_documents_employee_active",
            "employee_id",
            postgresql_where=text("employee_id IS NOT NULL AND deleted_at IS NULL"),
            sqlite_where=text("employee_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index(
            "ix_documents_expiry_active",
            "expiry_date",
            postgresql_where=text("expiry_date IS NOT NULL AND deleted_at IS NULL AND superseded_at IS NULL"),
            sqlite_where=text("expiry_date IS NOT NULL AND deleted_at IS NULL AND superseded_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True,
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True, index=True,
    )

    doc_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    storage_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(EncryptedString(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    replaces_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=True, index=True,
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    deleted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )


class DocumentExpiryNotification(Base, TimestampMixin):
    """Idempotency ledger for the daily expiry scanner."""

    __tablename__ = "document_expiry_notifications"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "expiry_date",
            "threshold_days",
            name="uq_document_expiry_notification_band",
        ),
        CheckConstraint(
            "threshold_days IN (-1, 7, 30, 60)",
            name="ck_document_expiry_notification_threshold",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    threshold_days: Mapped[int] = mapped_column(Integer, nullable=False)
