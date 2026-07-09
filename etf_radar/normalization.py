from __future__ import annotations

from datetime import date, datetime
from typing import Any


EMPTY_MARKERS = {"", "-", "--", "—", "nan", "None", "null"}


def parse_number(value: Any) -> float | None:
    """Parse common public-market numeric strings into floats."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)

    text = str(value).strip()
    if text in EMPTY_MARKERS:
        return None
    text = text.replace(",", "").replace("%", "").replace("＋", "+")
    text = text.replace("−", "-").replace("－", "-")
    if text in EMPTY_MARKERS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_share_to_yi(value: Any, column_name: str = "") -> float | None:
    """Normalize ETF fund shares into yi-fen, i.e. 100 million shares."""
    number = parse_number(value)
    if number is None:
        return None

    column = column_name.replace("（", "(").replace("）", ")")
    if "万份" in column or "(万" in column:
        return number / 10000
    if "亿份" in column or "(亿" in column:
        return number

    # Some public sources expose raw share counts without a unit hint.
    if abs(number) >= 10_000_000:
        return number / 100_000_000
    return number


def normalize_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if text in EMPTY_MARKERS:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            continue
    return None


def detect_exchange(code: Any) -> str | None:
    text = str(code).strip()
    # 55x 为科创债等跨市 ETF，也在上交所挂牌。
    if text.startswith(("51", "55", "56", "58")):
        return "SSE"
    if text.startswith(("15", "16", "18")):
        return "SZSE"
    return None


def compact_code(value: Any) -> str:
    text = str(value).strip()
    if "." in text and text.split(".", 1)[0].isdigit():
        text = text.split(".", 1)[0]
    return text.zfill(6) if text.isdigit() else text


def pick(row: dict[str, Any], candidates: list[str]) -> Any:
    for key in candidates:
        if key in row:
            return row[key]
    normalized = {str(k).strip().lower(): k for k in row}
    for key in candidates:
        actual = normalized.get(key.strip().lower())
        if actual is not None:
            return row[actual]
    return None
