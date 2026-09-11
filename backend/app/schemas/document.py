"""Pydantic schemas for API requests and the document list/dashboard views."""
import datetime
import enum

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(str, enum.Enum):
    invoice = "invoice"
    balance_sheet = "balance_sheet"
    profit_and_loss = "profit_and_loss"
    cash_flow_statement = "cash_flow_statement"


class ProcessingStatus(str, enum.Enum):
    PASS = "PASS"
    FAILED = "FAILED"


class DocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_name: str
    document_type: str
    processing_status: str
    overall_confidence: float | None = None
    created_at: datetime.datetime


class DocumentListResponse(BaseModel):
    total: int
    documents: list[DocumentListItem]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str
    timestamp: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))
