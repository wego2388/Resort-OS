"""
app/core/kernel/errors.py
Unified error handling — APIError, ErrorCode, ErrorHandler, setup_error_handlers.

Usage:
    from app.core.kernel.errors import setup_error_handlers
    setup_error_handlers(app)

    from app.core.kernel.errors import APIError, ErrorCode, ErrorHandler
    raise ErrorHandler.not_found("Booking", booking_id)
    raise APIError(ErrorCode.PAYMENT_FAILED, "Card declined", status_code=402)
"""

import traceback
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware


# ── Error codes ───────────────────────────────────────────────────────────────

class ErrorCode(str, Enum):
    INVALID_CREDENTIALS = "invalid_credentials"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_INVALID = "token_invalid"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    ACCOUNT_LOCKED = "account_locked"
    TWO_FA_REQUIRED = "2fa_required"

    VALIDATION_ERROR = "validation_error"
    INVALID_INPUT = "invalid_input"
    MISSING_FIELD = "missing_field"

    NOT_FOUND = "not_found"
    DUPLICATE = "duplicate_entry"
    CONFLICT = "conflict"

    PAYMENT_FAILED = "payment_failed"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    BOOKING_UNAVAILABLE = "booking_unavailable"
    PERIOD_CLOSED = "period_closed"

    INTERNAL_ERROR = "internal_error"
    DATABASE_ERROR = "database_error"
    SERVICE_UNAVAILABLE = "service_unavailable"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


# ── APIError ──────────────────────────────────────────────────────────────────

class APIError(Exception):
    """Raise anywhere in service/route code — auto-converted to JSON response."""

    def __init__(
        self,
        error_code: "ErrorCode | str",
        message: str,
        status_code: int = 400,
        details: Optional[Dict] = None,
        log_level: str = "warning",
    ):
        self.error_code = error_code if isinstance(error_code, str) else error_code.value
        self.message = message
        self.status_code = status_code
        self.details = details or {}

        if log_level == "error":
            logger.error(f"[{self.error_code}] {self.message}")
        elif log_level == "warning":
            logger.warning(f"[{self.error_code}] {self.message}")

    def to_dict(self) -> dict:
        return {
            "success": False,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details or None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def to_response(self) -> JSONResponse:
        return JSONResponse(status_code=self.status_code, content=self.to_dict())


# ── ErrorHandler factory ──────────────────────────────────────────────────────

class ErrorHandler:
    """Convenience factory — DRY raise helpers."""

    @staticmethod
    def not_found(resource: str, identifier: Any = None) -> APIError:
        msg = f"{resource} not found"
        if identifier:
            msg += f" (id: {identifier})"
        return APIError(ErrorCode.NOT_FOUND, msg, 404,
                        {"resource": resource, "id": identifier})

    @staticmethod
    def duplicate(field: str, value: Any = None) -> APIError:
        return APIError(ErrorCode.DUPLICATE, f"{field} already exists", 409,
                        {"field": field, "value": value})

    @staticmethod
    def unauthorized(reason: str = "Unauthorized") -> APIError:
        return APIError(ErrorCode.UNAUTHORIZED, reason, 401)

    @staticmethod
    def forbidden(reason: str = "Forbidden") -> APIError:
        return APIError(ErrorCode.FORBIDDEN, reason, 403)

    @staticmethod
    def validation(field: str, issue: str) -> APIError:
        return APIError(ErrorCode.VALIDATION_ERROR,
                        f"Validation error: {field} — {issue}", 422,
                        {"field": field, "issue": issue})

    @staticmethod
    def payment_failed(msg: str, provider: Optional[Dict] = None) -> APIError:
        return APIError(ErrorCode.PAYMENT_FAILED,
                        f"Payment failed: {msg}", 402,
                        provider or {}, log_level="error")

    @staticmethod
    def database(exc: Exception) -> APIError:
        logger.error(f"DB error: {exc}\n{traceback.format_exc()}")
        return APIError(ErrorCode.DATABASE_ERROR,
                        "A database error occurred. Please try again.", 500,
                        {"type": type(exc).__name__}, log_level="error")

    @staticmethod
    def external(service: str, exc: Exception) -> APIError:
        logger.error(f"{service} error: {exc}")
        return APIError(ErrorCode.EXTERNAL_SERVICE_ERROR,
                        f"Failed to reach {service}. Try again later.", 503,
                        {"service": service}, log_level="error")

    @staticmethod
    def internal(exc: Exception) -> APIError:
        logger.error(f"Internal error: {exc}\n{traceback.format_exc()}")
        return APIError(ErrorCode.INTERNAL_ERROR,
                        "An unexpected error occurred.", 500, log_level="error")


# ── Secure error middleware ───────────────────────────────────────────────────

class SecureErrorMiddleware(BaseHTTPMiddleware):
    """Catches unhandled exceptions — never leaks stack traces to clients."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except APIError as exc:
            return exc.to_response()
        except SQLAlchemyError as exc:
            # ⚠️ لا تستخدم f-string هنا أبداً — رسائل SQLAlchemy بتتضمّن
            # [parameters: {...}] كـ dict repr، وloguru بيعمل .format() على
            # نص الرسالة النهائي. أي براكيت حرفية جوه exc بتخلي .format() يفشل
            # بـ KeyError ويكسر الـ error handler نفسه (باج حقيقي كان بيمنع
            # ظهور أي رسالة خطأ حقيقية لأي DB error فيه براكيت في نصه — يعني
            # كل استجابة 500 كانت بتوصل للمستخدم فاضية بدل الرسالة المتوقعة).
            # التمبلت هنا نص حرفي بمكانين {} بس، والقيم بتتمرر كـ args منفصلة
            # فمفيش إعادة معالجة للبراكيت اللي جوه exc نفسه.
            logger.opt(exception=True).error("Unhandled DB error on {}: {}", request.url.path, exc)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error_code": "database_error",
                         "message": "Database operation failed"},
            )
        except Exception as exc:
            ref = f"ERR-{int(datetime.now().timestamp())}"
            logger.opt(exception=True).critical("Unhandled exception [{}] on {}: {}", ref, request.url.path, exc)
            return JSONResponse(
                status_code=500,
                content={"success": False, "error_code": "internal_error",
                         "message": f"Internal error — ref: {ref}"},
            )


# ── App registration ──────────────────────────────────────────────────────────

def setup_error_handlers(app: FastAPI) -> None:
    """Register all error handlers on the FastAPI app. Call in main.py."""
    app.add_middleware(SecureErrorMiddleware)

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            field = ".".join(str(loc) for loc in err["loc"] if loc != "body")
            errors.append({"field": field or "body", "issue": err["msg"]})
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "error_code": ErrorCode.VALIDATION_ERROR.value,
                "message": "Request validation failed",
                "details": {"errors": errors},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        # ⚠️ باج حقيقي كان موجود من زمان: أي `raise HTTPException(404, "...")`
        # حقيقي جوه أي route في الـ 14 موديول (زي "الموظف غير موجود"، "الحجز
        # غير موجود") كان بيتلخبط هنا مع الحالة التانية (مفيش route مطابق
        # أصلاً) — الاتنين كانوا بيرجعوا نفس الرسالة العامة "Path not found"،
        # يعني كل رسالة 404 حقيقية في المشروع كله كانت بتوصل فاضية من التفاصيل
        # (اتوثّق قبل كده في CLAUDE.md كباج معروف من مكتبة مشتركة، بس الـ kernel
        # بقى مملوك بالكامل لـ resort-os دلوقتي فمفيش سبب نسيبه من غير حل).
        # Starlette بيدّي أي HTTPException(404) من غير detail صريح القيمة
        # الافتراضية `http.HTTPStatus(404).phrase` == "Not Found" بالظبط — وده
        # بالظبط اللي بيحصل لما مفيش route مطابق أصلاً. أي قيمة تانية معناها
        # الرسالة دي جت من route حقيقي اتنفّذ وقرر يرمي 404 بسبب محدد.
        detail = getattr(exc, "detail", None)
        message = detail if detail and detail != "Not Found" else f"Path not found: {request.url.path}"
        return JSONResponse(
            status_code=404,
            content={"success": False, "error_code": "not_found", "message": message},
        )
