"""app/tasks/fraud_tasks.py — Operations & Control Layer plan §3.5 (Fraud Detection).

كاشف نشاط كاشير مشبوه — بيحسب عدد إجراءات حسّاسة معيّنة (مرتجع/إلغاء صنف/
محاولة خصم/فتح درج بدون بيع) لكل مستخدم خلال نافذة زمنية دوّارة، من بيانات
موجودة بالفعل (`AuditLog` + `CashMovement` — Batch 1/2 من نفس الخطة، مفيش
جدول تدقيق تاني، راجع تحذير الخطة الصريح ضد "second audit log"). لو أي عدّاد
تخطّى العتبة المضبوطة في `app/core/config.py`، بيتبعت تنبيه واتساب لإدارة
المنتجع (`core.kernel.whatsapp.notify_admin` — نفس آلية كل تنبيهات الـ Celery
التانية في المشروع، مفيش قناة جديدة).

`find_fraud_signals()` هو المنطق القابل للاختبار بالكامل (استعلامات + مقارنة
عتبات، مفيش Celery/واتساب/Redis هنا خالص) — راجع
`scan_for_fraud_signals` تحت للـ wrapper اللي بينادي عليها فعليًا مع
SessionLocal + إرسال التنبيهات + منع التكرار (dedup عبر Redis cache، نفس
البنية التحتية المستخدمة في `revoke_user_tokens`، مش آلية جديدة).

قرار تصميمي متعمد: العتبات هنا "عدد حركات خلال نافذة" مش "نسبة مئوية" —
حساب نسبة حقيقية (زي معدّل الإلغاء) محتاج مقام "إجمالي الطلبات المُنفَّذة"
وده بيفتح افتراضات إضافية (هل نقارن بعدد الطلبات ولا عدد الأصناف؟ في نفس
الوردية ولا نافذة زمنية منفصلة؟) Mohamed ما حددهاش صراحةً — قرار محافظ
ومبسّط، موثّق بوضوح في تقرير الدفعة دي وفي PROJECT_STATUS.md، سهل التوسيع
لنسبة مئوية حقيقية لاحقًا لو الحاجة ظهرت.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.core.config import settings
from app.core.kernel.worker import notify_task_failure

logger = logging.getLogger(__name__)


@dataclass
class FraudSignal:
    """إشارة احتيال محتملة واحدة — كاشير معيّن تخطّى عتبة قاعدة معيّنة."""
    user_id: int
    user_name: str
    rule: str            # "refund_count" | "void_count" | "discount_count" | "drawer_open_count"
    count: int
    threshold: int
    window_minutes: int
    message: str


def _count_audit_action_by_user(db: Session, action: str, since: datetime) -> dict[int, int]:
    """{user_id: عدد} — كل مستخدم نفّذ `action` معيّن في AuditLog من `since`
    لحد دلوقتي. `user_id` هو المنفّذ (مش الموافِق — راجع AuditLog.user_id
    بالظبط زي void/apply_discount)."""
    from app.modules.core.models import AuditLog  # noqa: PLC0415

    rows = (
        db.query(AuditLog.user_id, func.count(AuditLog.id))
        .filter(AuditLog.action == action, AuditLog.created_at >= since, AuditLog.user_id.isnot(None))
        .group_by(AuditLog.user_id)
        .all()
    )
    return {uid: count for uid, count in rows}


def _count_drawer_opens_by_user(db: Session, since: datetime) -> dict[int, int]:
    """راجع Batch 2 (Cash Control ledger) — drawer_open مش AuditLog action
    منفصل، هو CashMovement.movement_type. نفس شكل الإرجاع بالظبط عشان
    find_fraud_signals يعاملها بنفس المنطق."""
    try:
        from app.modules.finance.models import CashMovement  # noqa: PLC0415
    except ImportError:
        return {}

    rows = (
        db.query(CashMovement.performed_by, func.count(CashMovement.id))
        .filter(CashMovement.movement_type == "drawer_open", CashMovement.created_at >= since)
        .group_by(CashMovement.performed_by)
        .all()
    )
    return {uid: count for uid, count in rows}


def _user_display_name(db: Session, user_id: int) -> str:
    from app.core.kernel.models.user import User  # noqa: PLC0415

    user = db.query(User).filter(User.id == user_id).first()
    return user.full_name if user else f"مستخدم #{user_id}"


def find_fraud_signals(
    db: Session,
    now: datetime,
    *,
    refund_threshold: int,
    refund_window_minutes: int,
    void_threshold: int,
    void_window_minutes: int,
    discount_threshold: int,
    discount_window_minutes: int,
    drawer_open_threshold: int,
    drawer_open_window_minutes: int,
) -> list[FraudSignal]:
    """المنطق الأساسي القابل للاختبار — بيرجّع كل الإشارات اللي تخطّت
    عتبتها، بغض النظر عن أي إرسال/تكرار سابق (ده مسؤولية الـ task wrapper).
    ``now`` بارامتر صريح (مش datetime.utcnow() جوه الدالة) عشان التستات
    تقدر تتحكم فيه بالظبط — نفس نمط mark_b2b_contracts_overdue(db, today)."""
    signals: list[FraudSignal] = []

    checks = (
        ("refund_count", "refund_order_item", refund_threshold, refund_window_minutes,
         lambda cnt: f"⚠️ {cnt} مرتجع خلال {refund_window_minutes} دقيقة — راجع نشاط الكاشير"),
        ("void_count", "void_order_item", void_threshold, void_window_minutes,
         lambda cnt: f"⚠️ {cnt} إلغاء صنف خلال {void_window_minutes} دقيقة — راجع نشاط الكاشير"),
        ("discount_count", "apply_discount", discount_threshold, discount_window_minutes,
         lambda cnt: f"⚠️ {cnt} محاولة تطبيق خصم خلال {discount_window_minutes} دقيقة — راجع نشاط الكاشير"),
    )
    for rule, action, threshold, window_minutes, msg_fn in checks:
        since = now - timedelta(minutes=window_minutes)
        for user_id, count in _count_audit_action_by_user(db, action, since).items():
            if count >= threshold:
                name = _user_display_name(db, user_id)
                signals.append(FraudSignal(
                    user_id=user_id, user_name=name, rule=rule, count=count,
                    threshold=threshold, window_minutes=window_minutes,
                    message=f"🚨 {name}: {msg_fn(count)} (الحد {threshold})",
                ))

    since = now - timedelta(minutes=drawer_open_window_minutes)
    for user_id, count in _count_drawer_opens_by_user(db, since).items():
        if count >= drawer_open_threshold:
            name = _user_display_name(db, user_id)
            signals.append(FraudSignal(
                user_id=user_id, user_name=name, rule="drawer_open_count", count=count,
                threshold=drawer_open_threshold, window_minutes=drawer_open_window_minutes,
                message=(
                    f"🚨 {name}: {count} فتح درج بدون بيع خلال "
                    f"{drawer_open_window_minutes // 60} ساعة (الحد {drawer_open_threshold})"
                ),
            ))

    return signals


def _dedup_key(signal: FraudSignal) -> str:
    return f"fraud_alert:{signal.user_id}:{signal.rule}"


def _already_alerted(signal: FraudSignal) -> bool:
    from app.core.kernel.cache import get_cache  # noqa: PLC0415

    return get_cache(_dedup_key(signal)) is not None


def _mark_alerted(signal: FraudSignal) -> None:
    from app.core.kernel.cache import set_cache  # noqa: PLC0415

    set_cache(_dedup_key(signal), True, ttl=settings.FRAUD_ALERT_DEDUP_HOURS * 3600)


@celery_app.task(name="app.tasks.fraud_tasks.scan_for_fraud_signals", bind=True)
def scan_for_fraud_signals(self):
    """كل 15 دقيقة (راجع celery_app.py beat_schedule) — يفحص كل العتبات
    ويبعت تنبيه واتساب واحد بس لكل (كاشير، قاعدة) خلال نافذة
    FRAUD_ALERT_DEDUP_HOURS، عشان الفحص المتكرر كل 15 دقيقة ما يغرقش
    الإدارة برسايل مكررة عن نفس المشكلة المستمرة."""
    try:
        from app.core.database import SessionLocal  # noqa: PLC0415
        from app.core.kernel.whatsapp import notify_admin  # noqa: PLC0415

        with SessionLocal() as db:
            now = datetime.utcnow()
            signals = find_fraud_signals(
                db, now,
                refund_threshold=settings.FRAUD_REFUND_COUNT_THRESHOLD,
                refund_window_minutes=settings.FRAUD_REFUND_WINDOW_MINUTES,
                void_threshold=settings.FRAUD_VOID_COUNT_THRESHOLD,
                void_window_minutes=settings.FRAUD_VOID_WINDOW_MINUTES,
                discount_threshold=settings.FRAUD_DISCOUNT_COUNT_THRESHOLD,
                discount_window_minutes=settings.FRAUD_DISCOUNT_WINDOW_MINUTES,
                drawer_open_threshold=settings.FRAUD_DRAWER_OPEN_COUNT_THRESHOLD,
                drawer_open_window_minutes=settings.FRAUD_DRAWER_OPEN_WINDOW_MINUTES,
            )
            for signal in signals:
                if _already_alerted(signal):
                    continue
                logger.warning(
                    "Fraud signal: user=%s rule=%s count=%s threshold=%s",
                    signal.user_id, signal.rule, signal.count, signal.threshold,
                )
                notify_admin(signal.message)
                _mark_alerted(signal)

    except Exception as exc:
        logger.error("fraud scan_for_fraud_signals failed: %s", exc)
        notify_task_failure("app.tasks.fraud_tasks.scan_for_fraud_signals", exc)
