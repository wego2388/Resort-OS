"""
app/modules/owner/_services/search.py
Extracted from app/modules/owner/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session
from app.modules.owner.schemas import (
    OwnerSearchResponse,
    SearchResultItem,
)


def search_everything(db: Session, branch_id: int, query: str, limit: int = 15) -> OwnerSearchResponse:
    """بحث عام بالاسم عبر المنتجات/الموردين/حسابات المصروف/الموظفين —
    كل نوع بيرجع أعلى النتائج تطابقًا بالاسم بس (بدون بيانات مالية إضافية،
    الفرونت إند بيفتح الـdetail المناسب لما المستخدم يدوس على نتيجة)."""
    from app.modules.inventory.models import Product, Supplier  # noqa: PLC0415
    from app.modules.finance.models import Account  # noqa: PLC0415
    from app.modules.hr.models import Employee  # noqa: PLC0415
    from app.modules.dining.models import DiningItem  # noqa: PLC0415

    q = f"%{query.strip()}%"
    results: list[SearchResultItem] = []
    if not query.strip():
        return OwnerSearchResponse(query=query, results=[], computed_at=datetime.utcnow())

    dining_items = (
        db.query(DiningItem)
        .filter(DiningItem.branch_id == branch_id, DiningItem.name.ilike(q))
        .limit(limit)
        .all()
    )
    results += [
        SearchResultItem(
            entity_type="dining_item", entity_id=i.id, title=i.name,
            subtitle="صنف مطعم/كافيه",
        )
        for i in dining_items
    ]

    products = (
        db.query(Product)
        .filter(Product.branch_id == branch_id, Product.name.ilike(q))
        .limit(limit)
        .all()
    )
    results += [
        SearchResultItem(
            entity_type="product", entity_id=p.id, title=p.name,
            subtitle=f"مخزون — {p.sku}",
        )
        for p in products
    ]

    suppliers = (
        db.query(Supplier)
        .filter(Supplier.branch_id == branch_id, Supplier.name.ilike(q))
        .limit(limit)
        .all()
    )
    results += [
        SearchResultItem(
            entity_type="supplier", entity_id=s.id, title=s.name,
            subtitle="مورد",
        )
        for s in suppliers
    ]

    accounts = (
        db.query(Account)
        .filter(
            Account.branch_id == branch_id,
            Account.account_type == "expense",
            Account.name.ilike(q),
        )
        .limit(limit)
        .all()
    )
    results += [
        SearchResultItem(
            entity_type="expense_account", entity_id=a.id, title=a.name,
            subtitle=f"حساب مصروف — {a.code}", value_label=a.code,
        )
        for a in accounts
    ]

    employees = (
        db.query(Employee)
        .filter(Employee.branch_id == branch_id, Employee.full_name.ilike(q))
        .limit(limit)
        .all()
    )
    results += [
        SearchResultItem(
            entity_type="employee", entity_id=e.id, title=e.full_name,
            subtitle=e.position,
        )
        for e in employees
    ]

    return OwnerSearchResponse(query=query, results=results, computed_at=datetime.utcnow())
