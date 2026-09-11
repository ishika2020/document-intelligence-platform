"""FastAPI application entrypoint.

Serves both the REST API (under /api/v1) and the HTML/CSS/JS frontend
(dashboard + document detail pages) from a single deployable service, which
keeps deployment to one web process while still satisfying "frontend must
call the deployed backend/API" -- the pages are static shells that fetch
data client-side from the JSON API.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import documents, health
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging import configure_logging, get_logger
from app.utils.exceptions import DocumentIntelligenceError

configure_logging()
logger = get_logger(__name__)
settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s started. DB=%s", settings.app_name, settings.database_url)
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Intelligent document extraction, validation & API platform.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allow_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if (FRONTEND_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")

templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates")) if (FRONTEND_DIR / "templates").exists() else None


@app.exception_handler(DocumentIntelligenceError)
async def domain_error_handler(request: Request, exc: DocumentIntelligenceError):
    logger.warning("Handled error on %s: [%s] %s", request.url.path, exc.code, exc.message)
    return JSONResponse(status_code=exc.http_status, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "INVALID_REQUEST", "message": "Request validation failed.", "details": exc.errors()}},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}},
    )


app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(documents.router, prefix=settings.api_v1_prefix)


@app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    if templates is None:
        return HTMLResponse("<h1>Document Intelligence</h1><p>Frontend not found.</p>")
    return templates.TemplateResponse("dashboard.html", {"request": request, "api_base": settings.api_v1_prefix})


@app.get("/documents/{document_name}", response_class=HTMLResponse)
def document_result_page(request: Request, document_name: str):
    if templates is None:
        return HTMLResponse("<h1>Document Intelligence</h1><p>Frontend not found.</p>")
    return templates.TemplateResponse(
        "document_result.html",
        {"request": request, "api_base": settings.api_v1_prefix, "document_name": document_name},
    )
