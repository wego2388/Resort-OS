"""
app/core/kernel/auth/service.py
BaseService + AuthService — complete auth logic (login lockout, JWT issuance,
refresh token rotation, 2FA, password reset, token revocation).
"""

import base64
import hashlib
import hmac
import json
import secrets
import string
from io import BytesIO
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyotp
from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.kernel.correlation import get_request_id
from app.core.kernel.security import (
    verify_password, get_password_hash, create_access_token,
    validate_password_strength, validate_email_format,
)
from app.core.kernel.auth.repository import (
    UserRepository,
    delete_refresh_tokens_for_user,
)


# Gate 2B3B — the stable, filterable authentication event codes written into
# the unified AuditLog (entity_type="user_authentication"). This frozenset is
# the single allow-list the self-service security-activity endpoint reads
# back, so an action not listed here is never surfaced to a user. Rejected/
# noisy internal events (step_up_rejected, step_up_issuance_rejected) are
# deliberately absent — they are operator-facing, not personal activity.
AUTH_AUDIT_ACTIONS = frozenset({
    "login_succeeded", "login_failed", "login_locked_out",
    "login_blocked_locked", "login_blocked_inactive",
    "password_changed", "password_reset_requested", "password_reset_completed",
    "two_factor_setup_started", "two_factor_enabled", "two_factor_disabled",
    "two_factor_recovery_code_used", "two_factor_recovery_codes_regenerated",
    "logout", "session_revoked", "all_sessions_revoked", "refresh_token_replayed",
    "step_up_issued", "step_up_consumed",
})


# A real bcrypt hash computed once at import. When an email doesn't exist we
# still run verify_password against this so the failure path takes the same
# ~300ms as a wrong-password path — otherwise the timing gap (email-not-found
# returns in <1ms vs bcrypt-compare ~300ms) leaks which emails are registered.
_DUMMY_PASSWORD_HASH = get_password_hash("timing-equalizer-not-a-real-password")

# Single generic message for every bad-credentials outcome (unknown email OR
# wrong password) — distinct messages are a user-enumeration oracle just like
# the timing gap. Lockout/inactive keep their own messages on purpose: those
# are post-authentication states a legitimate user needs to see.
_GENERIC_AUTH_ERROR = "Incorrect email or password"
_RESET_TOKEN_PREFIX = "reset_"
_SAFE_ENVIRONMENTS = {"development", "test", "testing"}
_RECOVERY_CODE_BYTES = 15  # 120 bits; rendered as 24 base32 characters.
_RECOVERY_CODE_COUNT = 8

# A compromised web super-admin session must never be able to mint another
# super-admin. That role remains CLI-only through app.admin_bootstrap. Public
# customer/guest identities are also intentionally outside staff provisioning.
STAFF_PROVISIONABLE_ROLES = frozenset({
    "admin", "accountant", "hr_manager", "manager", "supervisor",
    "receptionist", "cashier", "waiter", "chef", "kitchen", "employee",
})


class BaseService:
    def __init__(self, db: Session):
        self.db = db
        self.logger = logger

    def _table_exists(self, table: str) -> bool:
        row = self.db.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = :t AND table_schema = 'public'"
            ),
            {"t": table},
        ).fetchone()
        return row is not None


class AuthService(BaseService):
    def __init__(self, db: Session, user_model, settings):
        super().__init__(db)
        self.repo = UserRepository(user_model, db)
        self.settings = settings
        # Gate 2B3B — per-request audit context. Set once by the router
        # dependency (attach_request_context) from the trusted client IP and
        # the request's User-Agent; None on non-HTTP callers (CLI, Celery,
        # tests) which simply record no IP/UA. request_id is read ambiently
        # from the correlation context var, so it needs no threading.
        self._audit_ip: Optional[str] = None
        self._audit_user_agent: Optional[str] = None

    def attach_request_context(self, *, ip: Optional[str], user_agent: Optional[str]) -> "AuthService":
        """Attach trusted request metadata for the unified auth audit. The IP
        must already be the trusted client IP resolved with the app's proxy
        policy (app.core.rate_limit._client_ip) — never a raw
        X-Forwarded-For value."""
        self._audit_ip = ip
        self._audit_user_agent = self._sanitize_user_agent(user_agent)
        return self

    # ── Registration ──────────────────────────────────────────────────────

    def register(self, email: str, password: str, full_name: str, phone: Optional[str] = None):
        if not validate_email_format(email):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid email format")
        if self.repo.get_by_email(email):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")
        valid, msg = validate_password_strength(password)
        if not valid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
        return self.repo.create({
            "email": email,
            "password_hash": get_password_hash(password),
            "full_name": full_name,
            "phone": phone,
        })

    # ── Login (with lockout) ──────────────────────────────────────────────

    def _is_safe_environment(self) -> bool:
        return (
            (getattr(self.settings, "ENVIRONMENT", "") or "").strip().lower()
            in _SAFE_ENVIRONMENTS
        )

    @staticmethod
    def _auth_error(code: str, message: str, *, status_code: int = 401) -> HTTPException:
        return HTTPException(status_code, {"code": code, "message": message})

    @staticmethod
    def _normalize_recovery_code(code: str) -> str:
        return "".join(character for character in (code or "").upper() if character.isalnum())

    @classmethod
    def _recovery_code_hash(cls, code: str) -> str:
        normalized = cls._normalize_recovery_code(code)
        return hashlib.sha256(normalized.encode("ascii", errors="ignore")).hexdigest()

    @staticmethod
    def _new_recovery_code() -> str:
        raw = base64.b32encode(secrets.token_bytes(_RECOVERY_CODE_BYTES)).decode("ascii").rstrip("=")
        return "-".join(raw[index:index + 4] for index in range(0, len(raw), 4))

    def _replace_recovery_codes(self, user_id: int) -> list[str]:
        from app.core.kernel.models.user import TwoFactorRecoveryCode  # noqa: PLC0415

        codes = [self._new_recovery_code() for _ in range(_RECOVERY_CODE_COUNT)]
        self.db.query(TwoFactorRecoveryCode).filter(
            TwoFactorRecoveryCode.user_id == user_id,
        ).delete(synchronize_session=False)
        self.db.add_all([
            TwoFactorRecoveryCode(user_id=user_id, code_hash=self._recovery_code_hash(code))
            for code in codes
        ])
        return codes

    def _consume_recovery_code(self, user_id: int, code: str) -> bool:
        from app.core.kernel.models.user import TwoFactorRecoveryCode  # noqa: PLC0415

        normalized = self._normalize_recovery_code(code)
        if len(normalized) != 24:
            return False
        consumed = self.db.query(TwoFactorRecoveryCode).filter(
            TwoFactorRecoveryCode.user_id == user_id,
            TwoFactorRecoveryCode.code_hash == self._recovery_code_hash(normalized),
        ).delete(synchronize_session=False)
        return consumed == 1

    @staticmethod
    def _matching_totp_step(secret: Optional[str], code: Optional[str]) -> Optional[int]:
        if not secret or not code:
            return None
        totp = pyotp.TOTP(secret)
        now = datetime.now(timezone.utc)
        for offset in (-1, 0, 1):
            candidate_time = now + timedelta(seconds=offset * totp.interval)
            if secrets.compare_digest(totp.at(candidate_time), str(code).strip()):
                return int(totp.timecode(candidate_time))
        return None

    def _consume_totp_code(self, user, code: Optional[str]) -> bool:
        """Accept a valid TOTP counter once, atomically across requests."""
        from sqlalchemy import or_  # noqa: PLC0415

        step = self._matching_totp_step(user.two_factor_secret, code)
        if step is None:
            return False
        consumed = self.db.query(self.repo.model).filter(
            self.repo.model.id == user.id,
            or_(
                self.repo.model.two_factor_last_used_step.is_(None),
                self.repo.model.two_factor_last_used_step < step,
            ),
        ).update(
            {self.repo.model.two_factor_last_used_step: step},
            synchronize_session=False,
        )
        return consumed == 1

    @staticmethod
    def _sanitize_user_agent(user_agent: Optional[str]) -> Optional[str]:
        """Strip control characters and cap length before storing a
        client-supplied User-Agent — it is untrusted, attacker-controlled
        text that must never carry log-injection payloads into AuditLog."""
        if not user_agent:
            return None
        cleaned = "".join(ch for ch in user_agent if ch.isprintable()).strip()
        return cleaned[:255] or None

    def _email_fingerprint(self, email: str) -> str:
        """Non-reversible, domain-separated HMAC of an email — for the
        unknown-account structured log only, so a login sweep is correlatable
        without ever writing a raw address (which would be both a PII leak
        and an enumeration oracle). Keyed with SECRET_KEY so the digest can't
        be precomputed from a wordlist by anyone without the server key."""
        return hmac.new(
            self.settings.SECRET_KEY.encode("utf-8"),
            b"auth-audit-email:" + (email or "").strip().casefold().encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:16]

    def _add_auth_audit(
        self,
        user,
        action: str,
        *,
        details: Optional[dict] = None,
        bounded: bool = False,
    ) -> None:
        """Append a secret-free authentication event to the existing unified
        AuditLog (no parallel audit table — Gate 2B3A's pattern). Records the
        actor, the stable event code, the trusted client IP, a sanitized
        User-Agent, and the correlation request id — never an email in the
        clear, password, TOTP/recovery code, or any token/secret hash.

        ``bounded=True`` gates the *write* behind a per-user/per-action
        rate_limit so a flood of failures (repeated bad-password attempts on
        one known account) cannot grow AuditLog without limit. The bound
        applies only to whether the row is written — the caller's own
        accept/reject decision is completely independent and already made.
        """
        from app.modules.core.models import AuditLog  # noqa: PLC0415

        # Accept either a user object or a bare id — some paths (refresh
        # replay, logout) only carry the id, not a loaded ORM user.
        user_id = user if isinstance(user, int) else user.id

        if bounded:
            from app.core.kernel.cache import rate_limit  # noqa: PLC0415

            if not rate_limit(
                f"auth-audit:{action}:{user_id}", max_requests=20, window_seconds=300,
            ):
                return

        payload = dict(details or {})
        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id
        self.db.add(AuditLog(
            user_id=user_id,
            branch_id=None,
            action=action,
            entity_type="user_authentication",
            entity_id=user_id,
            old_data=None,
            new_data=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ip_address=(self._audit_ip or None),
            user_agent=self._audit_user_agent,
        ))

    def _log_step_up_issuance_rejected(self, user, purpose: str, reason_code: str) -> None:
        """مراجعة Codex المستقلة (2026-07-18، Medium): كانت issue_step_up
        بترفض باسورد/TOTP غلط من غير أي أثر في AuditLog خالص — بعكس
        consume_step_up اللي بتسجّل كل محاولة استهلاك (ناجحة أو مرفوضة).
        دي دورة الإثبات نفسها لمستخدم معروف بالفعل (JWT صالح)، مش تدقيق
        دخول عام لإيميلات مجهولة (ده لسه مؤجَّل لـGate 2B3B عمدًا). بدون
        أي سر (باسورد/TOTP/recovery) — reason_code بس، ومحدودة بنفس
        rate_limit() المستخدمة في الاستهلاك المرفوض، عشان جلسة موثّقة
        خبيثة ميقدرش تضخّم AuditLog بمحاولات فاشلة متكررة عمدًا. يعمل
        commit فوري — الاستدعاء دايمًا قبل `raise` مباشرة، فمفيش commit
        تاني هيحصل بعده في نفس المسار."""
        from app.core.kernel.cache import rate_limit  # noqa: PLC0415

        if not rate_limit(f"stepup-issue-reject-audit:{user.id}", max_requests=20, window_seconds=300):
            return
        self._add_auth_audit(user, "step_up_issuance_rejected", details={
            "purpose": purpose, "reason_code": reason_code,
        })
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def _verify_enrollment_token(self, user, token: Optional[str]) -> None:
        expected_hash = getattr(user, "two_factor_enrollment_token_hash", None)
        expires_at = getattr(user, "two_factor_enrollment_expires_at", None)
        if not expected_hash or not expires_at:
            raise self._auth_error(
                "2FA_ENROLLMENT_NOT_PROVISIONED",
                "Secure enrollment has not been provisioned. Ask an authorized operator to run the bootstrap recovery command.",
                status_code=403,
            )
        if not token:
            raise self._auth_error(
                "2FA_ENROLLMENT_TOKEN_REQUIRED",
                "Enter the one-time enrollment token issued by the authorized operator.",
            )
        if self._as_utc(expires_at) <= datetime.now(timezone.utc):
            raise self._auth_error(
                "2FA_ENROLLMENT_TOKEN_EXPIRED",
                "The enrollment token expired. Ask an authorized operator to issue a replacement.",
                status_code=403,
            )
        supplied_hash = self._hash_token(token.strip())
        if not secrets.compare_digest(expected_hash, supplied_hash):
            raise self._auth_error(
                "2FA_ENROLLMENT_TOKEN_INVALID",
                "The enrollment token is invalid.",
            )

    def _login_requires_enrollment_token(self, user) -> bool:
        # A CLI-created/recovered temporary credential always needs the
        # independent token, including in development.  Legacy seed flags are
        # enforced in every non-safe environment so a copied dev database
        # cannot become a production password-only backdoor.
        if self._bootstrap_proof_required(user):
            return True
        from app.core.deps import MANDATORY_2FA_ROLES  # noqa: PLC0415

        return bool(
            getattr(self.settings, "LOGIN_2FA_ENFORCED", False)
            and user.role in MANDATORY_2FA_ROLES
            and not user.two_factor_enabled
        )

    def _bootstrap_proof_required(self, user) -> bool:
        """Require the out-of-band token for real bootstrap sessions.

        The data migration also marks known demo identities so a copied
        development database fails closed after it reaches staging or
        production. Inside an explicitly safe environment that marker alone
        must not strand an otherwise normal demo account. A temporary
        credential or a still-provisioned enrollment token from the local
        bootstrap command continues to require the independent proof there,
        including after password replacement but before TOTP binding.
        """
        return bool(
            getattr(user, "two_factor_bootstrap_required", False)
            and (
                getattr(user, "must_change_password", False)
                or bool(getattr(user, "two_factor_enrollment_token_hash", None))
                or not self._is_safe_environment()
            )
        )

    def login(
        self,
        email: str,
        password: str,
        otp_code: Optional[str] = None,
        recovery_code: Optional[str] = None,
        enrollment_token: Optional[str] = None,
    ) -> dict:
        max_attempts = getattr(self.settings, "MAX_LOGIN_ATTEMPTS", 5)
        lockout_minutes = getattr(self.settings, "LOCKOUT_MINUTES", 30)

        # trim whitespace — يمنع فشل الـ login بسبب space زيادة من autofill أو paste
        email = email.strip()
        password = password.strip()

        user = self.repo.get_by_email(email)
        if not user:
            # Equalize timing with the wrong-password path (bcrypt ~300ms) and
            # return the exact same message — no user-enumeration oracle.
            verify_password(password, _DUMMY_PASSWORD_HASH)
            # Gate 2B3B — an unknown account writes NO AuditLog row on purpose:
            # a database row per anonymous bot attempt is exactly the PII/write
            # amplification this gate must avoid. A single structured log line
            # with a keyed, non-reversible email fingerprint keeps the attempt
            # correlatable for operators without persisting a raw address.
            logger.warning(
                "login attempt for unknown account fp={} ip={}",
                self._email_fingerprint(email), self._audit_ip or "-",
            )
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC_AUTH_ERROR)

        if user.account_locked_until:
            locked_until = user.account_locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until > datetime.now(timezone.utc):
                remaining = int((locked_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
                self._add_auth_audit(user, "login_blocked_locked", bounded=True)
                self.db.commit()
                raise HTTPException(
                    status.HTTP_423_LOCKED,
                    f"Account locked after too many failed attempts. Try again in {remaining} minutes.",
                )
            user.account_locked_until = None
            user.failed_login_attempts = 0
            self.db.commit()

        if not user.is_active:
            self._add_auth_audit(user, "login_blocked_inactive", bounded=True)
            self.db.commit()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Inactive account")

        if not verify_password(password, user.password_hash):
            attempts = (user.failed_login_attempts or 0) + 1
            user.failed_login_attempts = attempts
            if attempts >= max_attempts:
                user.account_locked_until = datetime.now(timezone.utc) + timedelta(minutes=lockout_minutes)
                # Lockout is a bounded, once-per-lockout-window event — logged
                # unbounded (there can be at most one per max_attempts failures).
                self._add_auth_audit(user, "login_locked_out")
                self.db.commit()
                raise HTTPException(
                    status.HTTP_423_LOCKED,
                    f"Account locked after {max_attempts} failed attempts. Try again in {lockout_minutes} minutes.",
                )
            self._add_auth_audit(user, "login_failed", bounded=True)
            self.db.commit()
            # No "N attempts remaining" — that both confirms the email exists and
            # hands the attacker the lockout threshold. Same message as unknown email.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, _GENERIC_AUTH_ERROR)

        if self._login_requires_enrollment_token(user):
            self._verify_enrollment_token(user, enrollment_token)

        # ── Second factor (TOTP) ──────────────────────────────────────────
        # Password alone is not enough for a 2FA-enabled account: verify the
        # TOTP code here so 2FA is a real login-time second factor, not just an
        # enrollment flag. Gated by LOGIN_2FA_ENFORCED so it can be switched on
        # in lockstep with the frontend collecting the code (default off keeps
        # the current password-only client working).
        recovery_code_used = False
        if getattr(self.settings, "LOGIN_2FA_ENFORCED", False) and user.two_factor_enabled:
            if not otp_code and not recovery_code:
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED,
                    {"code": "2FA_CODE_REQUIRED", "message": "التحقق بخطوتين مطلوب — أدخل الرمز"},
                )
            valid_totp = self._consume_totp_code(user, otp_code)
            if recovery_code and not otp_code:
                recovery_code_used = self._consume_recovery_code(user.id, recovery_code)
            if not valid_totp and not recovery_code_used:
                self._add_auth_audit(
                    user, "login_failed", details={"factor": "2fa"}, bounded=True,
                )
                self.db.commit()
                raise HTTPException(
                    status.HTTP_401_UNAUTHORIZED,
                    {"code": "2FA_CODE_INVALID", "message": "رمز التحقق بخطوتين غير صحيح"},
                )

        if user.failed_login_attempts:
            user.failed_login_attempts = 0
            user.account_locked_until = None

        token = create_access_token(
            data={"sub": user.email},
            secret_key=self.settings.SECRET_KEY,
            algorithm=self.settings.ALGORITHM,
            expires_delta=timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        if recovery_code_used:
            self._add_auth_audit(user, "two_factor_recovery_code_used")
        self._add_auth_audit(user, "login_succeeded", details={
            "assurance": "2fa" if user.two_factor_enabled else "password",
        })
        self.db.commit()
        return {
            "access_token": token,
            "token_type": "bearer",
            "_user": user,
            # Bootstrap/restricted sessions are deliberately access-token
            # only.  A browser cannot silently extend a temporary credential
            # for seven days through the refresh cookie.
            "_allow_refresh": self._refresh_allowed_for_user(user),
        }

    @staticmethod
    def _require_active_user(user) -> None:
        if (
            not user
            or not getattr(user, "is_active", False)
            or getattr(user, "deleted_at", None) is not None
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Inactive account")

    @staticmethod
    def _revoke_access_tokens(user_id: int) -> None:
        # Local import keeps the owned kernel auth package usable without a
        # module-level dependency cycle through app.core.deps.
        from app.core.deps import revoke_user_tokens  # noqa: PLC0415

        revoke_user_tokens(user_id)

    def change_password(
        self,
        user,
        current_password: str,
        new_password: str,
        enrollment_token: Optional[str] = None,
    ) -> bool:
        """Change the current user's password and terminate every session.

        Every role follows the same current-password verification rule. The
        old admin/super_admin exemption turned a stolen 15-minute access token
        into a permanent account takeover. Refresh-token deletion is part of
        the password transaction; the access-token cutoff is published only
        after that transaction succeeds.
        """
        self._require_active_user(user)
        if self._bootstrap_proof_required(user):
            self._verify_enrollment_token(user, enrollment_token)
        valid, msg = validate_password_strength(new_password)
        if not valid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
        if verify_password(new_password, user.password_hash):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "New password must be different from the current password",
            )

        user.password_hash = get_password_hash(new_password)
        user.must_change_password = False
        from app.core.deps import MANDATORY_2FA_ROLES  # noqa: PLC0415

        # Optional-role seed/recovery accounts finish bootstrap when their
        # password is rotated. Mandatory roles keep the token until a TOTP
        # factor is bound successfully.
        if user.role not in MANDATORY_2FA_ROLES:
            user.two_factor_bootstrap_required = False
            user.two_factor_enrollment_token_hash = None
            user.two_factor_enrollment_expires_at = None
        delete_refresh_tokens_for_user(self.db, user.id)
        self._add_auth_audit(user, "password_changed")
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self._revoke_access_tokens(user.id)
        return True

    def update_user(self, user_id: int, data: dict, actor) -> object:
        """Gate 2A (2026-07-18): role/is_active mutations are refused
        unconditionally here, not gated by actor.role like the old code did.
        This generic repo.update() path bypasses every super_admin invariant
        in app.modules.core.services.update_user_role() — no row locking
        (ordered or otherwise), no self-lockout check, no last-active-
        super-admin check, and no AuditLog entry, just a bare
        revoke_user_tokens() call. No confirmed caller exists in this
        codebase today (grep found none), but the reason to keep it
        fail-closed is exactly that: an unreachable path that silently does
        the wrong thing is a backdoor waiting for its first caller, not a
        safe no-op. Any client that needs to change role/is_active must go
        through PATCH /users/{id}/role, which enforces those invariants."""
        user = self.repo.get(user_id)
        if not user:
            raise HTTPException(404, "User not found")
        if "role" in data or "is_active" in data:
            raise HTTPException(
                403,
                {
                    "error_code": "USE_SUPER_ADMIN_CONTROL_PLANE",
                    "message": (
                        "Changing role or is_active through this path is not allowed. "
                        "Use PATCH /users/{id}/role, which enforces the super_admin "
                        "safeguards (Gate 2A)."
                    ),
                },
            )
        if "password" in data and data["password"]:
            data["password_hash"] = get_password_hash(data.pop("password"))
        return self.repo.update(user_id, data)

    # ── Refresh tokens ────────────────────────────────────────────────────

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create_refresh_token(self, user_id: int, device_fingerprint: Optional[str] = None) -> str:
        """Start a brand-new refresh-token *family* for one login (Gate 2B3B).

        A fresh, random ``family_id`` (never derived from ``user_id``) and a
        separate public handle are minted here; every later rotation stays
        inside the same family so a replay can be traced to, and revoke, the
        whole lineage.
        """
        from app.core.kernel.models.user import RefreshToken
        user = self.repo.get(user_id)
        self._require_active_user(user)
        if not self._refresh_allowed_for_user(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Account onboarding is not complete")
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS)
        self.db.add(RefreshToken(
            user_id=user_id,
            token_hash=self._hash_token(token),
            device_fingerprint=device_fingerprint,
            expires_at=expires_at,
            created_at=now,
            family_id=secrets.token_hex(16),
            # 128-bit public reference. It is not a bearer secret, but the
            # larger space makes an accidental collision between two session
            # families operationally negligible without exposing family_id.
            family_public_id=secrets.token_hex(16),
            family_started_at=now,
            user_agent=self._audit_user_agent,
        ))
        self.db.commit()
        return token

    # ── Refresh-token family helpers (Gate 2B3B) ─────────────────────────

    def _revoke_family(self, user_id: int, family_id: str) -> int:
        """Atomically mark every still-live row of one family revoked. Does
        NOT commit — the caller owns the transaction so the revocation and any
        accompanying audit/access cutoff land together. Follows the same
        conditional-UPDATE pattern as refresh rotation and step-up consumption
        (the ``revoked_at IS NULL`` guard makes a double-revoke a safe no-op)."""
        from app.core.kernel.models.user import RefreshToken  # noqa: PLC0415

        return (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.user_id == user_id,
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .update({RefreshToken.revoked_at: datetime.now(timezone.utc)}, synchronize_session=False)
        )

    def _handle_replay(self, refresh_token) -> None:
        """A consumed token was presented again — provable replay. Revoke the
        whole family AND publish a global access-token cutoff (a detected token
        theft warrants killing every access token immediately, unlike a routine
        self-service session revoke). Secret-free audit; never the token."""
        self._revoke_family(refresh_token.user_id, refresh_token.family_id)
        logger.warning(
            "refresh-token replay detected for user {} (family revoked)",
            refresh_token.user_id,
        )
        self._add_auth_audit(
            refresh_token.user_id,
            "refresh_token_replayed",
            details={"session_ref": refresh_token.family_public_id, "reason": "reuse_detected"},
        )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self._revoke_access_tokens(refresh_token.user_id)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _refresh_allowed_for_user(self, user) -> bool:
        if (
            getattr(user, "must_change_password", False)
            or self._bootstrap_proof_required(user)
        ):
            return False
        if getattr(self.settings, "LOGIN_2FA_ENFORCED", False):
            from app.core.deps import MANDATORY_2FA_ROLES  # noqa: PLC0415

            if user.role in MANDATORY_2FA_ROLES and not user.two_factor_enabled:
                return False
        return True

    def _refresh_token_predates_revocation(self, refresh_token) -> bool:
        """Honor the existing access-token cutoff for legacy refresh rows.

        Gate 2A published a cache cutoff on role/status changes but did not
        delete the corresponding database refresh rows. New Gate 2B writes do
        both; this check safely retires any legacy rows still present.
        """
        from app.core.deps import REVOKED_CACHE_PREFIX  # noqa: PLC0415
        from app.core.kernel.cache import get_cache  # noqa: PLC0415

        revoked_at = get_cache(f"{REVOKED_CACHE_PREFIX}:{refresh_token.user_id}")
        if not revoked_at or not refresh_token.created_at:
            return False
        created_at = self._as_utc(refresh_token.created_at).timestamp()
        return created_at < float(revoked_at)

    def verify_refresh_token(self, token: str, device_fingerprint: Optional[str] = None):
        from app.core.kernel.models.user import RefreshToken
        rt = (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.token_hash == self._hash_token(token),
                RefreshToken.consumed_at.is_(None),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
            .first()
        )
        if not rt:
            return None
        if device_fingerprint and rt.device_fingerprint != device_fingerprint:
            logger.warning("Device fingerprint mismatch for user {}", rt.user_id)
            return None
        user = self.repo.get(rt.user_id)
        if (
            not user
            or not user.is_active
            or getattr(user, "deleted_at", None) is not None
            or not self._refresh_allowed_for_user(user)
            or self._refresh_token_predates_revocation(rt)
        ):
            return None
        return user

    def rotate_refresh_token(self, old_token: str, device_fingerprint: Optional[str] = None) -> Optional[tuple]:
        """Consume one refresh token and issue its successor in the same
        family — atomically, with replay detection (Gate 2B3B).

        Rotation no longer hard-deletes the old row; it stamps ``consumed_at``
        (a tombstone) via a conditional UPDATE that is the concurrency
        boundary: two requests may both read the row unconsumed, but only one
        UPDATE can flip ``consumed_at`` from NULL, so only one successor is
        ever minted. Presenting an already-tombstoned token again is a
        *provable* replay → the whole family is revoked and access tokens are
        cut off. A concurrent-race loser (it read the row unconsumed but lost
        the UPDATE) is rejected generically WITHOUT revoking the family — it
        never observed a tombstone, so it is a benign double-submit, not a
        provable replay (see slice B design).
        """
        from app.core.kernel.models.user import RefreshToken
        if not old_token:
            return None
        token_hash = self._hash_token(old_token)
        now = datetime.now(timezone.utc)
        initial_rt = (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .first()
        )
        if not initial_rt:
            # Unknown token — no tombstone proves prior consumption, so this is
            # a plain invalid token, not a provable replay. Generic reject.
            return None

        # A stable per-user row lock serializes refresh rotation, replay
        # handling, logout and self-service family revocation. The old
        # token-row-only boundary prevented double minting, but could not
        # guarantee that a family-wide revoke saw a successor inserted by a
        # concurrent transaction after the UPDATE statement's snapshot.
        user = self._lock_user_for_update(initial_rt.user_id)
        rt = (
            self.db.query(RefreshToken)
            .filter(RefreshToken.token_hash == token_hash)
            .populate_existing()
            .first()
        )
        if rt is None:
            self.db.rollback()
            return None

        # ── Provable replay: a consumed token presented again ──
        if rt.consumed_at is not None:
            self._handle_replay(rt)
            return None

        # Already-revoked family (sibling replay, explicit revoke, credential
        # change) or expired → generic reject; never revive.
        if rt.revoked_at is not None or self._as_utc(rt.expires_at) <= now:
            return None

        if device_fingerprint and rt.device_fingerprint != device_fingerprint:
            logger.warning("Device fingerprint mismatch for user {}", rt.user_id)
            return None

        # Capture family lineage into locals BEFORE any UPDATE/expunge — never
        # read attributes off an ORM row after a bulk UPDATE/commit (the
        # ObjectDeletedError class of bug found in Gate 2B3A).
        rt_id = rt.id
        family_id = rt.family_id
        family_public_id = rt.family_public_id
        family_started_at = rt.family_started_at or rt.created_at
        rt_user_agent = rt.user_agent
        user_id = rt.user_id

        if (
            not user
            or not user.is_active
            or getattr(user, "deleted_at", None) is not None
            or not self._refresh_allowed_for_user(user)
            or self._refresh_token_predates_revocation(rt)
        ):
            # A now-ineligible account: retire the whole family rather than
            # leaving live rows behind.
            self._revoke_family(user_id, family_id)
            self.db.commit()
            return None

        new_token = secrets.token_urlsafe(32)
        new_token_hash = self._hash_token(new_token)

        # Atomic consume. The WHERE clause re-checks consumed/revoked/expiry so
        # a session-revoke or a sibling rotation racing this one cannot be
        # revived: only one caller flips consumed_at from NULL.
        consumed = (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.id == rt_id,
                RefreshToken.consumed_at.is_(None),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .update(
                {
                    RefreshToken.consumed_at: now,
                    RefreshToken.successor_token_hash: new_token_hash,
                },
                synchronize_session=False,
            )
        )
        if consumed != 1:
            # Lost the race (or revoked/expired between SELECT and UPDATE) —
            # generic reject, no family revocation (no tombstone was observed).
            self.db.rollback()
            return None

        # Bulk UPDATE bypasses ORM synchronization; drop the stale instance
        # from the identity map before adding the successor.
        self.db.expunge(rt)
        self.db.add(RefreshToken(
            user_id=user.id,
            token_hash=new_token_hash,
            device_fingerprint=device_fingerprint,
            expires_at=now + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS),
            created_at=now,
            family_id=family_id,
            family_public_id=family_public_id,
            family_started_at=family_started_at,
            user_agent=self._audit_user_agent or rt_user_agent,
        ))
        # Bounded cleanup: only this user's own expired rows (never a global
        # sweep) — keeps tombstones alive for replay detection until natural
        # expiry, then reaps them off the hot path.
        self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user.id,
            RefreshToken.expires_at <= now,
        ).delete(synchronize_session=False)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return user, new_token

    # ── Self-service session management (Gate 2B3B) ──────────────────────

    def current_session(
        self,
        refresh_token: Optional[str],
        *,
        expected_user_id: Optional[int] = None,
    ) -> Optional[tuple[str, str]]:
        """Resolve (family_id, family_public_id) of the live session that
        presented this refresh token, or None. Used only to flag the caller's
        own 'current' session and to protect 'revoke others'."""
        from app.core.kernel.models.user import RefreshToken  # noqa: PLC0415

        if not refresh_token:
            return None
        query = self.db.query(RefreshToken).filter(
                RefreshToken.token_hash == self._hash_token(refresh_token),
                RefreshToken.consumed_at.is_(None),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        if expected_user_id is not None:
            query = query.filter(RefreshToken.user_id == expected_user_id)
        rt = query.first()
        return (rt.family_id, rt.family_public_id) if rt else None

    def list_active_sessions(self, user_id: int, *, current_family_id: Optional[str] = None) -> list[dict]:
        """Return the user's live refresh families as non-secret DTO dicts —
        one row per family (the live successor). Never exposes token_hash,
        successor_token_hash, or the internal family_id."""
        from app.core.kernel.models.user import RefreshToken  # noqa: PLC0415

        now = datetime.now(timezone.utc)
        rows = (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.user_id == user_id,
                RefreshToken.consumed_at.is_(None),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .order_by(RefreshToken.created_at.desc(), RefreshToken.id.desc())
            .all()
        )
        return [
            {
                "session_ref": r.family_public_id,
                "started_at": self._as_utc(r.family_started_at or r.created_at),
                "last_active_at": self._as_utc(r.created_at),
                "expires_at": self._as_utc(r.expires_at),
                "device": r.user_agent,
                "current": bool(current_family_id and r.family_id == current_family_id),
            }
            for r in rows
        ]

    def revoke_session_by_ref(self, user_id: int, session_ref: str) -> bool:
        """Revoke one refresh family the caller owns, by its public reference.
        Returns True if a live family was revoked, False if none matched
        (unknown ref, another user's ref, or already revoked) — the endpoint
        maps False to 404 so a user cannot probe another user's session refs.

        Deliberately does NOT publish a global access-token cutoff: that is a
        user-wide switch that would also kill the caller's *current* access
        token. Killing the target family stops its refresh, so that session
        ends within one access-token TTL; the caller's session is untouched.
        (A detected replay is different — that path cuts access immediately.)"""
        from app.core.kernel.models.user import RefreshToken  # noqa: PLC0415

        self._lock_user_for_update(user_id)
        now = datetime.now(timezone.utc)
        live = self.db.query(RefreshToken.family_id).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.family_public_id == session_ref,
            RefreshToken.consumed_at.is_(None),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        ).first()
        affected = self._revoke_family(user_id, live[0]) if live else 0
        if affected == 0:
            self.db.rollback()
            return False
        self._add_auth_audit(user_id, "session_revoked", details={"session_ref": session_ref})
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return True

    def revoke_other_sessions(self, user_id: int, *, keep_family_id: Optional[str]) -> int:
        """Revoke every refresh family the caller owns except the current one.
        Returns the number of families revoked. Same surgical, no-global-cutoff
        policy as revoke_session_by_ref — the kept current session stays live."""
        from app.core.kernel.models.user import RefreshToken  # noqa: PLC0415

        self._lock_user_for_update(user_id)
        now = datetime.now(timezone.utc)
        family_query = self.db.query(RefreshToken.family_id).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.consumed_at.is_(None),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
        if keep_family_id is not None:
            family_query = family_query.filter(RefreshToken.family_id != keep_family_id)
        family_ids = [row[0] for row in family_query.distinct().all()]
        if family_ids:
            self.db.query(RefreshToken).filter(
                RefreshToken.user_id == user_id,
                RefreshToken.family_id.in_(family_ids),
                RefreshToken.revoked_at.is_(None),
            ).update({RefreshToken.revoked_at: now}, synchronize_session=False)
        affected = len(family_ids)
        self._add_auth_audit(
            user_id, "all_sessions_revoked",
            details={"revoked_count": affected, "kept_current": keep_family_id is not None},
        )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return affected

    def list_security_activity(self, user_id: int, *, limit: int, offset: int) -> tuple[list, int]:
        """Paginated, allow-listed view of the caller's OWN authentication
        audit events. Only actions in AUTH_AUDIT_ACTIONS are surfaced, and
        only rows owned by this user — never another user's, never the raw
        audit payload beyond the whitelisted fields the endpoint returns."""
        from app.modules.core.models import AuditLog  # noqa: PLC0415

        base = self.db.query(AuditLog).filter(
            AuditLog.user_id == user_id,
            AuditLog.entity_type == "user_authentication",
            AuditLog.action.in_(AUTH_AUDIT_ACTIONS),
        )
        total = base.count()
        rows = (
            base.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return rows, total

    # ── 2FA ───────────────────────────────────────────────────────────────

    def _lock_user_for_update(self, user_id: int):
        return (
            self.db.query(self.repo.model)
            .filter(self.repo.model.id == user_id)
            .with_for_update()
            .populate_existing()
            .one()
        )

    def setup_2fa(
        self,
        user,
        *,
        current_password: Optional[str] = None,
        enrollment_token: Optional[str] = None,
    ) -> dict:
        self._require_active_user(user)
        if user.two_factor_enabled:
            raise HTTPException(400, "2FA already enabled")
        if getattr(user, "must_change_password", False):
            raise self._auth_error(
                "PASSWORD_CHANGE_REQUIRED",
                "Replace the temporary password before enrolling two-factor authentication.",
                status_code=409,
            )

        if self._bootstrap_proof_required(user):
            self._verify_enrollment_token(user, enrollment_token)
        elif not current_password or not verify_password(current_password, user.password_hash):
            raise self._auth_error(
                "CURRENT_PASSWORD_REQUIRED",
                "Enter the current password before binding a new authenticator.",
                status_code=403,
            )

        # Preserve an in-progress enrollment secret across retry/reload. A
        # fresh secret on every setup request invalidates the QR the user may
        # already be scanning on another device.
        secret = user.two_factor_secret or pyotp.random_base32()
        if not user.two_factor_secret:
            user.two_factor_secret = secret
            self._add_auth_audit(user, "two_factor_setup_started")
            self.db.commit()
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=getattr(self.settings, "APP_NAME", "Resort OS"),
        )
        # Never send an otpauth URI to a third-party QR service. The previous
        # api.qrserver.com image URL disclosed the permanent TOTP seed to that
        # provider as soon as the browser rendered it. qrcode[pil] is already
        # a pinned project dependency, so generate a self-contained PNG.
        import qrcode  # noqa: PLC0415

        image = qrcode.make(uri)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        qr_data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        return {
            "secret": secret,
            "provisioning_uri": uri,
            "qr_url": qr_data_url,
        }

    def enable_2fa(
        self,
        user,
        code: str,
        *,
        enrollment_token: Optional[str] = None,
    ) -> dict:
        self._require_active_user(user)
        locked_user = self._lock_user_for_update(user.id)
        if locked_user.two_factor_enabled:
            raise HTTPException(400, "2FA already enabled")
        if not locked_user.two_factor_secret:
            raise HTTPException(400, "Setup 2FA first")
        if self._bootstrap_proof_required(locked_user):
            self._verify_enrollment_token(locked_user, enrollment_token)
        if not self._consume_totp_code(locked_user, code):
            raise HTTPException(400, "Invalid 2FA code")
        recovery_codes = self._replace_recovery_codes(locked_user.id)
        locked_user.two_factor_enabled = True
        locked_user.two_factor_bootstrap_required = False
        locked_user.two_factor_enrollment_token_hash = None
        locked_user.two_factor_enrollment_expires_at = None
        delete_refresh_tokens_for_user(self.db, locked_user.id)
        self._add_auth_audit(
            locked_user,
            "two_factor_enabled",
            details={"recovery_code_count": len(recovery_codes)},
        )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self._revoke_access_tokens(locked_user.id)
        return {
            "recovery_codes": recovery_codes,
            "reauthentication_required": True,
        }

    def disable_2fa(self, user, code: str, *, current_password: str) -> bool:
        self._require_active_user(user)
        if not user.two_factor_enabled:
            raise HTTPException(400, "2FA not enabled")
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(400, "Current password is incorrect")
        if not self._consume_totp_code(user, code):
            raise HTTPException(400, "Invalid 2FA code")
        # app.core.deps.get_current_active_user blocks *access* for
        # MANDATORY_2FA_ROLES (super_admin/accountant) while 2FA is off, but
        # nothing stopped one of those users from turning it back off right
        # here — this endpoint had no idea the role-level mandate existed.
        # Local import: kernel/ must stay importable standalone (no hard
        # dependency on app.core.deps at module load time).
        from app.core.deps import MANDATORY_2FA_ROLES  # noqa: PLC0415
        if getattr(user, "role", None) in MANDATORY_2FA_ROLES:
            raise HTTPException(400, "التحقق بخطوتين إجباري لهذا الدور — لا يمكن تعطيله")
        user.two_factor_enabled = False
        user.two_factor_secret = None
        user.two_factor_last_used_step = None
        from app.core.kernel.models.user import TwoFactorRecoveryCode  # noqa: PLC0415

        self.db.query(TwoFactorRecoveryCode).filter(
            TwoFactorRecoveryCode.user_id == user.id,
        ).delete(synchronize_session=False)
        delete_refresh_tokens_for_user(self.db, user.id)
        self._add_auth_audit(user, "two_factor_disabled")
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self._revoke_access_tokens(user.id)
        return True

    def regenerate_recovery_codes(
        self,
        user,
        *,
        current_password: str,
        code: str,
    ) -> dict:
        self._require_active_user(user)
        locked_user = self._lock_user_for_update(user.id)
        if not locked_user.two_factor_enabled or not locked_user.two_factor_secret:
            raise HTTPException(400, "2FA not enabled")
        if not verify_password(current_password, locked_user.password_hash):
            raise HTTPException(400, "Current password is incorrect")
        if not self._consume_totp_code(locked_user, code):
            raise HTTPException(400, "Invalid 2FA code")

        recovery_codes = self._replace_recovery_codes(locked_user.id)
        delete_refresh_tokens_for_user(self.db, locked_user.id)
        self._add_auth_audit(
            locked_user,
            "two_factor_recovery_codes_regenerated",
            details={"recovery_code_count": len(recovery_codes)},
        )
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self._revoke_access_tokens(locked_user.id)
        return {
            "recovery_codes": recovery_codes,
            "reauthentication_required": True,
        }

    # ── Step-up grants (Gate 2B3A) ──────────────────────────────────────
    # A DB-backed, hashed, one-time proof of recent reauthentication for one
    # exact operation. See app.core.kernel.auth.step_up for the scope-hash
    # contract shared between issuance (here) and every consuming endpoint.

    def issue_step_up(
        self,
        user,
        *,
        current_password: str,
        purpose: str,
        scope_hash: str,
        access_token_hash: str,
        totp_code: Optional[str] = None,
        recovery_code: Optional[str] = None,
    ) -> dict:
        """Verify identity fresh, then issue a single-use grant for exactly
        one hashed operation scope.

        Every role must re-prove its current password — there is no
        password-only shortcut that skips this. A mandatory-2FA role
        (super_admin/accountant) can never fall back to password-only: if
        it somehow reaches this method without two_factor_enabled, that is
        refused outright rather than silently downgrading assurance (in
        practice get_current_active_user already blocks such an account
        from every non-/auth/* route, so this is defense in depth, not the
        primary gate). An account with 2FA enabled must present exactly one
        of a fresh TOTP code or one recovery code — never both, and never
        neither.
        """
        from app.core.deps import MANDATORY_2FA_ROLES  # noqa: PLC0415

        self._require_active_user(user)
        if not verify_password(current_password, user.password_hash):
            self._log_step_up_issuance_rejected(user, purpose, "CURRENT_PASSWORD_REQUIRED")
            raise self._auth_error(
                "CURRENT_PASSWORD_REQUIRED",
                "Enter the current password to confirm this action.",
                status_code=403,
            )
        if totp_code and recovery_code:
            self._log_step_up_issuance_rejected(user, purpose, "STEP_UP_PROOF_AMBIGUOUS")
            raise self._auth_error(
                "STEP_UP_PROOF_AMBIGUOUS",
                "Provide either an authenticator code or a recovery code, not both.",
                status_code=400,
            )

        mandatory_role = user.role in MANDATORY_2FA_ROLES
        if user.two_factor_enabled:
            if not totp_code and not recovery_code:
                self._log_step_up_issuance_rejected(user, purpose, "2FA_CODE_REQUIRED")
                raise self._auth_error(
                    "2FA_CODE_REQUIRED",
                    "التحقق بخطوتين مطلوب — أدخل الرمز أو كود استرداد",
                )
            recovery_used = False
            valid_totp = False
            if totp_code:
                valid_totp = self._consume_totp_code(user, totp_code)
            elif recovery_code:
                recovery_used = self._consume_recovery_code(user.id, recovery_code)
            if not valid_totp and not recovery_used:
                self._log_step_up_issuance_rejected(user, purpose, "2FA_CODE_INVALID")
                raise self._auth_error(
                    "2FA_CODE_INVALID",
                    "رمز التحقق بخطوتين غير صحيح",
                )
            assurance_method = "recovery_code" if recovery_used else "totp"
        else:
            if mandatory_role:
                # Not reachable through the normal HTTP chain (see docstring
                # above) — kept as an explicit, fail-closed statement rather
                # than an implicit password-only fallback for this role.
                self._log_step_up_issuance_rejected(user, purpose, "MANDATORY_2FA_REQUIRED")
                raise self._auth_error(
                    "MANDATORY_2FA_REQUIRED",
                    "This role requires two-factor authentication before confirming sensitive actions.",
                    status_code=403,
                )
            assurance_method = "password_only"

        from app.core.kernel.models.user import StepUpGrant  # noqa: PLC0415

        now = datetime.now(timezone.utc)
        token = secrets.token_urlsafe(32)
        public_reference = secrets.token_hex(8)
        expires_at = now + timedelta(seconds=self.settings.STEP_UP_TOKEN_TTL_SECONDS)

        # Bounded cleanup: only this user's own expired grants, not a global
        # sweep — cheap, and avoids lock contention with unrelated users.
        self.db.query(StepUpGrant).filter(
            StepUpGrant.user_id == user.id,
            StepUpGrant.expires_at <= now,
        ).delete(synchronize_session=False)

        self.db.add(StepUpGrant(
            public_reference=public_reference,
            user_id=user.id,
            purpose=purpose,
            scope_hash=scope_hash,
            token_hash=self._hash_token(token),
            access_token_hash=access_token_hash,
            assurance_method=assurance_method,
            expires_at=expires_at,
        ))
        self._add_auth_audit(user, "step_up_issued", details={
            "purpose": purpose,
            "assurance_method": assurance_method,
            "public_reference": public_reference,
        })
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {
            "step_up_token": token,
            "public_reference": public_reference,
            "expires_at": expires_at,
            "assurance_method": assurance_method,
        }

    def consume_step_up(
        self,
        *,
        user_id: int,
        purpose: str,
        scope_hash: str,
        access_token_hash: str,
        token: Optional[str],
    ) -> Optional[dict]:
        """Atomically consume exactly one grant matching every binding
        dimension at once (user, purpose, scope, session, not expired).
        Returns the grant's non-secret metadata (for the caller's audit
        entry) on success, or ``None`` on any failure.

        A single conditional DELETE is the concurrency boundary — two
        concurrent requests presenting the same token can both attempt this
        delete, but only one can affect a row; the other observes a
        zero-row-count and is rejected. The preceding SELECT below is only
        to read the metadata of *our own* row before deleting it — it does
        not weaken the atomicity guarantee, since "did our own DELETE
        affect exactly one row" is the only thing that decides success, not
        whether a matching row was visible a moment earlier. It is also,
        deliberately, the only source of "why did this fail" information:
        user/purpose/scope/session/expiry mismatches all produce the same
        zero-row outcome, so the caller cannot distinguish them
        (STEP_UP_INVALID is intentionally generic — see the consuming
        router endpoints).

        This method commits its own transaction immediately. It is a
        separate commit from whatever business mutation the caller performs
        next on the same session — not one atomic transaction spanning both
        (the existing services already commit internally, so there is no
        clean way to nest this inside their transaction without a broader
        refactor out of scope for Gate 2B3A). If the business mutation
        fails afterward, the grant is already gone; the UI must request a
        fresh step-up rather than silently retrying with a token that is
        now guaranteed to fail.
        """
        if not token:
            return None
        token_hash = self._hash_token(token)
        now = datetime.now(timezone.utc)

        from app.core.kernel.models.user import StepUpGrant  # noqa: PLC0415

        match = (
            StepUpGrant.token_hash == token_hash,
            StepUpGrant.user_id == user_id,
            StepUpGrant.purpose == purpose,
            StepUpGrant.scope_hash == scope_hash,
            StepUpGrant.access_token_hash == access_token_hash,
            StepUpGrant.expires_at > now,
        )
        candidate = self.db.query(StepUpGrant).filter(*match).first()
        # اقرأ الحقول المطلوبة للـaudit *قبل* الـcommit تحت — commit
        # بيمسح (expire) كل objects الـsession بالافتراضي، والصف بقى محذوف
        # فعليًا وقت الـDELETE تحت، فأي وصول لـcandidate.<attr> بعد الـcommit
        # كان بيطلع ObjectDeletedError (باج حقيقي اتكشف واتصلح هنا).
        candidate_public_reference = candidate.public_reference if candidate else None
        candidate_assurance_method = candidate.assurance_method if candidate else None
        consumed = self.db.query(StepUpGrant).filter(*match).delete(synchronize_session=False)

        if consumed == 1:
            # Bounded cleanup of this user's other expired grants only on
            # the success path — same reasoning as issue_step_up, and kept
            # out of the rejection path so a replay/mismatch attempt cannot
            # be used to quietly sweep away unrelated still-valid grants.
            self.db.query(StepUpGrant).filter(
                StepUpGrant.user_id == user_id,
                StepUpGrant.expires_at <= now,
            ).delete(synchronize_session=False)
        else:
            self.db.rollback()

        from app.modules.core.models import AuditLog  # noqa: PLC0415

        # مراجعة Codex المستقلة (2026-07-18، Medium): نجاح الاستهلاك بيتسجّل
        # دايمًا (حدث واحد لكل proof، محدود بطبيعته — proof وحيد الاستخدام).
        # الرفض (توكن مفقود/منتهي/مُعاد استخدامه/غلط) كان بيتسجّل بلا حد —
        # جلسة موثّقة (super_admin/admin) خبيثة تقدر تضخّم AuditLog بتكرار
        # محاولات استهلاك وهمية على أي من الأربعة endpoints المحمية (مفيش
        # rate limit على دي، بعكس POST /auth/step-up نفسها). rate_limit()
        # هنا بيحد عدد صفوف step_up_rejected لكل مستخدم خلال نافذة زمنية —
        # الرفض الفعلي للطلب (STEP_UP_INVALID) بيفضل يحصل دايمًا، بس السجل
        # بس اللي بيتحد. مش تدقيق دخول عام مجهول (ده لسه Gate 2B3B).
        should_log = consumed == 1
        if not should_log:
            from app.core.kernel.cache import rate_limit  # noqa: PLC0415
            should_log = rate_limit(f"stepup-reject-audit:{user_id}", max_requests=20, window_seconds=300)

        if should_log:
            self.db.add(AuditLog(
                user_id=user_id,
                branch_id=None,
                action="step_up_consumed" if consumed == 1 else "step_up_rejected",
                entity_type="user_authentication",
                entity_id=user_id,
                old_data=None,
                new_data=json.dumps({"purpose": purpose}, ensure_ascii=False, sort_keys=True),
            ))
        self.db.commit()
        if consumed == 1 and candidate_public_reference is not None:
            return {
                "public_reference": candidate_public_reference,
                "assurance_method": candidate_assurance_method,
            }
        return None

    # ── Out-of-band privileged bootstrap ────────────────────────────────

    @staticmethod
    def _new_temporary_password(length: int = 24) -> str:
        """Generate a password that always satisfies validate_password_strength."""
        special = "!@#$%^&*"
        characters = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.digits),
            secrets.choice(special),
        ]
        alphabet = string.ascii_letters + string.digits + special
        characters.extend(secrets.choice(alphabet) for _ in range(length - len(characters)))
        secrets.SystemRandom().shuffle(characters)
        return "".join(characters)

    def provision_account_bootstrap(
        self,
        *,
        email: str,
        full_name: Optional[str],
        create: bool,
    ) -> dict:
        """Create a named super-admin or securely recover an existing account.

        This method is intentionally not exposed through HTTP.  The local CLI
        is the control plane, so a compromised web super-admin session cannot
        mint another super-admin or bypass Gate 2A.
        """
        from app.core.kernel.models.user import (  # noqa: PLC0415
            RefreshToken,
            TwoFactorRecoveryCode,
        )
        from app.modules.core.models import AuditLog  # noqa: PLC0415

        normalized_email = (email or "").strip().casefold()
        normalized_name = (full_name or "").strip()
        if not validate_email_format(normalized_email):
            raise ValueError("A valid email address is required")

        user = self.db.query(self.repo.model).filter(
            self.repo.model.email == normalized_email,
        ).with_for_update().first()
        if create:
            if user:
                raise ValueError("An account with this email already exists")
            if len(normalized_name) < 3:
                raise ValueError("A named super-admin requires a full name")
            user = self.repo.model(
                email=normalized_email,
                password_hash="pending-bootstrap-hash",
                full_name=normalized_name,
                role="super_admin",
                is_active=True,
            )
            self.db.add(user)
            self.db.flush()
            action = "super_admin_bootstrap_created"
        else:
            if not user or getattr(user, "deleted_at", None) is not None:
                raise ValueError("Super-admin account not found")
            # Recovery preserves the existing role exactly.  It may repair an
            # old accountant or other seeded staff identity, but it can never
            # turn that identity into a super-admin. Role changes remain owned
            # by the Gate 2A HTTP control plane and its concurrency invariants.
            action = "account_bootstrap_recovered"

        temporary_password = self._new_temporary_password()
        enrollment_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.settings.TWO_FACTOR_ENROLLMENT_TOKEN_TTL_MINUTES,
        )

        user.password_hash = get_password_hash(temporary_password)
        user.is_active = True
        user.failed_login_attempts = 0
        user.account_locked_until = None
        user.must_change_password = True
        user.two_factor_enabled = False
        user.two_factor_secret = None
        user.two_factor_last_used_step = None
        user.two_factor_bootstrap_required = True
        user.two_factor_enrollment_token_hash = self._hash_token(enrollment_token)
        user.two_factor_enrollment_expires_at = expires_at

        self.db.query(RefreshToken).filter(RefreshToken.user_id == user.id).delete(
            synchronize_session=False,
        )
        self.db.query(TwoFactorRecoveryCode).filter(
            TwoFactorRecoveryCode.user_id == user.id,
        ).delete(synchronize_session=False)
        self.db.add(AuditLog(
            user_id=None,
            branch_id=None,
            action=action,
            entity_type="user_authentication",
            entity_id=user.id,
            old_data=None,
            new_data=json.dumps(
                {
                    "email": normalized_email,
                    "full_name": user.full_name,
                    "enrollment_expires_at": expires_at.isoformat(),
                    "requires_password_change": True,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ))
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self._revoke_access_tokens(user.id)
        return {
            "user_id": user.id,
            "email": normalized_email,
            "full_name": user.full_name,
            "temporary_password": temporary_password,
            "enrollment_token": enrollment_token,
            "enrollment_expires_at": expires_at,
        }

    def provision_staff_account(
        self,
        *,
        email: str,
        full_name: str,
        phone: Optional[str],
        employee_id: Optional[int],
        role: str,
        preferred_language: str,
        actor_id: int,
        reason: str,
        step_up_public_reference: str,
        assurance_method: str,
    ) -> dict:
        """Provision one staff identity after super-admin step-up.

        The returned temporary password and enrollment token are one-time
        response values. Only password/token hashes are stored. Super-admin
        creation deliberately remains out-of-band in ``app.admin_bootstrap``.
        """
        from app.modules.core import crud  # noqa: PLC0415
        from app.modules.core.models import AuditLog  # noqa: PLC0415

        normalized_email = (email or "").strip().casefold()
        normalized_name = (full_name or "").strip()
        normalized_phone = (phone or "").strip() or None
        normalized_reason = (reason or "").strip()

        if not validate_email_format(normalized_email):
            raise ValueError("A valid email address is required")
        if len(normalized_name) < 3:
            raise ValueError("A full name is required")
        if role not in STAFF_PROVISIONABLE_ROLES:
            raise ValueError("This role cannot be provisioned through the web control plane")
        if preferred_language not in {"ar", "en"}:
            raise ValueError("Unsupported staff language")
        if len(normalized_reason) < 3:
            raise ValueError("A reason is required")

        # Serialize privileged control-plane mutations and re-check the actor
        # under the same ordered lock used by Gate 2A role changes.
        active_super_admins = crud.lock_active_super_admins(self.db)
        if actor_id not in {user.id for user in active_super_admins}:
            raise PermissionError("Your super-admin privileges changed; reload and try again")

        existing = self.db.query(self.repo.model).filter(
            func.lower(self.repo.model.email) == normalized_email,
        ).with_for_update().first()
        if existing is not None:
            raise ValueError("An account with this email already exists")

        temporary_password = self._new_temporary_password()
        enrollment_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.settings.TWO_FACTOR_ENROLLMENT_TOKEN_TTL_MINUTES,
        )
        user = self.repo.model(
            email=normalized_email,
            password_hash=get_password_hash(temporary_password),
            full_name=normalized_name,
            phone=normalized_phone,
            role=role,
            is_active=True,
            preferred_language=preferred_language,
            must_change_password=True,
            two_factor_enabled=False,
            two_factor_bootstrap_required=True,
            two_factor_enrollment_token_hash=self._hash_token(enrollment_token),
            two_factor_enrollment_expires_at=expires_at,
        )
        self.db.add(user)
        self.db.flush()
        if employee_id is not None:
            from app.modules.hr.models import Employee  # noqa: PLC0415

            employee = self.db.query(Employee).filter(
                Employee.id == employee_id,
            ).with_for_update().first()
            if employee is None:
                raise ValueError("The selected employee record does not exist")
            if employee.user_id is not None:
                raise ValueError("The selected employee record is already linked to an account")
            employee.user_id = user.id
        self.db.add(AuditLog(
            user_id=actor_id,
            branch_id=None,
            action="staff_account_provisioned",
            entity_type="user",
            entity_id=user.id,
            old_data=None,
            new_data=json.dumps({
                "email": normalized_email,
                "full_name": normalized_name,
                "phone": normalized_phone,
                "employee_id": employee_id,
                "role": role,
                "preferred_language": preferred_language,
                "reason": normalized_reason,
                "step_up_public_reference": step_up_public_reference,
                "assurance_method": assurance_method,
                "enrollment_expires_at": expires_at.isoformat(),
                "requires_password_change": True,
            }, ensure_ascii=False, sort_keys=True),
        ))
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(user)
        return {
            "user": user,
            "temporary_password": temporary_password,
            "enrollment_token": enrollment_token,
            "enrollment_expires_at": expires_at,
        }

    # ── Token blacklist / revocation ────────────────────────────────────

    def revoke_token(self, token: str, user_id: int, *, commit: bool = True) -> None:
        if not token:
            return
        token_hash = self._hash_token(token)
        # Both supported databases implement ON CONFLICT. Keeping this as one
        # statement avoids a check-then-insert race between duplicate logout
        # requests while still allowing the caller to own the final commit.
        self.db.execute(
            text("""
                INSERT INTO token_blacklist (token_hash, user_id, expires_at)
                VALUES (:h, :uid, :exp) ON CONFLICT DO NOTHING
            """),
            {
                "h": token_hash,
                "uid": user_id,
                "exp": datetime.now(timezone.utc) + timedelta(days=8),
            },
        )
        if commit:
            self.db.commit()

    def revoke_session(
        self,
        *,
        access_token: str,
        refresh_token: str,
        user_id: int,
    ) -> None:
        """Revoke both credentials belonging to the current browser session
        (logout). The presented refresh token's whole family is revoked (not
        just the single row) so its consumed-token tombstones stay behind for
        replay detection while no live successor remains."""
        from app.core.kernel.models.user import RefreshToken  # noqa: PLC0415

        self.revoke_token(access_token, user_id, commit=False)
        if refresh_token:
            self._lock_user_for_update(user_id)
            rt = self.db.query(RefreshToken).filter(
                RefreshToken.user_id == user_id,
                RefreshToken.token_hash == self._hash_token(refresh_token),
            ).first()
            if rt is not None:
                self._revoke_family(user_id, rt.family_id)
        self._add_auth_audit(user_id, "logout")
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def is_token_revoked(self, token_hash: str) -> bool:
        from app.core.kernel.models.user import TokenBlacklist  # noqa: PLC0415

        return self.db.query(TokenBlacklist.id).filter(
            TokenBlacklist.token_hash == token_hash,
            TokenBlacklist.expires_at > datetime.now(timezone.utc),
        ).first() is not None

    # ── Password reset ────────────────────────────────────────────────────

    def create_password_reset_token(self, email: str) -> Optional[str]:
        from app.core.kernel.models.user import TokenBlacklist  # noqa: PLC0415
        from app.core.kernel.cache import rate_limit  # noqa: PLC0415

        email = email.strip()
        email_bucket = self._hash_token(email.casefold())
        if not rate_limit(
            f"password-reset-account:{email_bucket}",
            max_requests=self.settings.PASSWORD_RESET_ACCOUNT_RATE_LIMIT_MAX,
            window_seconds=self.settings.PASSWORD_RESET_ACCOUNT_RATE_LIMIT_WINDOW_SECONDS,
        ):
            # Keep the public response indistinguishable from an unknown email
            # while preventing distributed email bombing of one account.
            return None

        user = self.repo.get_by_email(email)
        if (
            not user
            or not user.is_active
            or getattr(user, "deleted_at", None) is not None
        ):
            return None
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=2)
        # One live recovery link per account. A newer request invalidates any
        # older email so a previously stolen link cannot reset the password
        # after the legitimate user has already requested another one.
        self.db.query(TokenBlacklist).filter(
            TokenBlacklist.user_id == user.id,
            TokenBlacklist.token_hash.startswith(_RESET_TOKEN_PREFIX, autoescape=True),
        ).delete(synchronize_session=False)
        self.db.add(TokenBlacklist(
            token_hash=self._password_reset_token_hash(token),
            user_id=user.id,
            expires_at=expires,
        ))
        # Server-side audit only (never returned to the client, so not an
        # enumeration side channel) and already bounded by the per-account
        # rate limit above — records that a real account requested a reset.
        self._add_auth_audit(user, "password_reset_requested")
        self.db.commit()
        return token

    @classmethod
    def _password_reset_token_hash(cls, token: str) -> str:
        return f"{_RESET_TOKEN_PREFIX}{cls._hash_token(token)}"

    def confirm_password_reset(self, token: str, new_password: str) -> bool:
        from sqlalchemy import or_  # noqa: PLC0415
        from app.core.kernel.models.user import TokenBlacklist  # noqa: PLC0415

        valid, msg = validate_password_strength(new_password)
        if not valid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
        # Accept the legacy raw-token key only during its original two-hour
        # lifetime, preserving links issued just before deployment. All newly
        # issued rows are SHA-256 hashes and never expose the bearer token.
        row = self.db.query(TokenBlacklist).filter(
            or_(
                TokenBlacklist.token_hash == self._password_reset_token_hash(token),
                TokenBlacklist.token_hash == f"{_RESET_TOKEN_PREFIX}{token}",
            ),
            TokenBlacklist.expires_at > datetime.now(timezone.utc),
        ).first()
        if not row:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token expired or invalid")
        user = self.repo.get(row.user_id)
        if (
            not user
            or not user.is_active
            or getattr(user, "deleted_at", None) is not None
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token expired or invalid")

        user.password_hash = get_password_hash(new_password)
        user.must_change_password = False
        self.db.query(TokenBlacklist).filter(
            TokenBlacklist.user_id == user.id,
            TokenBlacklist.token_hash.startswith(_RESET_TOKEN_PREFIX, autoescape=True),
        ).delete(synchronize_session=False)
        delete_refresh_tokens_for_user(self.db, user.id)
        self._add_auth_audit(user, "password_reset_completed")
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self._revoke_access_tokens(user.id)
        return True

    # ── Admin helpers ────────────────────────────────────────────────────

    def unlock_account(self, user_id: int) -> bool:
        user = self.repo.get(user_id)
        if not user:
            raise HTTPException(404, "User not found")
        user.account_locked_until = None
        user.failed_login_attempts = 0
        self.db.commit()
        return True
