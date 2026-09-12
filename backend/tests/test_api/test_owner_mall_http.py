"""Owner mall summary: real leasing figures, branch isolation and no PII."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.config import settings
from app.resort_os.timezone_utils import local_today
from tests.conftest import _create_test_user, _make_token, assign_test_user_to_branch


def _branch(db, label: str):
    from app.modules.core.models import Branch

    branch = Branch(
        name=f"Mall {label}",
        name_ar=f"مول {label}",
        code=f"MAL-{uuid.uuid4().hex[:8].upper()}",
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


def _headers(db, role: str, branch_id: int) -> dict[str, str]:
    email = f"mall-{role}-{uuid.uuid4().hex[:8]}@test.local"
    user_id = _create_test_user(email, role, two_factor_enabled=(role == "owner"))
    assign_test_user_to_branch(db, user_id, branch_id)
    db.commit()
    return {"Authorization": f"Bearer {_make_token(email, branch_id=branch_id)}"}


def _contract(db, branch_id: int, *, number: str, unit: str, status: str = "active"):
    from app.modules.leasing.models import LeaseContract

    today = local_today(settings.TIMEZONE)
    contract = LeaseContract(
        branch_id=branch_id,
        contract_number=number,
        tenant_name=f"TENANT-SECRET-{number}",
        tenant_phone="01000000000",
        tenant_national_id="29801010101010",
        unit_description=unit,
        start_date=today - timedelta(days=60),
        end_date=today + timedelta(days=20),
        base_rent=Decimal("1000.00"),
        status=status,
    )
    db.add(contract)
    db.flush()
    return contract


def test_owner_mall_summary_uses_real_sources_without_pii_or_cross_branch_leak(
    client, db, setup_db,
):
    from app.modules.finance.models import Payment
    from app.modules.leasing.models import LeasePayment, TenantCashLog

    branch = _branch(db, "A")
    other_branch = _branch(db, "B")
    headers = _headers(db, "owner", branch.id)
    today = local_today(settings.TIMEZONE)

    contract = _contract(
        db, branch.id, number=f"LC-{uuid.uuid4().hex[:10]}", unit="محل الواجهة 4",
    )
    current_payment = LeasePayment(
        contract_id=contract.id,
        due_date=today,
        amount=Decimal("1000.00"),
        paid_amount=Decimal("400.00"),
        status="partial",
        accrued=True,
    )
    overdue_payment = LeasePayment(
        contract_id=contract.id,
        due_date=today - timedelta(days=40),
        amount=Decimal("500.00"),
        penalty=Decimal("50.00"),
        paid_amount=Decimal("100.00"),
        status="overdue",
        accrued=True,
    )
    db.add_all([current_payment, overdue_payment])
    db.flush()

    direct_log = TenantCashLog(
        branch_id=branch.id,
        contract_id=contract.id,
        amount=Decimal("250.00"),
        activity_type="revenue_share",
        payment_method="bank_transfer",
    )
    deposit_log = TenantCashLog(
        branch_id=branch.id,
        contract_id=contract.id,
        amount=Decimal("900.00"),
        activity_type="deposit",
        payment_method="bank_transfer",
    )
    db.add_all([direct_log, deposit_log])
    db.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add_all([
        Payment(
            branch_id=branch.id, amount=Decimal("400.00"), method="card",
            posted_at=now, source="leasing_rent", ref_order_id=current_payment.id,
        ),
        Payment(
            branch_id=branch.id, amount=Decimal("250.00"), method="bank_transfer",
            posted_at=now, source="leasing_cash_log", ref_order_id=direct_log.id,
        ),
        Payment(
            branch_id=branch.id, amount=Decimal("900.00"), method="bank_transfer",
            posted_at=now, source="leasing_cash_log", ref_order_id=deposit_log.id,
        ),
    ])

    other_contract = _contract(
        db, other_branch.id, number=f"LC-{uuid.uuid4().hex[:10]}", unit="OTHER-BRANCH-UNIT",
    )
    db.add(LeasePayment(
        contract_id=other_contract.id,
        due_date=today,
        amount=Decimal("99999.00"),
        paid_amount=Decimal(0),
        status="pending",
        accrued=True,
    ))
    db.commit()

    response = client.get("/api/v1/owner/mall/summary", headers=headers)

    assert response.status_code == 200, response.text
    assert "no-store" in response.headers["cache-control"]
    body = response.json()
    assert body["registry_ready"] is False
    assert body["map_available"] is False
    assert body["registered_unit_count"] is None
    assert body["occupied_unit_count"] is None
    assert body["vacant_unit_count"] is None
    assert body["occupancy_pct"] is None
    assert body["total_contract_count"] == 1
    assert body["active_contract_count"] == 1
    assert body["expiring_within_30_days"] == 1
    assert Decimal(body["scheduled_rent"]) == Decimal("1000.00")
    assert Decimal(body["accrued_rent"]) == Decimal("1000.00")
    assert Decimal(body["collected_rent"]) == Decimal("650.00")
    assert Decimal(body["overdue_receivables"]) == Decimal("450.00")
    assert body["contracts"][0]["unit_description"] == "محل الواجهة 4"
    serialized = response.text
    assert "TENANT-SECRET" not in serialized
    assert "01000000000" not in serialized
    assert "29801010101010" not in serialized
    assert "OTHER-BRANCH-UNIT" not in serialized


def test_owner_mall_summary_empty_state_is_truthful(client, db, setup_db):
    branch = _branch(db, "EMPTY")
    response = client.get(
        "/api/v1/owner/mall/summary",
        headers=_headers(db, "owner", branch.id),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contracts"] == []
    assert body["total_contract_count"] == 0
    assert body["scheduled_rent"] == "0.00"
    assert body["collected_rent"] == "0.00"
    assert body["occupancy_pct"] is None


def test_non_owner_cannot_read_owner_mall_summary(client, db, setup_db):
    branch = _branch(db, "DENIED")
    response = client.get(
        "/api/v1/owner/mall/summary",
        headers=_headers(db, "cashier", branch.id),
    )
    assert response.status_code == 403
    assert "no-store" in response.headers["cache-control"]
