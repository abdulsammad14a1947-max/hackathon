"""Shared calendar helpers — weekends, holidays and working-day counts.

Used by BOTH leave (working days in a range) and payroll (per-day denominator),
so this module is coordinator-owned and frozen.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import CompanySettings, Holiday

WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def get_settings(db: Session, company_id: int) -> CompanySettings:
    settings = (
        db.query(CompanySettings).filter(CompanySettings.company_id == company_id).first()
    )
    if settings is None:
        # Defaults for a company whose settings row was not seeded yet.
        settings = CompanySettings(company_id=company_id)
        db.add(settings)
        db.flush()
    return settings


def weekend_days(settings: CompanySettings) -> set[str]:
    return set(settings.weekend_days or ["Saturday", "Sunday"])


def is_weekend(date: dt.date, settings: CompanySettings) -> bool:
    return WEEKDAY_NAMES[date.weekday()] in weekend_days(settings)


def holiday_map(db: Session, company_id: int) -> dict[dt.date, str]:
    rows = db.query(Holiday).filter(Holiday.company_id == company_id).all()
    return {row.date: row.name for row in rows}


def is_working_day(date: dt.date, settings: CompanySettings, holidays: dict[dt.date, str]) -> bool:
    if date in holidays:
        return False
    return not is_weekend(date, settings)


def iter_days(start: dt.date, end: dt.date):
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def count_working_days(
    db: Session, company_id: int, start: dt.date, end: dt.date
) -> float:
    """Working days in [start, end], excluding configured weekends and holidays."""
    if end < start:
        return 0.0
    settings = get_settings(db, company_id)
    holidays = holiday_map(db, company_id)
    return float(
        sum(1 for d in iter_days(start, end) if is_working_day(d, settings, holidays))
    )


def working_days_in_month(db: Session, company_id: int, year: int, month: int) -> float:
    start = dt.date(year, month, 1)
    if month == 12:
        end = dt.date(year, 12, 31)
    else:
        end = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    return count_working_days(db, company_id, start, end)


def month_date_range(year: int, month: int) -> tuple[dt.date, dt.date]:
    start = dt.date(year, month, 1)
    end = (
        dt.date(year, 12, 31)
        if month == 12
        else dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    )
    return start, end


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    from math import asin, cos, radians, sin, sqrt

    r = 6_371_000.0
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lng2 - lng1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * r * asin(sqrt(a))
