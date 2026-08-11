"""
app/main.py
FastAPI application factory — نقطة دخول المشروع كاملة
"""
from __future__ import annotations

import importlib
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from app.core.kernel.auth.router import build_auth_router
from app.core.kernel.errors import setup_error_handlers
from app.core.kernel.health import build_health_router
from app.core.kernel.logging_setup import setup_logging
from app.core.kernel.middleware import SecurityHeadersMiddleware, RequestTimingMiddleware
from app.core.kernel.correlation import CorrelationMiddleware
from app.core.kernel.sentry import setup_sentry

from app.core.config import settings
from app.core.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)


class SensitiveNoStoreMiddleware(BaseHTTPMiddleware):
    """Prevent caching for chat and financial credit responses, including errors."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(("/api/v1/chat", "/api/v1/credit")):
            response.headers["Cache-Control"] = "no-store"
        return response

# كل الموديولات دايمًا مفعّلة — مفيش نظام تفعيل/تعطيل. القايمة هنا بس لتحديد
# ترتيب الـ router registration، مش لأي قرار وصول.
# DINING_CUTOVER_PLAN.md Batch 6 — restaurant/cafe اتشالوا (dining هو
# المصدر الوحيد للحقيقة دلوقتي، راجع CLAUDE.md §18 للتاريخ الكامل).
_MODULE_KEYS = (
    "core", "finance", "inventory", "hr", "dining", "pms",
    "timeshare", "beach", "maintenance", "crm", "analytics", "hub", "leasing",
    "chat", "owner", "credit",
)


def _register_all_routes(app: FastAPI) -> None:
    """يُسجّل routers كل الموديولات عند startup — كلها دايمًا شغالة."""
    for key in _MODULE_KEYS:
        try:
            mod = importlib.import_module(f"app.modules.{key}.api.router")
            app.include_router(mod.router, prefix="/api/v1")
            logger.info("✓ Router registered: %s", key)
        except ModuleNotFoundError:
            logger.debug("Router not yet implemented: %s — skipped", key)

    # ── Static files: رفع صور قائمة الطعام (4-D) ──────────────────────
    import os  # noqa: PLC0415
    from fastapi.staticfiles import StaticFiles  # noqa: PLC0415
    uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """يُسجّل كل routes عند startup.

    ⚠️ باج حقيقي حي (2026-08-10): `_register_all_routes` بيستورد كل
    `api/router.py` بس — أي موديول models بيتسجل بس لو الـrouter بتاعه
    استورده (مباشر أو transitively عبر services). ده معتمد على ترتيب/محتوى
    استيرادات كل موديول، مش مضمون. لوحظ فعليًا: `GuestReview`'s
    `relationship("ReviewCategory")` كان بيفشل 500 قصدي على `/auth/login`
    و`/auth/refresh` في بعض الـworker processes بس (نفس الباج المكتشف قبل
    كده في الأدوات المستقلة — راجع app.seed._import_all_models's توثيق)،
    لأن SQLAlchemy's lazy `configure_mappers()` بيتنفذ أول query حقيقي في
    أي endpoint، قبل ما `analytics.models` (المسجّلة الحادي عشر في
    `_MODULE_KEYS`) تتستورد فعليًا في نفس العملية. الحل: نفس دالة الاستيراد
    الحتمية الجاهزة، هنا كمان — قبل أي route registration، مش بعده.
    """
    from app.seed import _import_all_models  # noqa: PLC0415
    _import_all_models()
    _register_all_routes(app)
    yield


# ── App Factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    setup_logging(settings)
    setup_sentry(settings)

    # ⚠️ enforce_owner_access_policy إجباري هنا على مستوى التطبيق كله —
    # مش على owner router بس. باج أمني حقيقي اتصلح 2026-08-11: النسخة
    # القديمة (enforce_owner_write_policy) كانت موجودة من فترة لكن من غير
    # أي استدعاء في أي مكان في المشروع خالص — owner كان يقدر يوصل لأي
    # endpoint في المشروع (زي POST /crm/customers) بطلب صالح. راجع
    # app/modules/owner/owner_policy.py's docstring الكامل للتفاصيل.
    from app.modules.owner.owner_policy import enforce_owner_access_policy  # noqa: PLC0415

    app = FastAPI(
        title=settings.RESORT_NAME,
        version="1.0.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        lifespan=lifespan,
        dependencies=[Depends(enforce_owner_access_policy)],
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
    app.add_middleware(SensitiveNoStoreMiddleware)

    # ── Error Handling ─────────────────────────────────────────────────
    setup_error_handlers(app)

    # ── Fixed Routes (خارج نظام الـ modules) ──────────────────────────
    try:
        app.include_router(build_health_router(settings), prefix="/health")
    except Exception:
        pass  # graceful: health router is optional in tests

    try:
        from app.core.kernel.models.user import User as _User  # noqa: PLC0415
        from app.core.deps import get_current_user  # noqa: PLC0415
        app.include_router(
            build_auth_router(_User, settings, get_current_user),
            prefix=f"{settings.API_PREFIX}/auth",
        )
    except Exception:
        pass  # graceful: auth router optional if User model unavailable

    from app.core.me_router import router as me_router  # noqa: PLC0415
    app.include_router(me_router, prefix=f"{settings.API_PREFIX}/auth", tags=["auth"])

    # باقي الـ routes تُسجَّل في lifespan عبر _register_all_routes()

    return app


# ── Entry Point ───────────────────────────────────────────────────────────────
app = create_app()
