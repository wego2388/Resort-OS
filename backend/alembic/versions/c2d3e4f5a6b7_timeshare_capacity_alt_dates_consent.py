"""timeshare: unit_capacity/beneficiary/phones/mailing_address + visit-request alt dates + consent audit

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-10

OPS-DATA-02 §8 TIMESHARE-01R:

- نقطة 2 (السعة): unit_capacity nullable — Studio يُستنتَج بأمان = 2،
  Chalet (كان قديمًا 4R أو 6R قبل migration f2a3b4c5d6e7 اللي وحّدتهم)
  يفضل None لحد مراجعة يدوية؛ صفر default=2 عشوائي. CHECK constraint
  بيسمح NULL أو {2,4,6} — مش NOT NULL لسه (backfill غير كامل عمدًا).
- نقطة 1 (إثبات الموافقة): terms_version/terms_accepted_at/
  booking_rules_version/booking_rules_accepted_at على timeshare_visit_requests
  — NOT NULL لأن كل طلب جديد من هنا فصاعدًا لازم يمر schemas.
  TimeshareVisitRequestCreate الصارم (Literal[version_حالي]).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None

TIMESHARE_TERMS_VERSION = "timeshare-terms-2026-08-10.v1"
TIMESHARE_BOOKING_RULES_VERSION = "timeshare-booking-rules-2026-08-10.v1"


def upgrade() -> None:
    op.add_column("timeshare_contracts", sa.Column("unit_capacity", sa.Integer(), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("beneficiary_name", sa.String(200), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("customer_phone_work", sa.String(20), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("customer_phone_home", sa.String(20), nullable=True))
    op.add_column("timeshare_contracts", sa.Column("mailing_address", sa.String(300), nullable=True))
    op.create_check_constraint(
        "ck_timeshare_contracts_unit_capacity_valid",
        "timeshare_contracts",
        "unit_capacity IS NULL OR unit_capacity IN (2, 4, 6)",
    )

    # Backfill آمن: Studio = 2 دايمًا (استنتاج 100% مضمون، مفيش أي room_type
    # تاني بيتحول لـStudio). Chalet يفضل NULL — القديم اتفقد فعليًا (4R/6R
    # اندمجوا) ولا يوجد استنتاج آمن من البيانات الحالية لوحدها.
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE timeshare_contracts SET unit_capacity = 2 WHERE room_type = 'Studio' AND unit_capacity IS NULL"
    ))

    op.add_column("timeshare_visit_requests", sa.Column("alt_start_1", sa.Date(), nullable=True))
    op.add_column("timeshare_visit_requests", sa.Column("alt_end_1", sa.Date(), nullable=True))
    op.add_column("timeshare_visit_requests", sa.Column("alt_start_2", sa.Date(), nullable=True))
    op.add_column("timeshare_visit_requests", sa.Column("alt_end_2", sa.Date(), nullable=True))

    op.add_column(
        "timeshare_visit_requests",
        sa.Column("terms_version", sa.String(60), nullable=False, server_default=TIMESHARE_TERMS_VERSION),
    )
    op.add_column(
        "timeshare_visit_requests",
        sa.Column("terms_accepted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        "timeshare_visit_requests",
        sa.Column("booking_rules_version", sa.String(60), nullable=False, server_default=TIMESHARE_BOOKING_RULES_VERSION),
    )
    op.add_column(
        "timeshare_visit_requests",
        sa.Column("booking_rules_accepted_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    # السيرفر-ديفولت أعلاه بس لعمود موجود مسبقًا (طلبات تاريخية قبل الحقل
    # ده) — طلبات جديدة بتحدد القيمة صراحةً دايمًا عبر schemas الصارم.
    op.alter_column("timeshare_visit_requests", "terms_version", server_default=None)
    op.alter_column("timeshare_visit_requests", "terms_accepted_at", server_default=None)
    op.alter_column("timeshare_visit_requests", "booking_rules_version", server_default=None)
    op.alter_column("timeshare_visit_requests", "booking_rules_accepted_at", server_default=None)


def downgrade() -> None:
    op.drop_column("timeshare_visit_requests", "booking_rules_accepted_at")
    op.drop_column("timeshare_visit_requests", "booking_rules_version")
    op.drop_column("timeshare_visit_requests", "terms_accepted_at")
    op.drop_column("timeshare_visit_requests", "terms_version")
    op.drop_column("timeshare_visit_requests", "alt_end_2")
    op.drop_column("timeshare_visit_requests", "alt_start_2")
    op.drop_column("timeshare_visit_requests", "alt_end_1")
    op.drop_column("timeshare_visit_requests", "alt_start_1")

    op.drop_constraint("ck_timeshare_contracts_unit_capacity_valid", "timeshare_contracts", type_="check")
    op.drop_column("timeshare_contracts", "mailing_address")
    op.drop_column("timeshare_contracts", "customer_phone_home")
    op.drop_column("timeshare_contracts", "customer_phone_work")
    op.drop_column("timeshare_contracts", "beneficiary_name")
    op.drop_column("timeshare_contracts", "unit_capacity")
