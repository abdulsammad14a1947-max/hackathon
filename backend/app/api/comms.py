"""Communications & audit endpoints (M9) — see ARCHITECTURE §4 "Comms & audit".

GET    /api/announcements               all roles, own company, newest first
POST   /api/announcements               HR + Admin (audit + notify every employee)
DELETE /api/announcements/{id}          Admin OR the author, else 403 (audit-logged)
GET    /api/notifications               own inbox (?unread=true)
GET    /api/notifications/unread-count  own unread count
POST   /api/notifications/read          {ids: []} — only the caller's own rows
GET    /api/audit-logs                  Admin only (HR/Employee → 403)

NOTE: audit_logs are immutable — this module exposes ONLY a read endpoint for
them (verified: no POST/PATCH/PUT/DELETE route touches audit_logs anywhere in
the files owned by this agent).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin, require_hr
from app.models import Announcement, AuditLog, Notification, User
from app.schemas.comms import (
    AnnouncementCreate,
    AnnouncementOut,
    AnnouncementPage,
    AuditLogOut,
    AuditLogPage,
    MarkReadRequest,
    MarkReadResponse,
    NotificationOut,
    NotificationPage,
)
from app.services.notifications import notify_role
from app.utils.audit import record_audit, serialize as audit_serialize

router = APIRouter(tags=["comms"])


def _announcement_out(row: Announcement, author_name: str | None) -> AnnouncementOut:
    return AnnouncementOut(
        id=row.id,
        title=row.title,
        body=row.body,
        audience=row.audience,
        created_by=row.created_by,
        created_by_name=author_name,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------- announcements
@router.get(
    "/api/announcements",
    response_model=AnnouncementPage,
    summary="List announcements (all roles, own company)",
)
def list_announcements(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnnouncementPage:
    q = db.query(Announcement).filter(Announcement.company_id == user.company_id)
    total = q.count()
    rows = (
        q.order_by(Announcement.created_at.desc(), Announcement.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    author_ids = {r.created_by for r in rows if r.created_by is not None}
    authors = (
        db.query(User).filter(User.id.in_(author_ids)).all() if author_ids else []
    )
    names = {u.id: u.full_name for u in authors}
    items = [_announcement_out(r, names.get(r.created_by)) for r in rows]
    return AnnouncementPage(items=items, total=total, page=page, page_size=page_size)


@router.post(
    "/api/announcements",
    response_model=AnnouncementOut,
    status_code=201,
    summary="Post an announcement (HR + Admin)",
)
def create_announcement(
    payload: AnnouncementCreate,
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
) -> AnnouncementOut:
    row = Announcement(
        company_id=user.company_id,
        title=payload.title,
        body=payload.body,
        audience="all",
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="announcement.created",
        entity_type="announcement",
        entity_id=row.id,
        after=audit_serialize(row),
    )
    notify_role(
        db,
        company_id=user.company_id,
        role="employee",
        title=row.title,
        body=row.body[:900],
        link="/announcements",
    )
    db.commit()
    db.refresh(row)
    return _announcement_out(row, user.full_name)


@router.delete(
    "/api/announcements/{announcement_id}",
    status_code=204,
    summary="Delete an announcement (Admin or its author)",
)
def delete_announcement(
    announcement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    row = db.get(Announcement, announcement_id)
    if row is None or row.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Announcement not found")
    if user.role != "admin" and row.created_by != user.id:
        raise HTTPException(status_code=403, detail="Only Admin or the author may delete")
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="announcement.deleted",
        entity_type="announcement",
        entity_id=row.id,
        before=audit_serialize(row),
    )
    db.delete(row)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- notifications
def _unread_count(db: Session, user_id: int) -> int:
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read.is_(False))
        .count()
    )


@router.get(
    "/api/notifications",
    response_model=NotificationPage,
    summary="My notifications (newest first)",
)
def list_notifications(
    unread: bool = Query(default=False, description="Return only unread items"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPage:
    q = db.query(Notification).filter(Notification.user_id == user.id)
    total = q.count()
    rows = q.order_by(Notification.created_at.desc(), Notification.id.desc())
    if unread:
        rows = rows.filter(Notification.is_read.is_(False))
    items = rows.offset((page - 1) * page_size).limit(page_size).all()
    return NotificationPage(
        items=[
            NotificationOut(
                id=r.id,
                title=r.title,
                body=r.body,
                link=r.link,
                is_read=r.is_read,
                created_at=r.created_at,
            )
            for r in items
        ],
        total=total,
        unread=_unread_count(db, user.id),
    )


@router.get(
    "/api/notifications/unread-count",
    summary="My unread notification count",
)
def unread_count(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return {"count": _unread_count(db, user.id)}


@router.post(
    "/api/notifications/read",
    response_model=MarkReadResponse,
    summary="Mark my notifications as read (only own ids are honoured)",
)
def mark_notifications_read(
    payload: MarkReadRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MarkReadResponse:
    ids = list(dict.fromkeys(payload.ids))  # de-duplicate, keep order
    updated = 0
    if ids:
        rows = (
            db.query(Notification)
            .filter(
                Notification.user_id == user.id,  # scope: own rows only
                Notification.id.in_(ids),
                Notification.is_read.is_(False),
            )
            .all()
        )
        for row in rows:
            row.is_read = True
            updated += 1
        db.commit()
    return MarkReadResponse(updated=updated)


# ---------------------------------------------------------------- audit logs (read-only)
@router.get(
    "/api/audit-logs",
    response_model=AuditLogPage,
    summary="Audit log (Admin only; immutable — read-only endpoint)",
)
def list_audit_logs(
    action: str | None = Query(default=None, description="Exact action filter"),
    entity_type: str | None = Query(default=None, description="Exact entity type filter"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuditLogPage:
    q = db.query(AuditLog).filter(AuditLog.company_id == user.company_id)
    if action:
        q = q.filter(AuditLog.action == action)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    total = q.count()
    rows = (
        q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [
        AuditLogOut(
            id=r.id,
            actor=r.actor_email,
            actor_email=r.actor_email,
            actor_user_id=r.actor_user_id,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            before=r.before,
            after=r.after,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return AuditLogPage(items=items, total=total, page=page, page_size=page_size)
