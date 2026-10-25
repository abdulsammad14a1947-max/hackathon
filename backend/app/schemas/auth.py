"""Auth & setup request/response schemas."""
from __future__ import annotations

from typing import Annotated

from email_validator import EmailNotValidError
from email_validator import validate_email as _validate_email
from pydantic import AfterValidator, BaseModel, Field


def _normalize_email(value: str) -> str:
    """Validate an email address (RFC syntax, no DNS lookup).

    `test_environment=True` keeps reserved test domains such as ``acme.test``
    valid — used by the seeded fixtures and the demo data.
    """
    try:
        result = _validate_email(
            value.strip(), check_deliverability=False, test_environment=True
        )
    except EmailNotValidError as exc:
        raise ValueError(str(exc)) from exc
    return result.normalized


#: String schema that validates + normalizes an email address.
EmailInput = Annotated[str, Field(max_length=255), AfterValidator(_normalize_email)]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserBrief(BaseModel):
    """Shape returned by login / setup (frozen in ARCHITECTURE §4)."""

    id: int
    role: str
    full_name: str
    email: str
    employee_id: int | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool = False
    user: UserBrief


class UserProfile(BaseModel):
    id: int
    role: str
    full_name: str
    email: str
    employee_id: int | None = None
    is_active: bool
    must_change_password: bool


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class SetupAdminInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailInput
    password: str = Field(min_length=8, max_length=128)


class SetupCompanyRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    admin: SetupAdminInput


class SetupStatusResponse(BaseModel):
    needs_setup: bool
