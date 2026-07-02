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
