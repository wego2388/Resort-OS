"""Guest review replay guard — one review per booking/visit

Revision ID: 6449668eb81a
Revises: 45aabf472620
Create Date: 2026-08-30

Additive, forward-only.

مراجعة Codex المستقلة قبل الإطلاق (2026-08-30، M-03): survey token
(GET /analytics/reviews/survey-token/{booking_id} أو .../timeshare/{visit_id})
صالح 7 أيام ومفيش أي تتبع "تم استهلاكه" — نفس اللينك كان يقدر يتبعت
POST /analytics/reviews/submit عدد غير محدود من المرات، كل مرة بينشئ صف
GuestReview جديد (ولو التقييم ≤2، Activity شكوى جديدة في CRM كل مرة كمان).

الحل: partial unique index على guest_reviews.booking_id (WHERE NOT NULL)
وعلى guest_reviews.timeshare_visit_id (WHERE NOT NULL) — أقصى تقييم واحد
لكل حجز/زيارة، بغض النظر عن عدد مرات إرسال نفس اللينك. services.submit_review
بيمسك IntegrityError ويرفعها كـValueError واضح ("تم تسجيل تقييم لهذا
المرجع من قبل") بدل خطأ DB خام.

كل صف guest_reviews حالي (لو موجود) بيتوقع صف واحد بس لكل booking_id/
timeshare_visit_id فعليًا (الميزة نفسها حديثة نسبيًا ومفيش مسار تاني كان
بيكتب فيها) — مفيش preflight duplicate-check هنا، لو فشل CREATE UNIQUE
INDEX يبان فورًا وقت upgrade، مش بصمت.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "6449668eb81a"
down_revision = "45aabf472620"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_guest_review_booking", "guest_reviews", ["booking_id"], unique=True,
        postgresql_where=sa.text("booking_id IS NOT NULL"),
        sqlite_where=sa.text("booking_id IS NOT NULL"),
    )
    op.create_index(
        "uq_guest_review_timeshare_visit", "guest_reviews", ["timeshare_visit_id"], unique=True,
        postgresql_where=sa.text("timeshare_visit_id IS NOT NULL"),
        sqlite_where=sa.text("timeshare_visit_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_guest_review_timeshare_visit", table_name="guest_reviews")
    op.drop_index("uq_guest_review_booking", table_name="guest_reviews")
