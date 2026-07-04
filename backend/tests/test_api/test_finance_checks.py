"""tests/test_api/test_finance_checks.py"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from tests.test_api.test_pms import make_branch


class TestCheckManagement:

    def test_create_check(self, db):
        from app.modules.finance.crud import create_check
        branch = make_branch(db)
        check = create_check(db, {
            "branch_id": branch.id,
            "check_number": "CHK-001",
            "bank_name": "البنك الأهلي",
            "amount": Decimal("5000.00"),
            "due_date": date(2026, 8, 1),
            "drawer_name": "شركة التوريد",
            "status": "received",
            "created_by": 1,
            "received_at": date.today(),
        })
        assert check.id is not None
        assert check.status == "received"

    def test_move_check_to_deposited(self, db):
        from app.modules.finance.crud import create_check, move_check_status
        branch = make_branch(db)
        check = create_check(db, {
            "branch_id": branch.id,
            "check_number": "CHK-002",
            "bank_name": "بنك القاهرة",
            "amount": Decimal("2000.00"),
            "due_date": date(2026, 9, 1),
            "drawer_name": "مورد",
            "status": "received",
            "created_by": 1,
            "received_at": date.today(),
        })
        updated = move_check_status(db, check, "deposited", moved_by=1, notes="تم الإيداع")
        assert updated.status == "deposited"
        assert updated.deposited_at == date.today()

    def test_move_check_to_cleared(self, db):
        from app.modules.finance.crud import create_check, move_check_status
        branch = make_branch(db)
        check = create_check(db, {
            "branch_id": branch.id,
            "check_number": "CHK-003",
            "bank_name": "بنك مصر",
            "amount": Decimal("3000.00"),
            "due_date": date(2026, 7, 15),
            "drawer_name": "مستأجر",
            "status": "deposited",
            "created_by": 1,
            "received_at": date.today(),
        })
        updated = move_check_status(db, check, "cleared", moved_by=1)
        assert updated.status == "cleared"
        assert updated.cleared_at == date.today()

    def test_move_check_to_bounced(self, db):
        from app.modules.finance.crud import create_check, move_check_status
        branch = make_branch(db)
        check = create_check(db, {
            "branch_id": branch.id,
            "check_number": "CHK-004",
            "bank_name": "بنك الإسكندرية",
            "amount": Decimal("4000.00"),
            "due_date": date(2026, 10, 1),
            "drawer_name": "عميل",
            "status": "deposited",
            "created_by": 1,
            "received_at": date.today(),
        })
        updated = move_check_status(db, check, "bounced", moved_by=1, notes="رصيد غير كافٍ")
        assert updated.status == "bounced"
        assert updated.bounced_at == date.today()

    def test_list_checks_by_status(self, db):
        from app.modules.finance.crud import create_check, list_checks
        branch = make_branch(db)
        for i in range(3):
            create_check(db, {
                "branch_id": branch.id,
                "check_number": f"CHK-{i:03d}",
                "bank_name": "بنك",
                "amount": Decimal("1000"),
                "due_date": date(2026, 8, i+1),
                "drawer_name": "مورد",
                "status": "received",
                "created_by": 1,
                "received_at": date.today(),
            })
        received = list_checks(db, branch.id, status="received")
        assert len(received) >= 3
