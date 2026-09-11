# Single-service image: FastAPI backend + static/Jinja frontend, OCR via
# local Tesseract. No external API keys required.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/

ENV PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////app/backend/data/document_intelligence.db \
    UPLOAD_DIR=/app/backend/data/uploads \
    OMP_THREAD_LIMIT=1
    # OMP_THREAD_LIMIT=1 caps Tesseract's internal OpenMP threading, which
    # otherwise spikes memory well past 512MB on a single OCR request and
    # gets the process OOM-killed on memory-constrained free-tier hosts.

WORKDIR /app/backend
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
