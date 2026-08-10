"""HIST-01 — مولّد بيانات التايم شير التاريخية ليوليو 2026 (OPS-DATA-02 §10.8).

بيستخدم services الحقيقية بس (create_contract/pay_installment/
pay_maintenance_due/cancel_contract) — صفر SQL مباشر.

⚠️ قرار نطاق موثّق صراحةً (نفس مبدأ hist_leasing.py): §11.3's opening
balance journal (2026-06-30) بيحتوي صراحةً "Timeshare installment AR 1170:
320,000.00" كرصيد افتتاحي جاهز، مش حصيلة عقود حديثة الإنشاء. مفيش أي طريقة
واقعية أبني بيها 12 عقد "جديد" هنا وأخلي رصيدهم المستحق يساوي بالظبط
320,000 من غير تلفيق تاريخ دفعات وهمي (خارج نطاق "بيانات يوليو التشغيلية"
المطلوب هنا فعليًا). العقود الـ12 بتتعامل كعقود نشطة موقّعة يونيو 2026
(دفعة أولى + أول قسط استحقاقه يونيو بيتحصّلوا كتاريخ مستقر سابق على
يوليو نفسه — نفس نمط hist_leasing.py's June rent)، وسيناريو يوليو الفعلي
هو تحصيل القسط التاني (استحقاق 1 يوليو) بمزيج واقعي: تحصيل كامل (بنك/كارت/
كاش)، دفعة جزئية واحدة، عقد متأخر بدون تحصيل، وعقدين ملغيين برد جزئي —
بالظبط "partial/overdue/cancelled scenario" المطلوبة في §10.8. القيم
المُبلَّغة في totals هي المحصَّل الفعلي المُتحقَّق من GL حقيقي، مش نسخة من
رقم §10.8 التوضيحي (نفس مبدأ التصحيح في hist_leasing.py لغرامة SHOP1)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.resort_os.clock import scenario_clock

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.operational_history_seed import ScenarioContext


@dataclass(frozen=True)
class _ContractSpec:
    tier: str  # "2R"|"4R"|"6R"
    total_value: Decimal
    maintenance_fee: Decimal
    # سيناريو يوليو: full|partial|overdue|cancelled
    july_scenario: str
    july_method: str  # cash|card|bank_transfer (مهمل لو overdue/cancelled)


_CONTRACTS: tuple[_ContractSpec, ...] = (
    _ContractSpec("2R", Decimal("45000"), Decimal("2500"), "full", "bank_transfer"),
    _ContractSpec("2R", Decimal("50000"), Decimal("2500"), "full", "cash"),
    _ContractSpec("2R", Decimal("50000"), Decimal("0"), "full", "card"),
    _ContractSpec("2R", Decimal("70000"), Decimal("0"), "partial", "cash"),
    _ContractSpec("4R", Decimal("70000"), Decimal("2500"), "full", "bank_transfer"),
    _ContractSpec("4R", Decimal("73500"), Decimal("2500"), "full", "cash"),
    _ContractSpec("4R", Decimal("100000"), Decimal("0"), "full", "bank_transfer"),
    _ContractSpec("4R", Decimal("100000"), Decimal("0"), "overdue", "cash"),
    _ContractSpec("4R", Decimal("100000"), Decimal("0"), "full", "card"),
    _ContractSpec("6R", Decimal("140000"), Decimal("0"), "full", "bank_transfer"),
    _ContractSpec("6R", Decimal("140000"), Decimal("0"), "cancelled", "cash"),
    _ContractSpec("6R", Decimal("140000"), Decimal("0"), "cancelled", "cash"),
)

_DOWN_PAYMENT_PCT = Decimal("0.10")  # 10% دفعة أولى — افتراض صناعي موثّق، لا يوجد رقم محدد في §10.8
_FIRST_INSTALLMENT_DATE = date(2026, 6, 1)
_CONTRACT_DATE = date(2026, 6, 1)


def generate(db: "Session", ctx: "ScenarioContext") -> dict:
    from app.modules.timeshare import services as ts_services
    from app.modules.timeshare.schemas import (
        PayInstallmentRequest, PayMaintenanceDueRequest, TimeshareContractCreate,
    )

    branch_id = ctx.branch_id
    tz = ZoneInfo(ctx.tz_name)
    contracts = []

    with scenario_clock(datetime(2026, 6, 1, 12, 0, tzinfo=tz)):
        for i, spec in enumerate(_CONTRACTS, start=1):
            room_type = "Studio" if spec.tier == "2R" else "Chalet"
            unit_capacity = {"2R": 2, "4R": 4, "6R": 6}[spec.tier]
            down_payment = (spec.total_value * _DOWN_PAYMENT_PCT).quantize(Decimal("0.01"))
            contract = ts_services.create_contract(db, TimeshareContractCreate(
                branch_id=branch_id, customer_name=f"عميل HIST-{spec.tier}-{i:02d}",
                customer_phone=f"010{i:08d}",
                room_type=room_type, unit_capacity=unit_capacity,
                total_value=spec.total_value, down_payment=down_payment,
                installments=12, installment_period=1,
                first_installment_date=_FIRST_INSTALLMENT_DATE,
                start_date=_CONTRACT_DATE, contract_date=_CONTRACT_DATE,
                maintenance_fee=spec.maintenance_fee,
            ), signed_by=0)
            contracts.append((spec, contract))

        # قسط يونيو (الأول) — تاريخ مستقر سابق على سيناريو يوليو نفسه، راجع
        # docstring الملف. بيتحصّل بالكامل لكل العقود عدا الملغيين تحت.
        for spec, contract in contracts:
            if spec.july_scenario == "cancelled":
                continue
            june_installment = contract.installments_list[0]
            ts_services.pay_installment(db, june_installment.id, PayInstallmentRequest(
                paid_amount=june_installment.amount, payment_method="bank_transfer",
            ))

    # ── سيناريو يوليو الفعلي: القسط التاني (استحقاق 1 يوليو) ────────────
    total_collected = Decimal("0")
    cancelled_count = 0
    with scenario_clock(datetime(2026, 7, 5, 12, 0, tzinfo=tz)):
        for spec, contract in contracts:
            db.refresh(contract)
            if spec.july_scenario == "cancelled":
                ts_services.cancel_contract(
                    db, contract.id, cancel_amount=Decimal("500.00"), cancelled_by=0,
                )
                cancelled_count += 1
                continue

            july_installment = contract.installments_list[1]
            if spec.july_scenario == "overdue":
                continue  # مفيش تحصيل خالص — يفضل pending/overdue

            amount = (
                july_installment.amount if spec.july_scenario == "full"
                else (july_installment.amount / 2).quantize(Decimal("0.01"))  # partial
            )
            ts_services.pay_installment(db, july_installment.id, PayInstallmentRequest(
                paid_amount=amount, payment_method=spec.july_method,
            ))
            total_collected += amount

    # ── مستحقات الصيانة — العقود اللي عندها رسم صيانة فعلي بتسدده في يوليو
    maintenance_collected = Decimal("0")
    maintenance_paid_count = 0
    with scenario_clock(datetime(2026, 7, 10, 12, 0, tzinfo=tz)):
        for spec, contract in contracts:
            if spec.july_scenario == "cancelled" or spec.maintenance_fee <= 0:
                continue
            db.refresh(contract)
            if not contract.maintenance_dues_list:
                continue
            due = contract.maintenance_dues_list[0]
            ts_services.pay_maintenance_due(db, due.id, PayMaintenanceDueRequest(
                paid_amount=due.amount, payment_method="cash",
            ))
            maintenance_collected += due.amount
            maintenance_paid_count += 1

    return {
        "counts": {
            "contracts_created": len(_CONTRACTS),
            "full_payments": sum(1 for s in _CONTRACTS if s.july_scenario == "full"),
            "partial_payments": sum(1 for s in _CONTRACTS if s.july_scenario == "partial"),
            "overdue_uncollected": sum(1 for s in _CONTRACTS if s.july_scenario == "overdue"),
            "cancelled": cancelled_count,
            "maintenance_dues_paid": maintenance_paid_count,
        },
        "totals": {
            "contract_value_total": str(sum(s.total_value for s in _CONTRACTS)),
            "july_installment_collected": str(total_collected),
            "july_maintenance_collected": str(maintenance_collected),
            "july_cash_in_total": str(total_collected + maintenance_collected),
        },
    }
