"""Pydantic schemas describing the structured processing result envelope.

The extracted_data payload shape legitimately differs per document_type
(invoice fields vs. balance-sheet line items, etc.) so it is kept as a
free-form dict at the top level, while every individual field inside it
follows the ExtractedField shape enforced by the extraction services.
"""
from typing import Any

from pydantic import BaseModel


class Evidence(BaseModel):
    source_text: str | None = None
    page_number: int | None = None


class ExtractedField(BaseModel):
    value: Any = None
    confidence: float | None = None
    page_number: int | None = None
    evidence: Evidence | None = None


class FileValidation(BaseModel):
    file_type: str
    is_supported: bool
    is_readable: bool
    page_count: int | None = None
    status: str
    reason: str | None = None


class ValidationCheck(BaseModel):
    name: str
    formula: str
    operands: dict[str, Any]
    calculated_value: float | None = None
    reported_value: float | None = None
    variance: float | None = None
    status: str  # PASS | FAIL | NOT_APPLICABLE
    period: str | None = None
    message: str | None = None


class ValidationResult(BaseModel):
    checks: list[ValidationCheck]
    overall_status: str
    issues: list[str]


class ProcessingMetadata(BaseModel):
    ocr_used: bool
    processed_at: str
    processing_time_ms: int
    extraction_method: str


class ProcessDocumentResponse(BaseModel):
    document_name: str
    document_type: str
    processing_status: str
    overall_confidence: float | None = None
    file_validation: FileValidation
    extracted_data: dict[str, Any]
    validation: ValidationResult
    processing_metadata: ProcessingMetadata
