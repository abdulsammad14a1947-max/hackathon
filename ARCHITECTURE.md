# ARCHITECTURE — HCM Lite (AI-assisted Human Capital Management)

> Owner: coordinator (built on `hackathon-template`). This document is the **frozen contract**.
> All agents code against the model field names, API paths, and rules below.
> Canonical location: project root (mirrored intent of kit README).

## 1. Problem restatement & assumptions

Hackathon build of a multi-tenant HCM SaaS (Admin / HR / Employee roles) with attendance,
leave, payroll-lite, analytics, and an AI assistant with permission-checked tools.

Assumptions (stated explicitly):
- **Money** stored as `Numeric(12,2)`; all calculations rounded to 2 dp at the end of each computation.
- **Tax slabs** in the brief are *illustrative annualized gross* rules, applied to `gross * 12`.
- **Half day** = worked hours < 5 (status `half_day`, 0.5 day deduction in payroll).
- **Late** = check-in after office_start + grace_period (default 09:15).
- **Payslip** = finalized `payroll_items` row; PDF rendered on demand. No separate payslip table.
- **Email** is globally unique across tenants (login identifier); `employee_code` unique per company.
- **Timezone**: company setting, default `Asia/Karachi`; all date resolution uses it.
- Local dev runs on **SQLite** if PostgreSQL is unavailable; production uses **PostgreSQL**
  (SQLAlchemy 2.0 typed ORM, Alembic migrations, portable column types only).

## 2. Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router, TS), Tailwind CSS, Recharts, responsive ≥375px |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic |
| DB | PostgreSQL (prod) / SQLite (dev fallback), via `DATABASE_URL` |
| Auth | JWT (HS256, PyJWT), bcrypt password hashing, `must_change_password` flag |
| AI | OpenAI-compatible provider (tool calling) + deterministic offline fallback, backend-only key |
| PDF | reportlab |
| Tests | pytest + FastAPI TestClient |

## 3. Data model (frozen field names)

All tables: `id` (int PK), `company_id` FK → companies.id (indexed), `created_at`, `updated_at` unless noted.

- **companies**: name, address?, phone?
- **company_settings**: company_id (unique FK), office_start_time (Time, 09:00), grace_period_minutes (15),
  weekend_days (JSON ["Saturday","Sunday"]), office_lat, office_lng, geofence_radius_m (1000),
  timezone ("Asia/Karachi"), half_day_threshold_hours (5.0)
- **users**: email (unique global), password_hash, role (admin|hr|employee), employee_id (FK nullable),
  is_active (bool), must_change_password (bool), full_name
- **employees**: employee_code (unique per company), first_name, last_name, email (unique per company),
  phone?, address?, department_id (FK), designation_id (FK), joining_date (Date), employment_status
  (active|inactive|terminated), gender? (male|female|other), basic_salary Numeric(12,2) (current basic),
  date_of_birth?, termination_date?
- **departments**: name (unique per company)
- **designations**: name (unique per company)
- **leave_types**: name, code (ANNUAL|SICK|CASUAL|UNPAID, unique per company), yearly_quota (int,
  null = unlimited), is_paid (bool)
- **holidays**: name, date (Date, unique per company+date)
- **attendance**: employee_id+date (unique), check_in (DateTime server), check_out? (DateTime),
  status (present|late|half_day|missing_checkout|absent|on_leave|weekend|holiday), worked_hours (float),
  check_in_lat?, check_in_lng?
- **attendance_corrections**: attendance_date, requested_check_in, requested_check_out, reason,
  status (pending|approved|rejected), reviewed_by (user id), reviewed_at?, review_comment?, requested_by?
- **leave_requests**: leave_type_id, start_date, end_date, working_days (float), reason,
  status (pending|approved|rejected|cancelled), reviewed_by?, reviewed_at?, review_comment?
- **salary_structures**: employee_id, basic_salary, effective_from (Date), effective_to? (Date)
- **payroll_runs**: period_year, period_month (1-12), status (draft|finalized), generated_by, generated_at,
  finalized_by?, finalized_at?, total_gross, total_deductions, total_net; unique (company, year, month)
- **payroll_items**: run_id FK, employee_id, basic, hra, medical, gross, working_days, present_days,
  absent_days, unpaid_leave_days, half_days, deduction_amount, tax, net_pay, note?;
  unique (run_id, employee_id)
- **announcements**: title, body, created_by, audience (all)
- **notifications**: user_id, title, body?, link?, is_read (bool default false)
- **audit_logs**: actor_user_id?, actor_email, action, entity_type, entity_id?, before (JSON?),
  after (JSON?), created_at (NOT NULL, indexed by company+created_at). Immutable via app API.
- **ai_logs**: user_id, role, prompt?, summary?, tools (JSON), success (bool), provider?, model?,
  latency_ms?, created_at

Rules: no app endpoint updates/deletes audit_logs; multi-step writes use one transaction.

## 4. API contract (frozen) — all under `/api`, JWT Bearer unless noted

Auth & setup (public):
- `GET /api/setup/status` → `{needs_setup: bool}`
- `POST /api/setup/company` `{company_name, admin:{full_name,email,password}}` → 201 `{access_token, user}`
  (only when needs_setup; seeds default leave types + settings; 409 if already set up)
- `POST /api/auth/login` `{email,password}` → `{access_token, token_type, must_change_password, user:{id,role,full_name,email,employee_id}}`
- `GET /api/auth/me` → current user profile
- `POST /api/auth/change-password` `{current_password,new_password}` → 200; clears must_change_password
- `POST /api/auth/logout` → 204 (audit-logged)

**Mandatory password change gate**: a user with `must_change_password=true` gets **403
"Password change required"** on every authenticated endpoint except `/api/auth/me`,
`/api/auth/change-password`, `/api/auth/logout`, `/api/setup/status`, `/api/health`.

Org (read: HR+Admin — leave-types readable by every role; write: Admin only):
- `GET/PATCH /api/org/settings`
- `GET/POST/PATCH/DELETE /api/org/departments[/{id}]`, `/api/org/designations[/{id}]`,
  `/api/org/holidays[/{id}]`, `/api/org/leave-types[/{id}]`

Employees (brief §8 matrix enforced server-side):
- `GET /api/employees?q=&department_id=&status=&page=&page_size=` (HR+Admin)
- `POST /api/employees` — **HR registers employees**; `create_login_role="hr"` is **Admin-only**
  (#05/#06). → 201 `{employee, temp_password}` (must_change_password)
- `GET /api/employees/{id}` (360°; employee: self only, salary fields only for staff/owner)
- `PATCH /api/employees/{id}` (**HR only** — Admin View); `PATCH /api/employees/me` (self: phone/address only)
- `POST /api/employees/import?dry_run=true|false` (**HR only**) → row/field/reason report
- `GET /api/employees/export` (**HR only**)
- `POST /api/employees/{id}/reset-password|deactivate|activate` — Admin: any login; HR: employee logins only

Attendance:
- `POST /api/attendance/check-in` `{lat?,lng?,accuracy_m?}` → 201; duplicate → 409;
  accuracy > 100 m → 422; outside geofence → 422 (server-side Haversine)
- `POST /api/attendance/check-out` → 200; 409 if already out / not checked in
- `GET /api/attendance/me?year=&month=` → month records + summary
- `GET /api/attendance/board?date=&department_id=` (HR+Admin) → day roster w/ status
- `POST /api/attendance/corrections` (employee self or HR for employee) → pending
- `GET /api/attendance/corrections?status=&scope=` (Admin View + HR; employee: own)
- `POST /api/attendance/corrections/{id}/approve|reject` `{comment?}` — **HR only** (#11: Admin View)

Leave:
- `GET /api/leave/types` (all roles; own company)
- `POST /api/leave/requests` `{leave_type_code,start_date,end_date,reason}` → 201
  (overlap → 409, insufficient balance → 422, invalid range → 422)
- `GET /api/leave/requests?scope=me|all&status=&page=` (all=HR+Admin view; Admin cannot approve)
- `GET /api/leave/balance?year=&employee_id=` (self; Admin/HR may pass `employee_id=`)
- `POST /api/leave/requests/{id}/cancel` (owner, pending only)
- `POST /api/leave/requests/{id}/approve|reject` `{comment?}` — **HR only** (#13: Admin View;
  not own request → 403)

Payroll (#14–#17: salary structures & drafts = HR Manage / Admin View; finalize = Admin only):
- `POST /api/payroll/salary-structures` (**HR only**) / `GET /api/payroll/salary-structures?employee_id=` (HR+Admin)
- `POST /api/payroll/runs` `{year,month}` (**HR only**) → draft run (regenerating replaces draft)
- `GET /api/payroll/runs?page=`, `GET /api/payroll/runs/{id}` (HR+Admin)
- `POST /api/payroll/runs/{id}/finalize` (**Admin only**; finalized → immutable; audit-logged)
- `GET /api/payroll/runs/{id}/items` (HR+Admin)
- `GET /api/payroll/payslips/me`, `GET /api/payroll/payslips/{item_id}/pdf` (owner or HR/Admin)

Analytics (server-computed, empty-safe):
- `GET /api/analytics/admin?from=&to=&department_id=` → headcount, attrition_ytd, payroll_cost,
  avg_salary, headcount_by_department, payroll_cost_by_department, gender_breakdown, tenure,
  recent_audit
- `GET /api/analytics/hr?from=&to=&department_id=` → headcount, present/late/on_leave, pending_approvals,
  attendance_trend, absenteeism_by_department, leave_utilization, top_late_comers, insights[]
- `GET /api/analytics/employee/me` → today_status, week_hours vs 40, late_count, leave_balances,
  recent_attendance, last_payslip, announcements

AI:
- `POST /api/ai/chat` `{message, conversation_id?}` → `{reply, tool_calls:[{tool,args,result_summary}],
  smart_leave?:{type,start,end,reason,working_days}, requires_confirmation:bool, provider:"llm"|"offline",
  label}`; rate limit ~20/user/hour → 429; 15s timeout; never persists/approves leave

Comms & audit:
- `GET/POST /api/announcements` (POST: HR+Admin), `DELETE /api/announcements/{id}` (Admin or author)
- `GET /api/notifications`, `GET /api/notifications/unread-count`, `POST /api/notifications/read` `{ids:[]}`
- `GET /api/audit-logs?action=&entity_type=&page=` (**Admin only**; HR/Employee → 403)
- `GET /api/health` (public)

Errors: 401 unauthenticated, 403 forbidden, 404 missing/other-tenant, 409 conflict,
422 validation, 429 rate limit. `{detail: str|list}`.

## 5. Business rules (frozen)

- Attendance: server clock only; one record/employee/day; late if check-in > start+grace;
  missing_checkout if no check-out by end of day (detected in summaries);
  half_day if worked_hours < 5; absent if no record, not weekend/holiday, no approved leave.
- Geofence: server-side Haversine vs office coords; reject outside radius; reject GPS accuracy > 100 m.
- Leave: working days exclude weekends + holidays; balance = quota − approved this year;
  unpaid unlimited; overlap check across pending+approved; approvals notify employee.
- Payroll: hra=40% basic, medical=10% basic, gross=1.5×basic; per-day = gross/working_days(month);
  deductions = (absent_days + unpaid_leave_days + 0.5×half_days) × per-day; prorate joiners/leavers;
  tax = slab(gross×12)/12 deducted monthly; net = adjusted gross − deduction − tax.
- Self-approval of own leave/correction forbidden; employees scoped via `user.employee_id`.
- Audit: login, employee create/update/deactivate, correction decisions, leave decisions,
  payroll generate/finalize, announcements, settings changes, password resets.

## 5b. Frozen service contracts (cross-module imports)

```python
# app/services/analytics.py  (owner: backend-engineer C)
def admin_summary(db, company_id, date_from, date_to, department_id=None) -> dict
def hr_summary(db, company_id, date_from, date_to, department_id=None) -> dict
def employee_summary(db, company_id, employee_id) -> dict

# app/services/leave_service.py  (owner: backend-engineer B)
def get_balance(db, company_id, employee_id, year: int) -> dict
def list_requests(db, company_id, employee_id=None, status=None, page=1, page_size=20) -> dict

# app/services/employee_service.py  (owner: backend-engineer A)
def search_employees(db, company_id, q=None, department_id=None, status=None,
                     page=1, page_size=20) -> dict

# app/services/attendance_service.py  (owner: backend-engineer B)
def summary_for_employee(db, company_id, employee_id, date_from, date_to) -> dict
```

## 5c. Metric formulas (brief Section 7 — authoritative)

- Headcount = active + probation employees on end date. Attrition % = exits in period ÷ average headcount × 100.
- Attendance rate = (present + late + missing_checkout + 0.5 × half_day) ÷ (working-day records − on_leave).
- Late % = late ÷ (present + late). Absenteeism = absent days ÷ expected working days, per department.
- Leave utilization = approved days ÷ quota, per leave type and department.
- Payroll cost = sum of gross and net by month and department. Avg salary = mean gross by department/designation.
- Gender + tenure breakdowns from employees table. AI "Summarize" receives the KPI JSON and returns
  3–5 bullets using only those numbers.

## 6. Frontend routes

`/login`, `/setup` (first run), `/` (role redirect), `/dashboard`, `/employees`, `/employees/[id]`,
`/attendance`, `/leave`, `/payroll`, `/payroll/[id]`, `/payslips`, `/announcements`,
`/settings`, `/audit`, `/assistant`. Sidebar filtered by role; dark charcoal + indigo accents.
Admin sees leave/corrections/payroll as **read-only** views (no approve/generate buttons).

## 7. Risks & fallbacks

| Risk | Fallback |
|---|---|
| No LLM key at demo | Offline deterministic provider (rules + smart-leave parser), labeled "Offline rules mode" |
| No local PostgreSQL | SQLite dev URL; Postgres migrations/instructions in README |
| PDF/font issues | reportlab Helvetica built-in fonts only |

## 8. File ownership

| Path | Owner |
|---|---|
| `backend/app/core/**`, `models/**`, `main.py`, docs, root docs | coordinator |
| `backend/app/api/setup.py, auth.py, org.py, employees.py` + schemas/services for those | backend-engineer A |
| `backend/app/api/attendance.py, leave.py` + schemas/services for those | backend-engineer B |
| `backend/app/api/payroll.py, analytics.py, comms.py` + schemas/services for those | backend-engineer C |
| `backend/app/ai/**`, `api/ai.py`, `tests/test_ai.py` | agent-engineer |
| `backend/tests/test_auth_org_employees.py` | A · `test_attendance_leave.py` | B |
| `backend/tests/test_payroll.py, test_analytics.py, test_comms.py` | C |
| `frontend/**` | frontend-engineer |
