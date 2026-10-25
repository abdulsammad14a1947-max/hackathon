"""CSV bulk employee import with dry-run validation (multipart upload).

Expected columns (header row, UTF-8):
    employee_code,first_name,last_name,email,department,designation,
    joining_date,basic_salary[,gender,phone]
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Department, Designation, Employee, User
from app.services import employee_service as emp_svc
from app.services.employee_service import normalize_email
from app.utils.audit import record_audit

BASE_COLUMNS = [
    "employee_code",
    "first_name",
    "last_name",
    "email",
    "department",
    "designation",
    "joining_date",
    "basic_salary",
]
OPTIONAL_COLUMNS = ["gender", "phone"]
REQUIRED_VALUE_COLUMNS = [
    "employee_code",
    "first_name",
    "email",
    "department",
    "joining_date",
    "basic_salary",
]
EXPORT_COLUMNS = [
    "employee_code",
    "first_name",
    "last_name",
    "email",
    "phone",
    "department",
    "designation",
    "joining_date",
    "employment_status",
    "gender",
    "basic_salary",
]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GENDERS = {"male", "female", "other"}


def _parse(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Decode + parse the CSV. Raises 422 with a clear detail on structural problems."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="CSV file must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=422, detail="CSV file is empty")
    headers = [str(h).strip() for h in reader.fieldnames]
    missing = [c for c in BASE_COLUMNS if c not in headers]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=[f"Missing required column: {name}" for name in missing],
        )

    rows: list[dict[str, str]] = []
    for raw_row in reader:
        row = {
            str(k).strip(): ("" if v is None else str(v).strip())
            for k, v in raw_row.items()
            if k is not None
        }
        if not any(row.values()):
            continue  # skip blank lines
        rows.append(row)
    if not rows:
        raise HTTPException(status_code=422, detail="CSV file has no data rows")
    return headers, rows


def _lookup_maps(db: Session, company_id: int) -> tuple[dict[str, int], dict[str, int]]:
    departments = {
        r.name.strip().lower(): r.id
        for r in db.query(Department).filter(Department.company_id == company_id).all()
    }
    designations = {
        r.name.strip().lower(): r.id
        for r in db.query(Designation).filter(Designation.company_id == company_id).all()
    }
    return departments, designations


def _validate_row(
    row: dict[str, str],
    *,
    row_number: int,
    departments: dict[str, int],
    designations: dict[str, int],
    seen_codes: dict[str, int],
    seen_emails: dict[str, int],
    db_codes: set[str],
    db_emails: set[str],
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    """Return (errors, normalized data-or-None)."""
    errors: list[dict[str, str]] = []

    def err(field: str, reason: str) -> None:
        errors.append({"field": field, "reason": reason})

    data: dict[str, Any] = {}

    code = row.get("employee_code", "")
    if not code:
        err("employee_code", "required")
    elif code in seen_codes:
        err("employee_code", f"duplicate of row {seen_codes[code]} in this file")
    elif code in db_codes:
        err("employee_code", "employee code already exists")
    else:
        data["employee_code"] = code

    first = row.get("first_name", "")
    if not first:
        err("first_name", "required")
    else:
        data["first_name"] = first

    data["last_name"] = row.get("last_name", "") or None

    email = normalize_email(row.get("email", ""))
    if not email:
        err("email", "required")
    elif not _EMAIL_RE.match(email):
        err("email", "invalid email address")
    elif email in seen_emails:
        err("email", f"duplicate of row {seen_emails[email]} in this file")
    elif email in db_emails:
        err("email", "email already exists")
    else:
        data["email"] = email

    dept_name = row.get("department", "")
    if not dept_name:
        err("department", "required")
    elif dept_name.strip().lower() not in departments:
        err("department", f"department '{dept_name}' does not exist")
    else:
        data["department_id"] = departments[dept_name.strip().lower()]

    desig_name = row.get("designation", "")
    if desig_name:
        if desig_name.strip().lower() not in designations:
            err("designation", f"designation '{desig_name}' does not exist")
        else:
            data["designation_id"] = designations[desig_name.strip().lower()]
    else:
        data["designation_id"] = None

    date_text = row.get("joining_date", "")
    if not date_text:
        err("joining_date", "required")
    else:
        try:
            data["joining_date"] = dt.date.fromisoformat(date_text)
        except ValueError:
            err("joining_date", "must be an ISO date (YYYY-MM-DD)")

    salary_text = row.get("basic_salary", "")
    if not salary_text:
        err("basic_salary", "required")
    else:
        try:
            salary = float(salary_text.replace(",", ""))
        except ValueError:
            err("basic_salary", "must be a number greater than 0")
        else:
            if salary <= 0:
                err("basic_salary", "must be greater than 0")
            else:
                data["basic_salary"] = salary

    gender = row.get("gender", "")
    if gender:
        if gender.strip().lower() not in _GENDERS:
            err("gender", "must be one of male, female, other")
        else:
            data["gender"] = gender.strip().lower()

    data["phone"] = row.get("phone", "") or None

    if not errors:
        # Only fully-valid rows claim their code/email within this file.
        seen_codes[data["employee_code"]] = row_number
        seen_emails[data["email"]] = row_number

    return errors, (data if not errors else None)


def process_import(
    db: Session,
    company_id: int,
    raw: bytes,
    *,
    dry_run: bool,
    role: str = "employee",
    actor: User | None = None,
) -> dict[str, Any]:
    _, rows = _parse(raw)
    departments, designations = _lookup_maps(db, company_id)

    db_codes = {
        r[0]
        for r in db.query(Employee.employee_code)
        .filter(Employee.company_id == company_id)
        .all()
    }
    db_emails = {
        (r[0] or "").lower()
        for r in db.query(Employee.email)
        .filter(Employee.company_id == company_id)
        .all()
    }
    db_emails |= {
        (r[0] or "").lower() for r in db.query(User.email).all()
    }  # emails are globally unique logins

    seen_codes: dict[str, int] = {}
    seen_emails: dict[str, int] = {}

    results: list[dict[str, Any]] = []
    valid: list[tuple[int, dict[str, Any]]] = []

    for index, row in enumerate(rows, start=1):
        errors, data = _validate_row(
            row,
            row_number=index,
            departments=departments,
            designations=designations,
            seen_codes=seen_codes,
            seen_emails=seen_emails,
            db_codes=db_codes,
            db_emails=db_emails,
        )
        if data is not None:
            valid.append((index, data))
            results.append({"row": index, "errors": []})
        else:
            results.append({"row": index, "errors": errors})

    valid_count = len(valid)
    error_count = len(results) - valid_count

    if dry_run:
        return {
            "dry_run": True,
            "rows": results,
            "valid_count": valid_count,
            "error_count": error_count,
            "would_create": valid_count,
        }

    # Real import: persist every valid row in ONE transaction.
    created = 0
    by_row = {r["row"]: r for r in results}
    try:
        for index, data in valid:
            emp, temp_password = emp_svc.create_employee(
                db, company_id, data, role=role, actor=actor, commit=False
            )
            by_row[index].update(
                {
                    "created": True,
                    "employee_code": emp.employee_code,
                    "temp_password": temp_password,
                }
            )
            created += 1
        record_audit(
            db,
            company_id=company_id,
            user=actor,
            action="employee_import",
            entity_type="employee",
            after={"created": created, "invalid_rows": error_count, "dry_run": False},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Import aborted: a conflicting record was written concurrently",
        ) from exc

    for result in results:
        result.setdefault("created", False)
        result.setdefault("employee_code", None)
        result.setdefault("temp_password", None)

    return {
        "dry_run": False,
        "rows": results,
        "valid_count": valid_count,
        "error_count": error_count,
        "created_count": created,
    }


def export_csv(db: Session, company_id: int) -> str:
    """Render the company directory as CSV text (for the export endpoint)."""
    rows = (
        db.query(Employee)
        .filter(Employee.company_id == company_id)
        .order_by(Employee.employee_code.asc())
        .all()
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for emp in rows:
        writer.writerow(
            [
                emp.employee_code,
                emp.first_name,
                emp.last_name or "",
                emp.email,
                emp.phone or "",
                emp.department.name if emp.department else "",
                emp.designation.name if emp.designation else "",
                emp.joining_date.isoformat() if emp.joining_date else "",
                emp.employment_status,
                emp.gender or "",
                float(emp.basic_salary) if emp.basic_salary is not None else "",
            ]
        )
    return buffer.getvalue()
