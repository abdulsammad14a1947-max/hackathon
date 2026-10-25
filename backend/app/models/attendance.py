"""Attendance and correction models."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, Float, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.utils.timestamps import TimestampMixin


class Attendance(Base, TimestampMixin):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("employee_id", "date", name="uq_attendance_emp_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    check_in: Mapped[dt.datetime | None] = mapped_column(DateTime)
    check_out: Mapped[dt.datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="present")
    worked_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    check_in_lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    check_in_lng: Mapped[float | None] = mapped_column(Numeric(9, 6))
    # How this day record was created: manual UI punch vs camera face check-in
    # (server default 'manual' covers pre-existing rows; M10).
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")


class AttendanceCorrection(Base, TimestampMixin):
    __tablename__ = "attendance_corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attendance_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    requested_check_in: Mapped[dt.datetime | None] = mapped_column(DateTime)
    requested_check_out: Mapped[dt.datetime | None] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    review_comment: Mapped[str | None] = mapped_column(String(500))
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, name="requested_by"
    )
