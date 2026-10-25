"""AI tool registry — 7 read-only, permission-checked tools (brief Section 4).

Design contract:
* Each tool = JSON-schema (for the LLM's function calling) + a pydantic args model
  + an executor with signature ``(user, db, args) -> dict``.
* Executors REUSE the same services the REST API uses
  (``analytics.hr_summary`` / ``admin_summary``, ``leave_service.get_balance`` /
  ``list_requests``, ``attendance_service.summary_for_employee``,
  ``employee_service.search_employees``), so AI answers equal the dashboards by
  construction and inherit the same tenant scoping.
* ROLE SCOPING (defence in depth — the model never sees other people's data):
    employee -> own records only; company-wide/aggregated people data and
    payroll are REFUSED politely (``{"refusal": True, "message": ...}``).
    hr       -> HR scope (aggregate company data, all employees).
    admin    -> company scope.
  ``get_payroll_summary`` is HR+Admin only. Salary of another employee is never
  returned to an employee - refusal contains no numbers at all.
* EVERY argument is validated (pydantic); failures raise :class:`ToolError` with a
  friendly, 422-style message that is shown in the reply (never an HTTP 500).
* Nothing here writes to the database.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.models import Department, Employee, PayrollItem, PayrollRun, User
from app.services import analytics, attendance_service, employee_service, leave_service
from app.services.calendar_utils import get_settings

STAFF_ROLES = ("admin", "hr")


class ToolError(Exception):
    """Friendly tool failure (bad arguments / bad scope request) -> shown in reply."""


# --------------------------------------------------------------------------- helpers
def company_today(db: Session, company_id: int) -> dt.date:
    """Today's real date in the COMPANY timezone (never the client's guess)."""
    s = get_settings(db, company_id)
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(ZoneInfo(s.timezone or "Asia/Karachi")).date()
    except Exception:  # zoneinfo/tzdata missing on some Windows installs
        return dt.date.today()


def _parse_date(value: Any, field_name: str, default: dt.date) -> dt.date:
    if value is None or value == "":
        return default
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    try:
        return dt.date.fromisoformat(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ToolError(f"{field_name} must be a date in YYYY-MM-DD format (got {value!r})") from exc


def _parse_range(start: Any, end: Any, default: dt.date) -> tuple[dt.date, dt.date]:
    start_d = _parse_date(start, "date_from", default)
    end_d = _parse_date(end, "date_to", default)
    if end_d < start_d:
        start_d, end_d = end_d, start_d
    return start_d, end_d


def _is_staff(user: User) -> bool:
    return user.role in STAFF_ROLES


def _own_employee(db: Session, user: User) -> Employee | None:
    if user.employee_id is None:
        return None
    emp = db.get(Employee, user.employee_id)
    if emp is None or emp.company_id != user.company_id:
        return None
    return emp


def _refusal(message: str) -> dict:
    return {"refusal": True, "message": message}


def _resolve_department(db: Session, company_id: int, value: Any) -> tuple[int, str]:
    """Accept a department id or a (partial) name; friendly error when unknown."""
    raw = str(value).strip()
    q = db.query(Department).filter(Department.company_id == company_id)
    if raw.isdigit():
        row = q.filter(Department.id == int(raw)).first()
    else:
        row = q.filter(Department.name.ilike(f"%{raw}%")).first()
    if row is None:
        names = [
            d.name
            for d in db.query(Department)
            .filter(Department.company_id == company_id)
            .order_by(Department.name)
            .all()
        ]
        raise ToolError(
            f"No department named {raw!r}. Available: {', '.join(names) or 'none yet'}."
        )
    return row.id, row.name


def _iso_dates(d: dict, *keys: str) -> dict:
    for key in keys:
        value = d.get(key)
        if isinstance(value, dt.date):
            d[key] = value.isoformat()
    return d


def make_tool_call(name: str, args: Any, result: dict) -> dict:
    """Response/ai_logs entry: {tool, args, result_summary}."""
    if not isinstance(args, dict):
        args = {} if args is None else {"value": str(args)}
    summary = json.dumps(result, default=str, ensure_ascii=False)
    if len(summary) > 1500:
        summary = summary[:1500] + "..."
    return {"tool": name, "args": args, "result_summary": summary}


# --------------------------------------------------------------------------- args models
class _BaseArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")


class HeadcountArgs(_BaseArgs):
    department: str | None = Field(default=None, description="Department name or id")
    date: str | None = Field(default=None, description="YYYY-MM-DD (default: today)")


class AttendanceArgs(_BaseArgs):
    date_from: str | None = Field(default=None, description="YYYY-MM-DD (default: today)")
    date_to: str | None = Field(default=None, description="YYYY-MM-DD (default: today)")
    department_id: int | None = Field(default=None, description="Department id filter (staff only)")


class LateComersArgs(_BaseArgs):
    date_from: str | None = Field(default=None, description="YYYY-MM-DD (default: today)")
    date_to: str | None = Field(default=None, description="YYYY-MM-DD (default: today)")
    limit: int = Field(default=5, ge=1, le=20, description="Max rows (1-20)")


class LeaveSummaryArgs(_BaseArgs):
    date_from: str | None = Field(default=None, description="YYYY-MM-DD (default: today)")
    date_to: str | None = Field(default=None, description="YYYY-MM-DD (default: today)")


class BalanceArgs(_BaseArgs):
    year: int | None = Field(default=None, ge=2000, le=2100)


class PayrollArgs(_BaseArgs):
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    department_id: int | None = None


class SearchArgs(_BaseArgs):
    q: str = Field(min_length=1, max_length=100, description="Name, code or email fragment")


# --------------------------------------------------------------------------- executors
def _headcount(user: User, db: Session, args: HeadcountArgs) -> dict:
    today = company_today(db, user.company_id)
    day = _parse_date(args.date, "date", today)
    if not _is_staff(user):
        return _refusal(
            "Company headcount is HR and Admin information - your own dashboard "
            "shows your own records."
        )
    dept_id = None
    dept_name = None
    if args.department:
        dept_id, dept_name = _resolve_department(db, user.company_id, args.department)
    # Same formula as the dashboards (§5c): active on the end date.
    summary = analytics.hr_summary(db, user.company_id, day, day, dept_id)
    return {
        "headcount": summary["headcount"],
        "date": day.isoformat(),
        "department": dept_name,
        "department_id": dept_id,
    }


def _attendance_summary(user: User, db: Session, args: AttendanceArgs) -> dict:
    today = company_today(db, user.company_id)
    start, end = _parse_range(args.date_from, args.date_to, today)
    if not _is_staff(user):
        emp = _own_employee(db, user)
        if emp is None:
            return _refusal("Your login has no employee profile, so there is no attendance to show.")
        result = attendance_service.summary_for_employee(db, user.company_id, emp.id, start, end)
        return _iso_dates(result, "date_from", "date_to") | {"scope": "self"}
    result = analytics.hr_summary(db, user.company_id, start, end, args.department_id)
    return {
        "scope": "department" if args.department_id else "company",
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "headcount": result["headcount"],
        "present": result["present"],
        "late": result["late"],
        "on_leave": result["on_leave"],
        "half_day": result["half_day"],
        "attendance_rate": result["attendance_rate"],
        "late_pct": result["late_pct"],
    }


def _late_comers(user: User, db: Session, args: LateComersArgs) -> dict:
    today = company_today(db, user.company_id)
    start, end = _parse_range(args.date_from, args.date_to, today)
    if not _is_staff(user):
        emp = _own_employee(db, user)
        if emp is None:
            return _refusal("Your login has no employee profile, so there is no attendance to show.")
        own = attendance_service.summary_for_employee(db, user.company_id, emp.id, start, end)
        return {
            "scope": "self",
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "late_count": own["late"],
            "note": "Employees can only see their own attendance.",
        }
    summary = analytics.hr_summary(db, user.company_id, start, end, None)
    return {
        "scope": "company",
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "late_comers": summary["top_late_comers"][: args.limit],
    }


def _leave_summary(user: User, db: Session, args: LeaveSummaryArgs) -> dict:
    today = company_today(db, user.company_id)
    start, end = _parse_range(args.date_from, args.date_to, today)
    employee_id = None if _is_staff(user) else user.employee_id
    if not _is_staff(user) and employee_id is None:
        return _refusal("Your login has no employee profile, so there is no leave to show.")
    page = leave_service.list_requests(
        db, user.company_id, employee_id=employee_id, status=None, page=1, page_size=100
    )
    items = [
        {
            "employee_name": row["employee_name"],
            "employee_code": row["employee_code"],
            "leave_type_code": row["leave_type_code"],
            "start_date": row["start_date"].isoformat(),
            "end_date": row["end_date"].isoformat(),
            "working_days": row["working_days"],
            "status": row["status"],
        }
        for row in page["items"]
        if row["end_date"] >= start and row["start_date"] <= end
    ]
    return {
        "scope": "self" if employee_id is not None else "company",
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "count": len(items),
        "requests": items,
        "note": None if employee_id is not None else "Employees only see their own requests.",
    }


def _my_leave_balance(user: User, db: Session, args: BalanceArgs) -> dict:
    year = args.year or company_today(db, user.company_id).year
    if user.employee_id is None:
        return {
            "year": year,
            "items": [],
            "note": "This login has no employee profile, so it has no leave balance.",
        }
    balance = leave_service.get_balance(db, user.company_id, user.employee_id, year)
    return {"scope": "self", "year": balance["year"], "items": balance["items"]}


def _payroll_summary(user: User, db: Session, args: PayrollArgs) -> dict:
    if not _is_staff(user):
        return _refusal(
            "Payroll numbers are handled by HR and Admin only - I can't share them. "
            "Your own payslips are on the Payslips page."
        )
    today = company_today(db, user.company_id)
    year = args.year or today.year
    q = db.query(PayrollRun).filter(
        PayrollRun.company_id == user.company_id, PayrollRun.period_year == year
    )
    if args.month is not None:
        q = q.filter(PayrollRun.period_month == args.month)
    runs = q.order_by(PayrollRun.period_month.asc()).all()
    if not runs:
        return {"year": year, "month": args.month, "runs": [], "totals": None,
                "note": "No payroll run for that period yet."}

    dept_name = None
    if args.department_id is not None:
        _, dept_name = _resolve_department(db, user.company_id, args.department_id)

    rows = (
        db.query(PayrollItem, Employee)
        .join(Employee, PayrollItem.employee_id == Employee.id)
        .filter(
            PayrollItem.company_id == user.company_id,
            PayrollItem.run_id.in_([r.id for r in runs]),
        )
        .all()
    )
    if args.department_id is not None:
        rows = [(i, e) for i, e in rows if e.department_id == args.department_id]

    gross = round(sum(float(i.gross or 0) for i, _ in rows), 2)
    net = round(sum(float(i.net_pay or 0) for i, _ in rows), 2)
    deductions = round(sum(float(i.deduction_amount or 0) for i, _ in rows), 2)
    return {
        "scope": "company" if dept_name is None else "department",
        "year": year,
        "month": args.month,
        "department": dept_name,
        "employee_count": len(rows),
        "runs": [
            {
                "period": f"{r.period_year}-{r.period_month:02d}",
                "status": r.status,
                "total_gross": float(r.total_gross or 0),
                "total_deductions": float(r.total_deductions or 0),
                "total_net": float(r.total_net or 0),
            }
            for r in runs
        ],
        "totals": {"gross": gross, "net": net, "deductions": deductions},
        "note": "Aggregate only - individual pay slips stay on the Payslips page.",
    }


def _search(user: User, db: Session, args: SearchArgs) -> dict:
    result = employee_service.search_employees(
        db, user.company_id, q=args.q, page=1, page_size=10
    )
    items = result["items"]
    if not _is_staff(user):
        # Employees: ONLY their own row, and never salary/login internals.
        items = [i for i in items if i.get("id") == user.employee_id]
        keep = ("id", "employee_code", "first_name", "last_name", "full_name",
                "department", "designation", "joining_date", "employment_status")
        items = [{k: i.get(k) for k in keep} for i in items]
        note = "Employees can only look up their own directory record."
    else:
        note = None
    return {"query": args.q, "total": len(items), "items": items, "note": note}


# --------------------------------------------------------------------------- registry
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    executor: Callable[[User, Session, BaseModel], dict]

    def schema(self) -> dict:
        params = self.args_model.model_json_schema()
        params.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
        }


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "get_headcount",
            "Count active employees for a date, optionally filtered by department. "
            "Staff (HR/Admin) only; employees get a polite refusal.",
            HeadcountArgs,
            _headcount,
        ),
        Tool(
            "get_attendance_summary",
            "Attendance KPIs (present/late/on leave/half day, attendance rate) over a "
            "date range. Staff get company/department aggregates; employees get their "
            "own records.",
            AttendanceArgs,
            _attendance_summary,
        ),
        Tool(
            "get_late_comers",
            "Rank employees by late arrivals over a date range (staff scope). "
            "Employees receive only their own late count.",
            LateComersArgs,
            _late_comers,
        ),
        Tool(
            "get_leave_summary",
            "List leave requests overlapping a date range (staff: company-wide, "
            "employees: their own).",
            LeaveSummaryArgs,
            _leave_summary,
        ),
        Tool(
            "get_my_leave_balance",
            "The caller's own leave balance (quota, used, pending, remaining) for a year.",
            BalanceArgs,
            _my_leave_balance,
        ),
        Tool(
            "get_payroll_summary",
            "Aggregate payroll totals for a year/month/department. HR and Admin only - "
            "employees are refused; never returns individual pay.",
            PayrollArgs,
            _payroll_summary,
        ),
        Tool(
            "search_employees",
            "Search the employee directory by name, code or email. Employees only ever "
            "receive their own row.",
            SearchArgs,
            _search,
        ),
    )
}


def tool_schemas() -> list[dict]:
    return [tool.schema() for tool in TOOLS.values()]


def validate_args(name: str, args: Any) -> BaseModel:
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(
            f"Unknown tool {name!r}. Available tools: {', '.join(sorted(TOOLS))}."
        )
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ToolError(f"Arguments for {name} must be an object.")
    try:
        return tool.args_model.model_validate(args)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'arguments'}: {err['msg']}"
            for err in exc.errors()
        )
        raise ToolError(f"Invalid arguments for {name} ({problems}).") from exc


def execute_tool(name: str, user: User, db: Session, args: Any) -> dict:
    """Validate + run one tool with the caller's scope. Raises ToolError with a
    friendly message on bad input; never writes to the database."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"Unknown tool {name!r}.")
    parsed = validate_args(name, args)
    return tool.executor(user, db, parsed)


def run_tool(name: str, user: User, db: Session, args: Any) -> tuple[dict, dict]:
    """Execute and build the {tool, args, result_summary} entry.

    ANY failure (bad args, unexpected exception) becomes a friendly error dict —
    the chat endpoint must never 500 because a tool failed.
    """
    args_dict = args if isinstance(args, dict) else ({} if args is None else {"value": str(args)})
    try:
        result = execute_tool(name, user, db, args)
    except ToolError as exc:
        result = {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - defence in depth, never 500 the demo
        result = {"error": f"{name} failed unexpectedly: {exc}"}
    return result, make_tool_call(name, args_dict, result)
