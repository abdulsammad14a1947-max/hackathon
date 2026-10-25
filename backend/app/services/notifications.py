"""In-app notifications helper — shared by leave, payroll, announcements."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Notification, User


def notify_user(
    db: Session,
    *,
    company_id: int,
    user_id: int,
    title: str,
    body: str | None = None,
    link: str | None = None,
    commit: bool = False,
) -> Notification:
    note = Notification(
        company_id=company_id,
        user_id=user_id,
        title=title,
        body=body,
        link=link,
    )
    db.add(note)
    if commit:
        db.commit()
    return note


def notify_role(
    db: Session,
    *,
    company_id: int,
    role: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> list[Notification]:
    """Notify every active user with the given role (e.g. HR inbox of new requests)."""
    users = (
        db.query(User)
        .filter(
            User.company_id == company_id,
            User.role == role,
            User.is_active.is_(True),
        )
        .all()
    )
    return [
        notify_user(
            db, company_id=company_id, user_id=u.id, title=title, body=body, link=link
        )
        for u in users
    ]


def notify_employee(
    db: Session,
    *,
    employee_id: int,
    title: str,
    body: str | None = None,
    link: str | None = None,
) -> Notification | None:
    """Notify the login user linked to an employee (if any)."""
    user = db.query(User).filter(User.employee_id == employee_id).first()
    if user is None:
        return None
    return notify_user(
        db,
        company_id=user.company_id,
        user_id=user.id,
        title=title,
        body=body,
        link=link,
    )
