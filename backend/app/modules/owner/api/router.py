"""
app/modules/owner/api/router.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — API Router (Decision 0004, Phase 2+3).

Phase 2: OwnerWatchlist + OwnerAllocationRule draft endpoints.
Phase 3: Aggregation endpoints — /owner/now + /owner/performance.

قواعد ثابتة:
• كل endpoint يستخدم get_owner_reader — يقبل owner أو super_admin فقط.
• branch_id يُشتق دائماً من الـ session server-side — لا يُقبل من الـ client.
• لا يوجد endpoint يقبل branch_id كـ query param على شاشات التجميع.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.deps import DbDep, get_owner_reader
from app.modules.owner import services
from app.modules.owner.schemas import (
    AllocationRuleDraftCreate,
    AllocationRuleDraftUpdate,
    AllocationRuleRead,
    OwnerNowResponse,
    OwnerPerformanceResponse,
    OwnerWatchlistCreate,
    OwnerWatchlistRead,
)

router = APIRouter(prefix="/owner", tags=["owner"])

_NO_STORE = "no-store, no-cache, must-revalidate, private"
"""Cache-Control header للـ financial endpoints — Decision 0004 §New engineering surface."""


# ══════════════════════════════════════════════════════════════════════
# Phase 3 — Aggregation Endpoints
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/now",
    response_model=OwnerNowResponse,
    name="owner_now",
    summary="شاشة الآن — المقاييس السبعة الرئيسية (A-1 → A-7)",
    description=(
        "يعيد إيراد اليوم، كاش الأدراج، مصروفات اليوم، ذمم B2B، "
        "ذمم تايم شير، إشغال الغرف، وسعة الشاطئ — كلها بتوقيت القاهرة. "
        "branch_id يُشتق من الـ session، لا يُقبل من الـ client."
    ),
)
def owner_now(
    response: Response,
    db: DbDep,
    user=Depends(get_owner_reader),
):
    """
    GET /api/v1/owner/now

    المقاييس السبعة بتوقيت القاهرة الحالي.
    كل رقم يحمل is_provisional — لا يُقدَّم رقم provisional كأنه نهائي.
    """
    # Cache-Control: no-store — بيانات مالية حساسة (Decision 0004)
    response.headers["Cache-Control"] = _NO_STORE

    # branch_id يُشتق حصراً من الـ session server-side — لا يُقبل من الـ client.
    branch_id: int | None = getattr(user, "_active_branch_id", None)
    if branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_ACTIVE_BRANCH",
                    "message": "لا يوجد فرع نشط لهذه الجلسة — سجّل الدخول مجدداً"},
        )
    try:
        return services.get_owner_now(db, branch_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "OWNER_NOW_FAILED", "message": str(exc)},
        ) from exc


@router.get(
    "/performance",
    response_model=OwnerPerformanceResponse,
    name="owner_performance",
    summary="شاشة الأداء — مقارنة ثلاث فترات",
    description=(
        "اليوم vs أمس، الأسبوع الحالي vs الأسبوع الماضي، "
        "الشهر الحالي vs الشهر الماضي — إيراد ومصروف وصافي دخل. "
        "branch_id يُشتق من الـ session، لا يُقبل من الـ client."
    ),
)
def owner_performance(
    response: Response,
    db: DbDep,
    user=Depends(get_owner_reader),
):
    """
    GET /api/v1/owner/performance

    مقارنة ثلاث فترات. الـ delta والنسب محسوبة في owner services —
    لا في finance module.
    """
    # Cache-Control: no-store — بيانات مالية حساسة (Decision 0004)
    response.headers["Cache-Control"] = _NO_STORE

    branch_id: int | None = getattr(user, "_active_branch_id", None)
    if branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_ACTIVE_BRANCH",
                    "message": "لا يوجد فرع نشط لهذه الجلسة — سجّل الدخول مجدداً"},
        )
    try:
        return services.get_owner_performance(db, branch_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "OWNER_PERFORMANCE_FAILED", "message": str(exc)},
        ) from exc


# ══════════════════════════════════════════════════════════════════════
# Phase 2 — OwnerWatchlist
# ══════════════════════════════════════════════════════════════════════

@router.get("/watchlist", response_model=list[OwnerWatchlistRead])
def list_watchlist(
    db: DbDep,
    user=Depends(get_owner_reader),
    branch_id: int = 1,
):
    """قائمة metrics المثبّتة للمالك."""
    return services.get_watchlist(db, user.id, branch_id)


@router.post(
    "/watchlist",
    response_model=OwnerWatchlistRead,
    status_code=status.HTTP_201_CREATED,
    name="create_owner_watchlist_item",
)
def add_watchlist_item(
    data: OwnerWatchlistCreate,
    db: DbDep,
    user=Depends(get_owner_reader),
):
    """إضافة metric للـ watchlist."""
    try:
        return services.add_watchlist_item(db, data, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.delete(
    "/watchlist/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    name="delete_owner_watchlist_item",
)
def remove_watchlist_item(
    item_id: int,
    db: DbDep,
    user=Depends(get_owner_reader),
):
    """حذف metric من الـ watchlist."""
    try:
        services.remove_watchlist_item(db, item_id, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


# ══════════════════════════════════════════════════════════════════════
# Phase 2 — OwnerAllocationRule (مسودات فقط)
# ══════════════════════════════════════════════════════════════════════

@router.get("/allocation-rules", response_model=list[AllocationRuleRead])
def list_allocation_rules(
    db: DbDep,
    user=Depends(get_owner_reader),
    branch_id: int = 1,
):
    """قائمة قواعد التخصيص (drafts + published)."""
    return services.list_allocation_rules(db, branch_id)


@router.post(
    "/allocation-rules/draft",
    response_model=AllocationRuleRead,
    status_code=status.HTTP_201_CREATED,
    name="create_owner_allocation_rule_draft",
)
def create_draft(
    data: AllocationRuleDraftCreate,
    db: DbDep,
    user=Depends(get_owner_reader),
):
    """إنشاء مسودة قاعدة تخصيص جديدة."""
    try:
        return services.create_draft(db, data, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.patch(
    "/allocation-rules/{rule_id}",
    response_model=AllocationRuleRead,
    name="update_owner_allocation_rule_draft",
)
def update_draft(
    rule_id: int,
    data: AllocationRuleDraftUpdate,
    db: DbDep,
    user=Depends(get_owner_reader),
):
    """تعديل مسودة — published immutable."""
    try:
        return services.update_draft(db, rule_id, data, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.delete(
    "/allocation-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    name="delete_owner_allocation_rule_draft",
)
def delete_draft(
    rule_id: int,
    db: DbDep,
    user=Depends(get_owner_reader),
):
    """حذف مسودة — published immutable."""
    try:
        services.delete_draft(db, rule_id, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
