"""Audit logging helper — every important mutation should call record_audit()."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def _safe(value: Any) -> Any:
    """Make a value JSON-serialisable for audit storage."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return str(value)


def serialize(obj: Any) -> dict | None:
    """Convert a SQLAlchemy model / dict into a JSON-safe dict (id + columns)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return _safe(obj)
    if hasattr(obj, "__table__"):
        data: dict[str, Any] = {}
        for col in obj.__table__.columns:  # type: ignore[attr-defined]
            val = getattr(obj, col.name, None)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            data[col.name] = _safe(val)
        if data.get("password_hash"):
            data["password_hash"] = "***"
        return data
    return {"value": str(obj)}


def record_audit(
    db: Session,
    *,
    company_id: int,
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: Any = None,
    before: Any = None,
    after: Any = None,
    commit: bool = False,
) -> AuditLog:
    entry = AuditLog(
        company_id=company_id,
        actor_user_id=user.id if user else None,
        actor_email=user.email if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=serialize(before),
        after=serialize(after),
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def audit_entries_to_dicts(rows: list[AuditLog]) -> list[dict]:
    return [
        {
            "id": r.id,
            "actor_email": r.actor_email,
            "actor_user_id": r.actor_user_id,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "before": r.before,
            "after": r.after,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def dumps(value: Any) -> str:
    return json.dumps(_safe(value), default=str)
