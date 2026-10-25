"""M6 Payroll Lite tests — formulas, immutability, permissions, payslips, PDF.

Fixtures come from tests/conftest.py: client, db, company, admin_headers,
hr_headers, emp_headers.
"""
from __future__ import annotations

import datetime as dt

import pytest
from fastapi import HTTPException

from app.models import (
    Attendance,
    AuditLog,
    Notification,
    PayrollItem,
    PayrollRun,
    SalaryStructure,
    User,
)
from app.services.calendar_utils import (
    get_settings,
    holiday_map,
    is_working_day,
    iter_days,
    month_date_range,
)
from app.services.payroll_service import compute_annual_tax, monthly_tax_for_gross
from app.services.pdf_service import payslip_context

# Fixtures (client, db, company, admin_headers, hr_headers, emp_headers) come
# from tests/conftest.py.


# --------------------------------------------------------------------- helpers
def _working_days(db, company_id: int, year: int, month: int) -> list[dt.date]:
    settings = get_settings(db, company_id)
    holidays = holiday_map(db, company_id)
    start, end = month_date_range(year, month)
    return [d for d in iter_days(start, end) if is_working_day(d, settings, holidays)]


def _seed_attendance(db, company_id, employee_id, dates, status="present", hours=8.0):
    for day in dates:
        db.add(
            Attendance(
                company_id=company_id,
                employee_id=employee_id,
                date=day,
                status=status,
                worked_hours=hours,
            )
        )
    db.commit()


def _create_run(client, headers, year: int, month: int):
    resp = client.post(
        "/api/payroll/runs", json={"year": year, "month": month}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _items(client, headers, run_id: int) -> list[dict]:
    resp = client.get(f"/api/payroll/runs/{run_id}/items", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _item_for(items: list[dict], employee_id: int) -> dict:
    return next(i for i in items if i["employee_id"] == employee_id)


# --------------------------------------------------------------------- formulas
def test_allowances_and_gross_and_per_day(client, db, company, hr_headers):
    """basic 100000 → hra 40000, medical 10000, gross 150000; Feb-2025 = 20 w-days."""
    cid = company["company"].id
    sara = company["employee"]
    days = _working_days(db, cid, 2025, 2)
    assert len(days) == 20  # Feb 2025, Sat/Sun off, no seeded holidays
    _seed_attendance(db, cid, sara.id, days)  # fully attended month

    run = _create_run(client, hr_headers, 2025, 2)
    sara_item = _item_for(_items(client, hr_headers, run["id"]), sara.id)

    assert sara_item["basic"] == 100000
    assert sara_item["hra"] == 40000          # 40%
    assert sara_item["medical"] == 10000      # 10%
    assert sara_item["gross"] == 150000       # 1.5 × basic
    assert sara_item["working_days"] == 20
    assert sara_item["absent_days"] == 0
    # per-day = 150000 / 20 = 7500; tax = slab(1.8M)/12 = 120000/12 = 10000
    assert sara_item["tax"] == 10000
    assert sara_item["net_pay"] == 140000     # 150000 − 0 − 10000

    # run totals: both employees have rows (Sara + Hira)
    detail = client.get(f"/api/payroll/runs/{run['id']}", headers=hr_headers).json()
    assert detail["item_count"] == 2
    assert detail["status"] == "draft"
    assert detail["total_gross"] > 0
    assert detail["total_net"] > 0

    # Hira has no attendance rows → full absence; net clamps at 0 with a note
    hira_item = _item_for(_items(client, hr_headers, run["id"]), company["hr_employee"].id)
    assert hira_item["absent_days"] == 20
    assert hira_item["net_pay"] == 0
    assert hira_item["note"] and "net pay clamped to 0" in hira_item["note"]


def test_absence_deduction_uses_per_day(client, db, company, hr_headers):
    cid = company["company"].id
    sara = company["employee"]
    days = _working_days(db, cid, 2025, 2)
    _seed_attendance(db, cid, sara.id, days[:10])  # 10 present, 10 with no record

    run = _create_run(client, hr_headers, 2025, 2)
    item = _item_for(_items(client, hr_headers, run["id"]), sara.id)

    assert item["absent_days"] == 10
    assert item["deduction_amount"] == 75000      # 10 × (150000/20)
    assert item["net_pay"] == 65000               # 150000 − 75000 − 10000


def test_leave_deduction_paid_vs_unpaid(client, db, company, hr_headers):
    from app.models import LeaveType

    cid = company["company"].id
    sara = company["employee"]
    days = _working_days(db, cid, 2025, 2)
    unpaid_dates = days[0:2]
    paid_dates = days[2:4]
    other = [d for d in days if d not in set(unpaid_dates) | set(paid_dates)]
    _seed_attendance(db, cid, sara.id, other)

    unpaid = db.query(LeaveType).filter(
        LeaveType.company_id == cid, LeaveType.code == "UNPAID"
    ).one()
    annual = db.query(LeaveType).filter(
        LeaveType.company_id == cid, LeaveType.code == "ANNUAL"
    ).one()

    from app.models import LeaveRequest

    for ltype, dates in ((unpaid, unpaid_dates), (annual, paid_dates)):
        db.add(
            LeaveRequest(
                company_id=cid,
                employee_id=sara.id,
                leave_type_id=ltype.id,
                start_date=dates[0],
                end_date=dates[1],
                working_days=2,
                reason="test",
                status="approved",
            )
        )
    db.commit()

    run = _create_run(client, hr_headers, 2025, 2)
    item = _item_for(_items(client, hr_headers, run["id"]), sara.id)

    assert item["unpaid_leave_days"] == 2
    assert item["absent_days"] == 0            # paid + unpaid leave days are not absent
    assert item["deduction_amount"] == 15000   # 2 × 7500 only (paid leave not deducted)
    assert item["net_pay"] == 125000           # 150000 − 15000 − 10000


def test_joiner_proration_mid_month(client, db, company, hr_headers):
    """Sara joins 2025-01-15 → eligible 13 of 23 working days in January."""
    cid = company["company"].id
    sara = company["employee"]
    assert str(sara.joining_date) == "2025-01-15"
    jan_days = _working_days(db, cid, 2025, 1)
    eligible = [d for d in jan_days if d >= dt.date(2025, 1, 15)]
    assert len(jan_days) == 23
    assert len(eligible) == 13
    _seed_attendance(db, cid, sara.id, eligible)  # worked every eligible day

    run = _create_run(client, hr_headers, 2025, 1)
    item = _item_for(_items(client, hr_headers, run["id"]), sara.id)

    assert item["working_days"] == 23
    assert item["absent_days"] == 0             # absence only counted in eligible window
    assert item["note"] is not None and "Prorated 13/23" in item["note"]
    adjusted = round(150000 / 23 * 13, 2)       # per_day × eligible_days
    assert item["net_pay"] == round(adjusted - 10000, 2)


def test_tax_slab_boundaries():
    """Every slab edge from the brief (frozen formulas)."""
    assert compute_annual_tax(599999) == 0
    assert compute_annual_tax(600000) == 0
    assert compute_annual_tax(600001) == 0.05
    assert compute_annual_tax(1_200_000) == 30000
    assert compute_annual_tax(1_200_001) == 30000.15
    assert compute_annual_tax(2_400_000) == 210000
    assert compute_annual_tax(2_400_001) == 210000.25
    assert compute_annual_tax(3_600_000) == 510000
    assert compute_annual_tax(3_600_001) == 510000.35
    # monthly helper: gross 150000 → annual 1.8M → (30000 + 15%×600k)/12
    assert monthly_tax_for_gross(150000) == 10000


# --------------------------------------------------------------------- salary structures
def test_salary_structure_validation_and_roles(client, db, company, hr_headers, emp_headers, admin_headers):
    cid = company["company"].id
    sara = company["employee"]

    # validation: basic_salary must be > 0 (422)
    bad = client.post(
        "/api/payroll/salary-structures",
        json={"employee_id": sara.id, "basic_salary": 0},
        headers=hr_headers,
    )
    assert bad.status_code == 422

    # employee role cannot create (403)
    forbidden = client.post(
        "/api/payroll/salary-structures",
        json={"employee_id": sara.id, "basic_salary": 150000},
        headers=emp_headers,
    )
    assert forbidden.status_code == 403

    resp = client.post(
        "/api/payroll/salary-structures",
        json={
            "employee_id": sara.id,
            "basic_salary": 150000,
            "effective_from": "2025-03-01",
        },
        headers=hr_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["basic_salary"] == 150000
    assert body["employee_code"] == "EMP-001"

    # audit recorded
    db.expire_all()
    entries = (
        db.query(AuditLog)
        .filter(AuditLog.action == "salary_structure.created")
        .all()
    )
    assert len(entries) == 1
    assert entries[0].actor_email == "hr@acme.test"
    assert entries[0].created_at is not None

    # listing with filter
    lst = client.get(
        f"/api/payroll/salary-structures?employee_id={sara.id}", headers=hr_headers
    )
    assert lst.status_code == 200
    assert lst.json()["total"] == 1

    # effective structure wins over employee.basic_salary for March 2025
    run = _create_run(client, hr_headers, 2025, 3)
    item = _item_for(_items(client, hr_headers, run["id"]), sara.id)
    assert item["basic"] == 150000
    assert item["hra"] == 60000
    assert item["medical"] == 15000
    assert item["gross"] == 225000

    # Admin is view-only for salary structures per brief matrix #14 (ARCHITECTURE §4)
    admin_create = client.post(
        "/api/payroll/salary-structures",
        json={"employee_id": sara.id, "basic_salary": 160000},
        headers=admin_headers,
    )
    assert admin_create.status_code == 403
    # ...but Admin can read
    assert client.get("/api/payroll/salary-structures", headers=admin_headers).status_code == 200


# --------------------------------------------------------------------- runs & immutability
def test_list_runs_newest_first_and_employee_denied(
    client, db, company, hr_headers, emp_headers, admin_headers
):
    _create_run(client, hr_headers, 2025, 1)
    _create_run(client, hr_headers, 2025, 2)

    resp = client.get("/api/payroll/runs?page=1", headers=hr_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert [r["period_month"] for r in data["items"]] == [2, 1]  # newest period first
    assert all("item_count" in r for r in data["items"])

    page1 = client.get("/api/payroll/runs?page=1&page_size=1", headers=hr_headers).json()
    assert page1["total"] == 2 and len(page1["items"]) == 1

    # employees cannot list runs
    assert client.get("/api/payroll/runs", headers=emp_headers).status_code == 403

    # brief matrix #15: Admin is view-only for drafts (HR Manage) → 403 on create
    admin_create = client.post(
        "/api/payroll/runs", json={"year": 2025, "month": 3}, headers=admin_headers
    )
    assert admin_create.status_code == 403


def test_draft_regeneration_replaces_items(client, db, company, hr_headers):
    cid = company["company"].id
    sara = company["employee"]
    days = _working_days(db, cid, 2025, 2)

    first = _create_run(client, hr_headers, 2025, 2)
    first_item = _item_for(_items(client, hr_headers, first["id"]), sara.id)
    assert first_item["absent_days"] == 20  # no attendance seeded yet

    _seed_attendance(db, cid, sara.id, days)  # now fully attended
    second = _create_run(client, hr_headers, 2025, 2)  # regenerate same period

    assert second["id"] == first["id"]  # unique (company, year, month) reused
    runs = client.get("/api/payroll/runs", headers=hr_headers).json()
    assert runs["total"] == 1  # items replaced, not duplicated
    again = _item_for(_items(client, hr_headers, second["id"]), sara.id)
    assert again["absent_days"] == 0


def test_hr_cannot_finalize_admin_can_and_immutable(
    client, db, company, hr_headers, admin_headers
):
    run = _create_run(client, hr_headers, 2025, 2)

    # HR finalize → 403 (Admin only)
    hr_fin = client.post(f"/api/payroll/runs/{run['id']}/finalize", headers=hr_headers)
    assert hr_fin.status_code == 403

    # Admin finalize → 200
    ok = client.post(f"/api/payroll/runs/{run['id']}/finalize", headers=admin_headers)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "finalized"
    assert ok.json()["finalized_by"] is not None

    # already finalized → 409
    again = client.post(f"/api/payroll/runs/{run['id']}/finalize", headers=admin_headers)
    assert again.status_code == 409

    # regenerating a FINALIZED period → 409 (immutability enforced in service)
    regen = client.post(
        "/api/payroll/runs", json={"year": 2025, "month": 2}, headers=hr_headers
    )
    assert regen.status_code == 409

    # audit row with before/after
    db.expire_all()
    entries = db.query(AuditLog).filter(AuditLog.action == "payroll.finalized").all()
    assert len(entries) == 1
    assert entries[0].actor_email == "admin@acme.test"
    assert entries[0].entity_type == "payroll_run"
    assert entries[0].before["status"] == "draft"
    assert entries[0].after["status"] == "finalized"
    assert entries[0].created_at is not None

    # every employee with an item got a payslip-ready notification
    notes = (
        db.query(Notification)
        .filter(Notification.title == "Your payslip for February 2025 is ready")
        .all()
    )
    assert len(notes) == 2  # Sara + Hira
    assert all(n.link == "/payslips" for n in notes)
    assert all(n.created_at is not None for n in notes)
    notified_user_ids = {n.user_id for n in notes}
    sara_user = db.query(User).filter(User.email == "sara@acme.test").one()
    assert sara_user.id in notified_user_ids


def test_employee_denied_run_endpoints(client, db, company, emp_headers):
    run_owner_view = client.get("/api/payroll/runs", headers=emp_headers)
    assert run_owner_view.status_code == 403


# --------------------------------------------------------------------- payslips
def _finalized_run_with_full_attendance(client, db, company, hr_headers, admin_headers):
    cid = company["company"].id
    days = _working_days(db, cid, 2025, 2)
    for emp_key in ("employee", "hr_employee"):
        _seed_attendance(db, cid, company[emp_key].id, days)
    run = _create_run(client, hr_headers, 2025, 2)
    resp = client.post(f"/api/payroll/runs/{run['id']}/finalize", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return run


def test_payslips_me_scoped_to_owner(client, db, company, hr_headers, admin_headers, emp_headers):
    _finalized_run_with_full_attendance(client, db, company, hr_headers, admin_headers)

    emp_view = client.get("/api/payroll/payslips/me", headers=emp_headers)
    assert emp_view.status_code == 200
    emp_items = emp_view.json()["items"]
    assert emp_items, "Sara should see her own finalized payslip"
    assert all(i["employee_id"] == company["employee"].id for i in emp_items)
    assert all(i["status"] == "finalized" for i in emp_items)
    assert emp_items[0]["period_year"] == 2025 and emp_items[0]["period_month"] == 2

    hr_view = client.get("/api/payroll/payslips/me", headers=hr_headers).json()
    assert hr_view["items"]
    assert all(i["employee_id"] == company["hr_employee"].id for i in hr_view["items"])

    admin_view = client.get("/api/payroll/payslips/me", headers=admin_headers).json()
    assert admin_view["items"] == []  # admin has no employee profile


def test_payslip_pdf_permissions_and_bytes(
    client, db, company, hr_headers, admin_headers, emp_headers
):
    run = _finalized_run_with_full_attendance(client, db, company, hr_headers, admin_headers)
    items = _items(client, hr_headers, run["id"])
    sara_item = _item_for(items, company["employee"].id)
    hira_item = _item_for(items, company["hr_employee"].id)

    # owner can download own PDF
    mine = client.get(f"/api/payroll/payslips/{sara_item['id']}/pdf", headers=emp_headers)
    assert mine.status_code == 200
    assert mine.headers["content-type"] == "application/pdf"
    assert 'payslip_EMP-001_2025_02.pdf' in mine.headers["content-disposition"]
    assert mine.content.startswith(b"%PDF")
    assert len(mine.content) > 1000

    # another employee's payslip → 403
    others = client.get(f"/api/payroll/payslips/{hira_item['id']}/pdf", headers=emp_headers)
    assert others.status_code == 403

    # HR/Admin may download any payslip in their company
    hr_pdf = client.get(f"/api/payroll/payslips/{sara_item['id']}/pdf", headers=hr_headers)
    assert hr_pdf.status_code == 200 and hr_pdf.content.startswith(b"%PDF")
    admin_pdf = client.get(f"/api/payroll/payslips/{hira_item['id']}/pdf", headers=admin_headers)
    assert admin_pdf.status_code == 200 and admin_pdf.content.startswith(b"%PDF")

    # unknown id → 404
    missing = client.get("/api/payroll/payslips/999999/pdf", headers=admin_headers)
    assert missing.status_code == 404


def test_payslip_context_data_mapping(db, company, client, hr_headers, admin_headers):
    """Unit test on the PDF data-mapping function (no PDF parsing needed)."""
    _finalized_run_with_full_attendance(client, db, company, hr_headers, admin_headers)
    db.expire_all()
    item = (
        db.query(PayrollItem)
        .join(PayrollRun, PayrollItem.run_id == PayrollRun.id)
        .filter(
            PayrollItem.employee_id == company["employee"].id,
            PayrollRun.status == "finalized",
        )
        .one()
    )
    ctx = payslip_context(db, item.id)
    assert ctx["company_name"] == "Acme Textiles"
    assert ctx["period_label"] == "February 2025"
    assert ctx["employee"]["code"] == "EMP-001"
    assert ctx["employee"]["name"] == "Sara Khan"
    assert ctx["employee"]["department"] == "Engineering"
    assert ctx["employee"]["designation"] == "Software Engineer"
    assert ctx["earnings"] == {"basic": 100000, "hra": 40000, "medical": 10000, "gross": 150000}
    assert ctx["deductions"]["tax"] == 10000
    assert ctx["net_pay"] == 140000
    assert ctx["generated_date"]

    with pytest.raises(HTTPException) as exc:
        payslip_context(db, 999999)
    assert exc.value.status_code == 404
