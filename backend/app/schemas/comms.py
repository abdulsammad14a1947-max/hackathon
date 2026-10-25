"""Pydantic schemas for communications + audit endpoints (M9)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- announcements
class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=4000)


class AnnouncementOut(BaseModel):
    id: int
    title: str
    body: str
    audience: str = "all"
    created_by: int | None = None
    created_by_name: str | None = None
    created_at: dt.datetime | None = None


class AnnouncementPage(BaseModel):
    items: list[AnnouncementOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------- notifications
class NotificationOut(BaseModel):
    id: int
    title: str
    body: str | None = None
    link: str | None = None
    is_read: bool = False
    created_at: dt.datetime | None = None


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int


class MarkReadRequest(BaseModel):
    ids: list[int] = Field(..., max_length=500)


class MarkReadResponse(BaseModel):
    updated: int


# ---------------------------------------------------------------- audit logs
class AuditLogOut(BaseModel):
    id: int
    actor: str | None = None
    actor_email: str | None = None
    actor_user_id: int | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    before: dict | list | None = None
    after: dict | list | None = None
    created_at: dt.datetime | None = None


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int
