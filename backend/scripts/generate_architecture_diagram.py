"""One-off dev script to (re)generate docs/architecture.png. Not part of the
runtime application -- run manually: python scripts/generate_architecture_diagram.py"""
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

fig, ax = plt.subplots(figsize=(11, 11.6))
ax.set_xlim(0, 11)
ax.set_ylim(3.3, 15.5)
ax.axis("off")

COLORS = {
    "frontend": "#2054c9",
    "api": "#0d8a4f",
    "service": "#b3730a",
    "data": "#6a3fb5",
    "text": "#1a2233",
}


def box(x, y, w, h, text, color, fontsize=10.5, fontweight="bold", textcolor="white"):
    rect = mpatches.FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.06,rounding_size=0.12",
        linewidth=0, facecolor=color, alpha=0.95, zorder=2,
    )
    ax.add_patch(rect)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fontsize,
            fontweight=fontweight, color=textcolor, zorder=3, wrap=True)
    return (x + w / 2, y), (x + w / 2, y + h)


def arrow(p1, p2, color="#333"):
    a = FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=16, color=color, linewidth=1.6, zorder=1)
    ax.add_patch(a)


ax.text(5.5, 15.15, "Document Intelligence Platform — Architecture", ha="center", fontsize=15, fontweight="bold", color=COLORS["text"])

# Frontend
top1, bot1 = box(2.5, 13.5, 6, 1.1, "Browser Frontend\nDashboard + Document Detail (HTML/CSS/JS)", COLORS["frontend"])

arrow((5.5, 13.5), (5.5, 13.0))
ax.text(5.9, 13.2, "fetch() JSON over HTTPS", fontsize=8.5, color="#555")

# API layer
top2, bot2 = box(2, 11.9, 7, 1.0, "FastAPI REST API  (/api/v1)\nPOST /process · GET /documents · GET /{name} · GET /health", COLORS["api"], fontsize=8.7)

arrow((5.5, 11.9), (5.5, 11.4))

# Pipeline stages
pipeline_steps = [
    "1. Document Validation\n(file-type sniff, integrity, page-limit ≤3)",
    "2. Text Extraction / OCR\n(PyMuPDF native text + Tesseract for scanned pages/images)",
    "3. AI-based Field & Table Extraction\n(rule-based NLP: regex/keyword + positional table parser)",
    "4. Financial Calculation Validation\n(per-document formulas, tolerance-based PASS/FAIL/NOT_APPLICABLE)",
    "5. Confidence & Evidence\n(derived from OCR word confidence, source-text + page grounding)",
]
y = 10.5
step_positions = []
for step in pipeline_steps:
    t, b = box(1.7, y, 7.6, 0.85, step, COLORS["service"], fontsize=9)
    step_positions.append((t, b))
    y -= 1.05

for i in range(len(step_positions) - 1):
    arrow(step_positions[i][0], step_positions[i + 1][1])

arrow(step_positions[-1][0], (5.5, y + 0.85))

# Persistence
top_db, bot_db = box(2, y - 0.35, 7, 0.85, "Repository Layer → SQLite Database\n(processed_documents table)", COLORS["data"], fontsize=9.5)

# Side notes: document types
ax.text(9.4, 10.9, "Document Types", fontsize=9.5, fontweight="bold", color=COLORS["text"])
for i, t in enumerate(["Invoice", "Balance Sheet", "Profit & Loss", "Cash Flow Stmt"]):
    ax.text(9.4, 10.55 - i * 0.32, f"• {t}", fontsize=8.5, color="#444")

ax.text(9.4, 8.9, "Inputs", fontsize=9.5, fontweight="bold", color=COLORS["text"])
for i, t in enumerate(["PDF (native)", "PDF (scanned)", "JPG / PNG"]):
    ax.text(9.4, 8.55 - i * 0.32, f"• {t}", fontsize=8.5, color="#444")

# Bottom: response
arrow((5.5, y - 0.35), (5.5, y - 0.75))
box(1.7, y - 1.55, 7.6, 0.8, "Structured JSON Response\nname · status · extracted_data · validation · metadata", "#333f55", fontsize=9.5)

fig.savefig("../docs/architecture.png", dpi=170, bbox_inches="tight", facecolor="white")
print("Saved docs/architecture.png")
