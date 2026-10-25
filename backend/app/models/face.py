"""Face attendance models: protected templates, verification events and
one-time challenges (M10).

Privacy contract (ARCHITECTURE M10):
* ``EmployeeFaceTemplate.embedding`` holds ONLY the 128-float L2-normalised
  descriptor — raw photographs are never stored.
* Templates are excluded from every ordinary employee API response; only
  ``GET /api/attendance/face/status`` reports non-biometric enrolment metadata.
* ``FaceVerificationEvent`` records outcomes/metrics for audit — never
  embeddings or image bytes.
* ``FaceChallenge`` backs signed, single-use, short-lived verification
  challenges (anti-replay).
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base
from app.utils.timestamps import TimestampMixin


class EmployeeFaceTemplate(Base, TimestampMixin):
    """Protected biometric template for ONE authenticated employee."""

    __tablename__ = "employee_face_templates"
    __table_args__ = (
        UniqueConstraint("employee_id", name="uq_face_template_employee"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )

    embedding: Mapped[str] = mapped_column(Text, nullable=False)  # JSON[128] floats
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False, default=128)
    model_name: Mapped[str] = mapped_column(String(60), nullable=False)
    template_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Non-biometric capture metadata (quality/telemetry only — no pixels).
    capture_meta: Mapped[dict | None] = mapped_column(JSON)

    enrolled_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    enrolled_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False
    )  # first enrolment (== created_at, kept explicit for API clarity)
    # updated_at from TimestampMixin == last re-enrolment (onupdate=func.now())


class FaceVerificationEvent(Base, TimestampMixin):
    """One row per verification/enrolment attempt — outcomes only."""

    __tablename__ = "face_verification_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    purpose: Mapped[str] = mapped_column(String(20), nullable=False)  # enroll|verify|check_in|check_out
    outcome: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    detail: Mapped[str | None] = mapped_column(String(300))

    similarity: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    detector_score: Mapped[float | None] = mapped_column(Float)
    template_version: Mapped[int | None] = mapped_column(Integer)

    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)

    attendance_id: Mapped[int | None] = mapped_column(
        ForeignKey("attendance.id", ondelete="SET NULL")
    )


class FaceChallenge(Base, TimestampMixin):
    """Single-use, short-lived verification challenge (anti-replay token).

    The client must fetch a challenge before submitting a frame; the server
    marks it used atomically before evaluating the frame, so a captured
    request cannot be replayed and expired challenges are rejected.
    """

    __tablename__ = "face_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nonce: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    token: Mapped[str] = mapped_column(String(200), nullable=False)  # HMAC over nonce.user.exp
    issued_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, index=True)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
