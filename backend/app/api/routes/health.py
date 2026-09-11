"""Health check endpoint."""
from fastapi import APIRouter

from app.schemas.document import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> HealthResponse:
    return HealthResponse(service="document-intelligence-api", version="1.0.0")
