"""app/modules/leasing/crud.py"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.modules.leasing.models import LeaseContract, LeasePayment, TenantCashLog
from app.modules.leasing.schemas import (
    LeaseContractCreate, LeaseContractUpdate, PayLeaseRequest, TenantCashLogCreate,
)
from app.resort_os.clock import scenario_utcnow
from app.resort_os.timezone_utils import local_today


def _next_contract_number(db: Session) -> str:
    """رقم العقد بيحمل تاريخ اليوم (LC-YYYYMMDD-NNNN) — لازم يكون تاريخ المنتجع
    (Africa/Cairo) مش تاريخ السيرفر (UTC غالبًا في الإنتاج)، وإلا عقد اتعمل
    الساعة 00:30 بتوقيت القاهرة كان هياخد رقم بتاريخ اليوم اللي فات (نفس فئة
    الباج الموثّقة في resort_os/timezone_utils.py)."""
    today = local_today(settings.TIMEZONE).strftime("%Y%m%d")
    count = db.query(LeaseContract).filter(
        LeaseContract.contract_number.like(f"LC-{today}-%")
    ).count()
    return f"LC-{today}-{count + 1:04d}"


def get_contract(db: Session, contract_id: int) -> Optional[LeaseContract]:
    return db.query(LeaseContract).filter(LeaseContract.id == contract_id).first()


def list_contracts(
    db: Session, branch_id: int,
    status: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0, limit: int = 50,
) -> tuple[list[LeaseContract], int]:
    q = db.query(LeaseContract).filter(LeaseContract.branch_id == branch_id)
    if status:
        q = q.filter(LeaseContract.status == status)
    if search:
        like = f"%{search}%"
        q = q.filter(
            LeaseContract.tenant_name.ilike(like) |
            LeaseContract.contract_number.ilike(like)
        )
    total = q.count()
    # ⚠️ باج N+1 حقيقي كان هنا (اتصلح 2026-07-28): LeaseContractRead.payments
    # بيتسريلايز من contract.payments (lazy="select") لكل عقد في القايمة —
    # صفحة من 20 عقد كانت بتولّد 20 استعلام إضافي بدل استعلام واحد.
    items = (
        q.options(selectinload(LeaseContract.payments))
        .order_by(LeaseContract.created_at.desc()).offset(skip).limit(limit).all()
    )
    return items, total


def get_tenant_aging(db: Session, branch_id: int, as_of: date) -> list[dict]:
    """رصيد مستحق (فعليًا واجب التحصيل، مش قيمة العقد المتبقية كلها) لكل عقد
    عنده دفعات وصل تاريخ استحقاقها ولسه مش متسددة بالكامل (pending/partial/
    overdue وdue_date <= as_of)، مقسّم لفئة تأخير حسب أقدم دفعة مستحقة —
    راجع OPS-DATA-02 §10.5: "أظهر aging للمستأجرين". دفعات مستقبلية لسه ما
    استحقتش عمدًا برّه الحساب — مش ذمة فعلية لحد ما تاريخ استحقاقها يجي."""
    contracts = (
        db.query(LeaseContract)
        .filter(LeaseContract.branch_id == branch_id)
        .options(selectinload(LeaseContract.payments))
        .all()
    )
    rows: list[dict] = []
    for c in contracts:
        open_payments = [
            p for p in c.payments
            if p.status in ("pending", "partial", "overdue") and p.due_date <= as_of
        ]
        if not open_payments:
            continue
        outstanding = sum((p.amount + p.penalty - p.paid_amount for p in open_payments), start=Decimal("0"))
        if outstanding <= 0:
            continue
        oldest_due = min(p.due_date for p in open_payments)
        days_overdue = max(0, (as_of - oldest_due).days)
        if days_overdue <= 0:
            bucket = "current"
        elif days_overdue <= 30:
            bucket = "1-30"
        elif days_overdue <= 60:
            bucket = "31-60"
        elif days_overdue <= 90:
            bucket = "61-90"
        else:
            bucket = "90+"
        rows.append({
            "contract_id": c.id, "contract_number": c.contract_number,
            "tenant_name": c.tenant_name, "outstanding": outstanding,
            "oldest_due_date": oldest_due, "days_overdue": days_overdue, "bucket": bucket,
        })
    rows.sort(key=lambda r: r["days_overdue"], reverse=True)
    return rows


def list_contracts_expiring_soon(
    db: Session, branch_id: int, today: date, within_days: int = 30,
) -> list[LeaseContract]:
    """عقود نشطة هتنتهي خلال `within_days` يوم القادمة (شامل النهاردة نفسه).

    wagdy.md بند #28: عقود الإيجار كانت بتنتهي من غير أي تنبيه — مدير الإيجارات
    كان بيكتشف الانتهاء بالصدفة بس. `today` لازم يتحسب بتوقيت المنتجع
    (استدعِ عبر `services.list_expiring_soon` اللي بيمرر `local_today()`، مش
    `date.today()` الخام هنا)."""
    horizon = today + timedelta(days=within_days)
    return (
        db.query(LeaseContract)
        .filter(
            LeaseContract.branch_id == branch_id,
            LeaseContract.status == "active",
            LeaseContract.end_date >= today,
            LeaseContract.end_date <= horizon,
        )
        .order_by(LeaseContract.end_date)
        .all()
    )


def create_contract(db: Session, data: LeaseContractCreate, signed_by: int) -> LeaseContract:
    contract = LeaseContract(
        **data.model_dump(),
        contract_number=_next_contract_number(db),
        signed_by=signed_by,
    )
    db.add(contract)
    db.flush()
    return contract


def update_contract(db: Session, contract: LeaseContract, data: LeaseContractUpdate) -> LeaseContract:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(contract, field, value)
    db.flush()
    return contract


def create_payments(db: Session, contract_id: int, schedule: list[dict]) -> list[LeasePayment]:
    objs = []
    for item in schedule:
        p = LeasePayment(
            contract_id=contract_id,
            due_date=item["due_date"],
            amount=item["amount"],
            year_n=item.get("year_n", 0),
        )
        db.add(p)
        objs.append(p)
    db.flush()
    return objs


def list_payments(db: Session, contract_id: int) -> list[LeasePayment]:
    return (
        db.query(LeasePayment)
        .filter(LeasePayment.contract_id == contract_id)
        .order_by(LeasePayment.due_date)
        .all()
    )


def get_payment(db: Session, payment_id: int) -> Optional[LeasePayment]:
    return db.query(LeasePayment).filter(LeasePayment.id == payment_id).first()


def list_unaccrued_due_payments(db: Session, branch_id: int, as_of: date) -> list[LeasePayment]:
    """دفعات إيجار وصل تاريخ استحقاقها (due_date <= as_of) ولسه ما
    اتحقّقتش محاسبيًا (accrued=False) — راجع services.accrue_due_rents."""
    return (
        db.query(LeasePayment)
        .join(LeaseContract, LeaseContract.id == LeasePayment.contract_id)
        .filter(
            LeaseContract.branch_id == branch_id,
            LeasePayment.due_date <= as_of,
            LeasePayment.accrued.is_(False),
        )
        .order_by(LeasePayment.due_date)
        .all()
    )


def lock_payment_for_update(db: Session, payment_id: int) -> Optional[LeasePayment]:
    """SELECT ... FOR UPDATE NOWAIT — باج حقيقي اتصلح (2026-07-28، مرآة نفس
    الباج في timeshare.crud.lock_installment_for_update): pay_payment كانت
    بتقرا/تعدّل paid_amount من غير أي قفل صف، فتحصيلين متزامنين على نفس
    القسط الإيجاري كانوا يمسحوا بعض بصمت."""
    return (
        db.query(LeasePayment)
        .filter(LeasePayment.id == payment_id)
        .with_for_update(nowait=True)
        .populate_existing()
        .first()
    )


def pay_payment(db: Session, payment: LeasePayment, req: PayLeaseRequest) -> LeasePayment:
    payment.paid_amount += req.paid_amount
    payment.payment_method = req.payment_method
    payment.receipt_number = req.receipt_number
    payment.notes = req.notes
    if payment.paid_amount >= payment.amount + payment.penalty:
        payment.status = "paid"
        # scenario_utcnow() (بديل datetime.utcnow()) — راجع resort_os/clock.py's
        # توثيق: باج حقيقي حي اتكشف (2026-08-10)، /analytics/revenue's فلترة
        # leasing بمدى يوليو كانت بترجع صفر رغم دفعات حقيقية، لأن paid_at كان
        # بيتسجّل بوقت تشغيل أداة HIST-01 الحقيقي مش تاريخ يوليو المحاكى.
        payment.paid_at = scenario_utcnow()
    else:
        payment.status = "partial"
    db.flush()
    return payment


# ── TenantCashLog ─────────────────────────────────────────────────────

def create_cash_log(db: Session, data: TenantCashLogCreate, recorded_by: int) -> TenantCashLog:
    log = TenantCashLog(**data.model_dump(), recorded_by=recorded_by)
    db.add(log)
    db.flush()
    return log


def list_cash_logs(db: Session, contract_id: int) -> list[TenantCashLog]:
    return (
        db.query(TenantCashLog)
        .filter(TenantCashLog.contract_id == contract_id)
        .order_by(TenantCashLog.created_at.desc())
        .all()
    )
