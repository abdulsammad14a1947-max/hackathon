"""Per-user sliding-window rate limit for the AI assistant (brief guardrails).

Rule: at most ``settings.ai_rate_limit_per_hour`` chat requests (default 20) per
user in the last 60 minutes, counted over ``ai_logs.created_at`` — i.e. the log
table itself is the counter, so the limit survives restarts and cannot be
bypassed by dropping state.

Violation -> HTTP 429 ``{"detail": "Hourly AI limit reached. Try again later."}``.
"""
from __future__ import annotations

import datetime as dt

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AILog

WINDOW = dt.timedelta(hours=1)


def utc_now() -> dt.datetime:
    """Naive UTC now — matches SQLite/Postgres ``func.now()`` (UTC) storage."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def window_start() -> dt.datetime:
    return utc_now() - WINDOW


def requests_in_window(db: Session, user_id: int) -> int:
    return (
        db.query(AILog)
        .filter(AILog.user_id == user_id, AILog.created_at >= window_start())
        .count()
    )


def ensure_within_limit(db: Session, user_id: int) -> None:
    """Raise 429 when the user is at/over the hourly limit. Call BEFORE logging
    the current request (the current one must not count against itself)."""
    limit = get_settings().ai_rate_limit_per_hour
    if limit <= 0:  # 0/negative disables the endpoint entirely (documented)
        raise HTTPException(status_code=429, detail="Hourly AI limit reached. Try again later.")
    used = requests_in_window(db, user_id)
    if used >= limit:
        raise HTTPException(
            status_code=429, detail="Hourly AI limit reached. Try again later."
        )
