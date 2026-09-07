"""
app/modules/finance/_services/discounts.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.modules.finance import crud
from app.resort_os.timezone_utils import local_today
from app.modules.finance.schemas import (
    ConditionalDiscountCreate,
)
from app.resort_os.discount_engine import DiscountResult, DiscountRule, OrderContext, calculate_discount
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.modules.finance.models import ConditionalDiscount  # noqa: F401


def create_discount(db: Session, data: ConditionalDiscountCreate):
    if data.valid_from > data.valid_until:
        raise ValueError("valid_from يجب أن يكون قبل valid_until")
    obj = crud.create_discount(db, data)
    db.commit()
    db.refresh(obj)
    return obj


def calculate_order_discount(
    db: Session,
    branch_id: int,
    order_total: Decimal,
    item_count: int = 1,
    customer_group: str = "default",
    order_date: Optional[date] = None,
    order_time: Optional[time] = None,
) -> DiscountResult:
    # اليوم المحلي بتوقيت المنتجع (Africa/Cairo) لو المستخدم مبعتش تاريخ صريح —
    # مش date.today() (توقيت السيرفر، راجع §13 CLAUDE.md لفئة الباج دي).
    order_date = order_date or local_today(settings.TIMEZONE)
    rules_orm, _ = crud.list_discounts(db, branch_id, active_only=True, limit=200)
    rules = [discount_rule_from_orm(r) for r in rules_orm]
    ctx = OrderContext(
        total_amount=order_total,
        item_count=item_count,
        order_date=order_date,
        order_time=order_time or time(0, 0),
        customer_group=customer_group,
    )
    return calculate_discount(order_total, rules, ctx)


def discount_rule_from_orm(r: "ConditionalDiscount") -> DiscountRule:
    """يحوّل صف ConditionalDiscount (ORM) لـ DiscountRule (plain dataclass) —
    نفس التحويل مُكرر سابقًا في finance/restaurant/cafe services، مُوحَّد هنا
    كمصدر وحيد للحقيقة (عشان أي حقل جديد يُضاف مرة واحدة بس)."""
    return DiscountRule(
        id=r.id,
        condition_type=r.condition_type,
        condition_value=r.condition_value,
        discount_type=r.discount_type,
        discount_value=r.discount_value,
        max_uses=r.max_uses,
        valid_from=r.valid_from,
        valid_until=r.valid_until,
        priority=r.priority,
        uses_count=r.uses_count,
        scope_type=r.scope_type,
        scope_outlet=r.scope_outlet,
        scope_id=r.scope_id,
    )


# ── Double-Entry Accounting ────────────────────────────────────────────
