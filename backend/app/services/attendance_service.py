"""Attendance service: check-in/out, month view, daily roster, corrections.

Time convention (module-wide, ARCHITECTURE §5):
* ``Attendance.check_in`` / ``check_out`` store **naive UTC** datetimes from the
  SERVER clock only — client-supplied timestamps are rejected at the schema layer.
* Every date/status decision is made in COMPANY-LOCAL time
  (``CompanySettings.timezone``, default Asia/Karachi).
* API responses serialise punch times as company-local ISO-8601 **with offset**;
  ``reviewed_*``/audit timestamps are serialised as naive-UTC ISO strings.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    Attendance,
    AttendanceCorrection,
    Employee,
    LeaveRequest,
    LeaveType,
    User,
)
from app.permissions.access import ensure_not_self_approval, ensure_self_or_staff
from app.services.calendar_utils import (
    get_settings,
    haversine_m,
    holiday_map,
    is_weekend,
    is_working_day,
    iter_days,
    month_date_range,
)
from app.services.notifications import notify_employee
from app.utils.audit import record_audit, serialize

UTC = dt.timezone.utc

# Display-only status: never persisted, computed for summaries/rosters (§5).
MISSING_CHECKOUT = "missing_checkout"


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #
def _tz(name: str | None) -> dt.tzinfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return UTC


def utc_now() -> dt.datetime:
    """Naive UTC timestamp — the ONLY source of attendance time."""
    return dt.datetime.now(UTC).replace(tzinfo=None)


def to_local(ts: dt.datetime | None, tz_name: str | None) -> dt.datetime | None:
    if ts is None:
        return None
    return ts.replace(tzinfo=UTC).astimezone(_tz(tz_name))


def iso_local(ts: dt.datetime | None, tz_name: str | None) -> str | None:
    loc = to_local(ts, tz_name)
    return loc.isoformat() if loc is not None else None


def local_to_utc(naive_local: dt.datetime, tz_name: str | None) -> dt.datetime:
    return naive_local.replace(tzinfo=_tz(tz_name)).astimezone(UTC).replace(tzinfo=None)


def local_today(settings) -> dt.date:
    return to_local(utc_now(), settings.timezone).date()  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# Status rules (pure, unit-testable — see tests/test_attendance_leave.py)
# --------------------------------------------------------------------------- #
def compute_status(
    check_in_local: dt.datetime | None, settings, worked_hours: float = 0.0
) -> str:
    """Deterministic attendance status (ARCHITECTURE §5).

    Precedence: ``half_day`` (0 < worked_hours < threshold) > ``late`` > ``present``.
    Late iff check-in is strictly after ``office_start_time + grace_period_minutes``
    (boundaries: 09:00 -> present, 09:15 -> present, 09:16 -> late for 09:00+15m).
    ``check_in_local`` must be company-local wall-clock time.
    """
    threshold = float(getattr(settings, "half_day_threshold_hours", None) or 5.0)
    if worked_hours and 0 < worked_hours < threshold:
        return "half_day"
    if check_in_local is None:
        return "absent"
    # Accept aware (company-local) or naive inputs; compare wall-clock only.
    check_in_local = check_in_local.replace(tzinfo=None)
    start = dt.datetime.combine(
        check_in_local.date(), settings.office_start_time or dt.time(9, 0)
    )
    deadline = start + dt.timedelta(minutes=int(settings.grace_period_minutes or 0))
    return "late" if check_in_local > deadline else "present"


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #
def _require_employee(db: Session, user: User) -> Employee:
    if user.employee_id is None:
        raise HTTPException(status_code=403, detail="No employee profile")
    emp = db.get(Employee, user.employee_id)
    if emp is None or emp.company_id != user.company_id:
        raise HTTPException(status_code=403, detail="No employee profile")
    return emp


def _full_name(emp: Employee) -> str:
    return f"{emp.first_name} {emp.last_name or ''}".strip()


def _is_missing_checkout(
    rec: Attendance, settings, holidays: dict[dt.date, str], today: dt.date
) -> bool:
    """Open record on a PAST working day -> missing_checkout (§5)."""
    return (
        rec.check_in is not None
        and rec.check_out is None
        and rec.date < today
        and is_working_day(rec.date, settings, holidays)
    )


def _record_dict(rec: Attendance, settings, holidays: dict[dt.date, str]) -> dict:
    # DECISION (task requirement): missing_checkout is exposed as a per-day
    # computed flag ``missing_checkout`` plus ``display_status``; the persisted
    # ``attendance.status`` column is never rewritten — §5 says it is
    # "detected in summaries".
    missing = _is_missing_checkout(rec, settings, holidays, local_today(settings))
    return {
        "id": rec.id,
        "employee_id": rec.employee_id,
        "date": rec.date.isoformat(),
        "check_in": iso_local(rec.check_in, settings.timezone),
        "check_out": iso_local(rec.check_out, settings.timezone),
        "status": rec.status,
        "display_status": MISSING_CHECKOUT if missing else rec.status,
        "missing_checkout": missing,
        "worked_hours": round(float(rec.worked_hours or 0.0), 2),
        "source": rec.source or "manual",
    }


def _to_utc(ts: dt.time | dt.datetime | None, on_date: dt.date, tz_name: str):
    """Normalise correction input to naive UTC: time-only values are clock
    times on ``attendance_date`` (company-local); naive datetimes are treated
    as company-local; aware datetimes are converted directly."""
    if ts is None:
        return None
    if isinstance(ts, dt.datetime):
        if ts.tzinfo is not None:
            return ts.astimezone(UTC).replace(tzinfo=None)
        return local_to_utc(ts, tz_name)
    return local_to_utc(dt.datetime.combine(on_date, ts), tz_name)


# --------------------------------------------------------------------------- #
# Check-in / check-out
# --------------------------------------------------------------------------- #
def check_in(db: Session, *, user: User, payload, source: str = "manual") -> dict:
    """``source`` records HOW the day record was created (``manual`` punch vs
    ``face_camera`` check-in, M10); it is only ever set together with a record
    that passed all checks."""
    emp = _require_employee(db, user)
    settings = get_settings(db, user.company_id)
    today = local_today(settings)

    # One record per employee per day -> 409 (checked before geofence).
    existing = (
        db.query(Attendance)
        .filter(
            Attendance.company_id == user.company_id,
            Attendance.employee_id == emp.id,
            Attendance.date == today,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Already checked in today")

    lat = lng = None
    if payload is not None:
        if payload.accuracy_m is not None and payload.accuracy_m > 100:
            raise HTTPException(status_code=422, detail="GPS accuracy too low")
        lat, lng = payload.lat, payload.lng
        # Geofence only enforced when both lat/lng and office coords exist (§5).
        if lat is not None and settings.office_lat is not None and settings.office_lng is not None:
            dist = haversine_m(
                float(lat), float(lng), float(settings.office_lat), float(settings.office_lng)
            )
            radius = float(settings.geofence_radius_m or 1000)
            if dist > radius:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Outside office geofence: {dist:.0f} m from office "
                        f"(radius {radius:.0f} m)"
                    ),
                )

    now = utc_now()  # server clock only
    rec = Attendance(
        company_id=user.company_id,
        employee_id=emp.id,
        date=today,
        check_in=now,
        status=compute_status(to_local(now, settings.timezone), settings, 0.0),
        worked_hours=0.0,
        check_in_lat=lat,
        check_in_lng=lng,
        source=source,
    )
    db.add(rec)
    db.flush()
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="attendance.check_in",
        entity_type="attendance",
        entity_id=rec.id,
        after=serialize(rec),
    )
    db.commit()
    db.refresh(rec)
    return _record_dict(rec, settings, holiday_map(db, user.company_id))


def check_out(db: Session, *, user: User) -> dict:
    emp = _require_employee(db, user)
    settings = get_settings(db, user.company_id)
    today = local_today(settings)
    rec = (
        db.query(Attendance)
        .filter(
            Attendance.company_id == user.company_id,
            Attendance.employee_id == emp.id,
            Attendance.date == today,
        )
        .first()
    )
    if rec is None:
        raise HTTPException(status_code=409, detail="Not checked in today")
    if rec.check_out is not None:
        raise HTTPException(status_code=409, detail="Already checked out today")

    before = serialize(rec)
    now = utc_now()
    rec.check_out = now
    elapsed = max((now - rec.check_in).total_seconds(), 0.0) if rec.check_in else 0.0
    rec.worked_hours = round(elapsed / 3600.0, 2)
    rec.status = compute_status(
        to_local(rec.check_in, settings.timezone), settings, rec.worked_hours
    )
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="attendance.check_out",
        entity_type="attendance",
        entity_id=rec.id,
        before=before,
        after=serialize(rec),
    )
    db.commit()
    db.refresh(rec)
    return _record_dict(rec, settings, holiday_map(db, user.company_id))


# --------------------------------------------------------------------------- #
# Month view + frozen summary contract
# --------------------------------------------------------------------------- #
def _approved_leave_days(
    db: Session,
    company_id: int,
    employee_id: int,
    date_from: dt.date,
    date_to: dt.date,
    settings,
    holidays: dict[dt.date, str],
) -> set[dt.date]:
    rows = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.company_id == company_id,
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= date_to,
            LeaveRequest.end_date >= date_from,
        )
        .all()
    )
    days: set[dt.date] = set()
    for row in rows:
        start = max(row.start_date, date_from)
        end = min(row.end_date, date_to)
        for day in iter_days(start, end):
            if is_working_day(day, settings, holidays):
                days.add(day)
    return days


def summary_for_employee(
    db: Session, company_id: int, employee_id: int, date_from: dt.date, date_to: dt.date
) -> dict:
    """FROZEN contract (ARCHITECTURE §5b).

    Returns ``{days_present, late, half_days, absent, on_leave, total_hours,
    working_days, missing_checkout, date_from, date_to}``.
    ``absent`` counts working days up to and including today that have no
    attendance record and no approved leave; approved-leave working days are
    counted as ``on_leave`` instead (so approved leave is NEVER absent).
    """
    result = {
        "days_present": 0,
        "late": 0,
        "half_days": 0,
        "absent": 0,
        "on_leave": 0,
        "total_hours": 0.0,
        "working_days": 0,
        "missing_checkout": 0,
        "date_from": date_from,
        "date_to": date_to,
    }
    if date_to < date_from:
        return result

    settings = get_settings(db, company_id)
    holidays = holiday_map(db, company_id)
    today = local_today(settings)
    records = (
        db.query(Attendance)
        .filter(
            Attendance.company_id == company_id,
            Attendance.employee_id == employee_id,
            Attendance.date >= date_from,
            Attendance.date <= date_to,
        )
        .all()
    )
    by_date = {r.date: r for r in records}
    leave_days = _approved_leave_days(
        db, company_id, employee_id, date_from, date_to, settings, holidays
    )

    for day in iter_days(date_from, date_to):
        is_wd = is_working_day(day, settings, holidays)
        if is_wd:
            result["working_days"] += 1
        rec = by_date.get(day)
        if rec is not None:
            # Punched records always count, even on a weekend/holiday.
            result["total_hours"] += float(rec.worked_hours or 0.0)
            st = rec.status
            if st == "present":
                result["days_present"] += 1
            elif st == "late":
                result["late"] += 1
            elif st == "half_day":
                result["half_days"] += 1
            if _is_missing_checkout(rec, settings, holidays, today):
                result["missing_checkout"] += 1
        elif is_wd:
            if day in leave_days:
                result["on_leave"] += 1
            elif day <= today:
                result["absent"] += 1

    result["total_hours"] = round(result["total_hours"], 2)
    return result


def month_view(
    db: Session, *, user: User, year: int | None, month: int | None
) -> dict:
    emp = _require_employee(db, user)
    settings = get_settings(db, user.company_id)
    today = local_today(settings)
    year = year or today.year
    month = month or today.month
    start, end = month_date_range(year, month)
    holidays = holiday_map(db, user.company_id)
    rows = (
        db.query(Attendance)
        .filter(
            Attendance.company_id == user.company_id,
            Attendance.employee_id == emp.id,
            Attendance.date >= start,
            Attendance.date <= end,
        )
        .order_by(Attendance.date)
        .all()
    )
    summary = summary_for_employee(db, user.company_id, emp.id, start, end)
    return {
        "year": year,
        "month": month,
        "records": [_record_dict(r, settings, holidays) for r in rows],
        "summary": summary,
    }


# --------------------------------------------------------------------------- #
# Day roster (HR/Admin)
# --------------------------------------------------------------------------- #
def board(
    db: Session, *, company_id: int, day: dt.date, department_id: int | None = None
) -> dict:
    from app.models import Department

    settings = get_settings(db, company_id)
    holidays = holiday_map(db, company_id)
    today = local_today(settings)

    if day in holidays:
        day_type = "holiday"
    elif is_weekend(day, settings):
        day_type = "weekend"
    else:
        day_type = "working"

    q = db.query(Employee).filter(
        Employee.company_id == company_id, Employee.employment_status == "active"
    )
    if department_id is not None:
        q = q.filter(Employee.department_id == department_id)
    employees = q.order_by(Employee.employee_code).all()

    dept_map = {
        d.id: d.name
        for d in db.query(Department).filter(Department.company_id == company_id).all()
    }
    records = {
        r.employee_id: r
        for r in db.query(Attendance)
        .filter(Attendance.company_id == company_id, Attendance.date == day)
        .all()
    }
    leave_rows = (
        db.query(LeaveRequest, LeaveType.code)
        .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
        .filter(
            LeaveRequest.company_id == company_id,
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= day,
            LeaveRequest.end_date >= day,
        )
        .all()
    )
    leave_map = {
        req.employee_id: {"request_id": req.id, "leave_type_code": code}
        for req, code in leave_rows
    }

    items: list[dict] = []
    for emp in employees:
        rec = records.get(emp.id)
        leave = leave_map.get(emp.id)
        missing = False
        check_in = check_out = None
        hours = 0.0
        if rec is not None:
            # A punched record always wins over leave/non-working classification.
            status = rec.status
            missing = _is_missing_checkout(rec, settings, holidays, today)
            check_in = iso_local(rec.check_in, settings.timezone)
            check_out = iso_local(rec.check_out, settings.timezone)
            hours = round(float(rec.worked_hours or 0.0), 2)
        elif leave is not None:
            status = "on_leave"
        elif day_type == "holiday":
            status = "off"  # non-working holiday (ARCHITECTURE §4 roster enum)
        elif day_type == "weekend":
            status = "weekend"
        elif day <= today:
            status = "absent"
        else:
            # Forward-looking roster row; display-only, never persisted.
            status = "scheduled"
        items.append(
            {
                "employee_id": emp.id,
                "employee_code": emp.employee_code,
                "full_name": _full_name(emp),
                "department_id": emp.department_id,
                "department_name": dept_map.get(emp.department_id),
                "status": status,
                "missing_checkout": missing,
                "check_in": check_in,
                "check_out": check_out,
                "worked_hours": hours,
                "leave": leave,
            }
        )
    return {"date": day.isoformat(), "day_type": day_type, "items": items}


# --------------------------------------------------------------------------- #
# Corrections
# --------------------------------------------------------------------------- #
def _correction_dict(corr: AttendanceCorrection, settings, db: Session) -> dict:
    emp = db.get(Employee, corr.employee_id)
    return {
        "id": corr.id,
        "employee_id": corr.employee_id,
        "employee_name": _full_name(emp) if emp is not None else None,
        "attendance_date": corr.attendance_date.isoformat(),
        "requested_check_in": iso_local(corr.requested_check_in, settings.timezone),
        "requested_check_out": iso_local(corr.requested_check_out, settings.timezone),
        "reason": corr.reason,
        "status": corr.status,
        "requested_by": corr.requested_by,
        "reviewed_by": corr.reviewed_by,
        "reviewed_at": corr.reviewed_at.isoformat() if corr.reviewed_at else None,
        "review_comment": corr.review_comment,
        "created_at": corr.created_at.isoformat() if corr.created_at else None,
    }


def create_correction(db: Session, *, user: User, payload) -> dict:
    if payload.employee_id is None and user.employee_id is None:
        raise HTTPException(status_code=422, detail="employee_id is required")
    target_id = (
        payload.employee_id if payload.employee_id is not None else user.employee_id
    )
    # Employees may only request corrections for themselves (403 otherwise).
    ensure_self_or_staff(user, target_id, "correction")
    emp = db.get(Employee, target_id)
    if emp is None or emp.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Employee not found")

    settings = get_settings(db, user.company_id)
    ci = _to_utc(payload.check_in, payload.attendance_date, settings.timezone)
    co = _to_utc(payload.check_out, payload.attendance_date, settings.timezone)
    if ci is None and co is None:
        raise HTTPException(
            status_code=422, detail="Provide check_in and/or check_out to correct"
        )
    if ci is not None and co is not None and co <= ci:
        raise HTTPException(
            status_code=422, detail="check_out must be after check_in"
        )

    corr = AttendanceCorrection(
        company_id=user.company_id,
        employee_id=target_id,
        attendance_date=payload.attendance_date,
        requested_check_in=ci,
        requested_check_out=co,
        reason=payload.reason,
        status="pending",
        requested_by=user.id,
    )
    db.add(corr)
    db.flush()
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="attendance.correction.requested",
        entity_type="attendance_correction",
        entity_id=corr.id,
        after=serialize(corr),
    )
    db.commit()
    db.refresh(corr)
    return _correction_dict(corr, settings, db)


def list_corrections(
    db: Session,
    *,
    company_id: int,
    employee_id: int | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    settings = get_settings(db, company_id)
    q = (
        db.query(AttendanceCorrection)
        .filter(AttendanceCorrection.company_id == company_id)
    )
    if employee_id is not None:
        q = q.filter(AttendanceCorrection.employee_id == employee_id)
    if status:
        q = q.filter(AttendanceCorrection.status == status)
    total = q.count()
    rows = (
        q.order_by(
            AttendanceCorrection.attendance_date.desc(), AttendanceCorrection.id.desc()
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_correction_dict(r, settings, db) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _get_correction(db: Session, user: User, correction_id: int) -> AttendanceCorrection:
    corr = db.get(AttendanceCorrection, correction_id)
    if corr is None or corr.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Correction not found")
    return corr


def approve_correction(
    db: Session, *, user: User, correction_id: int, comment: str | None = None
) -> dict:
    corr = _get_correction(db, user, correction_id)
    # HR/Admin must not approve their own correction (§5).
    ensure_not_self_approval(user, corr.employee_id, "correction")
    if corr.status != "pending":
        raise HTTPException(
            status_code=409, detail=f"Correction already {corr.status}"
        )

    settings = get_settings(db, user.company_id)
    rec = (
        db.query(Attendance)
        .filter(
            Attendance.company_id == corr.company_id,
            Attendance.employee_id == corr.employee_id,
            Attendance.date == corr.attendance_date,
        )
        .first()
    )
    before = serialize(rec)  # None => day record did not exist yet
    if rec is None:
        rec = Attendance(
            company_id=corr.company_id,
            employee_id=corr.employee_id,
            date=corr.attendance_date,
            status="present",
            worked_hours=0.0,
        )
        db.add(rec)
    if corr.requested_check_in is not None:
        rec.check_in = corr.requested_check_in
    if corr.requested_check_out is not None:
        rec.check_out = corr.requested_check_out
    if rec.check_in is not None and rec.check_out is not None:
        rec.worked_hours = round(
            max((rec.check_out - rec.check_in).total_seconds(), 0.0) / 3600.0, 2
        )
    else:
        rec.worked_hours = 0.0
    if rec.check_in is not None:
        rec.status = compute_status(
            to_local(rec.check_in, settings.timezone), settings, rec.worked_hours
        )
    else:
        rec.status = "present"  # edge: only a check-out was corrected

    corr.status = "approved"
    corr.reviewed_by = user.id
    corr.reviewed_at = utc_now()
    corr.review_comment = comment

    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="attendance.correction.approved",
        entity_type="attendance_correction",
        entity_id=corr.id,
        before=before,
        after=serialize(rec),
    )
    notify_employee(
        db,
        employee_id=corr.employee_id,
        title="Attendance correction approved",
        body=f"Correction for {corr.attendance_date.isoformat()} was approved.",
        link="/attendance",
    )
    db.commit()
    db.refresh(corr)
    return _correction_dict(corr, settings, db)


def reject_correction(
    db: Session, *, user: User, correction_id: int, comment: str | None = None
) -> dict:
    corr = _get_correction(db, user, correction_id)
    ensure_not_self_approval(user, corr.employee_id, "correction")
    if corr.status != "pending":
        raise HTTPException(
            status_code=409, detail=f"Correction already {corr.status}"
        )

    before = serialize(corr)
    corr.status = "rejected"
    corr.reviewed_by = user.id
    corr.reviewed_at = utc_now()
    corr.review_comment = comment
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="attendance.correction.rejected",
        entity_type="attendance_correction",
        entity_id=corr.id,
        before=before,
        after=serialize(corr),
    )
    notify_employee(
        db,
        employee_id=corr.employee_id,
        title="Attendance correction rejected",
        body=f"Correction for {corr.attendance_date.isoformat()} was rejected.",
        link="/attendance",
    )
    db.commit()
    db.refresh(corr)
    return _correction_dict(corr, get_settings(db, user.company_id), db)
