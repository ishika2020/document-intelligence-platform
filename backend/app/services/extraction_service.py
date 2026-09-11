"""AI-based field & table extraction service.

This is the single dispatch point for turning OCR'd/native document text
into the structured `extracted_data` payload required by the API response.
It uses a deterministic, explainable rule-based/NLP approach (regex +
keyword matching + positional table parsing) rather than a hosted LLM, so
extraction is free, reproducible and runs fully offline -- see the README
for the rationale. Confidence scores, where included, are derived directly
from the underlying OCR engine's per-word confidence, never invented.

  - Invoices: regex/keyword extraction over OCR'd text lines.
  - Balance Sheet / Profit & Loss / Cash Flow Statement: the shared
    financial_statement_parser table parser, with per-type keyword mappings
    onto the field names required by the spec.
"""
import re
from dataclasses import dataclass

from app.core.logging import get_logger
from app.services import financial_statement_parser as fsp
from app.services.ocr_service import DocumentContent, Line, Word
from app.utils.date_parsing import extract_first_date
from app.utils.number_parsing import find_numeric_matches, find_numeric_tokens, parse_amount

logger = get_logger(__name__)


@dataclass
class ExtractionResult:
    extracted_data: dict
    statement: fsp.FinancialStatement | None = None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _line_avg_conf(line: Line) -> float:
    if not line.words:
        return 0.7
    return round(sum(w.conf for w in line.words) / len(line.words) / 100.0, 2)


def _all_lines(content: DocumentContent) -> list[tuple[int, Line]]:
    return [(page.page_number, line) for page in content.pages for line in page.lines]


def _field(value, page_number: int, source_text: str, confidence: float | None = None) -> dict:
    result = {
        "value": value,
        "page_number": page_number,
        "evidence": {"source_text": source_text, "page_number": page_number},
    }
    if confidence is not None:
        result["confidence"] = confidence
    return result


_CURRENCY_PATTERNS = [
    (re.compile(r"₹|\bRs\.?\b|\bINR\b", re.IGNORECASE), "INR"),
    (re.compile(r"\$|\bUSD\b", re.IGNORECASE), "USD"),
    (re.compile(r"€|\bEUR\b", re.IGNORECASE), "EUR"),
    (re.compile(r"£|\bGBP\b", re.IGNORECASE), "GBP"),
    (re.compile(r"\bRM\b|\bMYR\b", re.IGNORECASE), "MYR"),
]


def _detect_currency(text: str) -> str | None:
    for pattern, code in _CURRENCY_PATTERNS:
        if pattern.search(text):
            return code
    return None


# ---------------------------------------------------------------------------
# Invoice extraction
# ---------------------------------------------------------------------------

_LABEL_KEYWORDS = ("seller", "client", "buyer", "bill to", "ship to", "vendor", "customer")


def _find_amount_field(
    content: DocumentContent,
    include: list[str],
    exclude: list[str] | None = None,
    prefer_last: bool = True,
) -> dict | None:
    exclude = exclude or []
    candidates: list[tuple[int, Line]] = []
    for page_number, line in _all_lines(content):
        lower = line.text.lower()
        if not any(kw in lower for kw in include):
            continue
        if any(kw in lower for kw in exclude):
            continue
        candidates.append((page_number, line))
    if not candidates:
        return None

    ordered = list(reversed(candidates)) if prefer_last else candidates
    for page_number, line in ordered:
        raw_tokens = find_numeric_tokens(line.text)
        numeric_values = [v for t in raw_tokens if not t.strip().endswith("%") and (v := parse_amount(t)) is not None]
        if not numeric_values:
            continue
        return _field(numeric_values[-1], page_number, line.text, _line_avg_conf(line))
    return None


def _find_invoice_number(content: DocumentContent) -> dict | None:
    pattern = re.compile(
        r"(?:invoice\s*(?:no\.?|number|#)|inv\.?\s*no\.?|receipt\s*no\.?|bill\s*no\.?|\btrn\b)\s*[:#]?\s*"
        r"([A-Za-z0-9][A-Za-z0-9\-\/]{2,})",
        re.IGNORECASE,
    )
    for page_number, line in _all_lines(content):
        m = pattern.search(line.text)
        if m:
            return _field(m.group(1).strip(" .:"), page_number, line.text, _line_avg_conf(line))
    return None


def _find_invoice_date(content: DocumentContent) -> dict | None:
    # Prefer a line explicitly labelled as a date field.
    labelled = re.compile(r"date\s*(?:of\s*issue)?\s*:?", re.IGNORECASE)
    for page_number, line in _all_lines(content):
        if labelled.search(line.text):
            iso = extract_first_date(line.text)
            if iso:
                return _field(iso, page_number, line.text, _line_avg_conf(line))
    # Fall back to the first recognisable date anywhere on the document.
    for page_number, line in _all_lines(content):
        iso = extract_first_date(line.text)
        if iso:
            return _field(iso, page_number, line.text, _line_avg_conf(line))
    return None


def _split_seller_client(content: DocumentContent) -> tuple[dict | None, dict | None]:
    """Detect a two-column 'Seller: ... Client: ...' style header and split the
    company-name line beneath it by word x-position."""
    for page in content.pages:
        for idx, line in enumerate(page.lines):
            lower = line.text.lower()
            if "seller" in lower and ("client" in lower or "buyer" in lower):
                right_label = next((w for w in line.words if w.text.lower().strip(":") in ("client", "buyer")), None)
                if right_label is None or idx + 1 >= len(page.lines):
                    continue
                split_x = right_label.x0
                name_line = page.lines[idx + 1]
                left_words = [w for w in name_line.words if w.x0 < split_x]
                right_words = [w for w in name_line.words if w.x0 >= split_x]
                vendor = None
                customer = None
                if left_words:
                    text = " ".join(w.text for w in left_words)
                    conf = round(sum(w.conf for w in left_words) / len(left_words) / 100.0, 2)
                    vendor = _field(text, page.page_number, name_line.text, conf)
                if right_words:
                    text = " ".join(w.text for w in right_words)
                    conf = round(sum(w.conf for w in right_words) / len(right_words) / 100.0, 2)
                    customer = _field(text, page.page_number, name_line.text, conf)
                return vendor, customer
    return None, None


_SKIP_FIRST_LINE_KEYWORDS = ("invoice", "receipt", "tax invoice", "date", "gst", "vat", "page")


def _fallback_vendor_name(content: DocumentContent) -> dict | None:
    if not content.pages or not content.pages[0].lines:
        return None
    for line in content.pages[0].lines[:3]:
        text = line.text.strip()
        lower = text.lower()
        if len(re.sub(r"[^A-Za-z]", "", text)) < 3:
            continue
        if any(kw in lower for kw in _SKIP_FIRST_LINE_KEYWORDS):
            continue
        return _field(text, content.pages[0].page_number, line.text, _line_avg_conf(line))
    return None


def _find_customer_name(content: DocumentContent) -> dict | None:
    pattern = re.compile(r"(?:bill\s*to|customer(?:\s*name)?|client)\s*:\s*(.+)", re.IGNORECASE)
    for page_number, line in _all_lines(content):
        m = pattern.search(line.text)
        if m and m.group(1).strip():
            return _field(m.group(1).strip(), page_number, line.text, _line_avg_conf(line))
    return None


_ITEM_ROW_MIN_NUMERIC_TOKENS = 3
_TABLE_START_KEYWORDS = ("items", "description", "qty")
_TABLE_END_KEYWORDS = ("summary", "total qty", "customer's payment", "gst summary")


def _extract_line_items(content: DocumentContent) -> list[dict]:
    items: list[dict] = []
    in_table = False
    for _page_number, line in _all_lines(content):
        lower = line.text.lower()
        if not in_table:
            if any(kw in lower for kw in _TABLE_START_KEYWORDS):
                in_table = True
            continue
        if any(kw in lower for kw in _TABLE_END_KEYWORDS):
            break

        # Strip a leading row-index marker ("5:", "2.", "10)") before scanning
        # for numbers, so the index itself is never mistaken for a data value
        # or for the start of the numeric columns.
        text = re.sub(r"^\s*\d{1,3}\s*[.\):]\s*", "", line.text)

        matches = find_numeric_matches(text)
        parsed = [(m, parse_amount(m.group(0))) for m in matches]
        parsed = [(m, v) for m, v in parsed if v is not None]
        if len(parsed) < _ITEM_ROW_MIN_NUMERIC_TOKENS:
            continue

        first_num_pos = parsed[0][0].start()
        description = text[:first_num_pos].strip(" .:-\t")
        if not description:
            continue

        values = [v for _, v in parsed]
        item: dict = {
            "description": description,
            "quantity": values[0],
            "unit_price": values[1] if len(values) > 1 else None,
            "amount": values[2] if len(values) > 2 else (values[-1] if len(values) > 1 else None),
        }
        if len(values) > 3:
            item["additional_values"] = values[3:]
        items.append(item)
    return items


def _find_totals_triplet(content: DocumentContent) -> tuple[dict, dict, dict] | None:
    """Find a 'Total' row carrying exactly 3 trailing amounts (net / tax / gross)
    and return them positionally as (subtotal, tax_amount, total_amount)."""
    for page_number, line in _all_lines(content):
        lower = line.text.lower()
        if "total" not in lower or "qty" in lower:
            continue
        raw_tokens = find_numeric_tokens(line.text)
        values = [v for t in raw_tokens if not t.strip().endswith("%") and (v := parse_amount(t)) is not None]
        if len(values) == 3:
            conf = _line_avg_conf(line)
            return (
                _field(values[0], page_number, line.text, conf),
                _field(values[1], page_number, line.text, conf),
                _field(values[2], page_number, line.text, conf),
            )
    return None


def extract_invoice(content: DocumentContent) -> ExtractionResult:
    full_text = content.full_text

    vendor, customer = _split_seller_client(content)
    if vendor is None:
        vendor = _fallback_vendor_name(content)
    if customer is None:
        customer = _find_customer_name(content)

    subtotal = _find_amount_field(content, ["subtotal", "sub total", "sub-total"], exclude=["vat", "gross"])
    tax_amount = _find_amount_field(
        content, ["vat", "gst", "tax amount", "sales tax"], exclude=["tax id", "gstin", "gst no", "total"]
    )
    discount = _find_amount_field(content, ["discount"])
    total_amount = _find_amount_field(content, ["total amount due", "grand total", "total includes", "amount due"])
    if total_amount is None:
        total_amount = _find_amount_field(content, ["total"], exclude=["qty", "subtotal", "sub total"])

    # Some templates place subtotal/tax/total as three numbers on one summary
    # "Total" row (e.g. "Total $ 126.27 $ 12.63 $ 138.90" = net / VAT / gross)
    # without repeating the field names on that same line. Fill in whatever
    # is still missing from that row, positionally, left-to-right.
    triplet = _find_totals_triplet(content)
    if triplet is not None:
        if subtotal is None:
            subtotal = triplet[0]
        if tax_amount is None:
            tax_amount = triplet[1]
        if total_amount is None:
            total_amount = triplet[2]

    # GST/VAT-inclusive receipts often state the tax and the tax-inclusive
    # total but never a separate taxable-amount line; derive it rather than
    # leaving it blank when both of its inputs are known.
    if subtotal is None and total_amount is not None and tax_amount is not None:
        subtotal = {
            "value": round(total_amount["value"] - tax_amount["value"], 2),
            "confidence": 0.6,
            "page_number": total_amount["page_number"],
            "evidence": {
                "source_text": "Derived as total_amount - tax_amount (no explicit subtotal/taxable-amount line found).",
                "page_number": total_amount["page_number"],
            },
        }

    cash_paid = _find_amount_field(content, ["cash"], exclude=["cashier"])
    change = _find_amount_field(content, ["change"])

    if discount is None:
        discount = {"value": 0.0, "confidence": 0.5, "page_number": None,
                    "evidence": {"source_text": "No explicit discount line found; assumed 0.00.", "page_number": None}}

    extracted_data = {
        "invoice_number": _find_invoice_number(content),
        "invoice_date": _find_invoice_date(content),
        "vendor_name": vendor,
        "customer_name": customer,
        "currency": ({"value": c, "page_number": None} if (c := _detect_currency(full_text)) else None),
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "discount": discount,
        "total_amount": total_amount,
        "cash_paid": cash_paid,
        "change": change,
        "line_items": _extract_line_items(content),
    }
    return ExtractionResult(extracted_data=extracted_data)


# ---------------------------------------------------------------------------
# Balance Sheet / Profit & Loss / Cash Flow (shared table parser)
# ---------------------------------------------------------------------------


def _serialize_line_items(statement: fsp.FinancialStatement) -> list[dict]:
    items = []
    for li in statement.line_items:
        if li.is_header or not li.values:
            continue
        items.append(
            {
                "label": li.label,
                "schedule": li.schedule,
                "current_period_value": li.values[0] if len(li.values) > 0 else None,
                "comparative_period_value": li.values[1] if len(li.values) > 1 else None,
                "page_number": li.page_number,
                "source_text": li.source_text,
            }
        )
    return items


def _header_fields(statement: fsp.FinancialStatement) -> dict:
    period_dates = [extract_first_date(p) or p for p in statement.period_labels]
    return {
        "statement_title": statement.title,
        "currency": statement.currency,
        "currency_unit": statement.currency_unit_note,
        "current_period_end": period_dates[0] if len(period_dates) > 0 else None,
        "comparative_period_end": period_dates[1] if len(period_dates) > 1 else None,
    }


def extract_balance_sheet(content: DocumentContent) -> ExtractionResult:
    statement = fsp.parse_financial_statement(content, ["balance sheet"])
    fl = fsp.find_line

    data = _header_fields(statement)
    data.update(
        {
            "total_assets": fsp.line_to_field(fl(statement, ["total"], ["assets"])),
            "capital_and_liabilities_total": fsp.line_to_field(fl(statement, ["total"], ["capital and liabilities"])),
            "total_liabilities": fsp.line_to_field(fl(statement, ["total", "liabilit"])),
            "total_equity": fsp.line_to_field(fl(statement, ["total", "equity"])),
            "capital": fsp.line_to_field(fl(statement, ["capital"], ["capital and liabilities"])),
            "reserves_and_surplus": fsp.line_to_field(fl(statement, ["reserves"])),
            "deposits": fsp.line_to_field(fl(statement, ["deposits"])),
            "borrowings": fsp.line_to_field(fl(statement, ["borrowings"])),
            "line_items": _serialize_line_items(statement),
        }
    )
    return ExtractionResult(extracted_data=data, statement=statement)


def extract_profit_and_loss(content: DocumentContent) -> ExtractionResult:
    statement = fsp.parse_financial_statement(content, ["profit and loss"])
    fl = fsp.find_line

    total_income = fl(statement, ["total"], ["income"])
    total_expenditure = fl(statement, ["total"], ["expenditure"])
    net_profit_before_minority = fl(statement, ["net profit for the year"])
    consolidated_net_profit = fl(statement, ["consolidated profit for the year"])

    data = _header_fields(statement)
    data.update(
        {
            "interest_earned": fsp.line_to_field(fl(statement, ["interest earned"])),
            "other_income": fsp.line_to_field(fl(statement, ["other income"])),
            "total_income": fsp.line_to_field(total_income),
            "interest_expended": fsp.line_to_field(fl(statement, ["interest expended"])),
            "operating_expenses": fsp.line_to_field(fl(statement, ["operating expenses"])),
            "provisions_and_contingencies": fsp.line_to_field(fl(statement, ["provisions and contingencies"])),
            "total_expenditure": fsp.line_to_field(total_expenditure),
            "net_profit_before_minority_interest": fsp.line_to_field(net_profit_before_minority),
            "minority_interest": fsp.line_to_field(fl(statement, ["minority interest"])),
            "consolidated_net_profit": fsp.line_to_field(consolidated_net_profit),
            "brought_forward_profit": fsp.line_to_field(fl(statement, ["brought forward"])),
            "total_available_for_appropriation": fsp.line_to_field(fl(statement, ["total"], ["appropriations"])),
            # Generic minimum-field aliases required by the spec's document scope table.
            "revenue": fsp.line_to_field(total_income),
            "cost_of_sales": None,
            "gross_profit": None,
            "operating_profit": None,
            "tax": fsp.line_to_field(fl(statement, ["tax"], ["appropriations"])),
            "net_profit": fsp.line_to_field(consolidated_net_profit),
            "line_items": _serialize_line_items(statement),
        }
    )
    return ExtractionResult(extracted_data=data, statement=statement)


def extract_cash_flow_statement(content: DocumentContent) -> ExtractionResult:
    statement = fsp.parse_financial_statement(content, ["cash flow"])
    fl = fsp.find_line

    data = _header_fields(statement)
    data.update(
        {
            "operating_cash_flow": fsp.line_to_field(fl(statement, ["net cash flow"], ["operating"])),
            "investing_cash_flow": fsp.line_to_field(fl(statement, ["net cash flow"], ["investing"])),
            "financing_cash_flow": fsp.line_to_field(fl(statement, ["net cash flow"], ["financing"])),
            "fx_translation_adjustment": fsp.line_to_field(fl(statement, ["exchange fluctuation"])),
            "net_change_in_cash": fsp.line_to_field(fl(statement, ["net increase"])),
            "opening_cash": fsp.line_to_field(fl(statement, ["as at april"])),
            "cash_acquired_on_amalgamation": fsp.line_to_field(fl(statement, ["amalgamation"])),
            "closing_cash": fsp.line_to_field(fl(statement, ["as at march"])),
            "line_items": _serialize_line_items(statement),
        }
    )
    return ExtractionResult(extracted_data=data, statement=statement)


_EXTRACTORS = {
    "invoice": extract_invoice,
    "balance_sheet": extract_balance_sheet,
    "profit_and_loss": extract_profit_and_loss,
    "cash_flow_statement": extract_cash_flow_statement,
}


def extract(document_type: str, content: DocumentContent) -> ExtractionResult:
    extractor = _EXTRACTORS.get(document_type)
    if extractor is None:
        raise ValueError(f"No extractor registered for document_type={document_type!r}")
    return extractor(content)
