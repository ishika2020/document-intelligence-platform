"""Generic label/value table parser shared by the balance sheet, profit & loss
and cash-flow-statement extractors.

These bank-style financial statements share one layout: a label column,
an optional small schedule/note-reference column, and one numeric column
per reporting period (current period, comparative period). This module
turns OCR'd/native lines into structured LineItem rows using word x-position
so numeric columns are not confused with label text or schedule references,
then exposes small keyword-matching helpers so each document-type extractor
can map rows onto the field names required by the spec without duplicating
this parsing logic.
"""
import re
from dataclasses import dataclass, field

from app.services.ocr_service import DocumentContent
from app.utils.date_parsing import extract_first_date
from app.utils.number_parsing import find_numeric_tokens, looks_like_schedule_ref, parse_amount

_PERIOD_DATE_RE = re.compile(
    r"\b\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}\b"
    r"|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},?\s+\d{4}\b"
)
_CURRENCY_UNIT_RE = re.compile(
    r"(₹|Rs\.?|INR|USD|\$|EUR|€|GBP|£)\s*in\s*'?(000|Lakh[s]?|Crore[s]?|Million[s]?|Thousand[s]?)'?",
    re.IGNORECASE,
)
_SYMBOL_TO_CURRENCY = {"₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR", "$": "USD", "usd": "USD",
                        "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP"}


@dataclass
class LineItem:
    label: str
    schedule: str | None
    values: list[float]
    page_number: int
    source_text: str
    is_header: bool = False
    section: str | None = None
    value_confidences: list[float] = field(default_factory=list)  # 0-1, aligned with `values`


@dataclass
class FinancialStatement:
    title: str | None
    currency: str | None
    currency_unit_note: str | None
    period_labels: list[str]
    line_items: list[LineItem] = field(default_factory=list)


def _detect_currency(full_text: str) -> tuple[str | None, str | None]:
    m = _CURRENCY_UNIT_RE.search(full_text)
    if m:
        symbol = m.group(1).lower()
        currency = _SYMBOL_TO_CURRENCY.get(symbol, m.group(1))
        return currency, f"in '{m.group(2)}"
    for sym, code in _SYMBOL_TO_CURRENCY.items():
        if sym in full_text.lower():
            return code, None
    return None, None


def _detect_period_labels(full_text: str) -> list[str]:
    matches = _PERIOD_DATE_RE.findall(full_text)
    seen_normalized: set[str] = set()
    result: list[str] = []
    for m in matches:
        # Dedupe by normalised calendar date, not raw string, so "March 31, 2020"
        # and "31-Mar-20" (the same date in two formats/places) count once.
        key = extract_first_date(m) or m
        if key in seen_normalized:
            continue
        seen_normalized.add(key)
        result.append(m)
    return result[:4]


def _detect_title(lines_page1: list[str], keywords: list[str]) -> str | None:
    for line in lines_page1:
        lower = line.lower()
        if any(kw in lower for kw in keywords):
            return line.strip()
    return lines_page1[0].strip() if lines_page1 else None


_SECTION_HEADER_HINTS = (
    "capital and liabilities", "assets", "income", "expenditure", "profit",
    "appropriations", "operating activities", "investing activities",
    "financing activities",
)


def parse_financial_statement(
    content: DocumentContent, title_keywords: list[str]
) -> FinancialStatement:
    full_text = content.full_text
    currency, currency_unit_note = _detect_currency(full_text)
    page1_lines = [ln.text for ln in content.pages[0].lines] if content.pages else []
    # Restrict period-date detection to the document header (first ~15 lines)
    # so signature-block dates ("Mumbai, April 18, 2020") further down the
    # page are never mistaken for a comparative reporting period.
    header_text = "\n".join(page1_lines[:15])
    period_labels = _detect_period_labels(header_text)
    title = _detect_title(page1_lines, title_keywords)

    line_items: list[LineItem] = []
    current_section: str | None = None

    for page in content.pages:
        for line in page.lines:
            tokens = [w.text for w in line.words]
            if not tokens:
                continue

            i = len(tokens) - 1
            trailing_numeric: list[str] = []
            trailing_confs: list[float] = []
            while i >= 0 and parse_amount(tokens[i]) is not None and re.search(r"\d", tokens[i]):
                trailing_numeric.insert(0, tokens[i])
                trailing_confs.insert(0, line.words[i].conf)
                i -= 1

            schedule = None
            if len(trailing_numeric) >= 3 and looks_like_schedule_ref(trailing_numeric[0]):
                # A plain-digit schedule ref (e.g. "1", "13") has no comma, so the
                # while-loop above swept it up as if it were a value column too.
                schedule = trailing_numeric.pop(0)
                trailing_confs.pop(0)
            elif i >= 0 and trailing_numeric and looks_like_schedule_ref(tokens[i]) and i > 0:
                # A schedule ref containing a letter (e.g. "2A") stopped the
                # numeric run on its own, so it's still sitting in `tokens[i]`.
                schedule = tokens[i]
                i -= 1

            label_tokens = tokens[: i + 1] if trailing_numeric or schedule else tokens

            label = " ".join(label_tokens).strip(" :")
            if not label:
                continue

            values: list[float] = []
            value_confidences: list[float] = []
            for t, c in zip(trailing_numeric, trailing_confs, strict=True):
                v = parse_amount(t)
                if v is not None:
                    values.append(v)
                    value_confidences.append(round(max(0.0, min(c, 99.0)) / 100.0, 2))
            is_header = len(values) == 0

            if is_header:
                lower_label = label.lower()
                if any(hint in lower_label for hint in _SECTION_HEADER_HINTS):
                    current_section = lower_label

            line_items.append(
                LineItem(
                    label=label,
                    schedule=schedule,
                    values=values,
                    page_number=page.page_number,
                    source_text=line.text,
                    is_header=is_header,
                    section=current_section,
                    value_confidences=value_confidences,
                )
            )

    return FinancialStatement(
        title=title,
        currency=currency,
        currency_unit_note=currency_unit_note,
        period_labels=period_labels,
        line_items=line_items,
    )


def find_line(
    statement: FinancialStatement,
    label_keywords: list[str],
    section_keywords: list[str] | None = None,
) -> LineItem | None:
    """Return the first non-header line item whose label contains all `label_keywords`
    (case-insensitive), optionally restricted to a section whose header matched any
    of `section_keywords`."""
    for item in statement.line_items:
        if item.is_header or not item.values:
            continue
        lower_label = item.label.lower()
        if not all(kw in lower_label for kw in label_keywords):
            continue
        if section_keywords:
            if not item.section or not any(kw in item.section for kw in section_keywords):
                continue
        return item
    return None


def find_lines_in_section(statement: FinancialStatement, section_keywords: list[str]) -> list[LineItem]:
    """All non-header line items belonging to a section whose header matched any of
    `section_keywords`, up to (excluding) that section's own "Total" row. Items
    appearing after the Total (e.g. off-balance-sheet disclosures that share the
    same section tag) are deliberately excluded so they aren't double-counted."""
    results = []
    closed_sections: set[str] = set()
    for item in statement.line_items:
        if not item.section or not any(kw in item.section for kw in section_keywords):
            continue
        if item.section in closed_sections:
            continue
        if item.label.strip().lower() == "total":
            closed_sections.add(item.section)
            continue
        if item.is_header or not item.values:
            continue
        results.append(item)
    return results


def line_to_field(item: LineItem | None, period_index: int = 0) -> dict | None:
    if item is None:
        return None
    if period_index >= len(item.values):
        return None
    field = {
        "value": item.values[period_index],
        "page_number": item.page_number,
        "evidence": {"source_text": item.source_text, "page_number": item.page_number},
    }
    if period_index < len(item.value_confidences):
        field["confidence"] = item.value_confidences[period_index]
    return field
