"""REST API routes for document upload/processing and retrieval."""
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.repositories import document_repository
from app.schemas.document import DocumentListItem, DocumentListResponse, DocumentType
from app.services.document_service import process_document
from app.utils.exceptions import DocumentNotFoundError, UnsupportedFileTypeError

router = APIRouter(prefix="/documents", tags=["documents"])
logger = get_logger(__name__)


@router.post("/process")
async def process_document_endpoint(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(...),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    data = await file.read()

    size_mb = len(data) / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        raise UnsupportedFileTypeError(
            f"File exceeds maximum allowed size of {settings.max_file_size_mb} MB.",
            code="FILE_TOO_LARGE",
            http_status=413,
        )

    logger.info("Processing upload: name=%s type=%s size=%d bytes", file.filename, document_type.value, len(data))
    result = process_document(file.filename or "unnamed", file.content_type, data, document_type)
    document_repository.save_result(db, result)
    return result


@router.get("")
def list_documents(limit: int = 200, db: Session = Depends(get_db)) -> DocumentListResponse:
    rows = document_repository.list_latest_documents(db, limit=limit)
    return DocumentListResponse(
        total=len(rows),
        documents=[DocumentListItem.model_validate(row) for row in rows],
    )


@router.get("/{document_name}")
def get_document_by_name(document_name: str, db: Session = Depends(get_db)):
    row = document_repository.get_latest_by_name(db, document_name)
    if row is None:
        raise DocumentNotFoundError(f"No processed result found for document_name='{document_name}'.")
    return {
        "document_name": row.document_name,
        "document_type": row.document_type,
        "processing_status": row.processing_status,
        "overall_confidence": row.overall_confidence,
        "file_validation": row.file_validation,
        "extracted_data": row.extracted_data,
        "validation": row.validation,
        "processing_metadata": row.processing_metadata,
    }
