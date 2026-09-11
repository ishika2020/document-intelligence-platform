"""Orchestrates the full document processing pipeline:

  validate file -> OCR/text extraction -> AI-based field extraction
  -> financial validation -> confidence -> structured result

This is the only place that sequences the other services together, so the
API layer and the persistence layer stay decoupled from how processing
actually happens.
"""
import datetime
import time
from typing import Any

from app.core.logging import get_logger
from app.schemas.document import DocumentType
from app.services import extraction_service, financial_validation_service, ocr_service
from app.services.document_validation_service import validate_file
from app.utils.exceptions import DocumentIntelligenceError

logger = get_logger(__name__)


def _collect_confidences(node: Any, out: list[float]) -> None:
    if isinstance(node, dict):
        conf = node.get("confidence")
        if isinstance(conf, (int, float)):
            out.append(float(conf))
        for value in node.values():
            _collect_confidences(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_confidences(item, out)


def _overall_confidence(extracted_data: dict) -> float | None:
    scores: list[float] = []
    _collect_confidences(extracted_data, scores)
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


_EXTRACTION_METHOD = {
    "invoice": "regex/keyword rule-based extraction over OCR text",
    "balance_sheet": "positional label/value table parser over OCR text",
    "profit_and_loss": "positional label/value table parser over OCR text",
    "cash_flow_statement": "positional label/value table parser over OCR text",
}


def process_document(filename: str, content_type: str | None, data: bytes, document_type: DocumentType) -> dict:
    """Run the full pipeline for one uploaded document and return the
    structured response dict matching ProcessDocumentResponse."""
    start = time.monotonic()
    file_validation = validate_file(filename, content_type, data)

    if file_validation.status != "PASS":
        logger.warning("File validation failed for %s: %s", filename, file_validation.reason)
        return _build_response(
            document_name=filename,
            document_type=document_type.value,
            processing_status="FAILED",
            overall_confidence=None,
            file_validation=file_validation.model_dump(),
            extracted_data={},
            validation={"checks": [], "overall_status": "NOT_APPLICABLE", "issues": [file_validation.reason or "File validation failed."]},
            ocr_used=False,
            started=start,
        )

    try:
        content = ocr_service.extract_document_content(data, file_validation.file_type)
        result = extraction_service.extract(document_type.value, content)
        validation = financial_validation_service.validate(document_type.value, result.extracted_data, result.statement)
        overall_confidence = _overall_confidence(result.extracted_data)

        return _build_response(
            document_name=filename,
            document_type=document_type.value,
            processing_status="PASS",
            overall_confidence=overall_confidence,
            file_validation=file_validation.model_dump(),
            extracted_data=result.extracted_data,
            validation=validation,
            ocr_used=content.ocr_used,
            started=start,
            extraction_method=_EXTRACTION_METHOD.get(document_type.value, "rule-based extraction"),
        )
    except DocumentIntelligenceError as exc:
        logger.error("Processing failed for %s: %s", filename, exc.message)
        return _build_response(
            document_name=filename,
            document_type=document_type.value,
            processing_status="FAILED",
            overall_confidence=None,
            file_validation=file_validation.model_dump(),
            extracted_data={},
            validation={"checks": [], "overall_status": "NOT_APPLICABLE", "issues": [exc.message]},
            ocr_used=False,
            started=start,
        )
    except Exception:  # noqa: BLE001 - last-resort safety net; never leak internals to the client
        logger.exception("Unexpected error processing %s", filename)
        return _build_response(
            document_name=filename,
            document_type=document_type.value,
            processing_status="FAILED",
            overall_confidence=None,
            file_validation=file_validation.model_dump(),
            extracted_data={},
            validation={"checks": [], "overall_status": "NOT_APPLICABLE", "issues": ["An unexpected error occurred while processing the document."]},
            ocr_used=False,
            started=start,
        )


def _build_response(
    *,
    document_name: str,
    document_type: str,
    processing_status: str,
    overall_confidence: float | None,
    file_validation: dict,
    extracted_data: dict,
    validation: dict,
    ocr_used: bool,
    started: float,
    extraction_method: str = "n/a",
) -> dict:
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "document_name": document_name,
        "document_type": document_type,
        "processing_status": processing_status,
        "overall_confidence": overall_confidence,
        "file_validation": file_validation,
        "extracted_data": extracted_data,
        "validation": validation,
        "processing_metadata": {
            "ocr_used": ocr_used,
            "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "processing_time_ms": elapsed_ms,
            "extraction_method": extraction_method,
        },
    }
