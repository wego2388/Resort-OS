"""
tests/test_tasks/test_finance_tasks_coverage.py
Tests للـ finance_tasks.py — due reminders للـ timeshare و leasing
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest


def _get_or_create_manager(db) -> int:
    from app.core.kernel.models.user import User
    from app.core.kernel.security import get_password_hash
    import uuid
    user = User(
        email=f"mgr_{uuid.uuid4().hex[:6]}@test.com",
        password_hash=get_password_hash("Test@12345"),
        full_name="Test Manager",
        role="manager",
        is_active=True,
    )
    db.add(user); db.commit()
    return user.id


def _make_branch(db, prefix="Task"):
    from app.modules.core.models import Branch
    import uuid
    branch = Branch(
        name=f"{prefix}-{uuid.uuid4().hex[:4]}",
        code=f"{prefix[:3].upper()}{uuid.uuid4().hex[:4].upper()}",
    )
    db.add(branch); db.commit()
    return branch


def test_check_due_reminders_runs_without_error(db):
    """check_due_reminders — يشتغل بدون exception"""
    from app.tasks.finance_tasks import check_due_reminders
    check_due_reminders()


def test_check_timeshare_dues_sends_reminder(db):
    """_check_timeshare_dues — يبعت واتساب لأصحاب الأقساط المستحقة"""
    import app.core.kernel.whatsapp as wa_module
    from app.tasks.finance_tasks import _check_timeshare_dues
    from app.modules.timeshare import crud as ts_crud
    from app.modules.timeshare.schemas import TimeshareContractCreate
    from app.modules.timeshare.models import TimeshareInstallment

    sent_messages = []
    original_fn = wa_module.send_whatsapp_message
    wa_module.send_whatsapp_message = lambda phone, msg: sent_messages.append(
        {"phone": phone, "message": msg}
    )
    try:
        branch = _make_branch(db, "TSTask")
        signed_by = _get_or_create_manager(db)
        remind_date = date.today() + timedelta(days=3)

        from app.modules.timeshare.schemas import TimeshareContractCreate
        contract_data = TimeshareContractCreate(
            branch_id=branch.id,
            customer_name="Mohamed Ali",
            customer_phone="01099999999",
            room_type="Studio",
            total_value=Decimal("50000"),
            down_payment=Decimal("10000"),
            installments=12,
            installment_period=1,
            first_installment_date=remind_date,
            start_date=date.today(),
            season="high",
        )
        contract = ts_crud.create_contract(db, contract_data, signed_by=signed_by)
        db.flush()

        inst = TimeshareInstallment(
            contract_id=contract.id,
            installment_no=1,
            due_date=remind_date,
            amount=Decimal("5000"),
            status="pending",
        )
        db.add(inst)
        db.commit()

        _check_timeshare_dues(db, branch.id, remind_date)

        assert len(sent_messages) == 1
        assert sent_messages[0]["phone"] == "01099999999"
    finally:
        wa_module.send_whatsapp_message = original_fn


def test_check_timeshare_dues_no_message_if_paid(db):
    """_check_timeshare_dues — مفيش رسالة لأقساط مدفوعة"""
    import app.core.kernel.whatsapp as wa_module
    from app.tasks.finance_tasks import _check_timeshare_dues
    from app.modules.timeshare import crud as ts_crud
    from app.modules.timeshare.schemas import TimeshareContractCreate
    from app.modules.timeshare.models import TimeshareInstallment

    sent_messages = []
    original_fn = wa_module.send_whatsapp_message
    wa_module.send_whatsapp_message = lambda phone, msg: sent_messages.append(
        {"phone": phone, "message": msg}
    )
    try:
        branch = _make_branch(db, "TSNoPay")
        signed_by = _get_or_create_manager(db)
        # استخدام remind_date مختلف عن التست السابق
        remind_date = date.today() + timedelta(days=5)

        contract_data = TimeshareContractCreate(
            branch_id=branch.id,
            customer_name="Aya Samir",
            customer_phone="01088888888",
            room_type="Studio",
            total_value=Decimal("40000"),
            down_payment=Decimal("10000"),
            installments=12,
            installment_period=1,
            first_installment_date=remind_date,
            start_date=date.today(),
            season="high",
        )
        contract = ts_crud.create_contract(db, contract_data, signed_by=signed_by)
        db.flush()

        # قسط مدفوع
        inst = TimeshareInstallment(
            contract_id=contract.id,
            installment_no=1,
            due_date=remind_date,
            amount=Decimal("4000"),
            status="paid",
        )
        db.add(inst)
        db.commit()

        _check_timeshare_dues(db, branch.id, remind_date)

        assert len(sent_messages) == 0
    finally:
        wa_module.send_whatsapp_message = original_fn


def test_check_leasing_dues_sends_reminder(db):
    """_check_leasing_dues — يبعت واتساب لأصحاب دفعات الإيجار"""
    import app.core.kernel.whatsapp as wa_module
    from app.tasks.finance_tasks import _check_leasing_dues
    from app.modules.leasing import crud as lease_crud
    from app.modules.leasing.schemas import LeaseContractCreate
    from app.modules.leasing.models import LeasePayment

    sent_messages = []
    original_fn = wa_module.send_whatsapp_message
    wa_module.send_whatsapp_message = lambda phone, msg: sent_messages.append(
        {"phone": phone, "message": msg}
    )
    try:
        branch = _make_branch(db, "LeaseTask")
        signed_by = _get_or_create_manager(db)
        remind_date = date.today() + timedelta(days=3)

        contract_data = LeaseContractCreate(
            branch_id=branch.id,
            tenant_name="Business Owner",
            tenant_phone="01077777777",
            unit_description="Shop 1 - Ground Floor",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            base_rent=Decimal("3000"),
        )
        contract = lease_crud.create_contract(db, contract_data, signed_by=signed_by)
        db.commit()

        # نعدّل أول دفعة لتكون due_date = remind_date و pending
        payment = db.query(LeasePayment).filter(
            LeasePayment.contract_id == contract.id
        ).first()
        if payment:
            payment.due_date = remind_date
            payment.status = "pending"
            db.commit()

        _check_leasing_dues(db, branch.id, remind_date)

        if payment:
            assert len(sent_messages) == 1
            assert sent_messages[0]["phone"] == "01077777777"
        else:
            assert len(sent_messages) == 0
    finally:
        wa_module.send_whatsapp_message = original_fn


def test_check_leasing_dues_no_message_if_paid(db):
    """_check_leasing_dues — مفيش رسالة لدفعات مدفوعة"""
    import app.core.kernel.whatsapp as wa_module
    from app.tasks.finance_tasks import _check_leasing_dues
    from app.modules.leasing import crud as lease_crud
    from app.modules.leasing.schemas import LeaseContractCreate
    from app.modules.leasing.models import LeasePayment

    sent_messages = []
    original_fn = wa_module.send_whatsapp_message
    wa_module.send_whatsapp_message = lambda phone, msg: sent_messages.append(
        {"phone": phone, "message": msg}
    )
    try:
        branch = _make_branch(db, "LeaseNoPay")
        signed_by = _get_or_create_manager(db)
        remind_date = date.today() + timedelta(days=3)

        contract_data = LeaseContractCreate(
            branch_id=branch.id,
            tenant_name="Tenant 2",
            tenant_phone="01066666666",
            unit_description="Shop 2 - First Floor",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            base_rent=Decimal("2500"),
        )
        contract = lease_crud.create_contract(db, contract_data, signed_by=signed_by)
        db.commit()

        # كل الدفعات مدفوعة
        db.query(LeasePayment).filter(
            LeasePayment.contract_id == contract.id
        ).update({"status": "paid", "due_date": remind_date})
        db.commit()

        _check_leasing_dues(db, branch.id, remind_date)

        assert len(sent_messages) == 0
    finally:
        wa_module.send_whatsapp_message = original_fn


def test_check_timeshare_dues_does_not_leak_across_branches(db):
    """_check_timeshare_dues كان بياخد branch_id بدون أي استخدام فعلي في
    الاستعلام — check_due_reminders (الـCelery task الأب) بينادي الدالة دي
    مرة لكل فرع نشط، يعني كل فرع كان بيعيد إرسال تذكير واتساب لكل الأقساط
    المستحقة في *كل الفروع* بدل فرعه بس. مع فرعين نشطين، العميل كان هياخد
    رسالة مكررة مرتين بدل مرة واحدة. اتصلح بـjoin + فلترة بـbranch_id عبر
    TimeshareContract — هذا التست يثبت العزل بين فرعين حقيقيين، مش بس إنه
    مايبعتش لقسط مدفوع (test_check_timeshare_dues_no_message_if_paid فوق)."""
    import app.core.kernel.whatsapp as wa_module
    from app.tasks.finance_tasks import _check_timeshare_dues
    from app.modules.timeshare import crud as ts_crud
    from app.modules.timeshare.schemas import TimeshareContractCreate
    from app.modules.timeshare.models import TimeshareInstallment

    sent_messages = []
    original_fn = wa_module.send_whatsapp_message
    wa_module.send_whatsapp_message = lambda phone, msg: sent_messages.append(
        {"phone": phone, "message": msg}
    )
    try:
        branch_a = _make_branch(db, "TSBranchA")
        branch_b = _make_branch(db, "TSBranchB")
        signed_by = _get_or_create_manager(db)
        remind_date = date.today() + timedelta(days=9)

        def _make_due_installment(branch, phone):
            contract = ts_crud.create_contract(db, TimeshareContractCreate(
                branch_id=branch.id,
                customer_name="Cross Branch Test",
                customer_phone=phone,
                room_type="Studio",
                total_value=Decimal("40000"),
                down_payment=Decimal("10000"),
                installments=12,
                installment_period=1,
                first_installment_date=remind_date,
                start_date=date.today(),
                season="high",
            ), signed_by=signed_by)
            db.flush()
            db.add(TimeshareInstallment(
                contract_id=contract.id, installment_no=1,
                due_date=remind_date, amount=Decimal("4000"), status="pending",
            ))
            db.commit()

        _make_due_installment(branch_a, "01011111111")
        _make_due_installment(branch_b, "01022222222")

        _check_timeshare_dues(db, branch_a.id, remind_date)

        assert len(sent_messages) == 1
        assert sent_messages[0]["phone"] == "01011111111"
    finally:
        wa_module.send_whatsapp_message = original_fn
