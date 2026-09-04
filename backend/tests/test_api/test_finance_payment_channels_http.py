"""
tests/test_api/test_finance_payment_channels_http.py
HTTP + service-level tests for PaymentChannel (branch-scoped collection
channels — cash drawer / Visa CIB / Vodafone Cash / ... — each posting to a
mandatory GL account and an optional bank account).

⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed — the
HTTP request goes through a different DB session than the `db` fixture.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.modules.finance import services
from app.modules.finance.schemas import PaymentChannelCreate, PaymentChannelUpdate


def make_branch(db, name="PayChan Branch"):
    from app.modules.core.models import Branch
    b = Branch(name=name, name_ar="فرع اختبار قنوات التحصيل",
               code=f"PCH-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


def make_account(db, branch, code, *, account_type="asset", is_active=True):
    from app.modules.finance.models import Account
    acc = Account(
        branch_id=branch.id, code=code, name=f"Account {code}",
        name_ar=f"حساب {code}", account_type=account_type, is_active=is_active,
    )
    db.add(acc)
    db.commit()
    return acc


def make_bank_account(db, branch, *, is_active=True):
    from app.modules.finance.models import BankAccount
    ba = BankAccount(
        branch_id=branch.id, bank_name="CIB", account_name="CIB Main",
        account_number=f"ACC-{uuid.uuid4().hex[:10]}", currency="EGP", is_active=is_active,
    )
    db.add(ba)
    db.commit()
    return ba


def make_manager_headers(db, branch, role="manager"):
    from tests.conftest import _create_test_user, _make_token
    from app.modules.core.models import UserBranchMembership

    email = f"{role}-{uuid.uuid4().hex[:10]}@test.local"
    user_id = _create_test_user(email, role)
    db.add(UserBranchMembership(user_id=user_id, branch_id=branch.id, is_default=True, is_active=True))
    db.commit()
    return {"Authorization": f"Bearer {_make_token(email)}"}


# ─── Service-layer validation ─────────────────────────────────────────────

class TestPaymentChannelValidation:
    def test_create_requires_active_asset_account_same_branch(self, db):
        branch = make_branch(db)
        other_branch = make_branch(db, "Other")
        liability = make_account(db, branch, "2100", account_type="liability")
        inactive = make_account(db, branch, "1101", is_active=False)
        wrong_branch = make_account(db, other_branch, "1100")
        good = make_account(db, branch, "1100")

        with pytest.raises(ValueError, match="أصل"):
            services.create_payment_channel(db, PaymentChannelCreate(
                branch_id=branch.id, code="X1", name="X", method="cash",
                gl_account_id=liability.id,
            ))
        with pytest.raises(ValueError, match="نشط"):
            services.create_payment_channel(db, PaymentChannelCreate(
                branch_id=branch.id, code="X2", name="X", method="cash",
                gl_account_id=inactive.id,
            ))
        with pytest.raises(ValueError, match="غير موجود"):
            services.create_payment_channel(db, PaymentChannelCreate(
                branch_id=branch.id, code="X3", name="X", method="cash",
                gl_account_id=wrong_branch.id,
            ))
        channel = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-OK", name="Cash", method="cash",
            gl_account_id=good.id,
        ))
        assert channel.id is not None

    def test_cash_channel_cannot_link_bank_account(self, db):
        branch = make_branch(db)
        gl = make_account(db, branch, "1100")
        bank = make_bank_account(db, branch)
        with pytest.raises(ValueError, match="بنك"):
            services.create_payment_channel(db, PaymentChannelCreate(
                branch_id=branch.id, code="CASH-BANK", name="Cash", method="cash",
                gl_account_id=gl.id, bank_account_id=bank.id,
            ))

    def test_card_channel_bank_account_must_be_active_and_same_branch(self, db):
        branch = make_branch(db)
        other_branch = make_branch(db, "Other2")
        gl = make_account(db, branch, "1120")
        inactive_bank = make_bank_account(db, branch, is_active=False)
        wrong_branch_bank = make_bank_account(db, other_branch)

        with pytest.raises(ValueError, match="نشط"):
            services.create_payment_channel(db, PaymentChannelCreate(
                branch_id=branch.id, code="CARD-1", name="Card", method="card",
                gl_account_id=gl.id, bank_account_id=inactive_bank.id,
            ))
        with pytest.raises(ValueError, match="غير موجود"):
            services.create_payment_channel(db, PaymentChannelCreate(
                branch_id=branch.id, code="CARD-2", name="Card", method="card",
                gl_account_id=gl.id, bank_account_id=wrong_branch_bank.id,
            ))

    def test_only_one_default_per_branch_and_method(self, db):
        branch = make_branch(db)
        gl1 = make_account(db, branch, "1100")
        gl2 = make_account(db, branch, "1101")
        first = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-A", name="Cash A", method="cash",
            gl_account_id=gl1.id, is_default=True,
        ))
        second = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-B", name="Cash B", method="cash",
            gl_account_id=gl2.id, is_default=True,
        ))
        db.refresh(first)
        assert first.is_default is False
        assert second.is_default is True

        channels = services.list_payment_channels(db, branch.id, method="cash")
        defaults = [c for c in channels if c.is_default]
        assert len(defaults) == 1
        assert defaults[0].id == second.id

    def test_duplicate_code_same_branch_rejected(self, db):
        branch = make_branch(db)
        gl = make_account(db, branch, "1100")
        services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="DUPCODE", name="A", method="cash", gl_account_id=gl.id,
        ))
        with pytest.raises(ValueError, match="مستخدم"):
            services.create_payment_channel(db, PaymentChannelCreate(
                branch_id=branch.id, code="DUPCODE", name="B", method="cash", gl_account_id=gl.id,
            ))

    def test_update_disables_channel_instead_of_delete(self, db):
        branch = make_branch(db)
        gl = make_account(db, branch, "1100")
        channel = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-D", name="Cash", method="cash", gl_account_id=gl.id,
        ))
        updated = services.update_payment_channel(db, channel.id, PaymentChannelUpdate(is_active=False))
        assert updated.is_active is False
        assert updated.id == channel.id  # نفس الصف — مفيش حذف


# ─── resolve_payment_channel — used by Beach/Dining sale flow ────────────

class TestResolvePaymentChannel:
    def test_no_channels_configured_returns_none_legacy_fallback(self, db):
        branch = make_branch(db)
        assert services.resolve_payment_channel(db, branch.id, "cash") is None

    def test_explicit_channel_must_be_active_and_match_branch_and_method(self, db):
        branch = make_branch(db)
        other_branch = make_branch(db, "Other3")
        gl = make_account(db, branch, "1100")
        cash_channel = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-R", name="Cash", method="cash", gl_account_id=gl.id,
        ))
        inactive = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-INACTIVE", name="Cash Off", method="cash", gl_account_id=gl.id,
        ))
        services.update_payment_channel(db, inactive.id, PaymentChannelUpdate(is_active=False))

        resolved = services.resolve_payment_channel(db, branch.id, "cash", channel_id=cash_channel.id)
        assert resolved.id == cash_channel.id

        with pytest.raises(ValueError, match="معطّلة"):
            services.resolve_payment_channel(db, branch.id, "cash", channel_id=inactive.id)
        with pytest.raises(ValueError, match="طريقة الدفع"):
            services.resolve_payment_channel(db, branch.id, "card", channel_id=cash_channel.id)
        with pytest.raises(ValueError, match="غير موجودة"):
            services.resolve_payment_channel(db, other_branch.id, "cash", channel_id=cash_channel.id)

    def test_channels_exist_but_no_valid_default_fails_explicitly(self, db):
        branch = make_branch(db)
        gl = make_account(db, branch, "1100")
        channel = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-NODEF", name="Cash", method="cash", gl_account_id=gl.id,
            is_default=False,
        ))
        with pytest.raises(ValueError, match="لا توجد قناة تحصيل افتراضية"):
            services.resolve_payment_channel(db, branch.id, "cash")

    def test_default_channel_resolved_when_no_channel_id_given(self, db):
        branch = make_branch(db)
        gl = make_account(db, branch, "1100")
        default_channel = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-DEF", name="Cash", method="cash", gl_account_id=gl.id,
            is_default=True,
        ))
        resolved = services.resolve_payment_channel(db, branch.id, "cash")
        assert resolved.id == default_channel.id

    def test_snapshot_captures_gl_account_code(self, db):
        branch = make_branch(db)
        gl = make_account(db, branch, "1100")
        channel = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-SNAP", name="Cash", method="cash", gl_account_id=gl.id,
        ))
        snap = services.payment_channel_snapshot(channel)
        assert snap == {
            "payment_channel_id": channel.id,
            "payment_channel_code": "CASH-SNAP",
            "payment_channel_name": "Cash",
            "settlement_account_code": "1100",
        }
        assert services.payment_channel_snapshot(None) == {
            "payment_channel_id": None,
            "payment_channel_code": None,
            "payment_channel_name": None,
            "settlement_account_code": None,
        }

    def test_snapshot_is_immutable_after_channel_is_later_edited(self, db):
        """تغيير القناة (اسم/حساب GL) بعد أخذ اللقطة ميرجعش يغيّر اللقطة
        المحفوظة فعليًا — نفس الغرض من التخزين المستقل بدل مرجع حي."""
        branch = make_branch(db)
        gl_old = make_account(db, branch, "1100")
        gl_new = make_account(db, branch, "1105")
        channel = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CASH-IMM", name="Old Name", method="cash", gl_account_id=gl_old.id,
        ))
        snap = services.payment_channel_snapshot(channel)
        assert snap["settlement_account_code"] == "1100"

        services.update_payment_channel(db, channel.id, PaymentChannelUpdate(
            name="New Name", gl_account_id=gl_new.id,
        ))

        # اللقطة اللي اتاخدت قبل التعديل لسه زي ما هي (dict عادي، مش مرتبط حي)
        assert snap["settlement_account_code"] == "1100"
        assert snap["payment_channel_name"] == "Old Name"


# ─── HTTP router — permissions + branch isolation ────────────────────────

class TestPaymentChannelHTTP:
    def test_create_list_update_roundtrip(self, client: TestClient, db):
        branch = make_branch(db)
        gl = make_account(db, branch, "1100")
        headers = make_manager_headers(db, branch)

        resp = client.post("/api/v1/finance/payment-channels", headers=headers, json={
            "branch_id": branch.id, "code": "VISA-CIB", "name": "Visa CIB",
            "name_ar": "فيزا CIB", "method": "card", "gl_account_id": gl.id,
            "is_default": True,
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["gl_account_code"] == "1100"
        assert data["is_default"] is True
        channel_id = data["id"]

        resp = client.get(
            "/api/v1/finance/payment-channels", headers=headers,
            params={"branch_id": branch.id},
        )
        assert resp.status_code == 200
        assert any(c["id"] == channel_id for c in resp.json())

        resp = client.patch(
            f"/api/v1/finance/payment-channels/{channel_id}", headers=headers,
            json={"is_active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_create_rejects_invalid_gl_account_with_400(self, client: TestClient, db):
        branch = make_branch(db)
        liability = make_account(db, branch, "2100", account_type="liability")
        headers = make_manager_headers(db, branch)

        resp = client.post("/api/v1/finance/payment-channels", headers=headers, json={
            "branch_id": branch.id, "code": "BAD", "name": "Bad", "method": "cash",
            "gl_account_id": liability.id,
        })
        assert resp.status_code == 400

    def test_branch_isolation_cannot_touch_other_branch_channels(self, client: TestClient, db):
        branch_a = make_branch(db, "Branch A")
        branch_b = make_branch(db, "Branch B")
        gl_a = make_account(db, branch_a, "1100")
        headers_a = make_manager_headers(db, branch_a)
        headers_b = make_manager_headers(db, branch_b)

        resp = client.post("/api/v1/finance/payment-channels", headers=headers_a, json={
            "branch_id": branch_a.id, "code": "A-CASH", "name": "Cash", "method": "cash",
            "gl_account_id": gl_a.id,
        })
        assert resp.status_code == 201
        channel_id = resp.json()["id"]

        # فرع B مايقدرش يقرا/يعدّل قنوات فرع A حتى لو حاول يزوّر الطلب
        resp = client.get(
            "/api/v1/finance/payment-channels", headers=headers_b,
            params={"branch_id": branch_a.id},
        )
        assert resp.status_code == 403

        resp = client.patch(
            f"/api/v1/finance/payment-channels/{channel_id}", headers=headers_b,
            json={"is_active": False},
        )
        assert resp.status_code == 403

        resp = client.post("/api/v1/finance/payment-channels", headers=headers_b, json={
            "branch_id": branch_a.id, "code": "SHOULD-FAIL", "name": "X", "method": "cash",
            "gl_account_id": gl_a.id,
        })
        assert resp.status_code == 403

    def test_cashier_cannot_manage_payment_channels(self, client: TestClient, db):
        branch = make_branch(db)
        gl = make_account(db, branch, "1100")
        headers = make_manager_headers(db, branch, role="cashier")

        resp = client.post("/api/v1/finance/payment-channels", headers=headers, json={
            "branch_id": branch.id, "code": "NOPE", "name": "X", "method": "cash",
            "gl_account_id": gl.id,
        })
        assert resp.status_code == 403


class TestBankReconciliationChannelMatching:
    """bank reconciliation لازم يطابق بس الدفعات اللي قناة تحصيلها مربوطة
    بنفس الحساب البنكي — دفعة كاش من الصندوق مايترشحش لسطر تحويل بنكي حتى
    لو المبلغ اتفق بالصدفة. دفعات legacy (بلا قناة) لسه بتترشح عادي."""

    def test_candidates_exclude_payments_from_other_bank_accounts(self, db):
        from app.modules.finance import crud as finance_crud
        from app.modules.finance.models import Payment
        from datetime import date

        branch = make_branch(db)
        card_gl = make_account(db, branch, "1120")
        bank_a = make_bank_account(db, branch)
        bank_b = make_bank_account(db, branch)

        channel_a = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CARD-A", name="Card via Bank A", method="card",
            gl_account_id=card_gl.id, bank_account_id=bank_a.id,
        ))
        channel_b = services.create_payment_channel(db, PaymentChannelCreate(
            branch_id=branch.id, code="CARD-B", name="Card via Bank B", method="card",
            gl_account_id=card_gl.id, bank_account_id=bank_b.id,
        ))

        today = date.today()
        payment_a = Payment(
            branch_id=branch.id, amount=Decimal("100.00"), currency="EGP", fx_rate=Decimal("1"),
            method="card", posted_at=today, source="dining",
            **services.payment_channel_snapshot(channel_a),
        )
        payment_b = Payment(
            branch_id=branch.id, amount=Decimal("100.00"), currency="EGP", fx_rate=Decimal("1"),
            method="card", posted_at=today, source="dining",
            **services.payment_channel_snapshot(channel_b),
        )
        legacy_payment = Payment(
            branch_id=branch.id, amount=Decimal("100.00"), currency="EGP", fx_rate=Decimal("1"),
            method="card", posted_at=today, source="dining",
        )
        db.add_all([payment_a, payment_b, legacy_payment])
        db.commit()

        candidates = finance_crud.find_matching_payment_candidates(
            db, branch.id, Decimal("100.00"), today, bank_account_id=bank_a.id,
        )
        candidate_ids = {p.id for p in candidates}
        assert payment_a.id in candidate_ids
        assert payment_b.id not in candidate_ids
        assert legacy_payment.id in candidate_ids  # توافق آمن للحركات القديمة
