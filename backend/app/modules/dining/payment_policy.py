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

from app.core.config import settings

# طرق الدفع المباشرة (بتحصّل كاش/مقاصّة فورًا في درج الوردية) مقابل room
# (ذمّة على فوليو الغرفة، بتتسوّى وقت الـ checkout — مش tender مباشر).
DIRECT_TENDER_METHODS = frozenset({"cash", "card", "wallet"})
ALL_TENDER_METHODS = frozenset({"cash", "card", "wallet", "room"})


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
