"""Application configuration, loaded from environment variables / .env file."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Document Intelligence Platform"
    api_v1_prefix: str = "/api/v1"

    # Storage
    database_url: str = "sqlite:///./data/document_intelligence.db"
    upload_dir: str = "./data/uploads"

    # Document validation limits
    max_pages: int = 3
    max_file_size_mb: int = 15
    allowed_content_types: tuple[str, ...] = (
        "application/pdf",
        "image/jpeg",
        "image/jpg",
        "image/png",
    )

    # OCR
    tesseract_cmd: str | None = None  # explicit path to tesseract binary, if not on PATH
    ocr_min_native_chars_per_page: int = 40  # below this, a PDF page is treated as scanned/image-based

    # Financial validation tolerance
    validation_tolerance_abs: float = 1.0  # absolute tolerance in statement currency units
    validation_tolerance_pct: float = 0.01  # 1% relative tolerance, whichever is larger

    # Logging
    log_level: str = "INFO"

    # CORS
    cors_allow_origins: tuple[str, ...] = ("*",)

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path and not db_path.startswith(":memory:"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return settings
