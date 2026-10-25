"""Tests for M1 auth/setup, M2 org, M3 employees (owner: backend-engineer A).

Run from backend/:  $env:HCM_TEST_DB="test_a.db"; python -m pytest tests/test_auth_org_employees.py -q
"""
from __future__ import annotations

import datetime as dt

from app.core.security import verify_password
from app.models import (
    AuditLog,
    Attendance,
    Company,
    CompanySettings,
    Employee,
    LeaveRequest,
    LeaveType,
    PayrollItem,
    PayrollRun,
    User,
)

CSV_HEADER = (
    "employee_code,first_name,last_name,email,department,designation,"
    "joining_date,basic_salary,gender,phone\n"
)


def _files(content: str) -> dict:
    return {"file": ("employees.csv", content.encode("utf-8"), "text/csv")}


def new_payload(company, **overrides) -> dict:
    payload = {
        "employee_code": "EMP-101",
        "first_name": "Nadia",
        "last_name": "Noor",
        "email": "nadia@acme.test",
        "department_id": company["department"].id,
        "designation_id": company["designation"].id,
        "joining_date": "2025-02-01",
        "basic_salary": 90000,
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------- M1 setup
def test_setup_status_when_empty(client):
    resp = client.get("/api/setup/status")
    assert resp.status_code == 200
    assert resp.json() == {"needs_setup": True}


def test_setup_rejects_weak_password(client):
    payload = {
        "company_name": "Beta Corp",
        "admin": {"full_name": "Boss Person", "email": "boss@beta.test", "password": "abcdefgh"},
    }
    resp = client.post("/api/setup/company", json=payload)
    assert resp.status_code == 422
    assert "mixed character" in resp.json()["detail"]
    assert client.get("/api/setup/status").json()["needs_setup"] is True


def test_setup_rejects_bad_email(client):
    payload = {
        "company_name": "Beta Corp",
        "admin": {"full_name": "Boss", "email": "not-an-email", "password": "Str0ngPass12"},
    }
    assert client.post("/api/setup/company", json=payload).status_code == 422


def test_setup_creates_company_then_conflicts(client, db):
    payload = {
        "company_name": "Beta Corp",
        "admin": {"full_name": "Boss Person", "email": "boss@beta.test", "password": "Str0ngPass12"},
    }
    resp = client.post("/api/setup/company", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["access_token"] and body["token_type"] == "bearer"
    assert body["user"]["role"] == "admin" and body["user"]["email"] == "boss@beta.test"

    # second attempt -> 409
    assert client.post("/api/setup/company", json=payload).status_code == 409
    assert client.get("/api/setup/status").json() == {"needs_setup": False}

    company = db.query(Company).filter_by(name="Beta Corp").one()
    leave_types = {
        lt.code: (lt.name, lt.yearly_quota, lt.is_paid)
        for lt in db.query(LeaveType).filter_by(company_id=company.id)
    }
    assert leave_types == {
        "ANNUAL": ("Annual Leave", 14, True),
        "SICK": ("Sick Leave", 8, True),
        "CASUAL": ("Casual Leave", 10, True),
        "UNPAID": ("Unpaid Leave", None, False),
    }
    settings = db.query(CompanySettings).filter_by(company_id=company.id).one()
    assert settings.office_start_time == dt.time(9, 0)
    assert settings.grace_period_minutes == 15
    assert settings.weekend_days == ["Saturday", "Sunday"]
    assert settings.geofence_radius_m == 1000
    assert settings.timezone == "Asia/Karachi"
    assert float(settings.half_day_threshold_hours) == 5.0

    # the returned token is usable immediately
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200


# ----------------------------------------------------------------------------- M1 auth
def test_login_success_and_me(client, company):
    resp = client.post(
        "/api/auth/login", json={"email": "admin@acme.test", "password": "AdminPass123"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["must_change_password"] is False
    assert set(body["user"]) == {"id", "role", "full_name", "email", "employee_id"}
    assert body["user"]["role"] == "admin"

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "admin@acme.test"
    assert me.json()["must_change_password"] is False


def test_login_wrong_password_and_unknown_email(client, company):
    resp = client.post(
        "/api/auth/login", json={"email": "admin@acme.test", "password": "WrongPass123"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"

    resp = client.post(
        "/api/auth/login", json={"email": "ghost@acme.test", "password": "Whatever123"}
    )
    assert resp.status_code == 401


def test_passwords_are_hashed_never_plaintext(db, company):
    user = db.query(User).filter_by(email="admin@acme.test").one()
    assert user.password_hash != "AdminPass123"
    assert user.password_hash.startswith("$2")
    assert "AdminPass123" not in user.password_hash
    assert verify_password("AdminPass123", user.password_hash) is True
    assert verify_password("nope", user.password_hash) is False


def test_logout_returns_204_and_audits(client, company, admin_headers, db):
    resp = client.post("/api/auth/logout", headers=admin_headers)
    assert resp.status_code == 204
    assert resp.content == b""
    entry = db.query(AuditLog).filter_by(action="logout").first()
    assert entry is not None
    assert entry.actor_email == "admin@acme.test"


def test_change_password_wrong_current_gives_401(client, company, admin_headers):
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "NotThePass1", "new_password": "BrandNew1234"},
        headers=admin_headers,
    )
    assert resp.status_code == 401


def test_change_password_weak_new_gives_422(client, company, admin_headers):
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "AdminPass123", "new_password": "abcdefgh"},
        headers=admin_headers,
    )
    assert resp.status_code == 422
    assert "mixed character" in resp.json()["detail"]


def test_change_password_success_clears_flag(client, company, admin_headers, db):
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "AdminPass123", "new_password": "BrandNew1234"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is False

    user = db.query(User).filter_by(email="admin@acme.test").one()
    assert verify_password("BrandNew1234", user.password_hash) is True
    assert verify_password("AdminPass123", user.password_hash) is False
    assert db.query(AuditLog).filter_by(action="password_change").count() == 1
    # old password no longer logs in, new one does
    assert (
        client.post(
            "/api/auth/login", json={"email": "admin@acme.test", "password": "AdminPass123"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": "admin@acme.test", "password": "BrandNew1234"}
        ).status_code
        == 200
    )


def test_mandatory_first_login_password_change(client, company, hr_headers):
    create = client.post(
        "/api/employees", json=new_payload(company), headers=hr_headers
    )
    assert create.status_code == 201, create.text
    temp = create.json()["temp_password"]
    emp_id = create.json()["employee"]["id"]

    login = client.post(
        "/api/auth/login", json={"email": "nadia@acme.test", "password": temp}
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # every non-exempt endpoint is blocked with a clear 403
    blocked = client.get(f"/api/employees/{emp_id}", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Password change required"
    assert client.get("/api/employees", headers=headers).status_code == 403
    assert client.get("/api/org/settings", headers=headers).status_code == 403

    # exempt endpoints still work
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert (
        client.post(
            "/api/auth/change-password",
            json={"current_password": temp, "new_password": "FreshPass1234"},
            headers=headers,
        ).status_code
        == 200
    )

    # after the change the same endpoint returns 200
    ok = client.get(f"/api/employees/{emp_id}", headers=headers)
    assert ok.status_code == 200, ok.text
    assert client.get("/api/auth/me", headers=headers).json()["must_change_password"] is False
    # and the new password is required for a fresh login
    again = client.post(
        "/api/auth/login", json={"email": "nadia@acme.test", "password": "FreshPass1234"}
    )
    assert again.status_code == 200
    assert again.json()["must_change_password"] is False


def test_inactive_account_gets_403_on_login_and_token(client, company, admin_headers, emp_headers):
    emp = company["employee"]
    assert client.get("/api/auth/me", headers=emp_headers).status_code == 200

    resp = client.post(f"/api/employees/{emp.id}/deactivate", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    login = client.post(
        "/api/auth/login", json={"email": "sara@acme.test", "password": "EmpPass1234"}
    )
    assert login.status_code == 403
    assert "deactivated" in login.json()["detail"].lower()
    # already-issued token is refused too
    assert client.get("/api/auth/me", headers=emp_headers).status_code == 403


def test_deactivate_and_activate_roundtrip(client, company, admin_headers):
    emp = company["employee"]
    assert (
        client.post(f"/api/employees/{emp.id}/deactivate", headers=admin_headers).json()["is_active"]
        is False
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": "sara@acme.test", "password": "EmpPass1234"}
        ).status_code
        == 403
    )
    resp = client.post(f"/api/employees/{emp.id}/activate", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True
    assert resp.json()["employment_status"] == "active"
    assert (
        client.post(
            "/api/auth/login", json={"email": "sara@acme.test", "password": "EmpPass1234"}
        ).status_code
        == 200
    )


# ------------------------------------------------------------------------- M2 role gates
def test_hr_cannot_patch_org_settings(client, company, hr_headers):
    resp = client.patch(
        "/api/org/settings", json={"grace_period_minutes": 20}, headers=hr_headers
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Insufficient permissions"


def test_employee_cannot_list_employees(client, company, emp_headers):
    resp = client.get("/api/employees", headers=emp_headers)
    assert resp.status_code == 403


def test_employee_cannot_read_org_settings_but_can_read_leave_types(
    client, company, emp_headers, hr_headers
):
    assert client.get("/api/org/settings", headers=emp_headers).status_code == 403
    resp = client.get("/api/org/leave-types", headers=emp_headers)
    assert resp.status_code == 200
    assert {lt["code"] for lt in resp.json()["items"]} == {
        "ANNUAL",
        "SICK",
        "CASUAL",
        "UNPAID",
    }
    # write attempts are refused for HR and employees
    assert (
        client.post(
            "/api/org/leave-types",
            json={"name": "Sneaky", "code": "SNK"},
            headers=emp_headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/org/leave-types",
            json={"name": "Sneaky", "code": "SNK"},
            headers=hr_headers,
        ).status_code
        == 403
    )


def test_settings_update_validates_and_audits(client, company, admin_headers, hr_headers, db):
    resp = client.get("/api/org/settings", headers=hr_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "office_start_time": "09:00",
        "grace_period_minutes": 15,
        "weekend_days": ["Saturday", "Sunday"],
        "office_lat": None,
        "office_lng": None,
        "geofence_radius_m": 1000,
        "timezone": "Asia/Karachi",
        "half_day_threshold_hours": 5.0,
    }

    resp = client.patch(
        "/api/org/settings",
        json={"office_start_time": "09:30", "grace_period_minutes": 10},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["office_start_time"] == "09:30"

    # invalid values -> 422
    for bad in (
        {"office_start_time": "25:99"},
        {"office_start_time": "9am"},
        {"weekend_days": ["Funday"]},
        {"weekend_days": ["Saturday", "Saturday"]},
        {"timezone": "Karachi"},
        {"grace_period_minutes": -5},
        {"half_day_threshold_hours": 0},
        {"office_lat": 123.0},
    ):
        resp = client.patch("/api/org/settings", json=bad, headers=admin_headers)
        assert resp.status_code == 422, (bad, resp.text)

    entry = db.query(AuditLog).filter_by(action="settings_update").first()
    assert entry is not None
    assert entry.before["office_start_time"] == "09:00"
    assert entry.after["office_start_time"] == "09:30"
    assert entry.before["grace_period_minutes"] == 15
    assert entry.after["grace_period_minutes"] == 10


def test_department_crud_conflicts_and_roles(client, company, admin_headers, hr_headers, emp_headers):
    resp = client.get("/api/org/departments", headers=hr_headers)
    assert resp.status_code == 200
    assert "Engineering" in [d["name"] for d in resp.json()["items"]]
    assert client.get("/api/org/departments", headers=emp_headers).status_code == 403

    # duplicate name -> 409 (case-insensitive)
    assert (
        client.post(
            "/api/org/departments", json={"name": "engineering"}, headers=admin_headers
        ).status_code
        == 409
    )
    # HR cannot write
    assert (
        client.post("/api/org/departments", json={"name": "Sales"}, headers=hr_headers).status_code
        == 403
    )

    created = client.post(
        "/api/org/departments", json={"name": "Finance"}, headers=admin_headers
    )
    assert created.status_code == 201
    dept_id = created.json()["id"]

    renamed = client.patch(
        f"/api/org/departments/{dept_id}",
        json={"name": "Finance & Accounts"},
        headers=admin_headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Finance & Accounts"

    # referenced department cannot be deleted
    engineering = company["department"].id
    conflict = client.delete(f"/api/org/departments/{engineering}", headers=admin_headers)
    assert conflict.status_code == 409
    assert "referenced" in conflict.json()["detail"]

    assert client.delete(f"/api/org/departments/{dept_id}", headers=admin_headers).status_code == 204
    assert (
        client.patch(
            "/api/org/departments/999999", json={"name": "Nope"}, headers=admin_headers
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/org/departments/{dept_id}", headers=admin_headers).status_code == 404
    )


def test_holiday_duplicate_date_conflict(client, company, admin_headers, hr_headers, emp_headers):
    resp = client.post(
        "/api/org/holidays",
        json={"name": "Independence Day", "date": "2025-08-14"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    dup = client.post(
        "/api/org/holidays",
        json={"name": "Another Day", "date": "2025-08-14"},
        headers=admin_headers,
    )
    assert dup.status_code == 409
    assert client.get("/api/org/holidays", headers=hr_headers).json()["items"][0]["date"] == "2025-08-14"
    assert client.get("/api/org/holidays", headers=emp_headers).status_code == 403
    # bad date -> 422
    assert (
        client.post(
            "/api/org/holidays",
            json={"name": "Bad", "date": "14-08-2025"},
            headers=admin_headers,
        ).status_code
        == 422
    )


def test_leave_type_crud_duplicates_and_referenced_delete(
    client, company, admin_headers, hr_headers, db
):
    # duplicate code -> 409
    dup = client.post(
        "/api/org/leave-types",
        json={"name": "Annual Again", "code": "annual", "yearly_quota": 5, "is_paid": True},
        headers=admin_headers,
    )
    assert dup.status_code == 409

    created = client.post(
        "/api/org/leave-types",
        json={"name": "Medical Leave", "code": "MEDICAL", "yearly_quota": 6, "is_paid": True},
        headers=admin_headers,
    )
    assert created.status_code == 201
    lt_id = created.json()["id"]

    patched = client.patch(
        f"/api/org/leave-types/{lt_id}", json={"yearly_quota": 8}, headers=admin_headers
    )
    assert patched.status_code == 200
    assert patched.json()["yearly_quota"] == 8

    assert client.delete(f"/api/org/leave-types/{lt_id}", headers=hr_headers).status_code == 403
    assert client.delete(f"/api/org/leave-types/{lt_id}", headers=admin_headers).status_code == 204

    # a leave type referenced by a request cannot be deleted
    annual = (
        db.query(LeaveType)
        .filter_by(company_id=company["company"].id, code="ANNUAL")
        .one()
    )
    db.add(
        LeaveRequest(
            company_id=company["company"].id,
            employee_id=company["employee"].id,
            leave_type_id=annual.id,
            start_date=dt.date.today(),
            end_date=dt.date.today(),
            working_days=1,
            reason="rest",
            status="approved",
        )
    )
    db.commit()
    conflict = client.delete(f"/api/org/leave-types/{annual.id}", headers=admin_headers)
    assert conflict.status_code == 409


# ------------------------------------------------------------------------- M3 employees
def test_employee_create_conflicts_and_validation(client, company, hr_headers):
    # duplicate employee_code -> 409
    resp = client.post(
        "/api/employees", json=new_payload(company, employee_code="EMP-001"), headers=hr_headers
    )
    assert resp.status_code == 409
    assert "employee_code" in resp.json()["detail"]

    # duplicate email -> 409
    resp = client.post(
        "/api/employees", json=new_payload(company, email="sara@acme.test"), headers=hr_headers
    )
    assert resp.status_code == 409

    # salary <= 0 -> 422
    resp = client.post(
        "/api/employees", json=new_payload(company, basic_salary=0), headers=hr_headers
    )
    assert resp.status_code == 422
    resp = client.post(
        "/api/employees", json=new_payload(company, basic_salary=-100), headers=hr_headers
    )
    assert resp.status_code == 422

    # bad email -> 422
    resp = client.post(
        "/api/employees", json=new_payload(company, email="not-an-email"), headers=hr_headers
    )
    assert resp.status_code == 422

    # bad joining_date -> 422
    resp = client.post(
        "/api/employees", json=new_payload(company, joining_date="01/02/2025"), headers=hr_headers
    )
    assert resp.status_code == 422

    # department / designation must belong to the company -> 422
    resp = client.post(
        "/api/employees", json=new_payload(company, department_id=999999), headers=hr_headers
    )
    assert resp.status_code == 422
    resp = client.post(
        "/api/employees", json=new_payload(company, designation_id=999999), headers=hr_headers
    )
    assert resp.status_code == 422


def test_employee_register_is_hr_only(client, company, admin_headers):
    # Brief matrix #06: Admin is View-only for employee registration -> 403
    resp = client.post("/api/employees", json=new_payload(company), headers=admin_headers)
    assert resp.status_code == 403
    assert "HR" in resp.json()["detail"]


def test_employee_create_success_and_temp_login(client, company, hr_headers, db):
    resp = client.post("/api/employees", json=new_payload(company), headers=hr_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == {"employee", "temp_password"}
    assert body["temp_password"].startswith("Tmp-")
    assert body["employee"]["employee_code"] == "EMP-101"
    assert body["employee"]["department"] == "Engineering"
    assert body["employee"]["designation"] == "Software Engineer"
    assert body["employee"]["full_name"] == "Nadia Noor"

    login = client.post(
        "/api/auth/login",
        json={"email": "nadia@acme.test", "password": body["temp_password"]},
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    assert login.json()["user"]["role"] == "employee"

    user = db.query(User).filter_by(email="nadia@acme.test").one()
    assert user.role == "employee"
    assert user.must_change_password is True
    assert user.is_active is True
    assert user.password_hash != body["temp_password"]
    assert db.query(AuditLog).filter_by(action="employee_create").count() >= 1


def test_employee_create_hr_role(client, company, admin_headers, db):
    payload = new_payload(
        company, employee_code="EMP-102", email="hr2@acme.test", create_login_role="hr"
    )
    resp = client.post("/api/employees", json=payload, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    user = db.query(User).filter_by(email="hr2@acme.test").one()
    assert user.role == "hr"
    # the new HR user can reach the directory
    headers = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'email': 'hr2@acme.test', 'password': resp.json()['temp_password']}).json()['access_token']}"}
    assert client.get("/api/employees", headers=headers).status_code == 403  # still must change pw


def test_employee_list_search_filters_and_pagination(client, company, admin_headers, hr_headers):
    resp = client.get("/api/employees", headers=hr_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"items", "total", "page", "page_size"}
    assert body["total"] == 2
    assert body["page"] == 1 and body["page_size"] == 20
    assert all("department" in item and "designation" in item for item in body["items"])

    assert client.get("/api/employees?q=sara", headers=admin_headers).json()["total"] == 1
    assert client.get("/api/employees?q=EMP-001", headers=admin_headers).json()["total"] == 1
    assert client.get("/api/employees?q=zzzzz", headers=admin_headers).json()["total"] == 0
    assert (
        client.get(f"/api/employees?department_id={company['department'].id}", headers=admin_headers).json()["total"]
        == 2
    )
    assert client.get("/api/employees?status=terminated", headers=admin_headers).json()["total"] == 0
    paged = client.get("/api/employees?page=2&page_size=1", headers=admin_headers).json()
    assert paged["page"] == 2 and paged["page_size"] == 1 and len(paged["items"]) == 1


def test_employee_profile_360(client, company, admin_headers, db):
    emp = company["employee"]
    cid = company["company"].id
    today = dt.date.today()
    db.add(
        Attendance(
            company_id=cid,
            employee_id=emp.id,
            date=today - dt.timedelta(days=1),
            status="present",
            worked_hours=8.0,
        )
    )
    db.add(
        Attendance(
            company_id=cid,
            employee_id=emp.id,
            date=today,
            status="late",
            worked_hours=6.5,
        )
    )
    annual = db.query(LeaveType).filter_by(company_id=cid, code="ANNUAL").one()
    db.add(
        LeaveRequest(
            company_id=cid,
            employee_id=emp.id,
            leave_type_id=annual.id,
            start_date=today,
            end_date=today,
            working_days=1,
            reason="rest",
            status="pending",
        )
    )
    final_run = PayrollRun(
        company_id=cid, period_year=2025, period_month=1, status="finalized",
        total_gross=150000, total_deductions=0, total_net=150000,
    )
    db.add(final_run)
    db.flush()
    db.add(
        PayrollItem(
            company_id=cid, run_id=final_run.id, employee_id=emp.id,
            basic=100000, hra=40000, medical=10000, gross=150000,
            working_days=22, present_days=22, absent_days=0, unpaid_leave_days=0,
            half_days=0, deduction_amount=0, tax=0, net_pay=150000,
        )
    )
    draft_run = PayrollRun(
        company_id=cid, period_year=2025, period_month=2, status="draft",
        total_gross=0, total_deductions=0, total_net=0,
    )
    db.add(draft_run)
    db.flush()
    db.add(
        PayrollItem(
            company_id=cid, run_id=draft_run.id, employee_id=emp.id,
            basic=1, hra=0, medical=0, gross=1, working_days=22, present_days=1,
            absent_days=0, unpaid_leave_days=0, half_days=0, deduction_amount=0,
            tax=0, net_pay=1,
        )
    )
    db.commit()

    resp = client.get(f"/api/employees/{emp.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["employee"]["id"] == emp.id
    assert body["employee"]["department"] == "Engineering"
    assert body["employee"]["designation"] == "Software Engineer"
    assert float(body["employee"]["basic_salary"]) == 100000
    assert body["can_view_salary"] is True

    summary = body["attendance_summary"]
    assert summary["records"] == 2
    assert summary["by_status"]["present"] == 1
    assert summary["by_status"]["late"] == 1
    assert summary["total_hours"] == 14.5

    assert len(body["leave_history"]) == 1
    assert body["leave_history"][0]["code"] == "ANNUAL"
    assert body["leave_history"][0]["status"] == "pending"

    # only the finalized run shows up
    assert [p["period_month"] for p in body["payroll_history"]] == [1]
    assert float(body["payroll_history"][0]["gross"]) == 150000
    assert float(body["payroll_history"][0]["net_pay"]) == 150000

    # missing employee -> 404
    assert client.get("/api/employees/999999", headers=admin_headers).status_code == 404


def test_employee_cannot_read_others_profile(client, company, emp_headers):
    other_id = company["hr_employee"].id
    resp = client.get(f"/api/employees/{other_id}", headers=emp_headers)
    assert resp.status_code == 403
    assert "Access denied" in resp.json()["detail"]

    own_id = company["employee"].id
    own = client.get(f"/api/employees/{own_id}", headers=emp_headers)
    assert own.status_code == 200
    assert own.json()["employee"]["id"] == own_id
    # owner may see their own salary
    assert own.json()["employee"]["basic_salary"] is not None
    assert own.json()["can_view_salary"] is True


def test_employee_cannot_patch_others_or_use_staff_patch(client, company, emp_headers, db):
    other_id = company["hr_employee"].id
    resp = client.patch(
        f"/api/employees/{other_id}", json={"phone": "+92 300 0000000"}, headers=emp_headers
    )
    assert resp.status_code == 403

    resp = client.patch(
        f"/api/employees/{company['employee'].id}",
        json={"basic_salary": 1},
        headers=emp_headers,
    )
    assert resp.status_code == 403
    db.expire_all()
    emp = db.get(Employee, company["employee"].id)
    assert float(emp.basic_salary) == 100000  # unchanged


def test_employee_self_update_phone_address_only(client, company, emp_headers, db):
    resp = client.patch(
        "/api/employees/me",
        json={"phone": "+92 300 9999999", "address": "House 1, Karachi"},
        headers=emp_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["employee"]["phone"] == "+92 300 9999999"

    for forbidden in (
        {"role": "admin"},
        {"basic_salary": 999999},
        {"email": "hijack@acme.test"},
        {"employee_code": "EMP-999"},
    ):
        resp = client.patch("/api/employees/me", json=forbidden, headers=emp_headers)
        assert resp.status_code == 422, (forbidden, resp.text)

    db.expire_all()
    emp = db.get(Employee, company["employee"].id)
    assert emp.email == "sara@acme.test"
    assert float(emp.basic_salary) == 100000
    assert emp.address == "House 1, Karachi"
    assert db.query(AuditLog).filter_by(action="employee_self_update").count() == 1


def test_hr_update_employee_audits_before_after(client, company, hr_headers, db):
    emp = company["employee"]
    resp = client.patch(
        f"/api/employees/{emp.id}",
        json={"basic_salary": 150000, "phone": "+92 300 1111111", "employment_status": "active"},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text
    assert float(resp.json()["employee"]["basic_salary"]) == 150000

    entry = (
        db.query(AuditLog).filter_by(action="employee_update").order_by(AuditLog.id.desc()).first()
    )
    assert entry is not None
    assert "100000" in str(entry.before["basic_salary"])
    assert "150000" in str(entry.after["basic_salary"])
    assert entry.actor_email == "hr@acme.test"

    # invalid status -> 422
    resp = client.patch(
        f"/api/employees/{emp.id}", json={"employment_status": "zombie"}, headers=hr_headers
    )
    assert resp.status_code == 422
    # unknown email in another login -> 409
    resp = client.patch(
        f"/api/employees/{emp.id}", json={"email": "admin@acme.test"}, headers=hr_headers
    )
    assert resp.status_code == 409


def test_employee_update_syncs_login(client, company, hr_headers, db):
    emp = company["employee"]
    resp = client.patch(
        f"/api/employees/{emp.id}",
        json={"first_name": "Sara", "last_name": "Khan-Lodhi", "email": "sara.lodhi@acme.test"},
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["employee"]["full_name"] == "Sara Khan-Lodhi"
    user = db.query(User).filter_by(employee_id=emp.id).one()
    assert user.email == "sara.lodhi@acme.test"
    assert user.full_name == "Sara Khan-Lodhi"
    # new email works for login, old one does not
    assert (
        client.post(
            "/api/auth/login", json={"email": "sara.lodhi@acme.test", "password": "EmpPass1234"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login", json={"email": "sara@acme.test", "password": "EmpPass1234"}
        ).status_code
        == 401
    )


def test_reset_password_returns_temp_and_forces_change(client, company, admin_headers, db):
    emp = company["employee"]
    resp = client.post(f"/api/employees/{emp.id}/reset-password", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["temp_password"].startswith("Tmp-")
    assert body["must_change_password"] is True
    assert body["email"] == "sara@acme.test"

    assert (
        client.post(
            "/api/auth/login", json={"email": "sara@acme.test", "password": "EmpPass1234"}
        ).status_code
        == 401
    )
    login = client.post(
        "/api/auth/login", json={"email": "sara@acme.test", "password": body["temp_password"]}
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/employees", headers=headers).json()["detail"] == "Password change required"

    user = db.query(User).filter_by(email="sara@acme.test").one()
    assert user.must_change_password is True
    assert verify_password(body["temp_password"], user.password_hash) is True
    assert db.query(AuditLog).filter_by(action="password_reset").count() == 1


def test_export_forbidden_for_employee_admin_and_csv_for_hr(
    client, company, hr_headers, emp_headers, admin_headers
):
    assert client.get("/api/employees/export", headers=emp_headers).status_code == 403
    # Brief matrix #08: Admin has no export access -> 403
    assert client.get("/api/employees/export", headers=admin_headers).status_code == 403

    resp = client.get("/api/employees/export", headers=hr_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert "employees.csv" in resp.headers["content-disposition"]
    assert "employee_code" in resp.text
    assert "sara@acme.test" in resp.text


# ------------------------------------------------------------------------ M3 CSV import
def test_csv_dry_run_reports_rows_and_persists_nothing(client, company, hr_headers, db):
    content = (
        CSV_HEADER
        + "EMP-201,Adil,Raza,adil@acme.test,Engineering,Software Engineer,2025-03-01,85000,male,+92 300 0000001\n"
        + "EMP-202,Sami,Bad,not-an-email,Engineering,Software Engineer,not-a-date,-5,frob,+92 300 0000002\n"
    )
    before = db.query(Employee).count()

    resp = client.post(
        "/api/employees/import?dry_run=true",
        files=_files(content),
        headers=hr_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is True
    assert body["valid_count"] == 1
    assert body["error_count"] == 1
    assert body["would_create"] == 1

    bad = [r for r in body["rows"] if r["errors"]]
    assert len(bad) == 1
    assert bad[0]["row"] == 2
    fields = {e["field"] for e in bad[0]["errors"]}
    assert {"email", "joining_date", "basic_salary", "gender"} <= fields
    assert all(e["reason"] for e in bad[0]["errors"])
    assert all(set(e) == {"field", "reason"} for e in bad[0]["errors"])

    db.expire_all()
    assert db.query(Employee).count() == before  # nothing persisted


def test_csv_real_import_persists_valid_rows(client, company, hr_headers, db):
    content = (
        CSV_HEADER
        + "EMP-201,Adil,Raza,adil@acme.test,Engineering,Software Engineer,2025-03-01,85000,male,+92 300 0000001\n"
        + "EMP-202,Sami,Bad,not-an-email,Engineering,Software Engineer,not-a-date,-5,,\n"
        + "EMP-203,Ria,Khan,ria@acme.test,Engineering,Software Engineer,2025-03-02,70000,female,\n"
    )
    before = db.query(Employee).count()
    resp = client.post(
        "/api/employees/import?dry_run=false", files=_files(content), headers=hr_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dry_run"] is False
    assert body["created_count"] == 2
    assert body["error_count"] == 1
    assert [r["row"] for r in body["rows"] if r["created"]] == [1, 3]

    db.expire_all()
    assert db.query(Employee).count() == before + 2

    # created rows get a working temp login with a forced password change
    created = [r for r in body["rows"] if r["created"]][0]
    assert created["temp_password"].startswith("Tmp-")
    login = client.post(
        "/api/auth/login",
        json={"email": "adil@acme.test", "password": created["temp_password"]},
    )
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True

    # the directory search finds the new rows
    assert client.get("/api/employees?q=adil", headers=hr_headers).json()["total"] == 1
    assert db.query(AuditLog).filter_by(action="employee_import").count() == 1


def test_csv_duplicate_detection_within_file_and_against_db(
    client, company, hr_headers, db
):
    content = (
        CSV_HEADER
        + "EMP-301,Ana,First,ana1@acme.test,Engineering,Software Engineer,2025-03-01,50000,,\n"
        + "EMP-301,Ana,Second,ana2@acme.test,Engineering,Software Engineer,2025-03-01,50000,,\n"
        + "EMP-001,Sara,Clone,sara@acme.test,Engineering,Software Engineer,2025-03-01,50000,,\n"
    )
    resp = client.post(
        "/api/employees/import?dry_run=true", files=_files(content), headers=hr_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["would_create"] == 1

    rows = {r["row"]: r for r in body["rows"]}
    assert rows[1]["errors"] == []
    dup_in_file = rows[2]["errors"]
    assert dup_in_file[0]["field"] == "employee_code"
    assert "duplicate of row 1" in dup_in_file[0]["reason"]
    dup_in_db = rows[3]["errors"]
    assert dup_in_db[0]["field"] == "employee_code"
    assert "already exists" in dup_in_db[0]["reason"]

    db.expire_all()
    assert db.query(Employee).count() == 2  # nothing persisted by the dry run


def test_csv_rejects_missing_columns(client, company, hr_headers):
    resp = client.post(
        "/api/employees/import?dry_run=true",
        files=_files("name,email\nSara,sara@acme.test\n"),
        headers=hr_headers,
    )
    assert resp.status_code == 422
    assert any("Missing required column" in item for item in resp.json()["detail"])


def test_csv_import_forbidden_for_employee(client, company, emp_headers):
    resp = client.post(
        "/api/employees/import?dry_run=true", files=_files(CSV_HEADER), headers=emp_headers
    )
    assert resp.status_code == 403
