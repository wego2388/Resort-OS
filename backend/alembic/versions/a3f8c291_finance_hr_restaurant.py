"""finance_hr_restaurant_tables

Revision ID: a3f8c291
Revises: 47f5f348
Create Date: 2026-06-30 09:10:00

Tables: conditional_discounts, folios, folio_charges, payments,
        employees, social_insurance_configs, tax_bracket_configs,
        employee_allowances, payroll_runs, payroll_lines,
        attendance_records, leave_balances,
        menu_categories, menu_items, dining_tables, orders, order_items
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision      = "a3f8c291"
down_revision = "47f5f348"
branch_labels = None
depends_on    = None


def upgrade() -> None:

    # ── Finance ───────────────────────────────────────────────────────
    op.create_table(
        "conditional_discounts",
        sa.Column("id",              sa.Integer(),     nullable=False),
        sa.Column("branch_id",       sa.Integer(),     nullable=False),
        sa.Column("condition_type",  sa.String(40),    nullable=False),
        sa.Column("condition_value", sa.String(100),   nullable=False),
        sa.Column("discount_type",   sa.String(30),    nullable=False),
        sa.Column("discount_value",  sa.Numeric(10,2), nullable=False),
        sa.Column("max_uses",        sa.Integer(),     nullable=False, server_default="-1"),
        sa.Column("uses_count",      sa.Integer(),     nullable=False, server_default="0"),
        sa.Column("valid_from",      sa.Date(),        nullable=False),
        sa.Column("valid_until",     sa.Date(),        nullable=False),
        sa.Column("priority",        sa.Integer(),     nullable=False, server_default="1"),
        sa.Column("is_active",       sa.Boolean(),     nullable=False, server_default="true"),
        sa.Column("created_at",      sa.DateTime(),    nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(),    nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discounts_branch_active", "conditional_discounts", ["branch_id", "is_active"])

    op.create_table(
        "folios",
        sa.Column("id",         sa.Integer(),      nullable=False),
        sa.Column("branch_id",  sa.Integer(),      nullable=False),
        sa.Column("guest_name", sa.String(200),    nullable=False),
        sa.Column("check_in",   sa.DateTime(),     nullable=False),
        sa.Column("check_out",  sa.DateTime(),     nullable=False),
        sa.Column("status",     sa.String(20),     nullable=False, server_default="open"),
        sa.Column("total",      sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_folios_branch_status", "folios", ["branch_id", "status"])

    op.create_table(
        "folio_charges",
        sa.Column("id",              sa.Integer(),      nullable=False),
        sa.Column("folio_id",        sa.Integer(),      nullable=False),
        sa.Column("charge_type",     sa.String(30),     nullable=False),
        sa.Column("description",     sa.String(300),    nullable=False),
        sa.Column("amount",          sa.Numeric(10, 2), nullable=False),
        sa.Column("vat_amount",      sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("posted_at",       sa.DateTime(),     nullable=False),
        sa.Column("is_settled",      sa.Boolean(),      nullable=False, server_default="false"),
        sa.Column("ref_order_id",    sa.Integer(),      nullable=True),
        sa.Column("ref_beach_tx_id", sa.Integer(),      nullable=True),
        sa.Column("created_at",      sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["folio_id"], ["folios.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_folio_charges_folio", "folio_charges", ["folio_id"])

    op.create_table(
        "payments",
        sa.Column("id",         sa.Integer(),      nullable=False),
        sa.Column("folio_id",   sa.Integer(),      nullable=False),
        sa.Column("branch_id",  sa.Integer(),      nullable=False),
        sa.Column("amount",     sa.Numeric(10, 2), nullable=False),
        sa.Column("method",     sa.String(30),     nullable=False),
        sa.Column("reference",  sa.String(100),    nullable=True),
        sa.Column("notes",      sa.String(500),    nullable=True),
        sa.Column("posted_at",  sa.DateTime(),     nullable=False),
        sa.Column("voided_at",  sa.DateTime(),     nullable=True),
        sa.Column("voided_by",  sa.Integer(),      nullable=True),
        sa.Column("created_at", sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["folio_id"],  ["folios.id"],   ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── HR ────────────────────────────────────────────────────────────
    op.create_table(
        "employees",
        sa.Column("id",            sa.Integer(),      nullable=False),
        sa.Column("branch_id",     sa.Integer(),      nullable=False),
        sa.Column("employee_code", sa.String(20),     nullable=False),
        sa.Column("full_name",     sa.String(200),    nullable=False),
        sa.Column("national_id",   sa.String(20),     nullable=True),
        sa.Column("position",      sa.String(100),    nullable=False),
        sa.Column("department",    sa.String(100),    nullable=True),
        sa.Column("basic_salary",  sa.Numeric(10, 2), nullable=False),
        sa.Column("hire_date",     sa.Date(),         nullable=False),
        sa.Column("birth_date",    sa.Date(),         nullable=True),
        sa.Column("status",        sa.String(20),     nullable=False, server_default="active"),
        sa.Column("phone",         sa.String(20),     nullable=True),
        sa.Column("email",         sa.String(100),    nullable=True),
        sa.Column("created_at",    sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",    sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_code"),
    )

    op.create_table(
        "social_insurance_configs",
        sa.Column("id",                        sa.Integer(),      nullable=False),
        sa.Column("max_insurable_salary",      sa.Numeric(10, 2), nullable=False),
        sa.Column("employee_rate",             sa.Numeric(5, 4),  nullable=False),
        sa.Column("employer_rate",             sa.Numeric(5, 4),  nullable=False),
        sa.Column("personal_exemption_annual", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_penalty_days_monthly",  sa.Integer(),      nullable=False, server_default="5"),
        sa.Column("effective_from",            sa.Date(),         nullable=False),
        sa.Column("is_active",                 sa.Boolean(),      nullable=False, server_default="true"),
        sa.Column("created_at",                sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",                sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "tax_bracket_configs",
        sa.Column("id",             sa.Integer(),      nullable=False),
        sa.Column("lower_bound",    sa.Numeric(12, 2), nullable=False),
        sa.Column("upper_bound",    sa.Numeric(12, 2), nullable=True),
        sa.Column("rate",           sa.Numeric(5, 4),  nullable=False),
        sa.Column("effective_from", sa.Date(),         nullable=False),
        sa.Column("is_active",      sa.Boolean(),      nullable=False, server_default="true"),
        sa.Column("created_at",     sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",     sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "employee_allowances",
        sa.Column("id",             sa.Integer(),      nullable=False),
        sa.Column("employee_id",    sa.Integer(),      nullable=False),
        sa.Column("name",           sa.String(100),    nullable=False),
        sa.Column("amount",         sa.Numeric(10, 2), nullable=False),
        sa.Column("is_taxable",     sa.Boolean(),      nullable=False),
        sa.Column("is_pensionable", sa.Boolean(),      nullable=False),
        sa.Column("is_active",      sa.Boolean(),      nullable=False, server_default="true"),
        sa.Column("created_at",     sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",     sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "payroll_runs",
        sa.Column("id",           sa.Integer(),      nullable=False),
        sa.Column("branch_id",    sa.Integer(),      nullable=False),
        sa.Column("period_year",  sa.Integer(),      nullable=False),
        sa.Column("period_month", sa.Integer(),      nullable=False),
        sa.Column("status",       sa.String(20),     nullable=False, server_default="draft"),
        sa.Column("total_gross",  sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_net",    sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_tax",    sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_si",     sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("approved_by",  sa.Integer(),      nullable=True),
        sa.Column("approved_at",  sa.DateTime(),     nullable=True),
        sa.Column("created_at",   sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",   sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", "period_year", "period_month", name="uq_payroll_period"),
    )

    op.create_table(
        "payroll_lines",
        sa.Column("id",                     sa.Integer(),      nullable=False),
        sa.Column("payroll_run_id",         sa.Integer(),      nullable=False),
        sa.Column("employee_id",            sa.Integer(),      nullable=False),
        sa.Column("basic_salary",           sa.Numeric(10, 2), nullable=False),
        sa.Column("gross_salary",           sa.Numeric(10, 2), nullable=False),
        sa.Column("net_salary",             sa.Numeric(10, 2), nullable=False),
        sa.Column("employee_si",            sa.Numeric(10, 2), nullable=False),
        sa.Column("employer_si",            sa.Numeric(10, 2), nullable=False),
        sa.Column("monthly_tax",            sa.Numeric(10, 2), nullable=False),
        sa.Column("penalty_deduction",      sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("unpaid_leave_deduction", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("journal_entry",          sa.Text(),         nullable=True),
        sa.Column("created_at",             sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",             sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["payroll_run_id"], ["payroll_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"],    ["employees.id"],    ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "attendance_records",
        sa.Column("id",          sa.Integer(),  nullable=False),
        sa.Column("employee_id", sa.Integer(),  nullable=False),
        sa.Column("branch_id",   sa.Integer(),  nullable=False),
        sa.Column("record_date", sa.Date(),     nullable=False),
        sa.Column("check_in",    sa.DateTime(), nullable=True),
        sa.Column("check_out",   sa.DateTime(), nullable=True),
        sa.Column("status",      sa.String(20), nullable=False, server_default="present"),
        sa.Column("notes",       sa.String(300),nullable=True),
        sa.Column("created_at",  sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"],   ["branches.id"],  ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "record_date", name="uq_attendance_employee_date"),
    )
    op.create_index("ix_attendance_date", "attendance_records", ["record_date"])

    op.create_table(
        "leave_balances",
        sa.Column("id",              sa.Integer(), nullable=False),
        sa.Column("employee_id",     sa.Integer(), nullable=False),
        sa.Column("year",            sa.Integer(), nullable=False),
        sa.Column("annual_entitled", sa.Integer(), nullable=False),
        sa.Column("annual_taken",    sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sick_taken",      sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at",      sa.DateTime(),nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",      sa.DateTime(),nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "year", name="uq_leave_employee_year"),
    )

    # ── Restaurant ────────────────────────────────────────────────────
    op.create_table(
        "menu_categories",
        sa.Column("id",         sa.Integer(),  nullable=False),
        sa.Column("branch_id",  sa.Integer(),  nullable=False),
        sa.Column("name",       sa.String(100),nullable=False),
        sa.Column("name_ar",    sa.String(100),nullable=True),
        sa.Column("sort_order", sa.Integer(),  nullable=False, server_default="0"),
        sa.Column("is_active",  sa.Boolean(),  nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "menu_items",
        sa.Column("id",                   sa.Integer(),      nullable=False),
        sa.Column("branch_id",            sa.Integer(),      nullable=False),
        sa.Column("category_id",          sa.Integer(),      nullable=True),
        sa.Column("name",                 sa.String(200),    nullable=False),
        sa.Column("name_ar",              sa.String(200),    nullable=True),
        sa.Column("price",                sa.Numeric(10, 2), nullable=False),
        sa.Column("cost",                 sa.Numeric(10, 2), nullable=True),
        sa.Column("is_available",         sa.Boolean(),      nullable=False, server_default="true"),
        sa.Column("preparation_minutes",  sa.Integer(),      nullable=False, server_default="10"),
        sa.Column("image_url",            sa.String(500),    nullable=True),
        sa.Column("created_at",           sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",           sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"],   ["branches.id"],         ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["menu_categories.id"],  ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "dining_tables",
        sa.Column("id",           sa.Integer(),  nullable=False),
        sa.Column("branch_id",    sa.Integer(),  nullable=False),
        sa.Column("table_number", sa.String(20), nullable=False),
        sa.Column("capacity",     sa.Integer(),  nullable=False, server_default="4"),
        sa.Column("status",       sa.String(30), nullable=False, server_default="available"),
        sa.Column("section",      sa.String(50), nullable=True),
        sa.Column("created_at",   sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",   sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "orders",
        sa.Column("id",                       sa.Integer(),      nullable=False),
        sa.Column("branch_id",                sa.Integer(),      nullable=False),
        sa.Column("table_id",                 sa.Integer(),      nullable=True),
        sa.Column("order_number",             sa.String(30),     nullable=False),
        sa.Column("status",                   sa.String(30),     nullable=False, server_default="open"),
        sa.Column("order_type",               sa.String(30),     nullable=False, server_default="dine_in"),
        sa.Column("subtotal",                 sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("vat_amount",               sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("service_charge",           sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("discount_amount",          sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("total",                    sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("guests_count",             sa.Integer(),      nullable=False, server_default="1"),
        sa.Column("notes",                    sa.String(500),    nullable=True),
        sa.Column("waiter_id",                sa.Integer(),      nullable=True),
        sa.Column("folio_id",                 sa.Integer(),      nullable=True),
        sa.Column("applied_discount_rule_id", sa.Integer(),      nullable=True),
        sa.Column("created_at",               sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",               sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"],      ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["table_id"],  ["dining_tables.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number"),
    )
    op.create_index("ix_orders_branch_status", "orders", ["branch_id", "status"])

    op.create_table(
        "order_items",
        sa.Column("id",           sa.Integer(),      nullable=False),
        sa.Column("order_id",     sa.Integer(),      nullable=False),
        sa.Column("menu_item_id", sa.Integer(),      nullable=False),
        sa.Column("name",         sa.String(200),    nullable=False),
        sa.Column("unit_price",   sa.Numeric(10, 2), nullable=False),
        sa.Column("quantity",     sa.Integer(),      nullable=False, server_default="1"),
        sa.Column("notes",        sa.String(200),    nullable=True),
        sa.Column("status",       sa.String(20),     nullable=False, server_default="pending"),
        sa.Column("created_at",   sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at",   sa.DateTime(),     nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["order_id"],     ["orders.id"],     ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["menu_item_id"], ["menu_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("dining_tables")
    op.drop_table("menu_items")
    op.drop_table("menu_categories")
    op.drop_table("leave_balances")
    op.drop_table("attendance_records")
    op.drop_table("payroll_lines")
    op.drop_table("payroll_runs")
    op.drop_table("employee_allowances")
    op.drop_table("tax_bracket_configs")
    op.drop_table("social_insurance_configs")
    op.drop_table("employees")
    op.drop_table("payments")
    op.drop_table("folio_charges")
    op.drop_table("folios")
    op.drop_table("conditional_discounts")
