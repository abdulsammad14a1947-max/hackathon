"""Attendance endpoints (ARCHITECTURE §4): check-in/out, month view, day
roster and correction workflow."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_hr, require_roles
from app.models import User
from app.permissions.access import ensure_staff
from app.schemas.attendance import (
    CheckInRequest,
    CheckOutRequest,
    CorrectionCreate,
    CorrectionDecision,
)
from app.services import attendance_service
from app.services.calendar_utils import get_settings

router = APIRouter(prefix="/api/attendance", tags=["attendance"])


@router.post("/check-in", status_code=201)
def check_in(
    payload: CheckInRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Server-timestamped check-in; duplicate today -> 409; bad GPS -> 422.
    Any client-supplied timestamp field is rejected with 422 (extra="forbid")."""
    return attendance_service.check_in(db, user=user, payload=payload)


@router.post("/check-out", status_code=200)
def check_out(
    payload: CheckOutRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Server-timestamped check-out; not checked in / already out -> 409."""
    return attendance_service.check_out(db, user=user)


@router.get("/me")
def my_month(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Own month records + summary. ``missing_checkout`` is a per-day computed
    flag (display only) — see attendance_service._record_dict."""
    return attendance_service.month_view(db, user=user, year=year, month=month)


@router.get("/board")
def board(
    date: dt.date | None = Query(default=None),
    department_id: int | None = Query(default=None),
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
):
    """HR/Admin day roster: every active employee with a status
    present|late|half_day|absent|on_leave|weekend|off|scheduled."""
    settings = get_settings(db, user.company_id)
    day = date or attendance_service.local_today(settings)
    return attendance_service.board(
        db, company_id=user.company_id, day=day, department_id=department_id
    )


@router.post("/corrections", status_code=201)
def create_correction(
    payload: CorrectionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Employee (own) or HR/Admin (any employee_id) -> pending correction."""
    return attendance_service.create_correction(db, user=user, payload=payload)


@router.get("/corrections")
def list_corrections(
    scope: str = Query(default="me"),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """``scope=all`` -> HR/Admin only (403 for employees); ``scope=me`` -> own."""
    if scope == "all":
        ensure_staff(user)  # employees -> 403
        employee_id = None
    elif scope == "me":
        employee_id = user.employee_id
        if employee_id is None:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
    else:
        raise HTTPException(status_code=422, detail="scope must be 'me' or 'all'")
    return attendance_service.list_corrections(
        db,
        company_id=user.company_id,
        employee_id=employee_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.post("/corrections/{correction_id}/approve")
def approve_correction(
    correction_id: int,
    payload: CorrectionDecision | None = None,
    user: User = Depends(require_roles("hr")),  # brief matrix #11: Admin View, HR Approve
    db: Session = Depends(get_db),
):
    """HR only (Admin gets 403) applies requested times (creating the day record if missing);
    self-approval of own correction -> 403; audited + notifies the employee."""
    return attendance_service.approve_correction(
        db,
        user=user,
        correction_id=correction_id,
        comment=payload.comment if payload else None,
    )


@router.post("/corrections/{correction_id}/reject")
def reject_correction(
    correction_id: int,
    payload: CorrectionDecision | None = None,
    user: User = Depends(require_roles("hr")),  # brief matrix #11: Admin View, HR Approve
    db: Session = Depends(get_db),
):
    return attendance_service.reject_correction(
        db,
        user=user,
        correction_id=correction_id,
        comment=payload.comment if payload else None,
    )
