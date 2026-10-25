"""First-run company setup (public endpoints)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import create_access_token, verify_password_strength
from app.models import Company
from app.schemas.auth import SetupCompanyRequest, SetupStatusResponse
from app.services.bootstrap import create_company_with_admin

router = APIRouter(prefix="/api/setup", tags=["setup"])


def _needs_setup(db: Session) -> bool:
    return db.query(Company.id).first() is None


@router.get("/status", response_model=SetupStatusResponse)
def setup_status(db: Session = Depends(get_db)) -> dict:
    return {"needs_setup": _needs_setup(db)}


@router.post("/company", status_code=status.HTTP_201_CREATED)
def setup_company(payload: SetupCompanyRequest, db: Session = Depends(get_db)) -> dict:
    """Create the first company + default settings/leave types + admin login."""
    if not _needs_setup(db):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup already completed")

    strength_error = verify_password_strength(payload.admin.password)
    if strength_error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=strength_error)

    try:
        company, admin = create_company_with_admin(
            db,
            company_name=payload.company_name.strip(),
            admin_email=str(payload.admin.email),
            admin_name=payload.admin.full_name.strip(),
            admin_password=payload.admin.password,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Setup already completed"
        ) from exc

    token = create_access_token(
        user_id=admin.id, company_id=company.id, role=admin.role
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "must_change_password": admin.must_change_password,
        "user": {
            "id": admin.id,
            "role": admin.role,
            "full_name": admin.full_name,
            "email": admin.email,
            "employee_id": admin.employee_id,
        },
    }
