"""Bootstrap helpers: optional env-based admin, used at app startup."""
from __future__ import annotations

import logging

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password, verify_password_strength
from app.models import Company, CompanySettings, LeaveType, User

logger = logging.getLogger("hcm.bootstrap")

DEFAULT_LEAVE_TYPES = [
    {"name": "Annual Leave", "code": "ANNUAL", "yearly_quota": 14, "is_paid": True},
    {"name": "Sick Leave", "code": "SICK", "yearly_quota": 8, "is_paid": True},
    {"name": "Casual Leave", "code": "CASUAL", "yearly_quota": 10, "is_paid": True},
    {"name": "Unpaid Leave", "code": "UNPAID", "yearly_quota": None, "is_paid": False},
]


def seed_default_leave_types(db, company_id: int) -> None:
    for lt in DEFAULT_LEAVE_TYPES:
        exists = (
            db.query(LeaveType)
            .filter(LeaveType.company_id == company_id, LeaveType.code == lt["code"])
            .first()
        )
        if not exists:
            db.add(LeaveType(company_id=company_id, **lt))


def create_company_with_admin(
    db, *, company_name: str, admin_email: str, admin_name: str, admin_password: str
) -> tuple[Company, User]:
    """Create a company + settings + default leave types + admin user in one transaction."""
    company = Company(name=company_name)
    db.add(company)
    db.flush()
    db.add(CompanySettings(company_id=company.id))
    seed_default_leave_types(db, company.id)
    user = User(
        company_id=company.id,
        email=admin_email.strip().lower(),
        password_hash=hash_password(admin_password),
        role="admin",
        full_name=admin_name,
        must_change_password=False,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(company)
    db.refresh(user)
    return company, user


def bootstrap_env_admin() -> None:
    """Create the first company+admin from ADMIN_EMAIL/ADMIN_PASSWORD if set and unused."""
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        return
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        if verify_password_strength(settings.admin_password):
            logger.warning("ADMIN_PASSWORD rejected by strength check; skipping bootstrap")
            return
        company, _ = create_company_with_admin(
            db,
            company_name="My Company",
            admin_email=settings.admin_email,
            admin_name="Administrator",
            admin_password=settings.admin_password,
        )
        logger.info("Bootstrapped admin %s for company %s", settings.admin_email, company.name)
    finally:
        db.close()
