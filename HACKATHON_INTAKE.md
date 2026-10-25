# HACKATHON INTAKE — HCM Lite (Saylani AI Hackathon)

> Completed copy for this project. Rules: never paste actual secrets — provider/key names only.

---

**Problem statement:**
Saylani HCM Lite — an AI-assisted Human Capital Management web app for Admin, HR and Employees.
Authoritative spec: `Saylani_Hackathon_HCM_Lite_Brief.pdf` (nine modules M1–M9, 25 functionalities,
role permissions, business rules, AI guardrails, dashboard metrics, submission requirements).
Full extraction of requirements lives in `docs/ARCHITECTURE.md` and `docs/requirements-checklist.md`.

**Hackathon theme:**
AI applied to real business workflows (HR/People operations).

**Judging criteria (100 points):**
Core HR flows 25 · Data & analytics 20 · AI features 15 · Code quality 15 · UI/UX 10 ·
Security & RBAC 10 · Demo & documentation 5.

**Time remaining:**
Build window treated as a single continuous session; 6-hour timebox discipline applied.

**Required deliverables:**
Working web application (frontend + backend + database), README, requirements checklist,
5-minute demo script, tests, deployment instructions.

**Required technology or restrictions:**
Frontend: Next.js + TypeScript + Tailwind + Recharts. Backend: Python/FastAPI/SQLAlchemy/Alembic/
PostgreSQL/JWT/bcrypt. AI: hosted LLM with tool calling, key backend-only, structured outputs,
permission-checked tools, 15s timeout, ~20 req/user/hour, friendly fallback. Tests: pytest.
Vercel-compatible frontend + hosted FastAPI + managed PostgreSQL.

**Available models and API keys:**
- OpenAI-compatible provider abstraction implemented in `backend/app/ai/`; key name `AI_API_KEY` (env, backend only).
- **No key available in this build environment** → labeled offline provider (deterministic rules +
  smart-leave parser) is the default and fully functional; setting `AI_API_KEY` switches to live LLM mode.

**Available data:**
No external datasets. All demo data is created by judges/users through first-run setup (by design).

**Target users:**
Company Admin, HR staff, and employees of a small-to-mid organization.

**Expected outcome:**
A deployed, judgeable SaaS app where a judge creates their own company from scratch and walks the
5-minute demo (setup → employees → check-in → AI leave request → approval → analytics → payroll →
payslip → AI refuses other employee's salary → audit log).

**Deployment requirements:**
Browser-accessible. Frontend → Vercel; backend → any host running FastAPI (Render/Railway/Fly);
managed PostgreSQL (Neon/Supabase/Render). Environment-based configuration.

**Team size:**
Solo developer with AI coding agents.

**Additional constraints:**
Windows dev machine, no Docker, no local PostgreSQL server (SQLite dev fallback documented;
PostgreSQL is the documented production target).

---

## Assumptions log

| # | Missing info | Assumption made | Impact if wrong |
|---|---|---|---|
| 1 | No AI key in build env | Offline labeled provider by default; live mode activates with `AI_API_KEY` | Judges see labeled offline mode unless they supply a key |
| 2 | No PostgreSQL server locally | SQLite for dev/test; PostgreSQL via `DATABASE_URL` + Alembic for deploy | None if DATABASE_URL documented |
| 3 | Brief's tax slabs described as illustrative | Implemented exactly as written, labeled illustrative in README | None |
| 4 | Payslip storage shape unspecified | Payslip = finalized payroll item, PDF generated on demand | None |
| 5 | Half-day = worked hours < 5 | Matches brief's "working time under five hours" rule | None |
| 6 | Email uniqueness scope | Globally unique (login identifier), employee_code unique per company | None |

## Clarifying questions for the human (only if material)

- None blocking — implementation proceeds on stated assumptions.
