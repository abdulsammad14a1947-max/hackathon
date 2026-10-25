"""Request schemas for the leave module (Pydantic v2, ARCHITECTURE §4)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LeaveRequestCreate(BaseModel):
    """POST /api/leave/requests body. Invalid ranges are rejected here with 422."""

    model_config = ConfigDict(extra="forbid")

    leave_type_code: str = Field(min_length=1, max_length=20)
    start_date: dt.date
    end_date: dt.date
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _valid_range(self) -> "LeaveRequestCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class LeaveDecision(BaseModel):
    """Body for approve/reject (``{comment?}``, may be omitted)."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=500)
