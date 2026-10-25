"""Policy Q&A — curated rules from the official brief (Section 3 / M2–M7).

The same text is injected into the LLM system prompt (so the model "answers only
from the rules or says it does not know") and used verbatim by the offline
provider for deterministic answers. Live company settings (office start, grace,
weekend, half-day threshold) and live leave-type quotas are read from the DB so
answers always match what the app actually enforces.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import LeaveType
from app.services.calendar_utils import get_settings, weekend_days

# Short form used inside the LLM system prompt.
POLICY_TEXT = """\
- Office start 09:00 (company setting), grace period 15 minutes -> an arrival is
  "late" only after 09:15; lateness is decided by the SERVER clock only.
- Half day = worked hours below the half-day threshold (default 5 h).
- Weekend = Saturday and Sunday (company setting); public holidays are set by Admin.
- Working days for leave/payroll exclude weekends and holidays.
- Leave quotas (yearly): annual 14, sick 8, casual 10, unpaid unlimited.
  Balance = quota - approved days this year; overlapping pending/approved or
  over-balance requests are rejected (409 / 422).
- Approval: HR approves leave requests and attendance corrections; employees can
  never approve their own request; Admin is view-only for approvals and is the
  only role that finalizes payroll (finalized runs are immutable).
- Payroll: gross = 1.5 x basic (HRA 40% of basic, medical 10% of basic);
  per-day = gross / working days in the month; deduction = (absent + unpaid leave
  + 0.5 x half days) x per-day; joiners/leavers are prorated.
- Income tax (illustrative annualized slabs on gross x 12): 0 to 600k = 0%;
  up to 1.2M = 5%; up to 2.4M = 30k + 15%; up to 3.6M = 210k + 25%;
  above = 510k + 35%. Monthly tax = annual / 12.
- Roles: Admin = full access incl. settings, payroll finalize; HR = people ops
  (employees, attendance, leave approvals, payroll runs); Employee = own records
  only (own attendance, own leave, own payslip). Salaries of other employees are
  never shown to an employee.
- Attendance: one record per employee per day; absent = no record on a working
  day with no approved leave; missing checkout = no check-out after the day ends.
  Geofence: check-in accepted only inside the Admin-set radius (Haversine on the
  server) with GPS accuracy better than 100 m.
"""

# Offline matcher: ordered (phrases, answer key); ANY phrase (lowercased) hits.
_PHRASES: list[tuple[tuple[str, ...], str]] = [
    (
        (
            "office time",
            "office timing",
            "office hours",
            "start time",
            "what time",
            "kitna bajey",
            "kitne baje",
            "office start",
        ),
        "office",
    ),
    (
        (
            "grace",
            "late after",
            "counts as late",
            "counted as late",
            "marked late",
            "being late",
            "when am i late",
            "late kab",
        ),
        "late",
    ),
    (("half day", "halfday", "under 5", "less than 5 hours", "5 hours"), "halfday"),
    (("weekend", "saturday", "sunday", "hafta"), "weekend"),
    (("holiday", "public holiday", "chutti ka din", "non-working"), "holiday"),
    (("working day", "working days", "kaam ke din"), "workingday"),
    (
        (
            "quota",
            "per year",
            "in a year",
            "how many days of leave",
            "kitni chutti",
            "allowed leave",
            "leave allowed",
            "can i take",
            "leave policy",
            "leave rules",
        ),
        "quota",
    ),
    (("tax", "slab", "income tax"), "tax"),
    (("gross", "hra", "1.5", "salary structure", "pay structure"), "formula"),
    (("deduct", "deduction", "net pay", "absent day"), "deduction"),
    (("approve", "approval", "who signs", "self-approval"), "approval"),
    (("permission", "role", "who can", "access", "visibility", "rbac"), "roles"),
    (("geofence", "camera", "gps", "radius", "location"), "geofence"),
    (("correction", "correct my attendance", "punch"), "correction"),
    (("overlap", "over balance", "insufficient", "not enough leave"), "leave_errors"),
]


def _office_answer(s) -> str:
    start = s.office_start_time.strftime("%H:%M") if s.office_start_time else "09:00"
    return (
        f"Office starts at {start} (company setting). The grace period is "
        f"{int(s.grace_period_minutes or 0)} minutes, so you are only marked late "
        f"after {start} + {int(s.grace_period_minutes or 0)} minutes."
    )


def _late_answer(s) -> str:
    start = s.office_start_time.strftime("%H:%M") if s.office_start_time else "09:00"
    deadline = s.office_start_time
    import datetime as dt

    if deadline is not None:
        deadline = (
            dt.datetime.combine(dt.date(2000, 1, 1), deadline)
            + dt.timedelta(minutes=int(s.grace_period_minutes or 0))
        ).strftime("%H:%M")
    else:
        deadline = "09:15"
    return (
        f"You are marked late only when you check in after {start} plus the "
        f"{int(s.grace_period_minutes or 0)}-minute grace period, i.e. after {deadline}. "
        "The server clock decides - not the device clock."
    )


def _quota_answer(db: Session, company_id: int) -> str:
    rows = (
        db.query(LeaveType)
        .filter(LeaveType.company_id == company_id)
        .order_by(LeaveType.id)
        .all()
    )
    if not rows:
        return (
            "Leave quotas (defaults): annual 14, sick 8, casual 10, unpaid unlimited "
            "per year."
        )
    parts = []
    for r in rows:
        quota = "unlimited" if r.yearly_quota is None else f"{r.yearly_quota} days/year"
        parts.append(f"{r.name} ({r.code}): {quota}, {'paid' if r.is_paid else 'unpaid'}")
    return (
        "Your company's yearly quotas are " + "; ".join(parts) +
        ". Balance = quota - approved days this year; pending requests don't reduce "
        "the balance until approved, and unpaid leave is unlimited."
    )


_ANSWERS: dict[str, callable] = {
    "office": lambda db, cid, s: _office_answer(s),
    "late": lambda db, cid, s: _late_answer(s),
    "halfday": lambda db, cid, s: (
        f"A day with less than {s.half_day_threshold_hours or 5} worked hours is a "
        f"half day (0.5 day deduction in payroll)."
    ),
    "weekend": lambda db, cid, s: (
        "The weekend is " + " and ".join(sorted(weekend_days(s))) +
        " (company setting); no attendance is expected on weekends."
    ),
    "holiday": lambda db, cid, s: (
        "Public holidays are configured by Admin (Org > Holidays). Weekends and "
        "holidays are excluded from leave working days and payroll denominators."
    ),
    "workingday": lambda db, cid, s: (
        "A working day excludes weekends and public holidays — leave and payroll "
        "counts only include working days."
    ),
    "quota": lambda db, cid, s: _quota_answer(db, cid),
    "tax": lambda db, cid, s: (
        "Income tax uses the illustrative annualized slabs on gross x 12: 0-600k = 0%; "
        "up to 1.2M = 5%; up to 2.4M = 30k + 15%; up to 3.6M = 210k + 25%; "
        "above = 510k + 35%. Monthly tax = annual tax / 12, deducted from net pay."
    ),
    "formula": lambda db, cid, s: (
        "Payroll formula: gross = 1.5 x basic (HRA = 40% of basic, medical = 10% of "
        "basic). Per-day = gross / working days in the month; joiners and leavers are "
        "prorated. Tax = slab(gross x 12) / 12."
    ),
    "deduction": lambda db, cid, s: (
        "Deduction = (absent days + unpaid leave days + 0.5 x half days) x per-day "
        "rate. Approved paid leave is never deducted; net = adjusted gross - "
        "deduction - tax (clamped at 0)."
    ),
    "approval": lambda db, cid, s: (
        "HR approves leave requests and attendance corrections; employees can never "
        "approve their own request. Admin is view-only for approvals and is the only "
        "role that finalizes a payroll run (finalized runs are locked)."
    ),
    "roles": lambda db, cid, s: (
        "Roles: Admin = everything, including settings and payroll finalize; HR = "
        "people operations (employees, attendance, leave approvals, payroll runs); "
        "Employee = own records only. The assistant applies exactly these rules, so "
        "an employee can never see another employee's data."
    ),
    "geofence": lambda db, cid, s: (
        "Check-in is accepted only inside the office radius set by Admin "
        f"({int(s.geofence_radius_m or 1000)} m, Haversine calculated on the server) "
        "and with GPS accuracy better than 100 m. The server time is authoritative."
    ),
    "correction": lambda db, cid, s: (
        "If an attendance record is wrong, raise a correction (Attendance > "
        "Corrections) with the date and the right times; HR approves or rejects it. "
        "Employees can only request corrections for themselves."
    ),
    "leave_errors": lambda db, cid, s: (
        "A leave request is rejected when it overlaps an existing pending/approved "
        "request (409) or when the requested working days exceed the remaining "
        "balance (422). Working days exclude weekends and holidays."
    ),
}


def answer_policy(message: str, db: Session, company_id: int) -> str | None:
    """Return a rules answer for `message`, or None when the rules don't cover it
    (the caller must then say it does not know)."""
    text = " ".join(message.lower().split())
    if not text:
        return None
    for phrases, key in _PHRASES:
        if any(p in text for p in phrases):
            return _ANSWERS[key](db, company_id, get_settings(db, company_id))
    return None
