"""Best-effort date extraction/normalisation for OCR'd / parsed document text."""
import datetime
import re

_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}
_MONTH_ABBR = {k[:3]: v for k, v in _MONTHS.items()}

_DATE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "dmy_slash"),
    (re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b"), "dmy_dash"),
    (re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b"), "dmy_dot"),
    (re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b"), "d_month_y"),
    (re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b"), "month_d_y"),
    (re.compile(r"\b(\d{1,2})-([A-Za-z]{3,9})-(\d{2})\b"), "dmy_dash_2digit"),
]


def _month_num(name: str) -> int | None:
    name = name.lower()
    return _MONTHS.get(name) or _MONTH_ABBR.get(name[:3])


def extract_first_date(text: str) -> str | None:
    """Return the first recognisable date in `text`, normalised to ISO YYYY-MM-DD, else None."""
    for pattern, kind in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        try:
            if kind == "ymd":
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif kind in ("dmy_slash", "dmy_dash", "dmy_dot"):
                d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if mo > 12 and d <= 12:
                    d, mo = mo, d
            elif kind == "d_month_y":
                d = int(m.group(1))
                mo = _month_num(m.group(2))
                y = int(m.group(3))
                if mo is None:
                    continue
            elif kind == "month_d_y":
                mo = _month_num(m.group(1))
                d = int(m.group(2))
                y = int(m.group(3))
                if mo is None:
                    continue
            elif kind == "dmy_dash_2digit":
                d = int(m.group(1))
                mo = _month_num(m.group(2))
                y = 2000 + int(m.group(3))
                if mo is None:
                    continue
            else:
                continue
            return datetime.date(y, mo, d).isoformat()
        except ValueError:
            continue
    return None
