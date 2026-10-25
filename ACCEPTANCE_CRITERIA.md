# ACCEPTANCE CRITERIA — HCM Lite

> Owner: coordinator. Verified by `qa-engineer`. Every criterion is testable by a command or a click.
> Status vocabulary: ⬜ not verified · ✅ PASS · ❌ FAIL · ⏭ SKIPPED · ⚠️ COULD NOT RUN (reason).

## MVP demo criteria (must pass to submit)

| # | Criterion | Proof (command / click-through) | Status |
|---|---|---|---|
| AC1 | First-run setup creates company + Admin on empty DB; admin logs in | `pytest tests/` setup tests + demo step 1 | ⬜ |
| AC2 | HR creates employee → temp password login → forced password change | demo step 3 + auth tests | ⬜ |
| AC3 | Employee check-in works; duplicate check-in returns 409 | `pytest -k 409` + demo step 3 | ⬜ |
| AC4 | Late/half-day/absence statuses computed by server rules | attendance unit tests | ⬜ |
| AC5 | Leave excludes weekends+holidays; overlap → 409; insufficient → 422 | leave tests | ⬜ |
| AC6 | HR approves leave → employee notified; self-approval → 403 | leave tests + demo step 5 | ⬜ |
| AC7 | Payroll draft matches brief formulas; finalize is Admin-only | payroll tests | ⬜ |
| AC8 | Finalized payroll immutable; payslip PDF downloads with correct data | payroll tests + demo step 8 | ⬜ |
| AC9 | Dashboards compute from real DB records; filters + empty states work | analytics tests + click-through | ⬜ |
| AC10 | AI chat answers from live data via permission-checked tools | ai tests + demo step 6 | ⬜ |
| AC11 | Smart leave returns validated structure → pre-filled form → user confirms | demo step 4 + ai tests | ⬜ |
| AC12 | AI refuses other employee's salary for Employee role | ai test + demo step 9 | ⬜ |
| AC13 | Without `AI_API_KEY`, assistant degrades to labeled offline mode; core app unaffected | unset key → run → label visible | ⬜ |
| AC14 | Audit log records actions; Admin-only access (HR/Employee → 403) | comms tests + demo step 10 | ⬜ |
| AC15 | Employee cannot view other employees' profiles/salary/payslips (403) | security tests | ⬜ |
| AC16 | App starts from clean clone in ≤ 3 commands (see README) | clean-clone rehearsal | ⬜ |

## Quality gates

| # | Gate | Proof | Status |
|---|---|---|---|
| Q1 | Backend test suite green | exact `pytest` command + real counts | ⬜ |
| Q2 | Frontend production build passes | `npm run build` output | ⬜ |
| Q3 | No secrets in repo | grep for key/password patterns → empty (except `.env.example` placeholders) | ⬜ |
| Q4 | Error states visible in UI | stop backend → UI shows error state with retry | ⬜ |
| Q5 | No TODO/stub endpoints in required modules | grep for `TODO`/`NotImplemented` in `backend/app` | ⬜ |

## Demo-journey criteria (the exact path the judge will see)

1. Judge opens app → `/setup` first-run → creates company + Admin → lands on Admin dashboard.
2. Admin adds department, leave types, creates HR login.
3. HR registers 2–3 employees → temp passwords shown once.
4. Employee signs in → forced password change → checks in (server timestamp).
5. Employee asks AI for leave in natural language → pre-filled form → confirms → HR approves.
6. HR views analytics, asks AI "who is on leave?" + KPI summary, generates payroll draft.
7. Admin finalizes payroll (HR's finalize attempt shows 403).
8. Employee downloads payslip PDF.
9. Employee asks AI for a colleague's salary → AI refuses (labeled).
10. Admin opens audit log → shows actors/actions/timestamps from steps above.

## Out of scope (do not build)

- Camera/facial attendance — optional bonus; deferred until required features verified.
- Attrition-risk scoring, absence anomaly detection, late-penalty automation — bonus tier.
- Email/SMS delivery — in-app notifications only.

## Change log

| Date | Change | Approved by |
|---|---|---|
| 2026-10-24 | Initial lock (M1–M9 scope from brief) | coordinator |
