"""Database operations for privacy-minimised chat metadata."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.chat.models import ChatConversation, ChatPublicFact


def token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def get_conversation_by_token(
    db: Session, raw_token: str,
) -> Optional[ChatConversation]:
    if not raw_token or len(raw_token) > 128:
        return None
    return (
        db.query(ChatConversation)
        .filter(ChatConversation.token_hash == token_digest(raw_token))
        .first()
    )


def create_conversation(
    db: Session,
    *,
    branch_id: int,
    public_reference: str,
    raw_token: str,
    language: str,
    visitor_page: Optional[str],
    expires_at: datetime,
) -> ChatConversation:
    row = ChatConversation(
        branch_id=branch_id,
        public_reference=public_reference,
        token_hash=token_digest(raw_token),
        language=language,
        visitor_page=visitor_page,
        status="active",
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def end_conversation(db: Session, row: ChatConversation) -> None:
    from app.core.config import settings  # noqa: PLC0415
    from app.resort_os.timezone_utils import local_now  # noqa: PLC0415

    row.status = "completed"
    row.ended_at = local_now(settings.TIMEZONE)
    db.commit()


def rate_conversation(
    db: Session, row: ChatConversation, rating: int,
) -> None:
    row.user_rating = rating
    db.commit()


def record_turn_usage(
    db: Session,
    row: ChatConversation,
    *,
    prompt_tokens: int,
    output_tokens: int,
) -> None:
    """Persist aggregates only; never persist the request or response text."""

    row.message_count += 1
    row.prompt_tokens += max(0, prompt_tokens)
    row.output_tokens += max(0, output_tokens)
    db.commit()


def list_approved_facts(
    db: Session,
    branch_id: int,
    *,
    now: datetime,
) -> list[ChatPublicFact]:
    return (
        db.query(ChatPublicFact)
        .filter(
            ChatPublicFact.branch_id == branch_id,
            ChatPublicFact.status == "approved",
            ChatPublicFact.approved_at.is_not(None),
            or_(
                ChatPublicFact.expires_at.is_(None),
                ChatPublicFact.expires_at > now,
            ),
        )
        .order_by(ChatPublicFact.fact_key, ChatPublicFact.id)
        .all()
    )
