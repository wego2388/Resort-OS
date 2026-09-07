"""app/modules/timeshare/_services/owner_portal.py — Owner Portal بوابة
صاحب العقد العامة (طلب Mohamed 2026-08-03).

صفحة على الموقع العام يتحقق فيها صاحب عقد ملكية جزئية من هويته (رقم العقد +
رقم موبايله المسجّل على العقد + كود OTP يوصله واتساب — مفيش باسورد
ولا حساب دائم، وده عمدًا: "ما يكونش معقد" + "السرية"). بعد التحقق بيشوف
عقده وحالة دفعاته، ويقدر يقدّم طلب حجز زيارة (المدير هو اللي يوافق
ويحدد الأسبوع الفعلي فعليًا — راجع visit_requests_support.approve_visit_request،
بتنادي visits.create_visit الموجودة فمفيش تكرار لمنطق التجميد/التعارض) أو
يفتح تذكرة دعم (نظام مستقل عن استفسارات الموقع العام، مش نفس صندوق CRM Lead)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import Session

from app.modules.timeshare import crud


class OwnerVerificationError(Exception):
    """كود OTP غلط/منتهي/العدد المسموح للمحاولات اتخلص، أو JWT owner-portal
    token غير صالح/منتهي."""


def _hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _normalize_phone_for_match(phone: str) -> str:
    """مقارنة أرقام الموبايل بعد تجريدها من أي رموز غير رقمية، ومقارنة آخر
    10 أرقام بس — العميل ممكن يكتب رقمه بصيغة دولية (+20...) مختلفة شوية
    عن الصيغة المسجّلة على العقد (01...)، من غير ما نطلب صيغة واحدة صارمة
    (طلب Mohamed: "سهولة المستخدم")."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def request_owner_otp(db: Session, contract_number: str, phone: str) -> None:
    """⚠️ أمان (anti-enumeration): الدالة دايمًا "تنجح" بصمت (بدون أي
    استثناء أو قيمة رجوع تكشف الفرق) بغض النظر عن تطابق رقم العقد/الموبايل
    من عدمه — لو فرّقنا الرد هيبقى oracle يقدر أي حد يجرّب أرقام عقود
    عشوائية ويكتشف أيها حقيقي بمجرد الفرق في رسالة الرد. الـOTP بيتبعت
    فعليًا واتساب بس لو التطابق صحيح فعلاً."""
    from app.core.config import settings  # noqa: PLC0415
    from app.core.kernel.cache import rate_limit, set_cache  # noqa: PLC0415
    from app.core.kernel.whatsapp import send_whatsapp_message  # noqa: PLC0415

    # مفتاحان منفصلان (رقم العقد + رقم الموبايل) — يمنعوا (أ) قصف نفس رقم
    # العقد بطلبات OTP متكررة، و(ب) محاولة تجربة أرقام عقود كتير مختلفة من
    # نفس رقم الموبايل.
    if not rate_limit(f"timeshare_otp_req_contract:{contract_number}", max_requests=3, window_seconds=600):
        return
    if not rate_limit(f"timeshare_otp_req_phone:{_normalize_phone_for_match(phone)}", max_requests=5, window_seconds=600):
        return

    contract = crud.get_contract_by_number(db, contract_number)
    if not contract or not contract.customer_phone:
        return
    if _normalize_phone_for_match(contract.customer_phone) != _normalize_phone_for_match(phone):
        return
    if contract.status == "cancelled":
        return

    code = f"{secrets.randbelow(1_000_000):06d}"
    set_cache(
        f"timeshare_otp:{contract_number}",
        {"code_hash": _hash_otp(code), "attempts": 0, "contract_id": contract.id},
        ttl=settings.TIMESHARE_OTP_TTL_SECONDS,
    )
    minutes = settings.TIMESHARE_OTP_TTL_SECONDS // 60
    send_whatsapp_message(
        contract.customer_phone,
        f"كود التحقق لبوابة عقدك في El Kheima Beach Resort: {code}\n"
        f"صالح لمدة {minutes} دقائق. لا تشارك هذا الكود مع أحد.",
    )


def _issue_owner_portal_token(contract_id: int) -> str:
    from app.core.config import settings  # noqa: PLC0415

    payload = {
        "sub": str(contract_id),
        "purpose": "timeshare_owner_portal",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.TIMESHARE_PORTAL_TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, settings.TIMESHARE_PORTAL_TOKEN_SECRET, algorithm="HS256")


def confirm_owner_otp(db: Session, contract_number: str, otp_code: str) -> str:
    """يتحقق من الكود المُدخَل مقابل المخزَّن في الكاش (مقارنة زمن ثابت،
    نفس نمط TOTP consumption في kernel.auth.service)، ولو صح بيرجّع owner
    portal token (JWT) جاهز. الكود يُستهلك (single-use) عند النجاح، ويُلغى
    نهائيًا لو عدد المحاولات الخاطئة وصل الحد الأقصى (يمنع تخمين الكود
    بالقوة الغاشمة خلال نافذة الصلاحية القصيرة)."""
    from app.core.config import settings  # noqa: PLC0415
    from app.core.kernel.cache import clear_cache, get_cache, set_cache  # noqa: PLC0415

    cache_key = f"timeshare_otp:{contract_number}"
    entry = get_cache(cache_key)
    if not entry:
        raise OwnerVerificationError("الكود منتهي الصلاحية أو غير موجود — اطلب كود جديد")

    if not secrets.compare_digest(_hash_otp(otp_code), entry["code_hash"]):
        entry["attempts"] = entry.get("attempts", 0) + 1
        if entry["attempts"] >= settings.TIMESHARE_OTP_MAX_ATTEMPTS:
            clear_cache(cache_key)
            raise OwnerVerificationError("عدد محاولات خاطئة كبير — اطلب كود جديد")
        set_cache(cache_key, entry, ttl=settings.TIMESHARE_OTP_TTL_SECONDS)
        raise OwnerVerificationError("كود التحقق غير صحيح")

    clear_cache(cache_key)
    return _issue_owner_portal_token(entry["contract_id"])


def verify_owner_portal_token(token: str) -> int:
    """يرجّع contract_id لو التوكن صالح وموقّع صح، وإلا يرفع
    OwnerVerificationError (الراوتر بيترجمها 401)."""
    from app.core.config import settings  # noqa: PLC0415

    try:
        payload = jwt.decode(token, settings.TIMESHARE_PORTAL_TOKEN_SECRET, algorithms=["HS256"])
    except Exception:
        raise OwnerVerificationError("انتهت صلاحية الجلسة — تحقق من هويتك مرة أخرى")
    if payload.get("purpose") != "timeshare_owner_portal":
        raise OwnerVerificationError("جلسة غير صالحة")
    return int(payload["sub"])
