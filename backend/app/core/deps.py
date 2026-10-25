"""FastAPI dependencies: authentication, role checks, tenant scoping."""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import TokenError, decode_access_token
from app.models import Employee, User

_bearer = HTTPBearer(auto_error=False)

ROLE_ADMIN = "admin"
ROLE_HR = "hr"
ROLE_EMPLOYEE = "employee"
ALL_ROLES = (ROLE_ADMIN, ROLE_HR, ROLE_EMPLOYEE)

# Mandatory first-login password change: a user with must_change_password=True may
# only reach these paths until they change their password (everything else -> 403).
PASSWORD_CHANGE_EXEMPT_PATHS = frozenset(
    {
        "/api/auth/me",
        "/api/auth/change-password",
        "/api/auth/logout",
        "/api/setup/status",
        "/api/health",
    }
)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )
    if user.must_change_password:
        path = request.url.path.rstrip("/")
        if path not in PASSWORD_CHANGE_EXEMPT_PATHS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Password change required"
            )
    return user


def require_roles(*roles: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return user

    return dependency


def require_admin(user: User = Depends(require_roles(ROLE_ADMIN))) -> User:
    return user


def require_hr(user: User = Depends(require_roles(ROLE_ADMIN, ROLE_HR))) -> User:
    return user


def require_active_employee(user: User = Depends(get_current_user)) -> User:
    if user.role == ROLE_EMPLOYEE and user.employee_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No employee profile")
    return user


def get_employee_for_user(user: User, db: Session) -> Employee | None:
    if user.employee_id is None:
        return None
    return db.get(Employee, user.employee_id)
