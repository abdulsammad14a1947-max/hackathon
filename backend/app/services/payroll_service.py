"""Payroll Lite service — salary structures, draft generation, finalization.

FROZEN FORMULAS (ARCHITECTURE §5 / brief M6 — do not change):
    hra      = 40%  × basic
    medical  = 10%  × basic
    gross    = basic + hra + medical = 1.5 × basic          (contractual, full month)
    working_days = working_days_in_month(db, company, y, m)  (weekends + holidays excluded)
    per_day  = gross / working_days
    deduction_amount = (absent_days + unpaid_leave_days + 0.5 × half_days) × per_day
    annual_tax  = compute_annual_tax(gross × 12)            (illustrative slabs)
    monthly_tax = annual_tax / 12
    adjusted_gross = per_day × eligible_days                (employment overlap w/ month)
    net_pay   = adjusted_gross − deduction_amount − tax, clamped at 0

DOCUMENTED ASSUMPTIONS (per instruction "document assumptions in code comments"):
1. `PayrollItem.gross` stores the CONTRACTUAL full-month gross (1.5 × basic) so the
   earnings table (basic/hra/medical/gross) is stable; proration shows up as a
   smaller `net_pay` and is described in `note` ("Prorated X/Y working days ...").
   Run totals: total_gross = Σ gross (contractual), total_net = Σ net_pay,
   total_deductions = total_gross − total_net (proration + deductions + tax).
2. Tax follows the frozen rule literally: annualized = CONTRACTUAL gross × 12 even
   for mid-month joiners / leavers (documented; keeps the slab rule deterministic).
3. Absence is only counted for working days inside the employment overlap with the
   month: joiners start counting from `joining_date`, leavers stop at
   `termination_date`. Approved PAID leave is paid (never deducted); approved
   UNPAID leave deducts one day per working day; a `half_day` attendance row
   deducts 0.5 day; a day with no attendance row AND no approved leave (or an
   attendance row whose status is literally "absent") counts as absent.
   Approved leave takes precedence over attendance rows (no double counting);
   an `on_leave` row without an approved request deducts nothing (assumption:
   the attendance module only writes `on_leave` for approved leave).
4. `net_pay` is rounded to 2 dp and clamped at 0 (a note "net pay clamped to 0"
   is appended when the raw value would be negative).
5. An employee is included in a run when `joining_date <= month_end` AND
   (`employment_status == "active"` OR `termination_date >= month_start`).
   "inactive" employees without a termination date are excluded (no pay while on
   hold — documented assumption).
6. Regenerating a draft run for the same (company, year, month) replaces its items
   inside ONE transaction; a FINALIZED run for that period is immutable (409).
"""
from __future__ import annotations

import datetime as dt

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import (
    Attendance,
    Employee,
    LeaveRequest,
    LeaveType,
    PayrollItem,
    PayrollRun,
    SalaryStructure,
    User,
)
from app.services.calendar_utils import (
    get_settings,
    holiday_map,
    is_working_day,
    iter_days,
    month_date_range,
    working_days_in_month,
)
from app.services.notifications import notify_employee
from app.utils.audit import record_audit

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


# ----------------------------------------------------------------- pure helpers
def round2(value: float) -> float:
    """Round to 2 dp (money) — architecture rule: 2 dp at end of each computation."""
    return round(float(value) + 0.0, 2)


def compute_annual_tax(annualized: float) -> float:
    """Illustrative annualized-gross slabs (frozen — brief M6).

    <=600k -> 0
    600k..1.2M -> 5%  of (a - 600k)
    1.2M..2.4M -> 30k + 15% of (a - 1.2M)
    2.4M..3.6M -> 210k + 25% of (a - 2.4M)
    >3.6M       -> 510k + 35% of (a - 3.6M)
    """
    a = float(annualized)
    if a <= 600_000:
        return 0.0
    if a <= 1_200_000:
        return round2(0.05 * (a - 600_000))
    if a <= 2_400_000:
        return round2(30_000 + 0.15 * (a - 1_200_000))
    if a <= 3_600_000:
        return round2(210_000 + 0.25 * (a - 2_400_000))
    return round2(510_000 + 0.35 * (a - 3_600_000))


def monthly_tax_for_gross(gross: float) -> float:
    """slab(gross × 12) / 12 — frozen rule."""
    return round2(compute_annual_tax(float(gross) * 12) / 12)


def _f(value) -> float:
    """Coerce DB numerics (Decimal on SQLite) to float safely."""
    return float(value) if value is not None else 0.0


# ----------------------------------------------------------------- salary structure
def effective_basic_salary(
    db: Session, company_id: int, employee: Employee, year: int, month: int
) -> float:
    """Basic effective for the period: latest salary_structure covering the month,
    falling back to `employee.basic_salary` (current basic)."""
    month_start, month_end = month_date_range(year, month)
    rows = (
        db.query(SalaryStructure)
        .filter(
            SalaryStructure.company_id == company_id,
            SalaryStructure.employee_id == employee.id,
            SalaryStructure.effective_from <= month_end,
        )
        .all()
    )
    covering = [
        r
        for r in rows
        if r.effective_to is None or r.effective_to >= month_start
    ]
    if not covering:
        return _f(employee.basic_salary)
    covering.sort(key=lambda r: (r.effective_from, r.id), reverse=True)
    return _f(covering[0].basic_salary)


# ----------------------------------------------------------------- run generation
def get_run(db: Session, company_id: int, run_id: int) -> PayrollRun:
    run = db.get(PayrollRun, run_id)
    if run is None or run.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")
    return run


def ensure_run_not_finalized(run: PayrollRun) -> None:
    """IMMUTABILITY (enforced in service, not just UI): finalized runs are locked."""
    if run.status == "finalized":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payroll run is finalized and cannot be modified",
        )


def _employees_for_run(
    db: Session, company_id: int, year: int, month: int
) -> list[Employee]:
    month_start, month_end = month_date_range(year, month)
    rows = (
        db.query(Employee)
        .filter(Employee.company_id == company_id, Employee.joining_date <= month_end)
        .all()
    )
    included: list[Employee] = []
    for emp in rows:
        if emp.employment_status == "active":
            included.append(emp)
        elif emp.termination_date is not None and emp.termination_date >= month_start:
            # leaver paid for the overlap of employment with the month
            included.append(emp)
    return included


def _approved_leave_days(
    db: Session, employee_id: int, start: dt.date, end: dt.date
) -> tuple[set[dt.date], set[dt.date]]:
    """Working days covered by APPROVED leave inside [start, end].

    Returns (paid_dates, unpaid_dates) — weekends/holidays already excluded.
    """
    rows = (
        db.query(LeaveRequest, LeaveType)
        .join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id)
        .filter(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
        )
        .all()
    )
    if not rows:
        return set(), set()
    paid: set[dt.date] = set()
    unpaid: set[dt.date] = set()
    # NOTE: returns raw calendar dates; weekend/holiday filtering happens in
    # `_approved_leave_days_for_company` (working days only, per frozen rules).
    for req, ltype in rows:
        lo = max(req.start_date, start)
        hi = min(req.end_date, end)
        target = paid if ltype.is_paid else unpaid
        for d in iter_days(lo, hi):
            target.add(d)  # working-day filtering happens in the caller
    return paid, unpaid


def _approved_leave_days_for_company(
    db: Session, company_id: int, employee_id: int, start: dt.date, end: dt.date
) -> tuple[set[dt.date], set[dt.date]]:
    paid, unpaid = _approved_leave_days(db, employee_id, start, end)
    settings = get_settings(db, company_id)
    holidays = holiday_map(db, company_id)
    working_paid = {d for d in paid if is_working_day(d, settings, holidays)}
    working_unpaid = {d for d in unpaid if is_working_day(d, settings, holidays)}
    # A day approved both paid+unpaid (overlapping requests) counts as paid.
    return working_paid, working_unpaid - working_paid


def compute_employee_payslip(
    db: Session, company_id: int, employee: Employee, year: int, month: int
) -> dict:
    """Compute one employee's payroll line for (year, month). Pure arithmetic once
    the attendance/leave rows are read. Returns a dict of PayrollItem fields."""
    month_start, month_end = month_date_range(year, month)

    # --- employment overlap with the month (proration window) -------------------
    joining = employee.joining_date
    termination = (
        employee.termination_date
        if employee.employment_status != "active" and employee.termination_date
        else None
    )
    elig_start = max(joining, month_start)
    elig_end = min(termination, month_end) if termination else month_end
    if elig_end < elig_start:
        elig_end = elig_start  # degenerate; kept for safety

    # --- allowances (frozen formulas) ------------------------------------------
    basic = effective_basic_salary(db, company_id, employee, year, month)
    hra = round2(basic * 0.40)
    medical = round2(basic * 0.10)
    gross = round2(basic + hra + medical)  # == 1.5 × basic (within rounding)

    working_days = working_days_in_month(db, company_id, year, month)
    per_day = (gross / working_days) if working_days > 0 else 0.0

    # --- eligible working days + day-by-day classification ---------------------
    settings = get_settings(db, company_id)
    holidays = holiday_map(db, company_id)

    att_rows = (
        db.query(Attendance)
        .filter(
            Attendance.employee_id == employee.id,
            Attendance.date >= elig_start,
            Attendance.date <= elig_end,
        )
        .all()
    )
    att_by_date = {row.date: row.status for row in att_rows}

    paid_leave, unpaid_leave = _approved_leave_days_for_company(
        db, company_id, employee.id, elig_start, elig_end
    )

    eligible_days = 0
    present_days = 0.0
    absent_days = 0.0
    unpaid_leave_days = 0.0
    half_days = 0.0
    for day in iter_days(elig_start, elig_end):
        if not is_working_day(day, settings, holidays):
            continue
        eligible_days += 1
        if day in paid_leave:
            continue  # approved PAID leave is paid — never counted absent
        if day in unpaid_leave:
            unpaid_leave_days += 1
            continue
        row_status = att_by_date.get(day)
        if row_status is None:
            absent_days += 1  # no record, no approved leave -> absent (frozen rule)
        elif row_status == "half_day":
            half_days += 1
        elif row_status == "absent":
            absent_days += 1  # explicit absence row, no leave -> absent
        elif row_status == "on_leave":
            continue  # on_leave without approved request: no deduction (assumption #3)
        else:  # present | late | missing_checkout
            present_days += 1

    # --- deductions / proration / tax / net ------------------------------------
    deduction_amount = round2((absent_days + unpaid_leave_days + 0.5 * half_days) * per_day)
    adjusted_gross = round2(per_day * eligible_days)
    tax = monthly_tax_for_gross(gross)
    raw_net = adjusted_gross - deduction_amount - tax
    clamped = raw_net < 0
    net_pay = round2(max(0.0, raw_net))  # never negative — clamped at 0

    notes: list[str] = []
    if eligible_days != working_days:
        notes.append(
            f"Prorated {eligible_days:g}/{working_days:g} working days "
            f"(joined {joining.isoformat()}"
            + (f", terminated {termination.isoformat()}" if termination else "")
            + f"); adjusted_gross={adjusted_gross:.2f}"
        )
    if clamped:
        notes.append("net pay clamped to 0")

    return {
        "employee_id": employee.id,
        "basic": round2(basic),
        "hra": hra,
        "medical": medical,
        "gross": gross,
        "working_days": float(working_days),
        "present_days": float(present_days),
        "absent_days": float(absent_days),
        "unpaid_leave_days": float(unpaid_leave_days),
        "half_days": float(half_days),
        "deduction_amount": deduction_amount,
        "tax": tax,
        "net_pay": net_pay,
        "note": "; ".join(notes)[:300] or None,
        "_eligible_days": eligible_days,
        "_adjusted_gross": adjusted_gross,
    }


def generate_draft_run(db: Session, user: User, year: int, month: int) -> PayrollRun:
    """Create or regenerate the DRAFT payroll run for (year, month).

    ONE transaction: everything is flushed and committed once at the end; any
    error rolls the whole generation back. A finalized run for the same period
    raises 409 (immutability enforced here in the service layer).
    """
    company_id = user.company_id
    try:
        existing = (
            db.query(PayrollRun)
            .filter(
                PayrollRun.company_id == company_id,
                PayrollRun.period_year == year,
                PayrollRun.period_month == month,
            )
            .first()
        )
        if existing is not None:
            if existing.status == "finalized":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Payroll run for this period is finalized and cannot be regenerated",
                )
            run = existing
            db.query(PayrollItem).filter(PayrollItem.run_id == run.id).delete(
                synchronize_session=False
            )
        else:
            run = PayrollRun(
                company_id=company_id,
                period_year=year,
                period_month=month,
                status="draft",
            )
            db.add(run)
        db.flush()

        run.generated_by = user.id
        run.generated_at = dt.datetime.utcnow()

        total_gross = 0.0
        total_net = 0.0
        for emp in _employees_for_run(db, company_id, year, month):
            line = compute_employee_payslip(db, company_id, emp, year, month)
            line.pop("_eligible_days", None)
            line.pop("_adjusted_gross", None)
            item = PayrollItem(run_id=run.id, company_id=company_id, **line)
            db.add(item)
            total_gross += _f(line["gross"])
            total_net += _f(line["net_pay"])
        db.flush()

        run.total_gross = round2(total_gross)
        run.total_net = round2(total_net)
        # identity: total_gross − total_deductions == total_net (proration included)
        run.total_deductions = round2(total_gross - total_net)

        record_audit(
            db,
            company_id=company_id,
            user=user,
            action="payroll.generated",
            entity_type="payroll_run",
            entity_id=run.id,
            after={
                "period_year": year,
                "period_month": month,
                "status": "draft",
                "item_count": db.query(PayrollItem).filter(PayrollItem.run_id == run.id).count(),
                "total_gross": run.total_gross,
                "total_net": run.total_net,
            },
        )
        db.commit()
        db.refresh(run)
        return run
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


def finalize_run(db: Session, user: User, run: PayrollRun) -> PayrollRun:
    """Admin locks the run; notifies every employee with an item. ONE transaction."""
    try:
        if run.status == "finalized":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Payroll run already finalized"
            )
        before = {"status": run.status, "finalized_at": run.finalized_at}
        run.status = "finalized"
        run.finalized_by = user.id
        run.finalized_at = dt.datetime.utcnow()

        record_audit(
            db,
            company_id=run.company_id,
            user=user,
            action="payroll.finalized",
            entity_type="payroll_run",
            entity_id=run.id,
            before=before,
            after={
                "status": "finalized",
                "finalized_by": user.id,
                "finalized_at": run.finalized_at.isoformat(),
                "total_gross": float(run.total_gross),
                "total_net": float(run.total_net),
            },
        )

        # notification for every employee with a payslip in this run
        item_rows = (
            db.query(PayrollItem.employee_id)
            .filter(PayrollItem.run_id == run.id)
            .distinct()
            .all()
        )
        title = (
            f"Your payslip for {MONTH_NAMES[run.period_month - 1]} {run.period_year} is ready"
        )
        for (emp_id,) in item_rows:
            notify_employee(
                db,
                employee_id=emp_id,
                title=title,
                body="Download it from the Payslips page.",
                link="/payslips",
            )

        db.commit()
        db.refresh(run)
        return run
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


# ----------------------------------------------------------------- read helpers
def _run_item_count(db: Session, run_id: int) -> int:
    return (
        db.query(PayrollItem).filter(PayrollItem.run_id == run_id).count()
    )


def list_runs(
    db: Session, company_id: int, page: int = 1, page_size: int = 20
) -> dict:
    base = db.query(PayrollRun).filter(PayrollRun.company_id == company_id)
    total = base.count()
    rows = (
        base.order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = []
    for run in rows:
        items.append(
            {
                "id": run.id,
                "period_year": run.period_year,
                "period_month": run.period_month,
                "status": run.status,
                "generated_by": run.generated_by,
                "generated_at": run.generated_at,
                "finalized_by": run.finalized_by,
                "finalized_at": run.finalized_at,
                "total_gross": _f(run.total_gross),
                "total_deductions": _f(run.total_deductions),
                "total_net": _f(run.total_net),
                "item_count": _run_item_count(db, run.id),
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def serialize_run(db: Session, run: PayrollRun) -> dict:
    return {
        "id": run.id,
        "period_year": run.period_year,
        "period_month": run.period_month,
        "status": run.status,
        "generated_by": run.generated_by,
        "generated_at": run.generated_at,
        "finalized_by": run.finalized_by,
        "finalized_at": run.finalized_at,
        "total_gross": _f(run.total_gross),
        "total_deductions": _f(run.total_deductions),
        "total_net": _f(run.total_net),
        "item_count": _run_item_count(db, run.id),
    }


def serialize_item(item: PayrollItem, emp: Employee | None) -> dict:
    department = None
    designation = None
    if emp is not None:
        if emp.department is not None:
            department = emp.department.name
        if emp.designation is not None:
            designation = emp.designation.name
    return {
        "id": item.id,
        "run_id": item.run_id,
        "employee_id": item.employee_id,
        "employee_code": emp.employee_code if emp else None,
        "employee_name": (f"{emp.first_name} {emp.last_name or ''}".strip() if emp else None),
        "department": department,
        "designation": designation,
        "basic": _f(item.basic),
        "hra": _f(item.hra),
        "medical": _f(item.medical),
        "gross": _f(item.gross),
        "working_days": _f(item.working_days),
        "present_days": _f(item.present_days),
        "absent_days": _f(item.absent_days),
        "unpaid_leave_days": _f(item.unpaid_leave_days),
        "half_days": _f(item.half_days),
        "deduction_amount": _f(item.deduction_amount),
        "tax": _f(item.tax),
        "net_pay": _f(item.net_pay),
        "note": item.note,
    }


def list_run_items(db: Session, company_id: int, run: PayrollRun) -> list[dict]:
    rows = (
        db.query(PayrollItem, Employee)
        .join(Employee, PayrollItem.employee_id == Employee.id)
        .filter(PayrollItem.run_id == run.id, PayrollItem.company_id == company_id)
        .order_by(Employee.employee_code.asc())
        .all()
    )
    return [serialize_item(item, emp) for item, emp in rows]


def payslips_for_user(db: Session, user: User) -> list[dict]:
    """Finalized payslips belonging to the caller's own employee profile."""
    if user.employee_id is None:
        return []
    rows = (
        db.query(PayrollItem, PayrollRun, Employee)
        .join(PayrollRun, PayrollItem.run_id == PayrollRun.id)
        .join(Employee, PayrollItem.employee_id == Employee.id)
        .filter(
            PayrollItem.employee_id == user.employee_id,
            PayrollItem.company_id == user.company_id,
            PayrollRun.status == "finalized",
        )
        .order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())
        .all()
    )
    out = []
    for item, run, emp in rows:
        payload = serialize_item(item, emp)
        payload["period_year"] = run.period_year
        payload["period_month"] = run.period_month
        payload["status"] = run.status
        out.append(payload)
    return out
