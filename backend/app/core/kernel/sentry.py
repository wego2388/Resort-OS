"""
app/core/kernel/sentry.py
Sentry error tracking + performance monitoring setup.

Usage:
    # main.py
    from app.core.kernel.sentry import setup_sentry
    setup_sentry(settings, app)

    # Manual capture anywhere
    from app.core.kernel.sentry import capture_exception
    try:
        risky_operation()
    except Exception as e:
        capture_exception(e, extra={"order_id": 123})

    .env:
        SENTRY_DSN=https://xxxx@o0.ingest.sentry.io/0
        SENTRY_ENVIRONMENT=production   ← optional, defaults to ENVIRONMENT
        SENTRY_TRACES_SAMPLE_RATE=0.1
"""

import os
from typing import Any, Optional

from loguru import logger


_initialized = False


def setup_sentry(settings=None, app=None) -> bool:
    """
    Initialize Sentry SDK. Call once at app startup.

    Returns:
        True if Sentry was configured, False if DSN is missing or sdk not installed.
    """
    global _initialized
    if _initialized:
        return True

    dsn = getattr(settings, "SENTRY_DSN", None) or os.getenv("SENTRY_DSN", "")
    if not dsn:
        logger.debug("[Sentry] No SENTRY_DSN configured — error tracking disabled")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logger.warning("[Sentry] sentry-sdk not installed — pip install sentry-sdk[fastapi]")
        return False

    environment = (
        getattr(settings, "SENTRY_ENVIRONMENT", None)
        or os.getenv("SENTRY_ENVIRONMENT")
        or getattr(settings, "ENVIRONMENT", None)
        or os.getenv("ENVIRONMENT", "production")
    )
    release = getattr(settings, "APP_VERSION", None) or os.getenv("APP_VERSION", "")
    traces_rate = float(
        getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", None)
        or os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")
    )

    integrations = [
        SqlalchemyIntegration(),
        LoggingIntegration(level=None, event_level=None),  # don't duplicate loguru logs
    ]

    if app is not None:
        try:
            from sentry_sdk.integrations.starlette import StarletteIntegration
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            integrations += [StarletteIntegration(), FastApiIntegration()]
        except ImportError:
            pass

    try:
        from sentry_sdk.integrations.celery import CeleryIntegration
        integrations.append(CeleryIntegration())
    except ImportError:
        pass

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or None,
        traces_sample_rate=traces_rate,
        integrations=integrations,
        send_default_pii=False,
        attach_stacktrace=True,
        before_send=_before_send,
    )

    app_name = getattr(settings, "APP_NAME", None) or os.getenv("APP_NAME", "resort-os")
    logger.info(f"[Sentry] initialized for {app_name!r} env={environment!r}")
    _initialized = True
    return True


def capture_exception(exc: Exception, *, extra: Optional[dict] = None, tags: Optional[dict] = None) -> Optional[str]:
    """Manually capture an exception with optional extra context."""
    if not _initialized:
        return None
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if extra:
                for k, v in extra.items():
                    scope.set_extra(k, v)
            if tags:
                for k, v in tags.items():
                    scope.set_tag(k, v)
            return sentry_sdk.capture_exception(exc)
    except Exception as e:
        logger.debug(f"[Sentry] capture_exception failed: {e}")
        return None


def capture_message(message: str, level: str = "info", *, extra: Optional[dict] = None) -> Optional[str]:
    """Capture an informational message in Sentry."""
    if not _initialized:
        return None
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if extra:
                for k, v in extra.items():
                    scope.set_extra(k, v)
            return sentry_sdk.capture_message(message, level=level)
    except Exception as e:
        logger.debug(f"[Sentry] capture_message failed: {e}")
        return None


def set_user_context(
    user_id: Any = None,
    email: Optional[str] = None,
    role: Optional[str] = None,
    username: Optional[str] = None,
) -> None:
    """Tag the current Sentry scope with user info for better error attribution."""
    if not _initialized:
        return
    try:
        import sentry_sdk
        sentry_sdk.set_user({
            "id": str(user_id) if user_id is not None else None,
            "email": email,
            "username": username,
            "role": role,
        })
    except Exception:
        pass


def add_breadcrumb(message: str, category: str = "app", level: str = "info", data: Optional[dict] = None) -> None:
    """Add a breadcrumb to trace what led to an error."""
    if not _initialized:
        return
    try:
        import sentry_sdk
        sentry_sdk.add_breadcrumb(message=message, category=category, level=level, data=data or {})
    except Exception:
        pass


def is_initialized() -> bool:
    return _initialized


def _before_send(event: dict, hint: dict) -> Optional[dict]:
    """Filter out non-actionable errors."""
    exc_info = hint.get("exc_info")
    if exc_info:
        exc_type = exc_info[0]
        if exc_type and exc_type.__name__ in ("HTTPException",):
            try:
                if hint["exc_info"][1].status_code < 500:
                    return None
            except Exception:
                pass
    return event
