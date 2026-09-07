"""
app/modules/finance/_services/depreciation.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.modules.finance import crud
from app.modules.finance.schemas import (
    AssetDepreciationEntryRead,
    DepreciationRunResult,
    JournalEntryCreate,
    JournalLineCreate,
)
from app.modules.finance._services.posting import (
    validate_period_open,
    post_journal_entry,
)


# نطاق مقصود: خطي (straight-line) بس — أكتر طريقة إهلاك استخدامًا وأبسطها
# للمراجعة، وكافية لأصول منتجع حقيقي (تكييف/معدات مطبخ/أثاث/عربيات). أي
# طريقة تانية (متناقصة/وحدات إنتاج) ممكن تتضاف لاحقًا لو ظهرت حاجة تشغيلية.

DEPRECIATION_EXPENSE_ACCOUNT_CODE = "5500"
ACCUMULATED_DEPRECIATION_ACCOUNT_CODE = "1590"


def _get_or_create_account(db: Session, branch_id: int, code: str, name: str, account_type: str):
    """حسابات الإهلاك (مصروف/مجمّع) داخلية للنظام — بتتنشئ تلقائيًا أول مرة
    تُستخدم بدل ما تفشل الدورة كلها لمجرد إن حد نسي يضيفها لدليل الحسابات."""
    from app.modules.finance.models import Account  # noqa: PLC0415
    account = crud.get_account_by_code(db, branch_id, code)
    if account:
        return account
    account = Account(branch_id=branch_id, code=code, name=name, account_type=account_type, is_active=True)
    db.add(account)
    db.flush()
    return account


def run_depreciation(db: Session, branch_id: int, year: int, month: int, user_id: int) -> DepreciationRunResult:
    """يشغّل دورة إهلاك خطي شهرية لكل الأصول المؤهّلة في الفرع (عندها
    purchase_cost + useful_life_years وحالتها مش disposed)، ويرحّل قيد يومية
    واحد مجمّع (Dr. مصروف إهلاك / Cr. مجمّع إهلاك) لإجمالي المبلغ.

    Idempotent فعليًا: UniqueConstraint(asset_id, year, month) في
    AssetDepreciationEntry يمنع ترحيل نفس الأصل لنفس الشهر مرتين — إعادة
    تشغيل الدورة نفسها بأمان بترحّل بس الأصول اللي لسه ماترحّلتش."""
    import calendar  # noqa: PLC0415
    from app.modules.finance.models import AssetDepreciationEntry  # noqa: PLC0415

    last_day = calendar.monthrange(year, month)[1]
    period_end = date(year, month, last_day)
    validate_period_open(db, branch_id, period_end)

    assets = crud.get_depreciable_assets(db, branch_id)
    created_entries: list[AssetDepreciationEntry] = []
    skipped: list[str] = []
    total_amount = Decimal("0")

    for asset in assets:
        if asset.depreciation_start_date and asset.depreciation_start_date > period_end:
            skipped.append(f"{asset.code} — لسه ماجاش تاريخ بداية الإهلاك")
            continue
        if crud.get_depreciation_entry_for_period(db, asset.id, year, month):
            skipped.append(f"{asset.code} — اترحّل الشهر ده قبل كده")
            continue

        depreciable_base = (asset.purchase_cost or Decimal("0")) - (asset.salvage_value or Decimal("0"))
        if depreciable_base <= 0 or not asset.useful_life_years:
            skipped.append(f"{asset.code} — لا توجد قيمة قابلة للإهلاك")
            continue

        remaining = depreciable_base - (asset.accumulated_depreciation or Decimal("0"))
        if remaining <= 0:
            skipped.append(f"{asset.code} — مُهلَك بالكامل بالفعل")
            continue

        monthly_amount = (depreciable_base / Decimal(asset.useful_life_years * 12)).quantize(Decimal("0.01"))
        actual_amount = min(monthly_amount, remaining)  # الشهر الأخير غالبًا أصغر بسبب التقريب
        new_accumulated = (asset.accumulated_depreciation or Decimal("0")) + actual_amount

        entry = crud.create_depreciation_entry(
            db, asset_id=asset.id, branch_id=branch_id, year=year, month=month,
            amount=actual_amount, accumulated_after=new_accumulated, posted_by=user_id,
        )
        asset.accumulated_depreciation = new_accumulated
        created_entries.append(entry)
        total_amount += actual_amount

    journal_entry_id: Optional[int] = None
    if created_entries:
        expense_acc = _get_or_create_account(
            db, branch_id, DEPRECIATION_EXPENSE_ACCOUNT_CODE, "مصروف إهلاك الأصول الثابتة", "expense",
        )
        accum_acc = _get_or_create_account(
            db, branch_id, ACCUMULATED_DEPRECIATION_ACCOUNT_CODE, "مجمّع إهلاك الأصول الثابتة", "asset",
        )
        entry_data = JournalEntryCreate(
            branch_id=branch_id,
            entry_date=period_end,
            reference=f"DEPR-{year}{month:02d}",
            description=f"إهلاك شهري ({len(created_entries)} أصل) — {year}-{month:02d}",
            source="depreciation",
            source_id=None,
            lines=[
                JournalLineCreate(account_id=expense_acc.id, debit=total_amount, credit=Decimal("0")),
                JournalLineCreate(account_id=accum_acc.id, debit=Decimal("0"), credit=total_amount),
            ],
        )
        je = post_journal_entry(db, entry_data, user_id)
        journal_entry_id = je.id
        for entry in created_entries:
            entry.journal_entry_id = journal_entry_id

    db.commit()
    for entry in created_entries:
        db.refresh(entry)

    return DepreciationRunResult(
        branch_id=branch_id, year=year, month=month,
        entries=[AssetDepreciationEntryRead.model_validate(e) for e in created_entries],
        total_amount=total_amount,
        journal_entry_id=journal_entry_id,
        skipped_assets=skipped,
    )


def list_depreciation_entries(db: Session, branch_id: int, asset_id: Optional[int], page: int, size: int):
    items, total = crud.list_depreciation_entries(db, branch_id, asset_id, skip=(page - 1) * size, limit=size)
    return items, total


# ── Bank Reconciliation ──────────────────────────────────────────────
