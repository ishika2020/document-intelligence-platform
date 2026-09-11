"""One-off dev script to (re)generate docs/solution_presentation.pdf -- a
landscape slide deck. Not part of the runtime application."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = landscape(letter)
NAVY = colors.HexColor("#163a8f")
BLUE = colors.HexColor("#2054c9")
DARK = colors.HexColor("#1a2233")
MUTED = colors.HexColor("#667085")
GREEN = colors.HexColor("#0d8a4f")
AMBER = colors.HexColor("#b3730a")
BG = colors.HexColor("#f4f6f9")

c = canvas.Canvas("../docs/solution_presentation.pdf", pagesize=landscape(letter))


def background():
    c.setFillColor(colors.white)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)


def header_bar(title, subtitle=None):
    c.setFillColor(NAVY)
    c.rect(0, PAGE_H - 1.15 * inch, PAGE_W, 1.15 * inch, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(0.6 * inch, PAGE_H - 0.72 * inch, title)
    if subtitle:
        c.setFont("Helvetica", 11)
        c.setFillColor(colors.HexColor("#cfe0ff"))
        c.drawString(0.6 * inch, PAGE_H - 0.98 * inch, subtitle)


def footer(page_num):
    c.setFont("Helvetica", 8.5)
    c.setFillColor(MUTED)
    c.drawString(0.6 * inch, 0.35 * inch, "Document Intelligence Platform — AI Engineer Internship Case Study")
    c.drawRightString(PAGE_W - 0.6 * inch, 0.35 * inch, str(page_num))


def bullets(items, x, y, width, size=13, leading=22, color=DARK, bullet_color=BLUE):
    c.setFont("Helvetica", size)
    for item in items:
        c.setFillColor(bullet_color)
        c.circle(x + 0.06 * inch, y + 0.09 * inch, 2, fill=1, stroke=0)
        c.setFillColor(color)
        c.drawString(x + 0.22 * inch, y, item)
        y -= leading
    return y


def new_page():
    c.showPage()
    background()


page = 1

# --- Slide 1: Title ---
background()
c.setFillColor(NAVY)
c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
c.setFillColor(colors.white)
c.setFont("Helvetica-Bold", 34)
c.drawCentredString(PAGE_W / 2, PAGE_H / 2 + 0.55 * inch, "Document Intelligence Platform")
c.setFont("Helvetica", 16)
c.setFillColor(colors.HexColor("#cfe0ff"))
c.drawCentredString(PAGE_W / 2, PAGE_H / 2 + 0.05 * inch, "Intelligent Document Extraction, Validation & API Platform")
c.setFont("Helvetica", 12)
c.drawCentredString(PAGE_W / 2, PAGE_H / 2 - 0.55 * inch, "AI Engineer Internship — Technical Case Study Submission")
c.setFont("Helvetica", 10)
c.setFillColor(colors.HexColor("#9db8e8"))
c.drawCentredString(PAGE_W / 2, 0.6 * inch, "FastAPI · PyMuPDF · Tesseract OCR · Rule-based NLP Extraction · SQLite · Docker")
footer(page)
new_page()
page += 1

# --- Slide 2: Problem & Objective ---
header_bar("Problem & Objective")
y = PAGE_H - 1.7 * inch
c.setFont("Helvetica-Bold", 14)
c.setFillColor(DARK)
c.drawString(0.6 * inch, y, "The challenge")
y -= 0.35 * inch
y = bullets([
    "Financial teams receive invoices & statements as native or scanned PDF/JPG/PNG.",
    "Varying layouts, OCR noise and inconsistent line items make manual extraction slow.",
    "Need: a reusable service that extracts everything, validates the numbers, and",
    "makes results available via a dashboard + REST API.",
], 0.7 * inch, y, 8 * inch)
y -= 0.25 * inch
c.setFont("Helvetica-Bold", 14)
c.drawString(0.6 * inch, y, "What this submission delivers")
y -= 0.35 * inch
bullets([
    "Full pipeline: validate → OCR/text extract → AI-based field & table extract →",
    "financial validation → confidence/evidence → persist → dashboard + REST API.",
    "All 4 document types: Invoice, Balance Sheet, Profit & Loss, Cash Flow Statement.",
    "Deployed, documented, tested — Dockerized for one-command deployment.",
], 0.7 * inch, y, 8 * inch)
footer(page)
new_page()
page += 1

# --- Slide 3: Architecture ---
header_bar("Architecture")
try:
    c.drawImage("../docs/architecture.png", 1.6 * inch, 0.55 * inch, width=6.8 * inch,
                height=PAGE_H - 1.9 * inch, preserveAspectRatio=True, anchor="c")
except Exception:
    c.setFont("Helvetica", 12)
    c.drawString(0.6 * inch, PAGE_H / 2, "(see docs/architecture.png)")
footer(page)
new_page()
page += 1

# --- Slide 4: Why no LLM ---
header_bar("AI-Based Extraction: Why Rule-Based, Not an LLM")
y = PAGE_H - 1.7 * inch
y = bullets([
    "Zero cost, zero external dependency — no API key, no rate limit risk during evaluation,",
    "runs fully offline.",
    "Deterministic & explainable — same input always gives the same output.",
    "Confidence scores are derived from the OCR engine's real per-word confidence,",
    "never an invented number.",
    "The 3 financial statement types share one consistent tabular layout — a positional",
    "label/value table parser handles this very reliably.",
], 0.7 * inch, y, 8.5 * inch)
y -= 0.2 * inch
c.setFont("Helvetica-Oblique", 12)
c.setFillColor(AMBER)
c.drawString(0.7 * inch, y, "Trade-off, stated honestly: a hosted LLM would generalize better to unseen layouts —")
y -= 0.24 * inch
c.drawString(0.7 * inch, y, "see \"Known Limitations\" in the README.")
footer(page)
new_page()
page += 1

# --- Slide 5: Extraction pipeline detail ---
header_bar("Extraction Pipeline", "services/ package")
y = PAGE_H - 1.65 * inch
steps = [
    ("1. Document Validation", ["Magic-byte file-type sniffing (not trusted extension), integrity check, 3-page limit."]),
    ("2. OCR Service", ["PyMuPDF native text extraction; scanned pages/images OCR'd via Tesseract with", "word-level confidence."]),
    ("3. Financial Statement Parser", ["Shared positional table parser: groups words into rows, separates schedule refs", "from period-value columns, tracks section headers for reconciliation."]),
    ("4. Extraction Service", ["Per document_type: regex/keyword extraction (invoices) or keyword-mapped table", "lookups (statements) + full line-item arrays."]),
    ("5. Financial Validation Service", ["Spec formulas §4.4 per document type & period; tolerance-based", "PASS / FAIL / NOT_APPLICABLE."]),
]
for title, desc_lines in steps:
    c.setFillColor(BLUE)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(0.7 * inch, y, title)
    y -= 0.27 * inch
    c.setFont("Helvetica", 11.5)
    c.setFillColor(DARK)
    for line in desc_lines:
        c.drawString(0.95 * inch, y, line)
        y -= 0.24 * inch
    y -= 0.14 * inch
footer(page)
new_page()
page += 1

# --- Slide 6: Financial validation ---
header_bar("Financial Validation — Examples")
y = PAGE_H - 1.7 * inch
c.setFont("Helvetica-Bold", 13)
c.setFillColor(DARK)
c.drawString(0.6 * inch, y, "Balance Sheet")
y -= 0.28 * inch
c.setFont("Helvetica", 11.5)
c.drawString(0.75 * inch, y, "Total Capital & Liabilities ≈ Total Assets, independently per reporting period,")
y -= 0.22 * inch
c.drawString(0.75 * inch, y, "plus component-sum reconciliation for each side.")
y -= 0.4 * inch
c.setFont("Helvetica-Bold", 13)
c.drawString(0.6 * inch, y, "Profit & Loss")
y -= 0.28 * inch
c.setFont("Helvetica", 11.5)
c.drawString(0.75 * inch, y, "Interest Earned + Other Income ≈ Total Income · Total Income − Total Expenditure ≈")
y -= 0.22 * inch
c.drawString(0.75 * inch, y, "Net Profit before Minority Interest · Current + Brought Forward ≈ Total for Appropriation")
y -= 0.4 * inch
c.setFont("Helvetica-Bold", 13)
c.drawString(0.6 * inch, y, "Cash Flow Statement")
y -= 0.28 * inch
c.setFont("Helvetica", 11.5)
c.drawString(0.75 * inch, y, "Operating + Investing + Financing + FX ≈ Net Increase in Cash · Opening + Net Increase")
y -= 0.22 * inch
c.drawString(0.75 * inch, y, "≈ Closing Cash. Parentheses treated as negative.")
y -= 0.45 * inch
c.setFillColor(AMBER)
c.setFont("Helvetica-Oblique", 11.5)
c.drawString(0.6 * inch, y, "Tolerance: max(±1.0 absolute, ±1% relative) — a check is NOT_APPLICABLE, never FAIL,")
y -= 0.22 * inch
c.drawString(0.6 * inch, y, "when a required field wasn't found — nothing is ever assumed or invented.")
footer(page)
new_page()
page += 1

# --- Slide 7: Demo scenarios ---
header_bar("Demonstrated Scenarios", "see sample_outputs/")
y = PAGE_H - 1.7 * inch
rows = [
    ("PASS", GREEN, "balance_sheet_pass.json / cash_flow_statement_pass.json / invoice_pass.json"),
    ("VALIDATION FAIL", AMBER, "profit_and_loss_validation_fail.json — a real OCR digit-misread on \"Total"),
    ("", None, "Expenditure\" is correctly caught by the reconciliation check, left un-fixed on purpose."),
    ("MISSING FIELDS", AMBER, "invoice_low_quality_missing_fields.json — heavily stamped receipt; unreadable"),
    ("", None, "fields report null (and low confidence) rather than a guess."),
    ("UNSUPPORTED FILE", colors.HexColor("#c02b2b"), "unsupported_file_failed.json — .txt upload rejected gracefully, no crash."),
]
c.setFont("Helvetica", 12)
for label, color, desc in rows:
    if label:
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(0.7 * inch, y, label)
        c.setFont("Helvetica", 12)
    c.setFillColor(DARK)
    c.drawString(2.6 * inch, y, desc)
    y -= 0.34 * inch
footer(page)
new_page()
page += 1

# --- Slide 8: Tech stack & repo ---
header_bar("Technology Stack & Repository Structure")
y = PAGE_H - 1.7 * inch
bullets([
    "FastAPI + Pydantic v2 — API, validation, auto Swagger docs at /docs",
    "PyMuPDF — native PDF text + rasterizing scanned pages/images",
    "Tesseract (pytesseract) — free, local, offline OCR with per-word confidence",
    "SQLAlchemy + SQLite — zero-config persistence, swappable to Postgres via DATABASE_URL",
    "Plain HTML/CSS/JS frontend (Jinja2 shells) — no Node/React build step",
    "pytest — 27 automated tests (file validation, financial validation, extraction, API)",
    "Docker — one Dockerfile deploys the whole app to Render / Railway / Koyeb",
], 0.7 * inch, y, 8.5 * inch, leading=0.3 * inch)
footer(page)
new_page()
page += 1

# --- Slide 9: Limitations & production notes ---
header_bar("Known Limitations & Production Roadmap")
y = PAGE_H - 1.7 * inch
c.setFont("Helvetica-Bold", 13)
c.setFillColor(DARK)
c.drawString(0.6 * inch, y, "Known Limitations")
y -= 0.3 * inch
y = bullets([
    "Rule-based extraction is tuned to the provided dataset's layouts; very different",
    "templates need their keyword lists extended.",
    "OCR occasionally misreads a digit on low-resolution/noisy scans (evidence text lets",
    "a reviewer verify every value quickly).",
    "SQLite on a free-tier deploy resets on redeploy unless a persistent disk is attached.",
], 0.7 * inch, y, 8.5 * inch, size=12, leading=0.26 * inch)
y -= 0.25 * inch
c.setFont("Helvetica-Bold", 13)
c.setFillColor(DARK)
c.drawString(0.6 * inch, y, "For Production")
y -= 0.3 * inch
bullets([
    "Managed Postgres + persistent file storage for originals.",
    "Optional LLM fallback for low-confidence documents, on top of the free default path.",
    "Background job queue for processing, with auth + rate limiting on the API.",
], 0.7 * inch, y, 8.5 * inch, size=12, leading=0.26 * inch)
footer(page)

c.save()
print("Saved docs/solution_presentation.pdf")
