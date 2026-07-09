from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .normalization import compact_code, normalize_date, parse_number


def cache_path(cache_dir: Path, code: str) -> Path:
    return cache_dir / "prices" / f"{compact_code(code)}.json"


def spot_cache_path(cache_dir: Path, as_of: date) -> Path:
    return cache_dir / "spot" / f"{as_of.isoformat()}.json"


def load_cached_spot_rows(cache_dir: Path | None, as_of: date) -> list[dict[str, Any]]:
    if cache_dir is None:
        return []
    path = spot_cache_path(cache_dir, as_of)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [dict(item) for item in data]


def save_cached_spot_rows(cache_dir: Path | None, as_of: date, rows: Iterable[dict[str, Any]]) -> None:
    if cache_dir is None:
        return
    path = spot_cache_path(cache_dir, as_of)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(rows), ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def load_cached_prices(cache_dir: Path | None, code: str) -> list[dict[str, Any]]:
    if cache_dir is None:
        return []
    path = cache_path(cache_dir, code)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for item in data:
        row_date = normalize_date(item.get("date"))
        close = parse_number(item.get("close"))
        if row_date is not None and close is not None:
            rows.append({"code": compact_code(item.get("code", code)), "date": row_date, "close": close})
    return sorted(rows, key=lambda item: item["date"])


def save_cached_prices(cache_dir: Path | None, code: str, rows: Iterable[dict[str, Any]]) -> None:
    if cache_dir is None:
        return
    path = cache_path(cache_dir, code)
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = [
        {"code": compact_code(row["code"]), "date": row["date"].isoformat(), "close": row["close"]}
        for row in sorted(rows, key=lambda item: item["date"])
    ]
    path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_price_rows(existing: Iterable[dict[str, Any]], incoming: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, date], dict[str, Any]] = {}
    for row in list(existing) + list(incoming):
        row_date = normalize_date(row.get("date"))
        close = parse_number(row.get("close"))
        code = compact_code(row.get("code"))
        if row_date is not None and close is not None:
            merged[(code, row_date)] = {"code": code, "date": row_date, "close": close}
    return [merged[key] for key in sorted(merged, key=lambda item: (item[0], item[1]))]


def cached_date_range(rows: Iterable[dict[str, Any]]) -> tuple[date | None, date | None]:
    dates = [row["date"] for row in rows if row.get("date") is not None]
    if not dates:
        return None, None
    return min(dates), max(dates)


def covers_range(rows: Iterable[dict[str, Any]], start_date: date, end_date: date) -> bool:
    first, last = cached_date_range(rows)
    return first is not None and last is not None and first <= start_date and last >= end_date
