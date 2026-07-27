"""Public chat API schemas.

The contract deliberately has no client supplied history, branch, location, or
guest identity.  Those values are either not needed or are resolved from
server-side capabilities.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

_LANG_PATTERN = r"^(ar|en|ru|it)$"
_SAFE_PAGE_PATTERN = r"^/[A-Za-z0-9/_\-]{0,199}$"


class _StrictPublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChatRequest(_StrictPublicModel):
    """One stateless AI turn.

    ``session_token`` is an opaque bearer secret issued by the server.  Only
    its SHA-256 digest is stored.  Raw messages and conversation history are
    never persisted by the backend.
    """

    message: str = Field(..., min_length=1, max_length=500)
    language: str = Field("ar", pattern=_LANG_PATTERN)
    session_token: str = Field(..., min_length=32, max_length=128)
    ai_disclosure_accepted: Literal[True]


class ChatResponse(BaseModel):
    reply: str


class ConversationStart(_StrictPublicModel):
    page: Optional[str] = Field(None, max_length=200, pattern=_SAFE_PAGE_PATTERN)
    language: str = Field("ar", pattern=_LANG_PATTERN)


class ConversationStartResponse(BaseModel):
    success: bool = True
    session_token: str


class ConversationEnd(_StrictPublicModel):
    session_token: str = Field(..., min_length=32, max_length=128)


class ConversationRate(_StrictPublicModel):
    session_token: str = Field(..., min_length=32, max_length=128)
    rating: int = Field(..., ge=1, le=5)


class WelcomeResponse(BaseModel):
    message: str
