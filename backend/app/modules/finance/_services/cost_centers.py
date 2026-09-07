"""
app/modules/finance/_services/cost_centers.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.finance import crud
from app.modules.finance.models import CostCenter
from app.modules.finance.schemas import (
    CostCenterCreate,
    CostCenterReport,
    CostCenterReportLine,
)


DEFAULT_COST_CENTERS = [
    {"code": "ROOM",  "name": "الفندق / الغرف"},
    {"code": "REST",  "name": "المطعم"},
    {"code": "CAFE",  "name": "الكافيه"},
    {"code": "BEACH", "name": "الشاطئ"},
    {"code": "TS",    "name": "الملكية الجزئية"},
    # OPS-DATA-02 §11.1
    {"code": "LEASE", "name": "الإيجارات"},
    {"code": "MAINT", "name": "الصيانة"},
    {"code": "ADMIN", "name": "الإدارة"},
]


def ensure_default_cost_centers(db: Session, branch_id: int, *, commit: bool = True) -> list[CostCenter]:
    """يزرع مراكز التكلفة الافتراضية أول مرة بس — idempotent زي seed.py.

    commit=False (Gate 1B، مسارات strict الصارمة زي دفع طلبات الدايننج):
    الزرع بيحصل بـflush بس، من غير commit مستقل — عشان مسار الدفع الصارم
    يفضل بـcommit واحد بس لكل الـtransaction، بدل ما تجهيز مركز تكلفة
    ناقص يعمل commit نص-الطريق قبل ما باقي القيد يترحّل. commit=True
    (الافتراضي) هو نفس السلوك القديم تمامًا لكل الاستدعاءات الحالية."""
    existing_codes = {c.code for c in crud.list_cost_centers(db, branch_id, active_only=False)}
    created_any = False
    for defn in DEFAULT_COST_CENTERS:
        if defn["code"] not in existing_codes:
            crud.create_cost_center(db, CostCenterCreate(branch_id=branch_id, **defn))
            created_any = True
    if created_any:
        if commit:
            db.commit()
        else:
            db.flush()
    return crud.list_cost_centers(db, branch_id, active_only=False)


def get_cost_center_report(db: Session, branch_id: int, date_from: date, date_to: date) -> CostCenterReport:
    """تقرير مركز التكلفة (الفندق/المطعم/الكافيه/الشاطئ/الملكية الجزئية) — إيراد
    *ومصروف* كل واحد سطر منفصل، الاتنين من journal_lines.cost_center_id
    مباشرة (Batch 3) — مش استنتاج بعدي من جداول عمليات منفصلة (folio_charges/
    beach_transactions) زي قبل كده. الوسم بيحصل وقت الترحيل نفسه (راجع
    post_simple_revenue_journal's cost_center_code وكل نقاط الترحيل في
    dining/beach/pms/timeshare/inventory.services).

    ⚠️ قيود قديمة اتُرحّلت قبل هذه الدفعة مالهاش cost_center_id (NULL) —
    مفيش backfill رجعي هنا (قرار نطاق موثّق في CostCenterReport docstring)،
    فتقرير على مدى قبل تاريخ الدفعة دي هيورّي أرقام أقل من الحقيقة الفعلية
    حتى تتراكم قيود جديدة موسومة."""
    centers = ensure_default_cost_centers(db, branch_id)
    sums = crud.sum_journal_lines_by_cost_center(db, branch_id, date_from, date_to)

    lines = [
        CostCenterReportLine(
            code=c.code, name=c.name,
            revenue=sums.get(c.id, {}).get("revenue", Decimal("0")),
            expense=sums.get(c.id, {}).get("expense", Decimal("0")),
            net=sums.get(c.id, {}).get("revenue", Decimal("0")) - sums.get(c.id, {}).get("expense", Decimal("0")),
        )
        for c in centers
    ]
    total_revenue = sum((ln.revenue for ln in lines), Decimal("0"))
    total_expense = sum((ln.expense for ln in lines), Decimal("0"))

    return CostCenterReport(
        branch_id=branch_id, date_from=date_from, date_to=date_to,
        lines=lines, total_revenue=total_revenue, total_expense=total_expense,
        total_net=total_revenue - total_expense,
    )


# ── Financial Reports ────────────────────────────────────────────────
# ملاحظة محاسبية: بما إن post_journal_entry() بيرفض أي قيد غير متزن (debit
# != credit)، فإجمالي المدين = إجمالي الدائن على مستوى دفتر اليومية كله
# بالضرورة — وده اللي بيخلي trial balance وbalance sheet بيوازنوا تلقائياً
# من غير ما نحتاج قيد "إقفال" فعلي لنقل الأرباح لحساب حقوق ملكية.
