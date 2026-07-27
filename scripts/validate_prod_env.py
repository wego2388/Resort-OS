#!/usr/bin/env python3
"""Fail-closed, secret-safe validation for Resort OS production settings.

The validator intentionally uses only Python's standard library so it can run
on a fresh VPS before application images or Python dependencies are installed.
It reports setting names and policy failures, never setting values.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import stat
from pathlib import Path
from urllib.parse import unquote, urlparse


WEAK_MARKERS = ("change_me", "changeme", "example", "secret", "test", "xxx")


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"line {line_number} is not KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        values[key] = value
    return values


def _is_true(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _strong_secret(values: dict[str, str], name: str, issues: list[str]) -> None:
    value = values.get(name, "")
    lowered = value.casefold()
    if len(value) < 32 or any(marker in lowered for marker in WEAK_MARKERS):
        issues.append(f"{name} must be a strong value of at least 32 characters")


def validate(path: Path, repository_root: Path) -> list[str]:
    issues: list[str] = []
    if not path.is_file():
        return [f"{path} does not exist"]

    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        issues.append(f"{path} must not be readable or writable by group/other")

    try:
        values = _read_env(path)
    except (OSError, ValueError) as exc:
        return [str(exc)]

    if values.get("ENVIRONMENT", "").strip().casefold() != "production":
        issues.append("ENVIRONMENT must equal production")
    if not _is_true(values.get("LOGIN_2FA_ENFORCED")):
        issues.append("LOGIN_2FA_ENFORCED must be true")

    _strong_secret(values, "SECRET_KEY", issues)
    _strong_secret(values, "SURVEY_TOKEN_SECRET", issues)

    encryption_key = values.get("FIELD_ENCRYPTION_KEY", "")
    try:
        decoded_key = base64.urlsafe_b64decode(encryption_key.encode("ascii"))
        if len(decoded_key) != 32:
            raise ValueError
    except (UnicodeEncodeError, ValueError):
        issues.append("FIELD_ENCRYPTION_KEY must be a valid Fernet key")

    database_url = urlparse(
        values.get("DATABASE_URL", "").replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
    )
    if database_url.hostname != "db_postgres" or (
        database_url.port or 5432
    ) != 5432:
        issues.append("DATABASE_URL must target internal db_postgres:5432")
    if len(unquote(database_url.password or "")) < 24:
        issues.append("DATABASE_URL password must be at least 24 characters")

    redis_url = urlparse(values.get("REDIS_URL", ""))
    if redis_url.hostname != "redis_cache" or (redis_url.port or 6379) != 6379:
        issues.append("REDIS_URL must target internal redis_cache:6379")

    public_url = urlparse(values.get("PUBLIC_SITE_URL", ""))
    if public_url.scheme != "https" or not public_url.hostname:
        issues.append("PUBLIC_SITE_URL must be a confirmed HTTPS origin")

    cors_origins = [
        origin.strip()
        for origin in values.get("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if not cors_origins:
        issues.append("CORS_ORIGINS must contain explicit HTTPS origins")
    for origin in cors_origins:
        parsed = urlparse(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.hostname in {"localhost", "127.0.0.1"}
        ):
            issues.append("CORS_ORIGINS may contain only explicit HTTPS origins")
            break

    marketing_context = values.get(
        "MARKETING_SITE_CONTEXT", "../elkheima-marketing-website"
    )
    context_path = Path(marketing_context)
    if not context_path.is_absolute():
        context_path = repository_root / context_path
    if not (context_path / "Dockerfile").is_file():
        issues.append("MARKETING_SITE_CONTEXT must contain a Dockerfile")

    if _is_true(values.get("CHATBOT_ENABLED")):
        if not values.get("GEMINI_API_KEY"):
            issues.append("GEMINI_API_KEY is required when CHATBOT_ENABLED=true")
        if not _is_true(values.get("CHAT_PROVIDER_DATA_GOVERNANCE_VERIFIED")):
            issues.append(
                "CHAT_PROVIDER_DATA_GOVERNANCE_VERIFIED must be true "
                "when CHATBOT_ENABLED=true"
            )
        try:
            host_map = json.loads(values.get("CHAT_PUBLIC_HOST_BRANCH_MAP", "{}"))
            if not isinstance(host_map, dict) or not host_map:
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            issues.append(
                "CHAT_PUBLIC_HOST_BRANCH_MAP must be a non-empty JSON object "
                "when CHATBOT_ENABLED=true"
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, type=Path)
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    issues = validate(args.env.resolve(), repository_root)
    if issues:
        print("Production environment validation failed:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print("Production environment validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
