"""Dashboards / analytics endpoints (M7).

GET /api/analytics/admin   — Admin only (HR → 403)
GET /api/analytics/hr      — HR + Admin
GET /api/analytics/employee/me — any role, own data only

All filters: ?from=YYYY-MM-DD&to=YYYY-MM-DD&department_id=<id> (defaults: today..today).
Every response is computed server-side from the DB and is empty-safe (zeros).
"""
from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin, require_hr
from app.models import User
from app.schemas.analytics import AdminSummaryOut, EmployeeSummaryOut, HRSummaryOut
from app.services import analytics as analytics_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

DateFrom = Annotated[dt.date | None, Query(alias="from", description="YYYY-MM-DD")]
DateTo = Annotated[dt.date | None, Query(alias="to", description="YYYY-MM-DD")]


def _resolve_range(
    db: Session, company_id: int, date_from: DateFrom, date_to: DateTo
) -> tuple[dt.date, dt.date]:
    today = analytics_service._today(db, company_id)
    start = date_from or today
    end = date_to or today
    if end < start:
        start, end = end, start
    return start, end


@router.get(
    "/admin",
    response_model=AdminSummaryOut,
    summary="Admin dashboard KPIs (Admin only)",
)
def admin_dashboard(
    date_from: DateFrom = None,
    date_to: DateTo = None,
    department_id: int | None = Query(default=None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminSummaryOut:
    start, end = _resolve_range(db, user.company_id, date_from, date_to)
    return AdminSummaryOut(
        **analytics_service.admin_summary(db, user.company_id, start, end, department_id)
    )


@router.get(
    "/hr",
    response_model=HRSummaryOut,
    summary="HR dashboard KPIs (HR + Admin)",
)
def hr_dashboard(
    date_from: DateFrom = None,
    date_to: DateTo = None,
    department_id: int | None = Query(default=None),
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
) -> HRSummaryOut:
    start, end = _resolve_range(db, user.company_id, date_from, date_to)
    return HRSummaryOut(
        **analytics_service.hr_summary(db, user.company_id, start, end, department_id)
    )


@router.get(
    "/employee/me",
    response_model=EmployeeSummaryOut,
    summary="Personal dashboard (own data, any role)",
)
def employee_dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmployeeSummaryOut:
    return EmployeeSummaryOut(
        **analytics_service.employee_summary(db, user.company_id, user.employee_id)
    )
