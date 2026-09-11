"""Input-control validation layer: file type, integrity and page-count checks.

This runs BEFORE any OCR/extraction. It never trusts the client-supplied
filename extension or Content-Type header alone -- the actual file type is
sniffed from magic bytes, which also guards against unsafe/spoofed uploads.
"""
import io

import fitz  # PyMuPDF
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.schemas.extraction import FileValidation

logger = get_logger(__name__)

_MAGIC_PDF = b"%PDF-"
_MAGIC_JPEG = b"\xff\xd8\xff"
_MAGIC_PNG = b"\x89PNG\r\n\x1a\n"


def _sniff_file_type(data: bytes) -> str | None:
    if data.startswith(_MAGIC_PDF):
        return "application/pdf"
    if data.startswith(_MAGIC_JPEG):
        return "image/jpeg"
    if data.startswith(_MAGIC_PNG):
        return "image/png"
    return None


def validate_file(filename: str, declared_content_type: str | None, data: bytes) -> FileValidation:
    """Validate an uploaded document and return a FileValidation result.

    Never raises for document-level problems (unsupported type, empty file,
    corrupted file, page-limit overrun) -- those are reported via the
    returned FileValidation.status so the caller can produce a graceful
    FAILED processing result instead of crashing.
    """
    settings = get_settings()

    if not data:
        logger.warning("Empty file uploaded: %s", filename)
        return FileValidation(
            file_type=declared_content_type or "unknown",
            is_supported=False,
            is_readable=False,
            page_count=None,
            status="FAIL",
            reason="Uploaded file is empty.",
        )

    size_mb = len(data) / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        logger.warning("File too large: %s (%.2f MB)", filename, size_mb)
        return FileValidation(
            file_type=declared_content_type or "unknown",
            is_supported=False,
            is_readable=False,
            page_count=None,
            status="FAIL",
            reason=f"File exceeds maximum allowed size of {settings.max_file_size_mb} MB.",
        )

    detected_type = _sniff_file_type(data)
    if detected_type is None:
        logger.warning("Unsupported file type for: %s (declared=%s)", filename, declared_content_type)
        return FileValidation(
            file_type=declared_content_type or "unknown",
            is_supported=False,
            is_readable=False,
            page_count=None,
            status="FAIL",
            reason="Only PDF, JPG and PNG documents are supported.",
        )

    if detected_type == "application/pdf":
        return _validate_pdf(data, settings.max_pages)
    return _validate_image(data, detected_type)


def _validate_pdf(data: bytes, max_pages: int) -> FileValidation:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - any parse failure means a corrupted PDF
        logger.warning("Corrupted PDF: %s", exc)
        return FileValidation(
            file_type="application/pdf",
            is_supported=True,
            is_readable=False,
            page_count=None,
            status="FAIL",
            reason="PDF file is corrupted or could not be read.",
        )

    try:
        page_count = doc.page_count
        if page_count == 0:
            return FileValidation(
                file_type="application/pdf",
                is_supported=True,
                is_readable=False,
                page_count=0,
                status="FAIL",
                reason="PDF contains no pages.",
            )
        if page_count > max_pages:
            return FileValidation(
                file_type="application/pdf",
                is_supported=True,
                is_readable=True,
                page_count=page_count,
                status="FAIL",
                reason=f"PDF has {page_count} pages, which exceeds the {max_pages}-page limit.",
            )
        return FileValidation(
            file_type="application/pdf",
            is_supported=True,
            is_readable=True,
            page_count=page_count,
            status="PASS",
        )
    finally:
        doc.close()


def _validate_image(data: bytes, detected_type: str) -> FileValidation:
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.warning("Corrupted image: %s", exc)
        return FileValidation(
            file_type=detected_type,
            is_supported=True,
            is_readable=False,
            page_count=None,
            status="FAIL",
            reason="Image file is corrupted or could not be read.",
        )

    return FileValidation(
        file_type=detected_type,
        is_supported=True,
        is_readable=True,
        page_count=1,
        status="PASS",
    )
