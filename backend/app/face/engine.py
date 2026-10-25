"""Server-side face detection and verification engine.

Pipeline (all server-side, single decoded frame held in memory only):

1. decode the uploaded frame with OpenCV (never persisted),
2. detect faces with **YuNet** (``face_detection_yunet_2023mar.onnx``),
3. require *exactly one* face above the detector confidence threshold,
4. quality-gate it (minimum face width in pixels),
5. align the face with its 5 landmarks and embed it with **SFace**
   (``face_recognition_sface_2021dec.onnx``) into a 128-d L2-normalised
   descriptor,
6. compare descriptors with cosine similarity in the service layer.

Detection (a face is present) and verification (the face matches the enrolled
template) are deliberately separate steps; this module only produces evidence,
the service decides the outcome.

Model files: ``python -m app.face.models`` (sha256-pinned, Apache-2.0
OpenCV model zoo). OpenCV 5 detection rows are
``[x, y, w, h, lm x5, score]`` — verified against the official sample photos.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings

# Optional heavy imports are deferred so the rest of the API still boots when
# the vision stack is missing; endpoints then answer 503 with instructions.
try:  # pragma: no cover - import guard exercised only on broken installs
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

DETECTOR_FILE = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_FILE = "face_recognition_sface_2021dec.onnx"
MODEL_REVISION = "sface_2021dec+yunet_2023mar"
EMBEDDING_DIM = 128


class FaceAnalysisError(Exception):
    """A frame-level problem the caller can surface to the user.

    ``code`` is stable and machine-readable: ``bad_image`` | ``no_face`` |
    ``multiple_faces`` | ``low_quality`` | ``engine_error``.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class FaceEngineUnavailable(Exception):
    """Models or the vision stack are missing -> endpoints answer 503."""


@dataclass(frozen=True)
class FaceCapture:
    """Evidence extracted from one frame. ``embedding`` is the biometric
    template candidate — keep it out of logs and API responses."""

    embedding: list[float]
    face_count: int
    detector_score: float
    face_width_px: float
    image_width: int
    image_height: int


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


class FaceEngine:
    """Lazily-loaded, thread-safe YuNet + SFace wrapper."""

    def __init__(self, model_dir: str | Path, *, detector_score: float, min_face_px: int):
        self.model_dir = Path(model_dir)
        self.detector_score = detector_score
        self.min_face_px = min_face_px
        self._detector = None
        self._recognizer = None
        self._lock = threading.Lock()

    # -- loading ----------------------------------------------------------- #
    def _require_stack(self) -> None:
        if cv2 is None or np is None:
            raise FaceEngineUnavailable(
                "opencv-python-headless and numpy are required "
                "(pip install -r requirements.txt)"
            )

    def _ensure_loaded(self) -> None:
        self._require_stack()
        if self._detector is not None:
            return
        det_path = self.model_dir / DETECTOR_FILE
        rec_path = self.model_dir / RECOGNIZER_FILE
        missing = [str(p) for p in (det_path, rec_path) if not p.exists()]
        if missing:
            raise FaceEngineUnavailable(
                "face model file(s) missing: "
                + ", ".join(missing)
                + " — run: python -m app.face.models"
            )
        # Model objects are constructed lazily because OpenCV DNN networks are
        # not safe to share across threads without external synchronisation.
        self._detector = cv2.FaceDetectorYN.create(
            str(det_path),
            "",
            (320, 320),
            score_threshold=self.detector_score,
            nms_threshold=0.3,
            top_k=5000,
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(rec_path), "")

    @property
    def available(self) -> bool:
        try:
            self._require_stack()
            return all(
                (self.model_dir / n).exists() for n in (DETECTOR_FILE, RECOGNIZER_FILE)
            )
        except FaceEngineUnavailable:
            return False

    # -- analysis ----------------------------------------------------------- #
    def analyze(self, image_bytes: bytes) -> FaceCapture:
        """Detect faces in one frame and embed the (single) best one.

        Raises ``FaceAnalysisError`` for every rejection reason; raises
        ``FaceEngineUnavailable`` when models cannot be loaded.
        """
        self._ensure_loaded()
        if not image_bytes:
            raise FaceAnalysisError("bad_image", "The uploaded frame is empty")

        buf = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None or img.size == 0:
            raise FaceAnalysisError(
                "bad_image", "The uploaded file is not a decodable image"
            )
        height, width = img.shape[:2]
        if height < 64 or width < 64:
            raise FaceAnalysisError(
                "low_quality", f"Image too small to analyse ({width}x{height})"
            )

        with self._lock:
            self._ensure_loaded()
            self._detector.setInputSize((width, height))
            result = self._detector.detect(img)
            if not (isinstance(result, tuple) and len(result) == 2):
                raise FaceAnalysisError(
                    "engine_error", "Unexpected detector output format"
                )
            faces = result[1]
            if faces is None or len(faces) == 0:
                raise FaceAnalysisError(
                    "no_face", "No face detected in the camera frame"
                )
            if len(faces) > 1:
                raise FaceAnalysisError(
                    "multiple_faces",
                    f"Multiple faces detected ({len(faces)}) — only one person is allowed",
                )
            row = faces[0]
            if row.shape[0] != 15:
                raise FaceAnalysisError(
                    "engine_error",
                    f"Unexpected detection row shape {tuple(row.shape)}",
                )
            score = float(row[14])
            face_w = float(row[2])
            face_h = float(row[3])
            if face_w < self.min_face_px or face_h < self.min_face_px:
                raise FaceAnalysisError(
                    "low_quality",
                    f"Face too small or too far away ({face_w:.0f}x{face_h:.0f} px, "
                    f"minimum {self.min_face_px} px) — move closer",
                )
            aligned = self._recognizer.alignCrop(img, row)
            feat = self._recognizer.feature(aligned).astype(np.float64).ravel()
            norm = float(np.linalg.norm(feat))
            if norm == 0.0:
                raise FaceAnalysisError("engine_error", "Empty face descriptor")
            feat = feat / norm

        return FaceCapture(
            embedding=[round(float(v), 6) for v in feat],
            face_count=int(len(faces)),
            detector_score=round(score, 4),
            face_width_px=round(face_w, 1),
            image_width=int(width),
            image_height=int(height),
        )


_engine: FaceEngine | None = None
_engine_lock = threading.Lock()


def get_face_engine() -> FaceEngine:
    """Process-wide engine singleton (FastAPI dependency + tests override)."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                s = get_settings()
                _engine = FaceEngine(
                    s.face_model_dir,
                    detector_score=s.face_detector_score,
                    min_face_px=s.face_min_face_px,
                )
    return _engine
