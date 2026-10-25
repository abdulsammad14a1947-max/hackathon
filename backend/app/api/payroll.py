"""Payroll Lite endpoints (M6) — see ARCHITECTURE §4 "Payroll".
Role matrix (per brief #14–#17, frozen in ARCHITECTURE):
    POST   /salary-structures      HR only        (Admin is view-only → 403)
    GET    /salary-structures      HR + Admin
    POST   /runs                   HR only        (Admin is view-only → 403)
    GET    /runs[/{id}[,/items]]   HR + Admin
    POST   /runs/{id}/finalize     Admin only     (HR → 403)
    GET    /payslips/me            any role, own data only
    GET    /payslips/{id}/pdf      owner or HR/Admin
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin, require_hr, require_roles
from app.models import Employee, PayrollItem, SalaryStructure, User
from app.schemas.payroll import (
    PayrollRunCreate,
    PayrollRunPage,
    PayrollRunOut,
    PayslipPage,
    SalaryStructureCreate,
    SalaryStructureOut,
    SalaryStructurePage,
)
from app.services import pdf_service, payroll_service
from app.utils.audit import record_audit, serialize as audit_serialize

router = APIRouter(prefix="/api/payroll", tags=["payroll"])


# ---------------------------------------------------------------- salary structures
@router.post(
    "/salary-structures",
    response_model=SalaryStructureOut,
    status_code=201,
    summary="Create a salary structure (HR only)",
)
def create_salary_structure(
    payload: SalaryStructureCreate,
    user: User = Depends(require_roles("hr")),  # brief matrix #14: HR Manage, Admin View
    db: Session = Depends(get_db),
) -> SalaryStructureOut:
    if payload.effective_to is not None and payload.effective_to < payload.effective_from:
        raise HTTPException(
            status_code=422, detail="effective_to must be on or after effective_from"
        )
    employee = db.get(Employee, payload.employee_id)
    if employee is None or employee.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Employee not found")

    row = SalaryStructure(
        company_id=user.company_id,
        employee_id=employee.id,
        basic_salary=payload.basic_salary,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="salary_structure.created",
        entity_type="salary_structure",
        entity_id=row.id,
        after=audit_serialize(row),
    )
    db.commit()
    db.refresh(row)
    return _structure_out(row, employee)


@router.get(
    "/salary-structures",
    response_model=SalaryStructurePage,
    summary="List salary structures (HR+Admin)",
)
def list_salary_structures(
    employee_id: int | None = Query(default=None),
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
) -> SalaryStructurePage:
    q = db.query(SalaryStructure).filter(SalaryStructure.company_id == user.company_id)
    if employee_id is not None:
        q = q.filter(SalaryStructure.employee_id == employee_id)
    rows = q.order_by(
        SalaryStructure.employee_id.asc(), SalaryStructure.effective_from.desc()
    ).all()
    items = []
    for row in rows:
        employee = db.get(Employee, row.employee_id)
        items.append(_structure_out(row, employee))
    return SalaryStructurePage(items=items, total=len(items))


def _structure_out(row: SalaryStructure, employee: Employee | None) -> SalaryStructureOut:
    department = None
    name = None
    code = None
    if employee is not None:
        code = employee.employee_code
        name = f"{employee.first_name} {employee.last_name or ''}".strip()
        if employee.department is not None:
            department = employee.department.name
    return SalaryStructureOut(
        id=row.id,
        employee_id=row.employee_id,
        basic_salary=float(row.basic_salary),
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        employee_code=code,
        employee_name=name,
        department=department,
    )


# ---------------------------------------------------------------- payroll runs
@router.post(
    "/runs",
    response_model=PayrollRunOut,
    status_code=201,
    summary="Generate (or regenerate) the draft payroll run for a month (HR only)",
)
def create_payroll_run(
    payload: PayrollRunCreate,
    user: User = Depends(require_roles("hr")),  # brief matrix #15: HR Manage, Admin View
    db: Session = Depends(get_db),
) -> PayrollRunOut:
    # Service enforces: finalized run for the same period → 409; regeneration of a
    # draft replaces its items; all inside ONE transaction.
    run = payroll_service.generate_draft_run(db, user, payload.year, payload.month)
    return PayrollRunOut(**payroll_service.serialize_run(db, run))


@router.get(
    "/runs",
    response_model=PayrollRunPage,
    summary="List payroll runs, newest period first (HR+Admin)",
)
def list_payroll_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
) -> PayrollRunPage:
    data = payroll_service.list_runs(db, user.company_id, page=page, page_size=page_size)
    return PayrollRunPage(
        items=[PayrollRunOut(**row) for row in data["items"]],
        total=data["total"],
        page=data["page"],
        page_size=data["page_size"],
    )


@router.get(
    "/runs/{run_id}",
    response_model=PayrollRunOut,
    summary="Payroll run detail with totals (HR+Admin)",
)
def get_payroll_run(
    run_id: int,
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
) -> PayrollRunOut:
    run = payroll_service.get_run(db, user.company_id, run_id)
    return PayrollRunOut(**payroll_service.serialize_run(db, run))


@router.get(
    "/runs/{run_id}/items",
    response_model=list[dict],
    summary="Payroll run items (HR+Admin)",
)
def list_payroll_run_items(
    run_id: int,
    user: User = Depends(require_hr),
    db: Session = Depends(get_db),
) -> list[dict]:
    run = payroll_service.get_run(db, user.company_id, run_id)
    return payroll_service.list_run_items(db, user.company_id, run)


@router.post(
    "/runs/{run_id}/finalize",
    response_model=PayrollRunOut,
    summary="Finalize (lock) a payroll run — Admin only",
)
def finalize_payroll_run(
    run_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PayrollRunOut:
    run = payroll_service.get_run(db, user.company_id, run_id)
    # finalize_run raises 409 when already finalized (immutability).
    run = payroll_service.finalize_run(db, user, run)
    return PayrollRunOut(**payroll_service.serialize_run(db, run))


# ---------------------------------------------------------------- payslips
@router.get(
    "/payslips/me",
    response_model=PayslipPage,
    summary="My finalized payslips (own employee only)",
)
def my_payslips(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PayslipPage:
    items = payroll_service.payslips_for_user(db, user)
    return PayslipPage(items=items, total=len(items))


@router.get(
    "/payslips/{item_id}/pdf",
    summary="Download payslip PDF (owner or HR/Admin)",
)
def payslip_pdf(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    item = db.get(PayrollItem, item_id)
    if item is None or item.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Payslip not found")
    if user.role == "employee" and item.employee_id != user.employee_id:
        raise HTTPException(status_code=403, detail="Access denied to other employee payslips")
    # pdf_service validates the run is finalized (payslip = finalized item only)
    ctx = pdf_service.payslip_context(db, item.id)
    pdf_bytes = pdf_service.build_payslip_pdf(db, item.id)
    filename = pdf_service.payslip_filename(ctx)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
