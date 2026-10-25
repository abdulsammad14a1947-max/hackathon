"""Face attendance service: enrolment, verification, challenges, geofence.

Trust model (M10 / threat notes):
* Identity ALWAYS comes from the JWT session (``user.employee_id``) — the
  multipart request carries no employee id and any extra form field is ignored.
* The client may only send *pixels + GPS*; the server detects, aligns, embeds
  and compares server-side. There is no ``face_verified`` flag to trust.
* Every submission consumes a **single-use, signed, short-lived challenge**
  (HMAC over nonce+user+expiry, ``used_at`` set before evaluation) so a captured
  request cannot be replayed and expired challenges are rejected.
* Geofence + GPS accuracy are re-validated here (and again inside
  ``attendance_service.check_in``) — browser-side distances are display-only.
* Failures record a ``FaceVerificationEvent`` outcome but NEVER create or
  modify an attendance record; embeddings never leave this module's call
  stack and are not written to audit rows or logs.
* Successful camera check-in reuses ``attendance_service.check_in`` unchanged,
  so duplicate-409 / late / half-day / audit rules apply identically.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import secrets
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings as app_settings
from app.face.engine import (
    MODEL_REVISION,
    FaceAnalysisError,
    FaceCapture,
    FaceEngine,
    FaceEngineUnavailable,
    cosine_similarity,
)
from app.models import EmployeeFaceTemplate, FaceChallenge, FaceVerificationEvent, User
from app.schemas.attendance import CheckInRequest
from app.services.attendance_service import _require_employee, utc_now
from app.services.attendance_service import check_in as attendance_check_in
from app.services.attendance_service import check_out as attendance_check_out
from app.services.calendar_utils import get_settings as get_company_settings
from app.services.calendar_utils import haversine_m
from app.utils.audit import record_audit

GPS_MAX_ACCURACY_M = 100.0  # brief §6: reject worse than 100 m


def _iso(ts: dt.datetime | None) -> str | None:
    return ts.isoformat() if ts else None


# --------------------------------------------------------------------------- #
# Challenges (signed, single-use, short-lived)
# --------------------------------------------------------------------------- #
def _challenge_key() -> bytes:
    # Domain-separated derivation so the JWT signing key is not reused raw.
    s = app_settings()
    return hashlib.sha256(f"face-challenge:{s.jwt_secret}".encode()).digest()


def _sign(nonce: str, user_id: int, expires_at: dt.datetime) -> str:
    payload = f"{nonce}.{user_id}.{expires_at.isoformat()}".encode()
    return hmac.new(_challenge_key(), payload, hashlib.sha256).hexdigest()


def issue_challenge(db: Session, user: User) -> dict[str, Any]:
    """Issue a single-use challenge bound to this session (anti-replay token)."""
    s = app_settings()
    now = utc_now()
    # opportunistic prune of long-expired rows
    db.query(FaceChallenge).filter(
        FaceChallenge.expires_at
        < now - dt.timedelta(days=s.face_retention_days)
    ).delete(synchronize_session=False)

    nonce = secrets.token_urlsafe(32)
    expires_at = now + dt.timedelta(seconds=s.face_challenge_ttl_seconds)
    token = _sign(nonce, user.id, expires_at)
    db.add(
        FaceChallenge(
            company_id=user.company_id,
            user_id=user.id,
            nonce=nonce,
            token=token,
            issued_at=now,
            expires_at=expires_at,
        )
    )
    db.commit()
    return {"nonce": nonce, "token": token, "expires_in": s.face_challenge_ttl_seconds}


def _fail(
    db: Session,
    user: User,
    employee_id: int,
    purpose: str,
    outcome: str,
    status_code: int,
    detail: str,
    **fields: Any,
) -> HTTPException:
    """Persist a verification event for a failed attempt, then build the error.

    Committing here means (a) failures are auditable, (b) a consumed challenge
    stays consumed, and (c) no attendance row is ever created by this path.
    """
    db.add(
        FaceVerificationEvent(
            company_id=user.company_id,
            employee_id=employee_id,
            user_id=user.id,
            purpose=purpose,
            outcome=outcome,
            detail=detail[:300],
            **fields,
        )
    )
    db.commit()
    return HTTPException(status_code=status_code, detail=detail)


def _consume_challenge(
    db: Session, user: User, employee_id: int, purpose: str, nonce: str | None, token: str | None
) -> None:
    now = utc_now()
    row = (
        db.query(FaceChallenge)
        .filter(FaceChallenge.nonce == (nonce or ""))
        .with_for_update()
        .first()
    )
    if row is None or row.user_id != user.id or row.company_id != user.company_id:
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            "challenge_invalid",
            400,
            "Invalid verification challenge — request a new one",
        )
    expected = _sign(row.nonce, row.user_id, row.expires_at)
    if not hmac.compare_digest(expected, token or ""):
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            "challenge_invalid",
            400,
            "Invalid verification challenge — request a new one",
        )
    if row.used_at is not None:
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            "challenge_replayed",
            409,
            "Verification challenge already used — request a new one",
        )
    if row.expires_at <= now:
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            "challenge_expired",
            410,
            "Verification challenge expired — request a new one",
        )
    row.used_at = now  # single-use: consumed even if later checks fail
    db.flush()


# --------------------------------------------------------------------------- #
# Shared verification steps
# --------------------------------------------------------------------------- #
def _template_for(db: Session, user: User, employee_id: int) -> EmployeeFaceTemplate | None:
    return (
        db.query(EmployeeFaceTemplate)
        .filter(
            EmployeeFaceTemplate.company_id == user.company_id,
            EmployeeFaceTemplate.employee_id == employee_id,
            EmployeeFaceTemplate.is_active.is_(True),
        )
        .first()
    )


def _analyze(
    db: Session,
    user: User,
    employee_id: int,
    engine: FaceEngine,
    purpose: str,
    image_bytes: bytes,
) -> FaceCapture:
    try:
        return engine.analyze(image_bytes)
    except FaceEngineUnavailable as exc:
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            "engine_unavailable",
            503,
            f"Face verification is unavailable: {exc}",
        ) from exc
    except FaceAnalysisError as exc:
        status = 500 if exc.code == "engine_error" else 422
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            exc.code,
            status,
            exc.message,
        ) from exc


def _match(
    db: Session,
    user: User,
    employee_id: int,
    purpose: str,
    tpl: EmployeeFaceTemplate,
    capture: FaceCapture,
) -> float:
    s = app_settings()
    stored: list[float] = json.loads(tpl.embedding)
    similarity = cosine_similarity(capture.embedding, stored)
    if similarity < s.face_match_threshold:
        # Frame-level rejection (422, like no_face/multi_face/geofence): the
        # identity check failed on the submitted frame — no attendance write.
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            "face_mismatch",
            422,
            "Face verification failed: the face does not match the enrolled employee",
            similarity=round(similarity, 4),
            threshold=s.face_match_threshold,
            detector_score=capture.detector_score,
            template_version=tpl.template_version,
        )
    return similarity


def _check_location(
    db: Session,
    user: User,
    employee_id: int,
    purpose: str,
    lat: float | None,
    lng: float | None,
    accuracy_m: float | None,
    *,
    required: bool,
) -> tuple[float | None, float | None, float | None]:
    """Server-side GPS validation. Returns (lat, lng, distance_m).

    ``distance_m`` is None when the company has no office coordinates
    configured (geofence not enforced — matches attendance §5 behaviour).
    """
    base: dict[str, Any] = {}
    if lat is not None:
        base["lat"] = float(lat)
    if lng is not None:
        base["lng"] = float(lng)
    if accuracy_m is not None:
        base["accuracy_m"] = float(accuracy_m)

    if lat is None or lng is None:
        if required:
            raise _fail(
                db,
                user,
                employee_id,
                purpose,
                "location_required",
                422,
                "Location is required for camera check-in (latitude and longitude)",
            )
        return None, None, None

    if not -90.0 <= float(lat) <= 90.0 or not -180.0 <= float(lng) <= 180.0:
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            "invalid_coordinates",
            422,
            "Invalid GPS coordinates",
            **base,
        )

    if accuracy_m is None:
        if required:
            raise _fail(
                db,
                user,
                employee_id,
                purpose,
                "accuracy_required",
                422,
                "GPS accuracy is required for camera check-in",
                **base,
            )
    elif float(accuracy_m) > GPS_MAX_ACCURACY_M:
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            "accuracy_too_low",
            422,
            f"GPS accuracy too low (±{float(accuracy_m):.0f} m — maximum {GPS_MAX_ACCURACY_M:.0f} m); "
            "move to an open area and retry",
            **base,
        )

    distance: float | None = None
    settings = get_company_settings(db, user.company_id)
    if settings.office_lat is not None and settings.office_lng is not None:
        distance = haversine_m(
            float(lat), float(lng), float(settings.office_lat), float(settings.office_lng)
        )
        radius = float(settings.geofence_radius_m or 1000)
        if distance > radius:
            raise _fail(
                db,
                user,
                employee_id,
                purpose,
                "outside_geofence",
                422,
                f"Outside office geofence: {distance:.0f} m from office (radius {radius:.0f} m)",
                distance_m=round(distance, 1),
                **base,
            )
    return float(lat), float(lng), (round(distance, 1) if distance is not None else None)


def _verify_identity(
    db: Session,
    user: User,
    engine: FaceEngine,
    purpose: str,
    image_bytes: bytes,
    nonce: str | None,
    token: str | None,
) -> tuple[int, EmployeeFaceTemplate, FaceCapture, float]:
    """Challenge -> template -> detect -> match. Failures raise HTTPException
    with a persisted event; returns (employee_id, template, capture, similarity)."""
    emp = _require_employee(db, user)  # identity strictly from the session
    employee_id = emp.id
    _consume_challenge(db, user, employee_id, purpose, nonce, token)

    tpl = _template_for(db, user, employee_id)
    if tpl is None:
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            "no_template",
            409,
            "Face not enrolled: complete face enrollment before camera check-in",
        )

    capture = _analyze(db, user, employee_id, engine, purpose, image_bytes)
    similarity = _match(db, user, employee_id, purpose, tpl, capture)
    return employee_id, tpl, capture, similarity


def _location_block(distance: float | None, accuracy_m: float | None) -> dict[str, Any] | None:
    if distance is None and accuracy_m is None:
        return None
    return {
        "distance_m": distance,
        "accuracy_m": accuracy_m,
        "within_geofence": (distance is not None),
    }


# --------------------------------------------------------------------------- #
# Public operations
# --------------------------------------------------------------------------- #
def face_status(db: Session, user: User, engine: FaceEngine) -> dict[str, Any]:
    """Self-only enrolment metadata — never an embedding, never another
    employee's data (there is no employee id input at all)."""
    s = app_settings()
    employee_id = user.employee_id
    tpl = _template_for(db, user, employee_id) if employee_id else None
    settings = get_company_settings(db, user.company_id)
    office = None
    if settings.office_lat is not None and settings.office_lng is not None:
        office = {
            "lat": float(settings.office_lat),
            "lng": float(settings.office_lng),
            "radius_m": int(settings.geofence_radius_m or 1000),
        }
    return {
        "enrolled": tpl is not None,
        "template_version": tpl.template_version if tpl else None,
        "model": tpl.model_name if tpl else None,
        "enrolled_at": _iso(tpl.enrolled_at) if tpl else None,
        "updated_at": _iso(tpl.updated_at) if tpl else None,
        "match_threshold": s.face_match_threshold,
        "engine_available": engine.available,
        "office": office,
    }


def enroll(
    db: Session,
    user: User,
    engine: FaceEngine,
    image_bytes: bytes,
    nonce: str | None,
    token: str | None,
) -> dict[str, Any]:
    """Create (or replace) the caller's own template from one captured frame."""
    s = app_settings()
    emp = _require_employee(db, user)
    employee_id = emp.id
    purpose = "enroll"
    _consume_challenge(db, user, employee_id, purpose, nonce, token)
    capture = _analyze(db, user, employee_id, engine, purpose, image_bytes)

    meta = {
        "detector_score": capture.detector_score,
        "face_width_px": capture.face_width_px,
        "image_width": capture.image_width,
        "image_height": capture.image_height,
    }  # non-biometric quality metadata only — no pixels, no embedding

    existing = _template_for(db, user, employee_id)
    now = utc_now()
    if existing is None:
        tpl = EmployeeFaceTemplate(
            company_id=user.company_id,
            employee_id=employee_id,
            embedding=json.dumps(capture.embedding),
            embedding_dim=len(capture.embedding),
            model_name=MODEL_REVISION,
            template_version=1,
            is_active=True,
            capture_meta=meta,
            enrolled_by_user_id=user.id,
            enrolled_at=now,
        )
        db.add(tpl)
        db.flush()
        re_enrolled = False
    else:
        tpl = existing
        tpl.embedding = json.dumps(capture.embedding)
        tpl.embedding_dim = len(capture.embedding)
        tpl.model_name = MODEL_REVISION
        tpl.template_version += 1
        tpl.is_active = True
        tpl.capture_meta = meta
        tpl.enrolled_by_user_id = user.id
        re_enrolled = True

    # audit without biometric data
    record_audit(
        db,
        company_id=user.company_id,
        user=user,
        action="face.enroll",
        entity_type="face_template",
        entity_id=tpl.id,
        after={
            "employee_id": employee_id,
            "template_version": tpl.template_version,
            "model_name": tpl.model_name,
            "re_enrolled": re_enrolled,
        },
    )
    db.add(
        FaceVerificationEvent(
            company_id=user.company_id,
            employee_id=employee_id,
            user_id=user.id,
            purpose=purpose,
            outcome="reenrolled" if re_enrolled else "enrolled",
            detector_score=capture.detector_score,
            template_version=tpl.template_version,
        )
    )
    db.commit()
    db.refresh(tpl)
    return {
        "enrolled": True,
        "re_enrolled": re_enrolled,
        "template_version": tpl.template_version,
        "model": tpl.model_name,
        "enrolled_at": _iso(tpl.enrolled_at),
        "match_threshold": s.face_match_threshold,
    }


def verify_only(
    db: Session,
    user: User,
    engine: FaceEngine,
    image_bytes: bytes,
    lat: float | None,
    lng: float | None,
    accuracy_m: float | None,
    nonce: str | None,
    token: str | None,
) -> dict[str, Any]:
    """Match the frame against the caller's template without writing
    attendance (used for enrolment self-tests and diagnostics)."""
    s = app_settings()
    purpose = "verify"
    employee_id, tpl, capture, similarity = _verify_identity(
        db, user, engine, purpose, image_bytes, nonce, token
    )
    location = None
    if lat is not None or lng is not None or accuracy_m is not None:
        lat, lng, distance = _check_location(
            db, user, employee_id, purpose, lat, lng, accuracy_m, required=False
        )
        location = _location_block(distance, accuracy_m)

    db.add(
        FaceVerificationEvent(
            company_id=user.company_id,
            employee_id=employee_id,
            user_id=user.id,
            purpose=purpose,
            outcome="matched",
            similarity=round(similarity, 4),
            threshold=s.face_match_threshold,
            detector_score=capture.detector_score,
            template_version=tpl.template_version,
            lat=lat,
            lng=lng,
            accuracy_m=accuracy_m,
            distance_m=(location or {}).get("distance_m"),
        )
    )
    db.commit()
    return {
        "verified": True,
        "purpose": purpose,
        "similarity": round(similarity, 4),
        "match_threshold": s.face_match_threshold,
        "detector_score": capture.detector_score,
        "template_version": tpl.template_version,
        "location": location,
        "attendance": None,
    }


def check_in_face(
    db: Session,
    user: User,
    engine: FaceEngine,
    image_bytes: bytes,
    lat: float | None,
    lng: float | None,
    accuracy_m: float | None,
    nonce: str | None,
    token: str | None,
) -> dict[str, Any]:
    s = app_settings()
    purpose = "check_in"
    employee_id, tpl, capture, similarity = _verify_identity(
        db, user, engine, purpose, image_bytes, nonce, token
    )
    lat, lng, distance = _check_location(
        db, user, employee_id, purpose, lat, lng, accuracy_m, required=True
    )

    try:
        record = attendance_check_in(
            db,
            user=user,
            payload=CheckInRequest(lat=lat, lng=lng, accuracy_m=accuracy_m),
            source="face_camera",
        )
    except HTTPException as exc:
        outcome = (
            "duplicate_check_in" if exc.status_code == 409 else "attendance_rejected"
        )
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            outcome,
            exc.status_code,
            str(exc.detail),
            similarity=round(similarity, 4),
            threshold=s.face_match_threshold,
            detector_score=capture.detector_score,
            template_version=tpl.template_version,
            lat=lat,
            lng=lng,
            accuracy_m=accuracy_m,
            distance_m=distance,
        ) from exc

    db.add(
        FaceVerificationEvent(
            company_id=user.company_id,
            employee_id=employee_id,
            user_id=user.id,
            purpose=purpose,
            outcome="matched",
            similarity=round(similarity, 4),
            threshold=s.face_match_threshold,
            detector_score=capture.detector_score,
            template_version=tpl.template_version,
            lat=lat,
            lng=lng,
            accuracy_m=accuracy_m,
            distance_m=distance,
            attendance_id=record.get("id"),
        )
    )
    db.commit()
    return {
        "verified": True,
        "purpose": purpose,
        "similarity": round(similarity, 4),
        "match_threshold": s.face_match_threshold,
        "detector_score": capture.detector_score,
        "template_version": tpl.template_version,
        "location": _location_block(distance, accuracy_m),
        "attendance": record,
    }


def check_out_face(
    db: Session,
    user: User,
    engine: FaceEngine,
    image_bytes: bytes,
    lat: float | None,
    lng: float | None,
    accuracy_m: float | None,
    nonce: str | None,
    token: str | None,
) -> dict[str, Any]:
    s = app_settings()
    purpose = "check_out"
    employee_id, tpl, capture, similarity = _verify_identity(
        db, user, engine, purpose, image_bytes, nonce, token
    )
    lat, lng, distance = _check_location(
        db, user, employee_id, purpose, lat, lng, accuracy_m, required=True
    )

    try:
        record = attendance_check_out(db, user=user)
    except HTTPException as exc:
        outcome = "state_conflict" if exc.status_code == 409 else "attendance_rejected"
        raise _fail(
            db,
            user,
            employee_id,
            purpose,
            outcome,
            exc.status_code,
            str(exc.detail),
            similarity=round(similarity, 4),
            threshold=s.face_match_threshold,
            detector_score=capture.detector_score,
            template_version=tpl.template_version,
            lat=lat,
            lng=lng,
            accuracy_m=accuracy_m,
            distance_m=distance,
        ) from exc

    db.add(
        FaceVerificationEvent(
            company_id=user.company_id,
            employee_id=employee_id,
            user_id=user.id,
            purpose=purpose,
            outcome="matched",
            similarity=round(similarity, 4),
            threshold=s.face_match_threshold,
            detector_score=capture.detector_score,
            template_version=tpl.template_version,
            lat=lat,
            lng=lng,
            accuracy_m=accuracy_m,
            distance_m=distance,
            attendance_id=record.get("id"),
        )
    )
    db.commit()
    return {
        "verified": True,
        "purpose": purpose,
        "similarity": round(similarity, 4),
        "match_threshold": s.face_match_threshold,
        "detector_score": capture.detector_score,
        "template_version": tpl.template_version,
        "location": _location_block(distance, accuracy_m),
        "attendance": record,
    }
