"""AI Assistant endpoint (M8) — POST /api/ai/chat (ARCHITECTURE §4).

Guardrails implemented here / in app/ai/*:
* JWT required (get_current_user, including the mandatory-password-change gate).
* ~20 requests/user/hour -> 429 (app/ai/rate_limit.py).
* 15 s provider timeout + friendly fallback, never a 500 (app/ai/provider.py).
* Every call logged to ai_logs and answered with label "AI-generated".
* The assistant never creates/updates/approves anything; `smart_leave` is only a
  draft for the user to review and submit via POST /api/leave/requests.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ai.chat import run_chat
from app.core.db import get_db
from app.core.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/api/ai", tags=["ai"])


class ChatRequest(BaseModel):
    """POST /api/ai/chat body (extra fields ignored for forward compatibility)."""

    model_config = ConfigDict(extra="ignore")

    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)
    kpi: dict[str, Any] | None = Field(
        default=None,
        description="Dashboard KPI JSON for the current filters (Summarize feature)",
    )


@router.post(
    "/chat",
    summary="Chat with the AI assistant (all roles, role-scoped tools)",
)
def chat(
    payload: ChatRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Returns {reply, label, provider, tool_calls, smart_leave?, requires_confirmation,
    conversation_id}. Rate limited (~20/user/hour -> 429); provider failures answer
    with a friendly fallback instead of an error status."""
    return run_chat(
        db,
        user,
        payload.message,
        conversation_id=payload.conversation_id,
        kpi=payload.kpi,
    )
