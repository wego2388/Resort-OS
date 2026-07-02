"""core: user_permissions table (fine-grained permission matrix over ROLE_LEVELS)

Revision ID: b1c9d4e7f203
Revises: f1a2b3c4d5e6
Create Date: 2026-07-02

Hand-written (not autogenerate) — the shared dev DB had concurrent migrations
from parallel agents landing mid-session, so autogenerate diffing against a
moving head was unreliable. This revision touches ONLY the new
`user_permissions` table added in app/modules/core/models.py::UserPermission.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b1c9d4e7f203'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_permissions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('resource', sa.String(length=100), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('allowed', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=True),
        sa.Column('granted_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            'user_id', 'resource', 'action', 'branch_id',
            name='uq_user_permission_scope',
        ),
    )
    op.create_index('ix_user_permissions_user_id', 'user_permissions', ['user_id'])
    op.create_index('ix_user_permissions_resource', 'user_permissions', ['resource'])
    op.create_index('ix_user_permissions_branch_id', 'user_permissions', ['branch_id'])


def downgrade() -> None:
    op.drop_index('ix_user_permissions_branch_id', table_name='user_permissions')
    op.drop_index('ix_user_permissions_resource', table_name='user_permissions')
    op.drop_index('ix_user_permissions_user_id', table_name='user_permissions')
    op.drop_table('user_permissions')
