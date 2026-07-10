"""app/modules/hr/api/router.py"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.core.deps import (
    DbDep, get_admin_user, get_current_active_user,
    get_manager_user, require_permission,
)
from app.modules.hr import crud, services
from app.modules.hr.schemas import (
    AllowanceRead,
    AttendancePolicyRead, AttendancePolicyUpsert,
    AttendanceRecordCreate, AttendanceRecordRead,
    DepartmentCreate, DepartmentRead,
    EmployeeCreate, EmployeeRead, EmployeeUpdate,
    EmployeeAllowanceCreate, EmployeeAllowanceUpdate,
    EmployeeLinkUserRequest,
    EmployeePenaltyCreate, EmployeePenaltyRead,
    LeaderboardEntry,
    LeaveApproveRequest, LeaveRejectRequest,
    LeaveRequestCreate, LeaveRequestRead, LeaveStatusUpdate,
    LeaveTypeCreate, LeaveTypeRead,
    MyLeaveRequestCreate, MyPayslipRead, MyProfileRead,
    PayrollLineRead,
    PayrollResultRead, PayrollRunCreate, PayrollRunRead,
    PenaltyTypeCreate, PenaltyTypeRead,
    RotaAssignmentCreate, RotaAssignmentRead,
    RotaTemplateCreate, RotaTemplateRead, RotaTemplateUpdate,
    ShiftCreate, ShiftRead,
    ShiftSwapRequestCreate, ShiftSwapRequestRead,
    SocialInsuranceConfigCreate, SocialInsuranceConfigRead,
    TaxBracketConfigCreate, TaxBracketConfigRead,
)
from app.modules.core.schemas import PaginatedResponse

router = APIRouter(tags=["hr"])


# ── Employees ─────────────────────────────────────────────────────────

@router.get("/hr/employees", response_model=PaginatedResponse)
def list_employees(
    db: DbDep,
    _=Depends(get_manager_user),
    branch_id: int = Query(...),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_employees(db, branch_id, status_filter,
                                        skip=(page - 1) * size, limit=size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[EmployeeRead.model_validate(e) for e in items])


@router.post("/hr/employees", response_model=EmployeeRead,
             status_code=status.HTTP_201_CREATED)
def create_employee(data: EmployeeCreate, db: DbDep, _=Depends(get_admin_user)):
    try:
        return services.create_employee(db, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/hr/employees/{employee_id}", response_model=EmployeeRead)
def get_employee(employee_id: int, db: DbDep, _=Depends(get_current_active_user)):
    emp = crud.get_employee(db, employee_id)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الموظف {employee_id} غير موجود")
    return EmployeeRead.model_validate(emp)


@router.patch("/hr/employees/{employee_id}", response_model=EmployeeRead)
def update_employee(employee_id: int, data: EmployeeUpdate, db: DbDep, user=Depends(get_admin_user)):
    try:
        return services.update_employee(db, employee_id, data, updated_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.patch("/hr/employees/{employee_id}/link-user", response_model=EmployeeRead)
def link_employee_user(
    employee_id: int, body: EmployeeLinkUserRequest, db: DbDep, _=Depends(get_manager_user),
):
    emp = crud.get_employee(db, employee_id)
    if not emp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الموظف {employee_id} غير موجود")
    try:
        return services.link_employee_to_user(db, emp, body.user_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/hr/employees/{employee_id}/payslip",
            response_model=PayrollResultRead)
def get_payslip(
    employee_id: int,
    db: DbDep,
    _=Depends(get_manager_user),
    period_year:  int = Query(..., ge=2020),
    period_month: int = Query(..., ge=1, le=12),
    penalty_days: int = Query(0, ge=0),
    unpaid_leave_days: int = Query(0, ge=0),
    overtime_amount: float = Query(0.0, ge=0),
    late_penalty_amount: float = Query(0.0, ge=0),
):
    from decimal import Decimal  # noqa: PLC0415
    try:
        return services.calculate_employee_payroll(
            db, employee_id, period_year, period_month,
            penalty_days, unpaid_leave_days, Decimal(str(overtime_amount)),
            Decimal(str(late_penalty_amount)),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Employee Allowances ───────────────────────────────────────────────
# EmployeeAllowance model كان موجود بالكامل (وبيدخل فعليًا في حساب الراتب —
# راجع services.calculate_employee_payroll) من غير أي طريقة لإضافته عن طريق
# الـ API — نفس فئة الباج (Lead/Campaign/TenantCashLog/CallNote/RotaTemplate).

@router.get("/hr/employees/{employee_id}/allowances", response_model=list[AllowanceRead])
def list_employee_allowances(
    employee_id: int, db: DbDep, _=Depends(get_manager_user),
    active_only: bool = Query(True),
):
    return [AllowanceRead.model_validate(a)
            for a in crud.list_allowances_for_employee(db, employee_id, active_only)]


@router.post("/hr/employees/{employee_id}/allowances", response_model=AllowanceRead,
             status_code=status.HTTP_201_CREATED)
def create_employee_allowance(
    employee_id: int, data: EmployeeAllowanceCreate, db: DbDep, _=Depends(get_admin_user),
):
    if data.employee_id != employee_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "employee_id في الجسم لازم يطابق الـ path")
    if not crud.get_employee(db, employee_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"الموظف {employee_id} غير موجود")
    allowance = crud.create_allowance(db, data)
    db.commit()
    db.refresh(allowance)
    return AllowanceRead.model_validate(allowance)


@router.patch("/hr/allowances/{allowance_id}", response_model=AllowanceRead)
def update_employee_allowance(
    allowance_id: int, data: EmployeeAllowanceUpdate, db: DbDep, _=Depends(get_admin_user),
):
    allowance = crud.get_allowance(db, allowance_id)
    if not allowance:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"البدل {allowance_id} غير موجود")
    allowance = crud.update_allowance(db, allowance, data)
    db.commit()
    db.refresh(allowance)
    return AllowanceRead.model_validate(allowance)


# ── Leaderboard ───────────────────────────────────────────────────────

@router.get("/hr/leaderboard", response_model=list[LeaderboardEntry])
def sales_leaderboard(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    date_from: date = Query(...),
    date_to: date = Query(...),
):
    """ترتيب الموظفين حسب إجمالي المبيعات الحقيقية (مطعم/كافيه/شاطئ) خلال المدى."""
    return services.get_sales_leaderboard(db, branch_id, date_from, date_to)


# ── Payroll Runs ──────────────────────────────────────────────────────

@router.get("/hr/payroll-runs", response_model=PaginatedResponse)
def list_payroll_runs(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(24, ge=1, le=60),
):
    items, total = crud.list_payroll_runs(db, branch_id, (page - 1) * size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[PayrollRunRead.model_validate(r) for r in items])


# frontend/apps/admin/src/views/HRView.vue بينادي GET /hr/payroll/runs (مش
# /hr/payroll-runs) — path مختلف عن الـ endpoint الأساسي فوق. alias بسيط
# بيرجّع نفس البيانات بدل ما يرجّع 404 حقيقي.
@router.get("/hr/payroll/runs", response_model=PaginatedResponse)
def list_payroll_runs_alias(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    page: int = Query(1, ge=1),
    size: int = Query(24, ge=1, le=60),
):
    return list_payroll_runs(db, _, branch_id, page, size)


@router.post("/hr/payroll-runs", response_model=PayrollRunRead,
             status_code=status.HTTP_201_CREATED)
def create_payroll_run(data: PayrollRunCreate, db: DbDep, _=Depends(get_admin_user)):
    try:
        return services.run_payroll_for_branch(
            db, data.branch_id, data.period_year, data.period_month
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/hr/payroll-runs/{run_id}", response_model=PayrollRunRead)
def get_payroll_run(run_id: int, db: DbDep, _=Depends(get_manager_user)):
    run = crud.get_payroll_run(db, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "كشف الرواتب غير موجود")
    return PayrollRunRead.model_validate(run)


@router.post("/hr/payroll-runs/{run_id}/approve",
             response_model=PayrollRunRead,
             dependencies=[Depends(require_permission("hr.approve_payroll_run", "approve", min_role_level=80))])
def approve_payroll_run(run_id: int, db: DbDep, user=Depends(get_current_active_user)):
    try:
        return services.approve_payroll_run(db, run_id, approved_by=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/hr/payroll-runs/{run_id}/lines",
            response_model=list[PayrollLineRead])
def list_payroll_lines(run_id: int, db: DbDep, _=Depends(get_manager_user)):
    return [PayrollLineRead.model_validate(row) for row in crud.list_lines_for_run(db, run_id)]


# ── Attendance ────────────────────────────────────────────────────────

@router.post("/hr/attendance", response_model=AttendanceRecordRead,
             status_code=status.HTTP_201_CREATED)
def record_attendance(data: AttendanceRecordCreate, db: DbDep, _=Depends(get_manager_user)):
    row = crud.upsert_attendance(db, data)
    db.commit()
    db.refresh(row)
    return AttendanceRecordRead.model_validate(row)


@router.get("/hr/attendance", response_model=PaginatedResponse)
def list_attendance(
    db: DbDep, _=Depends(get_manager_user),
    employee_id: Optional[int] = Query(None),
    branch_id:   Optional[int] = Query(None),
    date_from:   Optional[date] = Query(None),
    date_to:     Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    items, total = crud.list_attendance(db, employee_id, branch_id, date_from, date_to,
                                        (page - 1) * size, size)
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[AttendanceRecordRead.model_validate(r) for r in items])


# ── Departments ───────────────────────────────────────────────────────

@router.get("/hr/departments", response_model=list[DepartmentRead])
def list_departments(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
):
    return [DepartmentRead.model_validate(d) for d in crud.list_departments(db, branch_id)]


@router.post("/hr/departments", response_model=DepartmentRead,
             status_code=status.HTTP_201_CREATED)
def create_department(data: DepartmentCreate, db: DbDep, _=Depends(get_manager_user)):
    dept = crud.create_department(db, data)
    db.commit()
    db.refresh(dept)
    return DepartmentRead.model_validate(dept)


# ── Shifts ────────────────────────────────────────────────────────────

@router.get("/hr/shifts", response_model=list[ShiftRead])
def list_shifts(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
):
    return [ShiftRead.model_validate(s) for s in crud.list_shifts(db, branch_id)]


@router.post("/hr/shifts", response_model=ShiftRead,
             status_code=status.HTTP_201_CREATED)
def create_shift(data: ShiftCreate, db: DbDep, _=Depends(get_manager_user)):
    shift = crud.create_shift(db, data)
    db.commit()
    db.refresh(shift)
    return ShiftRead.model_validate(shift)


# ── Attendance Policy ─────────────────────────────────────────────────
# سياسة الحضور اللي بتغذّي حساب دقايق التأخير/الأوفرتايم التلقائي (راجع
# services._compute_auto_attendance_adjustments) — قابلة للتعديل من الإدارة،
# مش hardcoded في الكود.

@router.get("/hr/attendance-policy", response_model=AttendancePolicyRead)
def get_attendance_policy(db: DbDep, _=Depends(get_manager_user), branch_id: int = Query(...)):
    policy = crud.get_attendance_policy(db, branch_id)
    if not policy:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                             "لا توجد سياسة حضور مضبوطة لهذا الفرع بعد — استخدم PUT لإنشاء واحدة")
    return AttendancePolicyRead.model_validate(policy)


@router.put("/hr/attendance-policy", response_model=AttendancePolicyRead)
def upsert_attendance_policy(
    data: AttendancePolicyUpsert, db: DbDep, _=Depends(get_manager_user), branch_id: int = Query(...),
):
    policy = crud.upsert_attendance_policy(db, branch_id, data)
    db.commit()
    db.refresh(policy)
    return AttendancePolicyRead.model_validate(policy)


# ── Leave Types ───────────────────────────────────────────────────────

@router.get("/hr/leave-types", response_model=list[LeaveTypeRead])
def list_leave_types(
    db: DbDep, _=Depends(get_current_active_user),
    branch_id: int = Query(...),
):
    # بيانات مرجعية فقط (اسم/سقف أيام) — أي موظف يحتاجها ليختار نوع إجازة في
    # طلب /hr/me/leaves/request، مش بس المدير.
    return [LeaveTypeRead.model_validate(lt) for lt in crud.list_leave_types(db, branch_id)]


@router.post("/hr/leave-types", response_model=LeaveTypeRead,
             status_code=status.HTTP_201_CREATED)
def create_leave_type(data: LeaveTypeCreate, db: DbDep, _=Depends(get_manager_user)):
    lt = crud.create_leave_type(db, data)
    db.commit()
    db.refresh(lt)
    return LeaveTypeRead.model_validate(lt)


# ── Leave Requests ────────────────────────────────────────────────────

@router.post("/hr/leave-requests", response_model=LeaveRequestRead,
             status_code=status.HTTP_201_CREATED)
def create_leave_request(data: LeaveRequestCreate, db: DbDep, _=Depends(get_current_active_user)):
    try:
        req = services.request_leave(
            db,
            employee_id=data.employee_id,
            branch_id=data.branch_id,
            leave_type_id=data.leave_type_id,
            start_date=data.start_date,
            end_date=data.end_date,
            reason=data.reason,
        )
        return LeaveRequestRead.model_validate(req)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/hr/leave-requests", response_model=PaginatedResponse)
def list_leave_requests(
    db: DbDep, _=Depends(get_manager_user),
    branch_id:   int = Query(...),
    employee_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    items, total = crud.list_leave_requests(
        db, branch_id, employee_id, status_filter, (page - 1) * size, size
    )
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[LeaveRequestRead.model_validate(r) for r in items])


@router.patch("/hr/leave-requests/{request_id}/approve",
              response_model=LeaveRequestRead,
              dependencies=[Depends(require_permission("hr.approve_leave", "approve", min_role_level=60))])
def approve_leave_request(
    request_id: int, body: LeaveApproveRequest, db: DbDep, user=Depends(get_current_active_user)
):
    # ⚠️ body.approved_by متجاهَل عمدًا — كان بيثق في قيمة من الـ client مباشرة
    # (أي حد بصلاحية manager+ يقدر يبعت approved_by = أي user_id، حتى لو مش
    # هو اللي عامل الطلب فعليًا)، وده كمان كان بيلغي أي معنى لفحص
    # "منع الاعتماد الذاتي" في services.approve_leave لأنه بيعتمد على approved_by.
    # approved_by الحقيقي دايمًا هو المستخدم المصادَق عليه (user.id)، زي alias
    # /hr/leaves/{id} تحت واللي كان صحيح من الأول. الحقل باقٍ في الـ schema
    # بس لتوافق شكل الـ request مع أي عميل قديم بيبعته.
    try:
        req = services.approve_leave(db, request_id, user.id)
        return LeaveRequestRead.model_validate(req)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.patch("/hr/leave-requests/{request_id}/reject",
              response_model=LeaveRequestRead)
def reject_leave_request(
    request_id: int, body: LeaveRejectRequest, db: DbDep, _=Depends(get_manager_user)
):
    try:
        req = services.reject_leave(db, request_id, body.reason)
        return LeaveRequestRead.model_validate(req)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── /hr/leaves alias ─────────────────────────────────────────────────
# frontend/apps/admin/src/views/HRView.vue بينادي GET /hr/leaves و
# PATCH /hr/leaves/{id} بـ body {"status": "approved"|"rejected"} — path
# ومنطق مختلفين تماماً عن /hr/leave-requests فوق (مفيش route كان متوصّل
# خالص، فكان 404 حقيقي). الـ GET alias بسيط. الـ PATCH بيحوّل الجسم
# البسيط لنفس الـ approve/reject services الموجودة (المستخدم الحالي هو
# approved_by، ورفض بسبب افتراضي لو الـ frontend مبعتش سبب).
#
# ✅ تحديث: تم ربط Employee↔User (Employee.user_id) — self-service الحقيقي
# (تقديم إجازة، مشاهدة حضور/راتب/بروفايل) موجود دلوقتي تحت /hr/me/* تحت.
# GET/PATCH هنا فوق (/hr/leaves) لسه إدارية (manager+) — تشوف/تعتمد طلبات
# *كل* الموظفين في الفرع، مش طلب موظف واحد لنفسه.

@router.get("/hr/leaves", response_model=PaginatedResponse)
def list_leaves_alias(
    db: DbDep, _=Depends(get_manager_user),
    branch_id:   int = Query(...),
    employee_id: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    return list_leave_requests(db, _, branch_id, employee_id, status_filter, page, size)


@router.patch("/hr/leaves/{request_id}", response_model=LeaveRequestRead)
def update_leave_status_alias(
    request_id: int, body: LeaveStatusUpdate, db: DbDep, user=Depends(get_manager_user),
):
    try:
        if body.status == "approved":
            req = services.approve_leave(db, request_id, user.id)
        else:
            req = services.reject_leave(db, request_id, "مرفوض من الإدارة")
        return LeaveRequestRead.model_validate(req)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ── Self-Service (/hr/me/*) ──────────────────────────────────────────
# مبنية على Employee.user_id ↔ current_user.id — كل endpoint هنا بيرجّع
# بيانات صاحب الحساب نفسه بس، ومفتوح لأي مستخدم مسجّل دخول (مش role-gated)
# لأن ده self-service حقيقي، مش أداة إدارية.

def _my_employee_or_404(db: DbDep, user):
    try:
        return services.get_my_employee_or_404(db, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get("/hr/me/profile", response_model=MyProfileRead)
def get_my_profile(db: DbDep, user=Depends(get_current_active_user)):
    emp = _my_employee_or_404(db, user)
    return MyProfileRead.model_validate(emp)


@router.get("/hr/me/attendance", response_model=PaginatedResponse)
def get_my_attendance(
    db: DbDep, user=Depends(get_current_active_user),
    date_from: Optional[date] = Query(None),
    date_to:   Optional[date] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    emp = _my_employee_or_404(db, user)
    items, total = crud.list_attendance(
        db, employee_id=emp.id, date_from=date_from, date_to=date_to,
        skip=(page - 1) * size, limit=size,
    )
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[AttendanceRecordRead.model_validate(r) for r in items])


@router.post("/hr/me/attendance/punch-in", response_model=AttendanceRecordRead,
             status_code=status.HTTP_201_CREATED)
def punch_in(db: DbDep, user=Depends(get_current_active_user)):
    try:
        record = services.punch_in(db, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return AttendanceRecordRead.model_validate(record)


@router.post("/hr/me/attendance/punch-out", response_model=AttendanceRecordRead)
def punch_out(db: DbDep, user=Depends(get_current_active_user)):
    try:
        record = services.punch_out(db, user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return AttendanceRecordRead.model_validate(record)


@router.get("/hr/me/leaves", response_model=PaginatedResponse)
def get_my_leaves(
    db: DbDep, user=Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    emp = _my_employee_or_404(db, user)
    items, total = crud.list_leave_requests(
        db, emp.branch_id, employee_id=emp.id, skip=(page - 1) * size, limit=size,
    )
    return PaginatedResponse(total=total, page=page, size=size,
                             items=[LeaveRequestRead.model_validate(r) for r in items])


@router.post("/hr/me/leaves/request", response_model=LeaveRequestRead,
             status_code=status.HTTP_201_CREATED)
def request_my_leave(data: MyLeaveRequestCreate, db: DbDep, user=Depends(get_current_active_user)):
    try:
        req = services.request_my_leave(
            db, user.id, data.leave_type_id, data.start_date, data.end_date, data.reason,
        )
        return LeaveRequestRead.model_validate(req)
    except ValueError as exc:
        msg = str(exc)
        code = status.HTTP_404_NOT_FOUND if "ملف موظف" in msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(code, msg)


@router.get("/hr/me/payslips", response_model=PaginatedResponse)
def get_my_payslips(
    db: DbDep, user=Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    size: int = Query(24, ge=1, le=60),
):
    emp = _my_employee_or_404(db, user)
    lines, total = crud.list_payslips_for_employee(db, emp.id, skip=(page - 1) * size, limit=size)
    items = [
        MyPayslipRead(
            id=line.id, payroll_run_id=line.payroll_run_id,
            period_year=line.run.period_year, period_month=line.run.period_month,
            status=line.run.status,
            basic_salary=line.basic_salary, gross_salary=line.gross_salary, net_salary=line.net_salary,
            employee_si=line.employee_si, monthly_tax=line.monthly_tax,
            penalty_deduction=line.penalty_deduction,
            late_penalty_deduction=line.late_penalty_deduction,
            unpaid_leave_deduction=line.unpaid_leave_deduction,
        )
        for line in lines
    ]
    return PaginatedResponse(total=total, page=page, size=size, items=items)


# ── Payroll Config (Social Insurance / Tax Brackets) ───────────────────
# الموديلان (SocialInsuranceConfig/TaxBracketConfig) موجودين ومقروئين فعليًا
# جوه حساب الراتب (hr_engine)، بس مفيش أي schema/router لإضافة نسخة جديدة
# لما القانون يتغيّر — كانت الطريقة الوحيدة INSERT مباشر في الداتابيز
# (زي seed.py). admin-only لأنه بيأثر على حساب راتب كل الموظفين.

@router.post("/hr/config/social-insurance", response_model=SocialInsuranceConfigRead,
             status_code=status.HTTP_201_CREATED)
def create_social_insurance_config(
    data: SocialInsuranceConfigCreate, db: DbDep, _=Depends(get_admin_user),
):
    obj = crud.create_si_config(db, data)
    db.commit()
    db.refresh(obj)
    return SocialInsuranceConfigRead.model_validate(obj)


@router.get("/hr/config/social-insurance", response_model=list[SocialInsuranceConfigRead])
def list_social_insurance_configs(db: DbDep, _=Depends(get_admin_user)):
    return [SocialInsuranceConfigRead.model_validate(c) for c in crud.list_si_configs(db)]


@router.post("/hr/config/tax-brackets", response_model=TaxBracketConfigRead,
             status_code=status.HTTP_201_CREATED)
def create_tax_bracket_config(
    data: TaxBracketConfigCreate, db: DbDep, _=Depends(get_admin_user),
):
    obj = crud.create_tax_bracket(db, data)
    db.commit()
    db.refresh(obj)
    return TaxBracketConfigRead.model_validate(obj)


@router.get("/hr/config/tax-brackets", response_model=list[TaxBracketConfigRead])
def list_tax_bracket_configs(db: DbDep, _=Depends(get_admin_user)):
    return [TaxBracketConfigRead.model_validate(c) for c in crud.list_tax_brackets(db)]


# ── Penalty Types ─────────────────────────────────────────────────────
# PenaltyTypeCreate/Read schemas كانوا موجودين بالكامل من غير أي crud/router —
# EmployeePenalty.penalty_type_id اختياري فعلاً، فالنظام كان يشتغل من غيره،
# لكن مفيش طريقة لتعريف أنواع جزاءات موحّدة (تأخير/غياب/مخالفة زي...) بدل ما
# كل مدير يكتب سبب حر كل مرة — نفس فئة الباج الموثّقة مرارًا في هذا المشروع.

@router.post("/hr/penalty-types", response_model=PenaltyTypeRead,
             status_code=status.HTTP_201_CREATED)
def create_penalty_type(data: PenaltyTypeCreate, db: DbDep, _=Depends(get_manager_user)):
    penalty_type = crud.create_penalty_type(db, data)
    db.commit()
    db.refresh(penalty_type)
    return PenaltyTypeRead.model_validate(penalty_type)


@router.get("/hr/penalty-types", response_model=list[PenaltyTypeRead])
def list_penalty_types(
    db: DbDep, _=Depends(get_current_active_user),
    branch_id: int = Query(...),
):
    # بيانات مرجعية فقط (اسم/عدد أيام الجزاء) — أي مستخدم مسجّل دخول يقدر
    # يشوفها (نفس منطق GET /hr/leave-types)، الإنشاء بس محصور بـ manager+.
    return [PenaltyTypeRead.model_validate(t) for t in crud.list_penalty_types(db, branch_id)]


# ── Penalties ─────────────────────────────────────────────────────────

@router.post("/hr/penalties", response_model=EmployeePenaltyRead,
             status_code=status.HTTP_201_CREATED)
def create_penalty(data: EmployeePenaltyCreate, db: DbDep, _=Depends(get_manager_user)):
    penalty = crud.create_penalty(db, data)
    db.commit()
    db.refresh(penalty)
    return EmployeePenaltyRead.model_validate(penalty)


@router.get("/hr/penalties", response_model=list[EmployeePenaltyRead])
def list_penalties(
    db: DbDep, _=Depends(get_manager_user),
    branch_id:   int = Query(...),
    employee_id: Optional[int] = Query(None),
    month:       Optional[str] = Query(None, description="YYYY-MM"),
):
    items = crud.list_penalties(db, branch_id, employee_id, month)
    return [EmployeePenaltyRead.model_validate(p) for p in items]


# ── Rota Templates ────────────────────────────────────────────────────
# RotaTemplate كان موجود بالكامل في models.py من غير أي schema/crud/router —
# نفس فئة الباج (Lead/Campaign/TenantCashLog/CallNote).

@router.get("/hr/rota/templates", response_model=list[RotaTemplateRead])
def list_rota_templates(
    db: DbDep, _=Depends(get_manager_user),
    branch_id: int = Query(...),
    department_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
):
    items = crud.list_rota_templates(db, branch_id, department_id, is_active)
    return [RotaTemplateRead.model_validate(t) for t in items]


@router.post("/hr/rota/templates", response_model=RotaTemplateRead,
             status_code=status.HTTP_201_CREATED)
def create_rota_template(data: RotaTemplateCreate, db: DbDep, _=Depends(get_manager_user)):
    template = crud.create_rota_template(db, data)
    db.commit()
    db.refresh(template)
    return RotaTemplateRead.model_validate(template)


@router.get("/hr/rota/templates/{template_id}", response_model=RotaTemplateRead)
def get_rota_template(template_id: int, db: DbDep, _=Depends(get_manager_user)):
    template = crud.get_rota_template(db, template_id)
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"قالب الجدول {template_id} غير موجود")
    return RotaTemplateRead.model_validate(template)


@router.patch("/hr/rota/templates/{template_id}", response_model=RotaTemplateRead)
def update_rota_template(template_id: int, data: RotaTemplateUpdate, db: DbDep,
                         _=Depends(get_manager_user)):
    template = crud.get_rota_template(db, template_id)
    if not template:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"قالب الجدول {template_id} غير موجود")
    template = crud.update_rota_template(db, template, data)
    db.commit()
    db.refresh(template)
    return RotaTemplateRead.model_validate(template)


# ── Rota ──────────────────────────────────────────────────────────────

@router.get("/hr/rota", response_model=list[RotaAssignmentRead])
def get_rota(
    db: DbDep, _=Depends(get_manager_user),
    branch_id:   int = Query(...),
    week_start:  date = Query(...),
    week_end:    date = Query(...),
    employee_id: Optional[int] = Query(None),
):
    items = crud.list_rota_assignments(db, branch_id, week_start, week_end, employee_id)
    return [RotaAssignmentRead.model_validate(a) for a in items]


@router.get("/hr/payroll/{run_id}/payslip/{employee_id}")
def download_payslip(run_id: int, employee_id: int, db: DbDep, _=Depends(get_current_active_user)):
    try:
        pdf = services.generate_payslip_pdf(db, run_id, employee_id)
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=payslip-{run_id}-{employee_id}.pdf"},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.get("/hr/payroll/{run_id}/excel")
def download_payroll_excel(run_id: int, db: DbDep, _=Depends(get_manager_user)):
    try:
        xlsx = services.generate_payroll_excel(db, run_id)
        return Response(
            content=xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=payroll-{run_id}.xlsx"},
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/hr/rota/assignments", response_model=RotaAssignmentRead,
             status_code=status.HTTP_201_CREATED)
def create_rota_assignment(data: RotaAssignmentCreate, db: DbDep, _=Depends(get_manager_user)):
    assignment = crud.create_rota_assignment(db, data)
    db.commit()
    db.refresh(assignment)
    return RotaAssignmentRead.model_validate(assignment)


@router.post("/hr/rota/swap-requests", response_model=ShiftSwapRequestRead,
             status_code=status.HTTP_201_CREATED)
def create_swap_request(data: ShiftSwapRequestCreate, db: DbDep, _=Depends(get_current_active_user)):
    swap = crud.create_swap_request(db, data)
    db.commit()
    db.refresh(swap)
    return ShiftSwapRequestRead.model_validate(swap)


@router.patch("/hr/rota/swap-requests/{swap_id}/approve",
              response_model=ShiftSwapRequestRead)
def approve_swap_request(swap_id: int, db: DbDep, user=Depends(get_manager_user)):
    swap = crud.get_swap_request(db, swap_id)
    if not swap:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "طلب التبديل غير موجود")
    if swap.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"الطلب في حالة '{swap.status}'")
    approved = crud.approve_swap(db, swap, user.id)
    db.commit()
    db.refresh(approved)
    return ShiftSwapRequestRead.model_validate(approved)
