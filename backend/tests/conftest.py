"""Shared pytest fixtures for the HCM Lite backend test-suite.

Usage from module tests:
    from tests.conftest import login_headers   # noqa: F401  (fixture import)
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib

import pytest

# Configure a dedicated SQLite test database BEFORE app modules are imported.
# Parallel test runs set HCM_TEST_DB to a private file to avoid cross-talk.
_DEFAULT_DB = pathlib.Path(__file__).resolve().parent / (
    os.environ.get("HCM_TEST_DB") or "test_hcm_lite.db"
)
_TEST_DB = _DEFAULT_DB
if _TEST_DB.exists():
    _TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ.setdefault("AI_MOCK_MODE", "true")
os.environ.pop("ADMIN_EMAIL", None)
os.environ.pop("ADMIN_PASSWORD", None)

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.core.db import Base, SessionLocal, engine, init_db  # noqa: E402,E401
from app.main import app  # noqa: E402
from app.models import Department, Designation, Employee, User  # noqa: E402
from app.services.bootstrap import create_company_with_admin  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate all data between tests, keeping the schema."""
    yield
    db = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def company(db):
    """Seed one company with admin/hr users, an employee, org structure and leave types."""
    company_obj, admin = create_company_with_admin(
        db,
        company_name="Acme Textiles",
        admin_email="admin@acme.test",
        admin_name="Amina Admin",
        admin_password="AdminPass123",
    )
    dept = Department(company_id=company_obj.id, name="Engineering")
    db.add(dept)
    db.flush()
    desig = Designation(company_id=company_obj.id, name="Software Engineer")
    db.add(desig)
    db.flush()

    emp = Employee(
        company_id=company_obj.id,
        employee_code="EMP-001",
        first_name="Sara",
        last_name="Khan",
        email="sara@acme.test",
        phone="+92 300 1234567",
        department_id=dept.id,
        designation_id=desig.id,
        joining_date=dt.date(2025, 1, 15),
        employment_status="active",
        gender="female",
        basic_salary=100000,
    )
    hr = Employee(
        company_id=company_obj.id,
        employee_code="EMP-000",
        first_name="Hira",
        last_name="HR",
        email="hr@acme.test",
        department_id=dept.id,
        designation_id=desig.id,
        joining_date=dt.date(2024, 6, 1),
        employment_status="active",
        gender="female",
        basic_salary=120000,
    )
    db.add_all([emp, hr])
    db.flush()
    db.add_all(
        [
            User(
                company_id=company_obj.id,
                email="hr@acme.test",
                password_hash=_hash("HrPass1234"),
                role="hr",
                full_name="Hira HR",
                employee_id=hr.id,
            ),
            User(
                company_id=company_obj.id,
                email="sara@acme.test",
                password_hash=_hash("EmpPass1234"),
                role="employee",
                full_name="Sara Khan",
                employee_id=emp.id,
            ),
        ]
    )
    # Leave types are already seeded by create_company_with_admin().
    db.commit()

    return {
        "company": company_obj,
        "admin": admin,
        "employee": emp,
        "hr_employee": hr,
        "department": dept,
        "designation": desig,
    }


def _hash(password: str) -> str:
    from app.core.security import hash_password

    return hash_password(password)


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(client, company):
    return login(client, "admin@acme.test", "AdminPass123")


@pytest.fixture
def hr_headers(client, company):
    return login(client, "hr@acme.test", "HrPass1234")


@pytest.fixture
def emp_headers(client, company):
    return login(client, "sara@acme.test", "EmpPass1234")
