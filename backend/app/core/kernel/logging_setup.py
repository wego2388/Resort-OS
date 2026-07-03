"""
app/core/kernel/logging_setup.py
Unified loguru logging — call setup_logging(settings) once in main.py.

Production  → JSON lines to stdout (parseable by Grafana/ELK/Sentry)
Development → colored human-readable output
"""

import json
import sys
from typing import Optional
from loguru import logger

from app.core.kernel.correlation import get_request_id


def _json_sink(message) -> None:
    record = message.record
    data: dict = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "logger": record["name"],
        "func": record["function"],
        "line": record["line"],
        "msg": record["message"],
        "pid": record["process"].id,
        "correlation_id": record["extra"].get("correlation_id", ""),
    }
    ctx = {k: v for k, v in record["extra"].items() if k != "correlation_id"}
    if ctx:
        data["ctx"] = ctx
    if record["exception"]:
        exc = record["exception"]
        data["exc"] = {
            "type": exc.type.__name__ if exc.type else None,
            "value": str(exc.value) if exc.value else None,
        }
    print(json.dumps(data, ensure_ascii=False, default=str), flush=True)


def _inject_correlation(record) -> None:
    record["extra"].setdefault("correlation_id", get_request_id())


def setup_logging(settings=None, level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Configure loguru for the current environment.
    Call once at startup before any other imports that log.

    Args:
        settings: The app's Settings instance (reads .ENVIRONMENT). Falls back
                  to "development" if not provided.
        level:    Minimum log level. "DEBUG" in dev, "INFO" in prod.
        log_file: Optional file path for persistent logs (rotates at 10 MB).
    """
    env = getattr(settings, "ENVIRONMENT", None) or "development"
    logger.remove()
    logger.configure(patcher=_inject_correlation)

    if env == "production":
        logger.add(_json_sink, level=level, enqueue=True)
    else:
        logger.add(
            sys.stderr,
            format=(
                "<green>{time:HH:mm:ss}</green> "
                "<level>{level: <8}</level> "
                "<cyan>{name}</cyan>:<cyan>{line}</cyan> "
                "[<dim>{extra[correlation_id]}</dim>] "
                "— <level>{message}</level>"
            ),
            level="DEBUG" if env != "test" else "WARNING",
            colorize=True,
        )

    if log_file:
        logger.add(
            log_file,
            rotation="10 MB",
            retention="30 days",
            compression="gz",
            serialize=True,
            level=level,
            enqueue=True,
        )

    logger.info(f"[resort-os] Logging configured — env={env} level={level}")


def get_logger(name: str):
    """Return a loguru logger bound to a specific name/module."""
    return logger.bind(name=name)


async def log_request(request, response, duration_ms: float) -> None:
    """Log a completed HTTP request with timing."""
    level = "WARNING" if response.status_code >= 400 else "INFO"
    logger.log(level, "HTTP {method} {path} → {status} ({ms:.1f}ms)",
               method=request.method,
               path=request.url.path,
               status=response.status_code,
               ms=duration_ms)
