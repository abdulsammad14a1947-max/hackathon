"""Payroll models: salary structures, payroll runs and items (payslips)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.utils.timestamps import TimestampMixin


class SalaryStructure(Base, TimestampMixin):
    __tablename__ = "salary_structures"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    basic_salary: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    effective_from: Mapped[dt.date] = mapped_column(Date, nullable=False, default=dt.date.today)
    effective_to: Mapped[dt.date | None] = mapped_column(Date)


class PayrollRun(Base, TimestampMixin):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "period_year", "period_month", name="uq_payroll_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..12
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    generated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    generated_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    finalized_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    finalized_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    total_gross: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_deductions: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    total_net: Mapped[float] = mapped_column(Numeric(14, 2), default=0, nullable=False)

    items: Mapped[list["PayrollItem"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class PayrollItem(Base, TimestampMixin):
    __tablename__ = "payroll_items"
    __table_args__ = (UniqueConstraint("run_id", "employee_id", name="uq_payroll_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    basic: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    hra: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    medical: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    gross: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    working_days: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    present_days: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    absent_days: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    unpaid_leave_days: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    half_days: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    deduction_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    net_pay: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    note: Mapped[str | None] = mapped_column(String(300))

    run: Mapped[PayrollRun] = relationship(back_populates="items")
