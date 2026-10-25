"""Leave endpoints (ARCHITECTURE §4): types, requests, balance, decisions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_hr, require_roles
from app.models import Employee, LeaveType, User
from app.permissions.access import ensure_staff
from app.schemas.leave import LeaveDecision, LeaveRequestCreate
from app.services import leave_service

router = APIRouter(prefix="/api/leave", tags=["leave"])


@router.get("/types")
def list_leave_types(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """All leave types of the caller's company (every role)."""
    rows = (
        db.query(LeaveType)
        .filter(LeaveType.company_id == user.company_id)
        .order_by(LeaveType.id)
        .all()
    )
    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "yearly_quota": r.yearly_quota,
            "is_paid": bool(r.is_paid),
        }
        for r in rows
    ]


@router.post("/requests", status_code=201)
def create_request(
    payload: LeaveRequestCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Own request; invalid range -> 422, unknown type -> 422, overlap -> 409,
    insufficient balance -> 422 (detail shows quota/used/requested)."""
    return leave_service.create_request(db, user=user, payload=payload)


@router.get("/requests")
def list_requests(
    scope: str = Query(default="me"),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """``scope=all`` requires HR/Admin (403 for employees); ``scope=me`` -> own."""
    if scope == "all":
        ensure_staff(user)  # employees -> 403
        employee_id = None
    elif scope == "me":
        employee_id = user.employee_id
        if employee_id is None:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
    else:
        raise HTTPException(status_code=422, detail="scope must be 'me' or 'all'")
    return leave_service.list_requests(
        db,
        user.company_id,
        employee_id=employee_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/balance")
def balance(
    year: int | None = Query(default=None, ge=2000, le=2100),
    employee_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Own balance by default; HR/Admin may pass ``employee_id`` — anyone
    requesting another employee's balance without a staff role -> 403."""
    if employee_id is not None and employee_id != user.employee_id:
        if user.role not in ("admin", "hr"):
            raise HTTPException(
                status_code=403, detail="Access denied to other employee balance"
            )
        target = db.get(Employee, employee_id)
        if target is None or target.company_id != user.company_id:
            raise HTTPException(status_code=404, detail="Employee not found")
        target_id = employee_id
    else:
        target_id = user.employee_id
    year = year or leave_service.balance_year_default(db, user.company_id)
    return leave_service.get_balance(db, user.company_id, target_id, year)


@router.post("/requests/{request_id}/cancel")
def cancel_request(
    request_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Owner only, pending only (403 / 409)."""
    return leave_service.cancel_request(db, user=user, request_id=request_id)


@router.post("/requests/{request_id}/approve")
def approve_request(
    request_id: int,
    payload: LeaveDecision | None = None,
    user: User = Depends(require_roles("hr")),  # brief matrix #13: Admin View, HR Approve
    db: Session = Depends(get_db),
):
    """HR only (Admin gets 403); approving your OWN request -> 403; audited + notified."""
    return leave_service.decide(
        db,
        user=user,
        request_id=request_id,
        decision="approved",
        comment=payload.comment if payload else None,
    )


@router.post("/requests/{request_id}/reject")
def reject_request(
    request_id: int,
    payload: LeaveDecision | None = None,
    user: User = Depends(require_roles("hr")),  # brief matrix #13: Admin View, HR Approve
    db: Session = Depends(get_db),
):
    return leave_service.decide(
        db,
        user=user,
        request_id=request_id,
        decision="rejected",
        comment=payload.comment if payload else None,
    )
