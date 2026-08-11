"""HIST-01 — مولّد بيانات الإيجارات التاريخية ليوليو 2026 (OPS-DATA-02 §10.5).

بيستخدم services الحقيقية بس (create_contract/confirm_deposit_received/
pay_payment/apply_penalties/accrue_due_rents — كلهم من المرحلة 6، اللي
صححت محاسبة الإيجار بالكامل: accrual عند الاستحقاق، تأمين عند الاستلام
الفعلي بس، وطريقة الدفع الحقيقية بدل 1100 لكل الحالات). صفر SQL مباشر.

⚠️ قرار موثّق صراحةً: §10.5 بيقول "18,000 +360 غرامة يوم 15" افتراضًا إن
الغرامة 2% ثابتة (نفس افتراض الفقرة التمهيدية "غرامة 2% مرة واحدة"). لكن
المحرك الفعلي المُقفَل في الكود (`resort_os.timeshare_engine.
calculate_lease_penalty`، مُتحقَّق منه ومُختبَر من قبل هذه الجلسة) بيطبّق
شرائح 5%/10% (8-30 يوم تأخير = 5%، أكتر من 30 = 10%)، مش 2% ثابتة أبدًا.
دفعة SHOP1 بتتأخر 14 يوم (استحقاق يوم 1، تسديد يوم 15) → شريحة 5% فعليًا
= 900.00، مش 360.00. اتبع نفس مبدأ التصحيحات في TIMESHARE-01R (المرحلة 5):
المنطق التجاري المُقفَل الفعلي في الكود يفوز على رقم توضيحي في خطة/بريف
مرجعي، مش العكس. المولّد هنا بيحسب الغرامة من المحرك الحقيقي فعليًا (مش
رقم مكتوب يدويًا)، فأي تغيير مستقبلي في سياسة الغرامة بينعكس هنا تلقائيًا
بدل ما يفضل الرقم القديم عالق.

عقود الإيجار "نشطة من 2026-06-01" (§10.5 الفقرة التمهيدية) — يعني قسط
يونيو مستحق قبل بداية يوليو أصلًا. بيتحصّل هنا كتاريخ مستقر سابق (جزء من
إعداد العقد الواقعي، مش "سيناريو يوليو" نفسه) قبل ما نبدأ في معالجة عمود
يوليو الفعلي من الجدول.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

from app.resort_os.clock import scenario_clock

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.operational_history_seed import ScenarioContext


@dataclass(frozen=True)
class _ContractSpec:
    code: str
    tenant_name: str
    unit_description: str
    monthly_rent: Decimal
    security_deposit: Decimal
    deposit_method: str
    # July collection — إما دفعة واحدة، أو تقسيم على أكتر من طريقة دفع، أو
    # None لعقد يتسدّدش خالص في يوليو (SHOP2، overdue في 31 يوليو).
    july_payment_day: Optional[int]
    july_splits: tuple[tuple[str, Decimal], ...]  # (payment_method, amount)


_CONTRACTS: tuple[_ContractSpec, ...] = (
    _ContractSpec(
        code="HIST-LSE-DIVE-01", tenant_name="مركز الغوص", unit_description="منطقة مركز الغوص",
        monthly_rent=Decimal("45000"), security_deposit=Decimal("90000"), deposit_method="bank_transfer",
        july_payment_day=1, july_splits=(("bank_transfer", Decimal("45000")),),
    ),
    _ContractSpec(
        code="HIST-LSE-WATER-01", tenant_name="مركز الرياضات المائية", unit_description="منطقة الرياضات المائية",
        monthly_rent=Decimal("35000"), security_deposit=Decimal("70000"), deposit_method="bank_transfer",
        july_payment_day=4, july_splits=(("bank_transfer", Decimal("35000")),),
    ),
    _ContractSpec(
        code="HIST-LSE-SPA-01", tenant_name="وحدة السبا والمساج", unit_description="وحدة السبا",
        monthly_rent=Decimal("25000"), security_deposit=Decimal("50000"), deposit_method="bank_transfer",
        july_payment_day=1, july_splits=(("bank_transfer", Decimal("15000")), ("cash", Decimal("10000"))),
    ),
    _ContractSpec(
        code="HIST-LSE-SHOP-01", tenant_name="متجر مستلزمات بحر", unit_description="كشك مستلزمات بحر",
        monthly_rent=Decimal("18000"), security_deposit=Decimal("36000"), deposit_method="cash",
        july_payment_day=15, july_splits=(),  # المبلغ (إيجار+غرامة فعلية) بيتحسب وقت التنفيذ
    ),
    _ContractSpec(
        code="HIST-LSE-SHOP-02", tenant_name="بقالة الشاطئ", unit_description="كشك بقالة شاطئ",
        monthly_rent=Decimal("15000"), security_deposit=Decimal("30000"), deposit_method="bank_transfer",
        july_payment_day=None, july_splits=(),  # overdue في 31 يوليو — مفيش تحصيل خالص
    ),
)

_CONTRACT_START = date(2026, 6, 1)
_CONTRACT_END = date(2027, 5, 31)


def generate(db: "Session", ctx: "ScenarioContext") -> dict:
    from app.modules.leasing import crud as leasing_crud, services as leasing_services
    from app.modules.leasing.schemas import LeaseContractCreate, PayLeaseRequest

    branch_id = ctx.branch_id
    tz = ZoneInfo(ctx.tz_name)
    contracts: dict[str, "leasing_crud.LeaseContract"] = {}

    # ── 1) إنشاء العقود + تأكيد استلام التأمين + تسديد قسط يونيو (تاريخ
    # مستقر سابق على يوليو — راجع docstring الملف) — كله بتاريخ 30 يونيو.
    with scenario_clock(datetime(2026, 6, 30, 12, 0, tzinfo=tz)):
        for spec in _CONTRACTS:
            contract = leasing_services.create_contract(db, LeaseContractCreate(
                branch_id=branch_id, tenant_name=spec.tenant_name,
                unit_description=spec.unit_description,
                start_date=_CONTRACT_START, end_date=_CONTRACT_END,
                base_rent=spec.monthly_rent, billing_day=1,
                security_deposit=spec.security_deposit,
                notes=spec.code,
            ), signed_by=ctx.actor_id)
            leasing_services.confirm_deposit_received(
                db, contract.id, spec.deposit_method,
                received_by=ctx.actor_id, enforce_cash_shift=False,
            )
            contracts[spec.code] = contract

        for spec in _CONTRACTS:
            payments = leasing_crud.list_payments(db, contracts[spec.code].id)
            june_payment = payments[0]
            leasing_services.pay_payment(db, june_payment.id, PayLeaseRequest(
                paid_amount=june_payment.amount, payment_method="bank_transfer",
            ), collected_by=ctx.actor_id, enforce_cash_shift=False)

    # ── 2) عمود "سيناريو يوليو" الفعلي من §10.5 — كل عقد بتاريخه الحقيقي.
    penalty_details: dict[str, Decimal] = {}
    for spec in _CONTRACTS:
        contract = contracts[spec.code]
        payments = leasing_crud.list_payments(db, contract.id)
        july_payment = payments[1]

        if spec.july_payment_day is None:
            continue  # SHOP2 — مفيش تحصيل، هيتعالج تحت (accrual + overdue)

        with scenario_clock(datetime(2026, 7, spec.july_payment_day, 12, 0, tzinfo=tz)):
            if spec.july_splits:
                for method, amount in spec.july_splits:
                    leasing_services.pay_payment(db, july_payment.id, PayLeaseRequest(
                        paid_amount=amount, payment_method=method,
                    ), collected_by=ctx.actor_id, enforce_cash_shift=False)
            else:
                # SHOP1 — لازم تطبيق الغرامة الفعلية (المحرك الحقيقي، مش
                # رقم افتراضي — راجع docstring الملف) قبل تحديد المبلغ الكامل.
                leasing_services.apply_penalties(db, contract.id)
                db.refresh(july_payment)
                penalty_details[spec.code] = july_payment.penalty
                total_due = july_payment.amount + july_payment.penalty - july_payment.paid_amount
                leasing_services.pay_payment(db, july_payment.id, PayLeaseRequest(
                    paid_amount=total_due, payment_method="cash",
                ), collected_by=ctx.actor_id, enforce_cash_shift=False)

    # ── 3) SHOP2: يتحقق (accrue) عند الاستحقاق زي أي عقد، لكن يفضل غير
    # مسدد ويتحدد overdue بغرامته الفعلية في 31 يوليو (نفس اللي
    # leasing_tasks.mark_overdue هيعمله يوميًا في الإنتاج الحقيقي).
    with scenario_clock(datetime(2026, 7, 31, 20, 0, tzinfo=tz)):
        leasing_services.accrue_due_rents(db, branch_id, date(2026, 7, 31))
        shop2_updated = leasing_services.apply_penalties(db, contracts["HIST-LSE-SHOP-02"].id)
        if shop2_updated:
            penalty_details["HIST-LSE-SHOP-02"] = shop2_updated[0].penalty

    total_collected = sum(
        sum(amount for _, amount in spec.july_splits) for spec in _CONTRACTS if spec.july_splits
    )
    if "HIST-LSE-SHOP-01" in penalty_details:
        total_collected += Decimal("18000") + penalty_details["HIST-LSE-SHOP-01"]

    return {
        "counts": {
            "contracts_created": len(_CONTRACTS),
            "deposits_confirmed": len(_CONTRACTS),
            "july_payments_collected": sum(1 for s in _CONTRACTS if s.july_payment_day is not None),
            "overdue_uncollected": sum(1 for s in _CONTRACTS if s.july_payment_day is None),
        },
        "totals": {
            "monthly_rent_total": str(sum(s.monthly_rent for s in _CONTRACTS)),
            "security_deposit_total": str(sum(s.security_deposit for s in _CONTRACTS)),
            "july_collected_total": str(total_collected),
            "tenant_ar_outstanding": str(Decimal("15000")),  # HIST-LSE-SHOP-02
            "shop1_penalty_applied": str(penalty_details.get("HIST-LSE-SHOP-01", Decimal("0"))),
        },
    }
