"""HCM Lite — FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    analytics,
    attendance,
    auth,
    comms,
    employees,
    face,
    leave,
    org,
    payroll,
    setup,
    ai,
)
from app.core.config import get_settings
from app.core.db import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (dev convenience; production uses Alembic — see README).
    init_db()
    from app.services.bootstrap import bootstrap_env_admin

    bootstrap_env_admin()
    yield


app = FastAPI(
    title="HCM Lite API",
    description="AI-assisted Human Capital Management for Admin, HR and Employees",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api"
app.include_router(setup.router)
app.include_router(auth.router)
app.include_router(org.router)
app.include_router(employees.router)
app.include_router(attendance.router)
app.include_router(face.router)
app.include_router(leave.router)
app.include_router(payroll.router)
app.include_router(analytics.router)
app.include_router(comms.router)
app.include_router(ai.router)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "service": "hcm-lite"}
