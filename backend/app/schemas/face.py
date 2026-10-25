"""Response schemas for the face attendance endpoints (M10).

No schema ever carries an embedding or image bytes — enrolment status is
metadata only.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FaceOfficeInfo(BaseModel):
    """Office geofence for client-side display only (server re-validates)."""

    lat: float
    lng: float
    radius_m: int


class FaceStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enrolled: bool
    template_version: int | None = None
    model: str | None = None
    enrolled_at: str | None = None
    updated_at: str | None = None
    match_threshold: float
    engine_available: bool
    office: FaceOfficeInfo | None = None


class FaceChallengeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nonce: str
    token: str
    expires_in: int = Field(description="Seconds until the challenge expires")


class FaceLocationInfo(BaseModel):
    distance_m: float | None = None
    accuracy_m: float
    within_geofence: bool | None = None


class FaceResultResponse(BaseModel):
    """Returned by /verify, /check-in and /check-out after a successful match.

    ``attendance`` is the existing attendance record dict (check-in/check-out
    only). Nothing here is a client assertion — every field was computed
    server-side.
    """

    model_config = ConfigDict(extra="forbid")

    verified: bool
    purpose: str
    similarity: float
    match_threshold: float
    detector_score: float
    template_version: int
    location: FaceLocationInfo | None = None
    attendance: dict | None = None
