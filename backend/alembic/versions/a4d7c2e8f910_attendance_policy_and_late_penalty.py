"""attendance_policy_and_late_penalty

Revision ID: a4d7c2e8f910
Revises: c1f4a8e02b7d
Create Date: 2026-07-06 00:00:00.000000

⚠️ down_revision اتحدّث من b2d7f931a4e1 لـ c1f4a8e02b7d أثناء دمج الفروع
(2026-07-07) — الهجرة دي اتعملت بالتوازي في worktree منفصل على نفس الأب
(b2d7f931a4e1) زي هجرتين تانيين (B2B credit-limit + وصفة/BOM المطعم/الكافيه)،
فلما اتدمجوا التلاتة مع بعض ظهر أكتر من alembic head. أُعيدت هذه الهجرة في
آخر السلسلة (بعد الاتنين التانيين) لإرجاع تسلسل خطي واحد.

يضيف:
- جدول attendance_policies (سياسة حضور لكل فرع: سماحية تأخير/انصراف مبكر،
  وردية قياسية fallback، نسب أوفرتايم/خصم تأخير) — تغذّي محرك الحضور→راتب
  الجديد (app.resort_os.hr_engine.compute_attendance_minutes) بدل ما تكون
  الأرقام دي مدخلات يدوية بحتة لكل كشف رواتب.
- payroll_lines.late_penalty_deduction — خصم تأخير محسوب تلقائيًا من الحضور،
  منفصل عن penalty_deduction الموجود أصلاً (جزاءات تأديبية يدوية بالأيام).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4d7c2e8f910'
down_revision: Union[str, None] = 'c1f4a8e02b7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_policies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("late_grace_minutes", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("early_leave_grace_minutes", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("standard_shift_start", sa.String(length=5), nullable=False, server_default="09:00"),
        sa.Column("standard_shift_end", sa.String(length=5), nullable=False, server_default="17:00"),
        sa.Column("overtime_rate_multiplier", sa.Numeric(4, 2), nullable=False, server_default="1.50"),
        sa.Column("late_penalty_rate_multiplier", sa.Numeric(4, 2), nullable=False, server_default="1.00"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )

    op.add_column(
        "payroll_lines",
        sa.Column("late_penalty_deduction", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("payroll_lines", "late_penalty_deduction")
    op.drop_table("attendance_policies")
