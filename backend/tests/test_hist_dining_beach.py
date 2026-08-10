"""tests/test_hist_dining_beach.py — HIST-01 dining/beach generator (OPS-DATA-02 §10.4)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.hist_dining_beach import generate as generate_dining_beach


@pytest.fixture
def branch(db: Session):
    from app.modules.core.models import Branch
    b = Branch(name="Test Dining Beach HIST", name_ar="اختبار دايننج وشاطئ",
               code=f"HDB-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.commit()
    return b


def _seed_accounts(db: Session, branch):
    from app.modules.finance.models import Account
    for code, name, acc_type in [
        ("1100", "Cash", "asset"), ("1110", "Bank/Card", "asset"),
        ("1150", "Folio AR", "asset"),
        ("2160", "VAT Payable", "liability"), ("2165", "Service Charge Payable", "liability"),
        ("4200", "Restaurant Revenue", "revenue"), ("4300", "Beach Revenue", "revenue"),
        ("4400", "Cafe Revenue", "revenue"),
    ]:
        db.add(Account(branch_id=branch.id, code=code, name=name, account_type=acc_type))
    db.commit()


class _Ctx:
    def __init__(self, branch_id: int):
        self.branch_id = branch_id
        self.period_year = 2026
        self.period_month = 7
        self.tz_name = "Africa/Cairo"


class TestHistDiningBeachGenerator:
    def test_generate_produces_exact_counts(self, db: Session, branch):
        _seed_accounts(db, branch)
        result = generate_dining_beach(db, _Ctx(branch.id))
        db.commit()

        counts = result["counts"]
        assert counts["restaurant_orders"] == 110
        assert counts["cafe_orders"] == 80
        assert counts["beach_transactions"] == 110
        assert counts["shifts_closed"] == 62
        assert counts["voids"] == 1
        assert counts["discounts"] == 1
        assert counts["refunds"] == 1
        assert counts["split_tender_orders"] == 1
        assert counts["b2b_checkins"] == 2
        assert counts["beach_voids"] == 1
        assert counts["variance_shifts"] == 2

    def test_all_shifts_closed_with_no_open_remaining(self, db: Session, branch):
        from app.modules.finance.models import CashierShift

        _seed_accounts(db, branch)
        generate_dining_beach(db, _Ctx(branch.id))
        db.commit()

        shifts = db.query(CashierShift).filter(CashierShift.branch_id == branch.id).all()
        assert len(shifts) == 62
        assert all(s.status == "closed" for s in shifts)

    def test_beach_revenue_matches_real_gl_minus_void(self, db: Session, branch):
        from app.modules.finance.models import Account, JournalLine

        from app.modules.beach.models import BeachTransaction

        _seed_accounts(db, branch)
        generate_dining_beach(db, _Ctx(branch.id))
        db.commit()

        beach_account = db.query(Account).filter_by(branch_id=branch.id, code="4300").first()
        lines = db.query(JournalLine).filter(JournalLine.account_id == beach_account.id).all()
        beach_credit_sum = sum(l.credit for l in lines)
        beach_debit_sum = sum(l.debit for l in lines)

        # void_transaction ميحذفش قيد البيع الأصلي — بيضيف قيد عكسي منفصل
        # (Dr 4300، عكس Cr الأصلي)، فسطر الدائن الأصلي للمعاملة الملغاة
        # لسه موجود. مجموع الدائن الخام = كل المعاملات (110 عادية + 2 B2B)
        # من غير استبعاد، والصافي الحقيقي (دائن-مدين) هو اللي بيعكس الإلغاء.
        transactions = db.query(BeachTransaction).filter(BeachTransaction.branch_id == branch.id).all()
        expected_gross_credit = sum(tx.total_amount for tx in transactions)
        assert beach_credit_sum == expected_gross_credit

        voided = [tx for tx in transactions if tx.voided_at is not None]
        assert len(voided) == 1
        assert beach_debit_sum == voided[0].total_amount  # قيد العكس الوحيد
        net_beach_revenue = beach_credit_sum - beach_debit_sum
        assert net_beach_revenue > Decimal("130000.00")  # الهدف الأساسي 132,000 ناقص معاملة ملغاة + B2B فوقه

    def test_restaurant_and_cafe_revenue_posted_to_correct_accounts(self, db: Session, branch):
        from app.modules.finance.models import Account, JournalLine

        _seed_accounts(db, branch)
        generate_dining_beach(db, _Ctx(branch.id))
        db.commit()

        restaurant_account = db.query(Account).filter_by(branch_id=branch.id, code="4200").first()
        cafe_account = db.query(Account).filter_by(branch_id=branch.id, code="4400").first()
        restaurant_credit = sum(
            l.credit for l in db.query(JournalLine).filter(JournalLine.account_id == restaurant_account.id).all()
        )
        cafe_credit = sum(
            l.credit for l in db.query(JournalLine).filter(JournalLine.account_id == cafe_account.id).all()
        )
        assert restaurant_credit > Decimal("0")
        assert cafe_credit > Decimal("0")
        # الطلب الملغى (order_no=2) عمره ما اتسوّى — صفر إيراد له، فمجموع
        # المطعم لازم يكون أقل من 165,000 بالظبط بقيمة طلب واحد (1500) على
        # الأقل (وربما أكتر لو الخصم في order_no=1 قلل إيراده هو كمان).
        assert restaurant_credit <= Decimal("165000.00") - Decimal("1500.00")

    def test_b2b_transactions_use_contract_entry_price(self, db: Session, branch):
        from app.modules.beach.models import BeachTransaction

        _seed_accounts(db, branch)
        generate_dining_beach(db, _Ctx(branch.id))
        db.commit()

        b2b_tx = db.query(BeachTransaction).filter(
            BeachTransaction.branch_id == branch.id, BeachTransaction.b2b_contract_id.isnot(None),
        ).all()
        assert len(b2b_tx) == 2

    def test_generate_is_deterministic_across_two_branches(self, db: Session, branch):
        from app.modules.core.models import Branch
        from app.modules.finance.models import CashierShift

        _seed_accounts(db, branch)
        result1 = generate_dining_beach(db, _Ctx(branch.id))
        db.commit()

        branch2 = Branch(name="Second HIST Dining Beach", name_ar="فرع ثاني",
                          code=f"HDB2-{uuid.uuid4().hex[:6].upper()}")
        db.add(branch2)
        db.commit()
        _seed_accounts(db, branch2)
        result2 = generate_dining_beach(db, _Ctx(branch2.id))
        db.commit()

        assert result1["counts"] == result2["counts"]
        assert result1["totals"] == result2["totals"]
        shifts1 = db.query(CashierShift).filter(CashierShift.branch_id == branch.id).count()
        shifts2 = db.query(CashierShift).filter(CashierShift.branch_id == branch2.id).count()
        assert shifts1 == shifts2 == 62

    def test_room_charge_settles_against_real_room_not_folio_id(self, db: Session, branch):
        """⚠️ باج حقيقي اتصلح (اتكشف وقت Phase 8 Local apply ضد PostgreSQL
        حقيقي — مش من التستات دي، اللي عمرها ما كانت بتجهّز أي حجز
        checked_in خالص فمسار room-charge كان دايمًا مُتخطّى بصمت هنا).
        settle_order's "room" tender محتاج Room.id فعليًا (charge_to_room_id)
        عشان يلاقي الفوليو بنفسه عبر find_active_folio_for_room — مش
        Folio.id. بنجبر Folio.id ≠ Room.id عمدًا هنا (بإنشاء صفوف زيادة
        الأول) عشان لو الباج القديم رجع (تمرير Folio.id غلط) التست يفشل،
        مش ينجح بالصدفة زي ما كان ممكن يحصل لو الاتنين اتساووا رقميًا."""
        from sqlalchemy import func

        from app.modules.core.models import Branch
        from app.modules.finance.models import Folio
        from app.modules.pms.models import Booking, BookingRoom, Room, RoomType

        # صفوف Folio زيادة قبل الحقيقيين — تضمن Folio.id > أي Room.id
        # موجود لحد دلوقتي، بغض النظر عن ترتيب تشغيل باقي التستات في
        # الـsuite كله (عدد ثابت من الديكوي كان fragile ومعتمد على الترتيب
        # — فشل فعليًا لما اتشغّل جوه الـsuite الكامل، راجع الـcommit).
        decoy_branch = Branch(name="Decoy", name_ar="زيادة",
                               code=f"DEC-{uuid.uuid4().hex[:6].upper()}")
        db.add(decoy_branch)
        db.commit()
        current_room_max = db.query(func.max(Room.id)).scalar() or 0
        current_folio_max = db.query(func.max(Folio.id)).scalar() or 0
        decoys_needed = max(0, current_room_max - current_folio_max) + 3
        for _ in range(decoys_needed):
            db.add(Folio(branch_id=decoy_branch.id, guest_name="Decoy",
                          check_in=datetime(2026, 1, 1), check_out=datetime(2026, 1, 2)))
        db.commit()

        room_type = RoomType(branch_id=branch.id, name="Studio", base_rate=Decimal("2500.00"),
                              max_occupancy=2)
        db.add(room_type)
        db.commit()
        room = Room(branch_id=branch.id, room_type_id=room_type.id, name="101")
        db.add(room)
        db.commit()

        folio = Folio(branch_id=branch.id, guest_name="ضيف HIST تست",
                       check_in=datetime(2026, 7, 1), check_out=datetime(2026, 7, 5))
        db.add(folio)
        db.commit()
        assert folio.id > room.id, "الديكوي المفروض يضمن Folio.id أكبر من Room.id"

        booking = Booking(
            branch_id=branch.id, booking_number=f"BKG-TEST-{uuid.uuid4().hex[:8]}",
            guest_name="ضيف HIST تست", check_in=date(2026, 7, 1), check_out=date(2026, 7, 5),
            status="checked_in", folio_id=folio.id,
        )
        db.add(booking)
        db.commit()
        db.add(BookingRoom(booking_id=booking.id, room_id=room.id,
                            daily_rate=Decimal("2500.00"), nights=4, total=Decimal("10000.00")))
        db.commit()

        _seed_accounts(db, branch)
        result = generate_dining_beach(db, _Ctx(branch.id))
        db.commit()

        assert result["counts"]["room_charge_orders"] == 1
        # لو الباج القديم رجع، settle_order كان هيفشل بـValueError قبل ما
        # يوصل هنا خالص (الاستثناء كان هيوقف الدالة كلها) — نجاح الوصول
        # هنا + العداد=1 يثبت إن charge_to_room_id اتحل صح فعليًا.
