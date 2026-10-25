"""Payslip PDF rendering (reportlab) — pure functions, no HTTP concerns.

`payslip_context(db, item_id)` maps a finalized payroll item to the display data
(unit-testable without reportlab); `build_payslip_pdf(db, item_id) -> bytes`
renders the PDF document.
"""
from __future__ import annotations

import datetime as dt
import io

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Company, Employee, PayrollItem, PayrollRun
from app.services.payroll_service import MONTH_NAMES, _f


def payslip_context(db: Session, item_id: int) -> dict:
    """Resolve everything the payslip shows. Raises 404 when unknown.

    Returns:
        {
          company_name, period_label, period_year, period_month, generated_date,
          employee: {code, name, email, department, designation},
          earnings: {basic, hra, medical, gross},
          deductions: {absence_unpaid_half, tax},
          days: {working, present, absent, unpaid_leave, half},
          net_pay, note
        }
    """
    item = db.get(PayrollItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payslip not found")
    run = db.get(PayrollRun, item.run_id)
    if run is None or run.company_id != item.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payslip not found")
    if run.status != "finalized":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payslip is only available for finalized payroll runs",
        )
    emp = db.get(Employee, item.employee_id)
    if emp is None or emp.company_id != item.company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payslip not found")
    company = db.get(Company, item.company_id)

    department = emp.department.name if emp.department is not None else "-"
    designation = emp.designation.name if emp.designation is not None else "-"
    name = f"{emp.first_name} {emp.last_name or ''}".strip()

    return {
        "company_name": company.name if company is not None else "",
        "period_label": f"{MONTH_NAMES[run.period_month - 1]} {run.period_year}",
        "period_year": run.period_year,
        "period_month": run.period_month,
        "generated_date": (run.finalized_at or dt.datetime.utcnow()).strftime("%Y-%m-%d"),
        "employee": {
            "code": emp.employee_code,
            "name": name,
            "email": emp.email,
            "department": department,
            "designation": designation,
        },
        "earnings": {
            "basic": _f(item.basic),
            "hra": _f(item.hra),
            "medical": _f(item.medical),
            "gross": _f(item.gross),
        },
        "deductions": {
            "absence_unpaid_half": _f(item.deduction_amount),
            "tax": _f(item.tax),
        },
        "days": {
            "working": _f(item.working_days),
            "present": _f(item.present_days),
            "absent": _f(item.absent_days),
            "unpaid_leave": _f(item.unpaid_leave_days),
            "half": _f(item.half_days),
        },
        "net_pay": _f(item.net_pay),
        "note": item.note,
    }


def payslip_filename(ctx: dict) -> str:
    """payslip_<code>_<year>_<month>.pdf with a filesystem-safe employee code."""
    import re

    code = re.sub(r"[^A-Za-z0-9_-]", "_", str(ctx["employee"]["code"] or "employee"))
    return f"payslip_{code}_{ctx['period_year']}_{ctx['period_month']:02d}.pdf"


def build_payslip_pdf(db: Session, item_id: int) -> bytes:
    """Render the payslip PDF for a finalized payroll item (pure function → bytes)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    ctx = payslip_context(db, item_id)

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    def money(value: float) -> str:
        return f"{value:,.2f}"

    y = height - 25 * mm

    # Header ---------------------------------------------------------------
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, y, ctx["company_name"] or "Company")
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Payslip")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - 20 * mm, y, f"Period: {ctx['period_label']}")
    y -= 6 * mm
    c.drawRightString(width - 20 * mm, y, f"Generated: {ctx['generated_date']}")
    y -= 10 * mm

    # Employee block --------------------------------------------------------
    emp = ctx["employee"]
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Employee")
    y -= 5.5 * mm
    c.setFont("Helvetica", 10)
    details = [
        f"Code: {emp['code']}",
        f"Name: {emp['name']}",
        f"Department: {emp['department']}    Designation: {emp['designation']}",
        f"Email: {emp['email']}",
    ]
    for line in details:
        c.drawString(20 * mm, y, line)
        y -= 5.5 * mm
    y -= 4 * mm

    # Tables ----------------------------------------------------------------
    left_x = 20 * mm
    col_w = (width - 40 * mm) / 2

    def table(x0: float, title: str, rows: list[tuple[str, str]], y0: float) -> float:
        yy = y0
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x0, yy, title)
        yy -= 6 * mm
        c.setLineWidth(0.5)
        c.setStrokeColor(colors.grey)
        c.setFont("Helvetica", 10)
        for label, value in rows:
            c.drawString(x0, yy, label)
            c.drawRightString(x0 + col_w - 4 * mm, yy, value)
            c.line(x0, yy - 1.6 * mm, x0 + col_w - 4 * mm, yy - 1.6 * mm)
            yy -= 6 * mm
        return yy

    earnings = ctx["earnings"]
    y_left = table(
        left_x,
        "Earnings",
        [
            ("Basic", money(earnings["basic"])),
            ("HRA (40%)", money(earnings["hra"])),
            ("Medical (10%)", money(earnings["medical"])),
            ("Gross", money(earnings["gross"])),
        ],
        y,
    )
    deductions = ctx["deductions"]
    y_right = table(
        left_x + col_w,
        "Deductions",
        [
            ("Absence / unpaid / half-day", money(deductions["absence_unpaid_half"])),
            ("Income tax", money(deductions["tax"])),
            ("Total deductions", money(deductions["absence_unpaid_half"] + deductions["tax"])),
        ],
        y,
    )
    y = min(y_left, y_right) - 4 * mm

    # Days summary ----------------------------------------------------------
    days = ctx["days"]
    c.setFont("Helvetica-Bold", 11)
    c.drawString(left_x, y, "Attendance summary")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    c.drawString(
        left_x,
        y,
        f"Working days: {days['working']:g}    Present: {days['present']:g}    "
        f"Absent: {days['absent']:g}    Unpaid leave: {days['unpaid_leave']:g}    "
        f"Half days: {days['half']:g}",
    )
    y -= 12 * mm

    # Net pay ---------------------------------------------------------------
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.rect(left_x, y - 6 * mm, width - 40 * mm, 12 * mm, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(left_x + 4 * mm, y, "Net pay")
    c.drawRightString(width - 24 * mm, y, f"{money(ctx['net_pay'])}")
    y -= 14 * mm

    if ctx.get("note"):
        c.setFont("Helvetica-Oblique", 8.5)
        c.drawString(left_x, y, f"Note: {ctx['note']}")
        y -= 5 * mm

    c.setFont("Helvetica", 8)
    c.drawString(
        left_x,
        12 * mm,
        "This payslip was generated electronically by HCM Lite.",
    )

    c.showPage()
    c.save()
    return buffer.getvalue()
