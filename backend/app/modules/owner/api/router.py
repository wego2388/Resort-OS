"""
app/modules/owner/api/router.py
═══════════════════════════════════════════════════════════════════════
Owner Intelligence Cockpit — API Router (Decision 0004, Phase 2+3+6).

قواعد ثابتة:
• كل endpoint يستخدم get_owner_reader — يقبل owner أو super_admin فقط.
• branch_id يُشتق دائماً من الـ session server-side — لا يُقبل من الـ client.
• Cache-Control: no-store على كل financial endpoint.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.core.deps import DbDep, get_owner_reader
from app.modules.owner import services
from app.modules.owner.schemas import (
    AllocationRuleDraftCreate,
    AllocationRuleDraftUpdate,
    AllocationRuleRead,
    BeachPerformanceResponse,
    ChannelAnalyticsResponse,
    ExceptionsResponse,
    ExpenseAnalyticsResponse,
    OwnerNowResponse,
    OwnerPerformanceResponse,
    OwnerWatchlistCreate,
    OwnerWatchlistRead,
    ProcurementAnalyticsResponse,
    SalesPerformanceResponse,
    ShiftMonitorResponse,
)

router = APIRouter(prefix="/owner", tags=["owner"])

_NO_STORE = "no-store, no-cache, must-revalidate, private"


def _get_branch(user) -> int:
    """يشتق branch_id من الـ session — مشترك بين كل endpoints."""
    branch_id: int | None = getattr(user, "_active_branch_id", None)
    if branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_ACTIVE_BRANCH",
                    "message": "لا يوجد فرع نشط لهذه الجلسة — سجّل الدخول مجدداً"},
        )
    return branch_id


def _default_range() -> tuple[date, date]:
    """الشهر الحالي من 1 حتى اليوم."""
    today = date.today()
    return today.replace(day=1), today


# ══════════════════════════════════════════════════════════════════════
# Phase 3 — Aggregation Endpoints
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/now",
    response_model=OwnerNowResponse,
    name="owner_now",
    summary="شاشة الآن — المقاييس السبعة الرئيسية (A-1 → A-7)",
)
def owner_now(response: Response, db: DbDep, user=Depends(get_owner_reader)):
    """المقاييس السبعة بتوقيت القاهرة. كل رقم يحمل is_provisional."""
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        return services.get_owner_now(db, branch_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"code": "OWNER_NOW_FAILED", "message": str(exc)}) from exc


@router.get(
    "/performance",
    response_model=OwnerPerformanceResponse,
    name="owner_performance",
    summary="شاشة الأداء — مقارنة ثلاث فترات",
)
def owner_performance(response: Response, db: DbDep, user=Depends(get_owner_reader)):
    """اليوم vs أمس، الأسبوع الحالي vs الماضي، الشهر الحالي vs الماضي."""
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        return services.get_owner_performance(db, branch_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"code": "OWNER_PERFORMANCE_FAILED", "message": str(exc)}) from exc


# ══════════════════════════════════════════════════════════════════════
# Phase 6 — Analytics Endpoints
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/sales",
    response_model=SalesPerformanceResponse,
    name="owner_sales",
    summary="أداء المبيعات — top items + ABC Pareto + هامش",
)
def owner_sales(
    response: Response,
    db: DbDep,
    user=Depends(get_owner_reader),
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
    outlet:    str  = Query(default="dining", description="dining | beach | all"),
    limit:     int  = Query(default=50, ge=1, le=200),
):
    """
    C-1 + C-2: أداء المبيعات مع تصنيف ABC وهامش الربح.
    date_from/date_to اختياريان — الافتراضي: الشهر الحالي حتى اليوم.
    branch_id من الـ session فقط.
    """
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    if date_from is None or date_to is None:
        date_from, date_to = _default_range()
    if outlet not in ("dining", "beach", "all"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail={"code": "INVALID_OUTLET", "message": "outlet يجب أن يكون dining أو beach أو all"})
    try:
        return services.get_sales_performance(db, branch_id, date_from, date_to, outlet, limit)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"code": "OWNER_SALES_FAILED", "message": str(exc)}) from exc


@router.get(
    "/beach-performance",
    response_model=BeachPerformanceResponse,
    name="owner_beach_performance",
    summary="أداء الشاطئ — مقسّم بنوع التذكرة",
)
def owner_beach_performance(
    response: Response,
    db: DbDep,
    user=Depends(get_owner_reader),
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    """C-3: أداء الشاطئ — entry/entry_towel/towel_rent/towel_return."""
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    if date_from is None or date_to is None:
        date_from, date_to = _default_range()
    try:
        return services.get_beach_performance(db, branch_id, date_from, date_to)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"code": "OWNER_BEACH_FAILED", "message": str(exc)}) from exc


@router.get(
    "/channel-analytics",
    response_model=ChannelAnalyticsResponse,
    name="owner_channel_analytics",
    summary="تحليلات قنوات B2B — per hotel/contract",
)
def owner_channel_analytics(
    response: Response,
    db: DbDep,
    user=Depends(get_owner_reader),
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    """
    C-4: أداء الفنادق B2B — check-ins، إيراد، F&B attach.
    لا بيانات ضيف فردية (Decision 0004 §Isolation model item 7).
    """
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    if date_from is None or date_to is None:
        date_from, date_to = _default_range()
    try:
        return services.get_channel_analytics(db, branch_id, date_from, date_to)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"code": "OWNER_CHANNEL_FAILED", "message": str(exc)}) from exc


@router.get(
    "/expense-analytics",
    response_model=ExpenseAnalyticsResponse,
    name="owner_expense_analytics",
    summary="تحليل المصروفات — كل فئة كنسبة % من الإيراد",
)
def owner_expense_analytics(
    response: Response,
    db: DbDep,
    user=Depends(get_owner_reader),
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    """
    D-1 + D-2: المصروفات كنسبة % من الإيراد مع variance flags + رواتب aggregate.
    رواتب: لا per employee — aggregate فقط (Decision 0004 §Isolation model item 7).
    """
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    if date_from is None or date_to is None:
        date_from, date_to = _default_range()
    try:
        return services.get_expense_analytics(db, branch_id, date_from, date_to)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"code": "OWNER_EXPENSE_FAILED", "message": str(exc)}) from exc


@router.get(
    "/procurement-analytics",
    response_model=ProcurementAnalyticsResponse,
    name="owner_procurement_analytics",
    summary="تحليل المشتريات — تركّز الإنفاق + فرق PR vs PO",
)
def owner_procurement_analytics(
    response: Response,
    db: DbDep,
    user=Depends(get_owner_reader),
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    """
    E-1 + E-2: تركّز الإنفاق بالموردين + فرق estimate vs actual.
    concentration_flag عند تجاوز 50% من إجمالي الإنفاق بمورّد واحد.
    """
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    if date_from is None or date_to is None:
        date_from, date_to = _default_range()
    try:
        return services.get_procurement_analytics(db, branch_id, date_from, date_to)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"code": "OWNER_PROCUREMENT_FAILED", "message": str(exc)}) from exc


# ══════════════════════════════════════════════════════════════════════
# Phase 7 — Shift Monitoring & Exceptions
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/shifts",
    response_model=ShiftMonitorResponse,
    name="owner_shifts",
    summary="مراقبة الورديات — من يعمل الآن + حركات الكاش",
)
def owner_shifts(response: Response, db: DbDep, user=Depends(get_owner_reader)):
    """
    F-1 + F-2 + F-3: الورديات المفتوحة مع حركات الكاش.
    المالك يقرأ فقط — لا approve/close/dispute.
    """
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        return services.get_shift_monitor(db, branch_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"code": "OWNER_SHIFTS_FAILED", "message": str(exc)}) from exc


@router.get(
    "/exceptions",
    response_model=ExceptionsResponse,
    name="owner_exceptions",
    summary="قائمة الاستثناءات — مرتّبة بالخطورة",
)
def owner_exceptions(response: Response, db: DbDep, user=Depends(get_owner_reader)):
    """
    G-1 + G-2: استثناءات مرتّبة: critical → attention → watch.
    يستدعي fraud_tasks.find_fraud_signals مباشرة — لا تكرار للمنطق.
    """
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        return services.get_exceptions(db, branch_id)
    except Exception as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail={"code": "OWNER_EXCEPTIONS_FAILED", "message": str(exc)}) from exc


# ══════════════════════════════════════════════════════════════════════
# Phase 2 — OwnerWatchlist
# ══════════════════════════════════════════════════════════════════════

@router.get("/watchlist", response_model=list[OwnerWatchlistRead])
def list_watchlist(db: DbDep, user=Depends(get_owner_reader), branch_id: int = 1):
    return services.get_watchlist(db, user.id, branch_id)


@router.post(
    "/watchlist",
    response_model=OwnerWatchlistRead,
    status_code=status.HTTP_201_CREATED,
    name="create_owner_watchlist_item",
)
def add_watchlist_item(data: OwnerWatchlistCreate, db: DbDep, user=Depends(get_owner_reader)):
    try:
        return services.add_watchlist_item(db, data, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.delete(
    "/watchlist/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    name="delete_owner_watchlist_item",
)
def remove_watchlist_item(item_id: int, db: DbDep, user=Depends(get_owner_reader)):
    try:
        services.remove_watchlist_item(db, item_id, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


# ══════════════════════════════════════════════════════════════════════
# Phase 2 — OwnerAllocationRule (مسودات فقط)
# ══════════════════════════════════════════════════════════════════════

@router.get("/allocation-rules", response_model=list[AllocationRuleRead])
def list_allocation_rules(db: DbDep, user=Depends(get_owner_reader), branch_id: int = 1):
    return services.list_allocation_rules(db, branch_id)


@router.post(
    "/allocation-rules/draft",
    response_model=AllocationRuleRead,
    status_code=status.HTTP_201_CREATED,
    name="create_owner_allocation_rule_draft",
)
def create_draft(data: AllocationRuleDraftCreate, db: DbDep, user=Depends(get_owner_reader)):
    try:
        return services.create_draft(db, data, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.patch(
    "/allocation-rules/{rule_id}",
    response_model=AllocationRuleRead,
    name="update_owner_allocation_rule_draft",
)
def update_draft(rule_id: int, data: AllocationRuleDraftUpdate, db: DbDep, user=Depends(get_owner_reader)):
    try:
        return services.update_draft(db, rule_id, data, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e


@router.delete(
    "/allocation-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    name="delete_owner_allocation_rule_draft",
)
def delete_draft(rule_id: int, db: DbDep, user=Depends(get_owner_reader)):
    try:
        services.delete_draft(db, rule_id, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
