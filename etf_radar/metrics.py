from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable


# 数据日滞后达到这么多个交易日时，看板顶部显示红色滞后提示。
DEFAULT_STALE_AFTER_TRADING_DAYS = 3


DEFAULT_WINDOWS = [
    {"key": "1D", "label": "最近1日", "days": 1},
    {"key": "1W", "label": "最近1周", "days": 7},
    {"key": "2W", "label": "最近2周", "days": 14},
    {"key": "1M", "label": "最近1月", "days": 30},
    {"key": "3M", "label": "最近3月", "days": 90},
    {"key": "6M", "label": "最近6月", "days": 180},
    {"key": "YTD", "label": "今年以来", "ytd": True},
    {"key": "12M", "label": "最近12月", "days": 365},
]


def missing_data_codes(snapshot: dict[str, Any]) -> list[str]:
    """返回快照里数据不完整的 ETF 代码：没有规模（价格或份额缺失）或没有走势序列。"""
    trend_codes = {item["code"] for item in snapshot.get("trends", [])}
    missing = []
    for row in snapshot.get("rows", []):
        if row.get("scale_100m") is None or row["code"] not in trend_codes:
            missing.append(row["code"])
    return missing


def round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def nearest_on_or_before(dates: Iterable[date], target: date) -> date | None:
    candidates = [item for item in dates if item <= target]
    if not candidates:
        return None
    return max(candidates)


def classify_flow_tag(
    amount_delta_100m: float | None,
    return_pct: float | None,
    *,
    longer_return_pct: float | None = None,
    epsilon: float = 0.01,
) -> str | None:
    if amount_delta_100m is None or return_pct is None:
        return None
    if abs(amount_delta_100m) <= epsilon:
        return None

    if amount_delta_100m > 0 and return_pct < 0 and longer_return_pct is not None and longer_return_pct > 0:
        return "追高吃套"
    if amount_delta_100m > 0 and return_pct >= 0:
        return "追高"
    if amount_delta_100m > 0 and return_pct < 0:
        return "抄底"
    if amount_delta_100m < 0 and return_pct < 0:
        return "撤退"
    if amount_delta_100m < 0 and return_pct >= 0:
        return "止盈"
    return None


def _target_date(as_of: date, window: dict[str, Any]) -> date:
    if window.get("ytd"):
        return date(as_of.year, 1, 1)
    return as_of - timedelta(days=int(window["days"]))


def _max_anchor_gap_days(window: dict[str, Any]) -> int:
    if window.get("ytd"):
        return 10
    days = int(window["days"])
    if days <= 1:
        return 3
    return min(max(days // 2, 5), 14)


def _index_records(records: Iterable[dict[str, Any]], value_key: str) -> dict[str, dict[date, float]]:
    indexed: dict[str, dict[date, float]] = defaultdict(dict)
    for record in records:
        code = str(record["code"])
        record_date = record["date"]
        value = record.get(value_key)
        if record_date is not None and value is not None:
            indexed[code][record_date] = float(value)
    return indexed


def adjust_close_for_splits(
    closes: dict[date, float],
    *,
    drop_ratio: float = 0.7,
    rise_ratio: float = 1.43,
) -> dict[date, float]:
    """把 ETF 份额折算/拆分造成的价格跳变抹平，返回复权后的收盘价序列（供涨跌幅和走势使用）。

    ETF 净值单日不可能真实波动 30% 以上，超过阈值的相邻跳变视为折算，用累计因子
    把折算后的价格缩放回折算前的量纲，使收益率连续。规模和最新价仍用原始价格。
    """
    adjusted: dict[date, float] = {}
    multiplier = 1.0
    previous: float | None = None
    for record_date in sorted(closes):
        raw = closes[record_date]
        if previous is not None and previous > 0 and raw > 0:
            ratio = raw / previous
            if ratio <= drop_ratio or ratio >= rise_ratio:
                multiplier *= previous / raw
        adjusted[record_date] = raw * multiplier
        previous = raw
    return adjusted


def adjust_all_splits(price_by_code: dict[str, dict[date, float]]) -> dict[str, dict[date, float]]:
    return {code: adjust_close_for_splits(closes) for code, closes in price_by_code.items()}


def _window_metric(
    *,
    code: str,
    as_of: date,
    window: dict[str, Any],
    price_by_code: dict[str, dict[date, float]],
    share_by_code: dict[str, dict[date, float]],
    return_price_by_code: dict[str, dict[date, float]] | None = None,
) -> dict[str, Any]:
    # 涨跌幅用复权价（抹平折算），规模和金额净流入用原始价。
    return_price_by_code = return_price_by_code or price_by_code
    current_share = share_by_code.get(code, {}).get(as_of)
    current_close = price_by_code.get(code, {}).get(as_of)
    target = _target_date(as_of, window)
    anchor_share_date = nearest_on_or_before(share_by_code.get(code, {}).keys(), target)
    anchor_price_date = nearest_on_or_before(price_by_code.get(code, {}).keys(), target)

    if (
        current_share is None
        or current_close is None
        or anchor_share_date is None
        or (target - anchor_share_date).days > _max_anchor_gap_days(window)
    ):
        return {
            "share_delta_yi": None,
            "amount_delta_100m": None,
            "return_pct": None,
            "anchor_date": None,
            "price_anchor_date": None,
            "rank": None,
        }

    anchor_share = share_by_code[code][anchor_share_date]
    share_delta = current_share - anchor_share
    amount_delta = share_delta * current_close
    return_pct = None
    if anchor_price_date is not None and (target - anchor_price_date).days <= _max_anchor_gap_days(window):
        anchor_close = return_price_by_code.get(code, {}).get(anchor_price_date)
        current_adjusted = return_price_by_code.get(code, {}).get(as_of)
        if anchor_close not in (None, 0) and current_adjusted is not None:
            return_pct = (current_adjusted / anchor_close - 1) * 100
    return {
        "share_delta_yi": round_or_none(share_delta, 2),
        "amount_delta_100m": round_or_none(amount_delta, 2),
        "return_pct": round_or_none(return_pct, 2),
        "anchor_date": anchor_share_date.isoformat(),
        "price_anchor_date": anchor_price_date.isoformat() if anchor_price_date else None,
        "rank": None,
    }


def build_rotation(rows: list[dict[str, Any]], windows: list[dict[str, Any]]) -> dict[str, Any]:
    """按板块聚合资金轮动，供前端展示流入、流出和最大去向。"""
    windows_by_key: dict[str, Any] = {}
    for window in windows:
        key = window["key"]
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            value = row.get("windows", {}).get(key, {}).get("amount_delta_100m")
            if value is None:
                continue
            group = row.get("category") or "未分类"
            bucket = buckets.setdefault(
                group,
                {
                    "group": group,
                    "value_100m": 0.0,
                    "etf_count": 0,
                    "inflow_count": 0,
                    "outflow_count": 0,
                },
            )
            bucket["value_100m"] += float(value)
            bucket["etf_count"] += 1
            if value > 0:
                bucket["inflow_count"] += 1
            elif value < 0:
                bucket["outflow_count"] += 1

        entries = [
            {
                **bucket,
                "value_100m": round_or_none(bucket["value_100m"], 2),
            }
            for bucket in buckets.values()
        ]
        entries.sort(key=lambda item: item["value_100m"] or 0, reverse=True)

        inflow_total = sum(item["value_100m"] or 0 for item in entries if (item["value_100m"] or 0) > 0)
        outflow_total = sum(item["value_100m"] or 0 for item in entries if (item["value_100m"] or 0) < 0)
        destination = next((item for item in entries if (item["value_100m"] or 0) > 0), None)
        source = min(entries, key=lambda item: item["value_100m"] or 0, default=None)
        windows_by_key[key] = {
            "key": key,
            "label": window.get("label") or key,
            "inflow_total_100m": round_or_none(inflow_total, 2),
            "outflow_total_100m": round_or_none(outflow_total, 2),
            "net_flow_100m": round_or_none(inflow_total + outflow_total, 2),
            "largest_destination": destination["group"] if destination else None,
            "largest_destination_100m": destination["value_100m"] if destination else None,
            "largest_source": source["group"] if source and (source["value_100m"] or 0) < 0 else None,
            "largest_source_100m": source["value_100m"] if source and (source["value_100m"] or 0) < 0 else None,
            "entries": entries,
        }
    return {
        "grouping": "category",
        "unit": "亿元",
        "windows": windows_by_key,
    }


def empty_beta_pressure(as_of: date) -> dict[str, Any]:
    """ETF 持仓穿透维度的标准空态；接入持仓明细后可直接替换 rows/detail。"""
    return {
        "status": "unavailable",
        "as_of": as_of.isoformat(),
        "holding_as_of": None,
        "share_as_of": as_of.isoformat(),
        "reason": "当前 snapshot 未包含 ETF 持仓穿透数据。",
        "summary": {
            "stock_count": None,
            "linked_etf_count": None,
            "net_position_change_yi_shares": None,
            "margin_balance_100m": None,
            "data_status": "待接入持仓",
        },
        "rows": [],
        "history": [],
    }


def build_snapshot(
    *,
    master: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    shares: list[dict[str, Any]],
    as_of: date,
    generated_at: str | None = None,
    windows: list[dict[str, Any]] | None = None,
    status: str = "ready",
    sources: list[dict[str, str]] | None = None,
    source_errors: list[str] | None = None,
    stale_after_trading_days: int = DEFAULT_STALE_AFTER_TRADING_DAYS,
    beta_pressure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    windows = windows or DEFAULT_WINDOWS
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    price_by_code = _index_records(prices, "close")
    adjusted_price_by_code = adjust_all_splits(price_by_code)
    share_by_code = _index_records(shares, "shares_yi")

    rows = []
    for item in master:
        code = str(item["code"])
        current_share = share_by_code.get(code, {}).get(as_of)
        current_close = price_by_code.get(code, {}).get(as_of)
        scale = current_share * current_close if current_share is not None and current_close is not None else None
        row_windows = {
            window["key"]: _window_metric(
                code=code,
                as_of=as_of,
                window=window,
                price_by_code=price_by_code,
                share_by_code=share_by_code,
                return_price_by_code=adjusted_price_by_code,
            )
            for window in windows
        }
        longer_return = row_windows.get("3M", {}).get("return_pct")
        tag_source = row_windows.get("1W") or row_windows.get("1D") or {}
        rows.append(
            {
                "code": code,
                "name": item.get("name") or code,
                "exchange": item.get("exchange"),
                "category": item.get("category") or "未分类",
                "subcategory": item.get("subcategory") or item.get("category") or "未分类",
                "manager": item.get("manager"),
                "listed_date": item.get("listed_date"),
                "scale_100m": round_or_none(scale, 2),
                "latest_price": round_or_none(current_close, 4),
                "latest_share_yi": round_or_none(current_share, 2),
                "tag": classify_flow_tag(
                    tag_source.get("amount_delta_100m"),
                    tag_source.get("return_pct"),
                    longer_return_pct=longer_return,
                ),
                "windows": row_windows,
            }
        )

    for window in windows:
        key = window["key"]
        ranked = sorted(
            [row for row in rows if row["windows"][key]["amount_delta_100m"] is not None],
            key=lambda row: row["windows"][key]["amount_delta_100m"],
            reverse=True,
        )
        for rank, row in enumerate(ranked, start=1):
            row["windows"][key]["rank"] = rank

    rows.sort(key=lambda row: row["windows"].get("1D", {}).get("amount_delta_100m") or float("-inf"), reverse=True)

    def sum_window(key: str) -> float | None:
        values = [row["windows"][key]["amount_delta_100m"] for row in rows if key in row["windows"]]
        values = [value for value in values if value is not None]
        if not values:
            return None
        return round(sum(values), 2)

    summary = {
        "etf_count": len(rows),
        "total_scale_100m": round_or_none(sum(row["scale_100m"] or 0 for row in rows), 2),
        "flow_1d_100m": sum_window("1D"),
        "flow_1w_100m": sum_window("1W"),
    }

    trends = []
    for row in rows:
        # 走势和迷你走势用复权价，避免折算日出现断崖。
        series = sorted(
            (item for item in adjusted_price_by_code.get(row["code"], {}).items() if item[0] <= as_of)
        )
        if len(series) < 2:
            continue
        trends.append(
            {
                "code": row["code"],
                "dates": [item[0].isoformat() for item in series],
                "closes": [round(item[1], 4) for item in series],
            }
        )

    return {
        "meta": {
            "version": 1,
            "status": status,
            "as_of": as_of.isoformat(),
            "generated_at": generated_at,
            "stale_after_trading_days": stale_after_trading_days,
            "unit": {
                "share_delta_yi": "亿份",
                "amount_delta_100m": "亿元",
                "return_pct": "%",
                "scale_100m": "亿元",
                "rotation_flow_100m": "亿元",
            },
        },
        "summary": summary,
        "windows": windows,
        "rows": rows,
        "trends": trends,
        "rotation": build_rotation(rows, windows),
        "beta_pressure": beta_pressure or empty_beta_pressure(as_of),
        "sources": sources or [],
        "source_errors": source_errors or [],
    }
