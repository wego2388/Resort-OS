"""
tests/test_api/test_finance_http.py
HTTP-level tests for the finance module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).
Covers both the new financial reports (trial balance / income statement /
balance sheet) and the rest of the finance router surface (folios, shifts,
discounts, accounts, journal entries, periods, checks, cost centers) which
had ~0% HTTP-level coverage before this session.

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed — the
HTTP request goes through a different DB session (app.dependency_overrides
[get_db]) than the `db` fixture injected directly into the test function.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Finance HTTP Branch", name_ar="فرع مالي",
               code=f"FINH-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_account_committed(db, branch, code, name, account_type):
    from app.modules.finance.models import Account
    acc = Account(branch_id=branch.id, code=code, name=name, account_type=account_type)
    db.add(acc)
    db.commit()
    return acc


class TestTrialBalanceHTTP:
    def test_trial_balance_balances_after_posting_entries(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        cash = make_account_committed(db, branch, "1100", "Cash", "asset")
        revenue = make_account_committed(db, branch, "4100", "Room Revenue", "revenue")

        resp = client.post(
            "/api/v1/finance/journal-entries",
            json={
                "branch_id": branch.id,
                "entry_date": str(date.today()),
                "reference": "JE-HTTP-001",
                "description": "Test revenue entry",
                "lines": [
                    {"account_id": cash.id, "debit": "1000.00", "credit": "0"},
                    {"account_id": revenue.id, "debit": "0", "credit": "1000.00"},
                ],
            },
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text

        tb_resp = client.get(
            "/api/v1/finance/reports/trial-balance",
            params={"branch_id": branch.id, "as_of": str(date.today())},
            headers=manager_headers,
        )
        assert tb_resp.status_code == 200, tb_resp.text
        body = tb_resp.json()
        assert body["is_balanced"] is True
        assert Decimal(body["total_debit"]) == Decimal(body["total_credit"]) == Decimal("1000.00")
        codes = {line["account_code"] for line in body["lines"]}
        assert {"1100", "4100"} <= codes

    def test_trial_balance_excludes_future_entries(self, client: TestClient, db, manager_headers):
        """as_of في الماضي يجب ألا يشمل قيوداً بتاريخ لاحق."""
        branch = make_branch_committed(db)
        cash = make_account_committed(db, branch, "1100", "Cash", "asset")
        revenue = make_account_committed(db, branch, "4100", "Room Revenue", "revenue")

        future_date = date.today() + timedelta(days=30)
        resp = client.post(
            "/api/v1/finance/journal-entries",
            json={
                "branch_id": branch.id,
                "entry_date": str(future_date),
                "reference": "JE-HTTP-FUTURE",
                "description": "Future entry",
                "lines": [
                    {"account_id": cash.id, "debit": "500.00", "credit": "0"},
                    {"account_id": revenue.id, "debit": "0", "credit": "500.00"},
                ],
            },
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text

        tb_resp = client.get(
            "/api/v1/finance/reports/trial-balance",
            params={"branch_id": branch.id, "as_of": str(date.today())},
            headers=manager_headers,
        )
        assert tb_resp.status_code == 200, tb_resp.text
        body = tb_resp.json()
        assert body["lines"] == []
        assert Decimal(body["total_debit"]) == Decimal(body["total_credit"]) == Decimal("0")

    def test_trial_balance_requires_manager(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/finance/reports/trial-balance",
            params={"branch_id": branch.id, "as_of": str(date.today())},
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_trial_balance_missing_as_of_422(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/finance/reports/trial-balance",
            params={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert resp.status_code == 422


class TestIncomeStatementHTTP:
    def test_income_statement_computes_net_income(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        cash = make_account_committed(db, branch, "1100", "Cash", "asset")
        revenue = make_account_committed(db, branch, "4200", "Restaurant Revenue", "revenue")
        expense = make_account_committed(db, branch, "5200", "COGS", "expense")

        client.post(
            "/api/v1/finance/journal-entries",
            json={
                "branch_id": branch.id, "entry_date": str(date.today()),
                "reference": "JE-REV", "description": "Revenue",
                "lines": [
                    {"account_id": cash.id, "debit": "800.00", "credit": "0"},
                    {"account_id": revenue.id, "debit": "0", "credit": "800.00"},
                ],
            },
            headers=manager_headers,
        )
        client.post(
            "/api/v1/finance/journal-entries",
            json={
                "branch_id": branch.id, "entry_date": str(date.today()),
                "reference": "JE-EXP", "description": "Expense",
                "lines": [
                    {"account_id": expense.id, "debit": "300.00", "credit": "0"},
                    {"account_id": cash.id, "debit": "0", "credit": "300.00"},
                ],
            },
            headers=manager_headers,
        )

        resp = client.get(
            "/api/v1/finance/reports/income-statement",
            params={
                "branch_id": branch.id,
                "date_from": str(date.today() - timedelta(days=1)),
                "date_to": str(date.today()),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert Decimal(body["total_revenue"]) == Decimal("800.00")
        assert Decimal(body["total_expense"]) == Decimal("300.00")
        assert Decimal(body["net_income"]) == Decimal("500.00")

    def test_income_statement_requires_manager(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/finance/reports/income-statement",
            params={"branch_id": branch.id, "date_from": str(date.today()), "date_to": str(date.today())},
            headers=cashier_headers,
        )
        assert resp.status_code == 403


class TestBalanceSheetHTTP:
    def test_balance_sheet_balances(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        cash = make_account_committed(db, branch, "1100", "Cash", "asset")
        revenue = make_account_committed(db, branch, "4100", "Room Revenue", "revenue")

        client.post(
            "/api/v1/finance/journal-entries",
            json={
                "branch_id": branch.id, "entry_date": str(date.today()),
                "reference": "JE-BS", "description": "Revenue posting",
                "lines": [
                    {"account_id": cash.id, "debit": "1200.00", "credit": "0"},
                    {"account_id": revenue.id, "debit": "0", "credit": "1200.00"},
                ],
            },
            headers=manager_headers,
        )

        resp = client.get(
            "/api/v1/finance/reports/balance-sheet",
            params={"branch_id": branch.id, "as_of": str(date.today())},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_balanced"] is True
        assert Decimal(body["total_assets"]) == Decimal("1200.00")
        assert Decimal(body["retained_earnings"]) == Decimal("1200.00")
        assert Decimal(body["total_liabilities_and_equity"]) == Decimal(body["total_assets"])

    def test_balance_sheet_with_liability_and_expense_still_balances(self, client: TestClient, db, manager_headers):
        """Assets = Liabilities + Equity + Retained Earnings حتى مع خصوم ومصروفات."""
        branch = make_branch_committed(db)
        cash = make_account_committed(db, branch, "1100", "Cash", "asset")
        revenue = make_account_committed(db, branch, "4100", "Room Revenue", "revenue")
        payable = make_account_committed(db, branch, "2100", "Tax Payable", "liability")
        expense = make_account_committed(db, branch, "5100", "Salaries Expense", "expense")

        client.post(
            "/api/v1/finance/journal-entries",
            json={
                "branch_id": branch.id, "entry_date": str(date.today()),
                "reference": "JE-BS-REV", "description": "Revenue",
                "lines": [
                    {"account_id": cash.id, "debit": "2000.00", "credit": "0"},
                    {"account_id": revenue.id, "debit": "0", "credit": "2000.00"},
                ],
            },
            headers=manager_headers,
        )
        client.post(
            "/api/v1/finance/journal-entries",
            json={
                "branch_id": branch.id, "entry_date": str(date.today()),
                "reference": "JE-BS-EXP", "description": "Accrued salary expense",
                "lines": [
                    {"account_id": expense.id, "debit": "600.00", "credit": "0"},
                    {"account_id": payable.id, "debit": "0", "credit": "600.00"},
                ],
            },
            headers=manager_headers,
        )

        resp = client.get(
            "/api/v1/finance/reports/balance-sheet",
            params={"branch_id": branch.id, "as_of": str(date.today())},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_balanced"] is True
        assert Decimal(body["total_assets"]) == Decimal("2000.00")
        assert Decimal(body["total_liabilities"]) == Decimal("600.00")
        assert Decimal(body["retained_earnings"]) == Decimal("1400.00")  # 2000 revenue - 600 expense
        assert Decimal(body["total_liabilities_and_equity"]) == Decimal("2000.00")

    def test_balance_sheet_requires_manager(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/finance/reports/balance-sheet",
            params={"branch_id": branch.id, "as_of": str(date.today())},
            headers=cashier_headers,
        )
        assert resp.status_code == 403


class TestFolioHTTPFlow:
    def test_full_folio_lifecycle(self, client: TestClient, db, cashier_headers, manager_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/finance/folios",
            json={
                "branch_id": branch.id, "guest_name": "ضيف HTTP",
                "check_in": datetime.utcnow().isoformat(),
                "check_out": (datetime.utcnow() + timedelta(days=2)).isoformat(),
            },
            headers=cashier_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        folio_id = create_resp.json()["id"]

        get_resp = client.get(f"/api/v1/finance/folios/{folio_id}", headers=cashier_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "open"

        charge_resp = client.post(
            f"/api/v1/finance/folios/{folio_id}/charges",
            json={
                "charge_type": "room", "description": "إيجار ليلة",
                "amount": "500.00", "vat_amount": "70.00",
                "posted_at": datetime.utcnow().isoformat(),
            },
            headers=cashier_headers,
        )
        assert charge_resp.status_code == 201, charge_resp.text

        # لا يمكن الـ checkout قبل تسوية الرصيد المستحق
        settle_before_pay = client.post(f"/api/v1/finance/folios/{folio_id}/settle", headers=cashier_headers)
        assert settle_before_pay.status_code == 400
        assert "غير مسدد" in settle_before_pay.json()["detail"]

        pay_resp = client.post(
            f"/api/v1/finance/folios/{folio_id}/payments",
            json={
                "folio_id": folio_id, "branch_id": branch.id, "amount": "570.00",
                "method": "cash", "posted_at": datetime.utcnow().isoformat(),
            },
            headers=cashier_headers,
        )
        assert pay_resp.status_code == 201, pay_resp.text

        pdf_resp = client.get(f"/api/v1/finance/folios/{folio_id}/statement/pdf", headers=cashier_headers)
        assert pdf_resp.status_code == 200
        assert pdf_resp.content.startswith(b"%PDF")

        excel_resp = client.get(
            "/api/v1/finance/folios/report/export", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert excel_resp.status_code == 200

    def test_get_nonexistent_folio_404(self, client: TestClient, db, cashier_headers):
        resp = client.get("/api/v1/finance/folios/999999", headers=cashier_headers)
        assert resp.status_code == 404

    def test_post_charge_invalid_type_400(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        folio_resp = client.post(
            "/api/v1/finance/folios",
            json={
                "branch_id": branch.id, "guest_name": "ضيف",
                "check_in": datetime.utcnow().isoformat(),
                "check_out": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            },
            headers=cashier_headers,
        )
        folio_id = folio_resp.json()["id"]
        resp = client.post(
            f"/api/v1/finance/folios/{folio_id}/charges",
            json={
                "charge_type": "bogus_type", "description": "غير معروف",
                "amount": "50.00", "posted_at": datetime.utcnow().isoformat(),
            },
            headers=cashier_headers,
        )
        assert resp.status_code == 400

    def test_statement_pdf_404_for_missing_folio(self, client: TestClient, db, cashier_headers):
        resp = client.get("/api/v1/finance/folios/999999/statement/pdf", headers=cashier_headers)
        assert resp.status_code == 404

    def test_list_folios_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/finance/folios", params={"branch_id": branch.id}, headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_list_folios_success(self, client: TestClient, db, manager_headers, cashier_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/finance/folios",
            json={
                "branch_id": branch.id, "guest_name": "ضيف للقائمة",
                "check_in": datetime.utcnow().isoformat(),
                "check_out": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            },
            headers=cashier_headers,
        )
        folio_id = create_resp.json()["id"]

        resp = client.get(
            "/api/v1/finance/folios", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert resp.status_code == 200
        assert any(f["id"] == folio_id for f in resp.json()["items"])

    def test_add_payment_to_nonexistent_folio_400(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/folios/999999/payments",
            json={
                "folio_id": 999999, "branch_id": branch.id, "amount": "100.00",
                "method": "cash", "posted_at": datetime.utcnow().isoformat(),
            },
            headers=cashier_headers,
        )
        assert resp.status_code == 400


class TestVoidPaymentAndRevenueAuditLogHTTP:
    """Regression coverage — services.void_payment/crud.void_payment existed
    in full but had zero router endpoint (payments could never be voided via
    the API). RevenueAuditLog had the same bug at the model level (no
    schema/crud/router at all) — now populated automatically by void_payment
    and exposed read-only via GET /finance/revenue-audit-logs."""

    def _make_folio_with_payment(self, client, branch, cashier_headers, amount="570.00"):
        folio_resp = client.post(
            "/api/v1/finance/folios",
            json={
                "branch_id": branch.id, "guest_name": "ضيف",
                "check_in": datetime.utcnow().isoformat(),
                "check_out": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            },
            headers=cashier_headers,
        )
        folio_id = folio_resp.json()["id"]
        pay_resp = client.post(
            f"/api/v1/finance/folios/{folio_id}/payments",
            json={
                "folio_id": folio_id, "branch_id": branch.id, "amount": amount,
                "method": "cash", "posted_at": datetime.utcnow().isoformat(),
            },
            headers=cashier_headers,
        )
        return folio_id, pay_resp.json()

    def test_void_payment_writes_revenue_audit_log(self, client: TestClient, db, cashier_headers, manager_headers):
        branch = make_branch_committed(db)
        _, payment = self._make_folio_with_payment(client, branch, cashier_headers)

        void_resp = client.post(
            f"/api/v1/finance/payments/{payment['id']}/void",
            json={"reason": "الضيف دفع بالخطأ مرتين"},
            headers=manager_headers,
        )
        assert void_resp.status_code == 200, void_resp.text
        voided = void_resp.json()
        assert voided["voided_at"] is not None

        logs_resp = client.get(
            "/api/v1/finance/revenue-audit-logs",
            params={"branch_id": branch.id, "entity_type": "payment", "entity_id": payment["id"]},
            headers=manager_headers,
        )
        assert logs_resp.status_code == 200, logs_resp.text
        logs = logs_resp.json()
        assert len(logs) == 1
        assert logs[0]["entity_type"] == "payment"
        assert logs[0]["old_value"] == "570.00"
        assert logs[0]["new_value"] == "0.00"
        assert logs[0]["reason"] == "الضيف دفع بالخطأ مرتين"

    def test_cannot_void_already_voided_payment(
        self, client: TestClient, db, cashier_headers, manager_headers,
    ):
        """Regression: void_payment ما كانتش بتتحقق من voided_at قبل كده —
        نفس الدفعة كانت تتلغي أكتر من مرة، كل مرة بتكتب سطر RevenueAuditLog
        جديد (كأن 570 جنيه اتلغت تاني من الصفر) وبتدهس voided_at/voided_by
        الأصليين — يعني مراجع الحسابات يفقد مين ألغى الدفعة فعليًا وإمتى."""
        branch = make_branch_committed(db)
        _, payment = self._make_folio_with_payment(client, branch, cashier_headers)

        first = client.post(
            f"/api/v1/finance/payments/{payment['id']}/void",
            json={"reason": "إلغاء أول مرة"}, headers=manager_headers,
        )
        assert first.status_code == 200, first.text

        second = client.post(
            f"/api/v1/finance/payments/{payment['id']}/void",
            json={"reason": "محاولة إلغاء تانية"}, headers=manager_headers,
        )
        assert second.status_code == 400, second.text
        assert "ملغاة بالفعل" in second.json()["detail"]

        logs_resp = client.get(
            "/api/v1/finance/revenue-audit-logs",
            params={"branch_id": branch.id, "entity_type": "payment", "entity_id": payment["id"]},
            headers=manager_headers,
        )
        # سطر تدقيق واحد بس — مش اتنين لعملية إلغاء واحدة فعلية
        assert len(logs_resp.json()) == 1

    def test_void_payment_rejects_short_reason(self, client: TestClient, db, cashier_headers, manager_headers):
        branch = make_branch_committed(db)
        _, payment = self._make_folio_with_payment(client, branch, cashier_headers)

        resp = client.post(
            f"/api/v1/finance/payments/{payment['id']}/void",
            json={"reason": "x"},
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_void_nonexistent_payment_400(self, client: TestClient, db, manager_headers):
        resp = client.post(
            "/api/v1/finance/payments/999999/void",
            json={"reason": "دفعة غير موجودة"},
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_void_payment_requires_manager(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        _, payment = self._make_folio_with_payment(client, branch, cashier_headers)

        resp = client.post(
            f"/api/v1/finance/payments/{payment['id']}/void",
            json={"reason": "محاولة كاشير"},
            headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_revenue_audit_logs_requires_manager(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/finance/revenue-audit-logs", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert resp.status_code == 403


class TestCashierShiftHTTPFlow:
    def test_full_shift_lifecycle(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        open_resp = client.post(
            "/api/v1/finance/shifts/open",
            json={"branch_id": branch.id, "opening_float": "200.00"},
            headers=cashier_headers,
        )
        assert open_resp.status_code == 201, open_resp.text
        shift_id = open_resp.json()["id"]

        # لا يمكن فتح وردية ثانية لنفس الكاشير قبل ما يقفل الأولى
        dup_resp = client.post(
            "/api/v1/finance/shifts/open",
            json={"branch_id": branch.id, "opening_float": "0"},
            headers=cashier_headers,
        )
        assert dup_resp.status_code == 400

        current_resp = client.get(
            "/api/v1/finance/shifts/current", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert current_resp.status_code == 200
        assert current_resp.json()["id"] == shift_id

        report_resp = client.get(f"/api/v1/finance/shifts/{shift_id}/report", headers=cashier_headers)
        assert report_resp.status_code == 200
        assert report_resp.json()["opening_float"] == "200.00"

        pdf_resp = client.get(f"/api/v1/finance/shifts/{shift_id}/report/pdf", headers=cashier_headers)
        assert pdf_resp.status_code == 200
        assert pdf_resp.content.startswith(b"%PDF")

        close_resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={"counted_cash": "200.00"},
            headers=cashier_headers,
        )
        assert close_resp.status_code == 200, close_resp.text
        assert close_resp.json()["status"] == "closed"
        assert close_resp.json()["variance"] == "0.00"

        # لا يمكن قفل وردية مقفولة بالفعل
        reclose_resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={"counted_cash": "200.00"},
            headers=cashier_headers,
        )
        assert reclose_resp.status_code == 400

    def _open_shift_with_cash_sale(
        self, client: TestClient, cashier_headers, branch_id: int,
        opening_float: str, sale_amount: str,
    ) -> int:
        """يفتح وردية ويسجّل دفعة كاش حقيقية عليها (مبيعات فعلية) — بيرجع shift_id.
        Helper مشترك للاختبارات تحت (كلهم محتاجين نفس الإعداد: وردية + مبيعات
        كاش حقيقية تسجّل عبر HTTP، مش استدعاء مباشر للـ service)."""
        open_resp = client.post(
            "/api/v1/finance/shifts/open",
            json={"branch_id": branch_id, "opening_float": opening_float},
            headers=cashier_headers,
        )
        assert open_resp.status_code == 201, open_resp.text
        shift_id = open_resp.json()["id"]

        folio_resp = client.post(
            "/api/v1/finance/folios",
            json={
                "branch_id": branch_id, "guest_name": "ضيف مطابقة الكاش",
                "check_in": datetime.utcnow().isoformat(),
                "check_out": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            },
            headers=cashier_headers,
        )
        assert folio_resp.status_code == 201, folio_resp.text
        folio_id = folio_resp.json()["id"]

        pay_resp = client.post(
            f"/api/v1/finance/folios/{folio_id}/payments",
            json={
                "folio_id": folio_id, "branch_id": branch_id, "amount": sale_amount,
                "method": "cash", "posted_at": datetime.utcnow().isoformat(),
            },
            headers=cashier_headers,
        )
        assert pay_resp.status_code == 201, pay_resp.text
        return shift_id

    def test_close_shift_within_tolerance_reconciliation_ok(self, client: TestClient, db, cashier_headers):
        """فرق كاش صغير جدًا (تفكة/تقريب طبيعي) — الوردية تتقفل عادي وبدون
        أي تحذير: reconciliation_ok=True وreconciliation_warning=None."""
        branch = make_branch_committed(db)
        # افتتاح 500 + مبيعات كاش 300 = متوقع 800 — الكاشير يعدّ 810 (فرق +10 بس)
        shift_id = self._open_shift_with_cash_sale(
            client, cashier_headers, branch.id, opening_float="500.00", sale_amount="300.00",
        )

        close_resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={"counted_cash": "810.00"},
            headers=cashier_headers,
        )
        assert close_resp.status_code == 200, close_resp.text
        body = close_resp.json()
        assert body["status"] == "closed"
        assert body["expected_cash"] == "800.00"
        assert body["variance"] == "10.00"
        assert body["reconciliation_ok"] is True
        assert body["reconciliation_warning"] is None

    def test_close_shift_flags_moderate_variance_but_still_closes(self, client: TestClient, db, cashier_headers):
        """فرق أكبر من التفكة الطبيعية (150ج) لكن لسه أقل من حد الرفض
        (10% من 1000ج مبيعات = 100ج، أو 200ج كحد أدنى مطلق أيهما أكبر → 200ج) —
        الوردية تتقفل لكن reconciliation_warning لازم يظهر للمدير."""
        branch = make_branch_committed(db)
        shift_id = self._open_shift_with_cash_sale(
            client, cashier_headers, branch.id, opening_float="0.00", sale_amount="1000.00",
        )

        close_resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={"counted_cash": "1150.00"},  # فرق +150ج
            headers=cashier_headers,
        )
        assert close_resp.status_code == 200, close_resp.text
        body = close_resp.json()
        assert body["status"] == "closed"
        assert body["variance"] == "150.00"
        assert body["reconciliation_ok"] is False
        assert body["reconciliation_warning"] is not None
        assert "مراجعة المدير" in body["reconciliation_warning"]

    def test_close_shift_rejects_large_cash_variance_against_sales(self, client: TestClient, db, cashier_headers):
        """فجوة #14 الحرجة (wagdy.md): فرق كاش ضخم نسبةً لمبيعات الوردية
        (4000ج فرق على 1000ج مبيعات فقط) لازم يترفض بـ 400 — مش يتسجل بصمت.
        الوردية لازم تفضل مفتوحة (status='open') بعد الرفض، مش مقفولة بفرق
        غير مراجَع."""
        branch = make_branch_committed(db)
        shift_id = self._open_shift_with_cash_sale(
            client, cashier_headers, branch.id, opening_float="0.00", sale_amount="1000.00",
        )

        close_resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={"counted_cash": "5000.00"},  # فرق +4000ج — غير معقول إطلاقًا
            headers=cashier_headers,
        )
        assert close_resp.status_code == 400, close_resp.text
        assert "يتخطى الحد المسموح" in close_resp.json()["detail"]

        # الوردية لازم تفضل مفتوحة — الرفض ما كسرش حالتها ولا كتب أي بيانات جزئية
        current_resp = client.get(
            "/api/v1/finance/shifts/current", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert current_resp.status_code == 200
        assert current_resp.json()["id"] == shift_id
        assert current_resp.json()["status"] == "open"
        assert current_resp.json()["counted_cash"] is None

    def test_blind_cash_count_never_reveals_expected_cash_before_close(
        self, client: TestClient, db, cashier_headers,
    ):
        """عدّ الكاش لازم يكون 'أعمى' (blind count): الكاشير يعدّ الدرج فعليًا
        ويبعت رقمه *قبل* ما يشوف أي رقم متوقع من النظام — وإلا هيعدّ لحد ما
        يوصل للرقم المتوقع بدل ما يبلّغ عن عجز حقيقي. راجع best practice في
        Foodics/Square. الباك إند هنا بيحسب expected_cash بس وقت القفل نفسه
        (services.close_shift، سطر ~488) — قبل كده العمود فاضل NULL. الاختبار
        ده بيتأكد من السلوك ده فعليًا عبر HTTP، مش بس بيفترضه."""
        branch = make_branch_committed(db)
        open_resp = client.post(
            "/api/v1/finance/shifts/open",
            json={"branch_id": branch.id, "opening_float": "500.00"},
            headers=cashier_headers,
        )
        assert open_resp.status_code == 201, open_resp.text
        shift_id = open_resp.json()["id"]

        # فولية ودفعة كاش حقيقية أثناء الوردية — عشان expected_cash يبقى رقم
        # حقيقي غير صفري (500 افتتاح + 300 كاش = 800)، مش حالة تافهة.
        folio_resp = client.post(
            "/api/v1/finance/folios",
            json={
                "branch_id": branch.id, "guest_name": "ضيف عدّ أعمى",
                "check_in": datetime.utcnow().isoformat(),
                "check_out": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            },
            headers=cashier_headers,
        )
        assert folio_resp.status_code == 201, folio_resp.text
        folio_id = folio_resp.json()["id"]
        pay_resp = client.post(
            f"/api/v1/finance/folios/{folio_id}/payments",
            json={
                "folio_id": folio_id, "branch_id": branch.id, "amount": "300.00",
                "method": "cash", "posted_at": datetime.utcnow().isoformat(),
            },
            headers=cashier_headers,
        )
        assert pay_resp.status_code == 201, pay_resp.text

        # الكاشير بيشوف حالة ورديته (زي أي شاشة POS) — لازم مايشوفش أي رقم
        # متوقع هنا، وإلا هيقدر يعدّل عدّه ليطابقه بدل ما يبلّغ عن عجز حقيقي.
        current_resp = client.get(
            "/api/v1/finance/shifts/current", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert current_resp.status_code == 200
        assert current_resp.json()["expected_cash"] is None
        assert current_resp.json()["variance"] is None

        # حتى لو عميل (frontend مخترق أو buggy) بعت expected_cash في جسم
        # طلب القفل نفسه، لازم يتجاهله السيرفر تمامًا ويحسب قيمته الحقيقية
        # بنفسه من الدفعات الفعلية — الرقم المتوقع لازم يفضل server-authoritative.
        close_resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={"counted_cash": "750.00", "expected_cash": "750.00"},
            headers=cashier_headers,
        )
        assert close_resp.status_code == 200, close_resp.text
        body = close_resp.json()
        # الرقم المتوقع الحقيقي (800) لازم يظهر في الرد بعد القفل — مش الرقم
        # اللي حاول العميل يفرضه (750) — ده دليل إن الحساب سيرفر-سايد فعليًا.
        assert body["expected_cash"] == "800.00"
        assert body["counted_cash"] == "750.00"
        assert body["variance"] == "-50.00"

    def test_get_current_shift_404_when_none_open(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/finance/shifts/current", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert resp.status_code == 404

    def test_shift_report_404_for_missing_shift(self, client: TestClient, db, cashier_headers):
        resp = client.get("/api/v1/finance/shifts/999999/report", headers=cashier_headers)
        assert resp.status_code == 404

    def test_shift_report_pdf_404_for_missing_shift(self, client: TestClient, db, cashier_headers):
        resp = client.get("/api/v1/finance/shifts/999999/report/pdf", headers=cashier_headers)
        assert resp.status_code == 404

    def test_list_shifts_requires_manager_role(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/finance/shifts", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert resp.status_code == 403

    def test_list_shifts_success(self, client: TestClient, db, manager_headers, cashier_headers):
        branch = make_branch_committed(db)
        open_resp = client.post(
            "/api/v1/finance/shifts/open",
            json={"branch_id": branch.id, "opening_float": "100.00"},
            headers=cashier_headers,
        )
        shift_id = open_resp.json()["id"]

        resp = client.get(
            "/api/v1/finance/shifts", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert resp.status_code == 200
        assert any(s["id"] == shift_id for s in resp.json()["items"])


class TestCashMovementHTTP:
    """Cash Control ledger (Operations & Control Layer plan §3.2، Batch 2) —
    قرار Mohamed 2026-07-13: الكاشير صفر صلاحية على أي حركة كاش يدوية، أي
    مستوى أقل من مدير محتاج PIN دايمًا. راجع Batch 4 (سياسة رؤية سجل
    التدقيق): GET يقتصر على مدير+ بالظبط زي /audit-logs."""

    def _open_shift(self, client, headers, branch_id) -> int:
        resp = client.post(
            "/api/v1/finance/shifts/open",
            json={"branch_id": branch_id, "opening_float": "500.00"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def test_cashier_movement_without_pin_rejected(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        shift_id = self._open_shift(client, cashier_headers, branch.id)
        resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/cash-movements",
            json={"movement_type": "correction", "amount": "50.00", "reason": "تصحيح عدّ الكاش"},
            headers=cashier_headers,
        )
        assert resp.status_code == 400
        assert "موافقة" in resp.json()["detail"]

    def test_manager_movement_self_qualified(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        shift_id = self._open_shift(client, manager_headers, branch.id)
        resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/cash-movements",
            json={"movement_type": "drawer_open", "amount": "0", "reason": "فحص روتيني للدرج"},
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["approved_by"] is None

    def test_cashier_movement_with_valid_manager_pin_succeeds(
        self, client: TestClient, db, cashier_headers, manager_headers,
    ):
        manager_id = _set_shift_pin(db, "manager@test.local", "6688")
        branch = make_branch_committed(db)
        shift_id = self._open_shift(client, cashier_headers, branch.id)
        resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/cash-movements",
            json={
                "movement_type": "safe_drop", "amount": "400.00", "reason": "تنزيل خزنة",
                "approver_user_id": manager_id, "approver_pin": "6688",
            },
            headers=cashier_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["approved_by"] == manager_id

    def test_cashier_cannot_list_cash_movements(self, client: TestClient, db, cashier_headers, manager_headers):
        """راجع Batch 4 — سجل حركات الكاش تفصيل من سجل التدقيق (مين نفّذ/
        وافق)، زي /audit-logs بالظبط: مدير+ فقط، كاشير يترفض بـ 403."""
        manager_id = _set_shift_pin(db, "manager@test.local", "6699")
        branch = make_branch_committed(db)
        shift_id = self._open_shift(client, cashier_headers, branch.id)
        client.post(
            f"/api/v1/finance/shifts/{shift_id}/cash-movements",
            json={
                "movement_type": "cash_in", "amount": "100.00", "reason": "عهدة",
                "approver_user_id": manager_id, "approver_pin": "6699",
            },
            headers=cashier_headers,
        )
        forbidden = client.get(f"/api/v1/finance/shifts/{shift_id}/cash-movements", headers=cashier_headers)
        assert forbidden.status_code == 403

        allowed = client.get(f"/api/v1/finance/shifts/{shift_id}/cash-movements", headers=manager_headers)
        assert allowed.status_code == 200
        assert len(allowed.json()) == 1


def _set_shift_pin(db, email: str, pin: str) -> int:
    """نفس نمط _set_pin في test_restaurant_http.py — يضبط PIN حقيقي عبر
    core.services (مش تلاعب مباشر بالداتابيز) ويرجّع user.id."""
    from app.core.kernel.models.user import User
    from app.modules.core import services as core_services

    user = db.query(User).filter(User.email == email).first()
    core_services.set_pin(db, user.id, pin, created_by=user.id)
    db.commit()
    return user.id


def _second_cashier_headers(db) -> dict[str, str]:
    """كاشير تاني (مختلف عن fixture cashier_headers) — لازم لاختبارات عزل
    البيانات بين ورديات الكاشيرية المختلفة (S-02: كاشير لا يرى وردية غيره)."""
    import os
    from datetime import datetime, timedelta

    from jose import jwt

    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash

    email = "cashier2@test.local"
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email, password_hash=get_password_hash("Test@12345"),
            full_name="Test cashier2", role="cashier", is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    secret = os.environ["SECRET_KEY"]
    now = datetime.utcnow()
    token = jwt.encode(
        {"sub": email, "iat": now, "exp": now + timedelta(hours=1)}, secret, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class TestShiftInvoicesHTTP:
    """GET /finance/shifts/{shift_id}/invoices — wagdy.md بند S-02: سجل
    فواتير الوردية، مقصور على كاشير الوردية نفسه + محتاج موافقة PIN مدير+
    (راجع services.list_shift_invoices وPinGuardModal)."""

    def _open_shift_with_paid_folio(
        self, client: TestClient, cashier_headers, branch_id: int, guest_name: str, amount: str,
    ) -> tuple[int, int]:
        open_resp = client.post(
            "/api/v1/finance/shifts/open",
            json={"branch_id": branch_id, "opening_float": "0"},
            headers=cashier_headers,
        )
        assert open_resp.status_code == 201, open_resp.text
        shift_id = open_resp.json()["id"]

        folio_resp = client.post(
            "/api/v1/finance/folios",
            json={
                "branch_id": branch_id, "guest_name": guest_name,
                "check_in": datetime.utcnow().isoformat(),
                "check_out": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            },
            headers=cashier_headers,
        )
        assert folio_resp.status_code == 201, folio_resp.text
        folio_id = folio_resp.json()["id"]

        pay_resp = client.post(
            f"/api/v1/finance/folios/{folio_id}/payments",
            json={
                "folio_id": folio_id, "branch_id": branch_id, "amount": amount,
                "method": "cash", "posted_at": datetime.utcnow().isoformat(),
            },
            headers=cashier_headers,
        )
        assert pay_resp.status_code == 201, pay_resp.text
        return shift_id, pay_resp.json()["id"]

    def test_manager_lists_invoices_without_pin(self, client: TestClient, db, cashier_headers, manager_headers):
        branch = make_branch_committed(db)
        shift_id, payment_id = self._open_shift_with_paid_folio(
            client, cashier_headers, branch.id, "ضيف سجل الفواتير", "150.00",
        )

        resp = client.get(f"/api/v1/finance/shifts/{shift_id}/invoices", headers=manager_headers)
        assert resp.status_code == 200, resp.text
        lines = resp.json()
        assert len(lines) == 1
        assert lines[0]["payment_id"] == payment_id
        assert lines[0]["guest_name"] == "ضيف سجل الفواتير"
        assert Decimal(lines[0]["amount"]) == Decimal("150.00")
        assert lines[0]["is_voided"] is False

    def test_cashier_own_shift_requires_pin_approval(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        shift_id, _ = self._open_shift_with_paid_folio(
            client, cashier_headers, branch.id, "ضيف بدون موافقة", "50.00",
        )

        resp = client.get(f"/api/v1/finance/shifts/{shift_id}/invoices", headers=cashier_headers)
        assert resp.status_code == 400
        assert "PIN" in resp.json()["detail"] or "موافقة" in resp.json()["detail"]

    def test_cashier_own_shift_with_manager_pin_succeeds(
        self, client: TestClient, db, cashier_headers, manager_headers,
    ):
        manager_id = _set_shift_pin(db, "manager@test.local", "4321")
        branch = make_branch_committed(db)
        shift_id, payment_id = self._open_shift_with_paid_folio(
            client, cashier_headers, branch.id, "ضيف بموافقة مدير", "75.00",
        )

        resp = client.get(
            f"/api/v1/finance/shifts/{shift_id}/invoices",
            params={"approver_user_id": manager_id, "approver_pin": "4321"},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()[0]["payment_id"] == payment_id

    def test_cashier_own_shift_wrong_pin_rejected(self, client: TestClient, db, cashier_headers, manager_headers):
        manager_id = _set_shift_pin(db, "manager@test.local", "4321")
        branch = make_branch_committed(db)
        shift_id, _ = self._open_shift_with_paid_folio(
            client, cashier_headers, branch.id, "ضيف PIN غلط", "25.00",
        )

        resp = client.get(
            f"/api/v1/finance/shifts/{shift_id}/invoices",
            params={"approver_user_id": manager_id, "approver_pin": "0000"},
            headers=cashier_headers,
        )
        assert resp.status_code == 400

    def test_cashier_cannot_view_other_cashiers_shift(self, client: TestClient, db, cashier_headers, manager_headers):
        """⚠️ عزل بيانات إجباري (S-02): حتى مع موافقة PIN مدير صحيحة، كاشير
        مايشوفش وردية كاشير تاني خالص — 403 مش 400."""
        manager_id = _set_shift_pin(db, "manager@test.local", "4321")
        branch = make_branch_committed(db)
        shift_id, _ = self._open_shift_with_paid_folio(
            client, cashier_headers, branch.id, "ضيف كاشير أول", "60.00",
        )

        other_headers = _second_cashier_headers(db)
        resp = client.get(
            f"/api/v1/finance/shifts/{shift_id}/invoices",
            params={"approver_user_id": manager_id, "approver_pin": "4321"},
            headers=other_headers,
        )
        assert resp.status_code == 403

    def test_invoices_404_for_missing_shift(self, client: TestClient, db, manager_headers):
        resp = client.get("/api/v1/finance/shifts/999999/invoices", headers=manager_headers)
        assert resp.status_code == 400

    def test_voided_payment_shows_is_voided_true(
        self, client: TestClient, db, cashier_headers, manager_headers,
    ):
        branch = make_branch_committed(db)
        shift_id, payment_id = self._open_shift_with_paid_folio(
            client, cashier_headers, branch.id, "ضيف فاتورة ملغاة", "40.00",
        )
        void_resp = client.post(
            f"/api/v1/finance/payments/{payment_id}/void",
            json={"reason": "خطأ في التسجيل"},
            headers=manager_headers,
        )
        assert void_resp.status_code == 200, void_resp.text

        resp = client.get(f"/api/v1/finance/shifts/{shift_id}/invoices", headers=manager_headers)
        assert resp.status_code == 200
        assert resp.json()[0]["is_voided"] is True
        assert resp.json()[0]["voided_at"] is not None


class TestCloseShiftVarianceOverrideHTTP:
    """POST /finance/shifts/{shift_id}/close مع force_close — wagdy.md بند
    S-06: فرق كاش أكبر من الحد المسموح بيترفض القفل افتراضيًا (400)، إلا لو
    force_close=true مع موافقة PIN مدير+ (أو المنفّذ نفسه مدير+)."""

    def _open_shift_with_cash_sale(
        self, client: TestClient, headers, branch_id: int, opening_float: str, sale_amount: str,
    ) -> int:
        open_resp = client.post(
            "/api/v1/finance/shifts/open",
            json={"branch_id": branch_id, "opening_float": opening_float},
            headers=headers,
        )
        assert open_resp.status_code == 201, open_resp.text
        shift_id = open_resp.json()["id"]

        folio_resp = client.post(
            "/api/v1/finance/folios",
            json={
                "branch_id": branch_id, "guest_name": "ضيف تخطي الفرق",
                "check_in": datetime.utcnow().isoformat(),
                "check_out": (datetime.utcnow() + timedelta(days=1)).isoformat(),
            },
            headers=headers,
        )
        assert folio_resp.status_code == 201, folio_resp.text
        folio_id = folio_resp.json()["id"]

        pay_resp = client.post(
            f"/api/v1/finance/folios/{folio_id}/payments",
            json={
                "folio_id": folio_id, "branch_id": branch_id, "amount": sale_amount,
                "method": "cash", "posted_at": datetime.utcnow().isoformat(),
            },
            headers=headers,
        )
        assert pay_resp.status_code == 201, pay_resp.text
        return shift_id

    def test_force_close_without_pin_still_rejected(self, client: TestClient, db, cashier_headers):
        """force_close=true من غير approver_user_id/approver_pin — لازم
        يترفض برضو (كاشير مش مؤهّل يعتمد نفسه)."""
        branch = make_branch_committed(db)
        shift_id = self._open_shift_with_cash_sale(
            client, cashier_headers, branch.id, opening_float="0.00", sale_amount="1000.00",
        )

        resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={"counted_cash": "5000.00", "force_close": True},
            headers=cashier_headers,
        )
        assert resp.status_code == 400
        assert "PIN" in resp.json()["detail"] or "موافقة" in resp.json()["detail"]

        # الوردية لازم تفضل مفتوحة — نفس ضمان test_close_shift_rejects_large_cash_variance_against_sales
        current_resp = client.get(
            "/api/v1/finance/shifts/current", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert current_resp.json()["status"] == "open"

    def test_force_close_with_wrong_pin_rejected(self, client: TestClient, db, cashier_headers, manager_headers):
        manager_id = _set_shift_pin(db, "manager@test.local", "7777")
        branch = make_branch_committed(db)
        shift_id = self._open_shift_with_cash_sale(
            client, cashier_headers, branch.id, opening_float="0.00", sale_amount="1000.00",
        )

        resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={
                "counted_cash": "5000.00", "force_close": True,
                "approver_user_id": manager_id, "approver_pin": "0000",
            },
            headers=cashier_headers,
        )
        assert resp.status_code == 400

    def test_force_close_with_correct_manager_pin_succeeds_and_audits(
        self, client: TestClient, db, cashier_headers, manager_headers,
    ):
        manager_id = _set_shift_pin(db, "manager@test.local", "7777")
        branch = make_branch_committed(db)
        shift_id = self._open_shift_with_cash_sale(
            client, cashier_headers, branch.id, opening_float="0.00", sale_amount="1000.00",
        )

        resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={
                "counted_cash": "5000.00", "force_close": True,
                "approver_user_id": manager_id, "approver_pin": "7777",
            },
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "closed"
        assert body["variance"] == "4000.00"

        # AuditLog إجباري يوثّق مين وافق على تخطي الحد (راجع services.close_shift)
        logs_resp = client.get(
            "/api/v1/audit-logs",
            params={"branch_id": branch.id, "entity_type": "cashier_shift", "entity_id": shift_id},
            headers=manager_headers,
        )
        assert logs_resp.status_code == 200
        items = logs_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["action"] == "close_shift_variance_override"
        assert items[0]["approved_by"] == manager_id

    def test_manager_closing_own_shift_self_qualifies_no_pin_needed(
        self, client: TestClient, db, manager_headers,
    ):
        """مدير (level 60) بيقفل ورديته هو نفسه بفرق كبير — مؤهّل بنفسه من
        غير موافقة PIN منفصلة (نفس مبدأ resolve_pin_approval للأدوار الأعلى)."""
        branch = make_branch_committed(db)
        shift_id = self._open_shift_with_cash_sale(
            client, manager_headers, branch.id, opening_float="0.00", sale_amount="1000.00",
        )

        resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={"counted_cash": "5000.00", "force_close": True},
            headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "closed"

    def test_force_close_ignored_when_variance_within_threshold(self, client: TestClient, db, cashier_headers):
        """force_close=true لكن الفرق أصلاً داخل الحد المسموح — قفل عادي، من
        غير أي حاجة لموافقة PIN (مفيش تجاوز لازم يعتمد أصلاً)."""
        branch = make_branch_committed(db)
        shift_id = self._open_shift_with_cash_sale(
            client, cashier_headers, branch.id, opening_float="0.00", sale_amount="1000.00",
        )

        resp = client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={"counted_cash": "1000.00", "force_close": True},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["variance"] == "0.00"


class TestDiscountHTTPFlow:
    def test_create_list_update_delete_discount(self, client: TestClient, db, manager_headers, super_admin_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/finance/discounts",
            json={
                "branch_id": branch.id, "condition_type": "total_amount", "condition_value": ">=100",
                "discount_type": "percentage", "discount_value": "10",
                "valid_from": str(date.today() - timedelta(days=1)),
                "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=super_admin_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        discount_id = create_resp.json()["id"]

        list_resp = client.get(
            "/api/v1/finance/discounts", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        assert any(d["id"] == discount_id for d in list_resp.json()["items"])

        update_resp = client.patch(
            f"/api/v1/finance/discounts/{discount_id}",
            json={"discount_value": "15"},
            headers=super_admin_headers,
        )
        assert update_resp.status_code == 200
        assert Decimal(update_resp.json()["discount_value"]) == Decimal("15")

        delete_resp = client.delete(f"/api/v1/finance/discounts/{discount_id}", headers=super_admin_headers)
        assert delete_resp.status_code == 204

        # اتحذف فعلاً — تحديثه تاني لازم يرجّع 404
        redelete_resp = client.delete(f"/api/v1/finance/discounts/{discount_id}", headers=super_admin_headers)
        assert redelete_resp.status_code == 404

    def test_create_discount_invalid_date_range_400(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/discounts",
            json={
                "branch_id": branch.id, "condition_type": "total_amount", "condition_value": ">=50",
                "discount_type": "fixed_amount", "discount_value": "20",
                "valid_from": str(date.today() + timedelta(days=10)),
                "valid_until": str(date.today()),
            },
            headers=super_admin_headers,
        )
        assert resp.status_code == 400

    def test_update_nonexistent_discount_404(self, client: TestClient, db, super_admin_headers):
        resp = client.patch(
            "/api/v1/finance/discounts/999999", json={"discount_value": "5"}, headers=super_admin_headers,
        )
        assert resp.status_code == 404

    def _discount_payload(self, branch_id: int, **overrides) -> dict:
        payload = {
            "branch_id": branch_id, "condition_type": "total_amount", "condition_value": ">=100",
            "discount_type": "percentage", "discount_value": "10",
            "valid_from": str(date.today() - timedelta(days=1)),
            "valid_until": str(date.today() + timedelta(days=30)),
        }
        payload.update(overrides)
        return payload

    def test_create_discount_with_outlet_scope(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/discounts",
            json=self._discount_payload(branch.id, scope_type="outlet", scope_outlet="cafe"),
            headers=super_admin_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["scope_type"] == "outlet"
        assert body["scope_outlet"] == "cafe"
        assert body["scope_id"] is None

    def test_create_discount_time_of_day_valid_format(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/discounts",
            json=self._discount_payload(
                branch.id, condition_type="time_of_day", condition_value="14:00-17:00",
            ),
            headers=super_admin_headers,
        )
        assert resp.status_code == 201, resp.text

    def test_create_discount_time_of_day_invalid_format_400(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/discounts",
            json=self._discount_payload(
                branch.id, condition_type="time_of_day", condition_value="not-a-range",
            ),
            headers=super_admin_headers,
        )
        assert resp.status_code == 422

    def test_create_discount_combo_items_requires_outlet_scope_400(
        self, client: TestClient, db, super_admin_headers,
    ):
        """combo_items لازم يترافق مع scope_type='outlet' — راجع
        ConditionalDiscountCreate._validate_combo_scope."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/discounts",
            json=self._discount_payload(
                branch.id, condition_type="combo_items", condition_value="1:1,2:1",
                discount_type="combo_fixed_price",
                # scope_type الافتراضي "order" — لازم يترفض
            ),
            headers=super_admin_headers,
        )
        assert resp.status_code == 422

    def test_create_discount_combo_items_with_outlet_scope_succeeds(
        self, client: TestClient, db, super_admin_headers,
    ):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/discounts",
            json=self._discount_payload(
                branch.id, condition_type="combo_items", condition_value="1:1,2:1",
                discount_type="combo_fixed_price", discount_value="40",
                scope_type="outlet", scope_outlet="cafe",
            ),
            headers=super_admin_headers,
        )
        assert resp.status_code == 201, resp.text

    def test_create_discount_item_scope_requires_scope_id_400(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/discounts",
            json=self._discount_payload(branch.id, scope_type="item", scope_outlet="cafe"),  # scope_id ناقص
            headers=super_admin_headers,
        )
        assert resp.status_code == 422

    def test_create_discount_order_scope_rejects_scope_outlet_400(self, client: TestClient, db, super_admin_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/discounts",
            # scope_type الافتراضي "order" لا يقبل scope_outlet
            json=self._discount_payload(branch.id, scope_outlet="cafe"),
            headers=super_admin_headers,
        )
        assert resp.status_code == 422

    def test_create_discount_requires_admin(self, client: TestClient, db, manager_headers):
        """manager (60) لا يكفي — create_discount محتاج admin (80)."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/discounts",
            json={
                "branch_id": branch.id, "condition_type": "total_amount", "condition_value": ">=100",
                "discount_type": "percentage", "discount_value": "10",
                "valid_from": str(date.today()), "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 403

    def test_calculate_discount_endpoint(self, client: TestClient, db, cashier_headers, super_admin_headers):
        branch = make_branch_committed(db)
        client.post(
            "/api/v1/finance/discounts",
            json={
                "branch_id": branch.id, "condition_type": "total_amount", "condition_value": ">=100",
                "discount_type": "percentage", "discount_value": "10",
                "valid_from": str(date.today() - timedelta(days=1)),
                "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=super_admin_headers,
        )
        resp = client.post(
            "/api/v1/finance/calculate-discount",
            json={"branch_id": branch.id, "order_total": "200", "item_count": 2},
            headers=cashier_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["applied"] is True
        # calculate_discount_endpoint يرجّع dict خام (مش Pydantic response_model)،
        # فـ FastAPI's jsonable_encoder بيحوّل Decimal لـ float مش string.
        assert Decimal(str(body["amount_saved"])) == Decimal("20.00")


class TestAccountHTTPFlow:
    def test_create_and_list_account(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/finance/accounts",
            json={"branch_id": branch.id, "code": "9999", "name": "Test Account", "account_type": "asset"},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        list_resp = client.get(
            "/api/v1/finance/accounts", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        assert any(a["code"] == "9999" for a in list_resp.json()["items"])

    def test_create_duplicate_account_code_400(self, client: TestClient, db, manager_headers):
        """نفس (branch_id, code) مرتين لازم يترفض — uq_accounts_branch_code."""
        branch = make_branch_committed(db)
        payload = {"branch_id": branch.id, "code": "8888", "name": "Dup", "account_type": "asset"}
        first = client.post("/api/v1/finance/accounts", json=payload, headers=manager_headers)
        assert first.status_code == 201
        second = client.post("/api/v1/finance/accounts", json=payload, headers=manager_headers)
        assert second.status_code == 400

    def test_list_accounts_includes_computed_balance(self, client: TestClient, db, manager_headers):
        """Regression: AccountRead كان بالكامل من غير حقل balance — الفرونت
        إند (FinanceView.vue، تاب "الحسابات") كان بيقرأ acc.balance من غير ما
        الـ API يرجّعه أصلاً، يعني undefined.toLocaleString() كانت هتطيح
        الشاشة فعليًا. بعد ترحيل قيد (Dr. Cash 100 / Cr. Revenue 100)،
        الحساب المديني (asset) لازم يرجع برصيد موجب، والدائني (revenue) برصيد
        موجب كمان (نفس اتجاهه الطبيعي — دائن للإيرادات)."""
        branch = make_branch_committed(db)
        cash = make_account_committed(db, branch, "1100-BAL", "Cash", "asset")
        revenue = make_account_committed(db, branch, "4100-BAL", "Revenue", "revenue")
        client.post(
            "/api/v1/finance/journal-entries",
            json={
                "branch_id": branch.id, "entry_date": str(date.today()),
                "reference": "JE-BAL-TEST", "description": "balance regression",
                "lines": [
                    {"account_id": cash.id, "debit": "100.00", "credit": "0"},
                    {"account_id": revenue.id, "debit": "0", "credit": "100.00"},
                ],
            },
            headers=manager_headers,
        )
        resp = client.get(
            "/api/v1/finance/accounts", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert resp.status_code == 200
        items = {a["code"]: a for a in resp.json()["items"]}
        assert Decimal(str(items["1100-BAL"]["balance"])) == Decimal("100.00")
        assert Decimal(str(items["4100-BAL"]["balance"])) == Decimal("100.00")


class TestJournalEntryHTTPFlow:
    def test_post_unbalanced_entry_400(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        cash = make_account_committed(db, branch, "1100", "Cash", "asset")
        revenue = make_account_committed(db, branch, "4100", "Revenue", "revenue")
        resp = client.post(
            "/api/v1/finance/journal-entries",
            json={
                "branch_id": branch.id, "entry_date": str(date.today()),
                "reference": "JE-UNBAL", "description": "Unbalanced",
                "lines": [
                    {"account_id": cash.id, "debit": "100.00", "credit": "0"},
                    {"account_id": revenue.id, "debit": "0", "credit": "50.00"},
                ],
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_list_and_get_journal_entry(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        cash = make_account_committed(db, branch, "1100", "Cash", "asset")
        revenue = make_account_committed(db, branch, "4100", "Revenue", "revenue")
        create_resp = client.post(
            "/api/v1/finance/journal-entries",
            json={
                "branch_id": branch.id, "entry_date": str(date.today()),
                "reference": "JE-OK", "description": "Balanced",
                "lines": [
                    {"account_id": cash.id, "debit": "100.00", "credit": "0"},
                    {"account_id": revenue.id, "debit": "0", "credit": "100.00"},
                ],
            },
            headers=manager_headers,
        )
        entry_id = create_resp.json()["id"]

        list_resp = client.get(
            "/api/v1/finance/journal-entries", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        assert any(e["id"] == entry_id for e in list_resp.json()["items"])

        get_resp = client.get(f"/api/v1/finance/journal-entries/{entry_id}", headers=manager_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["reference"] == "JE-OK"

    def test_get_nonexistent_journal_entry_404(self, client: TestClient, db, manager_headers):
        resp = client.get("/api/v1/finance/journal-entries/999999", headers=manager_headers)
        assert resp.status_code == 404


class TestAccountingPeriodHTTPFlow:
    def test_list_and_close_period(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        list_resp = client.get(
            "/api/v1/finance/periods", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        assert list_resp.json()["items"] == []

        today = date.today()
        close_resp = client.post(
            f"/api/v1/finance/periods/{today.year}/{today.month}/close",
            json={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert close_resp.status_code == 200, close_resp.text
        assert close_resp.json()["status"] == "closed"

        list_after = client.get(
            "/api/v1/finance/periods", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert len(list_after.json()["items"]) == 1

    def test_closed_period_blocks_new_journal_entries(self, client: TestClient, db, manager_headers):
        """قيد يومية في فترة مقفولة لازم يترفض 400 — نفس القاعدة اللي بيتحقق
        منها validate_period_open."""
        branch = make_branch_committed(db)
        cash = make_account_committed(db, branch, "1100", "Cash", "asset")
        revenue = make_account_committed(db, branch, "4100", "Revenue", "revenue")
        today = date.today()
        client.post(
            f"/api/v1/finance/periods/{today.year}/{today.month}/close",
            json={"branch_id": branch.id},
            headers=manager_headers,
        )
        resp = client.post(
            "/api/v1/finance/journal-entries",
            json={
                "branch_id": branch.id, "entry_date": str(today),
                "reference": "JE-CLOSED-PERIOD", "description": "should fail",
                "lines": [
                    {"account_id": cash.id, "debit": "10.00", "credit": "0"},
                    {"account_id": revenue.id, "debit": "0", "credit": "10.00"},
                ],
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400
        assert "مقفولة" in resp.json()["detail"]


class TestCheckHTTPFlow:
    def test_create_list_and_move_check(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/finance/checks",
            json={
                "branch_id": branch.id, "check_number": "CHK-0001", "bank_name": "بنك مصر",
                "amount": "1500.00", "due_date": str(date.today() + timedelta(days=30)),
                "drawer_name": "أحمد علي", "received_at": str(date.today()),
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        check_id = create_resp.json()["id"]
        assert create_resp.json()["status"] == "received"

        list_resp = client.get(
            "/api/v1/finance/checks", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        assert any(c["id"] == check_id for c in list_resp.json())

        move_resp = client.patch(
            f"/api/v1/finance/checks/{check_id}/status",
            json={"to_status": "deposited"},
            headers=manager_headers,
        )
        assert move_resp.status_code == 200, move_resp.text
        assert move_resp.json()["status"] == "deposited"
        assert move_resp.json()["deposited_at"] is not None

    def test_move_nonexistent_check_404(self, client: TestClient, db, manager_headers):
        resp = client.patch(
            "/api/v1/finance/checks/999999/status", json={"to_status": "deposited"}, headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_move_check_invalid_status_422(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/finance/checks",
            json={
                "branch_id": branch.id, "check_number": "CHK-0002", "bank_name": "بنك مصر",
                "amount": "1000.00", "due_date": str(date.today() + timedelta(days=30)),
                "drawer_name": "سارة محمود", "received_at": str(date.today()),
            },
            headers=manager_headers,
        )
        check_id = create_resp.json()["id"]
        resp = client.patch(
            f"/api/v1/finance/checks/{check_id}/status",
            json={"to_status": "not_a_real_status"},
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_waiter_cannot_create_or_move_checks_403(self, client: TestClient, db, waiter_headers):
        """Regression: الشيكات كانت على get_current_active_user (أي موظف
        مسجّل دخول) بدل get_cashier_user/get_manager_user زي باقي المالية —
        جرسون (level 30) كان يقدر يسجّل شيك جديد أو ينقل حالته."""
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/finance/checks",
            json={
                "branch_id": branch.id, "check_number": "CHK-WAITER", "bank_name": "بنك مصر",
                "amount": "500.00", "due_date": str(date.today() + timedelta(days=30)),
                "drawer_name": "test", "received_at": str(date.today()),
            },
            headers=waiter_headers,
        )
        assert create_resp.status_code == 403

        list_resp = client.get(
            "/api/v1/finance/checks", params={"branch_id": branch.id}, headers=waiter_headers,
        )
        assert list_resp.status_code == 403

    def test_cashier_can_create_but_not_move_check_status(self, client: TestClient, db, cashier_headers):
        """كاشير (level 40) يقدر يسجّل شيك مستلم (عملية يومية عادية)، لكن نقل
        حالته (إيداع/تحصيل/ارتجاع — قرار محاسبي/بنكي) لسه محتاج manager+."""
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/finance/checks",
            json={
                "branch_id": branch.id, "check_number": "CHK-CASHIER", "bank_name": "بنك مصر",
                "amount": "700.00", "due_date": str(date.today() + timedelta(days=30)),
                "drawer_name": "test", "received_at": str(date.today()),
            },
            headers=cashier_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        check_id = create_resp.json()["id"]

        move_resp = client.patch(
            f"/api/v1/finance/checks/{check_id}/status",
            json={"to_status": "deposited"},
            headers=cashier_headers,
        )
        assert move_resp.status_code == 403

    def test_create_check_rejects_zero_amount_422(self, client: TestClient, db, manager_headers):
        """Regression: قبل ما تتضاف CheckCreate schema، الـ endpoint كان
        بياخد dict خام من غير أي validation — مبلغ صفري أو تاريخ فاسد كان
        بيوصل لقاعدة البيانات مباشرة (وبيطيح فعلياً على SQLite بـ TypeError
        بسبب غياب تحويل نص التاريخ لـ date)."""
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/checks",
            json={
                "branch_id": branch.id, "check_number": "CHK-BAD", "bank_name": "بنك",
                "amount": "0", "due_date": str(date.today()),
                "drawer_name": "x", "received_at": str(date.today()),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 422

    def test_check_status_cannot_skip_deposited_to_cleared_directly(
        self, client: TestClient, db, manager_headers,
    ):
        """Regression: move_check_status عمرها ما كانت بتتحقق من الانتقال
        نفسه — أي حالة من الأربعة (received/deposited/cleared/bounced) كانت
        مقبولة بغض النظر عن الحالة الحالية. مدير تحت ضغط كان يقدر "يصفّي"
        شيك لسه received من غير ما يمر بمرحلة الإيداع، أو (أخطر) يرجّع شيك
        cleared/bounced لحالة سابقة من غير أي أثر تدقيقي حقيقي غير سطر
        CheckMovement. اتصلح بـ CHECK_STATUS_TRANSITIONS في services.py."""
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/finance/checks",
            json={
                "branch_id": branch.id, "check_number": "CHK-SKIP", "bank_name": "بنك مصر",
                "amount": "900.00", "due_date": str(date.today() + timedelta(days=30)),
                "drawer_name": "test", "received_at": str(date.today()),
            },
            headers=manager_headers,
        )
        check_id = create_resp.json()["id"]

        # received → cleared مباشرة (تخطي deposited) لازم يترفض
        resp = client.patch(
            f"/api/v1/finance/checks/{check_id}/status",
            json={"to_status": "cleared"}, headers=manager_headers,
        )
        assert resp.status_code == 400, resp.text
        assert "received" in resp.json()["detail"]

    def test_check_status_cannot_move_out_of_terminal_state(
        self, client: TestClient, db, manager_headers,
    ):
        """شيك اترجع (bounced) أو اتحصّل (cleared) في حالة نهائية — مفيش رجوع
        منها عبر نفس الـ endpoint (يحتاج تصحيح/سجل جديد لا مجرد status flip)."""
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/finance/checks",
            json={
                "branch_id": branch.id, "check_number": "CHK-TERM", "bank_name": "بنك مصر",
                "amount": "900.00", "due_date": str(date.today() + timedelta(days=30)),
                "drawer_name": "test", "received_at": str(date.today()),
            },
            headers=manager_headers,
        )
        check_id = create_resp.json()["id"]

        resp = client.patch(
            f"/api/v1/finance/checks/{check_id}/status",
            json={"to_status": "deposited"}, headers=manager_headers,
        )
        assert resp.status_code == 200
        resp = client.patch(
            f"/api/v1/finance/checks/{check_id}/status",
            json={"to_status": "bounced"}, headers=manager_headers,
        )
        assert resp.status_code == 200

        # bounced حالة نهائية — لا يمكن نقلها لـ cleared أو أي حاجة تانية
        resp = client.patch(
            f"/api/v1/finance/checks/{check_id}/status",
            json={"to_status": "cleared"}, headers=manager_headers,
        )
        assert resp.status_code == 400, resp.text
        assert "نهائية" in resp.json()["detail"]


class TestHandoverNoteHTTP:
    def test_handover_note_null_when_no_closed_shift_yet(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/finance/shifts/handover-note", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == {"handover_note": None}

    def test_handover_note_returns_latest_closed_shift_note(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        open_resp = client.post(
            "/api/v1/finance/shifts/open",
            json={"branch_id": branch.id, "opening_float": "0"},
            headers=cashier_headers,
        )
        shift_id = open_resp.json()["id"]
        client.post(
            f"/api/v1/finance/shifts/{shift_id}/close",
            json={"counted_cash": "0", "handover_note": "خد بالك من طلبية الصبح"},
            headers=cashier_headers,
        )
        resp = client.get(
            "/api/v1/finance/shifts/handover-note", params={"branch_id": branch.id}, headers=cashier_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["handover_note"] == "خد بالك من طلبية الصبح"


class TestAccountingPeriodDoubleCloseHTTP:
    def test_closing_already_closed_period_returns_400(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        today = date.today()
        first = client.post(
            f"/api/v1/finance/periods/{today.year}/{today.month}/close",
            json={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert first.status_code == 200, first.text

        second = client.post(
            f"/api/v1/finance/periods/{today.year}/{today.month}/close",
            json={"branch_id": branch.id},
            headers=manager_headers,
        )
        assert second.status_code == 400
        assert "مقفولة بالفعل" in second.json()["detail"]


class TestExchangeRateHTTPFlow:
    def test_create_and_list_exchange_rate(self, client: TestClient, db, manager_headers):
        resp = client.post(
            "/api/v1/finance/exchange-rates",
            json={"from_currency": "USD", "to_currency": "EGP", "rate": "48.75",
                  "effective_date": "2026-06-01"},
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        assert Decimal(resp.json()["rate"]) == Decimal("48.75")

        list_resp = client.get(
            "/api/v1/finance/exchange-rates",
            params={"from_currency": "USD", "to_currency": "EGP"},
            headers=manager_headers,
        )
        assert list_resp.status_code == 200
        assert any(Decimal(r["rate"]) == Decimal("48.75") for r in list_resp.json()["items"])

    def test_create_duplicate_exchange_rate_400(self, client: TestClient, db, manager_headers):
        payload = {"from_currency": "EUR", "to_currency": "EGP", "rate": "55.00",
                   "effective_date": "2026-06-02"}
        first = client.post("/api/v1/finance/exchange-rates", json=payload, headers=manager_headers)
        assert first.status_code == 201
        second = client.post("/api/v1/finance/exchange-rates", json=payload, headers=manager_headers)
        assert second.status_code == 400


class TestETAInvoiceHTTPFlow:
    """POST /finance/eta/invoices — الجزء الأكثر حساسية قانونيًا في الموديول
    (تكامل مصلحة الضرائب المصرية). الشبكة الحقيقية مش متاحة هنا، فبنعمل mock
    لـ ETAService.submit_invoice بس (بناء المستند وقواعد ETA_ENABLED/الإعداد
    حقيقيين 100%، مفيش أي حاجة اتعملها mock غير استدعاء الشبكة نفسه)."""

    @staticmethod
    def _configure_eta(monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "ETA_ENABLED", True)
        monkeypatch.setattr(settings, "ETA_CLIENT_ID", "test-client")
        monkeypatch.setattr(settings, "ETA_CLIENT_SECRET", "test-secret")
        monkeypatch.setattr(settings, "ETA_TAXPAYER_RIN", "123456789")
        monkeypatch.setattr(settings, "ETA_TAXPAYER_NAME", "El Kheima Beach")

    def test_submit_disabled_returns_400(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/eta/invoices",
            json={
                "branch_id": branch.id, "receiver_name": "Guest",
                "line_items": [{"description": "Room", "quantity": 1, "unit_price": 500.0}],
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400
        assert "ETA_ENABLED" in resp.json()["detail"]

    def test_submit_accepted_creates_submitted_invoice_and_is_gettable(
        self, client: TestClient, db, manager_headers, monkeypatch,
    ):
        from app.modules.finance import eta_service
        self._configure_eta(monkeypatch)

        async def fake_submit_invoice(self, document):
            return {"acceptedDocuments": [{"uuid": "uuid-http-1", "longId": "LONG-HTTP-1"}]}
        monkeypatch.setattr(eta_service.ETAService, "submit_invoice", fake_submit_invoice)

        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/eta/invoices",
            json={
                "branch_id": branch.id, "receiver_name": "Guest",
                "line_items": [{"description": "Room", "quantity": 1, "unit_price": 500.0}],
            },
            headers=manager_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "submitted"
        assert body["submission_uuid"] == "uuid-http-1"

        get_resp = client.get(f"/api/v1/finance/eta/invoices/{body['id']}", headers=manager_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "submitted"

        list_resp = client.get(
            "/api/v1/finance/eta/invoices",
            params={"branch_id": branch.id, "status": "submitted"},
            headers=manager_headers,
        )
        assert list_resp.status_code == 200
        assert any(i["id"] == body["id"] for i in list_resp.json()["items"])

    def test_get_nonexistent_eta_invoice_404(self, client: TestClient, db, manager_headers):
        resp = client.get("/api/v1/finance/eta/invoices/999999", headers=manager_headers)
        assert resp.status_code == 404

    def test_submit_requires_manager_level(self, client: TestClient, db, cashier_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/finance/eta/invoices",
            json={
                "branch_id": branch.id, "receiver_name": "Guest",
                "line_items": [{"description": "Room", "quantity": 1, "unit_price": 500.0}],
            },
            headers=cashier_headers,
        )
        assert resp.status_code == 403


class TestCostCenterHTTPFlow:
    def test_create_and_list_cost_centers(self, client: TestClient, db, manager_headers, super_admin_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/finance/cost-centers",
            json={"branch_id": branch.id, "code": "TESTCC", "name": "Test Center"},
            headers=super_admin_headers,
        )
        assert create_resp.status_code == 201, create_resp.text

        list_resp = client.get(
            "/api/v1/finance/cost-centers", params={"branch_id": branch.id}, headers=manager_headers,
        )
        assert list_resp.status_code == 200
        assert any(c["code"] == "TESTCC" for c in list_resp.json())

    def test_cost_center_report(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.get(
            "/api/v1/finance/cost-centers/report",
            params={
                "branch_id": branch.id,
                "date_from": str(date.today() - timedelta(days=1)),
                "date_to": str(date.today()),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total_revenue"] == "0"
