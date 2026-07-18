"""
app/core/kernel/security.py
JWT, bcrypt password hashing, input sanitization, OWASP security headers.
"""

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import bcrypt
from jose import JWTError, jwt  # noqa: F401 — JWTError re-exported for project use


# ── Password ──────────────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def validate_password_strength(password: str) -> Tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not any(c.isupper() for c in password):
        return False, "Password must contain uppercase letters"
    if not any(c.islower() for c in password):
        return False, "Password must contain lowercase letters"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain numbers"
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        return False, "Password must contain special characters"
    return True, "OK"


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(
    data: Dict[str, Any],
    secret_key: str,
    algorithm: str = "HS256",
    expires_delta: Optional[timedelta] = None,
) -> str:
    payload = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=15))
    # Keep sub-second precision for iat. Session revocation stores a precise
    # cutoff timestamp; integer-second JWT dates can otherwise reject a fresh
    # login made later in the same second as a password/role change (or leave
    # an older token from that second indistinguishable from the new one).
    payload.update({"exp": expire, "iat": now.timestamp()})
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_token(token: str, secret_key: str, algorithm: str = "HS256") -> Dict[str, Any]:
    return jwt.decode(token, secret_key, algorithms=[algorithm])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── Input sanitization ────────────────────────────────────────────────────────

_DANGEROUS_RE = re.compile(
    r"<script[\s\S]*?</script>|javascript\s*:|on\w+\s*=|data\s*:\s*text/html",
    re.IGNORECASE,
)


def sanitize_input(value: str, max_length: int = 500) -> str:
    if not value:
        return ""
    cleaned = _DANGEROUS_RE.sub("", value.strip())
    return html.escape(cleaned)[:max_length]


def validate_email_format(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_phone_format(phone: str) -> bool:
    cleaned = re.sub(r"[\s\-\(\)]", "", phone)
    return bool(re.match(r"^\+?[1-9]\d{7,14}$", cleaned))


# ── Security headers ──────────────────────────────────────────────────────────

def get_security_headers(settings) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": settings.SECURITY_FRAME_OPTIONS,
        "X-XSS-Protection": "0",
        "Referrer-Policy": settings.SECURITY_REFERRER_POLICY,
        "Content-Security-Policy": settings.SECURITY_CSP,
        "Permissions-Policy": settings.SECURITY_PERMISSIONS_POLICY,
        "Cross-Origin-Resource-Policy": "cross-origin",
        "Cross-Origin-Opener-Policy": "same-origin",
    }
    if settings.ENVIRONMENT == "production":
        hsts = f"max-age={settings.SECURITY_HSTS_MAX_AGE}; includeSubDomains"
        if settings.SECURITY_HSTS_PRELOAD:
            hsts += "; preload"
        headers["Strict-Transport-Security"] = hsts
    return headers
