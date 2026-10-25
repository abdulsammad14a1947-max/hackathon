"""Pydantic schemas for the Payroll Lite endpoints (M6)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------- salary structures
class SalaryStructureCreate(BaseModel):
    employee_id: int = Field(..., description="Employee the structure belongs to")
    basic_salary: float = Field(..., gt=0, description="Monthly basic salary (> 0)")
    effective_from: dt.date = Field(
        default_factory=dt.date.today, description="First day the structure applies"
    )
    effective_to: dt.date | None = Field(
        default=None, description="Optional last day the structure applies"
    )


class SalaryStructureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    basic_salary: float
    effective_from: dt.date
    effective_to: dt.date | None = None
    # denormalised context for the UI
    employee_code: str | None = None
    employee_name: str | None = None
    department: str | None = None


class SalaryStructurePage(BaseModel):
    items: list[SalaryStructureOut]
    total: int


# ---------------------------------------------------------------- payroll runs
class PayrollRunCreate(BaseModel):
    year: int = Field(..., ge=1970, le=2200, description="Period year")
    month: int = Field(..., ge=1, le=12, description="Period month (1-12)")


class PayrollRunOut(BaseModel):
    id: int
    period_year: int
    period_month: int
    status: str
    generated_by: int | None = None
    generated_at: dt.datetime | None = None
    finalized_by: int | None = None
    finalized_at: dt.datetime | None = None
    total_gross: float = 0
    total_deductions: float = 0
    total_net: float = 0
    item_count: int = 0


class PayrollRunPage(BaseModel):
    items: list[PayrollRunOut]
    total: int
    page: int
    page_size: int


class PayrollItemOut(BaseModel):
    id: int
    run_id: int
    employee_id: int
    employee_code: str | None = None
    employee_name: str | None = None
    department: str | None = None
    designation: str | None = None
    basic: float
    hra: float
    medical: float
    gross: float
    working_days: float
    present_days: float
    absent_days: float
    unpaid_leave_days: float
    half_days: float
    deduction_amount: float
    tax: float
    net_pay: float
    note: str | None = None


class PayslipOut(PayrollItemOut):
    """A finalized payroll item as seen by its owner."""

    period_year: int
    period_month: int
    status: str = "finalized"


class PayslipPage(BaseModel):
    items: list[PayslipOut]
    total: int
