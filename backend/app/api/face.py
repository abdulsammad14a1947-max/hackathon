"""Face attendance endpoints (M10) mounted under the existing attendance API.

Endpoints (multipart — one JPEG/PNG/WebP frame per request, never video):

* ``GET  /api/attendance/face/status``    enrolment status (self only)
* ``POST /api/attendance/face/challenge`` issue single-use anti-replay token
* ``POST /api/attendance/face/enroll``    capture/replace own face template
* ``POST /api/attendance/face/verify``    server-side match, no attendance write
* ``POST /api/attendance/face/check-in``  match + geofence + attendance check-in
* ``POST /api/attendance/face/check-out`` match + geofence + attendance check-out

Identity is derived from the JWT session only; the frame + GPS are the only
client inputs that influence the outcome, and every decision is made on the
server (see ``app.services.face_service``).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.face.engine import FaceEngine, get_face_engine
from app.models import User
from app.services import face_service

router = APIRouter(prefix="/api/attendance/face", tags=["attendance-face"])

ALLOWED_TYPES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp"})


async def _read_frame(file: UploadFile) -> bytes:
    """Validate declared type + size before decoding anything."""
    s = get_settings()
    max_bytes = s.face_max_image_mb * 1024 * 1024
    ctype = (file.content_type or "").lower()
    if ctype not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported image type '{ctype}' — use JPEG, PNG or WebP",
        )
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=422,
            detail=f"Frame exceeds the {s.face_max_image_mb} MB limit",
        )
    if not data:
        raise HTTPException(status_code=422, detail="Uploaded frame is empty")
    return data


@router.get("/status")
def status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    engine: FaceEngine = Depends(get_face_engine),
):
    """Caller's own enrolment status + office geofence for display."""
    return face_service.face_status(db, user, engine)


@router.post("/challenge", status_code=201)
def challenge(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Issue a single-use signed challenge; required by every frame POST."""
    return face_service.issue_challenge(db, user)


@router.post("/enroll", status_code=201)
async def enroll(
    file: Annotated[UploadFile, File(description="One camera frame (JPEG/PNG/WebP)")],
    nonce: Annotated[str, Form()],
    token: Annotated[str, Form()],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    engine: FaceEngine = Depends(get_face_engine),
):
    """Enrol (or re-enrol) the AUTHENTICATED employee's face template."""
    data = await _read_frame(file)
    return face_service.enroll(db, user, engine, data, nonce, token)


@router.post("/verify")
async def verify(
    file: Annotated[UploadFile, File(description="One camera frame (JPEG/PNG/WebP)")],
    nonce: Annotated[str, Form()],
    token: Annotated[str, Form()],
    lat: Annotated[float | None, Form()] = None,
    lng: Annotated[float | None, Form()] = None,
    accuracy_m: Annotated[float | None, Form()] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    engine: FaceEngine = Depends(get_face_engine),
):
    """Server-side face match only — no attendance record is written."""
    data = await _read_frame(file)
    return face_service.verify_only(db, user, engine, data, lat, lng, accuracy_m, nonce, token)


@router.post("/check-in", status_code=201)
async def check_in(
    file: Annotated[UploadFile, File(description="One camera frame (JPEG/PNG/WebP)")],
    nonce: Annotated[str, Form()],
    token: Annotated[str, Form()],
    lat: Annotated[float | None, Form()] = None,
    lng: Annotated[float | None, Form()] = None,
    accuracy_m: Annotated[float | None, Form()] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    engine: FaceEngine = Depends(get_face_engine),
):
    """Match + geofence + the ordinary check-in rules (409 duplicate etc.)."""
    data = await _read_frame(file)
    return face_service.check_in_face(db, user, engine, data, lat, lng, accuracy_m, nonce, token)


@router.post("/check-out", status_code=200)
async def check_out(
    file: Annotated[UploadFile, File(description="One camera frame (JPEG/PNG/WebP)")],
    nonce: Annotated[str, Form()],
    token: Annotated[str, Form()],
    lat: Annotated[float | None, Form()] = None,
    lng: Annotated[float | None, Form()] = None,
    accuracy_m: Annotated[float | None, Form()] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    engine: FaceEngine = Depends(get_face_engine),
):
    """Match + geofence + the ordinary check-out rules (409 state conflicts)."""
    data = await _read_frame(file)
    return face_service.check_out_face(db, user, engine, data, lat, lng, accuracy_m, nonce, token)
