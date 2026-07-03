"""
app/core/kernel/middleware.py
SecurityHeadersMiddleware (OWASP headers) + RequestTimingMiddleware
(X-Response-Time + request logging).
"""

import time

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.kernel.security import get_security_headers


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings):
        super().__init__(app)
        self._headers = get_security_headers(settings)

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for key, value in self._headers.items():
            response.headers[key] = value
        return response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration = (time.monotonic() - start) * 1000

        level = "WARNING" if response.status_code >= 400 else "DEBUG"
        logger.log(
            level,
            "{method} {path} → {status} ({ms:.1f}ms)",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            ms=duration,
        )
        response.headers["X-Response-Time"] = f"{duration:.1f}ms"
        return response
