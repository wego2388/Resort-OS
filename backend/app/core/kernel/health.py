"""
app/core/kernel/health.py
Health checker — DB, Redis. Mounted at /health in main.py.
"""

import time
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

__version__ = "1.0.0"


async def _check_db(db_url: str) -> dict:
    start = time.monotonic()
    try:
        from sqlalchemy import text
        from app.core.kernel.database import get_engine
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "latency_ms": round((time.monotonic() - start) * 1000, 1)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def _check_redis(redis_url: Optional[str]) -> dict:
    if not redis_url:
        return {"status": "not_configured"}
    start = time.monotonic()
    try:
        import redis as _r
        client = _r.from_url(redis_url, socket_timeout=2, socket_connect_timeout=2)
        client.ping()
        client.close()
        return {"status": "ok", "latency_ms": round((time.monotonic() - start) * 1000, 1)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def build_health_router(settings) -> APIRouter:
    router = APIRouter()

    @router.get("/live")
    async def liveness():
        """Kubernetes liveness probe — always 200 if process is up."""
        return {"status": "ok"}

    @router.get("/ready")
    async def readiness():
        """Kubernetes readiness probe — checks DB + Redis."""
        db_check = await _check_db(settings.DATABASE_URL)
        redis_check = await _check_redis(getattr(settings, "REDIS_URL", None))

        healthy = db_check["status"] == "ok"
        status = "ok" if healthy else "degraded"

        return JSONResponse(
            status_code=200 if healthy else 503,
            content={
                "status": status,
                "app": getattr(settings, "APP_NAME", "Resort OS"),
                "checks": {"database": db_check, "redis": redis_check},
            },
        )

    @router.get("")
    async def health_full():
        """Full health info — app name, version, environment, all checks."""
        db_check = await _check_db(settings.DATABASE_URL)
        redis_check = await _check_redis(getattr(settings, "REDIS_URL", None))

        checks = {"database": db_check, "redis": redis_check}
        healthy = db_check["status"] == "ok"

        return JSONResponse(
            status_code=200 if healthy else 503,
            content={
                "status": "ok" if healthy else "degraded",
                "app": getattr(settings, "APP_NAME", "Resort OS"),
                "environment": getattr(settings, "ENVIRONMENT", "unknown"),
                "version": __version__,
                "checks": checks,
            },
        )

    return router
