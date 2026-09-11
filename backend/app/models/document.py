"""ORM model for a processed document result."""
import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProcessedDocument(Base):
    __tablename__ = "processed_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_name: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    file_validation: Mapped[dict] = mapped_column(JSON, nullable=False)
    extracted_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation: Mapped[dict] = mapped_column(JSON, nullable=False)
    processing_metadata: Mapped[dict] = mapped_column(JSON, nullable=False)

    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
