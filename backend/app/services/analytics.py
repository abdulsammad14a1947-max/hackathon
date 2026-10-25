"""Dashboards / analytics (M7) — every number computed from the DB, empty-safe.

Frozen signatures (ARCHITECTURE §5b):
    admin_summary(db, company_id, date_from, date_to, department_id=None) -> dict
    hr_summary(db, company_id, date_from, date_to, department_id=None) -> dict
    employee_summary(db, company_id, employee_id) -> dict

Metric formulas follow ARCHITECTURE §5c (brief Section 7):
    headcount        = active employees on the end date (joining <= end, no exit before it)
    attrition_ytd    = employees terminated in the calendar year (+ % of avg headcount)
    payroll_cost     = Σ net_pay of finalized runs overlapping the range
                       (fallback: Σ gross of the latest finalized run)
    avg_salary       = mean gross (1.5 × basic) of active employees
    attendance_rate  = (present + late + missing_checkout + 0.5×half_day)
                       ÷ (working-day records − on_leave)
    late_pct         = late ÷ (present + late)
    absenteeism      = absent days ÷ expected working days, per department
    leave_utilization= approved days ÷ yearly quota (annual, because quotas are yearly)

All queries are company-scoped (multi-tenant) and return zeros/empty lists when a
company has no data yet.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import (
    Announcement,
    Attendance,
    AttendanceCorrection,
    AuditLog,
    Employee,
    LeaveRequest,
    LeaveType,
    PayrollItem,
    PayrollRun,
)
from app.services.calendar_utils import (
    get_settings,
    holiday_map,
    is_working_day,
    iter_days,
    month_date_range,
)

# attendance statuses that count as "worked / not absent"
ATTENDED_STATUSES = ("present", "late", "missing_checkout", "half_day", "on_leave")


# ----------------------------------------------------------------- small helpers
def _f(value) -> float:
    return float(value) if value is not None else 0.0


def _employees(
    db: Session, company_id: int, department_id: int | None = None
) -> list[Employee]:
    q = db.query(Employee).filter(Employee.company_id == company_id)
    if department_id is not None:
        q = q.filter(Employee.department_id == department_id)
    return q.all()


def _active_on(emps: list[Employee], on_date: dt.date) -> list[Employee]:
    """Employees employed on `on_date` (headcount rule §5c: active on end date)."""
    out = []
    for e in emps:
        if e.joining_date is None or e.joining_date > on_date:
            continue
        if e.termination_date is not None and e.termination_date < on_date:
            continue
        if e.employment_status == "inactive" and e.termination_date is None:
            continue
        out.append(e)
    return out


def _dept_name(emp: Employee) -> str:
    return emp.department.name if emp.department is not None else "Unassigned"


def _today(db: Session, company_id: int) -> dt.date:
    """Today in the company timezone (fallback: system date if tz db missing)."""
    try:
        from zoneinfo import ZoneInfo

        settings = get_settings(db, company_id)
        tz = ZoneInfo(settings.timezone or "Asia/Karachi")
        return dt.datetime.now(tz).date()
    except Exception:  # zoneinfo/tzdata unavailable on some Windows installs
        return dt.date.today()


def _working_days_between(
    db: Session, company_id: int, start: dt.date, end: dt.date
) -> list[dt.date]:
    if end < start:
        return []
    settings = get_settings(db, company_id)
    holidays = holiday_map(db, company_id)
    return [d for d in iter_days(start, end) if is_working_day(d, settings, holidays)]


def _approved_leave_dates(
    db: Session, company_id: int, start: dt.date, end: dt.date
) -> dict[int, set[dt.date]]:
    """employee_id -> working dates covered by APPROVED leave in [start, end]."""
    rows = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.company_id == company_id,
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        )
        .all()
    )
    if not rows:
        return {}
    settings = get_settings(db, company_id)
    holidays = holiday_map(db, company_id)
    out: dict[int, set[dt.date]] = {}
    for req in rows:
        dates = out.setdefault(req.employee_id, set())
        lo = max(req.start_date, start)
        hi = min(req.end_date, end)
        for d in iter_days(lo, hi):
            if is_working_day(d, settings, holidays):
                dates.add(d)
    return out


# ----------------------------------------------------------------- admin summary
def _finalized_runs_in_range(
    db: Session, company_id: int, date_from: dt.date, date_to: dt.date
) -> list[PayrollRun]:
    runs = (
        db.query(PayrollRun)
        .filter(PayrollRun.company_id == company_id, PayrollRun.status == "finalized")
        .all()
    )
    in_range = []
    for run in runs:
        ms, me = month_date_range(run.period_year, run.period_month)
        if ms <= date_to and me >= date_from:
            in_range.append(run)
    in_range.sort(key=lambda r: (r.period_year, r.period_month), reverse=True)
    return in_range


def _payroll_sums(
    db: Session, company_id: int, runs: list[PayrollRun], department_id: int | None = None
) -> dict:
    if not runs:
        return {"net": 0.0, "gross": 0.0, "by_department": []}
    q = (
        db.query(PayrollItem, Employee)
        .join(Employee, PayrollItem.employee_id == Employee.id)
        .filter(
            PayrollItem.company_id == company_id,
            PayrollItem.run_id.in_([r.id for r in runs]),
        )
    )
    if department_id is not None:
        q = q.filter(Employee.department_id == department_id)
    rows = q.all()
    net = sum(_f(item.net_pay) for item, _ in rows)
    gross = sum(_f(item.gross) for item, _ in rows)
    per_dept: dict[str, dict[str, float]] = {}
    for item, emp in rows:
        bucket = per_dept.setdefault(_dept_name(emp), {"gross": 0.0, "net": 0.0})
        bucket["gross"] += _f(item.gross)
        bucket["net"] += _f(item.net_pay)
    by_department = [
        {"department": name, "gross": round(v["gross"], 2), "net": round(v["net"], 2)}
        for name, v in sorted(per_dept.items(), key=lambda kv: kv[0])
    ]
    return {"net": round(net, 2), "gross": round(gross, 2), "by_department": by_department}


def admin_summary(
    db: Session,
    company_id: int,
    date_from: dt.date,
    date_to: dt.date,
    department_id: int | None = None,
) -> dict:
    """Admin KPI dashboard (Admin role only — enforced at the API layer)."""
    emps = _employees(db, company_id, department_id)
    active = _active_on(emps, date_to)

    # --- headcount / attrition ------------------------------------------------
    active_headcount = len(active)
    target_year = date_to.year
    exits = [
        e
        for e in emps
        if e.termination_date is not None and e.termination_date.year == target_year
    ]
    year_start = dt.date(target_year, 1, 1)
    hc_start = len(_active_on(emps, year_start))
    avg_headcount = (hc_start + active_headcount) / 2
    attrition_pct = round((len(exits) / avg_headcount) * 100, 1) if avg_headcount else 0.0

    # --- payroll cost ---------------------------------------------------------
    runs = _finalized_runs_in_range(db, company_id, date_from, date_to)
    basis = "finalized_runs_in_range"
    if not runs:
        all_final = (
            db.query(PayrollRun)
            .filter(
                PayrollRun.company_id == company_id, PayrollRun.status == "finalized"
            )
            .order_by(
                PayrollRun.period_year.desc(), PayrollRun.period_month.desc()
            )
            .first()
        )
        if all_final is not None:
            runs = [all_final]
            basis = "latest_finalized_run_gross"
    sums = _payroll_sums(db, company_id, runs, department_id)
    payroll_cost = sums["gross"] if basis == "latest_finalized_run_gross" else sums["net"]

    # --- salaries -------------------------------------------------------------
    if active:
        avg_salary = round(sum(1.5 * _f(e.basic_salary) for e in active) / len(active), 2)
        avg_basic = round(sum(_f(e.basic_salary) for e in active) / len(active), 2)
        tenure_months = [
            (date_to - e.joining_date).days / 30.44 for e in active if e.joining_date
        ]
        tenure_avg = round(sum(tenure_months) / len(tenure_months), 1) if tenure_months else 0.0
    else:
        avg_salary = avg_basic = tenure_avg = 0.0

    # --- breakdowns -----------------------------------------------------------
    dept_counts: dict[str, int] = {}
    gender: dict[str, int] = {"male": 0, "female": 0, "other": 0, "unspecified": 0}
    for e in active:
        dept_counts[_dept_name(e)] = dept_counts.get(_dept_name(e), 0) + 1
        key = e.gender if e.gender in gender else "unspecified"
        gender[key] += 1
    headcount_by_department = [
        {"department": name, "count": count}
        for name, count in sorted(dept_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    # --- recent audit (last 8) ------------------------------------------------
    audit_rows = (
        db.query(AuditLog)
        .filter(AuditLog.company_id == company_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(8)
        .all()
    )
    recent_audit = [
        {
            "actor": row.actor_email,
            "action": row.action,
            "entity": row.entity_type,
            "entity_id": row.entity_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in audit_rows
    ]

    return {
        "active_headcount": active_headcount,
        "attrition_ytd": len(exits),
        "attrition_pct": attrition_pct,
        "payroll_cost": float(payroll_cost),
        "payroll_basis": basis if runs else "none",
        "avg_salary": avg_salary,
        "avg_basic_salary": avg_basic,
        "headcount_by_department": headcount_by_department,
        "payroll_cost_by_department": sums["by_department"],
        "gender_breakdown": gender,
        "tenure_months_avg": tenure_avg,
        "recent_audit": recent_audit,
    }


# ----------------------------------------------------------------- HR summary
def hr_summary(
    db: Session,
    company_id: int,
    date_from: dt.date,
    date_to: dt.date,
    department_id: int | None = None,
) -> dict:
    """HR KPI dashboard (HR + Admin)."""
    if date_to < date_from:
        date_from, date_to = date_to, date_from
    emps = _employees(db, company_id, department_id)
    active = _active_on(emps, date_to)

    # --- headline counts on `date_from` (defaults to today at the API layer) ---
    day_rows = (
        db.query(Attendance)
        .filter(Attendance.company_id == company_id, Attendance.date == date_from)
        .all()
    )
    emp_by_id = {e.id: e for e in emps}
    if department_id is not None:
        day_rows = [
            r for r in day_rows if r.employee_id in emp_by_id
        ]
    present = sum(1 for r in day_rows if r.status in ("present", "missing_checkout"))
    late = sum(1 for r in day_rows if r.status == "late")
    on_leave = sum(1 for r in day_rows if r.status == "on_leave")
    half_day = sum(1 for r in day_rows if r.status == "half_day")

    # --- pending approvals ----------------------------------------------------
    leave_q = db.query(LeaveRequest).filter(
        LeaveRequest.company_id == company_id, LeaveRequest.status == "pending"
    )
    corr_q = db.query(AttendanceCorrection).filter(
        AttendanceCorrection.company_id == company_id,
        AttendanceCorrection.status == "pending",
    )
    if department_id is not None:
        leave_q = leave_q.filter(LeaveRequest.employee_id.in_([e.id for e in emps]))
        corr_q = corr_q.filter(
            AttendanceCorrection.employee_id.in_([e.id for e in emps])
        )
    pending_leave = leave_q.count()
    pending_corr = corr_q.count()

    # --- range attendance aggregates (§5c formulas) ---------------------------
    range_rows = (
        db.query(Attendance)
        .filter(
            Attendance.company_id == company_id,
            Attendance.date >= date_from,
            Attendance.date <= date_to,
        )
        .all()
    )
    if department_id is not None:
        range_rows = [r for r in range_rows if r.employee_id in emp_by_id]
    working_records = [
        r for r in range_rows if r.status not in ("weekend", "holiday")
    ]
    denom = len(working_records) - on_leave_count(working_records)
    numer = sum(
        1
        for r in working_records
        if r.status in ("present", "late", "missing_checkout")
    ) + 0.5 * sum(1 for r in working_records if r.status == "half_day")
    attendance_rate = round(numer / denom, 3) if denom > 0 else 0.0
    present_agg = sum(
        1 for r in working_records if r.status in ("present", "missing_checkout")
    )
    late_agg = sum(1 for r in working_records if r.status == "late")
    late_pct = round(late_agg / (present_agg + late_agg), 3) if (present_agg + late_agg) else 0.0

    # --- attendance trend (last 14 days when no explicit range, else the range) -
    trend_start = date_to - dt.timedelta(days=13) if date_from == date_to else date_from
    trend = _attendance_trend(db, company_id, trend_start, date_to, emps)

    # --- absenteeism by department (§5c) --------------------------------------
    absenteeism = _absenteeism_by_department(db, company_id, date_from, date_to, emps)

    # --- leave utilization (calendar year of `to`, quotas are yearly) ----------
    leave_utilization = _leave_utilization(db, company_id, date_to.year, emps)

    # --- top late comers in range --------------------------------------------
    top_late = _top_late_comers(db, company_id, date_from, date_to, emps)

    insights = _build_insights(
        db,
        company_id,
        date_from=date_from,
        date_to=date_to,
        present=present,
        late=late,
        on_leave=on_leave,
        pending_leave=pending_leave,
        pending_corr=pending_corr,
        headcount=len(active),
        attendance_rate=attendance_rate,
        absenteeism=absenteeism,
        leave_utilization=leave_utilization,
        trend=trend,
        emp_ids={e.id for e in emps},
    )

    return {
        "headcount": len(active),
        "present": present,
        "late": late,
        "on_leave": on_leave,
        "half_day": half_day,
        "attendance_rate": attendance_rate,
        "late_pct": late_pct,
        "pending_approvals": {
            "leave_requests": pending_leave,
            "corrections": pending_corr,
        },
        "attendance_trend": trend,
        "absenteeism_by_department": absenteeism,
        "leave_utilization": leave_utilization,
        "top_late_comers": top_late,
        "insights": insights,
    }


def on_leave_count(rows: list[Attendance]) -> int:
    return sum(1 for r in rows if r.status == "on_leave")


def _attendance_trend(
    db: Session,
    company_id: int,
    start: dt.date,
    end: dt.date,
    emps: list[Employee],
) -> list[dict]:
    """[{date, present, late, absent}] per calendar day; non-working days are zeros."""
    if (end - start).days > 92:
        start = end - dt.timedelta(days=92)
    settings = get_settings(db, company_id)
    holidays = holiday_map(db, company_id)
    emp_ids = {e.id for e in emps}
    rows = (
        db.query(Attendance)
        .filter(
            Attendance.company_id == company_id,
            Attendance.date >= start,
            Attendance.date <= end,
        )
        .all()
    )
    if emp_ids:
        rows = [r for r in rows if r.employee_id in emp_ids]
    else:
        rows = []  # department filter matched no employees
    by_day: dict[dt.date, list[Attendance]] = {}
    for r in rows:
        by_day.setdefault(r.date, []).append(r)

    trend: list[dict] = []
    for day in iter_days(start, end):
        if not is_working_day(day, settings, holidays):
            trend.append({"date": day.isoformat(), "present": 0, "late": 0, "absent": 0})
            continue
        day_rows = by_day.get(day, [])
        present = sum(
            1 for r in day_rows if r.status in ("present", "missing_checkout", "half_day")
        )
        late = sum(1 for r in day_rows if r.status == "late")
        expected = len(_active_on(emps, day))
        not_absent = sum(1 for r in day_rows if r.status in ATTENDED_STATUSES)
        absent = max(0, expected - not_absent)
        trend.append(
            {"date": day.isoformat(), "present": present, "late": late, "absent": absent}
        )
    return trend


def _absenteeism_by_department(
    db: Session,
    company_id: int,
    date_from: dt.date,
    date_to: dt.date,
    emps: list[Employee],
) -> list[dict]:
    """absent days ÷ expected working days, per department (§5c)."""
    days = _working_days_between(db, company_id, date_from, date_to)
    if not days or not emps:
        return []
    att = (
        db.query(Attendance)
        .filter(
            Attendance.company_id == company_id,
            Attendance.date >= date_from,
            Attendance.date <= date_to,
        )
        .all()
    )
    att_status: dict[tuple[int, dt.date], str] = {
        (r.employee_id, r.date): r.status for r in att
    }
    leave_days = _approved_leave_dates(db, company_id, date_from, date_to)

    buckets: dict[str, dict[str, float]] = {}
    for emp in emps:
        dept = _dept_name(emp)
        bucket = buckets.setdefault(dept, {"absent": 0.0, "expected": 0.0})
        emp_leave = leave_days.get(emp.id, set())
        for day in days:
            if emp.joining_date and emp.joining_date > day:
                continue
            if emp.termination_date and emp.termination_date < day:
                continue
            if emp.employment_status == "inactive" and emp.termination_date is None:
                continue
            bucket["expected"] += 1
            if day in emp_leave:
                continue
            status = att_status.get((emp.id, day))
            if status is None or status == "absent":
                bucket["absent"] += 1
    out = []
    for name, v in buckets.items():
        rate = round(v["absent"] / v["expected"], 3) if v["expected"] else 0.0
        out.append(
            {
                "department": name,
                "absent_days": float(v["absent"]),
                "expected_days": float(v["expected"]),
                "rate": rate,
            }
        )
    out.sort(key=lambda row: (-row["rate"], row["department"]))
    return out


def _leave_utilization(
    db: Session, company_id: int, year: int, emps: list[Employee]
) -> list[dict]:
    """Approved days this year ÷ yearly quota, per leave type (annual = quota unit)."""
    types = (
        db.query(LeaveType)
        .filter(LeaveType.company_id == company_id)
        .order_by(LeaveType.code.asc())
        .all()
    )
    used: dict[int, float] = {}
    pending: dict[int, float] = {}
    emp_ids = {e.id for e in emps}
    if emp_ids:
        start = dt.date(year, 1, 1)
        end = dt.date(year, 12, 31)
        q = db.query(LeaveRequest).filter(
            LeaveRequest.company_id == company_id,
            LeaveRequest.start_date >= start,
            LeaveRequest.start_date <= end,
            LeaveRequest.employee_id.in_(emp_ids),
        )
        for req in q.all():
            if req.status in ("approved", "pending"):
                bucket = used if req.status == "approved" else pending
                bucket[req.leave_type_id] = bucket.get(req.leave_type_id, 0.0) + _f(
                    req.working_days
                )
    out = []
    for t in types:
        used_days = round(used.get(t.id, 0.0), 2)
        quota = t.yearly_quota
        util = round(used_days / quota, 3) if quota else None
        out.append(
            {"leave_type": t.name, "used": used_days, "quota": quota, "utilization": util}
        )
    return out


def _top_late_comers(
    db: Session,
    company_id: int,
    date_from: dt.date,
    date_to: dt.date,
    emps: list[Employee],
    limit: int = 5,
) -> list[dict]:
    rows = (
        db.query(Attendance)
        .filter(
            Attendance.company_id == company_id,
            Attendance.date >= date_from,
            Attendance.date <= date_to,
            Attendance.status == "late",
        )
        .all()
    )
    counts: dict[int, int] = {}
    for r in rows:
        counts[r.employee_id] = counts.get(r.employee_id, 0) + 1
    emp_by_id = {e.id: e for e in emps}
    out = []
    for emp_id, count in counts.items():
        emp = emp_by_id.get(emp_id)
        if emp is None:
            continue
        out.append(
            {
                "employee_id": emp.id,
                "employee_code": emp.employee_code,
                "employee_name": f"{emp.first_name} {emp.last_name or ''}".strip(),
                "department": _dept_name(emp),
                "late_count": count,
            }
        )
    out.sort(key=lambda row: (-row["late_count"], row["employee_name"]))
    return out[:limit]


def _build_insights(
    db: Session,
    company_id: int,
    *,
    date_from: dt.date,
    date_to: dt.date,
    present: int,
    late: int,
    on_leave: int,
    pending_leave: int,
    pending_corr: int,
    headcount: int,
    attendance_rate: float,
    absenteeism: list[dict],
    leave_utilization: list[dict],
    trend: list[dict],
    emp_ids: set[int] | None = None,
) -> list[str]:
    """3–5 short strings derived strictly from the computed numbers."""
    insights: list[str] = []

    # 1) late arrivals vs the same weekday one week earlier (dept-scoped)
    ref_day = date_from - dt.timedelta(days=7)
    ref_rows = [
        r
        for r in db.query(Attendance)
        .filter(
            Attendance.company_id == company_id,
            Attendance.date == ref_day,
            Attendance.status == "late",
        )
        .all()
        if emp_ids is None or r.employee_id in emp_ids
    ]
    ref_count = len(ref_rows)
    if ref_count > 0:
        pct = ((late - ref_count) / ref_count) * 100
        direction = "up" if pct > 0 else ("down" if pct < 0 else "flat")
        insights.append(
            f"Late arrivals {direction} {abs(pct):.0f}% vs same day last week "
            f"({late} vs {ref_count})."
        )
    elif late > 0:
        insights.append(
            f"{late} late arrival(s) on {date_from.isoformat()} vs none on the same day last week."
        )

    # 2) attendance week over week (from the trend we just computed)
    if len(trend) >= 14:
        recent = trend[-7:]
        previous = trend[-14:-7]
        r_present = sum(d["present"] for d in recent)
        p_present = sum(d["present"] for d in previous)
        if p_present > 0:
            pct = ((r_present - p_present) / p_present) * 100
            direction = "up" if pct > 0 else ("down" if pct < 0 else "steady")
            if direction == "steady":
                insights.append("Average daily attendance is steady vs the previous week.")
            else:
                insights.append(
                    f"Attendance {direction} {abs(pct):.0f}% vs previous week "
                    f"({r_present} vs {p_present} present-days)."
                )
        else:
            insights.append(f"{r_present} present-day(s) recorded in the last 7 days.")
    elif trend:
        total_present = sum(d["present"] for d in trend)
        insights.append(f"{total_present} present-day(s) recorded in the selected range.")

    # 3) pending approvals
    if pending_leave or pending_corr:
        insights.append(
            f"{pending_leave} leave request(s) and {pending_corr} attendance correction(s) "
            "await approval."
        )
    else:
        insights.append("No pending approvals.")

    # 4) highest absenteeism department in range
    if absenteeism and absenteeism[0]["absent_days"] > 0:
        top = absenteeism[0]
        insights.append(
            f"{top['department']} recorded the most absent days "
            f"({top['absent_days']:g} of {top['expected_days']:g} expected)."
        )

    # 5) leave usage vs quota
    quota_total = sum(row["quota"] for row in leave_utilization if row["quota"])
    used_total = sum(row["used"] for row in leave_utilization)
    if quota_total:
        insights.append(
            f"Employees used {used_total:g} of {quota_total:g} allocated leave days this year."
        )

    if not insights:
        insights.append("No activity recorded for the selected range.")
    if headcount == 0 and "No active employees yet." not in insights:
        insights.insert(0, "No active employees yet.")
    return insights[:5]


# ----------------------------------------------------------------- employee summary
def _empty_employee_summary() -> dict:
    return {
        "today_status": "not_checked_in",
        "week_hours": 0.0,
        "week_hours_target": 40.0,
        "late_count_this_month": 0,
        "leave_balances": [],
        "recent_attendance": [],
        "last_payslip": None,
        "announcement_count": 0,
    }


def employee_summary(db: Session, company_id: int, employee_id: int | None) -> dict:
    """Personal dashboard for the logged-in user's own employee profile."""
    if employee_id is None:
        return _empty_employee_summary()
    emp = db.get(Employee, employee_id)
    if emp is None or emp.company_id != company_id:
        return _empty_employee_summary()

    today = _today(db, company_id)

    # --- today status ---------------------------------------------------------
    row = (
        db.query(Attendance)
        .filter(Attendance.employee_id == employee_id, Attendance.date == today)
        .first()
    )
    if row is not None:
        today_status = row.status
    else:
        settings = get_settings(db, company_id)
        holidays = holiday_map(db, company_id)
        if today in holidays:
            today_status = "holiday"
        elif not is_working_day(today, settings, holidays):
            today_status = "weekend"
        else:
            leave_today = _approved_leave_dates(db, company_id, today, today)
            if employee_id in leave_today:
                today_status = "on_leave"
            elif today < dt.date.today():
                today_status = "absent"  # a past working day with no record
            else:
                today_status = "not_checked_in"

    # --- week hours (Mon .. today) -------------------------------------------
    monday = today - dt.timedelta(days=today.weekday())
    week_rows = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date >= monday,
            Attendance.date <= today,
        )
        .all()
    )
    week_hours = round(sum(_f(r.worked_hours) for r in week_rows), 2)

    # --- late count this month ------------------------------------------------
    month_start = today.replace(day=1)
    late_count = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date >= month_start,
            Attendance.date <= today,
            Attendance.status == "late",
        )
        .count()
    )

    # --- leave balances (quota vs approved this year) -------------------------
    year = today.year
    year_start = dt.date(year, 1, 1)
    year_end = dt.date(year, 12, 31)
    types = (
        db.query(LeaveType)
        .filter(LeaveType.company_id == company_id)
        .order_by(LeaveType.code.asc())
        .all()
    )
    reqs = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.start_date >= year_start,
            LeaveRequest.start_date <= year_end,
        )
        .all()
    )
    leave_balances = []
    for t in types:
        used = sum(
            _f(r.working_days)
            for r in reqs
            if r.leave_type_id == t.id and r.status == "approved"
        )
        pending = sum(
            _f(r.working_days)
            for r in reqs
            if r.leave_type_id == t.id and r.status == "pending"
        )
        remaining = None if t.yearly_quota is None else max(
            0.0, float(t.yearly_quota) - used
        )
        leave_balances.append(
            {
                "code": t.code,
                "name": t.name,
                "quota": t.yearly_quota,
                "used": round(used, 2),
                "pending": round(pending, 2),
                "remaining": None if remaining is None else round(remaining, 2),
                "is_paid": bool(t.is_paid),
            }
        )

    # --- recent attendance (last 7 days) --------------------------------------
    recent_rows = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee_id,
            Attendance.date >= today - dt.timedelta(days=6),
            Attendance.date <= today,
        )
        .order_by(Attendance.date.desc())
        .all()
    )
    recent_attendance = [
        {
            "date": r.date.isoformat(),
            "status": r.status,
            "check_in": r.check_in.isoformat() if r.check_in else None,
            "check_out": r.check_out.isoformat() if r.check_out else None,
            "worked_hours": _f(r.worked_hours),
        }
        for r in recent_rows
    ]

    # --- last finalized payslip ----------------------------------------------
    payslip = (
        db.query(PayrollItem, PayrollRun)
        .join(PayrollRun, PayrollItem.run_id == PayrollRun.id)
        .filter(
            PayrollItem.employee_id == employee_id,
            PayrollItem.company_id == company_id,
            PayrollRun.status == "finalized",
        )
        .order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())
        .first()
    )
    last_payslip = None
    if payslip is not None:
        item, run = payslip
        last_payslip = {
            "id": item.id,
            "period": f"{run.period_year}-{run.period_month:02d}",
            "net_pay": _f(item.net_pay),
        }

    announcement_count = (
        db.query(Announcement).filter(Announcement.company_id == company_id).count()
    )

    return {
        "today_status": today_status,
        "week_hours": week_hours,
        "week_hours_target": 40.0,
        "late_count_this_month": late_count,
        "leave_balances": leave_balances,
        "recent_attendance": recent_attendance,
        "last_payslip": last_payslip,
        "announcement_count": announcement_count,
    }
