"""
app/modules/finance/_services/payment_channels.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session
from app.modules.finance import crud
from app.modules.finance.schemas import (
    PaymentChannelCreate,
    PaymentChannelUpdate,
)


def get_payment_channel_or_404(db: Session, channel_id: int):
    channel = crud.get_payment_channel(db, channel_id)
    if not channel:
        raise ValueError(f"قناة التحصيل {channel_id} غير موجودة")
    return channel


def _validate_payment_channel_accounts(
    db: Session, branch_id: int, gl_account_id: int,
    bank_account_id: Optional[int], method: str,
) -> None:
    gl = crud.get_account(db, gl_account_id)
    if not gl or gl.branch_id != branch_id:
        raise ValueError(f"حساب GL {gl_account_id} غير موجود في هذا الفرع")
    if not gl.is_active:
        raise ValueError(f"حساب GL «{gl.name}» غير نشط")
    if gl.account_type != "asset":
        raise ValueError(f"حساب GL «{gl.name}» يجب أن يكون من نوع أصل (Asset) ليصلح لتحصيل قناة دفع")

    if bank_account_id is None:
        return
    if method == "cash":
        raise ValueError("قناة تحصيل نقدية (cash) لا يمكن ربطها بحساب بنكي")
    bank = crud.get_bank_account(db, bank_account_id)
    if not bank or bank.branch_id != branch_id:
        raise ValueError(f"الحساب البنكي {bank_account_id} غير موجود في هذا الفرع")
    if not bank.is_active:
        raise ValueError(f"الحساب البنكي «{bank.account_name}» غير نشط")


def list_payment_channels(
    db: Session, branch_id: int, active_only: bool = False, method: Optional[str] = None,
):
    return crud.list_payment_channels(db, branch_id, active_only, method)


def create_payment_channel(db: Session, data: PaymentChannelCreate):
    _validate_payment_channel_accounts(db, data.branch_id, data.gl_account_id, data.bank_account_id, data.method)
    if crud.get_payment_channel_by_code(db, data.branch_id, data.code):
        raise ValueError(f"كود القناة «{data.code}» مستخدم بالفعل في هذا الفرع")
    channel = crud.create_payment_channel(db, data)
    db.commit()
    return crud.get_payment_channel(db, channel.id)


def update_payment_channel(db: Session, channel_id: int, data: PaymentChannelUpdate):
    channel = get_payment_channel_or_404(db, channel_id)
    gl_account_id = data.gl_account_id if data.gl_account_id is not None else channel.gl_account_id
    if data.clear_bank_account:
        bank_account_id = None
    elif data.bank_account_id is not None:
        bank_account_id = data.bank_account_id
    else:
        bank_account_id = channel.bank_account_id
    _validate_payment_channel_accounts(db, channel.branch_id, gl_account_id, bank_account_id, channel.method)
    channel = crud.update_payment_channel(db, channel, data)
    db.commit()
    return crud.get_payment_channel(db, channel.id)


def resolve_payment_channel(
    db: Session, branch_id: int, method: str, channel_id: Optional[int] = None,
):
    """يحل القناة الفعلية المستخدمة لحركة بيع (Beach/Dining).

    - ``channel_id`` محدد صراحةً → لازم يكون نشط، لنفس الفرع، ولنفس
      ``method``، وإلا يترفض بوضوح.
    - غير محدد وفيه قنوات مُعرَّفة لهذا الفرع/الطريقة → يستخدم الـdefault
      النشط؛ عدم وجود default صالح خطأ صريح (مايترحّلش لحساب عشوائي).
    - غير محدد ومفيش أي قناة مُعرَّفة خالص لهذا الفرع/الطريقة → ``None``
      (توافق مؤقت مع الفروع/البيئات اللي لسه معملتش channels — المسار
      القديم القائم على متغيرات البيئة يفضل شغّال زي ما هو).
    """
    if channel_id is not None:
        channel = crud.get_payment_channel(db, channel_id)
        if not channel or channel.branch_id != branch_id:
            raise ValueError(f"قناة التحصيل {channel_id} غير موجودة في هذا الفرع")
        if not channel.is_active:
            raise ValueError(f"قناة التحصيل «{channel.name}» معطّلة، اختر قناة نشطة")
        if channel.method != method:
            raise ValueError(f"قناة التحصيل «{channel.name}» لا تدعم طريقة الدفع «{method}»")
        return channel

    existing = crud.list_payment_channels(db, branch_id, method=method)
    if not existing:
        return None

    default = crud.get_default_payment_channel(db, branch_id, method)
    if not default:
        raise ValueError(
            f"لا توجد قناة تحصيل افتراضية صالحة لطريقة الدفع «{method}» في هذا الفرع — "
            "اختر قناة يدويًا أو اضبط قناة افتراضية من إدارة قنوات التحصيل",
        )
    return default


def payment_channel_snapshot(channel) -> dict:
    """لقطة تُخزَّن على الحركة نفسها (Payment/BeachTransaction) — مش مرجع
    حي. ``channel=None`` (مسار legacy بلا قنوات مُعرَّفة) يرجّع لقطة فاضية،
    والمرتجع/الـvoid وقتها بيفضل يستخدم حساب البيئة القديم زي ما هو."""
    if channel is None:
        return {
            "payment_channel_id": None,
            "payment_channel_code": None,
            "payment_channel_name": None,
            "settlement_account_code": None,
        }
    return {
        "payment_channel_id": channel.id,
        "payment_channel_code": channel.code,
        "payment_channel_name": channel.name,
        "settlement_account_code": channel.gl_account.code,
    }
