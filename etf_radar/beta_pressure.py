from __future__ import annotations

from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import re
from statistics import median
from typing import Any, Iterable

from .metrics import empty_beta_pressure, round_or_none
from .normalization import compact_code, normalize_date, parse_number, pick


_QUARTER_ENDS = {
    1: (3, 31),
    2: (6, 30),
    3: (9, 30),
    4: (12, 31),
}


def stock_exchange(code: str) -> str | None:
    code = compact_code(code)
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return "SSE"
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZSE"
    if code.startswith(("4", "8", "92")):
        return "BSE"
    return None


def parse_holding_period(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    match = re.search(r"(\d{4})\s*年\s*([1-4])\s*季度", text)
    if match:
        year = int(match.group(1))
        month, day = _QUARTER_ENDS[int(match.group(2))]
        return date(year, month, day)
    return normalize_date(value)


def normalize_holding_records(rows: Iterable[dict[str, Any]], etf_code: str) -> list[dict[str, Any]]:
    """把基金持仓统一到 ETF-股票-报告期粒度，并合并同一报告中的重复证券行。"""
    grouped: dict[tuple[str, str, date], dict[str, Any]] = {}
    for raw in rows:
        raw_stock_code = pick(raw, ["股票代码", "证券代码", "代码", "stock_code"])
        raw_stock_text = str(raw_stock_code).strip().split(".", 1)[0]
        # 港股代码通常为 5 位，不能补零后误识别成深市 A 股。
        if raw_stock_text.isdigit() and len(raw_stock_text) == 5:
            continue
        stock_code = compact_code(raw_stock_code)
        report_date = parse_holding_period(pick(raw, ["季度", "报告期", "日期", "report_date"]))
        if stock_exchange(stock_code) is None or report_date is None:
            continue
        holding_wan_shares = parse_number(pick(raw, ["持股数", "持股数量", "holding_wan_shares"]))
        market_value_wan = parse_number(pick(raw, ["持仓市值", "市值", "market_value_wan"]))
        weight_pct = parse_number(pick(raw, ["占净值比例", "占基金净值比", "weight_pct"]))
        if holding_wan_shares is None or holding_wan_shares <= 0:
            continue
        key = (compact_code(etf_code), stock_code, report_date)
        item = grouped.setdefault(
            key,
            {
                "etf_code": compact_code(etf_code),
                "stock_code": stock_code,
                "stock_name": str(pick(raw, ["股票名称", "证券简称", "名称", "stock_name"]) or stock_code).strip(),
                "report_date": report_date,
                "holding_shares": 0.0,
                "market_value_yuan": 0.0,
                "weight_pct": 0.0,
            },
        )
        item["holding_shares"] += holding_wan_shares * 10_000
        item["market_value_yuan"] += max(market_value_wan or 0, 0) * 10_000
        item["weight_pct"] += max(weight_pct or 0, 0)
    return list(grouped.values())


def latest_holding_records(records: Iterable[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    by_etf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in records:
        report_date = normalize_date(item.get("report_date"))
        if report_date is not None and report_date <= as_of:
            normalized = dict(item)
            normalized["report_date"] = report_date
            by_etf[compact_code(item.get("etf_code"))].append(normalized)

    latest = []
    for rows in by_etf.values():
        latest_date = max(item["report_date"] for item in rows)
        latest.extend(item for item in rows if item["report_date"] == latest_date)
    return latest


def normalize_stock_market_rows(
    rows: Iterable[dict[str, Any]],
    *,
    source: str,
    wanted_codes: set[str] | None = None,
) -> list[dict[str, Any]]:
    normalized = []
    for raw in rows:
        code = compact_code(pick(raw, ["代码", "股票代码", "证券代码", "code"]))
        if stock_exchange(code) is None or (wanted_codes and code not in wanted_codes):
            continue
        price = parse_number(pick(raw, ["最新价", "现价", "trade", "price", "close"]))
        float_market_value = parse_number(pick(raw, ["流通市值", "float_market_value", "nmc"]))
        if source == "Sina" and float_market_value is not None:
            # 新浪 Market Center 的 nmc 单位为万元。
            float_market_value *= 10_000
        float_shares = None
        if price not in (None, 0) and float_market_value is not None:
            float_shares = float_market_value / price
        normalized.append(
            {
                "code": code,
                "name": str(pick(raw, ["名称", "股票名称", "name"]) or code).strip(),
                "price": price,
                "float_market_value_yuan": float_market_value,
                "float_shares": float_shares,
                "industry": pick(raw, ["行业", "industry"]),
                "source": source,
            }
        )
    return normalized


def normalize_margin_rows(
    sse_rows: Iterable[dict[str, Any]],
    szse_rows: Iterable[dict[str, Any]],
    market_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    market_by_code = {item["code"]: item for item in market_rows}
    result = []
    for raw in sse_rows:
        code = compact_code(pick(raw, ["标的证券代码", "证券代码", "代码"]))
        if stock_exchange(code) != "SSE":
            continue
        margin_yuan = parse_number(pick(raw, ["融资余额", "margin_balance"]))
        short_quantity = parse_number(pick(raw, ["融券余量", "short_quantity"]))
        price = market_by_code.get(code, {}).get("price")
        short_yuan = short_quantity * price if short_quantity is not None and price is not None else None
        result.append(
            {
                "code": code,
                "margin_balance_yuan": margin_yuan,
                "short_balance_yuan": short_yuan,
                "short_quantity": short_quantity,
                "exchange": "SSE",
            }
        )
    for raw in szse_rows:
        code = compact_code(pick(raw, ["证券代码", "标的证券代码", "代码"]))
        if stock_exchange(code) != "SZSE":
            continue
        result.append(
            {
                "code": code,
                "margin_balance_yuan": parse_number(pick(raw, ["融资余额", "margin_balance"])),
                "short_balance_yuan": parse_number(pick(raw, ["融券余额", "short_balance"])),
                "short_quantity": parse_number(pick(raw, ["融券余量", "short_quantity"])),
                "exchange": "SZSE",
            }
        )
    return result


def _latest_by_code(records: Iterable[dict[str, Any]], value_key: str, as_of: date) -> dict[str, tuple[date, float]]:
    result: dict[str, tuple[date, float]] = {}
    for item in records:
        item_date = normalize_date(item.get("date"))
        value = parse_number(item.get(value_key))
        code = compact_code(item.get("code"))
        if item_date is None or item_date > as_of or value is None:
            continue
        if code not in result or item_date > result[code][0]:
            result[code] = (item_date, value)
    return result


def _previous_by_code(records: Iterable[dict[str, Any]], value_key: str, current: dict[str, tuple[date, float]]) -> dict[str, tuple[date, float]]:
    result: dict[str, tuple[date, float]] = {}
    for item in records:
        code = compact_code(item.get("code"))
        item_date = normalize_date(item.get("date"))
        value = parse_number(item.get(value_key))
        current_item = current.get(code)
        if current_item is None or item_date is None or item_date >= current_item[0] or value is None:
            continue
        if code not in result or item_date > result[code][0]:
            result[code] = (item_date, value)
    return result


def _report_nav_yuan(records: list[dict[str, Any]]) -> float | None:
    estimates = []
    for item in records:
        weight_pct = parse_number(item.get("weight_pct"))
        market_value = parse_number(item.get("market_value_yuan"))
        if weight_pct is not None and weight_pct > 0 and market_value is not None and market_value > 0:
            estimates.append(market_value / (weight_pct / 100))
    return median(estimates) if estimates else None


def build_beta_pressure(
    *,
    master: list[dict[str, Any]],
    prices: list[dict[str, Any]],
    shares: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    stock_market: list[dict[str, Any]],
    margins: list[dict[str, Any]],
    as_of: date,
    top_stocks: int = 120,
) -> dict[str, Any]:
    latest_holdings = latest_holding_records(holdings, as_of)
    if not latest_holdings:
        result = empty_beta_pressure(as_of)
        result["reason"] = "未获取到观察池 ETF 的最新公开持仓。"
        return result

    master_by_code = {compact_code(item["code"]): item for item in master}
    current_prices = _latest_by_code(prices, "close", as_of)
    current_shares = _latest_by_code(shares, "shares_yi", as_of)
    previous_shares = _previous_by_code(shares, "shares_yi", current_shares)
    market_by_code = {item["code"]: item for item in stock_market}
    margin_by_code = {item["code"]: item for item in margins}

    holdings_by_etf: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in latest_holdings:
        holdings_by_etf[item["etf_code"]].append(item)

    stock_buckets: dict[str, dict[str, Any]] = {}
    used_etfs: set[str] = set()
    report_dates: set[date] = set()
    for etf_code, records in holdings_by_etf.items():
        current_price = current_prices.get(etf_code)
        current_share = current_shares.get(etf_code)
        previous_share = previous_shares.get(etf_code)
        if current_price is None or current_share is None or previous_share is None:
            continue
        etf_price = current_price[1]
        current_share_yi = current_share[1]
        share_delta_yi = current_share_yi - previous_share[1]
        if etf_price <= 0 or current_share_yi <= 0:
            continue
        report_nav = _report_nav_yuan(records)
        etf_market_value = current_share_yi * 100_000_000 * etf_price
        etf_flow_value = share_delta_yi * 100_000_000 * etf_price
        used_etfs.add(etf_code)
        report_dates.add(records[0]["report_date"])
        for item in records:
            market_value = parse_number(item.get("market_value_yuan")) or 0
            weight_pct = parse_number(item.get("weight_pct")) or 0
            weight = weight_pct / 100
            if weight <= 0 and report_nav not in (None, 0) and market_value > 0:
                weight = market_value / report_nav
            if not 0 < weight <= 1:
                continue
            stock_code = item["stock_code"]
            market = market_by_code.get(stock_code, {})
            stock_price = parse_number(market.get("price"))
            report_holding = parse_number(item.get("holding_shares")) or 0
            report_price = market_value / report_holding if report_holding > 0 and market_value > 0 else None
            valuation_price = stock_price or report_price
            if valuation_price in (None, 0):
                continue
            estimated_holding = etf_market_value * weight / valuation_price
            estimated_change = etf_flow_value * weight / valuation_price
            change_amount = estimated_change * valuation_price
            bucket = stock_buckets.setdefault(
                stock_code,
                {
                    "code": stock_code,
                    "name": item.get("stock_name") or market.get("name") or stock_code,
                    "industry": market.get("industry"),
                    "holding_shares": 0.0,
                    "change_shares": 0.0,
                    "change_amount_yuan": 0.0,
                    "linked_etfs": set(),
                    "contributors": [],
                },
            )
            bucket["holding_shares"] += estimated_holding
            bucket["change_shares"] += estimated_change
            bucket["change_amount_yuan"] += change_amount
            bucket["linked_etfs"].add(etf_code)
            bucket["contributors"].append(
                {
                    "code": etf_code,
                    "name": master_by_code.get(etf_code, {}).get("name") or etf_code,
                    "change_wan_shares": estimated_change / 10_000,
                    "change_amount_100m": change_amount / 100_000_000,
                    "weight_pct": weight * 100,
                }
            )

    if not stock_buckets:
        result = empty_beta_pressure(as_of)
        result["reason"] = "持仓已获取，但缺少可用于穿透计算的份额、价格或股票行情。"
        return result

    rows = []
    market_covered = 0
    for code, bucket in stock_buckets.items():
        market = market_by_code.get(code, {})
        margin = margin_by_code.get(code)
        if market.get("price") is not None:
            market_covered += 1
        contributors = sorted(bucket["contributors"], key=lambda item: abs(item["change_amount_100m"]), reverse=True)
        increase = sum(max(item["change_wan_shares"], 0) for item in contributors)
        decrease = sum(min(item["change_wan_shares"], 0) for item in contributors)
        rows.append(
            {
                "code": code,
                "name": market.get("name") or bucket["name"],
                "industry": market.get("industry") or bucket.get("industry"),
                "linked_etf_count": len(bucket["linked_etfs"]),
                "penetrated_holding_yi_shares": round_or_none(bucket["holding_shares"] / 100_000_000, 4),
                "today_change_wan_shares": round_or_none(bucket["change_shares"] / 10_000, 2),
                "change_amount_100m": round_or_none(bucket["change_amount_yuan"] / 100_000_000, 4),
                "margin_balance_100m": round_or_none((margin or {}).get("margin_balance_yuan") / 100_000_000, 3)
                if (margin or {}).get("margin_balance_yuan") is not None
                else None,
                "short_balance_100m": round_or_none((margin or {}).get("short_balance_yuan") / 100_000_000, 3)
                if (margin or {}).get("short_balance_yuan") is not None
                else None,
                "margin_eligible": margin is not None if margins else None,
                "float_shares_100m": round_or_none((market.get("float_shares") or 0) / 100_000_000, 4)
                if market.get("float_shares") is not None
                else None,
                "float_market_value_100m": round_or_none((market.get("float_market_value_yuan") or 0) / 100_000_000, 2)
                if market.get("float_market_value_yuan") is not None
                else None,
                "latest_price": round_or_none(market.get("price"), 4),
                "etf_increase_wan_shares": round_or_none(increase, 2),
                "etf_decrease_wan_shares": round_or_none(decrease, 2),
                "contributors": [
                    {
                        **item,
                        "change_wan_shares": round_or_none(item["change_wan_shares"], 2),
                        "change_amount_100m": round_or_none(item["change_amount_100m"], 4),
                        "weight_pct": round_or_none(item["weight_pct"], 3),
                    }
                    for item in contributors[:8]
                ],
            }
        )

    rows.sort(key=lambda item: abs(item.get("change_amount_100m") or 0), reverse=True)
    rows = rows[: max(top_stocks, 1)]
    eligible_etfs = [item for item in master if item.get("category") not in {"债券", "商品", "货币"}]
    holding_etfs = {item["etf_code"] for item in latest_holdings}
    holding_coverage = len(holding_etfs) / len(eligible_etfs) if eligible_etfs else 0
    market_coverage = market_covered / len(stock_buckets) if stock_buckets else 0
    status = "ready" if holding_coverage >= 0.7 and market_coverage >= 0.8 else "partial"
    reason = None
    if status == "partial":
        reason = f"公开持仓覆盖 {len(holding_etfs)}/{len(eligible_etfs)} 只权益 ETF，结果为部分样本估算。"
    return {
        "status": status,
        "as_of": as_of.isoformat(),
        "holding_as_of": max(report_dates).isoformat() if report_dates else None,
        "holding_periods": sorted(item.isoformat() for item in report_dates),
        "share_as_of": as_of.isoformat(),
        "market_as_of": as_of.isoformat(),
        "source_mode": "periodic_report_estimate",
        "method_label": "定期报告持仓 × ETF 份额变化估算",
        "reason": reason,
        "summary": {
            "stock_count": len(rows),
            "linked_etf_count": len(used_etfs),
            "net_position_change_yi_shares": round_or_none(sum((item["today_change_wan_shares"] or 0) for item in rows) / 10_000, 4),
            "margin_balance_100m": round_or_none(sum((item["margin_balance_100m"] or 0) for item in rows), 2) if margins else None,
            "data_status": "定期报告估算" if status == "ready" else "部分覆盖",
        },
        "coverage": {
            "eligible_etf_count": len(eligible_etfs),
            "holding_etf_count": len(holding_etfs),
            "holding_etf_pct": round_or_none(holding_coverage * 100, 1),
            "market_stock_count": market_covered,
            "market_stock_pct": round_or_none(market_coverage * 100, 1),
            "margin_stock_count": sum(1 for item in rows if item["margin_eligible"]),
            "margin_data_available": bool(margins),
        },
        "methodology": {
            "holding_basis": "最新公开季度持仓权重",
            "position_estimate": "ETF 最新规模 × 持仓权重 ÷ 个股价格",
            "change_estimate": "ETF 份额日变化 × ETF 价格 × 持仓权重 ÷ 个股价格",
            "limitation": "持仓不是实时披露，结果只反映 ETF 申赎方向的估算压力，不代表基金当日真实交易。",
        },
        "rows": rows,
        "history": [],
    }


def update_beta_history(cache_dir: Path | None, beta_pressure: dict[str, Any], max_points: int = 120) -> list[dict[str, Any]]:
    if cache_dir is None or not beta_pressure.get("rows"):
        return []
    path = cache_dir / "beta" / "history.json"
    history: list[dict[str, Any]] = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                history = [dict(item) for item in data]
        except (OSError, ValueError, TypeError):
            history = []
    current = {
        "date": beta_pressure.get("as_of"),
        "holding_as_of": beta_pressure.get("holding_as_of"),
        "rows": [
            {
                "code": item.get("code"),
                "today_change_wan_shares": item.get("today_change_wan_shares"),
                "change_amount_100m": item.get("change_amount_100m"),
                "penetrated_holding_yi_shares": item.get("penetrated_holding_yi_shares"),
            }
            for item in beta_pressure["rows"]
        ],
    }
    by_date = {str(item.get("date")): item for item in history if item.get("date")}
    by_date[str(current["date"])] = current
    history = [by_date[key] for key in sorted(by_date)][-max(max_points, 1) :]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history
