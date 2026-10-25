"""Employee directory service (owner: backend-engineer A).

`search_employees` is a FROZEN cross-module contract (ARCHITECTURE §5b) — other
modules and the AI tools import it with exactly this signature.
"""
from __future__ import annotations

import datetime as dt
import secrets
import string
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.security import hash_password
from app.models import (
    Attendance,
    Department,
    Designation,
    Employee,
    LeaveRequest,
    LeaveType,
    PayrollItem,
    PayrollRun,
    User,
)
from app.utils.audit import record_audit, serialize

ATTENDANCE_STATUSES = [
    "present",
    "late",
    "half_day",
    "missing_checkout",
    "absent",
    "on_leave",
    "weekend",
    "holiday",
]

MAX_PAGE_SIZE = 100


def normalize_email(value: str | None) -> str | None:
    return value.strip().lower() if value else value


# ------------------------------------------------------------------------- search
def search_employees(
    db,
    company_id,
    q=None,
    department_id=None,
    status=None,
    page=1,
    page_size=20,
) -> dict:
    """Frozen signature (ARCHITECTURE §5b).

    Returns {"items": [{id, employee_code, full_name, email, department, designation,
    joining_date, employment_status, ...}], "total", "page", "page_size"}.
    """
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = 20
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))

    query = db.query(Employee).filter(Employee.company_id == company_id)
    if q:
        needle = f"%{str(q).strip()}%"
        query = query.filter(
            or_(
                Employee.employee_code.ilike(needle),
                Employee.email.ilike(needle),
                Employee.first_name.ilike(needle),
                Employee.last_name.ilike(needle),
            )
        )
    if department_id is not None:
        query = query.filter(Employee.department_id == department_id)
    if status:
        query = query.filter(Employee.employment_status == status)

    total = query.count()
    rows = (
        query.options(joinedload(Employee.department), joinedload(Employee.designation))
        .order_by(Employee.employee_code.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    logins = _login_map(db, company_id)
    return {
        "items": [employee_to_dict(r, logins.get(r.id)) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _login_map(db: Session, company_id: int) -> dict[int, dict[str, Any]]:
    rows = (
        db.query(User)
        .filter(User.company_id == company_id, User.employee_id.is_not(None))
        .all()
    )
    return {
        u.employee_id: {"user_id": u.id, "user_role": u.role, "user_is_active": u.is_active}
        for u in rows
        if u.employee_id is not None
    }


def full_name_of(emp: Employee) -> str:
    return f"{emp.first_name} {emp.last_name or ''}".strip()


def employee_to_dict(emp: Employee, login: dict[str, Any] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": emp.id,
        "employee_code": emp.employee_code,
        "first_name": emp.first_name,
        "last_name": emp.last_name,
        "full_name": full_name_of(emp),
        "email": emp.email,
        "phone": emp.phone,
        "address": emp.address,
        "department_id": emp.department_id,
        "department": emp.department.name if emp.department is not None else None,
        "designation_id": emp.designation_id,
        "designation": emp.designation.name if emp.designation is not None else None,
        "joining_date": emp.joining_date.isoformat() if emp.joining_date else None,
        "employment_status": emp.employment_status,
        "gender": emp.gender,
        "basic_salary": float(emp.basic_salary) if emp.basic_salary is not None else None,
        "user_id": None,
        "user_role": None,
        "user_is_active": None,
    }
    if login is not None:
        data.update(login)
    elif emp.user is not None:
        data.update(
            {
                "user_id": emp.user.id,
                "user_role": emp.user.role,
                "user_is_active": emp.user.is_active,
            }
        )
    return data


# --------------------------------------------------------------------- validation
def validate_employee_data(
    db: Session,
    company_id: int,
    data: dict[str, Any],
    *,
    exclude_employee_id: int | None = None,
    exclude_user_id: int | None = None,
) -> dict[str, str]:
    """Structural + uniqueness checks. Returns {field: reason} (empty = valid).

    `department_id`/`designation_id` must belong to the company (422 class),
    `employee_code` is unique per company and `email` unique as a login (409 class).
    """
    errors: dict[str, str] = {}

    dept_id = data.get("department_id")
    if dept_id is not None:
        found = (
            db.query(Department.id)
            .filter(Department.id == dept_id, Department.company_id == company_id)
            .first()
        )
        if found is None:
            errors["department_id"] = "Department does not exist in this company"

    desig_id = data.get("designation_id")
    if desig_id is not None:
        found = (
            db.query(Designation.id)
            .filter(Designation.id == desig_id, Designation.company_id == company_id)
            .first()
        )
        if found is None:
            errors["designation_id"] = "Designation does not exist in this company"

    code = (data.get("employee_code") or "").strip()
    if code:
        query = db.query(Employee).filter(
            Employee.company_id == company_id, Employee.employee_code == code
        )
        if exclude_employee_id is not None:
            query = query.filter(Employee.id != exclude_employee_id)
        if query.first() is not None:
            errors["employee_code"] = "Employee code already exists"

    email = normalize_email(data.get("email"))
    if email:
        query = db.query(Employee).filter(
            Employee.company_id == company_id, func.lower(Employee.email) == email
        )
        if exclude_employee_id is not None:
            query = query.filter(Employee.id != exclude_employee_id)
        if query.first() is not None:
            errors["email"] = "Employee email already exists"
        else:
            user_query = db.query(User).filter(func.lower(User.email) == email)
            if exclude_user_id is not None:
                user_query = user_query.filter(User.id != exclude_user_id)
            if user_query.first() is not None:
                errors["email"] = "Email already used by a login account"

    return errors


# ------------------------------------------------------------------------- create
def generate_temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    body = "".join(secrets.choice(alphabet) for _ in range(12))
    return f"Tmp-{body}"


def create_employee(
    db: Session,
    company_id: int,
    data: dict[str, Any],
    *,
    role: str = "employee",
    actor: User | None = None,
    commit: bool = True,
) -> tuple[Employee, str]:
    """Create Employee + login user (must_change_password=True). Returns (employee, temp_password)."""
    emp = Employee(
        company_id=company_id,
        employee_code=str(data["employee_code"]).strip(),
        first_name=str(data["first_name"]).strip(),
        last_name=(data.get("last_name") or "").strip() or None,
        email=normalize_email(str(data["email"])) or "",
        phone=data.get("phone"),
        address=data.get("address"),
        department_id=data.get("department_id"),
        designation_id=data.get("designation_id"),
        joining_date=data["joining_date"],
        employment_status=data.get("employment_status") or "active",
        gender=data.get("gender"),
        basic_salary=data["basic_salary"],
    )
    db.add(emp)
    db.flush()

    temp_password = generate_temp_password()
    user = User(
        company_id=company_id,
        email=emp.email,
        password_hash=hash_password(temp_password),
        role=role,
        full_name=full_name_of(emp),
        employee_id=emp.id,
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    record_audit(
        db,
        company_id=company_id,
        user=actor,
        action="employee_create",
        entity_type="employee",
        entity_id=emp.id,
        after=serialize(emp),
    )
    if commit:
        db.commit()
        db.refresh(emp)
    return emp, temp_password


# ------------------------------------------------------------------- 360 profile
def attendance_summary(
    db: Session, company_id: int, employee_id: int, days: int = 30
) -> dict[str, Any]:
    today = dt.date.today()
    date_from = today - dt.timedelta(days=days - 1)
    rows = (
        db.query(Attendance.status, func.count(Attendance.id))
        .filter(
            Attendance.company_id == company_id,
            Attendance.employee_id == employee_id,
            Attendance.date >= date_from,
            Attendance.date <= today,
        )
        .group_by(Attendance.status)
        .all()
    )
    by_status = {name: 0 for name in ATTENDANCE_STATUSES}
    for status_name, count in rows:
        by_status[status_name] = count
    total_hours = (
        db.query(func.coalesce(func.sum(Attendance.worked_hours), 0.0))
        .filter(
            Attendance.company_id == company_id,
            Attendance.employee_id == employee_id,
            Attendance.date >= date_from,
            Attendance.date <= today,
        )
        .scalar()
        or 0.0
    )
    return {
        "days": days,
        "date_from": date_from.isoformat(),
        "date_to": today.isoformat(),
        "records": sum(by_status.values()),
        "by_status": by_status,
        "total_hours": round(float(total_hours), 2),
    }


def leave_history(db: Session, company_id: int, employee_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(LeaveRequest, LeaveType)
        .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
        .filter(
            LeaveRequest.company_id == company_id,
            LeaveRequest.employee_id == employee_id,
        )
        .order_by(LeaveRequest.start_date.desc(), LeaveRequest.id.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": req.id,
            "leave_type_id": req.leave_type_id,
            "code": lt.code,
            "leave_type": lt.name,
            "start_date": req.start_date.isoformat() if req.start_date else None,
            "end_date": req.end_date.isoformat() if req.end_date else None,
            "working_days": float(req.working_days or 0),
            "status": req.status,
            "reason": req.reason,
            "review_comment": req.review_comment,
        }
        for req, lt in rows
    ]


def payroll_history(db: Session, company_id: int, employee_id: int) -> list[dict[str, Any]]:
    """Only finalized runs are visible (draft payroll is not yet a payslip)."""
    rows = (
        db.query(PayrollItem, PayrollRun)
        .join(PayrollRun, PayrollItem.run_id == PayrollRun.id)
        .filter(
            PayrollItem.company_id == company_id,
            PayrollItem.employee_id == employee_id,
            PayrollRun.status == "finalized",
        )
        .order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())
        .limit(60)
        .all()
    )
    return [
        {
            "id": item.id,
            "run_id": item.run_id,
            "period_year": run.period_year,
            "period_month": run.period_month,
            "basic": float(item.basic or 0),
            "hra": float(item.hra or 0),
            "medical": float(item.medical or 0),
            "gross": float(item.gross or 0),
            "deduction_amount": float(item.deduction_amount or 0),
            "tax": float(item.tax or 0),
            "net_pay": float(item.net_pay or 0),
        }
        for item, run in rows
    ]


def employee_profile(
    db: Session, company_id: int, employee_id: int, *, include_salary: bool
) -> dict[str, Any] | None:
    emp = (
        db.query(Employee)
        .options(joinedload(Employee.department), joinedload(Employee.designation))
        .filter(Employee.id == employee_id, Employee.company_id == company_id)
        .first()
    )
    if emp is None:
        return None
    payload = employee_to_dict(emp)
    if not include_salary:
        payload["basic_salary"] = None
    return {
        "employee": payload,
        "attendance_summary": attendance_summary(db, company_id, employee_id),
        "leave_history": leave_history(db, company_id, employee_id),
        "payroll_history": payroll_history(db, company_id, employee_id)
        if include_salary
        else [],
        "can_view_salary": include_salary,
    }
