"""
tests/test_api/test_leasing_http.py
HTTP-level tests for the leasing module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Leasing HTTP Branch", name_ar="فرع إيجارات",
               code=f"LSE-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def contract_payload(branch_id: int) -> dict:
    return {
        "branch_id": branch_id,
        "tenant_name": "شركة النيل للتجارة",
        "unit_description": "محل تجاري رقم 12",
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=365)),
        "base_rent": "5000.00",
        "payment_period": "monthly",
    }


def seed_leasing_accounts(db, branch):
    """يزرع حسابات الشجرة المطلوبة لقيود الإيجار المحاسبية (1100/1260/2150/4500).
    tests/conftest.py's setup_db بينشئ الـ schema بس — من غير بيانات app.seed.py
    (اللي بيتشغل بس عن طريق الـ entrypoint الحقيقي) — فأي test بيتحقق من قيد
    محاسبي لازم يزرع الحسابات دي بنفسه، وإلا الـ journal posting بيعمل no-op
    بصمت (نفس الـ try/except pattern زي timeshare's _post_deferred_revenue_journal)."""
    from app.modules.finance.models import Account
    accounts = [
        Account(branch_id=branch.id, code="1100", name="Cash", account_type="asset"),
        Account(branch_id=branch.id, code="1260", name="Tenant AR", account_type="asset"),
        Account(branch_id=branch.id, code="2150", name="Tenant Deposits", account_type="liability"),
        Account(branch_id=branch.id, code="4500", name="Lease Revenue", account_type="revenue"),
    ]
    db.add_all(accounts)
    db.commit()


class TestLeasingContractFlow:
    def test_create_contract_generates_payment_schedule(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post("/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers)
        assert resp.status_code == 201, resp.text
        contract = resp.json()
        assert contract["status"] in ("draft", "active")
        assert len(contract["payments"]) >= 11  # ~12 monthly payments over a year

    def test_pay_payment_updates_status(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        payment_id = contract["payments"][0]["id"]
        amount = contract["payments"][0]["amount"]

        pay_resp = client.post(
            f"/api/v1/leasing/payments/{payment_id}/pay",
            json={"paid_amount": amount, "payment_method": "bank_transfer"},
            headers=manager_headers,
        )
        assert pay_resp.status_code == 200, pay_resp.text
        assert pay_resp.json()["status"] == "paid"

    def test_apply_penalties_via_http(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            f"/api/v1/leasing/contracts/{contract['id']}/apply-penalties", headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert "updated" in resp.json()


class TestLeasingPermissions:
    def test_create_contract_requires_manager(self, client: TestClient, db, fake_redis, cashier_headers):
        """cashier (40) must not create lease contracts (manager=60 required)."""
        branch = make_branch_committed(db)
        resp = client.post("/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=cashier_headers)
        assert resp.status_code == 403

    def test_apply_penalties_requires_manager(self, client: TestClient, db, fake_redis, manager_headers, cashier_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        resp = client.post(
            f"/api/v1/leasing/contracts/{contract['id']}/apply-penalties", headers=cashier_headers,
        )
        assert resp.status_code == 403


class TestLeasingValidation:
    def test_create_contract_rejects_end_before_start(self, client: TestClient, db, fake_redis, manager_headers):
        """end_date <= start_date is a business rule (ValueError -> 400), not a schema constraint."""
        branch = make_branch_committed(db)
        payload = contract_payload(branch.id)
        payload["end_date"] = str(date.today() - timedelta(days=10))
        resp = client.post("/api/v1/leasing/contracts", json=payload, headers=manager_headers)
        assert resp.status_code == 400

    def test_create_contract_rejects_zero_rent(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        payload = contract_payload(branch.id)
        payload["base_rent"] = "0"
        resp = client.post("/api/v1/leasing/contracts", json=payload, headers=manager_headers)
        assert resp.status_code == 422

    def test_pay_payment_rejects_invalid_method(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        payment_id = contract["payments"][0]["id"]

        resp = client.post(
            f"/api/v1/leasing/payments/{payment_id}/pay",
            json={"paid_amount": "100.00", "payment_method": "crypto"},
            headers=manager_headers,
        )
        assert resp.status_code == 422


class TestLeasingPenaltyTiers:
    """Regression coverage for the penalty-tier fix (Task B audit,
    resort-os-docs/12-TIMESHARE-COMPLETE.md § 'عقوبة تأخر الإيجار'): 5% for
    8-30 days late, 10% for >30 days. Previous code used 3/15-day thresholds,
    which didn't match the spec at all."""

    def _make_overdue_payment(self, db, branch, manager_headers, client, days_overdue: int):
        from app.modules.leasing.models import LeasePayment
        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        payment_id = contract["payments"][0]["id"]
        row = db.query(LeasePayment).filter(LeasePayment.id == payment_id).first()
        row.due_date = date.today() - timedelta(days=days_overdue)
        db.commit()
        return contract["id"], payment_id

    def test_no_penalty_before_8_days_overdue(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract_id, payment_id = self._make_overdue_payment(db, branch, manager_headers, client, days_overdue=5)

        client.post(f"/api/v1/leasing/contracts/{contract_id}/apply-penalties", headers=manager_headers)

        contract = client.get(f"/api/v1/leasing/contracts/{contract_id}", headers=manager_headers).json()
        payment = next(p for p in contract["payments"] if p["id"] == payment_id)
        assert Decimal(str(payment["penalty"])) == Decimal("0")

    def test_5pct_penalty_between_8_and_30_days_overdue(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract_id, payment_id = self._make_overdue_payment(db, branch, manager_headers, client, days_overdue=10)

        client.post(f"/api/v1/leasing/contracts/{contract_id}/apply-penalties", headers=manager_headers)

        contract = client.get(f"/api/v1/leasing/contracts/{contract_id}", headers=manager_headers).json()
        payment = next(p for p in contract["payments"] if p["id"] == payment_id)
        assert Decimal(str(payment["penalty"])) == (Decimal(str(payment["amount"])) * Decimal("0.05")).quantize(Decimal("0.01"))

    def test_10pct_penalty_beyond_30_days_overdue(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract_id, payment_id = self._make_overdue_payment(db, branch, manager_headers, client, days_overdue=35)

        client.post(f"/api/v1/leasing/contracts/{contract_id}/apply-penalties", headers=manager_headers)

        contract = client.get(f"/api/v1/leasing/contracts/{contract_id}", headers=manager_headers).json()
        payment = next(p for p in contract["payments"] if p["id"] == payment_id)
        assert Decimal(str(payment["penalty"])) == (Decimal(str(payment["amount"])) * Decimal("0.10")).quantize(Decimal("0.01"))


class TestLeasingAccountingIntegration:
    """Task B audit: leasing posted zero journal entries despite the spec's exact
    worked examples (deposit + rent collection). Verifies the new
    _post_deposit_journal/_post_rent_collection_journal wiring end-to-end."""

    def test_contract_with_deposit_posts_journal_entry(self, client: TestClient, db, fake_redis, manager_headers):
        from app.modules.finance.models import JournalEntry
        branch = make_branch_committed(db)
        seed_leasing_accounts(db, branch)

        payload = contract_payload(branch.id)
        payload["security_deposit"] = "3000.00"
        resp = client.post("/api/v1/leasing/contracts", json=payload, headers=manager_headers)
        assert resp.status_code == 201, resp.text
        contract_id = resp.json()["id"]

        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "leasing", JournalEntry.source_id == contract_id)
            .first()
        )
        assert entry is not None
        lines = {l.account.code: (l.debit, l.credit) for l in entry.lines}
        assert lines["1100"] == (Decimal("3000.00"), Decimal("0.00"))
        assert lines["2150"] == (Decimal("0.00"), Decimal("3000.00"))

    def test_contract_without_deposit_posts_no_journal_entry(self, client: TestClient, db, fake_redis, manager_headers):
        from app.modules.finance.models import JournalEntry
        branch = make_branch_committed(db)
        seed_leasing_accounts(db, branch)

        resp = client.post("/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers)
        contract_id = resp.json()["id"]

        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "leasing", JournalEntry.source_id == contract_id)
            .first()
        )
        assert entry is None

    def test_pay_payment_posts_two_journal_entries(self, client: TestClient, db, fake_redis, manager_headers):
        from app.modules.finance.models import JournalEntry
        branch = make_branch_committed(db)
        seed_leasing_accounts(db, branch)

        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        payment_id = contract["payments"][0]["id"]
        amount = contract["payments"][0]["amount"]

        pay_resp = client.post(
            f"/api/v1/leasing/payments/{payment_id}/pay",
            json={"paid_amount": amount, "payment_method": "cash"},
            headers=manager_headers,
        )
        assert pay_resp.status_code == 200, pay_resp.text

        entries = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "leasing", JournalEntry.source_id == payment_id)
            .all()
        )
        assert len(entries) == 2
        all_lines = {l.account.code: (l.debit, l.credit) for e in entries for l in e.lines}
        assert all_lines["1100"] == (Decimal(str(amount)), Decimal("0.00"))
        assert all_lines["4500"] == (Decimal("0.00"), Decimal(str(amount)))


class TestLeasingCashLog:
    """Task B audit: TenantCashLog model existed with a real migration but zero
    schemas/crud/services/router — same 'model exists, nothing wired' pattern
    as the Task A bugs (PMS housekeeping, CRM leads)."""

    def test_record_cash_log_posts_journal_entry_for_rent_payment(self, client: TestClient, db, fake_redis, manager_headers):
        from app.modules.finance.models import JournalEntry
        branch = make_branch_committed(db)
        seed_leasing_accounts(db, branch)
        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            f"/api/v1/leasing/contracts/{contract['id']}/cash-logs",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "amount": "1500.00", "activity_type": "rent_payment", "payment_method": "cash",
            },
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        log = resp.json()
        assert log["amount"] == "1500.00" or Decimal(str(log["amount"])) == Decimal("1500.00")

        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "leasing", JournalEntry.source_id == log["id"])
            .first()
        )
        assert entry is not None

    def test_record_cash_log_maintenance_type_posts_no_journal(self, client: TestClient, db, fake_redis, manager_headers):
        """Only rent_payment/revenue_share cash logs post journal entries — a
        maintenance note shouldn't create phantom accounting entries."""
        from app.modules.finance.models import JournalEntry
        branch = make_branch_committed(db)
        seed_leasing_accounts(db, branch)
        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            f"/api/v1/leasing/contracts/{contract['id']}/cash-logs",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "amount": "500.00", "activity_type": "maintenance",
            },
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        log = resp.json()

        entry = (
            db.query(JournalEntry)
            .filter(JournalEntry.source == "leasing", JournalEntry.source_id == log["id"])
            .first()
        )
        assert entry is None

    def test_list_cash_logs_via_http(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()
        client.post(
            f"/api/v1/leasing/contracts/{contract['id']}/cash-logs",
            json={"branch_id": branch.id, "contract_id": contract["id"], "amount": "200.00", "activity_type": "other"},
            headers=manager_headers,
        )

        resp = client.get(f"/api/v1/leasing/contracts/{contract['id']}/cash-logs", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) == 1
        assert resp.json()[0]["activity_type"] == "other"

    def test_create_cash_log_requires_manager(self, client: TestClient, db, fake_redis, manager_headers, cashier_headers):
        """cashier (40) must not record tenant cash-log entries — manager (60) required."""
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            f"/api/v1/leasing/contracts/{contract['id']}/cash-logs",
            json={"branch_id": branch.id, "contract_id": contract["id"], "amount": "100.00"},
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_create_cash_log_rejects_invalid_activity_type(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            f"/api/v1/leasing/contracts/{contract['id']}/cash-logs",
            json={
                "branch_id": branch.id, "contract_id": contract["id"],
                "amount": "100.00", "activity_type": "bribery",
            },
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_create_cash_log_rejects_mismatched_contract_id(self, client: TestClient, db, fake_redis, manager_headers):
        branch = make_branch_committed(db)
        contract = client.post(
            "/api/v1/leasing/contracts", json=contract_payload(branch.id), headers=manager_headers,
        ).json()

        resp = client.post(
            f"/api/v1/leasing/contracts/{contract['id']}/cash-logs",
            json={"branch_id": branch.id, "contract_id": contract["id"] + 999, "amount": "100.00"},
            headers=manager_headers,
        )
        assert resp.status_code == 400
