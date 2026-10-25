"""Request schemas for the attendance module (Pydantic v2, ARCHITECTURE §4)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CheckInRequest(BaseModel):
    """POST /api/attendance/check-in payload.

    ``extra="forbid"`` makes FastAPI answer **422** for ANY client-supplied
    timestamp field (``timestamp``, ``check_in``, ``time`` ...): check-in
    times are generated exclusively from the server clock (ARCHITECTURE §5).
    """

    model_config = ConfigDict(extra="forbid")

    lat: float | None = Field(default=None, description="WGS84 latitude")
    lng: float | None = Field(default=None, description="WGS84 longitude")
    accuracy_m: float | None = Field(default=None, ge=0, description="GPS accuracy in metres")

    @field_validator("lat")
    @classmethod
    def _valid_lat(cls, v: float | None) -> float | None:
        if v is not None and not -90.0 <= v <= 90.0:
            raise ValueError("lat must be between -90 and 90")
        return v

    @field_validator("lng")
    @classmethod
    def _valid_lng(cls, v: float | None) -> float | None:
        if v is not None and not -180.0 <= v <= 180.0:
            raise ValueError("lng must be between -180 and 180")
        return v

    @model_validator(mode="after")
    def _lat_lng_pair(self) -> "CheckInRequest":
        if (self.lat is None) != (self.lng is None):
            raise ValueError("lat and lng must be provided together")
        return self


class CheckOutRequest(BaseModel):
    """Optional body for POST /api/attendance/check-out (no parameters)."""

    model_config = ConfigDict(extra="forbid")


class CorrectionCreate(BaseModel):
    """POST /api/attendance/corrections — times may be clock times ("09:00")
    for ``attendance_date`` or full ISO datetimes; both are normalised to
    company-local time then stored as UTC by the service."""

    model_config = ConfigDict(extra="forbid")

    employee_id: int | None = None
    attendance_date: dt.date
    check_in: dt.time | dt.datetime | None = None
    check_out: dt.time | dt.datetime | None = None
    reason: str = Field(min_length=1, max_length=500)


class CorrectionDecision(BaseModel):
    """Body for correction approve/reject (``{comment?}``, may be omitted)."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=500)
