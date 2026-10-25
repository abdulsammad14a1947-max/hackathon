# REQUIREMENTS CHECKLIST — HCM Lite (Saylani brief)

Status vocabulary: **Implemented** = code exists · **Tested** = automated test proves it ·
**Partially implemented** · **Not implemented**. Final verification by `qa-engineer` fills the
"Verified" column with real command evidence; unverified rows stay ⬜ until then.

## Functionality checklist (brief Section 8, 25 items)

| # | Functionality | Admin | HR | Employee | Status | Verified |
|---|---|---|---|---|---|---|
| 01 | First-run setup: company profile + Admin account (or env bootstrap) | Manage | — | — | Implemented | ⬜ |
| 02 | Login, logout, change password; role-based menus & dashboards | Own | Own | Own | Implemented | ⬜ |
| 03 | Company settings: office hours, grace, weekend, office location + radius | Manage | View | — | Implemented | ⬜ |
| 04 | Departments, designations, leave types + quotas, public holidays | Manage | View | — | Implemented | ⬜ |
| 05 | Create HR logins; deactivate/reset any login | Manage | — | — | Implemented | ⬜ |
| 06 | Register employee (creates login) + edit details | View | Manage | Own phone & address | Implemented | ⬜ |
| 07 | Employee directory (search/filters); Employee 360 | All | All | Own | Implemented | ⬜ |
| 08 | CSV import with dry-run error report; CSV export | — | Manage | — | Implemented | ⬜ |
| 09 | Check in / check out on the web | — | Own | Own | Implemented | ⬜ |
| 10 | Attendance calendar + daily attendance board | All | All | Own | Implemented | ⬜ |
| 11 | Attendance correction: request and approve | View | Approve | Request | Implemented | ⬜ |
| 12 | Apply/cancel leave; see balance and history | — | Own | Own | Implemented | ⬜ |
| 13 | Approve/reject leave with a comment | View | Approve | — | Implemented | ⬜ |
| 14 | Salary structure per employee | View | Manage | — | Implemented | ⬜ |
| 15 | Monthly payroll: create and review the draft | View | Manage | — | Implemented | ⬜ |
| 16 | Finalize payroll (locks the month) | Manage | — | — | Implemented | ⬜ |
| 17 | Payslips with PDF download | All | All | Own | Implemented | ⬜ |
| 18 | Dashboards, KPIs, trends, insights with filters | Company | HR | Personal | Implemented | ⬜ |
| 19 | AI assistant chat answering from real data | All data | HR data | Own data | Implemented | ⬜ |
| 20 | AI dashboard summary (3–5 bullets from KPI JSON) | Yes | Yes | — | Implemented | ⬜ |
| 21 | Smart leave: sentence → pre-filled form (user confirms) | — | Own | Own | Implemented | ⬜ |
| 22 | Policy Q&A on attendance/leave/payroll rules | Yes | Yes | Yes | Implemented | ⬜ |
| 23 | Announcements | Post | Post | Read | Implemented | ⬜ |
| 24 | In-app notifications (leave decisions, payslips) | Own | Own | Own | Implemented | ⬜ |
| 25 | Audit log of create/update/approve/finalize | View | — | — | Implemented | ⬜ |

## Business rules (brief Section 3)

| Rule | Status | Verified |
|---|---|---|
| JWT + bcrypt; every API checks role AND data scope (Employee sees only own employee_id) | Implemented | ⬜ |
| Settings defaults: 09:00 start, 15-min grace, half day < 5h, Sat–Sun weekend, office lat/lng + radius | Implemented | ⬜ |
| CSV dry-run returns row + field + reason; checks required/unique/email/dept/ISO date/salary>0 | Implemented | ⬜ |
| Attendance: server stamps time; one record/employee/day (2nd check-in = 409); late after 09:15; missing_checkout flag | Implemented | ⬜ |
| Leave: working days only (skip weekends/holidays); quotas 14/8/10/unlimited; overlap or over-balance = 422/409 | Implemented | ⬜ |
| Payroll: gross 1.5×basic (HRA 40% + medical 10%); per-day = gross ÷ working days; deduct absent + unpaid + 0.5×half days; prorate; tax slabs on gross×12; Admin finalize locks | Implemented | ⬜ |
| Dashboards: computed on server (DB aggregation), filterable by date range + department | Implemented | ⬜ |
| Audit log: actor, action, entity, before/after JSON; immutable via API | Implemented | ⬜ |

## AI guardrails (brief Section 4)

| Guardrail | Status | Verified |
|---|---|---|
| AI_API_KEY backend-only; browser never calls provider | Implemented | ⬜ |
| Model never queries DB directly; tools reuse services + permission checks | Implemented | ⬜ |
| AI never saves data; JSON validated; retry once then normal form fallback | Implemented | ⬜ |
| 15s timeout, friendly fallback, ~20 req/user/hour, ai_logs rows, "AI-generated" label | Implemented | ⬜ |
| Employee salary question about colleague → polite refusal | Implemented | ⬜ |
| Works without a key (labeled offline mode) | Implemented | ⬜ |

## Section 7 metrics

| Metric | Formula implemented | Status | Verified |
|---|---|---|---|
| Headcount / attrition | active+probation on end date / exits ÷ avg headcount ×100 | Implemented | ⬜ |
| Attendance rate | (present+late+missing_checkout+0.5×half_day) ÷ (working-day records − on_leave) | Implemented | ⬜ |
| Late % / absenteeism | late ÷ (present+late) / absent ÷ expected working days, per dept | Implemented | ⬜ |
| Leave utilization | approved days ÷ quota, per type and dept | Implemented | ⬜ |
| Payroll cost / avg salary | sum gross+net by month/dept; mean gross by dept/designation | Implemented | ⬜ |

## Optional bonus (Section 5 & bonus list) — NOT required

| Item | Status |
|---|---|
| Camera attendance with face detection (face-api.js / MediaPipe) in browser | Not implemented (server geofence + GPS-accuracy check IS implemented; browser face detection deferred) |
| Face descriptor matching + blink liveness | Not implemented |
| Attrition risk score | Not implemented |
| Absence anomaly flags | Not implemented |
| Late penalty rule (3 lates = 0.5 day) | Not implemented |
| Roman Urdu understanding | Partially implemented (offline parser handles common phrases; live LLM handles naturally) |
| PWA / installable | Not implemented |

## Submission requirements (brief Section 9)

| Requirement | Status |
|---|---|
| Public repo + hosted link | Pending hosting (local verified; deploy instructions in README) |
| README: stack, run, first Admin, AI key, done/not-done | Implemented |
| `.env.example` committed, no real secrets | Implemented |
| 5-minute demo script | Implemented (DEMO_SCRIPT.md) |
