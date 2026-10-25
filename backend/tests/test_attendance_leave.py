"""Tests for M4 Attendance + M5 Leave (backend-engineer B).

Run from ``backend``:
    $env:HCM_TEST_DB="test_b.db"; python -m pytest tests/test_attendance_leave.py -q
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from app.core.security import hash_password
from app.models import (
    AuditLog,
    Attendance,
    CompanySettings,
    Department,
    Designation,
    Employee,
    Holiday,
    Notification,
    User,
)
from app.services import attendance_service, leave_service
from app.services.bootstrap import create_company_with_admin
from app.services.calendar_utils import count_working_days
from tests.conftest import login

LOCAL = ZoneInfo("Asia/Karachi")  # default company timezone (ARCHITECTURE §1)


# --------------------------------------------------------------------------- #
# Fixtures
#
# NOTE: these SHADOW the same-named fixtures in tests/conftest.py because the
# shared fixture passes ``joining_date="2025-01-15"`` (a string), which the
# SQLite Date type rejects ("SQLite Date type only accepts Python date objects
# as input"). conftest.py is coordinator-owned — the bug is reported to the
# coordinator with the one-line fix (use dt.date(...)); this file keeps the
# same fixture names so the required interface still holds.
# --------------------------------------------------------------------------- #
@pytest.fixture
def company(db):
    """Seed one company with admin/hr users, an employee, org structure, leave types."""
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
                password_hash=hash_password("HrPass1234"),
                role="hr",
                full_name="Hira HR",
                employee_id=hr.id,
            ),
            User(
                company_id=company_obj.id,
                email="sara@acme.test",
                password_hash=hash_password("EmpPass1234"),
                role="employee",
                full_name="Sara Khan",
                employee_id=emp.id,
            ),
        ]
    )
    # NOTE: create_company_with_admin() already seeds DEFAULT_LEAVE_TYPES —
    # re-adding them violates uq_leavetype_company_code (second bug worked
    # around from the same broken conftest fixture).
    db.commit()

    return {
        "company": company_obj,
        "admin": admin,
        "employee": emp,
        "hr_employee": hr,
        "department": dept,
        "designation": desig,
    }


@pytest.fixture
def admin_headers(client, company):
    return login(client, "admin@acme.test", "AdminPass123")


@pytest.fixture
def hr_headers(client, company):
    return login(client, "hr@acme.test", "HrPass1234")


@pytest.fixture
def emp_headers(client, company):
    return login(client, "sara@acme.test", "EmpPass1234")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _local_today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).astimezone(LOCAL).date()


def _past_working_day(back: int = 10) -> dt.date:
    """A weekday strictly before today (default weekends Sat/Sun)."""
    d = _local_today() - dt.timedelta(days=back)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def _next_monday() -> dt.date:
    d = _local_today() + dt.timedelta(days=7)
    while d.weekday() != 0:
        d += dt.timedelta(days=1)
    return d


def _settings_stub() -> CompanySettings:
    return CompanySettings(
        company_id=1,
        office_start_time=dt.time(9, 0),
        grace_period_minutes=15,
        weekend_days=["Saturday", "Sunday"],
        geofence_radius_m=1000,
        timezone="Asia/Karachi",
        half_day_threshold_hours=5.0,
    )


# --------------------------------------------------------------------------- #
# 1-2) check-in / check-out happy path + conflicts
# --------------------------------------------------------------------------- #
def test_duplicate_checkin_returns_409(client, emp_headers):
    r1 = client.post("/api/attendance/check-in", headers=emp_headers, json={})
    assert r1.status_code == 201, r1.text
    assert r1.json()["check_in"] is not None
    assert r1.json()["status"] in ("present", "late")

    r2 = client.post("/api/attendance/check-in", headers=emp_headers, json={})
    assert r2.status_code == 409, r2.text
    assert "already checked in" in r2.json()["detail"].lower()


def test_checkout_without_checkin_409(client, emp_headers):
    r = client.post("/api/attendance/check-out", headers=emp_headers, json={})
    assert r.status_code == 409, r.text


def test_checkin_then_checkout_200_and_hours_positive(client, db, emp_headers, company):
    r1 = client.post("/api/attendance/check-in", headers=emp_headers, json={})
    assert r1.status_code == 201, r1.text

    # Back-date the stored check-in by 3h so worked_hours is meaningful.
    rec = (
        db.query(Attendance)
        .filter(
            Attendance.company_id == company["company"].id,
            Attendance.employee_id == company["employee"].id,
        )
        .one()
    )
    rec.check_in = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(
        hours=3
    )
    db.commit()

    r2 = client.post("/api/attendance/check-out", headers=emp_headers, json={})
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["check_out"] is not None
    assert body["worked_hours"] > 0
    assert 2.9 <= body["worked_hours"] <= 3.1
    assert body["status"] in ("present", "late", "half_day")

    r3 = client.post("/api/attendance/check-out", headers=emp_headers, json={})
    assert r3.status_code == 409, r3.text


# --------------------------------------------------------------------------- #
# 3-4) status helper boundaries (unit tests, no wall clock needed)
# --------------------------------------------------------------------------- #
def test_compute_status_late_boundaries():
    s = _settings_stub()
    day = dt.date(2026, 1, 5)  # a Monday

    def at(h, m, sec=0):
        return dt.datetime.combine(day, dt.time(h, m, sec))

    assert attendance_service.compute_status(at(8, 59), s, 0.0) == "present"
    assert attendance_service.compute_status(at(9, 0), s, 0.0) == "present"
    assert attendance_service.compute_status(at(9, 15), s, 0.0) == "present"
    assert attendance_service.compute_status(at(9, 16), s, 0.0) == "late"
    assert attendance_service.compute_status(at(9, 20), s, 0.0) == "late"


def test_compute_status_half_day_threshold():
    s = _settings_stub()
    day = dt.date(2026, 1, 5)
    on_time = dt.datetime.combine(day, dt.time(9, 0))
    late_in = dt.datetime.combine(day, dt.time(10, 0))

    assert attendance_service.compute_status(on_time, s, 4.99) == "half_day"
    assert attendance_service.compute_status(on_time, s, 0.5) == "half_day"
    assert attendance_service.compute_status(on_time, s, 5.0) == "present"
    assert attendance_service.compute_status(on_time, s, 0.0) == "present"
    # half_day takes precedence over late (ARCHITECTURE §4 check-out rule)
    assert attendance_service.compute_status(late_in, s, 4.0) == "half_day"
    assert attendance_service.compute_status(late_in, s, 6.0) == "late"


# --------------------------------------------------------------------------- #
# 5) missing_checkout detection in summary + month view
# --------------------------------------------------------------------------- #
def test_missing_checkout_detected_in_summary(client, db, company, emp_headers):
    past = _past_working_day()
    db.add(
        Attendance(
            company_id=company["company"].id,
            employee_id=company["employee"].id,
            date=past,
            check_in=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            - dt.timedelta(days=1),
            status="present",
            worked_hours=0.0,
        )
    )
    db.commit()

    # Service-level (frozen contract §5b)
    summary = attendance_service.summary_for_employee(
        db, company["company"].id, company["employee"].id, past, past
    )
    assert summary["missing_checkout"] == 1
    assert summary["absent"] == 0  # a record exists -> not absent
    for key in ("days_present", "late", "half_days", "absent", "total_hours"):
        assert key in summary

    # Endpoint level
    r = client.get(
        "/api/attendance/me",
        headers=emp_headers,
        params={"year": past.year, "month": past.month},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    row = next(x for x in body["records"] if x["date"] == past.isoformat())
    assert row["missing_checkout"] is True
    assert row["display_status"] == "missing_checkout"
    # DB status column untouched (display-only decision, documented in service)
    assert row["status"] == "present"
    assert body["summary"]["missing_checkout"] >= 1
    assert body["summary"]["working_days"] >= 1


# --------------------------------------------------------------------------- #
# 6) approved leave => NOT absent (board + summary)
# --------------------------------------------------------------------------- #
def test_approved_leave_day_is_not_absent(
    client, db, company, emp_headers, hr_headers, admin_headers
):
    past = _past_working_day()
    r = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "UNPAID",
            "start_date": past.isoformat(),
            "end_date": past.isoformat(),
            "reason": "Day off",
        },
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    # Brief matrix #13: Admin may only VIEW leave decisions -> 403
    r = client.post(
        f"/api/leave/requests/{rid}/approve", headers=admin_headers, json={}
    )
    assert r.status_code == 403, r.text
    # HR approves
    r = client.post(f"/api/leave/requests/{rid}/approve", headers=hr_headers, json={})
    assert r.status_code == 200, r.text

    summary = attendance_service.summary_for_employee(
        db, company["company"].id, company["employee"].id, past, past
    )
    assert summary["absent"] == 0
    assert summary["on_leave"] == 1

    r = client.get(
        "/api/attendance/board",
        headers=admin_headers,
        params={"date": past.isoformat()},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    emp_row = next(x for x in items if x["employee_id"] == company["employee"].id)
    assert emp_row["status"] == "on_leave"
    # HR employee has no record/leave on that working day -> absent
    hr_row = next(x for x in items if x["employee_id"] == company["hr_employee"].id)
    assert hr_row["status"] == "absent"


def test_board_requires_hr(client, emp_headers):
    r = client.get("/api/attendance/board", headers=emp_headers)
    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# 7) working days exclude weekends + holidays
# --------------------------------------------------------------------------- #
def test_working_days_exclude_weekends_and_holidays(
    client, db, company, emp_headers
):
    monday = _next_monday()
    friday = monday + dt.timedelta(days=4)
    holiday_date = monday + dt.timedelta(days=2)  # Wednesday
    db.add(
        Holiday(
            company_id=company["company"].id, name="Test Holiday", date=holiday_date
        )
    )
    db.commit()

    expected = count_working_days(
        db, company["company"].id, monday, friday
    )
    assert expected == 4.0  # Mon-Fri minus the seeded holiday

    r = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "UNPAID",
            "start_date": monday.isoformat(),
            "end_date": friday.isoformat(),
            "reason": "Working-day count check",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["working_days"] == 4.0


# --------------------------------------------------------------------------- #
# 8-10) overlap, balance, invalid range
# --------------------------------------------------------------------------- #
def test_overlapping_leave_returns_409(client, emp_headers):
    base = _next_monday() + dt.timedelta(days=14)
    r1 = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "UNPAID",
            "start_date": base.isoformat(),
            "end_date": (base + dt.timedelta(days=2)).isoformat(),
            "reason": "First block",
        },
    )
    assert r1.status_code == 201, r1.text

    r2 = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "UNPAID",
            "start_date": (base + dt.timedelta(days=2)).isoformat(),
            "end_date": (base + dt.timedelta(days=4)).isoformat(),
            "reason": "Touching range",
        },
    )
    assert r2.status_code == 409, r2.text
    assert "overlap" in r2.json()["detail"].lower()

    # Overlap is checked across leave types too
    r3 = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "ANNUAL",
            "start_date": (base + dt.timedelta(days=1)).isoformat(),
            "end_date": (base + dt.timedelta(days=1)).isoformat(),
            "reason": "Single day inside range",
        },
    )
    assert r3.status_code == 409, r3.text


def test_insufficient_balance_returns_422_with_detail(client, emp_headers):
    start = _next_monday()  # 4 full weeks => 20 working days > ANNUAL quota 14
    end = start + dt.timedelta(days=27)
    r = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "ANNUAL",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "reason": "Long vacation",
        },
    )
    assert r.status_code == 422, r.text
    detail = str(r.json()["detail"])
    assert "quota" in detail and "used" in detail and "requested" in detail


def test_invalid_date_range_returns_422(client, emp_headers):
    r = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "UNPAID",
            "start_date": "2026-11-10",
            "end_date": "2026-11-01",
            "reason": "Backwards",
        },
    )
    assert r.status_code == 422, r.text

    r = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "UNPAID",
            "start_date": "not-a-date",
            "end_date": "2026-11-01",
            "reason": "Garbage",
        },
    )
    assert r.status_code == 422, r.text

    r = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "NOPE",
            "start_date": "2026-11-01",
            "end_date": "2026-11-02",
            "reason": "Unknown type",
        },
    )
    assert r.status_code == 422, r.text  # unknown leave type


# --------------------------------------------------------------------------- #
# 11) scoping: employees cannot use scope=all
# --------------------------------------------------------------------------- #
def test_employee_cannot_list_others_leave(client, emp_headers, hr_headers):
    # HR creates their own request
    r = client.post(
        "/api/leave/requests",
        headers=hr_headers,
        json={
            "leave_type_code": "UNPAID",
            "start_date": (_next_monday() + dt.timedelta(days=21)).isoformat(),
            "end_date": (_next_monday() + dt.timedelta(days=21)).isoformat(),
            "reason": "HR day off",
        },
    )
    assert r.status_code == 201, r.text

    # Employee creates their own request
    r = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "UNPAID",
            "start_date": (_next_monday() + dt.timedelta(days=22)).isoformat(),
            "end_date": (_next_monday() + dt.timedelta(days=22)).isoformat(),
            "reason": "Emp day off",
        },
    )
    assert r.status_code == 201, r.text

    r = client.get(
        "/api/leave/requests", headers=emp_headers, params={"scope": "all"}
    )
    assert r.status_code == 403, r.text

    r = client.get("/api/leave/requests", headers=emp_headers, params={"scope": "me"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert all(x["employee_id"] == body["items"][0]["employee_id"] for x in body["items"])


# --------------------------------------------------------------------------- #
# 12) HR cannot approve their own request
# --------------------------------------------------------------------------- #
def test_hr_cannot_approve_own_request(client, hr_headers, admin_headers):
    day = _next_monday() + dt.timedelta(days=28)
    r = client.post(
        "/api/leave/requests",
        headers=hr_headers,
        json={
            "leave_type_code": "UNPAID",
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "reason": "My own leave",
        },
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    r = client.post(f"/api/leave/requests/{rid}/approve", headers=hr_headers, json={})
    assert r.status_code == 403, r.text
    assert "own" in r.json()["detail"].lower()

    # Brief matrix #13: Admin cannot approve at all (View only) -> 403
    r = client.post(f"/api/leave/requests/{rid}/approve", headers=admin_headers, json={})
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "Insufficient permissions"


# --------------------------------------------------------------------------- #
# 13) approve/reject update status + notification + audit
# --------------------------------------------------------------------------- #
def test_approve_and_reject_write_status_notification_audit(
    client, db, company, emp_headers, hr_headers, admin_headers
):
    emp_user_id = (
        db.query(User).filter_by(employee_id=company["employee"].id).one().id
    )
    base = _next_monday() + dt.timedelta(days=7)

    r = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "SICK",
            "start_date": base.isoformat(),
            "end_date": (base + dt.timedelta(days=1)).isoformat(),
            "reason": "Flu",
        },
    )
    assert r.status_code == 201, r.text
    rid1 = r.json()["id"]
    # Admin is View-only for approvals (brief matrix #13)
    r = client.post(
        f"/api/leave/requests/{rid1}/approve", headers=admin_headers, json={}
    )
    assert r.status_code == 403, r.text
    r = client.post(
        f"/api/leave/requests/{rid1}/approve",
        headers=hr_headers,
        json={"comment": "Get well soon"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert r.json()["reviewed_by"] is not None
    assert r.json()["review_comment"] == "Get well soon"

    r = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "CASUAL",
            "start_date": (base + dt.timedelta(days=10)).isoformat(),
            "end_date": (base + dt.timedelta(days=10)).isoformat(),
            "reason": "Personal work",
        },
    )
    assert r.status_code == 201, r.text
    rid2 = r.json()["id"]
    r = client.post(
        f"/api/leave/requests/{rid2}/reject",
        headers=hr_headers,
        json={"comment": "Peak season"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"

    notes = db.query(Notification).filter_by(user_id=emp_user_id).all()
    assert len(notes) >= 2  # one per decision

    actions = {
        a.action for a in db.query(AuditLog).filter_by(entity_type="leave_request").all()
    }
    assert "leave.approved" in actions
    assert "leave.rejected" in actions
    approved_audit = (
        db.query(AuditLog).filter_by(action="leave.approved").one()
    )
    assert approved_audit.before["status"] == "pending"
    assert approved_audit.after["status"] == "approved"

    # Rejected leave must not consume balance (approved-only rule)
    bal = leave_service.get_balance(
        db, company["company"].id, company["employee"].id, base.year
    )
    sick = next(i for i in bal["items"] if i["code"] == "SICK")
    casual = next(i for i in bal["items"] if i["code"] == "CASUAL")
    assert sick["used"] == 2.0
    assert casual["used"] == 0.0


def test_employee_cannot_approve_requests(client, emp_headers):
    # approve requires HR/Admin regardless of ownership
    r = client.post("/api/leave/requests/1/approve", headers=emp_headers, json={})
    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# 14) employees cannot touch others' corrections / see scope=all
# --------------------------------------------------------------------------- #
def test_employee_cannot_access_others_corrections(client, emp_headers, company):
    past = _past_working_day()
    r = client.post(
        "/api/attendance/corrections",
        headers=emp_headers,
        json={
            "employee_id": company["hr_employee"].id,  # someone else's record
            "attendance_date": past.isoformat(),
            "check_in": "09:00",
            "reason": "Fix HR punch",
        },
    )
    assert r.status_code == 403, r.text

    r = client.get(
        "/api/attendance/corrections", headers=emp_headers, params={"scope": "all"}
    )
    assert r.status_code == 403, r.text

    # Own correction is fine, and default listing shows only own
    r = client.post(
        "/api/attendance/corrections",
        headers=emp_headers,
        json={
            "attendance_date": past.isoformat(),
            "check_in": "09:00",
            "check_out": "17:00",
            "reason": "Forgot to check out",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"

    r = client.get("/api/attendance/corrections", headers=emp_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["employee_id"] == company["employee"].id


# --------------------------------------------------------------------------- #
# 15) geofence: accuracy + radius + client timestamp rejection
# --------------------------------------------------------------------------- #
def test_checkin_geofence_accuracy_and_radius(client, db, company, emp_headers):
    st = (
        db.query(CompanySettings)
        .filter_by(company_id=company["company"].id)
        .one()
    )
    st.office_lat = 24.85
    st.office_lng = 67.05
    st.geofence_radius_m = 500
    db.commit()

    # accuracy_m > 100 (with coords) -> 422
    r = client.post(
        "/api/attendance/check-in",
        headers=emp_headers,
        json={"lat": 24.85, "lng": 67.05, "accuracy_m": 150},
    )
    assert r.status_code == 422, r.text
    assert "accuracy" in r.json()["detail"].lower()

    # accuracy alone (no coords) still rejected
    r = client.post(
        "/api/attendance/check-in", headers=emp_headers, json={"accuracy_m": 150}
    )
    assert r.status_code == 422, r.text

    # ~94 km away -> outside 500 m radius -> 422
    r = client.post(
        "/api/attendance/check-in",
        headers=emp_headers,
        json={"lat": 25.70, "lng": 67.05, "accuracy_m": 5},
    )
    assert r.status_code == 422, r.text
    assert "geofence" in r.json()["detail"].lower()

    # exactly at the office -> 201
    r = client.post(
        "/api/attendance/check-in",
        headers=emp_headers,
        json={"lat": 24.85, "lng": 67.05, "accuracy_m": 5},
    )
    assert r.status_code == 201, r.text


def test_checkin_rejects_client_supplied_timestamps(client, emp_headers):
    r = client.post(
        "/api/attendance/check-in",
        headers=emp_headers,
        json={"timestamp": "2026-01-01T09:00:00"},
    )
    assert r.status_code == 422, r.text

    r = client.post(
        "/api/attendance/check-in",
        headers=emp_headers,
        json={"check_in": "09:00"},
    )
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# 16) correction approve applies times + audits
# --------------------------------------------------------------------------- #
def test_correction_approve_applies_times_and_audits(
    client, db, company, emp_headers, hr_headers, admin_headers
):
    past = _past_working_day()
    r = client.post(
        "/api/attendance/corrections",
        headers=emp_headers,
        json={
            "attendance_date": past.isoformat(),
            "check_in": "09:00",
            "check_out": "17:00",
            "reason": "Terminal was down",
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    # Employees may not approve (HR only)
    r = client.post(
        f"/api/attendance/corrections/{cid}/approve", headers=emp_headers, json={}
    )
    assert r.status_code == 403, r.text
    # Brief matrix #11: Admin may only VIEW corrections -> 403
    r = client.post(
        f"/api/attendance/corrections/{cid}/approve", headers=admin_headers, json={}
    )
    assert r.status_code == 403, r.text

    # HR approves with a comment
    r = client.post(
        f"/api/attendance/corrections/{cid}/approve",
        headers=hr_headers,
        json={"comment": "Confirmed by logs"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert r.json()["review_comment"] == "Confirmed by logs"

    att = (
        db.query(Attendance)
        .filter_by(
            company_id=company["company"].id,
            employee_id=company["employee"].id,
            date=past,
        )
        .one()
    )
    assert att.worked_hours == 8.0
    local_in = att.check_in.replace(tzinfo=dt.timezone.utc).astimezone(LOCAL)
    local_out = att.check_out.replace(tzinfo=dt.timezone.utc).astimezone(LOCAL)
    assert (local_in.hour, local_in.minute) == (9, 0)
    assert (local_out.hour, local_out.minute) == (17, 0)
    assert att.status == "present"  # 09:00 <= 09:00 + 15 min grace

    audit = db.query(AuditLog).filter_by(
        action="attendance.correction.approved"
    ).one()
    assert audit.after is not None and audit.after["check_in"] is not None
    assert audit.before is None or "check_in" in audit.before

    note_titles = [n.title for n in db.query(Notification).all()]
    assert any("correction approved" in t.lower() for t in note_titles)


def test_hr_cannot_approve_own_correction(client, db, company, hr_headers):
    past = _past_working_day()
    r = client.post(
        "/api/attendance/corrections",
        headers=hr_headers,
        json={
            "attendance_date": past.isoformat(),
            "check_in": "08:55",
            "reason": "My own punch fix",
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    r = client.post(
        f"/api/attendance/corrections/{cid}/approve", headers=hr_headers, json={}
    )
    assert r.status_code == 403, r.text
    assert "own" in r.json()["detail"].lower()


def test_correction_reject_flow(client, db, company, emp_headers, hr_headers, admin_headers):
    past = _past_working_day()
    r = client.post(
        "/api/attendance/corrections",
        headers=emp_headers,
        json={
            "attendance_date": past.isoformat(),
            "check_out": "23:59",
            "reason": "Late checkout claim",
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    # Admin cannot reject (View only per brief matrix #11)
    r = client.post(
        f"/api/attendance/corrections/{cid}/reject", headers=admin_headers, json={}
    )
    assert r.status_code == 403, r.text

    r = client.post(
        f"/api/attendance/corrections/{cid}/reject",
        headers=hr_headers,
        json={"comment": "No badge records found"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"

    assert (
        db.query(AuditLog)
        .filter_by(action="attendance.correction.rejected")
        .count()
        == 1
    )
    note_titles = [n.title for n in db.query(Notification).all()]
    assert any("correction rejected" in t.lower() for t in note_titles)
    # No attendance row created for a rejected correction
    assert (
        db.query(Attendance)
        .filter_by(employee_id=company["employee"].id, date=past)
        .count()
        == 0
    )


# --------------------------------------------------------------------------- #
# Leave balance + cancel + types (supporting coverage)
# --------------------------------------------------------------------------- #
def test_leave_types_and_balance_endpoints(
    client, db, company, emp_headers, hr_headers
):
    r = client.get("/api/leave/types", headers=emp_headers)
    assert r.status_code == 200, r.text
    codes = {x["code"] for x in r.json()}
    assert {"ANNUAL", "SICK", "CASUAL", "UNPAID"} <= codes

    r = client.get("/api/leave/balance", headers=emp_headers)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    annual = next(i for i in items if i["code"] == "ANNUAL")
    assert annual["quota"] == 14
    assert annual["used"] == 0
    assert annual["remaining"] == 14
    assert annual["is_paid"] is True
    unpaid = next(i for i in items if i["code"] == "UNPAID")
    assert unpaid["quota"] is None
    assert unpaid["remaining"] is None  # unlimited

    # employee cannot read someone else's balance
    r = client.get(
        "/api/leave/balance",
        headers=emp_headers,
        params={"employee_id": company["hr_employee"].id},
    )
    assert r.status_code == 403, r.text

    # HR may read an employee's balance
    r = client.get(
        "/api/leave/balance",
        headers=hr_headers,
        params={"employee_id": company["employee"].id},
    )
    assert r.status_code == 200, r.text


def test_cancel_own_pending_request(client, db, company, emp_headers, hr_headers):
    day = _next_monday() + dt.timedelta(days=35)
    r = client.post(
        "/api/leave/requests",
        headers=emp_headers,
        json={
            "leave_type_code": "UNPAID",
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "reason": "Might change plans",
        },
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    # HR (non-owner) cannot cancel someone else's request -> 403
    r = client.post(f"/api/leave/requests/{rid}/cancel", headers=hr_headers)
    assert r.status_code == 403, r.text

    r = client.post(f"/api/leave/requests/{rid}/cancel", headers=emp_headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"

    # cancelled -> cannot cancel again (409) nor approve (409)
    r = client.post(f"/api/leave/requests/{rid}/cancel", headers=emp_headers)
    assert r.status_code == 409, r.text

    assert (
        db.query(AuditLog).filter_by(action="leave.cancelled").count() == 1
    )
