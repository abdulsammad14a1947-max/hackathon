"""Chat orchestrator: rate limit -> provider -> ai_logs -> response envelope.

POST /api/ai/chat flow (ARCHITECTURE §4, brief Section 4 guardrails):

    ensure_within_limit (429) -> LLM mode? (key + not mock) : offline
      LLM attempt 1..2 (retry ONCE only for invalid structured output)
        ProviderError  -> fixed friendly reply, success=False, HTTP 200
        InvalidOutput  -> retry once, then offline provider
      offline provider -> deterministic rules/tools (always available)
    -> write ONE ai_logs row (user_id, role, prompt, summary, tools, success,
       provider, model, latency_ms) and commit -> response envelope.

The endpoint NEVER creates/updates/approves anything; smart leave only returns a
draft for the user's own confirmation form.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.ai import rate_limit
from app.ai.provider import (
    LLMOutcome,
    OfflineOutcome,
    PROVIDER_FALLBACK_REPLY,
    InvalidOutputError,
    ProviderError,
    llm_chat,
    llm_enabled,
    offline_reply,
)
from app.core.config import get_settings
from app.models import AILog, User

MAX_LLM_ATTEMPTS = 2  # invalid structured output: retry the whole call ONCE


def run_chat(
    db: Session,
    user: User,
    message: str,
    conversation_id: str | None = None,
    kpi: dict[str, Any] | None = None,
) -> dict:
    rate_limit.ensure_within_limit(db, user.id)

    conversation_id = conversation_id or uuid.uuid4().hex
    started = time.perf_counter()

    provider = "offline"
    model = "offline-rules"
    success = True
    reply: str | None = None
    tool_calls: list[dict] = []
    smart_leave: dict | None = None
    requires_confirmation = False

    if llm_enabled():
        outcome: LLMOutcome | None = None
        for attempt in range(MAX_LLM_ATTEMPTS):
            try:
                outcome = llm_chat(db, user, message)
                break
            except ProviderError:
                reply = PROVIDER_FALLBACK_REPLY
                success = False
                break
            except InvalidOutputError:
                if attempt == MAX_LLM_ATTEMPTS - 1:
                    break  # retried once -> fall through to the offline provider
                continue
        if outcome is not None:
            provider = "llm"
            model = outcome.model or get_settings().ai_model
            reply = outcome.reply
            tool_calls = outcome.tool_calls
            smart_leave = outcome.smart_leave
            requires_confirmation = outcome.requires_confirmation

    if reply is None:
        offline: OfflineOutcome = offline_reply(db, user, message, kpi)
        provider = "offline"
        model = "offline-rules"
        reply = offline.reply
        tool_calls = offline.tool_calls
        smart_leave = offline.smart_leave
        requires_confirmation = offline.requires_confirmation

    latency_ms = int((time.perf_counter() - started) * 1000)
    log = AILog(
        company_id=user.company_id,
        user_id=user.id,
        role=user.role,
        prompt=message[:2000],
        summary=(reply or "")[:500],
        tools=tool_calls,
        success=success,
        provider=provider,
        model=model,
        latency_ms=latency_ms,
    )
    db.add(log)
    db.commit()

    response: dict[str, Any] = {
        "reply": reply,
        "label": "AI-generated",
        "provider": provider,
        "tool_calls": tool_calls,
        "requires_confirmation": requires_confirmation,
        "conversation_id": conversation_id,
    }
    if smart_leave is not None:
        response["smart_leave"] = smart_leave
    return response
