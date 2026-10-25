"""Employee schemas (create/update, 360 profile, CSV import, password resets)."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.auth import EmailInput


class EmployeeCreate(BaseModel):
    employee_code: str = Field(min_length=1, max_length=40)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    email: EmailInput
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=400)
    department_id: int
    designation_id: int | None = None
    joining_date: dt.date
    basic_salary: float = Field(gt=0)
    gender: Literal["male", "female", "other"] | None = None
    create_login_role: Literal["employee", "hr"] = "employee"


class EmployeeUpdate(BaseModel):
    """HR/Admin employment-record update. Never carries a `role` field (roles are immutable)."""

    employee_code: str | None = Field(default=None, min_length=1, max_length=40)
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    email: EmailInput | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=400)
    department_id: int | None = None
    designation_id: int | None = None
    joining_date: dt.date | None = None
    employment_status: Literal["active", "inactive", "terminated"] | None = None
    gender: Literal["male", "female", "other"] | None = None
    basic_salary: float | None = Field(default=None, gt=0)


class EmployeeSelfUpdate(BaseModel):
    """Employee self-service: phone + address ONLY. Anything else -> 422."""

    model_config = {"extra": "forbid"}

    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=400)


class EmployeeOut(BaseModel):
    id: int
    employee_code: str
    first_name: str
    last_name: str | None = None
    full_name: str
    email: str
    phone: str | None = None
    address: str | None = None
    department_id: int | None = None
    department: str | None = None
    designation_id: int | None = None
    designation: str | None = None
    joining_date: str | None = None
    employment_status: str
    gender: str | None = None
    basic_salary: float | None = None
    user_id: int | None = None
    user_role: str | None = None
    user_is_active: bool | None = None


class EmployeeProfile(BaseModel):
    employee: EmployeeOut
    attendance_summary: dict
    leave_history: list[dict]
    payroll_history: list[dict]
    can_view_salary: bool = True


class CreateEmployeeResponse(BaseModel):
    employee: EmployeeOut
    temp_password: str


class ResetPasswordResponse(BaseModel):
    employee_id: int
    email: str
    temp_password: str
    must_change_password: bool = True


class ImportRowError(BaseModel):
    field: str
    reason: str


class ImportRowResult(BaseModel):
    row: int
    errors: list[ImportRowError] = []
    created: bool | None = None
    employee_code: str | None = None
    temp_password: str | None = None


class ImportResponse(BaseModel):
    dry_run: bool
    rows: list[ImportRowResult]
    valid_count: int
    error_count: int
    would_create: int | None = None
    created_count: int | None = None
