"""
app/main.py
FastAPI application factory — نقطة دخول المشروع كاملة
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from wego_core.auth.router import build_auth_router
from wego_core.errors.handler import setup_error_handlers
from wego_core.health.checker import build_health_router
from wego_core.logging.setup import setup_logging
from wego_core.middleware.security import SecurityHeadersMiddleware
from wego_core.middleware.timing import RequestTimingMiddleware
from wego_core.correlation import CorrelationMiddleware
from wego_core.monitoring.sentry import setup_sentry

from app.core.config import settings
from app.core.module_loader import register_all_routes
from app.core.rate_limit import RateLimitMiddleware


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    يُسجّل كل routes عند startup.
    لا تحكم هنا في الـ modules — require_module() dependency يتولى ذلك.
    """
    register_all_routes(app)
    yield


# ── App Factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    setup_logging(settings)
    setup_sentry(settings)

    app = FastAPI(
        title=settings.RESORT_NAME,
        version="1.0.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
    )

    # ── Middleware (ترتيب مهم — من الخارج للداخل) ─────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(RequestTimingMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # ── Error Handling ─────────────────────────────────────────────────
    setup_error_handlers(app)

    # ── Fixed Routes (خارج نظام الـ modules) ──────────────────────────
    try:
        app.include_router(build_health_router(settings), prefix="/health")
    except Exception:
        pass  # graceful: health router is optional in tests

    try:
        from wego_core.models.user import User as _User  # noqa: PLC0415
        from app.core.deps import get_current_user  # noqa: PLC0415
        app.include_router(
            build_auth_router(_User, settings, get_current_user),
            prefix=f"{settings.API_PREFIX}/auth",
        )
    except Exception:
        pass  # graceful: auth router optional if User model unavailable

    from app.core.me_router import router as me_router  # noqa: PLC0415
    app.include_router(me_router, prefix=f"{settings.API_PREFIX}/auth", tags=["auth"])

    # باقي الـ routes تُسجَّل في lifespan عبر register_all_routes()

    return app


# ── Entry Point ───────────────────────────────────────────────────────────────
app = create_app()
