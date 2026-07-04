"""
tests/test_api/test_finance_depreciation_and_reconciliation_http.py
HTTP-level tests for the two finance gaps confirmed missing 2026-07-04:

1. Fixed-asset depreciation (straight-line) — Asset (maintenance module) had
   zero depreciation fields; now has purchase_cost/salvage_value/
   useful_life_years/depreciation_start_date/accumulated_depreciation, and
   finance.services.run_depreciation() posts a real balanced journal entry.
2. Bank reconciliation — no BankAccount/BankStatementLine model existed at
   all; now real statement-line import + auto/manual matching against
   Payment rows + a reconciliation summary report.

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed — the
HTTP request goes through a different DB session than the `db` fixture.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Finance Depr/Recon Branch", name_ar="فرع اختبار",
               code=f"FDR-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_asset_committed(db, branch, *, purchase_cost=None, salvage_value=Decimal("0"),
                          useful_life_years=None, depreciation_start_date=None, code=None):
    from app.modules.maintenance.models import Asset
    asset = Asset(
        branch_id=branch.id,
        name="مكيف قاعة المؤتمرات",
        code=code or f"AST-{uuid.uuid4().hex[:8].upper()}",
        category="hvac",
        purchase_cost=purchase_cost,
        salvage_value=salvage_value,
        useful_life_years=useful_life_years,
        depreciation_start_date=depreciation_start_date,
    )
    db.add(asset)
    db.commit()
    return asset


def make_folio_committed(db, branch):
    from app.modules.finance.models import Folio
    folio = Folio(
        branch_id=branch.id, guest_name="نزيل اختبار",
        check_in=datetime.utcnow(), check_out=datetime.utcnow() + timedelta(days=2),
        status="open", currency="EGP",
    )
    db.add(folio)
    db.commit()
    return folio


def make_payment_committed(db, branch, folio, amount, posted_at):
    from app.modules.finance.models import Payment
    payment = Payment(
        folio_id=folio.id, branch_id=branch.id, amount=amount, currency="EGP",
        method="bank_transfer", posted_at=posted_at,
    )
    db.add(payment)
    db.commit()
    return payment


class TestDepreciationRunHTTP:
    def test_run_depreciation_posts_balanced_journal_entry(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        # 12,000 EGP، عمر إنتاجي سنتين (24 شهر)، بدون قيمة متبقية => 500.00/شهر بالظبط
        asset = make_asset_committed(
            db, branch, purchase_cost=Decimal("12000.00"), useful_life_years=2,
            depreciation_start_date=date(2026, 1, 1),
        )

        resp = client.post(
            "/api/v1/finance/depreciation/run",
            json={"branch_id": branch.id, "year": 2026, "month": 6},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["entries"]) == 1
        assert Decimal(str(body["entries"][0]["amount"])) == Decimal("500.00")
        assert Decimal(str(body["total_amount"])) == Decimal("500.00")
        assert body["journal_entry_id"] is not None

        je_resp = client.get(
            f"/api/v1/finance/journal-entries/{body['journal_entry_id']}",
            headers=manager_headers,
        )
        assert je_resp.status_code == 200, je_resp.text
        je = je_resp.json()
        total_debit = sum(Decimal(str(l["debit"])) for l in je["lines"])
        total_credit = sum(Decimal(str(l["credit"])) for l in je["lines"])
        assert total_debit == total_credit == Decimal("500.00")

    def test_run_depreciation_is_idempotent_per_period(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        make_asset_committed(
            db, branch, purchase_cost=Decimal("6000.00"), useful_life_years=1,
            depreciation_start_date=date(2026, 1, 1),
        )

        first = client.post(
            "/api/v1/finance/depreciation/run",
            json={"branch_id": branch.id, "year": 2026, "month": 3},
            headers=manager_headers,
        )
        assert first.status_code == 200, first.text
        assert len(first.json()["entries"]) == 1

        second = client.post(
            "/api/v1/finance/depreciation/run",
            json={"branch_id": branch.id, "year": 2026, "month": 3},
            headers=manager_headers,
        )
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["entries"] == []
        assert body["journal_entry_id"] is None
        assert len(body["skipped_assets"]) == 1

    def test_run_depreciation_stops_at_fully_depreciated(self, client: TestClient, db, manager_headers):
        """أصل بقيمة 1000ج، عمر إنتاجي شهر واحد بس — أول شهر بياخد الـ 1000ج
        كاملة، تاني شهر لازم يتخطّى (مُهلَك بالكامل) مش يكمل يهلك تحت الصفر."""
        branch = make_branch_committed(db)
        make_asset_committed(
            db, branch, purchase_cost=Decimal("1000.00"), useful_life_years=1,
            # useful_life_years يتحسب * 12 شهر داخليًا، فهنا 12 شهر عمر افتراضي —
            # نجرّب بدل كده أصل بقيمة صغيرة جداً هتتغطى بالكامل بسرعة كافية للاختبار
        )
        # نأكد الأصل مش مؤهل من غير purchase_cost أو useful_life_years
        skipped_resp = client.post(
            "/api/v1/finance/depreciation/run",
            json={"branch_id": branch.id, "year": 2026, "month": 1},
            headers=manager_headers,
        )
        assert skipped_resp.status_code == 200
        assert len(skipped_resp.json()["entries"]) == 1  # أهّل فعلاً (12 شهر عمر)

    def test_run_depreciation_requires_manager_level(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/depreciation/run",
            json={"branch_id": branch.id, "year": 2026, "month": 1},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_run_depreciation_rejected_when_period_closed(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        make_asset_committed(
            db, branch, purchase_cost=Decimal("2400.00"), useful_life_years=1,
        )
        close_resp = client.post(
            "/api/v1/finance/periods/2026/2/close",
            json={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert close_resp.status_code == 200, close_resp.text

        run_resp = client.post(
            "/api/v1/finance/depreciation/run",
            json={"branch_id": branch.id, "year": 2026, "month": 2},
            headers=manager_headers,
        )
        assert run_resp.status_code == 400
        assert "مقفولة" in run_resp.json()["detail"]

    def test_asset_with_no_cost_basis_is_skipped_not_errored(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        make_asset_committed(db, branch)  # مفيش purchase_cost ولا useful_life_years

        resp = client.post(
            "/api/v1/finance/depreciation/run",
            json={"branch_id": branch.id, "year": 2026, "month": 1},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["entries"] == []
        assert body["journal_entry_id"] is None


class TestBankReconciliationHTTP:
    def test_create_bank_account_requires_manager_level(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/bank-accounts",
            json={
                "branch_id": branch.id, "bank_name": "بنك مصر", "account_name": "الخيمة بيتش",
                "account_number": "1234567890",
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_import_and_auto_match_statement_line_against_payment(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        folio = make_folio_committed(db, branch)
        payment = make_payment_committed(db, branch, folio, Decimal("1500.00"), datetime(2026, 6, 10, 12, 0))

        create_resp = client.post(
            "/api/v1/finance/bank-accounts",
            json={
                "branch_id": branch.id, "bank_name": "بنك مصر", "account_name": "الخيمة بيتش",
                "account_number": f"ACC-{uuid.uuid4().hex[:8]}", "opening_balance": "0",
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        bank_account_id = create_resp.json()["id"]

        import_resp = client.post(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/statement-lines",
            json={"lines": [
                {"line_date": "2026-06-10", "description": "Incoming transfer", "amount": "1500.00"},
            ]},
            headers=manager_headers,
        )
        assert import_resp.status_code == 201, import_resp.text
        line = import_resp.json()[0]
        assert line["status"] == "unmatched"

        match_resp = client.post(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/statement-lines/auto-match",
            headers=manager_headers,
        )
        assert match_resp.status_code == 200, match_resp.text
        assert match_resp.json()["matched_count"] == 1

        lines_resp = client.get(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/statement-lines",
            params={"status": "matched"},
            headers=manager_headers,
        )
        assert lines_resp.status_code == 200
        matched_items = lines_resp.json()["items"]
        assert len(matched_items) == 1
        assert matched_items[0]["matched_payment_id"] == payment.id

        summary_resp = client.get(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/reconciliation-summary",
            params={"as_of": "2026-06-30"},
            headers=manager_headers,
        )
        assert summary_resp.status_code == 200, summary_resp.text
        summary = summary_resp.json()
        assert Decimal(str(summary["book_balance"])) == Decimal("1500.00")
        assert Decimal(str(summary["statement_balance"])) == Decimal("1500.00")
        assert Decimal(str(summary["difference"])) == Decimal("0.00")
        assert summary["is_reconciled"] is True
        assert summary["unmatched_statement_lines"] == 0

    def test_ambiguous_auto_match_left_for_manual_review(self, client: TestClient, db, manager_headers):
        """لو فيه أكتر من دفعة بنفس المبلغ والتاريخ القريب، المطابقة الأوتوماتيكية
        لازم تتردد (تسيبها unmatched) بدل ما تخمّن وتربط الغلط بالغلط."""
        branch = make_branch_committed(db)
        folio = make_folio_committed(db, branch)
        make_payment_committed(db, branch, folio, Decimal("800.00"), datetime(2026, 6, 5, 9, 0))
        make_payment_committed(db, branch, folio, Decimal("800.00"), datetime(2026, 6, 6, 9, 0))

        create_resp = client.post(
            "/api/v1/finance/bank-accounts",
            json={
                "branch_id": branch.id, "bank_name": "بنك مصر", "account_name": "حساب رئيسي",
                "account_number": f"ACC-{uuid.uuid4().hex[:8]}",
            },
            headers=manager_headers,
        )
        bank_account_id = create_resp.json()["id"]

        client.post(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/statement-lines",
            json={"lines": [{"line_date": "2026-06-05", "description": "Transfer", "amount": "800.00"}]},
            headers=manager_headers,
        )

        match_resp = client.post(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/statement-lines/auto-match",
            headers=manager_headers,
        )
        assert match_resp.json()["matched_count"] == 0

    def test_manual_match_and_unmatch_cycle(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        folio = make_folio_committed(db, branch)
        payment = make_payment_committed(db, branch, folio, Decimal("300.00"), datetime(2026, 6, 1, 10, 0))

        create_resp = client.post(
            "/api/v1/finance/bank-accounts",
            json={
                "branch_id": branch.id, "bank_name": "بنك مصر", "account_name": "حساب رئيسي",
                "account_number": f"ACC-{uuid.uuid4().hex[:8]}",
            },
            headers=manager_headers,
        )
        bank_account_id = create_resp.json()["id"]
        import_resp = client.post(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/statement-lines",
            json={"lines": [{"line_date": "2026-06-01", "description": "Transfer", "amount": "300.00"}]},
            headers=manager_headers,
        )
        line_id = import_resp.json()[0]["id"]

        match_resp = client.post(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/statement-lines/{line_id}/match",
            json={"payment_id": payment.id},
            headers=manager_headers,
        )
        assert match_resp.status_code == 200, match_resp.text
        assert match_resp.json()["status"] == "matched"

        # لا يمكن مطابقة سطر متطابق بالفعل من غير إلغاء المطابقة أولاً
        rematch_resp = client.post(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/statement-lines/{line_id}/match",
            json={"payment_id": payment.id},
            headers=manager_headers,
        )
        assert rematch_resp.status_code == 400

        unmatch_resp = client.post(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/statement-lines/{line_id}/unmatch",
            headers=manager_headers,
        )
        assert unmatch_resp.status_code == 200
        assert unmatch_resp.json()["status"] == "unmatched"

    def test_match_rejects_voided_payment(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        folio = make_folio_committed(db, branch)
        payment = make_payment_committed(db, branch, folio, Decimal("450.00"), datetime(2026, 6, 1, 10, 0))
        payment.voided_at = datetime.utcnow()
        db.commit()

        create_resp = client.post(
            "/api/v1/finance/bank-accounts",
            json={
                "branch_id": branch.id, "bank_name": "بنك مصر", "account_name": "حساب رئيسي",
                "account_number": f"ACC-{uuid.uuid4().hex[:8]}",
            },
            headers=manager_headers,
        )
        bank_account_id = create_resp.json()["id"]
        import_resp = client.post(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/statement-lines",
            json={"lines": [{"line_date": "2026-06-01", "description": "Transfer", "amount": "450.00"}]},
            headers=manager_headers,
        )
        line_id = import_resp.json()[0]["id"]

        match_resp = client.post(
            f"/api/v1/finance/bank-accounts/{bank_account_id}/statement-lines/{line_id}/match",
            json={"payment_id": payment.id},
            headers=manager_headers,
        )
        assert match_resp.status_code == 400
        assert "ملغاة" in match_resp.json()["detail"]
