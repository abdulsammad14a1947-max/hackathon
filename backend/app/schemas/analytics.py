"""Pydantic response schemas for the dashboards (M7).

The services return plain dicts (frozen signatures in ARCHITECTURE §5b); these
models only document/validate the HTTP payloads.
"""
from __future__ import annotations

from pydantic import BaseModel


class DepartmentCount(BaseModel):
    department: str
    count: int


class DepartmentCost(BaseModel):
    department: str
    gross: float = 0
    net: float = 0


class AdminSummaryOut(BaseModel):
    active_headcount: int
    attrition_ytd: int
    attrition_pct: float = 0
    payroll_cost: float
    payroll_basis: str
    avg_salary: float
    avg_basic_salary: float = 0
    headcount_by_department: list[DepartmentCount]
    payroll_cost_by_department: list[DepartmentCost]
    gender_breakdown: dict[str, int]
    tenure_months_avg: float
    recent_audit: list[dict]


class DayTrend(BaseModel):
    date: str
    present: int
    late: int
    absent: int


class PendingApprovals(BaseModel):
    leave_requests: int
    corrections: int


class LeaveUtilization(BaseModel):
    leave_type: str
    used: float
    quota: int | None
    utilization: float | None = None


class DepartmentAbsenteeism(BaseModel):
    department: str
    absent_days: float
    expected_days: float
    rate: float


class LateComer(BaseModel):
    employee_id: int
    employee_code: str | None = None
    employee_name: str | None = None
    department: str | None = None
    late_count: int


class HRSummaryOut(BaseModel):
    headcount: int
    present: int
    late: int
    on_leave: int
    half_day: int = 0
    attendance_rate: float = 0
    late_pct: float = 0
    pending_approvals: PendingApprovals
    attendance_trend: list[DayTrend]
    absenteeism_by_department: list[DepartmentAbsenteeism]
    leave_utilization: list[LeaveUtilization]
    top_late_comers: list[LateComer]
    insights: list[str]


class LeaveBalanceRow(BaseModel):
    code: str
    name: str
    quota: int | None
    used: float
    pending: float
    remaining: float | None
    is_paid: bool


class PayslipRef(BaseModel):
    id: int
    period: str
    net_pay: float


class EmployeeSummaryOut(BaseModel):
    today_status: str
    week_hours: float
    week_hours_target: float = 40
    late_count_this_month: int
    leave_balances: list[LeaveBalanceRow]
    recent_attendance: list[dict]
    last_payslip: PayslipRef | None = None
    announcement_count: int
