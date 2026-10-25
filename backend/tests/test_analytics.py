"""M7 Dashboards/Analytics tests — server-computed numbers, filters, empty-safety,
role checks and per-user scoping.

Fixtures: client, db, company, admin_headers, hr_headers, emp_headers.
"""
from __future__ import annotations

import datetime as dt

from app.models import (
    Attendance,
    AttendanceCorrection,
    Department,
    Employee,
    LeaveRequest,
    LeaveType,
)
from app.services.analytics import admin_summary, employee_summary, hr_summary

# Fixtures (client, db, company, admin_headers, hr_headers, emp_headers) come
# from tests/conftest.py.

# Fixed working days used across tests (2026-10-25 is a Sunday → 21st = Wed, 22nd = Thu)
DAY_A = dt.date(2026, 10, 22)
DAY_B = dt.date(2026, 10, 21)


def _seed_att(db, company_id, employee_id, date, status="present", hours=8.0):
    db.add(
        Attendance(
            company_id=company_id,
            employee_id=employee_id,
            date=date,
            status=status,
            worked_hours=hours,
        )
    )
    db.commit()


# --------------------------------------------------------------------- admin
def test_admin_dashboard_roles_headcount_and_shape(
    client, db, company, admin_headers, hr_headers, emp_headers
):
    assert client.get("/api/analytics/admin", headers=hr_headers).status_code == 403
    assert client.get("/api/analytics/admin", headers=emp_headers).status_code == 403

    resp = client.get("/api/analytics/admin", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["active_headcount"] == 2  # Sara + Hira, both active
    assert data["attrition_ytd"] == 0
    assert data["payroll_cost"] == 0  # no finalized run yet
    assert data["payroll_basis"] == "none"
    assert data["avg_salary"] == 165000  # 1.5 × mean(100000, 120000)
    assert data["avg_basic_salary"] == 110000
    assert data["headcount_by_department"] == [{"department": "Engineering", "count": 2}]
    assert data["payroll_cost_by_department"] == []
    assert data["gender_breakdown"] == {
        "male": 0,
        "female": 2,
        "other": 0,
        "unspecified": 0,
    }
    assert data["tenure_months_avg"] > 0
    assert isinstance(data["recent_audit"], list)
    assert len(data["recent_audit"]) <= 8
    assert data["recent_audit"], "admin login should have been audit-logged"
    entry = data["recent_audit"][0]
    assert {"actor", "action", "entity", "created_at"} <= set(entry.keys())
    assert entry["created_at"] is not None


def test_admin_payroll_cost_range_and_fallback(
    client, db, company, admin_headers, hr_headers
):
    cid = company["company"].id
    from tests.test_payroll import _finalized_run_with_full_attendance

    run = _finalized_run_with_full_attendance(
        client, db, company, hr_headers, admin_headers
    )

    in_range = client.get(
        "/api/analytics/admin?from=2025-02-01&to=2025-02-28", headers=admin_headers
    ).json()
    assert in_range["payroll_basis"] == "finalized_runs_in_range"
    # Sara net 140000 + Hira net 165500 (both fully attended)
    assert in_range["payroll_cost"] == 305500
    assert in_range["payroll_cost_by_department"] == [
        {"department": "Engineering", "gross": 330000, "net": 305500}
    ]

    out_of_range = client.get(
        "/api/analytics/admin?from=2024-06-01&to=2024-06-30", headers=admin_headers
    ).json()
    assert out_of_range["payroll_basis"] == "latest_finalized_run_gross"
    assert out_of_range["payroll_cost"] == 330000  # fallback: sum of gross


def test_department_filter_changes_admin_results(
    client, db, company, admin_headers, hr_headers
):
    cid = company["company"].id
    sales = Department(company_id=cid, name="Sales")
    db.add(sales)
    db.flush()
    db.add(
        Employee(
            company_id=cid,
            employee_code="EMP-002",
            first_name="Bob",
            last_name="Stone",
            email="bob@acme.test",
            department_id=sales.id,
            joining_date=dt.date(2024, 1, 1),
            employment_status="active",
            gender="male",
            basic_salary=50000,
        )
    )
    db.commit()

    everything = client.get("/api/analytics/admin", headers=admin_headers).json()
    assert everything["active_headcount"] == 3
    assert everything["gender_breakdown"]["male"] == 1
    dept_map = {d["department"]: d["count"] for d in everything["headcount_by_department"]}
    assert dept_map == {"Engineering": 2, "Sales": 1}
    assert everything["avg_salary"] == 135000  # 1.5 × mean(100000,120000,50000)

    only_sales = client.get(
        f"/api/analytics/admin?department_id={sales.id}", headers=admin_headers
    ).json()
    assert only_sales["active_headcount"] == 1
    assert only_sales["headcount_by_department"] == [{"department": "Sales", "count": 1}]
    assert only_sales["gender_breakdown"]["male"] == 1


# --------------------------------------------------------------------- HR
def test_hr_dashboard_counts_filters_trend_and_pending(
    client, db, company, admin_headers, hr_headers, emp_headers
):
    cid = company["company"].id
    sara = company["employee"]
    hira = company["hr_employee"]

    assert client.get("/api/analytics/hr", headers=emp_headers).status_code == 403
    assert client.get("/api/analytics/hr", headers=admin_headers).status_code == 200

    _seed_att(db, cid, sara.id, DAY_A, "present")
    _seed_att(db, cid, sara.id, DAY_B, "late")
    _seed_att(db, cid, hira.id, DAY_A, "on_leave")

    day = client.get(
        f"/api/analytics/hr?from={DAY_A.isoformat()}&to={DAY_A.isoformat()}",
        headers=hr_headers,
    ).json()
    assert day["headcount"] == 2
    assert day["present"] == 1     # Sara present on the 22nd
    assert day["late"] == 0        # Sara's late row was on the 21st (date filter works)
    assert day["on_leave"] == 1    # Hira on leave on the 22nd
    assert day["pending_approvals"] == {"leave_requests": 0, "corrections": 0}
    assert len(day["attendance_trend"]) == 14  # default = last 14 days ending at `to`
    assert day["attendance_trend"][-1]["date"] == DAY_A.isoformat()
    assert {"date", "present", "late", "absent"} <= set(day["attendance_trend"][-1].keys())
    assert isinstance(day["insights"], list)
    assert 3 <= len(day["insights"]) <= 5

    prev_day = client.get(
        f"/api/analytics/hr?from={DAY_B.isoformat()}&to={DAY_B.isoformat()}",
        headers=hr_headers,
    ).json()
    assert prev_day["late"] == 1   # different date → different numbers
    assert prev_day["present"] == 0

    late_comers = client.get(
        f"/api/analytics/hr?from={DAY_B.isoformat()}&to={DAY_B.isoformat()}",
        headers=hr_headers,
    ).json()["top_late_comers"]
    assert len(late_comers) == 1
    assert late_comers[0]["employee_id"] == sara.id
    assert late_comers[0]["late_count"] == 1
    assert late_comers[0]["department"] == "Engineering"

    # pending approvals appear once seeded
    from app.models import LeaveType

    annual = db.query(LeaveType).filter(
        LeaveType.company_id == cid, LeaveType.code == "ANNUAL"
    ).one()
    db.add(
        LeaveRequest(
            company_id=cid,
            employee_id=sara.id,
            leave_type_id=annual.id,
            start_date=dt.date(2026, 11, 2),
            end_date=dt.date(2026, 11, 3),
            working_days=2,
            reason="trip",
            status="pending",
        )
    )
    db.add(
        AttendanceCorrection(
            company_id=cid,
            employee_id=sara.id,
            attendance_date=DAY_B,
            reason="forgot to check out",
            status="pending",
        )
    )
    db.commit()

    with_pending = client.get(
        f"/api/analytics/hr?from={DAY_A.isoformat()}&to={DAY_A.isoformat()}",
        headers=hr_headers,
    ).json()
    assert with_pending["pending_approvals"] == {"leave_requests": 1, "corrections": 1}


def test_hr_leave_utilization_and_absenteeism(
    client, db, company, hr_headers
):
    cid = company["company"].id
    sara = company["employee"]
    hira = company["hr_employee"]

    from app.models import LeaveType

    annual = db.query(LeaveType).filter(
        LeaveType.company_id == cid, LeaveType.code == "ANNUAL"
    ).one()
    db.add(
        LeaveRequest(
            company_id=cid,
            employee_id=hira.id,
            leave_type_id=annual.id,
            start_date=dt.date(2026, 9, 7),
            end_date=dt.date(2026, 9, 8),
            working_days=2,
            reason="vacation",
            status="approved",
        )
    )
    db.commit()

    _seed_att(db, cid, sara.id, DAY_A, "present")
    _seed_att(db, cid, sara.id, DAY_B, "late")
    _seed_att(db, cid, hira.id, DAY_A, "on_leave")

    data = client.get(
        f"/api/analytics/hr?from={DAY_B.isoformat()}&to={DAY_A.isoformat()}",
        headers=hr_headers,
    ).json()

    util = {row["leave_type"]: row for row in data["leave_utilization"]}
    assert util["Annual Leave"]["quota"] == 14
    assert util["Annual Leave"]["used"] == 2          # approved 2 days this year
    assert util["Annual Leave"]["utilization"] == round(2 / 14, 3)
    assert util["Unpaid Leave"]["quota"] is None      # unlimited
    assert util["Unpaid Leave"]["used"] == 0

    # 2 employees × 2 working days expected; only Hira's day-21 absence missing
    assert len(data["absenteeism_by_department"]) == 1
    row = data["absenteeism_by_department"][0]
    assert row["department"] == "Engineering"
    assert row["expected_days"] == 4
    assert row["absent_days"] == 1
    assert row["rate"] == 0.25


# --------------------------------------------------------------------- empty & scoping
def test_empty_company_returns_zeros(db, company):
    from app.models import Company

    empty = Company(name="Zero Co")
    db.add(empty)
    db.flush()

    start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)
    a = admin_summary(db, empty.id, start, end)
    assert a["active_headcount"] == 0
    assert a["attrition_ytd"] == 0
    assert a["payroll_cost"] == 0
    assert a["avg_salary"] == 0
    assert a["headcount_by_department"] == []
    assert a["payroll_cost_by_department"] == []
    assert a["gender_breakdown"]["female"] == 0
    assert a["tenure_months_avg"] == 0
    assert a["recent_audit"] == []

    h = hr_summary(db, empty.id, start, start)
    assert h["headcount"] == 0
    assert h["present"] == h["late"] == h["on_leave"] == 0
    assert h["pending_approvals"] == {"leave_requests": 0, "corrections": 0}
    assert h["absenteeism_by_department"] == []
    assert h["leave_utilization"] == []
    assert h["top_late_comers"] == []
    assert 3 <= len(h["insights"]) <= 5
    assert h["attendance_trend"], "trend must still render (zero-filled)"
    assert all(
        t["present"] == t["late"] == t["absent"] == 0 for t in h["attendance_trend"]
    )

    e = employee_summary(db, empty.id, None)
    assert e["today_status"] == "not_checked_in"
    assert e["week_hours"] == 0
    assert e["leave_balances"] == []
    assert e["last_payslip"] is None
    assert employee_summary(db, empty.id, 424242)["today_status"] == "not_checked_in"


def test_employee_me_summary_own_data_only(
    client, db, company, admin_headers, hr_headers, emp_headers
):
    cid = company["company"].id
    sara = company["employee"]
    hira = company["hr_employee"]
    from app.services.analytics import _today

    today = _today(db, cid)  # same clock the service uses (company timezone)
    monday = today - dt.timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # seed this-month late row + today's row for Sara
    if month_start == today:
        _seed_att(db, cid, sara.id, today, "late", 8.0)
        expected_status = "late"
        expected_week_hours = 8.0  # today is inside this week by definition
    else:
        _seed_att(db, cid, sara.id, month_start, "late", 8.0)
        _seed_att(db, cid, sara.id, today, "present", 8.0)
        expected_status = "present"
        expected_week_hours = 8.0 + (8.0 if monday <= month_start <= today else 0.0)

    # Hira has approved leave this year — Sara must NOT see it
    from app.models import LeaveType

    annual = db.query(LeaveType).filter(
        LeaveType.company_id == cid, LeaveType.code == "ANNUAL"
    ).one()
    year = today.year
    db.add(
        LeaveRequest(
            company_id=cid,
            employee_id=hira.id,
            leave_type_id=annual.id,
            start_date=dt.date(year, 9, 7),
            end_date=dt.date(year, 9, 8),
            working_days=2,
            reason="vacation",
            status="approved",
        )
    )
    db.commit()

    # a finalized payslip for both (Feb 2025, fully attended)
    from tests.test_payroll import _finalized_run_with_full_attendance

    _finalized_run_with_full_attendance(client, db, company, hr_headers, admin_headers)

    # one announcement company-wide
    resp = client.post(
        "/api/announcements",
        json={"title": "Town hall", "body": "Friday 3pm"},
        headers=hr_headers,
    )
    assert resp.status_code == 201

    sara_view = client.get("/api/analytics/employee/me", headers=emp_headers)
    assert sara_view.status_code == 200
    sara_data = sara_view.json()
    assert sara_data["today_status"] == expected_status
    assert sara_data["week_hours"] == expected_week_hours
    assert sara_data["week_hours_target"] == 40
    assert sara_data["late_count_this_month"] >= 1
    assert sara_data["announcement_count"] == 1
    assert sara_data["last_payslip"] == {
        "id": sara_data["last_payslip"]["id"],
        "period": "2025-02",
        "net_pay": 140000,
    }
    assert sara_data["recent_attendance"], "today's row should be listed"
    assert sara_data["recent_attendance"][0]["date"] == today.isoformat()
    bal = {b["code"]: b for b in sara_data["leave_balances"]}
    assert bal["ANNUAL"]["quota"] == 14
    assert bal["ANNUAL"]["used"] == 0       # own data only — Hira's leave not visible
    assert bal["UNPAID"]["quota"] is None

    hr_data = client.get("/api/analytics/employee/me", headers=hr_headers).json()
    hr_bal = {b["code"]: b for b in hr_data["leave_balances"]}
    assert hr_bal["ANNUAL"]["used"] == 2     # Hira's own approved leave
    assert hr_data["last_payslip"]["net_pay"] == 165500  # own payslip, not Sara's

    admin_data = client.get("/api/analytics/employee/me", headers=admin_headers).json()
    assert admin_data["today_status"] == "not_checked_in"
    assert admin_data["leave_balances"] == []
    assert admin_data["last_payslip"] is None
