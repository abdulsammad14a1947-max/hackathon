# DECISIONS — HCM Lite

> Living decision log. Once a decision is settled here it stays settled.

| # | When | Decision | Rationale (evidence) | Proposed by / objected by | Revisit when |
|---|---|---|---|---|---|
| D1 | start | Monorepo `frontend/` + `backend/` + `docs/`, docs at root from hackathon-template | brief requires separate Vercel frontend + FastAPI backend | coordinator / (none) | never |
| D2 | start | SQLite for local dev & tests, PostgreSQL for production via `DATABASE_URL` | no Docker/Postgres server on build machine; SQLAlchemy/Alembic keep both paths | coordinator / (none) | managed PG available at deploy |
| D3 | start | bcrypt (direct) for hashing, PyJWT HS256 for tokens | packages pre-installed, avoids deprecated passlib/bcrypt incompatibility | coordinator / (none) | never |
| D4 | start | Email globally unique; `employee_code` unique per company | login must find a user without company context | coordinator / (none) | multi-tenant domains needed |
| D5 | start | Frozen data model + API contract in `docs/ARCHITECTURE.md` before parallel build | 4 agents build in parallel against one contract | coordinator / (none) | contract change requested |
| D6 | start | Payslip = finalized `payroll_items` row, PDF rendered on demand | avoids duplicate storage; brief allows payslip records | coordinator / (none) | payslip history beyond payroll needed |
| D7 | start | Tax slabs implemented literally as brief's illustrative rules | brief marks them illustrative; judges score against the brief | coordinator / (none) | real tax engine required |
| D8 | start | AI: OpenAI-compatible tool-calling provider + labeled offline fallback | no `AI_API_KEY` in build env; app must work without it | coordinator / (none) | key supplied at demo |
| D9 | start | `must_change_password` enforced server-side as 403 on all non-auth endpoints | brief requires mandatory first-login change | coordinator / (none) | never |
| D10 | start | Shared `calendar_utils` + `notifications` services coordinator-owned | used by leave, payroll and AI agents — single implementation | coordinator / (none) | never |

## Open questions (unresolved, need human or coordinator)

| # | Question | Blocks | Needed by |
|---|---|---|---|
| 1 | Will judges have a live LLM key? (offline mode is ready either way) | AI demo polish | demo day |

## Rejected options (keep short — why NOT)

- **Postgres via winget-only local server** — install attempted, but app must run regardless; dual-path instead.
- **Docker Compose stack** — no Docker on build machine; rejected as local dev requirement (kept as deploy option only if documented).
- **Next.js API routes as backend** — brief mandates FastAPI backend with Python services.
