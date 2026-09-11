"""Text extraction / OCR service.

Produces a unified page/line/word structure regardless of source:
  - native PDF text layer (fast, exact) via PyMuPDF
  - scanned PDF pages (rendered to an image, then OCR'd) via PyMuPDF + Tesseract
  - JPG/PNG images via Tesseract

Downstream extraction services consume `PageContent.lines`, each of which
carries word-level bounding boxes so the financial-statement parser can
tell apart label text from numeric columns by horizontal position.
"""
import io
import re
from dataclasses import dataclass, field

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from app.core.config import get_settings
from app.core.logging import get_logger
from app.utils.exceptions import OCRProcessingError

logger = get_logger(__name__)

_settings = get_settings()
if _settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = _settings.tesseract_cmd

_OCR_RENDER_ZOOM = 1.6  # render scanned pages at this zoom for OCR accuracy
_MAX_OCR_DIMENSION = 3000  # soft safety net against pathologically huge uploads; normal scans are well under this


def _cap_image_size(image: Image.Image) -> Image.Image:
    """Downscale an image before OCR if it's larger than needed -- OCR accuracy
    plateaus well below this size, and Tesseract's memory use scales with pixel
    count, which matters on memory-constrained deployment tiers (e.g. 512MB)."""
    longer_side = max(image.size)
    if longer_side <= _MAX_OCR_DIMENSION:
        return image
    scale = _MAX_OCR_DIMENSION / longer_side
    new_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(new_size, Image.LANCZOS)


@dataclass
class Word:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 99.0  # OCR engine confidence 0-100; 99 for exact native PDF text


@dataclass
class Line:
    text: str
    words: list[Word] = field(default_factory=list)
    y: float = 0.0


@dataclass
class PageContent:
    page_number: int
    text: str
    lines: list[Line]
    source: str  # "native" | "ocr"


@dataclass
class DocumentContent:
    pages: list[PageContent]
    ocr_used: bool

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)


_NUMBER_CONTINUATION_RE = re.compile(r"^,\d{2,3}(,\d{3})*\)?\]?%?$")


def _merge_split_number_tokens(words: list[Word]) -> list[Word]:
    """Repair a common OCR artifact where a large comma-grouped number (e.g.
    "1,531,279,982") is mis-split into two word tokens ("1,531" + ",279,982")
    because of a faint gap in the source scan. Any token that starts with a
    stray leading comma almost certainly belongs glued to the previous token."""
    merged: list[Word] = []
    for w in words:
        if merged and _NUMBER_CONTINUATION_RE.match(w.text) and re.search(r"\d", merged[-1].text):
            prev = merged[-1]
            merged[-1] = Word(
                text=prev.text + w.text,
                x0=prev.x0,
                y0=prev.y0,
                x1=w.x1,
                y1=max(prev.y1, w.y1),
                conf=min(prev.conf, w.conf),
            )
        else:
            merged.append(w)
    return merged


def _group_words_into_lines(words: list[Word], y_tolerance: float = 4.0) -> list[Line]:
    if not words:
        return []
    # Sort purely by vertical position first so words belonging to one visual
    # row stay adjacent even when their y-tops jitter by a few pixels (common
    # in OCR output where digits/letters have slightly different baselines).
    words_sorted = sorted(words, key=lambda w: w.y0)
    lines: list[Line] = []
    current: list[Word] = [words_sorted[0]]
    cluster_y_sum = words_sorted[0].y0
    cluster_y_avg = words_sorted[0].y0

    for w in words_sorted[1:]:
        if abs(w.y0 - cluster_y_avg) <= y_tolerance:
            current.append(w)
            cluster_y_sum += w.y0
            cluster_y_avg = cluster_y_sum / len(current)
        else:
            current.sort(key=lambda ww: ww.x0)
            current = _merge_split_number_tokens(current)
            lines.append(Line(text=" ".join(ww.text for ww in current), words=current, y=cluster_y_avg))
            current = [w]
            cluster_y_sum = w.y0
            cluster_y_avg = w.y0
    current.sort(key=lambda ww: ww.x0)
    current = _merge_split_number_tokens(current)
    lines.append(Line(text=" ".join(ww.text for ww in current), words=current, y=cluster_y_avg))
    return lines


def _extract_native_pdf_page(page: "fitz.Page") -> PageContent | None:
    raw_words = page.get_text("words")  # (x0, y0, x1, y1, word, block_no, line_no, word_no)
    if not raw_words:
        return None
    words = [Word(text=w[4], x0=w[0], y0=w[1], x1=w[2], y1=w[3]) for w in raw_words]
    char_count = sum(len(w.text) for w in words)
    if char_count < _settings.ocr_min_native_chars_per_page:
        return None  # too little text -> treat page as scanned/image-based
    lines = _group_words_into_lines(words)
    text = "\n".join(line.text for line in lines)
    return PageContent(page_number=page.number + 1, text=text, lines=lines, source="native")


def _ocr_image(image: Image.Image, page_number: int) -> PageContent:
    image = _cap_image_size(image)
    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRProcessingError(
            "OCR engine (Tesseract) is not available on the server.", code="OCR_ENGINE_UNAVAILABLE"
        ) from exc

    words: list[Word] = []
    n = len(data["text"])
    for i in range(n):
        raw_text = data["text"][i].strip()
        if not raw_text or re.fullmatch(r"[|_~`•\-=]+", raw_text):
            continue  # drop pure table-border / underline OCR noise tokens
        conf_raw = data.get("conf", ["-1"] * n)[i]
        try:
            word_conf = float(conf_raw)
        except (ValueError, TypeError):
            word_conf = -1.0
        if word_conf < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(
            Word(text=raw_text, x0=float(x), y0=float(y), x1=float(x + w), y1=float(y + h), conf=word_conf)
        )

    lines = _group_words_into_lines(words, y_tolerance=11.0)
    text = "\n".join(line.text for line in lines)
    return PageContent(page_number=page_number, text=text, lines=lines, source="ocr")


def extract_document_content(data: bytes, file_type: str) -> DocumentContent:
    """Run text extraction / OCR across all pages of a validated PDF/JPG/PNG file."""
    if file_type == "application/pdf":
        return _extract_pdf(data)
    return _extract_image(data)


def _render_page_for_ocr(page: "fitz.Page") -> Image.Image:
    """Prefer the original embedded raster image for a scanned page (best
    fidelity, no double-resampling); fall back to rendering the page to a
    pixmap when it isn't a single clean full-page image."""
    images = page.get_images(full=True)
    if len(images) == 1:
        try:
            xref = images[0][0]
            extracted = page.parent.extract_image(xref)
            image = Image.open(io.BytesIO(extracted["image"]))
            if image.width >= 600 and image.height >= 600:
                return image.convert("RGB") if image.mode != "RGB" else image
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falling back to pixmap render for page %d: %s", page.number + 1, exc)

    pix = page.get_pixmap(matrix=fitz.Matrix(_OCR_RENDER_ZOOM, _OCR_RENDER_ZOOM))
    return Image.open(io.BytesIO(pix.tobytes("png")))


def _extract_pdf(data: bytes) -> DocumentContent:
    pages: list[PageContent] = []
    ocr_used = False
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise OCRProcessingError(f"Unable to open PDF for text extraction: {exc}") from exc

    try:
        for page in doc:
            native = _extract_native_pdf_page(page)
            if native is not None:
                pages.append(native)
                continue

            logger.info("Page %d has no usable native text layer -> falling back to OCR", page.number + 1)
            image = _render_page_for_ocr(page)
            pages.append(_ocr_image(image, page.number + 1))
            ocr_used = True
    finally:
        doc.close()

    return DocumentContent(pages=pages, ocr_used=ocr_used)


def _extract_image(data: bytes) -> DocumentContent:
    image = Image.open(io.BytesIO(data))
    if image.mode != "RGB":
        image = image.convert("RGB")
    page = _ocr_image(image, page_number=1)
    return DocumentContent(pages=[page], ocr_used=True)
