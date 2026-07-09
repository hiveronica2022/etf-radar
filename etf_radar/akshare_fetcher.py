from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
import signal
from time import sleep
from typing import Any, Iterable

from .metrics import DEFAULT_WINDOWS, build_snapshot
from .presets import ETF_NAME_OVERRIDES
from .normalization import (
    compact_code,
    detect_exchange,
    normalize_date,
    normalize_share_to_yi,
    parse_number,
    pick,
)
from .price_cache import (
    cached_date_range,
    load_cached_prices,
    load_cached_spot_rows,
    merge_price_rows,
    save_cached_prices,
    save_cached_spot_rows,
)


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchOptions:
    as_of: date
    start_date: date
    codes: list[str] | None = None
    limit: int | None = None
    cache_dir: Path | None = Path("cache")
    price_retries: int = 2
    retry_sleep_seconds: float = 1.0
    source_retries: int = 3
    source_timeout_seconds: int = 15
    price_pause_seconds: float = 0.35
    use_sina_fallback: bool = True
    strict: bool = False
    source_errors: list[str] = field(default_factory=list)
    windows: list[dict[str, Any]] | None = None


def _load_akshare():
    try:
        import akshare as ak  # type: ignore
    except ImportError as exc:
        raise FetchError("缺少 akshare。请先运行: python3 -m pip install -r requirements.txt") from exc
    return ak


def _ensure_func(ak: Any, name: str):
    func = getattr(ak, name, None)
    if func is None:
        raise FetchError(f"当前 AKShare 未提供 {name}，请升级 AKShare 或检查接口名称。")
    return func


class SourceTimeout(TimeoutError):
    pass


@contextmanager
def source_deadline(seconds: int | None):
    if not seconds or seconds <= 0:
        yield
        return

    def _raise_timeout(signum, frame):
        raise SourceTimeout(f"source call timed out after {seconds}s")

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 0)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])


def call_with_retries(
    func: Any,
    *,
    label: str,
    retries: int = 3,
    sleep_seconds: float = 1.0,
    timeout_seconds: int | None = 15,
    **kwargs: Any,
) -> Any:
    attempts = max(retries, 1)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with source_deadline(timeout_seconds):
                return func(**kwargs)
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1 and sleep_seconds > 0:
                sleep(sleep_seconds)
    raise FetchError(f"{label} 获取失败，已重试 {attempts} 次: {last_error}") from last_error


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return list(frame.to_dict("records"))
    if isinstance(frame, list):
        return [dict(item) for item in frame]
    raise FetchError(f"无法识别的数据表类型: {type(frame)!r}")


def _filter_codes(rows: Iterable[dict[str, Any]], codes: set[str] | None, limit: int | None) -> list[dict[str, Any]]:
    filtered = []
    for row in rows:
        code = compact_code(pick(row, ["代码", "基金代码", "证券代码", "code"]))
        if codes and code not in codes:
            continue
        new_row = dict(row)
        new_row["_code"] = code
        filtered.append(new_row)
        if limit is not None and len(filtered) >= limit:
            break
    return filtered


def _normalize_master_from_spot(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    master = []
    for row in rows:
        code = row["_code"]
        name = pick(row, ["名称", "基金简称", "基金名称", "name"]) or code
        clean_name = str(name).strip()
        category = classify_category(clean_name)
        master.append(
            {
                "code": code,
                "name": clean_name,
                "exchange": detect_exchange(code),
                "category": category,
                "subcategory": classify_subcategory(clean_name, category),
                "manager": infer_manager(clean_name),
                "listed_date": None,
            }
        )
    return master


def append_missing_code_masters(master: list[dict[str, Any]], codes: set[str] | None) -> None:
    if not codes:
        return
    existing = {item["code"] for item in master}
    for code in sorted(codes - existing):
        name = ETF_NAME_OVERRIDES.get(code, code)
        category = classify_category(name) if name != code else "未分类"
        master.append(
            {
                "code": code,
                "name": name,
                "exchange": detect_exchange(code),
                "category": category,
                "subcategory": classify_subcategory(name, category) if name != code else "未分类",
                "manager": infer_manager(name) if name != code else None,
                "listed_date": None,
            }
        )


def enrich_master_from_shares(master: list[dict[str, Any]], shares: Iterable[dict[str, Any]]) -> None:
    names = {}
    for item in shares:
        name = item.get("name")
        if name:
            names[item["code"]] = str(name)
    for item in master:
        code = item["code"]
        if item.get("name") == code and code in names:
            item["name"] = names[code]
            item["category"] = classify_category(names[code])
            item["subcategory"] = classify_subcategory(names[code], item["category"])
            item["manager"] = infer_manager(names[code])


def classify_category(name: str) -> str:
    rules = [
        ("债", "债券"),
        ("短融", "债券"),
        ("货币", "货币"),
        ("黄金", "商品"),
        ("有色", "商品"),
        ("能源", "商品"),
        ("油", "商品"),
        ("半导体", "科技"),
        ("芯片", "科技"),
        ("通信", "科技"),
        ("互联网", "科技"),
        ("人工智能", "科技"),
        ("软件", "科技"),
        ("云计算", "科技"),
        ("计算机", "科技"),
        ("信息技术", "科技"),
        ("电子", "科技"),
        ("机器人", "科技"),
        ("科技", "科技"),
        ("医药", "医药"),
        ("证券", "金融"),
        ("银行", "金融"),
        ("红利", "红利"),
        ("300", "宽基"),
        ("500", "宽基"),
        ("1000", "宽基"),
        ("A50", "宽基"),
        ("创业板", "宽基"),
        ("科创", "宽基"),
        ("深100", "宽基"),
        ("深证100", "宽基"),
        ("上证50", "宽基"),
    ]
    for needle, category in rules:
        if needle in name:
            return category
    return "行业主题"


# 各板块的细分子类规则：按名称关键词命中，顺序敏感（更具体的放前面）。
_SUBCATEGORY_RULES: dict[str, list[tuple[str, str]]] = {
    "红利": [
        ("港股", "港股红利"),
        ("恒生", "港股红利"),
        ("低波", "红利低波"),
        ("国企", "国企央企红利"),
        ("央企", "国企央企红利"),
        ("质量", "红利质量"),
    ],
    "科技": [
        ("半导体", "半导体芯片"),
        ("芯片", "半导体芯片"),
        ("通信", "通信"),
        ("人工智能", "人工智能"),
        ("机器人", "人工智能"),
        ("智能", "人工智能"),
        ("软件", "软件计算机"),
        ("云计算", "软件计算机"),
        ("计算机", "软件计算机"),
        ("信息技术", "软件计算机"),
        ("消费电子", "电子"),
        ("电子", "电子"),
        ("互联网", "互联网科技"),
        ("恒生科技", "互联网科技"),
    ],
    "宽基": [
        ("科创", "科创板"),
        ("创业板", "创业板"),
        ("双创", "双创"),
        ("深证100", "深证100"),
        ("深100", "深证100"),
        ("A500", "中证A500"),
        ("A50", "中证A50"),
        ("1000", "中证1000"),
        ("500", "中证500"),
        ("300", "沪深300"),
        ("上证50", "上证50"),
        ("50", "上证50"),
        ("深100", "深证100"),
    ],
    "债券": [
        ("可转债", "可转债"),
        ("转债", "可转债"),
        ("科创债", "科创债"),
        ("科债", "科创债"),
        ("短融", "短融"),
        ("公司债", "信用债"),
        ("信用债", "信用债"),
        ("国债", "利率债"),
        ("政金", "利率债"),
        ("地债", "利率债"),
        ("国开", "利率债"),
        ("金融债", "利率债"),
    ],
}


def classify_subcategory(name: str, category: str) -> str:
    """在板块内进一步细分子类；无匹配或该板块无细分时回退为板块名。"""
    for needle, subcategory in _SUBCATEGORY_RULES.get(category, []):
        if needle in name:
            return subcategory
    if category == "红利":
        return "宽口径红利"
    return category


def infer_manager(name: str) -> str | None:
    managers = [
        "华泰柏瑞",
        "华夏",
        "易方达",
        "嘉实",
        "南方",
        "国泰",
        "富国",
        "广发",
        "银华",
        "天弘",
        "万家",
        "平安",
        "博时",
        "招商",
        "鹏华",
        "汇添富",
    ]
    for manager in managers:
        if manager in name:
            return manager
    return None


def fetch_spot(ak: Any, codes: set[str] | None, limit: int | None, options: FetchOptions) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cached_rows = load_cached_spot_rows(options.cache_dir, options.as_of)
    if cached_rows:
        source_rows = cached_rows
    else:
        source_rows = _records(_ensure_func(ak, "fund_etf_spot_em")())
        save_cached_spot_rows(options.cache_dir, options.as_of, source_rows)
    rows = _filter_codes(source_rows, codes, limit)
    master = _normalize_master_from_spot(rows)
    prices = []
    for row in rows:
        code = row["_code"]
        close = parse_number(pick(row, ["最新价", "收盘", "现价", "最新净值", "单位净值"]))
        previous_close = parse_number(pick(row, ["昨收", "前收盘", "previous_close"]))
        data_date = normalize_date(pick(row, ["数据日期", "日期", "date"]))
        if close is not None:
            prices.append({"code": code, "date": data_date, "close": close, "previous_close": previous_close})
    return master, prices


def spot_price_rows_for_as_of(spot_prices: Iterable[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    rows = []
    for item in spot_prices:
        code = item["code"]
        data_date = normalize_date(item.get("date"))
        latest_close = parse_number(item.get("close"))
        previous_close = parse_number(item.get("previous_close"))
        close = None
        if data_date == as_of:
            close = latest_close
        elif data_date is not None and data_date > as_of:
            close = previous_close
        if close is not None:
            rows.append({"code": code, "date": as_of, "close": close})
    return rows


def windows_for_set(name: str) -> list[dict[str, Any]]:
    if name == "full":
        return DEFAULT_WINDOWS
    if name == "short":
        wanted = {"1D", "1W", "2W", "1M"}
        return [item for item in DEFAULT_WINDOWS if item["key"] in wanted]
    raise FetchError(f"未知 window set: {name}")


def price_fetch_range(
    *,
    requested_start: date,
    requested_end: date,
    cached_start: date | None,
    cached_end: date | None,
) -> tuple[date, date] | None:
    if cached_start is not None and cached_end is not None and cached_start <= requested_start and cached_end >= requested_end:
        return None
    return requested_start, requested_end


def fetch_price_frame_with_retries(hist_func: Any, *, options: FetchOptions, code: str, start: date, end: date) -> Any:
    return call_with_retries(
        hist_func,
        label=f"{code} 历史价格",
        retries=options.price_retries,
        sleep_seconds=options.retry_sleep_seconds,
        timeout_seconds=options.source_timeout_seconds,
        symbol=code,
        period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="",
    )


def sina_symbol(code: str) -> str | None:
    exchange = detect_exchange(code)
    if exchange == "SSE":
        return f"sh{code}"
    if exchange == "SZSE":
        return f"sz{code}"
    return None


def fetch_price_frame_sina(ak: Any, *, options: FetchOptions, code: str) -> Any:
    """新浪历史行情兜底：东财限流时使用。一次返回全部历史，调用方按区间过滤。"""
    symbol = sina_symbol(code)
    if symbol is None:
        return None
    hist_func = getattr(ak, "fund_etf_hist_sina", None)
    if hist_func is None:
        return None
    return call_with_retries(
        hist_func,
        label=f"{code} 历史价格(新浪)",
        retries=options.price_retries,
        sleep_seconds=options.retry_sleep_seconds,
        timeout_seconds=options.source_timeout_seconds,
        symbol=symbol,
    )


def price_rows_from_frame(frame: Any, code: str, *, start: date, end: date) -> list[dict[str, Any]]:
    rows = []
    for row in _records(frame) if frame is not None else []:
        row_date = normalize_date(pick(row, ["日期", "date"]))
        close = parse_number(pick(row, ["收盘", "close", "最新价"]))
        if row_date is not None and close is not None and start <= row_date <= end:
            rows.append({"code": code, "date": row_date, "close": close})
    return rows


def fetch_price_history(ak: Any, master: list[dict[str, Any]], options: FetchOptions) -> list[dict[str, Any]]:
    hist_func = _ensure_func(ak, "fund_etf_hist_em")
    prices = []
    made_request = False
    for item in master:
        code = item["code"]
        cached_rows = load_cached_prices(options.cache_dir, code)
        cached_start, cached_end = cached_date_range(cached_rows)
        request_range = price_fetch_range(
            requested_start=options.start_date,
            requested_end=options.as_of,
            cached_start=cached_start,
            cached_end=cached_end,
        )
        fetched_rows = []
        if request_range is not None:
            start, end = request_range
            if made_request and options.price_pause_seconds > 0:
                sleep(options.price_pause_seconds)
            made_request = True
            frame = None
            primary_error: Exception | None = None
            try:
                frame = fetch_price_frame_with_retries(hist_func, options=options, code=code, start=start, end=end)
            except FetchError as exc:
                primary_error = exc
            fetched_rows = price_rows_from_frame(frame, code, start=start, end=end)
            if not fetched_rows and options.use_sina_fallback:
                # 东财限流按 IP 硬断连，新浪接口不受影响，作为兜底源。
                try:
                    sina_frame = fetch_price_frame_sina(ak, options=options, code=code)
                    fetched_rows = price_rows_from_frame(sina_frame, code, start=start, end=end)
                except FetchError as exc:
                    primary_error = primary_error or exc
            if not fetched_rows and primary_error is not None:
                # 增量抓取失败时退回缓存数据，避免丢掉已有历史。
                if options.strict:
                    raise primary_error
                options.source_errors.append(str(primary_error))
        merged_rows = merge_price_rows(cached_rows, fetched_rows)
        save_cached_prices(options.cache_dir, code, merged_rows)
        prices.extend(row for row in merged_rows if options.start_date <= row["date"] <= options.as_of)
    return prices


def fetch_sse_share_for_dates(ak: Any, target_dates: Iterable[date], options: FetchOptions | None = None) -> list[dict[str, Any]]:
    scale_func = _ensure_func(ak, "fund_etf_scale_sse")
    shares = []
    seen: set[tuple[str, date]] = set()
    retries = options.source_retries if options else 3
    sleep_seconds = options.retry_sleep_seconds if options else 1.0
    timeout_seconds = options.source_timeout_seconds if options else 15
    for target in sorted(set(target_dates)):
        frame_date = _find_sse_available_date(
            scale_func,
            target,
            retries=retries,
            sleep_seconds=sleep_seconds,
            timeout_seconds=timeout_seconds,
        )
        if frame_date is None:
            continue
        try:
            frame = call_with_retries(
                scale_func,
                label=f"SSE ETF 份额 {frame_date.isoformat()}",
                retries=retries,
                sleep_seconds=sleep_seconds,
                timeout_seconds=timeout_seconds,
                date=frame_date.strftime("%Y%m%d"),
            )
        except FetchError as exc:
            if options and options.strict:
                raise
            if options:
                options.source_errors.append(str(exc))
            continue
        for row in _records(frame):
            code = compact_code(pick(row, ["基金代码", "代码", "证券代码", "code"]))
            if detect_exchange(code) != "SSE":
                continue
            share_column = _find_share_column(row)
            row_date = normalize_date(pick(row, ["日期", "交易日期", "date"])) or frame_date
            share = normalize_share_to_yi(row.get(share_column), share_column)
            name = pick(row, ["基金简称", "基金名称", "名称", "name"])
            key = (code, row_date)
            if share is not None and key not in seen:
                shares.append({"code": code, "date": row_date, "shares_yi": share, "source": "SSE", "name": name})
                seen.add(key)
    return shares


def _find_sse_available_date(
    scale_func: Any,
    target: date,
    *,
    retries: int = 3,
    sleep_seconds: float = 1.0,
    timeout_seconds: int | None = 15,
) -> date | None:
    for offset in range(0, 10):
        candidate = target - timedelta(days=offset)
        try:
            frame = call_with_retries(
                scale_func,
                label=f"SSE ETF 份额 {candidate.isoformat()}",
                retries=retries,
                sleep_seconds=sleep_seconds,
                timeout_seconds=timeout_seconds,
                date=candidate.strftime("%Y%m%d"),
            )
            if _records(frame):
                return candidate
        except FetchError:
            continue
    return None


def fetch_szse_shares(ak: Any, start_date: date, end_date: date, options: FetchOptions | None = None) -> list[dict[str, Any]]:
    hist_func = _ensure_func(ak, "fund_scale_daily_szse")
    rows = _records(
        call_with_retries(
            hist_func,
            label=f"SZSE ETF 份额 {start_date.isoformat()}~{end_date.isoformat()}",
            retries=options.source_retries if options else 3,
            sleep_seconds=options.retry_sleep_seconds if options else 1.0,
            timeout_seconds=options.source_timeout_seconds if options else 15,
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
            symbol="ETF",
        )
    )
    shares = []
    for row in rows:
        code = compact_code(pick(row, ["基金代码", "代码", "证券代码", "code"]))
        if detect_exchange(code) != "SZSE":
            continue
        row_date = normalize_date(pick(row, ["日期", "交易日期", "date"]))
        share_column = _find_share_column(row)
        share = normalize_share_to_yi(row.get(share_column), share_column)
        name = pick(row, ["基金简称", "基金名称", "名称", "name"])
        if row_date is not None and share is not None:
            shares.append({"code": code, "date": row_date, "shares_yi": share, "source": "SZSE", "name": name})
    return shares


def date_probe_ranges(target_dates: Iterable[date], lookback_days: int = 10) -> list[tuple[date, date]]:
    return [(target - timedelta(days=lookback_days), target) for target in sorted(set(target_dates))]


def fetch_szse_share_for_dates(ak: Any, target_dates: Iterable[date], options: FetchOptions | None = None) -> list[dict[str, Any]]:
    shares = []
    for start_date, end_date in date_probe_ranges(target_dates):
        try:
            shares.extend(fetch_szse_shares(ak, start_date, end_date, options))
        except FetchError as exc:
            if options and options.strict:
                raise
            if options:
                options.source_errors.append(str(exc))
    return _dedupe_shares(shares)


def _find_share_column(row: dict[str, Any]) -> str:
    for key in row:
        text = str(key)
        if "份额" in text:
            return key
    for key in row:
        text = str(key)
        if "规模" in text:
            return key
    return next(iter(row))


def target_dates_for_windows(as_of: date, windows: list[dict[str, Any]] | None = None) -> list[date]:
    result = [as_of]
    for window in windows or DEFAULT_WINDOWS:
        if window.get("ytd"):
            result.append(date(as_of.year, 1, 1))
        else:
            result.append(as_of - timedelta(days=int(window["days"])))
    return result


def choose_effective_as_of(
    *,
    requested_as_of: date,
    price_dates: Iterable[date],
    share_dates: Iterable[date],
) -> date:
    latest_price_date = max((item for item in price_dates if item <= requested_as_of), default=None)
    if latest_price_date is None:
        raise FetchError("未获取到请求日期之前的 ETF 价格数据。")
    latest_share_date = max((item for item in share_dates if item <= latest_price_date), default=None)
    if latest_share_date is None:
        raise FetchError("未获取到价格日期之前的 ETF 份额数据。")
    return min(latest_price_date, latest_share_date)


def _dedupe_shares(shares: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, date], dict[str, Any]] = {}
    for item in shares:
        deduped[(item["code"], item["date"])] = item
    return list(deduped.values())


def fetch_snapshot(options: FetchOptions) -> dict[str, Any]:
    ak = _load_akshare()
    code_filter = {compact_code(code) for code in options.codes} if options.codes else None
    master, spot_prices = fetch_spot(ak, code_filter, options.limit, options)
    append_missing_code_masters(master, code_filter)
    if not master:
        raise FetchError("未获取到 ETF 列表。请检查网络、代码过滤条件或 AKShare 数据源。")

    prices = fetch_price_history(ak, master, options)
    price_dates = [item["date"] for item in prices if item["date"] <= options.as_of]
    initial_as_of = max(price_dates) if price_dates else options.as_of

    windows = options.windows or DEFAULT_WINDOWS
    dates = target_dates_for_windows(initial_as_of, windows)
    sse_shares = fetch_sse_share_for_dates(ak, dates, options)
    szse_shares = fetch_szse_share_for_dates(ak, dates, options)
    shares = [item for item in sse_shares + szse_shares if not code_filter or item["code"] in code_filter]
    as_of = choose_effective_as_of(
        requested_as_of=options.as_of,
        price_dates=price_dates or [options.as_of],
        share_dates=[item["date"] for item in shares],
    )
    prices = merge_price_rows(prices, spot_price_rows_for_as_of(spot_prices, as_of))
    if as_of != initial_as_of:
        adjusted_dates = target_dates_for_windows(as_of, windows)
        extra_sse_shares = fetch_sse_share_for_dates(ak, adjusted_dates, options)
        extra_szse_shares = fetch_szse_share_for_dates(ak, adjusted_dates, options)
        shares.extend([item for item in extra_sse_shares + extra_szse_shares if not code_filter or item["code"] in code_filter])
        shares = _dedupe_shares(shares)
    enrich_master_from_shares(master, shares)

    sources = [
        {"label": "AKShare 公募基金数据", "href": "https://akshare.akfamily.xyz/data/fund/fund_public.html"},
        {"label": "上交所 ETF 基金规模", "href": "https://www.sse.com.cn/assortment/fund/etf/list/scale/"},
        {"label": "深交所基金规模日频数据", "href": "http://www.szse.cn/market/fund/volume/etf/index.html"},
    ]
    return build_snapshot(
        master=master,
        prices=prices,
        shares=shares,
        as_of=as_of,
        sources=sources,
        source_errors=options.source_errors,
        windows=windows,
    )
