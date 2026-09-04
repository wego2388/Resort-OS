"""app/modules/dining/payment_policy.py — Gate 4A typed, fail-closed
dining payment-method policy.

Every direct tender (cash|card|wallet) that actually collects money into a
drawer/clearing account must settle to a *known* GL account at payment time.
The old dining pay path always posted to Cash ``1100`` regardless of the
``payment_method`` string (Gate 4 brief §1.14) — so a card sale overstated
physical cash on hand. The brief is explicit: cash maps to the existing
``1100`` and room to receivables ``1150``, but card/wallet must **not** be
mapped to an invented GL account. If the resort wants card/wallet separated
in the ledger it must configure an explicit clearing account
(``settings.DINING_CARD_SETTLEMENT_ACCOUNT`` /
``DINING_WALLET_SETTLEMENT_ACCOUNT``, deployment-level, typed). Until then the
method **fails closed** with a clear configuration error (HTTP 503
``METHOD_NOT_CONFIGURED``) rather than silently posting to cash.

``room`` is not a direct tender here — it is a receivable charged to the guest
folio and settled at checkout, handled by the folio-charge path, not this
module.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, Optional

from app.core.config import settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# طرق الدفع المباشرة (بتحصّل كاش/مقاصّة فورًا في درج الوردية) مقابل room
# (ذمّة على فوليو الغرفة، بتتسوّى وقت الـ checkout — مش tender مباشر).
DIRECT_TENDER_METHODS = frozenset({"cash", "card", "wallet"})
ALL_TENDER_METHODS = frozenset({"cash", "card", "wallet", "room", "credit_account"})


class PaymentMethodNotConfiguredError(Exception):
    """طريقة دفع مباشرة (card/wallet) محتاجة حساب مقاصّة GL صريح لسه ما
    اتهيّأش على مستوى الـ deployment — 503 METHOD_NOT_CONFIGURED. مش خطأ
    عميل (400) ولا تخمين حساب: إعداد ناقص محتاج محاسب/مدير يظبطه (نفس فئة
    finance.services.FinancialConfigurationError بالظبط)."""


def is_direct_method(method: str) -> bool:
    return method in DIRECT_TENDER_METHODS


def resolve_direct_tender_account(method: str) -> str:
    """حساب GL اللي الـ tender المباشر ده بيترحّل عليه (مدين وقت البيع) —
    fail-closed لأي طريقة غير مهيّأة. cash ثابت 1100 (حساب الكاش الموجود).
    card/wallet لازم يكونوا مهيّأين صراحةً في الإعدادات، وإلا بيرفعوا
    PaymentMethodNotConfiguredError."""
    if method == "cash":
        return "1100"
    if method == "card":
        acc = settings.DINING_CARD_SETTLEMENT_ACCOUNT
        if not acc:
            raise PaymentMethodNotConfiguredError(
                "الدفع بالبطاقة غير مهيّأ محاسبيًا — لازم المحاسب يحدد حساب "
                "مقاصّة الفيزا (DINING_CARD_SETTLEMENT_ACCOUNT) قبل قبول دفع "
                "بالبطاقة، عشان مايترحّلش بالغلط على حساب الكاش"
            )
        return acc
    if method == "wallet":
        acc = settings.DINING_WALLET_SETTLEMENT_ACCOUNT
        if not acc:
            raise PaymentMethodNotConfiguredError(
                "الدفع بالمحفظة الإلكترونية غير مهيّأ محاسبيًا — لازم المحاسب "
                "يحدد حساب المحفظة (DINING_WALLET_SETTLEMENT_ACCOUNT) قبل "
                "قبول الدفع بالمحفظة"
            )
        return acc
    raise PaymentMethodNotConfiguredError(f"طريقة دفع غير معروفة: {method}")


class TenderResolution(NamedTuple):
    """حساب GL الفعلي لـtender مباشر + لقطة قناة التحصيل (لو موجودة).

    ``channel_snapshot`` بقيمه الأربعة ``None`` يعني مسار legacy (الفرع
    مفيهوش أي payment_channels لهذه الطريقة بعد) — الحساب راجع من
    ``resolve_direct_tender_account`` القديمة بدل قناة حقيقية."""
    account_code: str
    channel_snapshot: dict


def resolve_tender_channel(
    db: "Session", branch_id: int, method: str, channel_id: Optional[int] = None,
) -> TenderResolution:
    """المصدر الموحّد لحساب GL + لقطة قناة أي tender مباشر (شاطئ ودايننج
    الاتنين بينادوها). قنوات التحصيل المُعرَّفة في الداتابيز (finance.
    PaymentChannel) هي المصدر الأساسي؛ ``resolve_direct_tender_account``
    القديمة (متغيرات بيئة) تفضل fallback بس لفرع لسه معملوش أي قناة
    لهذه الطريقة — توافق مع الحركات القديمة، مش الحالة الافتراضية الجديدة."""
    from app.modules.finance import services as finance_services  # noqa: PLC0415

    channel = finance_services.resolve_payment_channel(db, branch_id, method, channel_id)
    if channel is not None:
        return TenderResolution(
            account_code=channel.gl_account.code,
            channel_snapshot=finance_services.payment_channel_snapshot(channel),
        )
    return TenderResolution(
        account_code=resolve_direct_tender_account(method),
        channel_snapshot=finance_services.payment_channel_snapshot(None),
    )
