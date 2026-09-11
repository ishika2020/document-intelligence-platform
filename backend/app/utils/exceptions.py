"""Domain-specific exceptions, mapped to HTTP responses by the API layer."""


class DocumentIntelligenceError(Exception):
    """Base class for controlled, expected application errors."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(self, message: str, code: str | None = None, http_status: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if http_status:
            self.http_status = http_status


class UnsupportedFileTypeError(DocumentIntelligenceError):
    code = "UNSUPPORTED_FILE_TYPE"
    http_status = 415


class FileValidationError(DocumentIntelligenceError):
    code = "FILE_VALIDATION_FAILED"
    http_status = 422


class DocumentNotFoundError(DocumentIntelligenceError):
    code = "DOCUMENT_NOT_FOUND"
    http_status = 404


class OCRProcessingError(DocumentIntelligenceError):
    code = "OCR_PROCESSING_FAILED"
    http_status = 422


class ExtractionError(DocumentIntelligenceError):
    code = "EXTRACTION_FAILED"
    http_status = 422
