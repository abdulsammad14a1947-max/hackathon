"""Leave service: balances and request lifecycle (frozen contracts §5b).

Balance rule (§5): ``quota − approved working_days this year``; unpaid (quota
null) is unlimited. Overlap check spans pending + approved requests.
"""
from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Employee, LeaveRequest, LeaveType, User
from app.permissions.access import ensure_not_self_approval
from app.services.attendance_service import local_today, utc_now
from app.services.calendar_utils import count_working_days, get_settings
from app.services.notifications import notify_employee, notify_role
from app.utils.audit import record_audit, serialize

REQUESTABLE_STATUSES = ("pending", "approved", "rejected", "cancelled")


def _full_name(first: str, last: str | None) -> str:
    return f"{first} {last or ''}".strip()


def _approved_used(
    db: Session, company_id: int, employee_id: int, leave_type_id: int, year: int
) -> float:
    rows = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.company_id == company_id,
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.leave_type_id == leave_type_id,
            LeaveRequest.status == "approved",
            LeaveRequest.start_date >= dt.date(year, 1, 1),
            LeaveRequest.start_date <= dt.date(year, 12, 31),
        )
        .all()
    )
    return round(sum(float(r.working_days or 0.0) for r in rows), 2)


# --------------------------------------------------------------------------- #
# Frozen contract: get_balance (ARCHITECTURE §5b)
# --------------------------------------------------------------------------- #
def get_balance(db, company_id, employee_id, year: int) -> dict:
    """-> {"year", "items":[{"code","name","quota","used","pending","remaining","is_paid"}]}

    ``quota=None`` means unlimited => ``remaining=None``. ``employee_id`` may be
    ``None`` (e.g. an admin without an employee profile) and yields zero usage.
    """
    types = (
        db.query(LeaveType)
        .filter(LeaveType.company_id == company_id)
        .order_by(LeaveType.id)
        .all()
    )
    used: dict[int, float] = {}
    pending: dict[int, float] = {}
    if employee_id is not None:
        rows = (
            db.query(LeaveRequest)
            .filter(
                LeaveRequest.company_id == company_id,
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.start_date >= dt.date(year, 1, 1),
                LeaveRequest.start_date <= dt.date(year, 12, 31),
                LeaveRequest.status.in_(("approved", "pending")),
            )
            .all()
        )
        for row in rows:
            bucket = used if row.status == "approved" else pending
            bucket[row.leave_type_id] = round(
                bucket.get(row.leave_type_id, 0.0) + float(row.working_days or 0.0), 2
            )

    items = []
    for lt in types:
        u = used.get(lt.id, 0.0)
        quota = lt.yearly_quota
        remaining = None if quota is None else round(max(float(quota) - u, 0.0), 2)
        items.append(
            {
                "code": lt.code,
                "name": lt.name,
                "quota": quota,
                "used": u,
                "pending": pending.get(lt.id, 0.0),
                "remaining": remaining,
                "is_paid": bool(lt.is_paid),
            }
        )
    return {"year": year, "items": items}


# --------------------------------------------------------------------------- #
# Frozen contract: list_requests (ARCHITECTURE §5b)
# --------------------------------------------------------------------------- #
def _row_to_item(
    req: LeaveRequest, first: str, last: str | None, emp_code: str, code: str, lt_name: str
) -> dict:
    return {
        "id": req.id,
        "employee_id": req.employee_id,
        "employee_name": _full_name(first, last),
        "employee_code": emp_code,
        "leave_type_id": req.leave_type_id,
        "leave_type_code": code,
        "leave_type_name": lt_name,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "working_days": float(req.working_days or 0.0),
        "reason": req.reason,
        "status": req.status,
        "reviewed_by": req.reviewed_by,
        # reviewed_at/created_at are serialised as naive-UTC ISO strings.
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
        "review_comment": req.review_comment,
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }


def list_requests(
    db, company_id, employee_id=None, status=None, page=1, page_size=20
) -> dict:
    """-> {"items","total","page","page_size"} with employee + leave-type names."""
    page = max(int(page), 1)
    page_size = max(1, min(int(page_size), 200))
    q = (
        db.query(
            LeaveRequest,
            Employee.first_name,
            Employee.last_name,
            Employee.employee_code,
            LeaveType.code,
            LeaveType.name,
        )
        .join(Employee, Employee.id == LeaveRequest.employee_id)
        .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
        .filter(LeaveRequest.company_id == company_id)
    )
    if employee_id is not None:
        q = q.filter(LeaveRequest.employee_id == employee_id)
    if status:
        q = q.filter(LeaveRequest.status == status)
    total = q.count()
    rows = (
        q.order_by(LeaveRequest.start_date.desc(), LeaveRequest.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        _row_to_item(req, first, last, emp_code, code, lt_name)
        for req, first, last, emp_code, code, lt_name in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def to_dict(db: Session, req: LeaveRequest) -> dict:
    emp = db.get(Employee, req.employee_id)
    lt = db.get(LeaveType, req.leave_type_id)
    return _row_to_item(
        req,
        emp.first_name if emp else "",
        emp.last_name if emp else None,
        emp.employee_code if emp else "",
        lt.code if lt else "",
        lt.name if lt else "",
    )


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def _own_employee(db: Session, user: User) -> Employee:
    if user.employee_id is None:
        raise HTTPException(status_code=403, detail="No employee profile")
    emp = db.get(Employee, user.employee_id)
    if emp is None or emp.company_id != user.company_id:
        raise HTTPException(status_code=403, detail="No employee profile")
    return emp


def create_request(db: Session, *, user: User, payload) -> dict:
    emp = _own_employee(db, user)
    code = payload.leave_type_code.strip().upper()
    leave_type = (
        db.query(LeaveType)
        .filter(LeaveType.company_id == user.company_id, LeaveType.code == code)
        .first()
    )
    if leave_type is None:
        raise HTTPException(
            status_code=422, detail=f"Unknown leave type code: {payload.leave_type_code}"
        )

    # Overlap with pending/approved requests of the same employee -> 409.
    overlap = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.company_id == user.company_id,
            LeaveRequest.employee_id == emp.id,
            LeaveRequest.status.in_(("pending", "approved")),
            LeaveRequest.start_date <= payload.end_date,
            LeaveRequest.end_date >= payload.start_date,
        )
        .first()
    )
    if overlap is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Overlapping {overlap.status} leave request #{overlap.id} "
                f"({overlap.start_date.isoformat()} to {overlap.end_date.isoformat()})"
            ),
        )

    # Working days exclude weekends + holidays (frozen calendar_utils).
    working_days = count_working_days(
        db, user.company_id, payload.start_date, payload.end_date
    )

    if leave_type.yearly_quota is not None:
        used = _approved_used(
            db, user.company_id, emp.id, leave_type.id, payload.start_date.year
        )
        remaining = float(leave_type.yearly_quota) - used
        if working_days > remaining:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Insufficient {leave_type.code} balance: "
                    f"quota={leave_type.yearly_quota}, used={used}, "
                    f"requested={working_days}"
                ),
            )

    req = LeaveRequest(
        company_id=user.company_id,
        employee_id=emp.id,
        leave_type_id=leave_type.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        working_days=working_days,
        reason=payload.reason,
        status="pending",
    )
    db.add(req)
    db.flush()
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="leave.requested",
        entity_type="leave_request",
        entity_id=req.id,
        after=serialize(req),
    )
    notify_role(
        db,
        company_id=user.company_id,
        role="hr",
        title="New leave request",
        body=(
            f"{_full_name(emp.first_name, emp.last_name)} requested {leave_type.code} "
            f"leave ({payload.start_date.isoformat()} to {payload.end_date.isoformat()})"
        ),
        link="/leave",
    )
    db.commit()
    db.refresh(req)
    return to_dict(db, req)


def _get_request(db: Session, user: User, request_id: int) -> LeaveRequest:
    req = db.get(LeaveRequest, request_id)
    if req is None or req.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return req


def cancel_request(db: Session, *, user: User, request_id: int) -> dict:
    """Owner only, pending only (403 / 409)."""
    req = _get_request(db, user, request_id)
    if user.employee_id is None or user.employee_id != req.employee_id:
        raise HTTPException(
            status_code=403, detail="You can only cancel your own leave request"
        )
    if req.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Only pending requests can be cancelled (current: {req.status})",
        )
    before = serialize(req)
    req.status = "cancelled"
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="leave.cancelled",
        entity_type="leave_request",
        entity_id=req.id,
        before=before,
        after=serialize(req),
    )
    notify_role(
        db,
        company_id=user.company_id,
        role="hr",
        title="Leave request cancelled",
        body=f"Leave request #{req.id} was cancelled by the employee.",
        link="/leave",
    )
    db.commit()
    db.refresh(req)
    return to_dict(db, req)


def decide(
    db: Session, *, user: User, request_id: int, decision: str, comment: str | None
) -> dict:
    """HR/Admin approve/reject. Self-approval of own request -> 403 (§5)."""
    req = _get_request(db, user, request_id)
    ensure_not_self_approval(user, req.employee_id, "leave request")
    if req.status != "pending":
        raise HTTPException(
            status_code=409, detail=f"Request already {req.status}"
        )
    before = serialize(req)
    req.status = decision  # "approved" | "rejected"
    req.reviewed_by = user.id
    req.reviewed_at = utc_now()
    req.review_comment = comment
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action=f"leave.{decision}",
        entity_type="leave_request",
        entity_id=req.id,
        before=before,
        after=serialize(req),
    )
    notify_employee(
        db,
        employee_id=req.employee_id,
        title=f"Leave request {decision}",
        body=(
            f"Your leave {req.start_date.isoformat()} to {req.end_date.isoformat()} "
            f"was {decision}."
        ),
        link="/leave",
    )
    db.commit()
    db.refresh(req)
    return to_dict(db, req)


def balance_year_default(db: Session, company_id: int) -> int:
    settings = get_settings(db, company_id)
    return local_today(settings).year
