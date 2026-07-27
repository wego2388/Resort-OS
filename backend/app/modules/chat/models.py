"""Privacy-minimised persistence for the public AI assistant.

No raw guest message or model reply is stored.  Conversation rows contain only
an opaque token digest, lifecycle state, and aggregate usage counters.
Approved public facts are a separate, auditable allowlist for prompt content.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.kernel.models.mixins import TimestampMixin


class ChatConversation(Base, TimestampMixin):
    __tablename__ = "chat_conversations"
    __table_args__ = (
        CheckConstraint(
            "language IN ('ar','en','ru','it')",
            name="ck_chat_conversations_language",
        ),
        CheckConstraint(
            "status IN ('active','completed')",
            name="ck_chat_conversations_status",
        ),
        CheckConstraint(
            "user_rating IS NULL OR user_rating BETWEEN 1 AND 5",
            name="ck_chat_conversations_rating",
        ),
        CheckConstraint(
            "message_count >= 0 AND prompt_tokens >= 0 AND output_tokens >= 0",
            name="ck_chat_conversations_usage_nonnegative",
        ),
        Index(
            "ix_chat_conversations_branch_status_created",
            "branch_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"),
        index=True,
    )
    public_reference: Mapped[str] = mapped_column(
        String(48), unique=True, index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    language: Mapped[str] = mapped_column(String(5), default="ar")
    visitor_page: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)


class ChatPublicFact(Base, TimestampMixin):
    """A public statement explicitly approved for inclusion in the AI prompt."""

    __tablename__ = "chat_public_facts"
    __table_args__ = (
        UniqueConstraint(
            "branch_id", "fact_key", name="uq_chat_public_facts_branch_key",
        ),
        CheckConstraint(
            "status IN ('draft','approved','retired')",
            name="ck_chat_public_facts_status",
        ),
        CheckConstraint(
            "status != 'approved' OR approved_at IS NOT NULL",
            name="ck_chat_public_facts_approval_timestamp",
        ),
        Index(
            "ix_chat_public_facts_branch_status_expiry",
            "branch_id",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("branches.id", ondelete="CASCADE"),
        index=True,
    )
    fact_key: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    source_reference: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
