"""M10 face attendance tests.

CV + geolocation providers are mocked (``FakeFaceEngine``) so the suite is
deterministic and offline; one test additionally exercises the REAL OpenCV
engine when the model files are present. Mocks prove control flow and rule
enforcement — they do not claim real-world recognition accuracy (see
docs/face-attendance.md for the manual camera procedure).
"""
from __future__ import annotations

import hashlib
import io
import json

import pytest
from fastapi.testclient import TestClient

from app.face.engine import (
    FaceAnalysisError,
    FaceCapture,
    FaceEngineUnavailable,
    get_face_engine,
)
from app.main import app
from app.models import Attendance, CompanySettings, EmployeeFaceTemplate, FaceVerificationEvent

# --------------------------------------------------------------------------- #
# Mocked CV provider
# --------------------------------------------------------------------------- #
class FakeFaceEngine:
    """Marker-driven stand-in for the real YuNet/SFace stack.

    Frame bytes follow ``frame:<marker>``:
    * ``noface`` / ``twofaces`` / ``small`` / ``garbage`` trigger the matching
      rejection,
    * any other marker becomes the person's identity — embeddings are derived
      deterministically from the marker, so same marker = same identity,
      different marker = a different (near-orthogonal) identity.
    """

    available = True

    def analyze(self, image_bytes: bytes) -> FaceCapture:
        if not image_bytes.startswith(b"frame:"):
            raise FaceAnalysisError(
                "bad_image", "The uploaded file is not a decodable image"
            )
        marker = image_bytes[6:].decode("ascii", "replace")
        if marker == "garbage":
            raise FaceAnalysisError(
                "bad_image", "The uploaded file is not a decodable image"
            )
        if marker == "noface":
            raise FaceAnalysisError("no_face", "No face detected in the camera frame")
        if marker == "twofaces":
            raise FaceAnalysisError(
                "multiple_faces", "Multiple faces detected (2) — only one person is allowed"
            )
        if marker == "small":
            raise FaceAnalysisError(
                "low_quality", "Face too small or too far away — move closer"
            )
        return FaceCapture(
            embedding=_embedding_for(marker),
            face_count=1,
            detector_score=0.93,
            face_width_px=210.0,
            image_width=640,
            image_height=480,
        )


class BrokenEngine(FakeFaceEngine):
    """Simulates models not downloaded / vision stack missing."""

    available = False

    def analyze(self, image_bytes: bytes) -> FaceCapture:
        raise FaceEngineUnavailable("face model file(s) missing — run: python -m app.face.models")


def _embedding_for(marker: str) -> list[float]:
    # Independent deterministic vector per marker: every dimension depends on
    # the marker, so different markers yield near-orthogonal identities
    # (cosine ~= 0, far below the 0.40 threshold) and the same marker yields
    # an identical vector (cosine = 1.0).
    vals = []
    for i in range(128):
        digest = hashlib.sha256(f"hcm-face:{marker}:{i}".encode()).digest()
        vals.append(int.from_bytes(digest[:4], "big") / 2**31 - 1.0)
    norm = sum(v * v for v in vals) ** 0.5
    return [round(v / norm, 6) for v in vals]


@pytest.fixture(autouse=True)
def fake_engine():
    engine = FakeFaceEngine()
    app.dependency_overrides[get_face_engine] = lambda: engine
    yield engine
    app.dependency_overrides.pop(get_face_engine, None)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _challenge(client: TestClient, headers: dict[str, str]) -> dict:
    r = client.post("/api/attendance/face/challenge", headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _post_frame(
    client: TestClient,
    headers: dict[str, str],
    route: str,
    marker: str,
    *,
    form: dict | None = None,
    nonce: str | None = None,
    token: str | None = None,
    content_type: str = "image/jpeg",
    payload: bytes | None = None,
):
    if nonce is None:
        ch = _challenge(client, headers)
        nonce, token = ch["nonce"], ch["token"]
    data: dict[str, str] = {"nonce": nonce, "token": token or ""}
    if form:
        data.update({k: str(v) for k, v in form.items()})
    body = payload if payload is not None else f"frame:{marker}".encode()
    return client.post(
        route,
        data=data,
        files={"file": ("frame.jpg", body, content_type)},
        headers=headers,
    )


GEO_OK = {"lat": 24.8607, "lng": 67.0011, "accuracy_m": 15}  # inside office below


def _set_office(db, lat=24.8607, lng=67.0011, radius=100) -> None:
    s = db.query(CompanySettings).first()
    assert s is not None
    s.office_lat = lat
    s.office_lng = lng
    s.geofence_radius_m = radius
    db.commit()


def _events(db) -> list[FaceVerificationEvent]:
    db.expire_all()
    return db.query(FaceVerificationEvent).order_by(FaceVerificationEvent.id).all()


# --------------------------------------------------------------------------- #
# Status + enrolment
# --------------------------------------------------------------------------- #
def test_status_before_enrollment(client: TestClient, emp_headers):
    r = client.get("/api/attendance/face/status", headers=emp_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["enrolled"] is False
    assert body["template_version"] is None
    assert body["engine_available"] is True
    assert body["match_threshold"] > 0
    assert "embedding" not in json.dumps(body).lower()


def test_enroll_and_reenroll(client: TestClient, emp_headers, db):
    r = _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["enrolled"] is True
    assert body["re_enrolled"] is False
    assert body["template_version"] == 1
    assert "embedding" not in json.dumps(body).lower()

    # re-enrolment replaces the template and bumps the version
    r2 = _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real-v2")
    assert r2.status_code == 201, r2.text
    assert r2.json()["re_enrolled"] is True
    assert r2.json()["template_version"] == 2

    db.expire_all()
    tpl = db.query(EmployeeFaceTemplate).one()
    # template belongs to the session's own employee only
    from app.models import User

    sara = db.query(User).filter_by(email="sara@acme.test").one()
    assert tpl.employee_id == sara.employee_id
    assert tpl.template_version == 2
    meta = tpl.capture_meta or {}
    assert set(meta) == {"detector_score", "face_width_px", "image_width", "image_height"}
    # audit row written WITHOUT biometric data
    from app.models import AuditLog

    audit = db.query(AuditLog).filter_by(action="face.enroll").all()
    assert audit, "face.enroll must be audited"
    for row in audit:
        assert "embedding" not in json.dumps(row.after or {}).lower()
    # events recorded
    outcomes = [e.outcome for e in _events(db)]
    assert outcomes == ["enrolled", "reenrolled"]


def test_status_is_self_scoped(client: TestClient, emp_headers, hr_headers):
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    # a different authenticated user sees ONLY their own (absent) template
    r = client.get("/api/attendance/face/status", headers=hr_headers)
    assert r.status_code == 200
    assert r.json()["enrolled"] is False
    # no endpoint accepts or returns another employee's template
    r2 = client.get("/api/attendance/face/status?employee_id=999", headers=hr_headers)
    assert r2.status_code == 200 and r2.json()["enrolled"] is False


def test_extra_employee_id_form_field_is_ignored(client: TestClient, emp_headers, db, company):
    """A client cannot enrol a face against another employee's account."""
    ch = _challenge(client, emp_headers)
    r = client.post(
        "/api/attendance/face/enroll",
        data={
            "nonce": ch["nonce"],
            "token": ch["token"],
            "employee_id": str(company["employee"].id + 999),  # spoof attempt
        },
        files={"file": ("frame.jpg", b"frame:sara-real", "image/jpeg")},
        headers=emp_headers,
    )
    assert r.status_code == 201, r.text
    db.expire_all()
    from app.models import User

    sara = db.query(User).filter_by(email="sara@acme.test").one()
    tpl = db.query(EmployeeFaceTemplate).one()
    assert tpl.employee_id == sara.employee_id


def test_admin_without_employee_profile_cannot_enroll(client: TestClient, admin_headers):
    r = _post_frame(client, admin_headers, "/api/attendance/face/enroll", "boss")
    assert r.status_code == 403
    assert "employee profile" in r.json()["detail"].lower()


# --------------------------------------------------------------------------- #
# Detection vs verification
# --------------------------------------------------------------------------- #
def test_no_template_rejected(client: TestClient, emp_headers, db):
    r = _post_frame(client, emp_headers, "/api/attendance/face/check-in", "sara-real", form=GEO_OK)
    assert r.status_code == 409
    assert "not enrolled" in r.json()["detail"].lower()
    assert db.query(Attendance).count() == 0
    assert _events(db)[-1].outcome == "no_template"


def test_no_face_detected(client: TestClient, emp_headers, db):
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    r = _post_frame(client, emp_headers, "/api/attendance/face/check-in", "noface", form=GEO_OK)
    assert r.status_code == 422
    assert "no face" in r.json()["detail"].lower()
    assert db.query(Attendance).count() == 0
    assert _events(db)[-1].outcome == "no_face"


def test_multiple_faces_detected(client: TestClient, emp_headers, db):
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    r = _post_frame(client, emp_headers, "/api/attendance/face/check-in", "twofaces", form=GEO_OK)
    assert r.status_code == 422
    assert "multiple faces" in r.json()["detail"].lower()
    assert db.query(Attendance).count() == 0


def test_low_quality_face_rejected(client: TestClient, emp_headers, db):
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    r = _post_frame(client, emp_headers, "/api/attendance/face/verify", "small")
    assert r.status_code == 422
    assert _events(db)[-1].outcome == "low_quality"


def test_undecodable_frame_rejected(client: TestClient, emp_headers, db):
    r = _post_frame(client, emp_headers, "/api/attendance/face/enroll", "", payload=b"not-an-image")
    assert r.status_code == 422
    assert _events(db)[-1].outcome == "bad_image"


def test_unsupported_content_type(client: TestClient, emp_headers, db):
    r = _post_frame(
        client,
        emp_headers,
        "/api/attendance/face/enroll",
        "sara-real",
        content_type="application/pdf",
    )
    assert r.status_code == 422
    assert "unsupported image type" in r.json()["detail"].lower()
    assert db.query(EmployeeFaceTemplate).count() == 0


def test_oversized_frame_rejected(client: TestClient, emp_headers, db):
    big = b"a" * (6 * 1024 * 1024 + 1)
    r = _post_frame(client, emp_headers, "/api/attendance/face/enroll", "", payload=big)
    assert r.status_code == 422
    assert "limit" in r.json()["detail"].lower()


def test_face_mismatch_rejected_and_no_attendance(
    client: TestClient, emp_headers, db, company
):
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    r = _post_frame(
        client, emp_headers, "/api/attendance/face/check-in", "intruder", form=GEO_OK
    )
    assert r.status_code == 422
    assert "does not match" in r.json()["detail"].lower()
    # failed verification must not create attendance or count as a punch
    assert db.query(Attendance).count() == 0
    ev = _events(db)[-1]
    assert ev.outcome == "face_mismatch"
    assert ev.similarity is not None and ev.threshold is not None
    assert ev.similarity < ev.threshold
    # analytics must not see a record either
    r2 = client.get("/api/attendance/me", headers=emp_headers)
    assert all(not rec.get("check_in") for rec in r2.json()["records"])


def test_engine_unavailable_503(client: TestClient, emp_headers, db):
    app.dependency_overrides[get_face_engine] = lambda: BrokenEngine()
    r = client.get("/api/attendance/face/status", headers=emp_headers)
    assert r.status_code == 200 and r.json()["engine_available"] is False
    r2 = _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real")
    assert r2.status_code == 503
    assert "python -m app.face.models" in r2.json()["detail"]
    assert db.query(EmployeeFaceTemplate).count() == 0


# --------------------------------------------------------------------------- #
# Challenges (anti-replay)
# --------------------------------------------------------------------------- #
def test_invalid_challenge_token(client: TestClient, emp_headers, db):
    r = _post_frame(
        client, emp_headers, "/api/attendance/face/check-in", "sara-real",
        nonce="made-up-nonce", token="forged-token", form=GEO_OK,
    )
    assert r.status_code == 400
    assert "challenge" in r.json()["detail"].lower()
    assert _events(db)[-1].outcome == "challenge_invalid"


def test_expired_challenge_rejected(client: TestClient, emp_headers, db):
    import datetime as dt

    from app.models import FaceChallenge
    from app.services.attendance_service import utc_now
    from app.services.face_service import _sign

    ch = _challenge(client, emp_headers)
    row = db.query(FaceChallenge).filter_by(nonce=ch["nonce"]).one()
    # expire it AND re-sign so the token stays valid (proves expiry, not auth)
    row.expires_at = utc_now() - dt.timedelta(seconds=5)
    row.token = _sign(row.nonce, row.user_id, row.expires_at)
    db.commit()
    r = _post_frame(
        client, emp_headers, "/api/attendance/face/verify", "sara-real",
        nonce=ch["nonce"], token=row.token,  # valid signature, expired row
    )
    assert r.status_code == 410
    assert "expired" in r.json()["detail"].lower()
    assert _events(db)[-1].outcome == "challenge_expired"


def test_challenge_is_single_use(client: TestClient, emp_headers, db):
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    ch = _challenge(client, emp_headers)
    r1 = _post_frame(
        client, emp_headers, "/api/attendance/face/verify", "sara-real",
        nonce=ch["nonce"], token=ch["token"],
    )
    assert r1.status_code == 200, r1.text
    # replay of the exact same request -> rejected
    r2 = _post_frame(
        client, emp_headers, "/api/attendance/face/verify", "sara-real",
        nonce=ch["nonce"], token=ch["token"],
    )
    assert r2.status_code == 409
    assert "already used" in r2.json()["detail"].lower()
    assert _events(db)[-1].outcome == "challenge_replayed"


def test_challenge_requires_auth(client: TestClient):
    r = client.post("/api/attendance/face/challenge")
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# Location / geofence
# --------------------------------------------------------------------------- #
def test_missing_location_rejected(client: TestClient, emp_headers, db):
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    r = _post_frame(client, emp_headers, "/api/attendance/face/check-in", "sara-real")
    assert r.status_code == 422
    assert "location is required" in r.json()["detail"].lower()
    assert db.query(Attendance).count() == 0


def test_invalid_coordinates_rejected(client: TestClient, emp_headers, db):
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    r = _post_frame(
        client, emp_headers, "/api/attendance/face/check-in", "sara-real",
        form={"lat": 999, "lng": 67.0, "accuracy_m": 10},
    )
    assert r.status_code == 422
    assert "invalid gps" in r.json()["detail"].lower()
    assert db.query(Attendance).count() == 0
    assert _events(db)[-1].outcome == "invalid_coordinates"


def test_unparseable_coordinates_rejected(client: TestClient, emp_headers):
    r = _post_frame(
        client, emp_headers, "/api/attendance/face/check-in", "sara-real",
        form={"lat": "abc", "lng": 67.0, "accuracy_m": 10},
    )
    assert r.status_code == 422  # FastAPI form parsing


def test_accuracy_worse_than_100m_rejected(client: TestClient, emp_headers, db):
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    r = _post_frame(
        client, emp_headers, "/api/attendance/face/check-in", "sara-real",
        form={"lat": 24.8607, "lng": 67.0011, "accuracy_m": 150},
    )
    assert r.status_code == 422
    assert "accuracy" in r.json()["detail"].lower()
    assert db.query(Attendance).count() == 0
    assert _events(db)[-1].outcome == "accuracy_too_low"


def test_outside_geofence_rejected(client: TestClient, emp_headers, db):
    _set_office(db, lat=24.8607, lng=67.0011, radius=100)
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    r = _post_frame(
        client, emp_headers, "/api/attendance/face/check-in", "sara-real",
        form={"lat": 25.8607, "lng": 67.0011, "accuracy_m": 10},
    )
    assert r.status_code == 422
    assert "outside office geofence" in r.json()["detail"].lower()
    assert db.query(Attendance).count() == 0
    ev = _events(db)[-1]
    assert ev.outcome == "outside_geofence"
    assert ev.distance_m and ev.distance_m > 100


def test_outside_geofence_on_check_out_too(client: TestClient, emp_headers, db):
    _set_office(db, lat=24.8607, lng=67.0011, radius=100)
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    ok = _post_frame(
        client, emp_headers, "/api/attendance/face/check-in", "sara-real", form=GEO_OK
    )
    assert ok.status_code == 201, ok.text
    r = _post_frame(
        client, emp_headers, "/api/attendance/face/check-out", "sara-real",
        form={"lat": 25.8607, "lng": 67.0011, "accuracy_m": 10},
    )
    assert r.status_code == 422
    assert "outside office geofence" in r.json()["detail"].lower()
    # attendance still open (checked in, not out)
    rec = db.query(Attendance).one()
    assert rec.check_out is None


# --------------------------------------------------------------------------- #
# Happy path + business rules
# --------------------------------------------------------------------------- #
def test_check_in_with_valid_match(client: TestClient, emp_headers, db, company):
    _set_office(db)
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    r = _post_frame(client, emp_headers, "/api/attendance/face/check-in", "sara-real", form=GEO_OK)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["verified"] is True
    assert body["similarity"] >= body["match_threshold"]
    assert body["attendance"]["source"] == "face_camera"
    assert body["location"]["within_geofence"] is True

    db.expire_all()
    rec = db.query(Attendance).one()
    assert rec.source == "face_camera"
    assert rec.status in ("present", "late")
    assert rec.check_in is not None
    ev = _events(db)[-1]
    assert ev.outcome == "matched" and ev.purpose == "check_in"
    assert ev.attendance_id == rec.id
    assert ev.similarity >= ev.threshold


def test_duplicate_check_in_409(client: TestClient, emp_headers, db):
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    first = _post_frame(client, emp_headers, "/api/attendance/face/check-in", "sara-real", form=GEO_OK)
    assert first.status_code == 201
    second = _post_frame(client, emp_headers, "/api/attendance/face/check-in", "sara-real", form=GEO_OK)
    assert second.status_code == 409
    assert "already checked in" in second.json()["detail"].lower()
    assert db.query(Attendance).count() == 1
    assert _events(db)[-1].outcome == "duplicate_check_in"


def test_check_out_flow_and_state_conflicts(client: TestClient, emp_headers, db):
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    # cannot check out before check-in
    r0 = _post_frame(client, emp_headers, "/api/attendance/face/check-out", "sara-real", form=GEO_OK)
    assert r0.status_code == 409
    assert _events(db)[-1].outcome == "state_conflict"

    assert _post_frame(client, emp_headers, "/api/attendance/face/check-in", "sara-real", form=GEO_OK).status_code == 201
    r1 = _post_frame(client, emp_headers, "/api/attendance/face/check-out", "sara-real", form=GEO_OK)
    assert r1.status_code == 200, r1.text
    assert r1.json()["attendance"]["check_out"] is not None
    # double checkout -> 409
    r2 = _post_frame(client, emp_headers, "/api/attendance/face/check-out", "sara-real", form=GEO_OK)
    assert r2.status_code == 409
    assert db.query(Attendance).count() == 1


def test_face_check_in_feeds_existing_dashboards_and_analytics(
    client: TestClient, emp_headers, hr_headers, db
):
    """Face-created rows are the SAME authoritative attendance records."""
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    assert _post_frame(client, emp_headers, "/api/attendance/face/check-in", "sara-real", form=GEO_OK).status_code == 201

    # employee month view
    me = client.get("/api/attendance/me", headers=emp_headers).json()
    today_rows = [r for r in me["records"] if r["check_in"]]
    assert today_rows and today_rows[0]["source"] == "face_camera"

    # HR day roster includes Sara as present/late
    board = client.get("/api/attendance/board", headers=hr_headers).json()
    rows = board["items"]
    sara_rows = [r for r in rows if "Sara" in str(r.get("full_name", ""))]
    assert sara_rows, board
    assert sara_rows[0].get("status") in ("present", "late")

    # analytics aggregate reads the same attendance rows
    summary = client.get("/api/analytics/hr", headers=hr_headers)
    assert summary.status_code == 200, summary.text


# --------------------------------------------------------------------------- #
# Authorization
# --------------------------------------------------------------------------- #
def test_face_routes_require_auth(client: TestClient):
    for method, path in (
        ("get", "/api/attendance/face/status"),
        ("post", "/api/attendance/face/challenge"),
        ("post", "/api/attendance/face/enroll"),
        ("post", "/api/attendance/face/verify"),
        ("post", "/api/attendance/face/check-in"),
        ("post", "/api/attendance/face/check-out"),
    ):
        r = getattr(client, method)(path)
        assert r.status_code == 401, (path, r.status_code)


def test_identity_derived_from_session_not_client(
    client: TestClient, emp_headers, hr_headers, db
):
    """HR with no template cannot check in even using the employee's frame —
    the employee identity comes from the token, not the request body."""
    assert _post_frame(client, emp_headers, "/api/attendance/face/enroll", "sara-real").status_code == 201
    r = _post_frame(client, hr_headers, "/api/attendance/face/check-in", "sara-real", form=GEO_OK)
    assert r.status_code == 409  # HR's own (missing) template
    assert "not enrolled" in r.json()["detail"].lower()
    assert db.query(Attendance).count() == 0


# --------------------------------------------------------------------------- #
# REAL engine (models must be downloaded) — detection path only
# --------------------------------------------------------------------------- #
def _real_engine_available() -> bool:
    try:
        return get_face_engine().available
    except Exception:
        return False


@pytest.mark.skipif(not _real_engine_available(), reason="face models not downloaded")
def test_real_engine_rejects_frame_without_face(client: TestClient, emp_headers, db):
    """Real YuNet runs server-side: a non-face photo must be rejected."""
    from PIL import Image

    app.dependency_overrides.pop(get_face_engine, None)  # exercise the REAL engine
    buf = io.BytesIO()
    Image.new("RGB", (320, 240), (120, 130, 140)).save(buf, format="JPEG")
    assert _post_frame(
        client, emp_headers, "/api/attendance/face/enroll", "x", payload=buf.getvalue()
    ).status_code == 422
    assert db.query(EmployeeFaceTemplate).count() == 0
