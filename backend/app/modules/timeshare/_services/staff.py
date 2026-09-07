"""app/modules/timeshare/_services/staff.py — Timeshare Staff: مدير
الملكية الجزئية بيدير موظفي وحدته (طلب Mohamed 2026-08-03: "يتحكم
بالموظفين الملكية الجزئية وحساباتهم"). نسخة مبسّطة ومعزولة من
core.kernel.auth.service.AuthService.provision_staff_account — مقفولة على
super_admin+step-up عمدًا (Gate 2B3A، مناسبة لإنشاء أي دور بما فيه أدوار
حساسة)، مش مناسبة لمدير وحدة معزولة زي ده بيعمل حاجة واحدة بس (إنشاء
timeshare_agent). role هنا ثابت دايمًا، مش قيمة بييجي بيها الطلب."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session


def provision_timeshare_agent(
    db: Session, *, email: str, full_name: str, phone: Optional[str],
    employee_id: int, branch_id: int, created_by: int,
    preferred_language: str = "ar",
) -> dict:
    """⚠️ باج توثيقي حقيقي اتصلح هنا: deps.py's get_timeshare_user كان
    بيدّعي إن timeshare_agent "بيحصل على UserPermission صريح على
    timeshare.access/view تلقائيًا عند إنشاء الحساب" — بس محدّش كان
    بيعمل ده فعليًا في provision_staff_account خالص (صفر استخدام لـ
    UserPermission هناك). هنا فعليًا بيتعمل، مش مجرد كومنت."""
    import json  # noqa: PLC0415
    import secrets as _secrets  # noqa: PLC0415

    from sqlalchemy import func  # noqa: PLC0415

    from app.core.kernel.models.user import User  # noqa: PLC0415
    from app.core.kernel.security import get_password_hash, validate_email_format  # noqa: PLC0415
    from app.modules.core.models import AuditLog, Branch, UserBranchMembership, UserPermission  # noqa: PLC0415
    from app.modules.hr.models import Employee  # noqa: PLC0415

    normalized_email = (email or "").strip().casefold()
    normalized_name = (full_name or "").strip()
    normalized_phone = (phone or "").strip() or None

    if not validate_email_format(normalized_email):
        raise ValueError("بريد إلكتروني غير صالح")
    if len(normalized_name) < 3:
        raise ValueError("الاسم الكامل مطلوب")
    if preferred_language not in {"ar", "en"}:
        raise ValueError("لغة غير مدعومة")

    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.is_active.is_(True)).first()
    if branch is None:
        raise ValueError("الفرع غير موجود أو غير نشط")

    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.branch_id == branch_id,
    ).with_for_update().first()
    if employee is None:
        raise ValueError("ملف الموظف غير موجود في فرع التشغيل")
    if employee.user_id is not None:
        raise ValueError("ملف الموظف مرتبط بحساب دخول بالفعل")
    if employee.status == "terminated":
        raise ValueError("لا يمكن إنشاء حساب لموظف منتهي الخدمة")

    existing = db.query(User).filter(func.lower(User.email) == normalized_email).first()
    if existing is not None:
        raise ValueError("يوجد حساب بهذا البريد الإلكتروني بالفعل")

    temporary_password = _secrets.token_urlsafe(12)
    user = User(
        email=normalized_email,
        password_hash=get_password_hash(temporary_password),
        full_name=normalized_name,
        phone=normalized_phone,
        role="timeshare_agent",
        is_active=True,
        preferred_language=preferred_language,
        must_change_password=True,
        # timeshare_agent مش من MANDATORY_2FA_ROLES (super_admin/accountant
        # بس) — مفيش داعي لرحلة enrollment token زي الأدوار الحساسة.
        two_factor_enabled=False,
        two_factor_bootstrap_required=False,
    )
    db.add(user)
    db.flush()
    employee.user_id = user.id
    db.add(UserBranchMembership(
        user_id=user.id, branch_id=branch_id, is_default=True, is_active=True, created_by=created_by,
    ))
    db.add(UserPermission(
        user_id=user.id, resource="timeshare.access", action="view",
        allowed=True, branch_id=None, granted_by=created_by,
    ))
    db.add(AuditLog(
        user_id=created_by, branch_id=branch_id, action="timeshare_agent_provisioned",
        entity_type="user", entity_id=user.id, old_data=None,
        new_data=json.dumps({
            "email": normalized_email,
            "full_name": normalized_name,
            "employee_id": employee_id,
        }, ensure_ascii=False),
    ))
    db.commit()
    db.refresh(user)
    return {
        "id": user.id, "employee_id": employee_id,
        "email": user.email, "full_name": user.full_name,
        "temporary_password": temporary_password, "must_change_password": True,
    }


def list_eligible_timeshare_employees(db: Session, branch_id: int) -> list:
    """Return only the non-sensitive HR fields needed by the account picker."""
    from app.modules.hr.models import Employee  # noqa: PLC0415

    return (
        db.query(Employee)
        .filter(
            Employee.branch_id == branch_id,
            Employee.user_id.is_(None),
            Employee.status != "terminated",
        )
        .order_by(Employee.full_name, Employee.id)
        .all()
    )


def list_timeshare_staff(db: Session, branch_id: int) -> list:
    from app.core.kernel.models.user import User  # noqa: PLC0415
    from app.modules.core.models import UserBranchMembership  # noqa: PLC0415

    return (
        db.query(User)
        .join(UserBranchMembership, UserBranchMembership.user_id == User.id)
        .filter(
            UserBranchMembership.branch_id == branch_id,
            User.role == "timeshare_agent",
        )
        .order_by(User.full_name)
        .all()
    )


def set_timeshare_staff_active(db: Session, staff_user_id: int, is_active: bool):
    """تفعيل/تعطيل حساب موظف ملكية جزئية — لازم revoke_user_tokens() (قاعدة
    ❻ في CLAUDE.md: أي تغيير is_active لازم يُبطل التوكنات القديمة فورًا،
    وإلا موظف اتعطّل حسابه يقدر يفضل شغال بتوكن قديم لحد ما ينتهي وحده)."""
    from app.core.deps import revoke_user_tokens  # noqa: PLC0415
    from app.core.kernel.models.user import User  # noqa: PLC0415

    user = db.query(User).filter(User.id == staff_user_id, User.role == "timeshare_agent").first()
    if not user:
        raise ValueError(f"موظف الملكية الجزئية {staff_user_id} غير موجود")
    user.is_active = is_active
    db.commit()
    revoke_user_tokens(user.id)
    db.refresh(user)
    return user
