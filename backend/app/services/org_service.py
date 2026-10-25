"""Organization settings + structure CRUD (write: Admin, read: HR/Admin).

All helpers validate tenant scoping (company_id) and audit their mutations.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    CompanySettings,
    Department,
    Designation,
    Employee,
    Holiday,
    LeaveRequest,
    LeaveType,
    User,
)
from app.services.calendar_utils import WEEKDAY_NAMES
from app.utils.audit import record_audit, serialize

DEFAULT_SETTINGS: dict[str, Any] = {
    "office_start_time": "09:00",
    "grace_period_minutes": 15,
    "weekend_days": ["Saturday", "Sunday"],
    "office_lat": None,
    "office_lng": None,
    "geofence_radius_m": 1000,
    "timezone": "Asia/Karachi",
    "half_day_threshold_hours": 5.0,
}

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$")
_TZ_RE = re.compile(r"^[A-Za-z0-9_+\-]+/[A-Za-z0-9_+\-]+$")


# --------------------------------------------------------------------------- settings
def get_settings_row(db: Session, company_id: int, *, create: bool = False) -> CompanySettings | None:
    row = (
        db.query(CompanySettings)
        .filter(CompanySettings.company_id == company_id)
        .first()
    )
    if row is None and create:
        row = CompanySettings(company_id=company_id)
        db.add(row)
        db.flush()
    return row


def settings_to_dict(row: CompanySettings | None) -> dict[str, Any]:
    if row is None:
        return dict(DEFAULT_SETTINGS)
    t = row.office_start_time
    return {
        "office_start_time": t.strftime("%H:%M") if t else DEFAULT_SETTINGS["office_start_time"],
        "grace_period_minutes": int(row.grace_period_minutes or 0),
        "weekend_days": list(row.weekend_days or []),
        "office_lat": float(row.office_lat) if row.office_lat is not None else None,
        "office_lng": float(row.office_lng) if row.office_lng is not None else None,
        "geofence_radius_m": int(row.geofence_radius_m or 0),
        "timezone": row.timezone or DEFAULT_SETTINGS["timezone"],
        "half_day_threshold_hours": float(row.half_day_threshold_hours or 0),
    }


def validate_settings_patch(data: dict[str, Any]) -> None:
    """Raise 422 (list of messages) when a settings patch is invalid."""
    errors: list[str] = []
    start = data.get("office_start_time")
    if start is not None:
        if not isinstance(start, str) or not _TIME_RE.match(start.strip()):
            errors.append("office_start_time must be HH:MM (or HH:MM:SS), e.g. 09:00")
    weekends = data.get("weekend_days")
    if weekends is not None:
        if not isinstance(weekends, list):
            errors.append("weekend_days must be a list of weekday names")
        else:
            if len(set(weekends)) != len(weekends):
                errors.append("weekend_days contains duplicates")
            for day in weekends:
                if day not in WEEKDAY_NAMES:
                    errors.append(f"Invalid weekend day: {day!r}")
    tz = data.get("timezone")
    if tz is not None and (not isinstance(tz, str) or not _TZ_RE.match(tz.strip())):
        errors.append("timezone must be an IANA name like 'Asia/Karachi'")
    lat = data.get("office_lat")
    if lat is not None and not (-90 <= float(lat) <= 90):
        errors.append("office_lat must be between -90 and 90")
    lng = data.get("office_lng")
    if lng is not None and not (-180 <= float(lng) <= 180):
        errors.append("office_lng must be between -180 and 180")
    if errors:
        raise HTTPException(status_code=422, detail=errors)


def update_settings(
    db: Session, company_id: int, user: User, data: dict[str, Any], fields_set: set[str]
) -> dict[str, Any]:
    validate_settings_patch(data)
    row = get_settings_row(db, company_id, create=True)
    assert row is not None
    before = settings_to_dict(row)

    for key in fields_set:
        value = data.get(key)
        if key == "office_start_time" and value is not None:
            value = dt.time.fromisoformat(value.strip())
        setattr(row, key, value)

    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="settings_update",
        entity_type="company_settings",
        entity_id=row.id,
        before=before,
        after=settings_to_dict(row),
    )
    db.commit()
    db.refresh(row)
    return settings_to_dict(row)


# ---------------------------------------------------------------------- departments
def _count_by_fk(db: Session, company_id: int, column) -> dict[int, int]:
    rows = (
        db.query(column, func.count(Employee.id))
        .join(Employee, Employee.department_id == column)
        .filter(Employee.company_id == company_id)
        .group_by(column)
        .all()
    )
    return {key: count for key, count in rows}


def list_departments(db: Session, company_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(Department)
        .filter(Department.company_id == company_id)
        .order_by(Department.name)
        .all()
    )
    counts = _count_by_fk(db, company_id, Department.id)
    return [
        {"id": r.id, "name": r.name, "employee_count": counts.get(r.id, 0)} for r in rows
    ]


def _get_department(db: Session, company_id: int, dept_id: int) -> Department:
    row = (
        db.query(Department)
        .filter(Department.id == dept_id, Department.company_id == company_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Department not found")
    return row


def create_department(db: Session, company_id: int, user: User, name: str) -> dict:
    name = name.strip()
    dup = (
        db.query(Department)
        .filter(Department.company_id == company_id, func.lower(Department.name) == name.lower())
        .first()
    )
    if dup is not None:
        raise HTTPException(status_code=409, detail="Department name already exists")
    row = Department(company_id=company_id, name=name)
    db.add(row)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="department_create",
        entity_type="department",
        entity_id=row.id,
        after=serialize(row),
    )
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "employee_count": 0}


def update_department(
    db: Session, company_id: int, user: User, dept_id: int, name: str
) -> dict:
    row = _get_department(db, company_id, dept_id)
    name = name.strip()
    dup = (
        db.query(Department)
        .filter(
            Department.company_id == company_id,
            func.lower(Department.name) == name.lower(),
            Department.id != dept_id,
        )
        .first()
    )
    if dup is not None:
        raise HTTPException(status_code=409, detail="Department name already exists")
    before = serialize(row)
    row.name = name
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="department_update",
        entity_type="department",
        entity_id=row.id,
        before=before,
        after=serialize(row),
    )
    db.commit()
    db.refresh(row)
    counts = _count_by_fk(db, company_id, Department.id)
    return {"id": row.id, "name": row.name, "employee_count": counts.get(row.id, 0)}


def delete_department(db: Session, company_id: int, user: User, dept_id: int) -> None:
    row = _get_department(db, company_id, dept_id)
    used = (
        db.query(func.count(Employee.id))
        .filter(Employee.company_id == company_id, Employee.department_id == dept_id)
        .scalar()
        or 0
    )
    if used:
        raise HTTPException(
            status_code=409,
            detail=f"Department is referenced by {used} employee(s)",
        )
    before = serialize(row)
    db.delete(row)
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="department_delete",
        entity_type="department",
        entity_id=dept_id,
        before=before,
    )
    db.commit()


# --------------------------------------------------------------------- designations
def list_designations(db: Session, company_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(Designation)
        .filter(Designation.company_id == company_id)
        .order_by(Designation.name)
        .all()
    )
    counts: dict[int, int] = {}
    for key, count in (
        db.query(Designation.id, func.count(Employee.id))
        .join(Employee, Employee.designation_id == Designation.id)
        .filter(Employee.company_id == company_id)
        .group_by(Designation.id)
        .all()
    ):
        counts[key] = count
    return [
        {"id": r.id, "name": r.name, "employee_count": counts.get(r.id, 0)} for r in rows
    ]


def _get_designation(db: Session, company_id: int, item_id: int) -> Designation:
    row = (
        db.query(Designation)
        .filter(Designation.id == item_id, Designation.company_id == company_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Designation not found")
    return row


def create_designation(db: Session, company_id: int, user: User, name: str) -> dict:
    name = name.strip()
    dup = (
        db.query(Designation)
        .filter(
            Designation.company_id == company_id,
            func.lower(Designation.name) == name.lower(),
        )
        .first()
    )
    if dup is not None:
        raise HTTPException(status_code=409, detail="Designation name already exists")
    row = Designation(company_id=company_id, name=name)
    db.add(row)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="designation_create",
        entity_type="designation",
        entity_id=row.id,
        after=serialize(row),
    )
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "employee_count": 0}


def update_designation(
    db: Session, company_id: int, user: User, item_id: int, name: str
) -> dict:
    row = _get_designation(db, company_id, item_id)
    name = name.strip()
    dup = (
        db.query(Designation)
        .filter(
            Designation.company_id == company_id,
            func.lower(Designation.name) == name.lower(),
            Designation.id != item_id,
        )
        .first()
    )
    if dup is not None:
        raise HTTPException(status_code=409, detail="Designation name already exists")
    before = serialize(row)
    row.name = name
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="designation_update",
        entity_type="designation",
        entity_id=row.id,
        before=before,
        after=serialize(row),
    )
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "employee_count": 0}


def delete_designation(db: Session, company_id: int, user: User, item_id: int) -> None:
    row = _get_designation(db, company_id, item_id)
    used = (
        db.query(func.count(Employee.id))
        .filter(Employee.company_id == company_id, Employee.designation_id == item_id)
        .scalar()
        or 0
    )
    if used:
        raise HTTPException(
            status_code=409,
            detail=f"Designation is referenced by {used} employee(s)",
        )
    before = serialize(row)
    db.delete(row)
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="designation_delete",
        entity_type="designation",
        entity_id=item_id,
        before=before,
    )
    db.commit()


# ------------------------------------------------------------------------ holidays
def list_holidays(db: Session, company_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(Holiday)
        .filter(Holiday.company_id == company_id)
        .order_by(Holiday.date)
        .all()
    )
    return [
        {"id": r.id, "name": r.name, "date": r.date.isoformat() if r.date else None}
        for r in rows
    ]


def _get_holiday(db: Session, company_id: int, item_id: int) -> Holiday:
    row = (
        db.query(Holiday)
        .filter(Holiday.id == item_id, Holiday.company_id == company_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return row


def create_holiday(
    db: Session, company_id: int, user: User, name: str, date: dt.date
) -> dict:
    dup = (
        db.query(Holiday)
        .filter(Holiday.company_id == company_id, Holiday.date == date)
        .first()
    )
    if dup is not None:
        raise HTTPException(status_code=409, detail="A holiday already exists on that date")
    row = Holiday(company_id=company_id, name=name.strip(), date=date)
    db.add(row)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="holiday_create",
        entity_type="holiday",
        entity_id=row.id,
        after=serialize(row),
    )
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "date": row.date.isoformat()}


def update_holiday(
    db: Session, company_id: int, user: User, item_id: int, name: str, date: dt.date
) -> dict:
    row = _get_holiday(db, company_id, item_id)
    dup = (
        db.query(Holiday)
        .filter(
            Holiday.company_id == company_id,
            Holiday.date == date,
            Holiday.id != item_id,
        )
        .first()
    )
    if dup is not None:
        raise HTTPException(status_code=409, detail="A holiday already exists on that date")
    before = serialize(row)
    row.name = name.strip()
    row.date = date
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="holiday_update",
        entity_type="holiday",
        entity_id=item_id,
        before=before,
        after=serialize(row),
    )
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "date": row.date.isoformat()}


def delete_holiday(db: Session, company_id: int, user: User, item_id: int) -> None:
    row = _get_holiday(db, company_id, item_id)
    before = serialize(row)
    db.delete(row)
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="holiday_delete",
        entity_type="holiday",
        entity_id=item_id,
        before=before,
    )
    db.commit()


# --------------------------------------------------------------------- leave types
def list_leave_types(db: Session, company_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(LeaveType)
        .filter(LeaveType.company_id == company_id)
        .order_by(LeaveType.code)
        .all()
    )
    return [
        {
            "id": r.id,
            "name": r.name,
            "code": r.code,
            "yearly_quota": r.yearly_quota,
            "is_paid": r.is_paid,
        }
        for r in rows
    ]


def _get_leave_type(db: Session, company_id: int, item_id: int) -> LeaveType:
    row = (
        db.query(LeaveType)
        .filter(LeaveType.id == item_id, LeaveType.company_id == company_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Leave type not found")
    return row


def create_leave_type(
    db: Session,
    company_id: int,
    user: User,
    *,
    name: str,
    code: str,
    yearly_quota: int | None,
    is_paid: bool,
) -> dict:
    code = code.strip().upper()
    dup = (
        db.query(LeaveType)
        .filter(LeaveType.company_id == company_id, LeaveType.code == code)
        .first()
    )
    if dup is not None:
        raise HTTPException(status_code=409, detail=f"Leave type code {code} already exists")
    dup_name = (
        db.query(LeaveType)
        .filter(
            LeaveType.company_id == company_id,
            func.lower(LeaveType.name) == name.strip().lower(),
        )
        .first()
    )
    if dup_name is not None:
        raise HTTPException(status_code=409, detail="Leave type name already exists")
    row = LeaveType(
        company_id=company_id,
        name=name.strip(),
        code=code,
        yearly_quota=yearly_quota,
        is_paid=is_paid,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="leave_type_create",
        entity_type="leave_type",
        entity_id=row.id,
        after=serialize(row),
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "name": row.name,
        "code": row.code,
        "yearly_quota": row.yearly_quota,
        "is_paid": row.is_paid,
    }


def update_leave_type(
    db: Session,
    company_id: int,
    user: User,
    item_id: int,
    data: dict[str, Any],
    fields_set: set[str] | None = None,
) -> dict:
    row = _get_leave_type(db, company_id, item_id)
    provided = fields_set if fields_set is not None else set(data)
    code = data.get("code")
    if code is not None and "code" in provided:
        code = str(code).strip().upper()
        dup = (
            db.query(LeaveType)
            .filter(
                LeaveType.company_id == company_id,
                LeaveType.code == code,
                LeaveType.id != item_id,
            )
            .first()
        )
        if dup is not None:
            raise HTTPException(
                status_code=409, detail=f"Leave type code {code} already exists"
            )
    else:
        code = None

    before = serialize(row)
    if "name" in provided and data.get("name"):
        row.name = str(data["name"]).strip()
    if code is not None:
        row.code = code
    if "yearly_quota" in provided:
        row.yearly_quota = data.get("yearly_quota")
    if "is_paid" in provided and data.get("is_paid") is not None:
        row.is_paid = bool(data["is_paid"])
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="leave_type_update",
        entity_type="leave_type",
        entity_id=item_id,
        before=before,
        after=serialize(row),
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "name": row.name,
        "code": row.code,
        "yearly_quota": row.yearly_quota,
        "is_paid": row.is_paid,
    }


def delete_leave_type(db: Session, company_id: int, user: User, item_id: int) -> None:
    row = _get_leave_type(db, company_id, item_id)
    used = (
        db.query(func.count(LeaveRequest.id))
        .filter(LeaveRequest.company_id == company_id, LeaveRequest.leave_type_id == item_id)
        .scalar()
        or 0
    )
    if used:
        raise HTTPException(
            status_code=409,
            detail=f"Leave type is referenced by {used} leave request(s)",
        )
    before = serialize(row)
    db.delete(row)
    record_audit(
        db,
        company_id=company_id,
        user=user,
        action="leave_type_delete",
        entity_type="leave_type",
        entity_id=item_id,
        before=before,
    )
    db.commit()
