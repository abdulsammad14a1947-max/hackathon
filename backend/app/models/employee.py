"""User (login credential) and Employee (directory record) models."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.utils.timestamps import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="employee")
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(default=False, nullable=False)

    employee: Mapped["Employee | None"] = relationship(back_populates="user", uselist=False)


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"
    __table_args__ = (UniqueConstraint("company_id", "employee_code", name="uq_emp_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_code: Mapped[str] = mapped_column(String(40), nullable=False)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(String(400))
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    designation_id: Mapped[int | None] = mapped_column(
        ForeignKey("designations.id", ondelete="SET NULL"), nullable=True
    )
    joining_date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    employment_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )  # active|inactive|terminated
    gender: Mapped[str | None] = mapped_column(String(20))
    date_of_birth: Mapped[dt.date | None] = mapped_column(Date)
    basic_salary: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    termination_date: Mapped[dt.date | None] = mapped_column(Date)

    user: Mapped[User | None] = relationship(back_populates="employee", uselist=False)
    department: Mapped["Department | None"] = relationship()  # type: ignore[name-defined]
    designation: Mapped["Designation | None"] = relationship()  # type: ignore[name-defined]


# late imports for relationship targets (avoid circulars at class-body time)
from app.models.company import Department, Designation  # noqa: E402,F401
