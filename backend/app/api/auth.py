"""Authentication endpoints: login, me, logout, change-password."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
    verify_password_strength,
)
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    TokenResponse,
    UserProfile,
)
from app.utils.audit import record_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _brief(user: User) -> dict:
    return {
        "id": user.id,
        "role": user.role,
        "full_name": user.full_name,
        "email": user.email,
        "employee_id": user.employee_id,
    }


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )

    token = create_access_token(
        user_id=user.id, company_id=user.company_id, role=user.role
    )
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="login",
        entity_type="user",
        entity_id=user.id,
        commit=True,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "must_change_password": user.must_change_password,
        "user": _brief(user),
    }


@router.get("/me", response_model=UserProfile)
def me(user: User = Depends(get_current_user)) -> dict:
    return {
        "id": user.id,
        "role": user.role,
        "full_name": user.full_name,
        "email": user.email,
        "employee_id": user.employee_id,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> Response:
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="logout",
        entity_type="user",
        entity_id=user.id,
        commit=True,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect"
        )
    strength_error = verify_password_strength(payload.new_password)
    if strength_error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=strength_error
        )

    before = {"must_change_password": user.must_change_password}
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="password_change",
        entity_type="user",
        entity_id=user.id,
        before=before,
        after={"must_change_password": False},
        commit=True,
    )
    return {"detail": "Password updated", "must_change_password": False}
