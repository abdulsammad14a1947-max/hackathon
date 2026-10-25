# DEMO SCRIPT — HCM Lite (5-minute Saylani judging)

> Owner: coordinator, rehearsed + verified by `qa-engineer`. Only steps proven to work appear here.
> Status: ⬜ rehearsal pending — final timings verified in the rehearsal log below.

## Setup (done before the judge arrives)

```bash
# Terminal 1 — backend (fresh DB so the judge does first-run setup themselves)
cd backend && pip install -r requirements.txt
python -m alembic upgrade head
uvicorn app.main:app --port 8000

# Terminal 2 — frontend
cd frontend && npm install && npm run dev

# Verify
curl http://localhost:8000/api/health     # {"status":"ok"}
open http://localhost:3000                # redirects to /setup
```

- Environment ready: ☐ no AI key needed for this run (offline mode is labeled) ☐ DB fresh ☐ mode: `offline`
- Backend+frontend running before the clock starts.

## Timed run-through (5:00)

| T | Step (click / say) | Expected observable result | Say this |
|---|---|---|---|
| 0:00 | Open http://localhost:3000 | First-run setup screen (empty system, no dummy data) | "HCM Lite starts empty — everything you're about to see, we create together." |
| 0:20 | Fill company + Admin account → submit | Auto-login as Admin, dashboard with zeros | "Company + Admin in one step; every KPI will be real." |
| 0:40 | Settings: office 09:00, grace 15, Sat/Sun, office lat/lng + radius; add dept "Engineering"; leave types already seeded | Settings saved (audit entry) | "These rules drive attendance and leave — configured, not hardcoded." |
| 1:00 | Admin → Users → create HR login | HR credentials shown once | "Only Admin can create HR logins — role matrix from the brief." |
| 1:15 | Log in as HR → add 2 employees | Directory shows 2 rows + temp passwords shown once | "HR registers staff; their logins come with temporary passwords." |
| 1:40 | Log in as employee → forced password change → check in | Change-password screen blocks everything; then check-in badge with server time | "Mandatory first-login change, server-stamped attendance." |
| 2:00 | (Same employee) try check in again | Toast: 409 already checked in | "One record per day — enforced server-side." |
| 2:10 | Employee → Assistant: "I need next Monday and Tuesday off for a wedding" | Pre-filled leave form (type/dates/reason) with Confirm button | "AI turns plain words into a validated form — the human confirms, never the AI." |
| 2:40 | Confirm → HR approves with comment | Status approved; employee notification appears | "Server checked balance, overlap, weekends and holidays first." |
| 2:55 | HR → Dashboard → Summarize; ask "who is on leave today?" | 3–5 insight bullets from live KPIs; correct on-leave answer | "Same services as the dashboard — answers always match the numbers." |
| 3:25 | HR → Payroll → generate draft for current month | Draft run with rows: basic, HRA, medical, gross, deductions, tax, net | "Brief's formulas: gross 1.5×basic, per-day deductions, illustrative tax slabs." |
| 3:50 | (Optional) log in as HR → try to finalize | 403 — button hidden AND server refuses | "RBAC is server-side; hiding buttons is not the control." |
| 4:00 | Admin → finalize payroll | Status locked; employees notified | "Only Admin can lock the month; finalized runs are immutable." |
| 4:15 | Employee → Payslips → download PDF | PDF opens with correct name, period, earnings, tax, net | "Real PDF from the finalized run." |
| 4:30 | Employee → Assistant: "What is Hira's salary?" | Polite refusal, labeled AI answer | "The assistant runs with the caller's permissions — it cannot leak salaries." |
| 4:45 | Admin → Audit log | Rows for setup, settings, employee creation, password change, check-in, leave approval, payroll finalize | "Every important action: who, what, when, before/after." |

## One-liner opening

"HCM Lite turns a blank database into a working HR system in five minutes — setup, attendance,
leave, payroll and an AI assistant that can only see what you're allowed to see. Let me show you."

## Failure-recovery lines (memorize)

- **If the AI is slow / provider down:** "That's the labeled fallback — the assistant degrades
  gracefully and the rest of the HR system is untouched."
- **If a page errors:** "That's a real error state with retry — no hidden failures."
- **If asked what's mocked:** nothing in the HR flow is mocked; point at the offline-mode badge
  if the assistant is running without a key.

## Post-demo

- Leave the app open on the audit log / dashboards.
- Evidence ready: `docs/requirements-checklist.md`, test counts from `pytest -q`.

## Rehearsal log

| Date | Duration | Failures observed | Fixes needed |
|---|---|---|---|
| | | | |
