"""Application configuration loaded from environment / .env."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "info"
    api_port: int = 8000

    database_url: str = f"sqlite:///{BACKEND_DIR / 'hcm_lite.db'}"

    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 720

    admin_email: str | None = None
    admin_password: str | None = None

    ai_provider: str = "offline"
    ai_api_key: str | None = None
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: float = 15.0
    ai_rate_limit_per_hour: int = 20
    ai_mock_mode: bool = False

    # ---- Face verification attendance (M10) ---------------------------------
    # Model files live outside the source tree listing; download once with
    # ``python -m app.face.models`` (sha256-pinned URLs, see that module).
    face_model_dir: str = str(BACKEND_DIR / "face_models")
    face_match_threshold: float = 0.40  # cosine similarity (calibrated: genuine >=0.91)
    face_detector_score: float = 0.7  # YuNet min detection confidence
    face_min_face_px: int = 80  # smallest acceptable face width for enrollment/verify
    face_challenge_ttl_seconds: int = 120  # verification challenge lifetime
    face_max_image_mb: int = 6  # hard cap on uploaded frame size
    face_retention_days: int = 30  # challenge rows older than this are pruned

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
