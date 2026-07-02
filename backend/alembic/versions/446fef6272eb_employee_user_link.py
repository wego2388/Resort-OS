"""employee_user_link

Revision ID: 446fef6272eb
Revises: b1c9d4e7f203
Create Date: 2026-07-02 04:47:11.416029

Employee.user_id → users.id (SET NULL, unique, nullable) — يسمح لموظف
مربوط بحساب دخول يشوف حضوره/إجازاته/راتبه بنفسه عبر /hr/me/*. NULL
افتراضياً (موظفين موسميين/بدون حساب نظام).

ملاحظة: alembic autogenerate التقط drift ضخم غير متعلق من موديولات تانية
شغّالة بالتوازي هذا الـ run (indexes/foreign keys/NOT NULL على جداول زي
audit_logs, notifications, settings, module_states, bookings, rooms, ...)
— اتشال يدوياً وسيبنا بس تغيير employees.user_id المقصود.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '446fef6272eb'
down_revision: Union[str, None] = 'b1c9d4e7f203'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('employees', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_unique_constraint('employees_user_id_key', 'employees', ['user_id'])
    op.create_foreign_key(
        'employees_user_id_fkey', 'employees', 'users',
        ['user_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('employees_user_id_fkey', 'employees', type_='foreignkey')
    op.drop_constraint('employees_user_id_key', 'employees', type_='unique')
    op.drop_column('employees', 'user_id')
