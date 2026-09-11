# Document Intelligence Platform

An end-to-end AI-powered document extraction and validation platform. It accepts **invoices, balance sheets, profit & loss statements and cash flow statements** (PDF / JPG / PNG, up to 3 pages) through a web dashboard or REST API, extracts every meaningful field and table it can find, runs financial-calculation validations, stores results in a database, and returns consistent structured JSON — with evidence back to the source document for every value.

Built for the AI Engineer Internship technical case study (Intelligent Document Extraction, Validation & API Platform).

---

## 1. Live Deployment

| Item | URL |
|---|---|
| Frontend / Dashboard | https://document-intelligence-platform-ptqf.onrender.com/ |
| Backend API (base) | https://document-intelligence-platform-ptqf.onrender.com |
| Swagger / OpenAPI docs | https://document-intelligence-platform-ptqf.onrender.com/docs |
| Health check | https://document-intelligence-platform-ptqf.onrender.com/api/v1/health |
| Public GitHub repository | https://github.com/ishika2020/document-intelligence-platform |

> Deployed on Render's free tier — the first request after 15 minutes of inactivity takes ~30-50s (cold start) while the instance spins back up.

> The frontend and backend are the **same deployed service** (see Architecture below), so there is one URL for both.

---

## 2. Solution Overview & Architecture

```
Browser (Dashboard + Document Detail pages, plain HTML/CSS/JS)
        │  fetch() → REST/JSON
        ▼
FastAPI application  (/api/v1)
        │
        ├─ 1. Document Validation      — file-type sniffing (magic bytes, not trusted
        │                                 extension), integrity check, ≤3-page limit
        ├─ 2. Text Extraction / OCR    — PyMuPDF for native PDF text; for scanned PDF
        │                                 pages and JPG/PNG images, render/extract the
        │                                 page image and run Tesseract OCR
        ├─ 3. AI-based Field & Table
        │      Extraction              — deterministic rule-based/NLP engine (regex +
        │                                 keyword matching + a positional label/value
        │                                 table parser) — see "Why no LLM?" below
        ├─ 4. Financial Validation     — per-document-type formulas from the spec,
        │                                 tolerance-based PASS / FAIL / NOT_APPLICABLE
        ├─ 5. Confidence & Evidence    — confidence derived from the OCR engine's own
        │                                 per-word confidence (never an invented number);
        │                                 every value carries source_text + page_number
        ▼
Repository layer → SQLite database (processed_documents)
        ▼
Structured JSON response ⇄ stored result ⇄ dashboard
```

See [`docs/architecture.png`](docs/architecture.png) for the diagram.

### Why no LLM? (AI-based extraction approach)

The case study permits either approach ("Any LLM/model available to the participant can be used... Free/local only is also fine"). This submission deliberately uses a **free, fully local, rule-based/NLP extraction engine** instead of a hosted LLM:

- **Zero cost / zero external dependency** — nothing to meter, no API key to leak, no rate limit that could fail during evaluation, works fully offline.
- **Deterministic & explainable** — the same document always produces the same output; every value's confidence is derived directly from the OCR engine's own per-word confidence score, never an arbitrary LLM-generated number (the spec explicitly asks for this if confidence is implemented).
- **Well suited to this document scope** — the three financial statements in the sample dataset share one consistent tabular layout (label / schedule / current-period value / comparative-period value), which a positional table parser handles very reliably; invoices are handled with keyword + regex extraction tuned to common invoice/receipt layouts.
- **Trade-off, honestly stated**: a general-purpose LLM would generalize better to layouts never seen before. See "Known Limitations" below.

### Extraction engine, concretely

1. `document_validation_service.py` — sniffs real file type from magic bytes (PDF/JPEG/PNG), checks integrity, enforces the 3-page limit.
2. `ocr_service.py` — unifies native PDF text (PyMuPDF `get_text("words")`), scanned PDF pages (extract the embedded raster image at full fidelity, or render the page, then OCR with Tesseract), and JPG/PNG images (OCR directly) into one page/line/word structure with bounding boxes and OCR confidence per word.
3. `financial_statement_parser.py` — a shared parser for Balance Sheet / P&L / Cash Flow: groups words into visual rows by y-position, separates the label from a schedule/note reference and up to two period-value columns using number-format-aware parsing (handles thousands separators, parentheses-as-negative, and repairs a common OCR artifact where a long comma-grouped number is split across two "words"). Section headers (`CAPITAL AND LIABILITIES`, `ASSETS`, `INCOME`, …) are tracked so line items can be reconciled against the correct subtotal.
4. `extraction_service.py` — dispatches per `document_type`:
   - **Invoice**: regex/keyword extraction for header fields (invoice number, date, vendor/customer via a two-column "Seller:/Client:" split or first-line heuristics, currency, subtotal/tax/discount/total, cash/change) plus a line-item table parser.
   - **Balance Sheet / P&L / Cash Flow**: keyword-mapped lookups over the parsed table (e.g. `total` inside the `ASSETS` section → `total_assets`) plus the *complete* list of parsed line items (both periods) returned verbatim for full "every visible line item" coverage.
5. `financial_validation_service.py` — runs the spec's formulas (§4.4) per document type and, for the statements, per reporting period.

---

## 3. Technology Stack

| Concern | Choice | Why |
|---|---|---|
| API framework | **FastAPI** | async, automatic OpenAPI/Swagger docs at `/docs`, first-class Pydantic validation |
| PDF parsing / rasterizing | **PyMuPDF (fitz)** | reads native text with word bounding boxes *and* rasterizes scanned pages/embedded images without a separate Poppler dependency |
| OCR | **Tesseract** (via `pytesseract`) | free, open-source, runs fully offline, per-word confidence output |
| Image handling | **Pillow** | image validation/decoding |
| Data validation / schemas | **Pydantic v2** | response/request schema enforcement |
| Persistence | **SQLAlchemy + SQLite** | zero-config file database; `DATABASE_URL` can be swapped for Postgres/MySQL with no code changes |
| Frontend | **Plain HTML/CSS/JS**, served by FastAPI via Jinja2 shells | satisfies "HTML/CSS, JS where required" without a separate Node/React build |
| Testing | **pytest** + FastAPI `TestClient` | no separate server needed for API tests |
| Deployment | **Docker** (works on Render / Railway / Koyeb) | one Dockerfile, one process serving both API and frontend |

---

## 4. Local Setup

### Prerequisites
- Python 3.11+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed locally (Windows: `winget install UB-Mannheim.TesseractOCR`; macOS: `brew install tesseract`; Linux: `apt-get install tesseract-ocr`)

### Steps
```bash
git clone <repo-url>
cd Document_Intelligence

python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash; use .venv\Scripts\activate on cmd, or source .venv/bin/activate on Linux/Mac

pip install -r backend/requirements-dev.txt

cp .env.example backend/.env
# On Windows, set TESSERACT_CMD in backend/.env if `tesseract` isn't on PATH, e.g.:
#   TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe

cd backend
uvicorn app.main:app --reload --port 8000
```

Open http://127.0.0.1:8000 for the dashboard, http://127.0.0.1:8000/docs for Swagger.

### Run tests
```bash
cd backend
pytest tests/ -v
```
27 tests covering file validation, financial-calculation validation (tolerance behaviour, PASS/FAIL/NOT_APPLICABLE), extraction accuracy against the real sample documents, and the full API flow (upload → process → retrieve → list → 404 → unsupported file → invalid document_type).

---

## 5. Environment Variables

See [`.env.example`](.env.example). None are secret — there is no external API key in this project.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/document_intelligence.db` | SQLAlchemy connection string. Swap for `postgresql://...` to use a managed Postgres with zero code changes. |
| `UPLOAD_DIR` | `./data/uploads` | scratch directory (created automatically) |
| `MAX_PAGES` | `3` | page-count validation limit |
| `MAX_FILE_SIZE_MB` | `15` | upload size guard |
| `TESSERACT_CMD` | *(empty → use PATH)* | explicit path to the Tesseract binary (mainly needed on Windows) |
| `VALIDATION_TOLERANCE_ABS` / `VALIDATION_TOLERANCE_PCT` | `1.0` / `0.01` | see §8 |
| `LOG_LEVEL` | `INFO` | app-wide log level |
| `CORS_ALLOW_ORIGINS` | `["*"]` | CORS allow-list |

---

## 6. API Reference

Full interactive docs at `/docs`. Summary:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/documents/process` | Upload + process a PDF/JPG/PNG |
| `GET` | `/api/v1/documents/{document_name}` | Latest structured result for a document name |
| `GET` | `/api/v1/documents` | List processed documents (latest per name) for the dashboard |
| `GET` | `/api/v1/health` | Health check |

### `POST /api/v1/documents/process`
```bash
curl -X POST "$API_BASE/api/v1/documents/process" \
  -F "file=@sample_documents/balance_sheet_2020.pdf;type=application/pdf" \
  -F "document_type=balance_sheet"
```
`document_type` is one of `invoice | balance_sheet | profit_and_loss | cash_flow_statement`.

Response: the full structured JSON described in §5.2 of the case study spec — `document_name`, `document_type`, `processing_status`, `overall_confidence`, `file_validation`, `extracted_data`, `validation`, `processing_metadata`. See [`sample_outputs/`](sample_outputs/) for real examples of every scenario.

**Processing status vs. validation status** — a deliberate design choice: `processing_status` is `FAILED` only when the *pipeline itself* couldn't run (unsupported/corrupted/empty file, page-limit exceeded, OCR engine unavailable). A document that was successfully extracted but where a financial check doesn't reconcile is still `processing_status: "PASS"`, with the mismatch surfaced in `validation.overall_status: "FAIL"` and `validation.issues[]` — this is far more useful for a reviewer than lumping "couldn't process this file at all" together with "processed fine, but the numbers don't add up."

### `GET /api/v1/documents/{document_name}`
```bash
curl "$API_BASE/api/v1/documents/balance_sheet_2020.pdf"
```
Returns the latest stored result for that name, or `404 {"error": {"code": "DOCUMENT_NOT_FOUND", ...}}`.

### `GET /api/v1/documents`
```bash
curl "$API_BASE/api/v1/documents"
```
Returns `{"total": N, "documents": [{id, document_name, document_type, processing_status, overall_confidence, created_at}, ...]}`, newest first, one row per distinct `document_name` (its latest processing result) — this is what powers the dashboard table.

### Error response shape
```json
{ "error": { "code": "UNSUPPORTED_FILE_TYPE", "message": "Only PDF, JPG and PNG documents are supported." } }
```

---

## 7. Frontend

Two pages, plain HTML/CSS + vanilla JS (no build step), served by FastAPI and talking to the REST API purely via `fetch()`:

- **`/`** — Dashboard: document-type selector, file upload, processed-documents table (name, type, status badge, confidence, processed time), clicking a row opens the detail page.
- **`/documents/{document_name}`** — Detail page with tabs: *Extracted Data* (key/value cards + line-item tables, missing fields highlighted red, low-confidence fields highlighted amber, each value shows its evidence source text + page), *Financial Validation* (every check with formula, inputs, calculated vs. reported value, variance, PASS/FAIL/NOT_APPLICABLE), *File Validation*, and *Raw JSON* (the exact API response, for evaluators who want to inspect the contract directly).

---

## 8. Financial Validation Rules & Tolerance

Implemented exactly per case study §4.4, per document type. A check is `NOT_APPLICABLE` (never a forced `FAIL`) whenever a required field wasn't found in the document — no value is ever assumed or invented to force a check to run.

**Tolerance**: a check passes if `|calculated − reported| ≤ max(VALIDATION_TOLERANCE_ABS, VALIDATION_TOLERANCE_PCT × |reported|)` — i.e. the larger of a flat ±1.0 (currency units) or ±1% of the reported value. The relative component matters a lot at bank-statement scale (₹ in '000s, values in the billions) where OCR can occasionally misread a single digit; the flat component matters for small invoice amounts.

- **Invoice**: `quantity × unit_price ≈ line total` per row; `sum(line items) ≈ subtotal` (or `≈ total` when the template shows GST-inclusive totals only); `subtotal + tax − discount ≈ total`; `cash_paid − total ≈ change`.
- **Balance Sheet**: `Total Capital & Liabilities ≈ Total Assets`; sum of capital & liability line items ≈ reported Capital & Liabilities total; sum of asset line items ≈ reported Assets total. Run independently for each reporting period present.
- **Profit & Loss**: `Interest Earned + Other Income ≈ Total Income`; `Interest Expended + Operating Expenses + Provisions & Contingencies ≈ Total Expenditure`; `Total Income − Total Expenditure ≈ Net Profit before Minority Interest`; `Profit before Minority Interest − Minority Interest ≈ Consolidated Net Profit`; `Current Profit + Brought Forward Profit ≈ Total Available for Appropriation`. Per period.
- **Cash Flow Statement**: `Operating + Investing + Financing Cash Flow + FX/Translation Adjustment ≈ Net Increase in Cash`; `Opening Cash + Net Increase + Cash Acquired on Amalgamation ≈ Closing Cash`. Parentheses are treated as negative values. Per period.

---

## 9. Confidence Scoring

Optional per the spec, implemented anyway because it's cheap and meaningful here: every extracted field's `confidence` is the OCR engine's own per-character/word confidence (0–100, from Tesseract) for the specific token(s) that produced the value, normalized to 0–1 — never a number invented by the extraction logic. Native-PDF text (no OCR involved) is treated as confidence 0.99. `overall_confidence` on the top-level response is the mean of every field-level confidence found in `extracted_data`. The frontend highlights any field below 70% confidence.

---

## 10. Database / Persistence

SQLite via SQLAlchemy (`backend/app/models/document.py`, one `processed_documents` table storing the full structured result — `file_validation`, `extracted_data`, `validation`, `processing_metadata` as JSON columns, plus `document_name`, `document_type`, `processing_status`, `overall_confidence`, `created_at`). Every processing run inserts a new row (history is kept); `GET /documents/{name}` returns the most recent row for that name; `GET /documents` returns the latest row per distinct name for the dashboard. Swapping to Postgres/MySQL is a one-line `DATABASE_URL` change — no other code changes needed, since access goes through `app/repositories/document_repository.py` only.

---

## 11. Sample Outputs

[`sample_outputs/`](sample_outputs/) contains real JSON results (produced by this codebase, not hand-written) covering:
- `balance_sheet_pass.json`, `cash_flow_statement_pass.json`, `invoice_pass.json` — clean PASS scenarios across three document types.
- `profit_and_loss_validation_fail.json` — a genuine validation-failure scenario: the OCR read the reported "Total Expenditure" digit incorrectly (`4,197,720,010` instead of `1,197,720,010` — a single-glyph misread on this specific scan), so the calculated vs. reported check correctly reports `FAIL` with the variance shown. Left as-is deliberately (not hand-corrected) to demonstrate the validation engine actually catching a real mismatch rather than always agreeing with the source.
- `invoice_low_quality_missing_fields.json` — a heavily stamped/overlaid receipt where several fields (date, vendor name) come back `null` with low-confidence neighbours rather than a hallucinated guess.
- `unsupported_file_failed.json` — a rejected `.txt` upload, `processing_status: "FAILED"`.

---

## 12. Testing

- `backend/tests/test_validation.py` — file validation (empty/corrupted/unsupported/oversized/valid, magic-byte sniffing independent of declared content-type) and financial validation (tolerance edges, NOT_APPLICABLE behaviour, invoice checks).
- `backend/tests/test_extraction.py` — extraction accuracy against the real sample documents (asserts specific extracted values match the source PDFs/images).
- `backend/tests/test_api.py` — full API flow: health, process (PASS), get-by-name, list, 404, unsupported file (graceful FAILED, not a crash), invalid `document_type` (422), re-processing the same name returns the latest result.

27/27 passing (`pytest tests/ -v`).

---

## 13. AI/Tool Usage Declaration

This solution was built with **Claude (Anthropic)** as an AI coding assistant inside Claude Code, used for: designing the service/module structure, writing the OCR/parsing/extraction/validation logic, debugging OCR-quality issues against the real sample documents (iteratively, by inspecting actual Tesseract output rather than guessing), writing the frontend, tests, this README, and deployment configuration. All logic was verified by actually running it against the provided sample dataset — nothing here is unverified boilerplate.

---

## 14. Known Limitations

- **Rule-based extraction, not an LLM**: layouts meaningfully different from the ones in the sample dataset (e.g. an invoice template with no "Seller:/Client:" columns and no summary "Total $x $y $z" row) will extract less completely. The three financial-statement types are tuned specifically to the bank-annual-report table layout in the provided dataset (label / schedule / current period / comparative period) — a differently-structured balance sheet (e.g. IFRS format with different section names) would need its keyword lists extended.
- **OCR is not perfect**: on low-resolution scans, Tesseract occasionally misreads a single digit in a long number (see `profit_and_loss_validation_fail.json` above) or drops a value entirely on very noisy images (stamps/handwriting overlays, see the low-quality receipt sample). Evidence (`source_text`) is always included so a human can verify every value against the original quickly.
- **Line-item table extraction on invoices** is heuristic (position/regex-based) and works best on clearly tabular layouts; free-form receipts with unusual column orders may under-extract line items (header/summary fields are unaffected).
- **SQLite on the deployed free tier**: unless a persistent disk is attached, data resets on redeploy/restart (not on every request — it persists for the life of the running container). Fine for a single evaluation session; see below for the production fix.
- **Synchronous processing**: fine for ≤3-page documents; a genuinely large-scale system would need a queue.
- **No authentication**: the API is open, as the spec's evaluation flow expects.

## 15. What I'd Change for Production

- Swap `DATABASE_URL` to a managed Postgres (already supported with zero code changes) and attach persistent storage for uploaded originals.
- Add an LLM-based extraction fallback for documents the rule-based parser has low confidence on, keeping the deterministic path as the fast/free default.
- Move OCR + extraction to a background worker/queue (e.g. Celery/RQ) with the API returning a job id immediately, for larger documents.
- Add authentication/rate limiting on the upload endpoint, and virus/malware scanning on uploaded files.
- Structured logging shipped to an observability backend; add request tracing IDs end-to-end.
- Expand the financial-statement keyword mappings to cover non-bank layouts (retail, manufacturing P&Ls, IFRS-style balance sheets).

---

## 16. Repository Structure

```
project-root/
├── backend/            # FastAPI app, services, models, schemas, tests
├── frontend/            # HTML/CSS/JS dashboard + document detail pages
├── docs/                 # architecture diagram, solution presentation
├── sample_documents/      # representative inputs used for dev/testing/demo
├── sample_outputs/         # real JSON outputs for every scenario (see §11)
├── Dockerfile
├── .env.example
└── README.md              # this file
```
