"""HTTP API for Decision 0005 personal credit accounts."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from app.core.deps import DbDep, get_cashier_user, get_current_active_user, require_permission, user_level
from app.modules.credit import services
from app.modules.credit.schemas import (
    CreditAccountCreate,
    CreditAccountLimitUpdate,
    CreditAccountPage,
    CreditAccountRead,
    CreditAccountStatusUpdate,
    CreditChargeCreate,
    CreditPaymentCreate,
    CreditReversalCreate,
    CreditStatementResponse,
    CreditTransactionRead,
)

router = APIRouter(prefix="/credit", tags=["credit"])
_NO_STORE = "no-store, no-cache, must-revalidate, private"


def _branch(user) -> int:
    branch_id = getattr(user, "_active_branch_id", None)
    if branch_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "BRANCH_CONTEXT_REQUIRED", "message": "اختر فرعًا نشطًا أولاً"},
        )
    return int(branch_id)


def _role(user) -> str:
    return str(getattr(user, "role", ""))


def _require_roles(*allowed: str):
    allowed_set = set(allowed)

    def dependency(user=Depends(get_current_active_user)):
        if _role(user) not in allowed_set:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "غير مصرح بهذا الإجراء")
        return user

    return dependency


credit_reader = _require_roles("manager", "accountant", "admin", "super_admin")
credit_manager = _require_roles("manager", "admin", "super_admin")
credit_admin = _require_roles("admin", "super_admin")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = _NO_STORE


def _raise_service_error(exc: Exception) -> None:
    from app.modules.finance.services import FinancialConfigurationError  # noqa: PLC0415

    if isinstance(exc, (services.CreditAccountNotFoundError, services.CreditTransactionNotFoundError)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if isinstance(exc, services.CreditConcurrencyError):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "CREDIT_ACCOUNT_BUSY", "message": str(exc)},
        ) from exc
    if isinstance(exc, services.CreditIdempotencyConflictError):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "IDEMPOTENCY_KEY_CONFLICT", "message": str(exc)},
        ) from exc
    if isinstance(exc, services.CreditLimitExceededError):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {
                "code": "CREDIT_LIMIT_EXCEEDED",
                "message": str(exc),
                "current_balance": str(exc.current),
                "credit_limit": str(exc.limit),
                "requested": str(exc.requested),
            },
        ) from exc
    if isinstance(exc, services.CreditAccountInactiveError):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {"code": "CREDIT_ACCOUNT_INACTIVE", "message": str(exc)},
        ) from exc
    if isinstance(exc, FinancialConfigurationError):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {"code": "FINANCIAL_CONFIGURATION_ERROR", "message": str(exc)},
        ) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    # Unexpected database/programming failures must reach the secure global
    # 500 handler; never downgrade them to 400 or expose SQL details.
    raise exc


@router.post(
    "/accounts",
    response_model=CreditAccountRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("credit.accounts", "create", min_role_level=60))],
)
def create_account(
    data: CreditAccountCreate,
    response: Response,
    db: DbDep,
    user=Depends(credit_manager),
):
    _no_store(response)
    try:
        return services.open_credit_account(db, data, _branch(user), user.id)
    except Exception as exc:
        _raise_service_error(exc)


@router.get(
    "/accounts",
    response_model=CreditAccountPage,
    dependencies=[Depends(require_permission("credit.accounts", "view", min_role_level=60))],
)
def list_accounts(
    response: Response,
    db: DbDep,
    user=Depends(credit_reader),
    account_status: str | None = Query(default=None, pattern=r"^(active|suspended|closed)$"),
    holder_type: str | None = Query(default=None, pattern=r"^(customer|employee)$"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
):
    _no_store(response)
    return services.list_accounts_for_branch(
        db, _branch(user), account_status, holder_type, page=page, size=size,
    )


@router.get(
    "/accounts/lookup",
    response_model=CreditAccountRead | None,
    dependencies=[Depends(require_permission("credit.accounts", "lookup", min_role_level=40))],
)
def lookup_account(
    response: Response,
    db: DbDep,
    user=Depends(get_cashier_user),
    holder_type: str = Query(..., pattern=r"^(customer|employee)$"),
    holder_id: int = Query(..., gt=0),
):
    _no_store(response)
    return services.lookup_account_by_holder(db, _branch(user), holder_type, holder_id)


@router.get(
    "/accounts/{account_id}",
    response_model=CreditAccountRead,
    dependencies=[Depends(require_permission("credit.accounts", "view", min_role_level=60))],
)
def get_account(
    account_id: int,
    response: Response,
    db: DbDep,
    user=Depends(credit_reader),
):
    _no_store(response)
    try:
        return services.get_account_detail(db, account_id, _branch(user))
    except Exception as exc:
        _raise_service_error(exc)


@router.patch(
    "/accounts/{account_id}/status",
    response_model=CreditAccountRead,
    dependencies=[Depends(require_permission("credit.accounts", "change_status", min_role_level=60))],
)
def update_status(
    account_id: int,
    data: CreditAccountStatusUpdate,
    response: Response,
    db: DbDep,
    user=Depends(credit_manager),
):
    _no_store(response)
    try:
        return services.update_account_status(
            db, account_id, _branch(user), data.status, data.notes, user.id,
        )
    except Exception as exc:
        _raise_service_error(exc)


@router.patch(
    "/accounts/{account_id}/limit",
    response_model=CreditAccountRead,
    dependencies=[Depends(require_permission("credit.accounts", "change_limit", min_role_level=80))],
)
def update_limit(
    account_id: int,
    data: CreditAccountLimitUpdate,
    response: Response,
    db: DbDep,
    user=Depends(credit_admin),
):
    _no_store(response)
    try:
        return services.update_credit_limit(
            db, account_id, _branch(user), data.credit_limit, data.notes, user.id,
        )
    except Exception as exc:
        _raise_service_error(exc)


@router.post(
    "/accounts/{account_id}/charge",
    response_model=CreditTransactionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("credit.transactions", "charge", min_role_level=40))],
)
def charge_account(
    account_id: int,
    data: CreditChargeCreate,
    response: Response,
    db: DbDep,
    user=Depends(get_cashier_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=100),
):
    _no_store(response)
    try:
        return services.charge_to_account(
            db,
            account_id,
            _branch(user),
            data.amount,
            user.id,
            ref_order_id=data.ref_order_id,
            ref_beach_tx_id=data.ref_beach_tx_id,
            notes=data.notes,
            acting_user_level=user_level(user),
            approver_user_id=data.approver_user_id,
            approver_pin=data.approver_pin,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        _raise_service_error(exc)


@router.post(
    "/accounts/{account_id}/payment",
    response_model=CreditTransactionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("credit.transactions", "collect", min_role_level=60))],
)
def collect_payment(
    account_id: int,
    data: CreditPaymentCreate,
    response: Response,
    db: DbDep,
    user=Depends(credit_reader),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=100),
):
    _no_store(response)
    try:
        return services.record_payment(
            db,
            account_id,
            _branch(user),
            data.amount,
            user.id,
            payment_method=data.payment_method,
            notes=data.notes,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        _raise_service_error(exc)


@router.post(
    "/accounts/{account_id}/reverse",
    response_model=CreditTransactionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("credit.transactions", "reverse", min_role_level=60))],
)
def reverse_transaction(
    account_id: int,
    data: CreditReversalCreate,
    response: Response,
    db: DbDep,
    user=Depends(credit_manager),
):
    _no_store(response)
    try:
        return services.reverse_transaction(
            db,
            data.original_txn_id,
            _branch(user),
            data.notes,
            user.id,
            expected_account_id=account_id,
        )
    except Exception as exc:
        _raise_service_error(exc)


@router.get(
    "/accounts/{account_id}/statement",
    response_model=CreditStatementResponse,
    dependencies=[Depends(require_permission("credit.accounts", "view", min_role_level=60))],
)
def statement(
    account_id: int,
    response: Response,
    db: DbDep,
    user=Depends(credit_reader),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
):
    _no_store(response)
    try:
        return services.get_statement(db, account_id, _branch(user), date_from, date_to)
    except Exception as exc:
        _raise_service_error(exc)
