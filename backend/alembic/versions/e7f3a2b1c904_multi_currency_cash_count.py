"""Add currency column to cashier_shift_cash_counts for multi-currency cash drawer

Revision ID: e7f3a2b1c904
Revises: c8f2d4b1e703
Create Date: 2026-07-09 18:40:00.000000

المشكلة: cashier_shift_cash_counts كانت تحفظ فئات الجنيه المصري بس — مفيش طريقة
الكاشير يسجّل دولار أو يورو في عدّ نهاية الوردية. أضفنا currency (افتراضي EGP)
عشان كل فئة ممكن تكون بعملة مختلفة، والإجمالي المعدود بيتحسب بعد تحويل الكل لـ EGP
باستخدام أسعار الصرف المخزّنة في exchange_rates.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e7f3a2b1c904"
down_revision: str = "c8f2d4b1e703"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # currency لكل سطر عدّ — EGP افتراضي للـ rows الموجودة (سليمة بدون تغيير)
    op.add_column(
        "cashier_shift_cash_counts",
        sa.Column("currency", sa.String(3), nullable=False, server_default="EGP"),
    )
    # egp_equivalent — قيمة السطر بعد التحويل لـ EGP (denomination × quantity × fx_rate)
    # بيتخزّن عند الإنشاء بدل إعادة حسابه كل مرة (مهم للتدقيق — لو سعر الصرف اتغيّر لاحقاً)
    op.add_column(
        "cashier_shift_cash_counts",
        sa.Column(
            "egp_equivalent",
            sa.Numeric(12, 2),
            nullable=True,   # nullable مؤقتاً للـ rows القديمة — يُملأ في data migration
        ),
    )
    # data migration للـ rows القديمة: egp_equivalent = subtotal (كلها EGP بالفعل)
    op.execute(
        "UPDATE cashier_shift_cash_counts SET egp_equivalent = subtotal WHERE egp_equivalent IS NULL"
    )
    # بعد الملء — نحوّله NOT NULL
    op.alter_column("cashier_shift_cash_counts", "egp_equivalent", nullable=False)

    # fx_rate المستخدم لتحويل هذا السطر (1.0 للـ EGP) — للتدقيق التاريخي
    op.add_column(
        "cashier_shift_cash_counts",
        sa.Column(
            "fx_rate",
            sa.Numeric(12, 6),
            nullable=False,
            server_default="1.000000",
        ),
    )


def downgrade() -> None:
    op.drop_column("cashier_shift_cash_counts", "fx_rate")
    op.drop_column("cashier_shift_cash_counts", "egp_equivalent")
    op.drop_column("cashier_shift_cash_counts", "currency")
