"""Public, privacy-minimised AI chat endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from app.core.config import settings
from app.core.deps import DbDep
from app.core.rate_limit import _client_ip
from app.modules.chat import crud, services
from app.modules.chat.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationEnd,
    ConversationRate,
    ConversationStart,
    ConversationStartResponse,
    WelcomeResponse,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _site_branch_or_503(request: Request, db: DbDep):
    branch = services.resolve_site_branch(db, request.url.hostname)
    if branch is None:
        raise HTTPException(
            503,
            "Chat service is not configured for this site.",
            headers={"Cache-Control": "no-store"},
        )
    return branch


def _active_conversation_or_409(db: DbDep, token: str, branch_id: int):
    row = crud.get_conversation_by_token(db, token)
    if (
        row is None
        or row.branch_id != branch_id
        or row.status != "active"
        or row.expires_at <= datetime.utcnow()
    ):
        raise HTTPException(
            409,
            "Chat session is invalid or expired.",
            headers={"Cache-Control": "no-store"},
        )
    return row


def _trusted_guest_location(
    db: DbDep,
    branch_id: int,
    guest_session_token: str | None,
) -> str | None:
    if not guest_session_token:
        return None
    from app.modules.core import services as core_services  # noqa: PLC0415

    try:
        _session, location = core_services.resolve_guest_session(
            db, guest_session_token,
        )
    except ValueError as exc:
        raise HTTPException(
            409,
            "Guest session is invalid or expired.",
            headers={"Cache-Control": "no-store"},
        ) from exc
    if location.branch_id != branch_id:
        raise HTTPException(
            403,
            "Guest session does not belong to this site.",
            headers={"Cache-Control": "no-store"},
        )
    return location.location_type


@router.get("/welcome", response_model=WelcomeResponse)
def get_welcome(
    request: Request,
    response: Response,
    db: DbDep,
    language: str = Query("ar", pattern=r"^(ar|en|ru|it)$"),
):
    _no_store(response)
    branch = _site_branch_or_503(request, db)
    return WelcomeResponse(
        message=services.build_welcome_message(db, branch.id, language),
    )


@router.post(
    "/conversations/start",
    response_model=ConversationStartResponse,
)
def start_conversation(
    request: Request,
    response: Response,
    db: DbDep,
    data: ConversationStart,
):
    _no_store(response)
    branch = _site_branch_or_503(request, db)
    public_reference, raw_token = services.new_session_credentials()
    crud.create_conversation(
        db,
        branch_id=branch.id,
        public_reference=public_reference,
        raw_token=raw_token,
        language=data.language,
        visitor_page=data.page,
        expires_at=datetime.utcnow()
        + timedelta(minutes=settings.CHAT_SESSION_TTL_MINUTES),
    )
    return ConversationStartResponse(session_token=raw_token)


@router.post("/conversations/rate")
def rate_conversation(
    request: Request,
    response: Response,
    db: DbDep,
    data: ConversationRate,
):
    _no_store(response)
    branch = _site_branch_or_503(request, db)
    row = crud.get_conversation_by_token(db, data.session_token)
    # Do not leak whether a supplied bearer token exists.
    if (
        row is not None
        and row.branch_id == branch.id
        and row.status == "active"
        and row.expires_at > datetime.utcnow()
    ):
        crud.rate_conversation(db, row, data.rating)
    return {"success": True}


@router.post("/conversations/end")
def end_conversation(
    request: Request,
    response: Response,
    db: DbDep,
    data: ConversationEnd,
):
    _no_store(response)
    branch = _site_branch_or_503(request, db)
    row = crud.get_conversation_by_token(db, data.session_token)
    # Idempotent and non-enumerable.
    if (
        row is not None
        and row.branch_id == branch.id
        and row.status == "active"
    ):
        crud.end_conversation(db, row)
    return {"success": True}


@router.post("", response_model=ChatResponse)
async def chat(
    request: Request,
    response: Response,
    db: DbDep,
    req: ChatRequest,
    x_guest_session: str | None = Header(None, alias="X-Guest-Session"),
):
    _no_store(response)
    branch = _site_branch_or_503(request, db)
    conversation = _active_conversation_or_409(
        db, req.session_token, branch.id,
    )
    location_type = _trusted_guest_location(
        db, branch.id, x_guest_session,
    )

    if not services.provider_preflight_ready():
        raise HTTPException(
            503,
            "Chat service is not configured.",
            headers={"Cache-Control": "no-store"},
        )
    if not services.production_cost_guard_ready():
        raise HTTPException(
            503,
            "Chat cost protection is unavailable.",
            headers={"Cache-Control": "no-store"},
        )

    safe_message = services.sanitize_message(req.message)
    system_prompt = services.build_system_prompt(db, branch.id)
    max_cost = services.estimate_max_cost_usd(system_prompt, safe_message)
    exhausted = services.reserve_request_budgets(
        ip=_client_ip(request),
        session_token=req.session_token,
        estimated_cost_usd=max_cost,
    )
    if exhausted in {"ip", "session"}:
        raise HTTPException(
            429,
            "Chat usage limit reached. Please try later.",
            headers={"Cache-Control": "no-store", "Retry-After": "3600"},
        )
    if exhausted is not None:
        raise HTTPException(
            503,
            "Chat daily provider budget has been reached.",
            headers={"Cache-Control": "no-store", "Retry-After": "3600"},
        )

    if not services.acquire_concurrency_slot():
        services.record_rejection("concurrency")
        raise HTTPException(
            503,
            "Chat service is busy. Please try again shortly.",
            headers={"Cache-Control": "no-store", "Retry-After": "5"},
        )

    try:
        try:
            result = await services.get_ai_response(
                system_prompt,
                safe_message,
                req.language,
                location_type=location_type,
            )
        except RuntimeError as exc:
            reason = str(exc)
            status_code = {
                "not_configured": 503,
                "circuit_open": 503,
                "timeout": 504,
                "blocked": 502,
                "invalid_response": 502,
                "unavailable": 502,
            }.get(reason, 502)
            raise HTTPException(
                status_code,
                "Chat service is currently unavailable.",
                headers={"Cache-Control": "no-store"},
            ) from exc

        crud.record_turn_usage(
            db,
            conversation,
            prompt_tokens=result.prompt_tokens,
            output_tokens=result.output_tokens,
        )
        return ChatResponse(reply=result.reply)
    finally:
        services.release_concurrency_slot()
