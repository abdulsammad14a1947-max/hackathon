"""Permission helpers shared by services (pure functions, unit-testable)."""
from __future__ import annotations

from fastapi import HTTPException, status

from app.models import User


def ensure_not_self_approval(user: User, target_employee_id: int | None, entity: str = "request") -> None:
    """HR/Admin must not approve their own {entity}."""
    if user.employee_id is not None and target_employee_id == user.employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You cannot approve your own {entity}",
        )


def ensure_self_or_staff(user: User, employee_id: int, what: str = "record") -> None:
    """Employees may only touch their own records; HR/Admin may touch any."""
    if user.role == "employee":
        if user.employee_id is None or user.employee_id != employee_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to other employee {what}",
            )


def ensure_staff(user: User) -> None:
    if user.role not in ("admin", "hr"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Staff access required"
        )
