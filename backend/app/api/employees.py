"""Employee directory endpoints: list, create, 360 profile, update, CSV import/export.

Access rules (brief §8 matrix — ARCHITECTURE §4):
  - GET list/{id} -> HR+Admin (Admin View, HR Manage/All)
  - POST create -> HR registers employees; Admin may only create an HR login
    (create_login_role="hr" is Admin-only, everything else is HR-only)
  - import/export/patch -> HR only (Admin has no access per #06/#08)
  - reset/deactivate/activate -> Admin any login; HR only employee-role logins (#05)
  - GET /{id} -> any role, but employees may only read their own record
  - PATCH /me -> self, phone/address only
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_hr, require_roles
from app.core.security import hash_password
from app.models import Employee, User
from app.schemas.employees import (
    CreateEmployeeResponse,
    EmployeeCreate,
    EmployeeProfile,
    EmployeeSelfUpdate,
    EmployeeUpdate,
    ImportResponse,
    ResetPasswordResponse,
)
from app.services import csv_import_service, employee_service
from app.services.employee_service import employee_to_dict, full_name_of
from app.utils.audit import record_audit, serialize

router = APIRouter(prefix="/api/employees", tags=["employees"])

_DUP_FIELDS = {"employee_code", "email"}


def _raise_validation(errors: dict[str, str]) -> None:
    """409 for uniqueness conflicts, 422 for structural problems (ARCHITECTURE §4)."""
    if not errors:
        return
    if any(key in _DUP_FIELDS for key in errors):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="; ".join(f"{k}: {v}" for k, v in errors.items()),
        )
    raise HTTPException(
        status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=[f"{k}: {v}" for k, v in errors.items()],
    )


def _get_employee_or_404(db: Session, company_id: int, employee_id: int) -> Employee:
    emp = (
        db.query(Employee)
        .filter(Employee.id == employee_id, Employee.company_id == company_id)
        .first()
    )
    if emp is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return emp


def _ensure_login_scope(user: User, login_user: User | None) -> None:
    """Brief matrix #05: Admin manages any login; HR may only manage employee logins."""
    if (
        user.role != "admin"
        and login_user is not None
        and login_user.role in ("hr", "admin")
    ):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only an Admin can manage this login",
        )


# --------------------------------------------------------------------------- list
@router.get("")
def list_employees(
    q: str | None = Query(default=None, max_length=100),
    department_id: int | None = Query(default=None),
    status: str | None = Query(default=None, max_length=20),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
) -> dict:
    return employee_service.search_employees(
        db,
        user.company_id,
        q=q,
        department_id=department_id,
        status=status,
        page=page,
        page_size=page_size,
    )


# -------------------------------------------------------------------------- create
@router.post("", status_code=http_status.HTTP_201_CREATED, response_model=CreateEmployeeResponse)
def create_employee(
    payload: EmployeeCreate,
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
) -> dict:
    data = payload.model_dump()
    role = data.pop("create_login_role", "employee")
    # Brief matrix: #05 "Create HR logins" = Admin only; #06 "Register employee" = HR only.
    if role == "hr":
        if user.role != "admin":
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Only an Admin can create HR logins",
            )
    elif user.role != "hr":
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only HR can register employees",
        )
    errors = employee_service.validate_employee_data(db, user.company_id, data)
    _raise_validation(errors)

    emp, temp_password = employee_service.create_employee(
        db, user.company_id, data, role=role, actor=user
    )
    return {"employee": employee_to_dict(emp), "temp_password": temp_password}


# ------------------------------------------------------------------- CSV import/out
@router.post("/import", response_model=ImportResponse)
async def import_employees(
    dry_run: bool = Query(default=True),
    file: UploadFile = File(...),
    user: User = Depends(require_roles("hr")),  # brief matrix #08: Admin has no access
    db: Session = Depends(get_db),
) -> dict:
    raw = await file.read()
    return csv_import_service.process_import(
        db, user.company_id, raw, dry_run=dry_run, actor=user
    )


@router.get("/export")
def export_employees(
    user: User = Depends(require_roles("hr")),  # brief matrix #08: Admin has no access
    db: Session = Depends(get_db),
) -> Response:
    text = csv_import_service.export_csv(db, user.company_id)
    return Response(
        content=text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="employees.csv"'},
    )


# ---------------------------------------------------------------------- self update
@router.patch("/me")
def update_me(
    payload: EmployeeSelfUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.employee_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN, detail="No employee profile"
        )
    emp = _get_employee_or_404(db, user.company_id, user.employee_id)
    fields = set(payload.model_fields_set)
    if fields:
        before = serialize(emp)
        if "phone" in fields:
            emp.phone = payload.phone
        if "address" in fields:
            emp.address = payload.address
        record_audit(
            db,
            company_id=user.company_id,
            user=user,
            action="employee_self_update",
            entity_type="employee",
            entity_id=emp.id,
            before=before,
            after=serialize(emp),
        )
        db.commit()
        db.refresh(emp)
    return {"employee": employee_to_dict(emp)}


# ------------------------------------------------------------------ 360° profile
@router.get("/{employee_id}", response_model=EmployeeProfile)
def get_employee(
    employee_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.role == "employee":
        if user.employee_id is None or user.employee_id != employee_id:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Access denied to other employee profile",
            )
    include_salary = user.role in ("admin", "hr") or user.employee_id == employee_id
    profile = employee_service.employee_profile(
        db, user.company_id, employee_id, include_salary=include_salary
    )
    if profile is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )
    return profile


# ---------------------------------------------------------------------- staff update
@router.patch("/{employee_id}")
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    user: User = Depends(require_roles("hr")),  # brief matrix #06: Admin View, HR Manage
    db: Session = Depends(get_db),
) -> dict:
    emp = _get_employee_or_404(db, user.company_id, employee_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return {"employee": employee_to_dict(emp)}

    login_user = db.query(User).filter(User.employee_id == emp.id).first()
    errors = employee_service.validate_employee_data(
        db,
        user.company_id,
        data,
        exclude_employee_id=emp.id,
        exclude_user_id=login_user.id if login_user else None,
    )
    _raise_validation(errors)

    before = serialize(emp)
    for key, value in data.items():
        setattr(emp, key, value)

    if login_user is not None:
        login_user.email = emp.email
        login_user.full_name = full_name_of(emp)

    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="employee_update",
        entity_type="employee",
        entity_id=emp.id,
        before=before,
        after=serialize(emp),
    )
    db.commit()
    db.refresh(emp)
    return {"employee": employee_to_dict(emp)}


# ------------------------------------------------------------------- account actions
@router.post(
    "/{employee_id}/reset-password", response_model=ResetPasswordResponse
)
def reset_password(
    employee_id: int,
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
) -> dict:
    emp = _get_employee_or_404(db, user.company_id, employee_id)
    login_user = db.query(User).filter(User.employee_id == emp.id).first()
    _ensure_login_scope(user, login_user)
    if login_user is None:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="This employee has no login account",
        )

    temp_password = employee_service.generate_temp_password()
    login_user.password_hash = hash_password(temp_password)
    login_user.must_change_password = True
    login_user.is_active = True
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="password_reset",
        entity_type="user",
        entity_id=login_user.id,
        after={"employee_id": emp.id, "must_change_password": True},
    )
    db.commit()
    return {
        "employee_id": emp.id,
        "email": login_user.email,
        "temp_password": temp_password,
        "must_change_password": True,
    }


@router.post("/{employee_id}/deactivate")
def deactivate_employee(
    employee_id: int,
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
) -> dict:
    emp = _get_employee_or_404(db, user.company_id, employee_id)
    before = {"employment_status": emp.employment_status}
    login_user = db.query(User).filter(User.employee_id == emp.id).first()
    _ensure_login_scope(user, login_user)
    if login_user is not None:
        before["is_active"] = login_user.is_active
        login_user.is_active = False
    if emp.employment_status == "active":
        emp.employment_status = "inactive"
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="employee_deactivate",
        entity_type="employee",
        entity_id=emp.id,
        before=before,
        after={
            "employment_status": emp.employment_status,
            "is_active": False if login_user is not None else None,
        },
    )
    db.commit()
    db.refresh(emp)
    return {
        "employee_id": emp.id,
        "user_id": login_user.id if login_user else None,
        "is_active": login_user.is_active if login_user else None,
        "employment_status": emp.employment_status,
    }


@router.post("/{employee_id}/activate")
def activate_employee(
    employee_id: int,
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
) -> dict:
    emp = _get_employee_or_404(db, user.company_id, employee_id)
    before = {"employment_status": emp.employment_status}
    login_user = db.query(User).filter(User.employee_id == emp.id).first()
    _ensure_login_scope(user, login_user)
    if login_user is not None:
        before["is_active"] = login_user.is_active
        login_user.is_active = True
    if emp.employment_status == "inactive":
        emp.employment_status = "active"
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="employee_activate",
        entity_type="employee",
        entity_id=emp.id,
        before=before,
        after={
            "employment_status": emp.employment_status,
            "is_active": True if login_user is not None else None,
        },
    )
    db.commit()
    db.refresh(emp)
    return {
        "employee_id": emp.id,
        "user_id": login_user.id if login_user else None,
        "is_active": login_user.is_active if login_user else True,
        "employment_status": emp.employment_status,
    }
