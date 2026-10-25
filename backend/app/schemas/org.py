"""Org settings / structure schemas (departments, designations, holidays, leave types)."""
from __future__ import annotations

import datetime as dt
import re

from pydantic import BaseModel, Field, field_validator

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$")
_TZ_RE = re.compile(r"^[A-Za-z0-9_+\-]+/[A-Za-z0-9_+\-]+$")


class SettingsOut(BaseModel):
    office_start_time: str  # "HH:MM"
    grace_period_minutes: int
    weekend_days: list[str]
    office_lat: float | None = None
    office_lng: float | None = None
    geofence_radius_m: int
    timezone: str
    half_day_threshold_hours: float


class SettingsPatch(BaseModel):
    office_start_time: str | None = None
    grace_period_minutes: int | None = Field(default=None, ge=0, le=1440)
    weekend_days: list[str] | None = None
    office_lat: float | None = None
    office_lng: float | None = None
    geofence_radius_m: int | None = Field(default=None, gt=0, le=100_000)
    timezone: str | None = None
    half_day_threshold_hours: float | None = Field(default=None, gt=0, le=24)

    @field_validator("office_start_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _TIME_RE.match(v.strip()):
            raise ValueError("office_start_time must be HH:MM (or HH:MM:SS), e.g. 09:00")
        return v.strip()

    @field_validator("weekend_days")
    @classmethod
    def _check_weekends(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if len(set(v)) != len(v):
            raise ValueError("weekend_days contains duplicates")
        for day in v:
            if day not in (
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ):
                raise ValueError(f"Invalid weekend day: {day!r}")
        return v

    @field_validator("timezone")
    @classmethod
    def _check_tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _TZ_RE.match(v.strip()):
            raise ValueError("timezone must be an IANA name like 'Asia/Karachi'")
        return v.strip()


class DepartmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class DepartmentOut(BaseModel):
    id: int
    name: str
    employee_count: int = 0


class DesignationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class DesignationOut(BaseModel):
    id: int
    name: str
    employee_count: int = 0


class HolidayIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    date: dt.date


class HolidayOut(BaseModel):
    id: int
    name: str
    date: str


class LeaveTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    code: str = Field(min_length=1, max_length=20)
    yearly_quota: int | None = Field(default=None, ge=0, le=365)
    is_paid: bool = True

    @field_validator("code")
    @classmethod
    def _upper_code(cls, v: str) -> str:
        return v.strip().upper()


class LeaveTypePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    code: str | None = Field(default=None, min_length=1, max_length=20)
    yearly_quota: int | None = Field(default=None, ge=0, le=365)
    is_paid: bool | None = None

    @field_validator("code")
    @classmethod
    def _upper_code(cls, v: str | None) -> str | None:
        return v.strip().upper() if v is not None else v


class LeaveTypeOut(BaseModel):
    id: int
    name: str
    code: str
    yearly_quota: int | None = None
    is_paid: bool
