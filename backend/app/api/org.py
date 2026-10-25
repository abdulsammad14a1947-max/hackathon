"""Organization endpoints: settings + departments/designations/holidays/leave-types.

Read: HR+Admin (leave-types readable by every role). Write: Admin only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin, require_hr
from app.models import User
from app.schemas.org import (
    DepartmentIn,
    HolidayIn,
    LeaveTypeIn,
    LeaveTypePatch,
    SettingsOut,
    SettingsPatch,
)
from app.services import org_service

router = APIRouter(prefix="/api/org", tags=["org"])


# ------------------------------------------------------------------------- settings
@router.get("/settings", response_model=SettingsOut)
def get_settings(
    user: User = Depends(require_hr), db: Session = Depends(get_db)
) -> dict:
    row = org_service.get_settings_row(db, user.company_id)
    return org_service.settings_to_dict(row)


@router.patch("/settings", response_model=SettingsOut)
def patch_settings(
    payload: SettingsPatch,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    data = payload.model_dump()
    fields_set = set(payload.model_fields_set)
    return org_service.update_settings(db, user.company_id, user, data, fields_set)


# ---------------------------------------------------------------------- departments
@router.get("/departments")
def list_departments(
    user: User = Depends(require_hr), db: Session = Depends(get_db)
) -> dict:
    return {"items": org_service.list_departments(db, user.company_id)}


@router.post("/departments", status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return org_service.create_department(db, user.company_id, user, payload.name)


@router.patch("/departments/{dept_id}")
def update_department(
    dept_id: int,
    payload: DepartmentIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return org_service.update_department(db, user.company_id, user, dept_id, payload.name)


@router.delete("/departments/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(
    dept_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    org_service.delete_department(db, user.company_id, user, dept_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------- designations
@router.get("/designations")
def list_designations(
    user: User = Depends(require_hr), db: Session = Depends(get_db)
) -> dict:
    return {"items": org_service.list_designations(db, user.company_id)}


@router.post("/designations", status_code=status.HTTP_201_CREATED)
def create_designation(
    payload: DepartmentIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return org_service.create_designation(db, user.company_id, user, payload.name)


@router.patch("/designations/{item_id}")
def update_designation(
    item_id: int,
    payload: DepartmentIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return org_service.update_designation(db, user.company_id, user, item_id, payload.name)


@router.delete("/designations/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_designation(
    item_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    org_service.delete_designation(db, user.company_id, user, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------------ holidays
@router.get("/holidays")
def list_holidays(
    user: User = Depends(require_hr), db: Session = Depends(get_db)
) -> dict:
    return {"items": org_service.list_holidays(db, user.company_id)}


@router.post("/holidays", status_code=status.HTTP_201_CREATED)
def create_holiday(
    payload: HolidayIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return org_service.create_holiday(
        db, user.company_id, user, payload.name, payload.date
    )


@router.patch("/holidays/{item_id}")
def update_holiday(
    item_id: int,
    payload: HolidayIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return org_service.update_holiday(
        db, user.company_id, user, item_id, payload.name, payload.date
    )


@router.delete("/holidays/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holiday(
    item_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    org_service.delete_holiday(db, user.company_id, user, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------- leave types
@router.get("/leave-types")
def list_leave_types(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return {"items": org_service.list_leave_types(db, user.company_id)}


@router.post("/leave-types", status_code=status.HTTP_201_CREATED)
def create_leave_type(
    payload: LeaveTypeIn,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return org_service.create_leave_type(
        db,
        user.company_id,
        user,
        name=payload.name,
        code=payload.code,
        yearly_quota=payload.yearly_quota,
        is_paid=payload.is_paid,
    )


@router.patch("/leave-types/{item_id}")
def update_leave_type(
    item_id: int,
    payload: LeaveTypePatch,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    return org_service.update_leave_type(
        db,
        user.company_id,
        user,
        item_id,
        payload.model_dump(),
        set(payload.model_fields_set),
    )


@router.delete("/leave-types/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_leave_type(
    item_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    org_service.delete_leave_type(db, user.company_id, user, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
