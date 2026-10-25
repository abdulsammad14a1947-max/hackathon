# HCM Lite — AI-assisted Human Capital Management

A web-based HCM system for **Admin, HR and Employees**: authentication and RBAC, organization setup,
employee management, web attendance with status rules, leave with approvals, Payroll Lite with PDF
payslips, server-computed dashboards, an AI assistant with permission-checked tools, announcements,
notifications and an immutable audit log.

Built for the **Saylani Hackathon (24 Oct 2026)** against `Saylani_Hackathon_HCM_Lite_Brief.pdf`
(9 modules, 25 functionalities). The system **starts empty** — a judge creates the company in
first-run setup and every number comes from real records.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router) · TypeScript · Tailwind CSS · Recharts |
| Backend | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 · Alembic |
| Database | PostgreSQL (production) · SQLite (zero-setup local dev) |
| Auth | JWT (HS256) · bcrypt password hashing · mandatory first-login password change |
| AI | OpenAI-compatible tool-calling provider + labeled offline fallback (backend-only key) |
| PDF | reportlab |
| Tests | pytest (backend), `npm run build` + ESLint (frontend) |

---

## Quick start (judge, fresh install — under 10 minutes)

### 1. Backend (FastAPI + SQLite, zero external services)

```bash
cd backend
pip install -r requirements.txt
python -m alembic upgrade head        # create the database schema
uvicorn app.main:app --reload --port 8000
```

Health check: <http://localhost:8000/api/health> → `{"status":"ok"}`.
Tables are also auto-created at startup if you skip Alembic (dev convenience).

### 2. Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000> — it redirects to `/setup` (first-run): enter **company name +
Admin account**, submit, and you are logged in as Admin. From there: create departments, leave
types (seeded defaults: Annual 14 / Sick 8 / Casual 10 / Unpaid unlimited), an **HR login**
(Admin → Users), then HR registers employees (each gets a **temporary password**, forced change
on first sign-in).

### Optional: environment configuration

```bash
cp .env.example backend/.env      # then edit values
```

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Default `sqlite:///./hcm_lite.db`. Production: `postgresql+psycopg://USER:PASSWORD@HOST:5432/hcm_lite` |
| `JWT_SECRET` | **Required in production** — long random string |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Optional: auto-creates first company+Admin on startup (instead of `/setup`) |
| `AI_API_KEY` | **Backend only, never in the frontend.** Empty → labeled offline mode |
| `AI_PROVIDER` / `AI_BASE_URL` / `AI_MODEL` | Any OpenAI-compatible chat-completions API with tool calling |
| `AI_RATE_LIMIT_PER_HOUR` | Default 20 requests per user per hour |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend → backend URL (set before `npm run build`) |

### Production database (PostgreSQL)

1. Create a managed PostgreSQL database (Neon / Supabase / Render).
2. `DATABASE_URL=postgresql+psycopg://...` in the backend environment.
3. `python -m alembic upgrade head` (portable migration, verified against SQLite; standard types only).
4. Set `JWT_SECRET`, restart.

---

## Demo in 5 minutes (matches the official script)

1. **Admin** runs first-run setup (company + Admin), sets office hours/location, adds a department,
   checks seeded leave types, creates an HR login.
2. **HR** registers 2–3 employees → temp passwords shown once.
3. One **employee** signs in → forced password change → **checks in** (server timestamp; duplicate
   check-in returns 409).
4. Employee asks the **AI assistant** for leave in plain words → **pre-filled form** (user confirms —
   the AI never submits by itself) → HR approves it.
5. **HR** opens the dashboard, clicks **Summarize**, asks "who is on leave today?", generates the
   **payroll draft** for the month.
6. **Admin finalizes payroll** (an HR finalize attempt gets 403 — demo this!).
7. **Employee downloads the payslip PDF**.
8. **Employee asks the AI for a colleague's salary → politely refused.**
9. **Admin shows the audit log** — every step above is there with actor/action/timestamp/before-after.

Full timed script with talk-track: `DEMO_SCRIPT.md`.

---

## AI assistant

- Tools: `get_headcount`, `get_attendance_summary`, `get_late_comers`, `get_leave_summary`,
  `get_my_leave_balance`, `get_payroll_summary`, `search_employees` — all run **backend-side with the
  caller's permissions and data scope** (an Employee's tools see only their own data).
- The model never touches the database directly and never writes data. Structured outputs are
  validated; invalid output is retried once, then falls back to the normal form.
- 15-second timeout, ~20 requests/user/hour, every call logged to `ai_logs`; answers are labeled
  "AI-generated". Policy Q&A answers only from the configured company rules.
- **Without an API key** the assistant uses a deterministic offline provider (clearly labeled
  "Offline rules mode") that still answers policy questions, executes tools for live numbers and
  parses smart-leave sentences — so the demo never breaks. Set `AI_API_KEY` to switch to the LLM.

---

## What is implemented / not implemented

See `docs/requirements-checklist.md` for the full 25-functionality checklist with verification
status of each item. Summary:

**Implemented and tested:** all nine modules M1–M9 (auth/RBAC/first-run, org setup, employees +
CSV import/export with dry-run, attendance + corrections + geofence, leave + balances + approvals,
payroll + tax slabs + proration + PDF payslips, three dashboards with filters, AI assistant with
tools/smart leave/policy Q&A/offline fallback, announcements/notifications/audit log).

**Not implemented (optional bonus items from the brief):** camera/facial attendance (server-side
geofence + GPS-accuracy validation IS implemented for check-in; the browser face-detection step is
deferred), attrition-risk scoring, absence anomaly flags, late-penalty automation. Roman Urdu AI is
best-effort: the offline provider understands common Roman Urdu leave phrases; live LLM mode
handles it via the model.

---

## Testing

```bash
cd backend
python -m pytest -q                     # full backend suite
cd ../frontend
npm run build                           # production build (type + lint checks)
```

Security-critical tests included: role enforcement, Employee data scoping (403s on other
employees' data/salary/payslips), duplicate check-in 409, leave overlap/balance 409/422,
self-approval 403, payroll immutability after finalize, Admin-only finalize and audit log,
AI tool scoping and salary-refusal, dashboard-vs-seeded-data agreement.

---

## Repository layout

```
backend/           FastAPI app (app/api, app/services, app/models, app/ai, migrations, tests)
frontend/          Next.js app (app routes, components, features, hooks, lib, types)
docs/              ARCHITECTURE.md (frozen contracts), requirements-checklist.md, demo-script.md
HACKATHON_INTAKE.md, ACCEPTANCE_CRITERIA.md, DECISIONS.md   # project docs (from the team kit)
.env.example       # placeholders only — no secrets
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Frontend shows "Cannot connect to API" | Start the backend on :8000; check `NEXT_PUBLIC_API_BASE_URL` |
| `403 Password change required` everywhere | Expected after first login with a temp password — change it at `/change-password` |
| `429` from the assistant | Hourly AI rate limit (20/user/h) — wait or raise `AI_RATE_LIMIT_PER_HOUR` |
| Postgres migration errors | Ensure `DATABASE_URL` is set before `alembic upgrade head`; dev SQLite DBs are disposable |
| Port 8000 busy | `uvicorn app.main:app --port 8001` and update the frontend env |
