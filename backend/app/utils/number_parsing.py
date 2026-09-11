"""Locale-tolerant numeric parsing helpers for financial documents.

Handles:
  - thousands separators: "1,234,567" -> 1234567
  - parentheses/brackets as negative: "(412,439,139)" -> -412439139
  - European decimal-comma amounts on the sample invoice template: "126,27" -> 126.27
  - trailing minus / leading minus: "1234-" or "-1234"
  - currency symbols and stray whitespace
"""
import re

NUMBER_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])[\(\[]?-?[₹$€£]?-?\d[\d,.]*[\)\]]?%?(?![A-Za-z0-9])"
)

_CURRENCY_SYMBOLS = "₹$€£"


_OCR_NOISE_CHARS_RE = re.compile(r"[|_~`••]")


def _strip_currency_and_spaces(token: str) -> str:
    token = token.strip()
    token = _OCR_NOISE_CHARS_RE.sub("", token)
    for sym in _CURRENCY_SYMBOLS:
        token = token.replace(sym, "")
    token = token.replace(" ", "")
    return token


def parse_amount(raw: str | float | int | None) -> float | None:
    """Best-effort parse of a numeric token found in a financial document into a float.

    Returns None if the token cannot be confidently parsed as a number.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)

    text = raw.strip()
    if not text:
        return None

    negative = False
    if (text.startswith("(") and text.endswith(")")) or (text.startswith("[") and text.endswith("]")):
        negative = True
        text = text[1:-1].strip()

    text = _strip_currency_and_spaces(text)
    if not text:
        return None

    if text.endswith("-"):
        negative = True
        text = text[:-1]
    if text.startswith("-"):
        negative = True
        text = text[1:]

    text = text.rstrip("%")

    if text in {"-", "--", "", "N/A", "n/a", "NA"}:
        return None
    # A lone dash/hyphen is how these bank statements denote a zero/blank cell.
    if text in {"–", "—"}:
        return 0.0

    has_comma = "," in text
    has_dot = "." in text

    value_str = text
    if has_comma and has_dot:
        # Whichever separator appears last is the decimal separator.
        if text.rfind(",") > text.rfind("."):
            value_str = text.replace(".", "").replace(",", ".")
        else:
            value_str = text.replace(",", "")
    elif has_comma and not has_dot:
        # Could be thousands ("1,234,567") or a European decimal ("126,27").
        groups = text.split(",")
        last_group = groups[-1]
        if len(groups) == 2 and len(last_group) == 2:
            # e.g. "126,27" -> decimal comma
            value_str = text.replace(",", ".")
        else:
            # e.g. "1,234,567" -> thousands separators
            value_str = text.replace(",", "")
    # else: plain integer/decimal with '.' or no separators at all

    if not re.fullmatch(r"-?\d+(\.\d+)?", value_str):
        return None

    try:
        value = float(value_str)
    except ValueError:
        return None

    return -value if negative else value


def find_numeric_matches(line: str) -> list[re.Match]:
    """Return regex Match objects (with exact positions) for numeric-looking tokens in a text line."""
    return [m for m in NUMBER_TOKEN_RE.finditer(line) if any(c.isdigit() for c in m.group(0))]


def find_numeric_tokens(line: str) -> list[str]:
    """Return numeric-looking tokens (in original left-to-right order) found in a text line."""
    return [m.group(0).strip() for m in find_numeric_matches(line)]


def looks_like_schedule_ref(token: str) -> bool:
    """True for small schedule/note references like '1', '2A', '17 & 18' (no thousands comma, short)."""
    t = token.strip().strip("()")
    if "," in t:
        return False
    return bool(re.fullmatch(r"\d{1,2}[A-Za-z]?", t))
