"""Company, settings, organization structure and leave-type models."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.db import Base
from app.utils.timestamps import TimestampMixin


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(400))
    phone: Mapped[str | None] = mapped_column(String(50))

    settings: Mapped["CompanySettings | None"] = relationship(
        back_populates="company", uselist=False, cascade="all, delete-orphan"
    )


class CompanySettings(Base, TimestampMixin):
    __tablename__ = "company_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    office_start_time: Mapped[dt.time] = mapped_column(Time, default=dt.time(9, 0), nullable=False)
    grace_period_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    weekend_days: Mapped[list] = mapped_column(
        JSON, default=lambda: ["Saturday", "Sunday"], nullable=False
    )
    office_lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    office_lng: Mapped[float | None] = mapped_column(Numeric(9, 6))
    geofence_radius_m: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    timezone: Mapped[str] = mapped_column(String(60), default="Asia/Karachi", nullable=False)
    half_day_threshold_hours: Mapped[float] = mapped_column(default=5.0, nullable=False)

    company: Mapped[Company] = relationship(back_populates="settings")


class Department(Base, TimestampMixin):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_department_company_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class Designation(Base, TimestampMixin):
    __tablename__ = "designations"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_designation_company_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class LeaveType(Base, TimestampMixin):
    __tablename__ = "leave_types"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_leavetype_company_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)  # ANNUAL|SICK|CASUAL|UNPAID
    yearly_quota: Mapped[int | None] = mapped_column(Integer)  # None = unlimited
    is_paid: Mapped[bool] = mapped_column(default=True, nullable=False)


class Holiday(Base, TimestampMixin):
    __tablename__ = "holidays"
    __table_args__ = (UniqueConstraint("company_id", "date", name="uq_holiday_company_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
