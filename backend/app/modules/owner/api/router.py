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

import logging
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_owner_reader
from app.modules.owner import services
from app.modules.owner.db_sessions import get_owner_metadata_write_db, get_owner_read_db
from app.modules.owner.schemas import (
    AllocationRuleDraftCreate,
    AllocationRuleDraftUpdate,
    AllocationRuleRead,
    BeachPerformanceResponse,
    BeachTypeDetailResponse,
    ChannelAnalyticsResponse,
    DiningItemDetailResponse,
    DiscountAnalyticsResponse,
    ExceptionsResponse,
    ExpenseAnalyticsResponse,
    ExpenseDetailResponse,
    HRSummaryResponse,
    NowHistoryResponse,
    OwnerNowResponse,
    OwnerPerformanceResponse,
    OwnerSearchResponse,
    OwnerWatchlistCreate,
    OwnerWatchlistRead,
    ProcurementAnalyticsResponse,
    ProductDetailResponse,
    SalesPerformanceResponse,
    ShiftHistoryResponse,
    ShiftMonitorResponse,
    SupplierDetailResponse,
)
from app.modules.credit.schemas import CreditReceivablesResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/owner", tags=["owner"])

_NO_STORE = "no-store, no-cache, must-revalidate, private"


def _log_owner_audit(db: Session, user, action: str, entity_type: str, entity_id: int | None = None) -> None:
    """Decision 0004 §Isolation model item 6: تسجيل فتح تقرير حساس/
    drill-down/export/إجراء allocation — مش polling عادي (اللي بيتكرر
    كل ثواني من الفرونت إند لشاشات زي /now و/performance، وتسجيله كان
    هيغرق audit_logs برقم صفوف عديم القيمة). بتكتب عبر نفس الـsession
    المُمرَّرة للـendpoint نفسه (OwnerReadDb أو OwnerMetaWriteDb) —
    الاتنين محتاجين INSERT-only على audit_logs تحديدًا (راجع
    scripts/provision_owner_db_roles.sql)، مش وصول أوسع."""
    from app.modules.core import crud as core_crud  # noqa: PLC0415
    from app.modules.core.schemas import AuditLogCreate  # noqa: PLC0415
    try:
        core_crud.create_audit_log(db, AuditLogCreate(
            user_id=user.id,
            branch_id=getattr(user, "_active_branch_id", None),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
        ))
        db.commit()
    except Exception:
        # التسجيل التدقيقي إضافي — فشله ميوقفش الطلب الأساسي (نفس مبدأ
        # printReceipt في الفرونت إند: convenience بعد نجاح العملية
        # الحقيقية، مش جزء من نجاحها).
        db.rollback()
        logger.exception("owner router: failed to write audit log for action=%s", action)


def _owner_error(code: str, exc: Exception) -> HTTPException:
    """⚠️ 2026-08-11: كل الـ500 هنا كانت بترجع str(exc) في الـresponse
    body — تسريب معلومات داخلية حقيقي (اسم عمود، رسالة SQLAlchemy، مسار
    ملف) لأي حد وصل للـendpoint، بما فيه تفاصيل ممكن تفيد مهاجم. الخطأ
    الحقيقي بيتسجّل داخليًا (log) والعميل بياخد رسالة عامة بس + كود ثابت
    يقدر الفرونت إند يتصرف عليه."""
    logger.exception("owner router error [%s]", code)
    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": code, "message": "حدث خطأ غير متوقع — حاول مرة أخرى"},
    )

# ── سيشنين محدودي الصلاحية على مستوى الـPostgres role نفسه (2026-08-11،
# Decision 0004 §Isolation model item 5) — راجع db_sessions.py للتفاصيل.
# OwnerReadDb: كل تقارير التجميع (GET) عبر الموديولات التانية. لا وصول
# كتابة خالص، حتى لو bug مستقبلي حاول.
# OwnerMetaWriteDb: كتابات owner_watchlist/owner_allocation_rules بس —
# مفيش وصول لأي جدول تشغيلي.
OwnerReadDb = Annotated[Session, Depends(get_owner_read_db)]
OwnerMetaWriteDb = Annotated[Session, Depends(get_owner_metadata_write_db)]


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
def owner_now(response: Response, db: OwnerReadDb, user=Depends(get_owner_reader)):
    """المقاييس السبعة بتوقيت القاهرة. كل رقم يحمل is_provisional."""
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        return services.get_owner_now(db, branch_id)
    except Exception as exc:
        raise _owner_error("OWNER_NOW_FAILED", exc) from exc


@router.get(
    "/now/history",
    response_model=NowHistoryResponse,
    name="owner_now_history",
    summary="تاريخ مقاييس الآن — للـ sparklines (آخر N أيام)",
)
def owner_now_history(
    response: Response,
    db: OwnerReadDb,
    user=Depends(get_owner_reader),
    days: int = Query(default=7, ge=1, le=30, description="عدد الأيام — 1 إلى 30"),
):
    """آخر N أيام من revenue/expense/occupancy/beach للـ sparklines. لا caching."""
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        return services.get_now_history(db, branch_id, days)
    except Exception as exc:
        raise _owner_error("OWNER_HISTORY_FAILED", exc) from exc


@router.get(
    "/performance",
    response_model=OwnerPerformanceResponse,
    name="owner_performance",
    summary="شاشة الأداء — مقارنة ثلاث فترات",
)
def owner_performance(response: Response, db: OwnerReadDb, user=Depends(get_owner_reader)):
    """اليوم vs أمس، الأسبوع الحالي vs الماضي، الشهر الحالي vs الماضي."""
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        return services.get_owner_performance(db, branch_id)
    except Exception as exc:
        raise _owner_error("OWNER_PERFORMANCE_FAILED", exc) from exc


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
    db: OwnerReadDb,
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
        raise _owner_error("OWNER_SALES_FAILED", exc) from exc


@router.get(
    "/beach-performance",
    response_model=BeachPerformanceResponse,
    name="owner_beach_performance",
    summary="أداء الشاطئ — مقسّم بنوع التذكرة",
)
def owner_beach_performance(
    response: Response,
    db: OwnerReadDb,
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
        raise _owner_error("OWNER_BEACH_FAILED", exc) from exc


@router.get(
    "/channel-analytics",
    response_model=ChannelAnalyticsResponse,
    name="owner_channel_analytics",
    summary="تحليلات قنوات B2B — per hotel/contract",
)
def owner_channel_analytics(
    response: Response,
    db: OwnerReadDb,
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
        raise _owner_error("OWNER_CHANNEL_FAILED", exc) from exc


@router.get(
    "/expense-analytics",
    response_model=ExpenseAnalyticsResponse,
    name="owner_expense_analytics",
    summary="تحليل المصروفات — كل فئة كنسبة % من الإيراد",
)
def owner_expense_analytics(
    response: Response,
    db: OwnerReadDb,
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
        raise _owner_error("OWNER_EXPENSE_FAILED", exc) from exc


@router.get(
    "/procurement-analytics",
    response_model=ProcurementAnalyticsResponse,
    name="owner_procurement_analytics",
    summary="تحليل المشتريات — تركّز الإنفاق + فرق PR vs PO",
)
def owner_procurement_analytics(
    response: Response,
    db: OwnerReadDb,
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
        raise _owner_error("OWNER_PROCUREMENT_FAILED", exc) from exc


# ══════════════════════════════════════════════════════════════════════
# Phase 7 — Shift Monitoring & Exceptions
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/shifts",
    response_model=ShiftMonitorResponse,
    name="owner_shifts",
    summary="مراقبة الورديات — من يعمل الآن + حركات الكاش",
)
def owner_shifts(response: Response, db: OwnerReadDb, user=Depends(get_owner_reader)):
    """
    F-1 + F-2 + F-3: الورديات المفتوحة مع حركات الكاش.
    المالك يقرأ فقط — لا approve/close/dispute.
    """
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        return services.get_shift_monitor(db, branch_id)
    except Exception as exc:
        raise _owner_error("OWNER_SHIFTS_FAILED", exc) from exc


@router.get(
    "/exceptions",
    response_model=ExceptionsResponse,
    name="owner_exceptions",
    summary="قائمة الاستثناءات — مرتّبة بالخطورة",
)
def owner_exceptions(response: Response, db: OwnerReadDb, user=Depends(get_owner_reader)):
    """
    G-1 + G-2: استثناءات مرتّبة: critical → attention → watch.
    يستدعي fraud_tasks.find_fraud_signals مباشرة — لا تكرار للمنطق.
    """
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        return services.get_exceptions(db, branch_id)
    except Exception as exc:
        raise _owner_error("OWNER_EXCEPTIONS_FAILED", exc) from exc


# ══════════════════════════════════════════════════════════════════════
# Phase 7b — Shift History
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/shifts/history",
    response_model=ShiftHistoryResponse,
    name="owner_shifts_history",
    summary="تاريخ الورديات المغلقة — آخر N أيام",
)
def owner_shifts_history(
    response: Response,
    db: OwnerReadDb,
    user=Depends(get_owner_reader),
    days: int = Query(default=7, ge=1, le=30, description="عدد الأيام — 1 إلى 30"),
):
    """
    F-3: الورديات المغلقة خلال آخر N أيام.
    المالك يقرأ فقط — لا approve/close/dispute.
    """
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        return services.get_shift_history(db, branch_id, days)
    except Exception as exc:
        raise _owner_error("OWNER_SHIFT_HISTORY_FAILED", exc) from exc


# ══════════════════════════════════════════════════════════════════════
# Phase 7c — HR Summary
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/hr-summary",
    response_model=HRSummaryResponse,
    name="owner_hr_summary",
    summary="ملخص الموارد البشرية — موظفين + رواتب + حضور",
)
def owner_hr_summary(response: Response, db: OwnerReadDb, user=Depends(get_owner_reader)):
    """
    H-1: قائمة الموظفين مع آخر PayrollLine + حضور الشهر الحالي.
    Decision 0004 §7c: لا national_id، لا employee_si، لا monthly_tax،
    لا phone، لا email.
    branch_id من الـ session فقط.
    """
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        return services.get_hr_summary(db, branch_id)
    except Exception as exc:
        raise _owner_error("OWNER_HR_FAILED", exc) from exc


# ══════════════════════════════════════════════════════════════════════
# Phase 7d — Discount Analytics
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/discount-analytics",
    response_model=DiscountAnalyticsResponse,
    name="owner_discount_analytics",
    summary="تحليل الخصومات — أنواع + يدوي per cashier + مجموعات بالاسم",
)
def owner_discount_analytics(
    response: Response,
    db: OwnerReadDb,
    user=Depends(get_owner_reader),
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    """
    I-1 + I-2: تحليل الخصومات — aggregate بأنواعها + مجموعات العملاء
    بالاسم فقط. لا هاتف/email/national_id. لا عملاء بدون مجموعة.
    Decision 0004 §7d.
    """
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    if date_from is None or date_to is None:
        date_from, date_to = _default_range()
    try:
        return services.get_discount_analytics(db, branch_id, date_from, date_to)
    except Exception as exc:
        raise _owner_error("OWNER_DISCOUNT_FAILED", exc) from exc


# ══════════════════════════════════════════════════════════════════════
# Phase 2 — OwnerWatchlist
# ══════════════════════════════════════════════════════════════════════

@router.get("/watchlist", response_model=list[OwnerWatchlistRead])
def list_watchlist(db: OwnerMetaWriteDb, user=Depends(get_owner_reader)):
    return services.get_watchlist(db, user.id, _get_branch(user))


@router.post(
    "/watchlist",
    response_model=OwnerWatchlistRead,
    status_code=status.HTTP_201_CREATED,
    name="create_owner_watchlist_item",
)
def add_watchlist_item(data: OwnerWatchlistCreate, db: OwnerMetaWriteDb, user=Depends(get_owner_reader)):
    # branch_id مشتق من الـsession دايمًا — نفس قاعدة كل endpoint تاني هنا،
    # مش من جسم الطلب (كان باج حقيقي: العميل يقدر يبعت أي branch_id).
    data.branch_id = _get_branch(user)
    try:
        item = services.add_watchlist_item(db, data, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    _log_owner_audit(db, user, "owner_watchlist_add", "owner_watchlist", item.id)
    return item


@router.delete(
    "/watchlist/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    name="delete_owner_watchlist_item",
)
def remove_watchlist_item(item_id: int, db: OwnerMetaWriteDb, user=Depends(get_owner_reader)):
    try:
        services.remove_watchlist_item(db, item_id, user.id, _get_branch(user))
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    _log_owner_audit(db, user, "owner_watchlist_remove", "owner_watchlist", item_id)


# ══════════════════════════════════════════════════════════════════════
# Phase 2 — OwnerAllocationRule (مسودات فقط)
# ══════════════════════════════════════════════════════════════════════

@router.get("/allocation-rules", response_model=list[AllocationRuleRead])
def list_allocation_rules(db: OwnerMetaWriteDb, user=Depends(get_owner_reader)):
    # ⚠️ 2026-08-11: كان `branch_id: int = 1` query param من العميل مباشرة —
    # IDOR حقيقي (owner أي فرع يقدر يقرأ قواعد تخصيص فرع تاني بتغيير الرقم
    # في الـURL). زي كل endpoint تاني هنا، الفرع لازم يُشتق من الجلسة.
    return services.list_allocation_rules(db, _get_branch(user))


@router.post(
    "/allocation-rules/draft",
    response_model=AllocationRuleRead,
    status_code=status.HTTP_201_CREATED,
    name="create_owner_allocation_rule_draft",
)
def create_draft(data: AllocationRuleDraftCreate, db: OwnerMetaWriteDb, user=Depends(get_owner_reader)):
    # branch_id مشتق من الـsession دايمًا — نفس نمط watchlist بالظبط (كان
    # باج حقيقي مشابه هناك، اتصلح قبل كده؛ نفس الفئة كانت لسه موجودة هنا).
    data.branch_id = _get_branch(user)
    try:
        rule = services.create_draft(db, data, user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    _log_owner_audit(db, user, "owner_allocation_rule_draft_create", "owner_allocation_rule", rule.id)
    return rule


@router.patch(
    "/allocation-rules/{rule_id}",
    response_model=AllocationRuleRead,
    name="update_owner_allocation_rule_draft",
)
def update_draft(rule_id: int, data: AllocationRuleDraftUpdate, db: OwnerMetaWriteDb, user=Depends(get_owner_reader)):
    # ⚠️ 2026-08-11: كان بيدور بـrule_id بس، من غير أي تحقق من فرع القاعدة —
    # owner فرع 101 كان يقدر يعدّل مسودة فرع 102 بتخمين الـid. branch_id
    # الجلسة بيتمرر دلوقتي ويتحقق منه جوه services.update_draft.
    try:
        rule = services.update_draft(db, rule_id, data, user.id, _get_branch(user))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    _log_owner_audit(db, user, "owner_allocation_rule_draft_update", "owner_allocation_rule", rule_id)
    return rule


@router.delete(
    "/allocation-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    name="delete_owner_allocation_rule_draft",
)
def delete_draft(rule_id: int, db: OwnerMetaWriteDb, user=Depends(get_owner_reader)):
    # نفس تحقق الفرع بتاع update_draft فوق.
    try:
        services.delete_draft(db, rule_id, user.id, _get_branch(user))
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    _log_owner_audit(db, user, "owner_allocation_rule_draft_delete", "owner_allocation_rule", rule_id)


# ══════════════════════════════════════════════════════════════════════
# Phase 5 (Decision 0005) — Credit Receivables
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/credit-receivables",
    response_model=CreditReceivablesResponse,
    name="owner_credit_receivables",
    summary="ذمم شخصية آجلة — للأونر قراءة فقط",
)
def owner_credit_receivables(
    response: Response,
    db: OwnerReadDb,
    user=Depends(get_owner_reader),
):
    """
    قائمة الحسابات الآجلة الشخصية النشطة بالفرع — اسم + رصيد + آخر حركة.
    الأونر يرى القراءة فقط — لا write على أي credit endpoint.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    branch_id = _get_branch(user)
    from app.modules.credit.services import get_credit_receivables_for_owner  # noqa: PLC0415
    return get_credit_receivables_for_owner(db, branch_id)


# ══════════════════════════════════════════════════════════════════════
# Phase 8 — تفاصيل التفاصيل (Universal Drill-Down) + بحث عام
# ══════════════════════════════════════════════════════════════════════

@router.get(
    "/sales/item-detail",
    response_model=DiningItemDetailResponse,
    name="owner_sales_item_detail",
    summary="تفاصيل كل الطلبات لصنف مطعم/كافيه معيّن",
)
def owner_sales_item_detail(
    response: Response,
    db: OwnerReadDb,
    user=Depends(get_owner_reader),
    item_id: int = Query(...),
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    if date_from is None or date_to is None:
        date_from, date_to = _default_range()
    try:
        result = services.get_dining_item_detail(db, branch_id, item_id, date_from, date_to)
    except Exception as exc:
        raise _owner_error("OWNER_ITEM_DETAIL_FAILED", exc) from exc
    _log_owner_audit(db, user, "owner_drill_down", "dining_item", item_id)
    return result


@router.get(
    "/beach/type-detail",
    response_model=BeachTypeDetailResponse,
    name="owner_beach_type_detail",
    summary="تفاصيل كل معاملات نوع تذكرة شاطئ معيّن",
)
def owner_beach_type_detail(
    response: Response,
    db: OwnerReadDb,
    user=Depends(get_owner_reader),
    tx_type: str = Query(...),
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    if date_from is None or date_to is None:
        date_from, date_to = _default_range()
    try:
        result = services.get_beach_type_detail(db, branch_id, tx_type, date_from, date_to)
    except Exception as exc:
        raise _owner_error("OWNER_BEACH_DETAIL_FAILED", exc) from exc
    _log_owner_audit(db, user, "owner_drill_down", "beach_ticket_type")
    return result


@router.get(
    "/expense-detail",
    response_model=ExpenseDetailResponse,
    name="owner_expense_detail",
    summary="تفاصيل كل قيود اليومية داخل فئة مصروف معيّنة",
)
def owner_expense_detail(
    response: Response,
    db: OwnerReadDb,
    user=Depends(get_owner_reader),
    account_code: str = Query(...),
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    if date_from is None or date_to is None:
        date_from, date_to = _default_range()
    try:
        result = services.get_expense_detail(db, branch_id, account_code, date_from, date_to)
    except Exception as exc:
        raise _owner_error("OWNER_EXPENSE_DETAIL_FAILED", exc) from exc
    _log_owner_audit(db, user, "owner_drill_down", "expense_account")
    return result


@router.get(
    "/procurement-detail",
    response_model=SupplierDetailResponse,
    name="owner_procurement_detail",
    summary="تفاصيل كل أوامر الشراء لمورد معيّن",
)
def owner_procurement_detail(
    response: Response,
    db: OwnerReadDb,
    user=Depends(get_owner_reader),
    supplier_id: int = Query(...),
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    if date_from is None or date_to is None:
        date_from, date_to = _default_range()
    try:
        result = services.get_supplier_detail(db, branch_id, supplier_id, date_from, date_to)
    except Exception as exc:
        raise _owner_error("OWNER_SUPPLIER_DETAIL_FAILED", exc) from exc
    _log_owner_audit(db, user, "owner_drill_down", "supplier", supplier_id)
    return result


@router.get(
    "/product-detail",
    response_model=ProductDetailResponse,
    name="owner_product_detail",
    summary="تفاصيل حركات مخزون منتج معيّن + الرصيد الحالي",
)
def owner_product_detail(
    response: Response,
    db: OwnerReadDb,
    user=Depends(get_owner_reader),
    product_id: int = Query(...),
    date_from: date = Query(default=None),
    date_to:   date = Query(default=None),
):
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    if date_from is None or date_to is None:
        date_from, date_to = _default_range()
    try:
        result = services.get_product_detail(db, branch_id, product_id, date_from, date_to)
    except Exception as exc:
        raise _owner_error("OWNER_PRODUCT_DETAIL_FAILED", exc) from exc
    _log_owner_audit(db, user, "owner_drill_down", "product", product_id)
    return result


@router.get(
    "/search",
    response_model=OwnerSearchResponse,
    name="owner_search",
    summary="بحث عام — أصناف/منتجات/موردين/حسابات مصروف/موظفين بالاسم",
)
def owner_search(
    response: Response,
    db: OwnerReadDb,
    user=Depends(get_owner_reader),
    q: str = Query(..., min_length=2, max_length=100),
):
    response.headers["Cache-Control"] = _NO_STORE
    branch_id = _get_branch(user)
    try:
        result = services.search_everything(db, branch_id, q)
    except Exception as exc:
        raise _owner_error("OWNER_SEARCH_FAILED", exc) from exc
    _log_owner_audit(db, user, "owner_search", "owner_search")
    return result
