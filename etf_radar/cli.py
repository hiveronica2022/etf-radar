from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path
from time import sleep
from typing import Any

from .akshare_fetcher import FetchError, FetchOptions, fetch_snapshot, windows_for_set
from .metrics import missing_data_codes
from .presets import resolve_codes
from .sample_data import sample_snapshot
from .static_builder import build_pages_site, build_static_html


def write_json(data: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def strip_proxy_env() -> None:
    for key in [name for name in os.environ if "proxy" in name.lower()]:
        os.environ.pop(key)
    os.environ["NO_PROXY"] = "*"


def add_fetch_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", type=Path, default=Path("data/dashboard_snapshot.json"))
    parser.add_argument("--as-of", type=lambda text: date.fromisoformat(text), default=None)
    parser.add_argument("--lookback-days", type=int, default=380)
    parser.add_argument("--codes", nargs="*", help="只抓取指定 ETF 代码，便于调试")
    parser.add_argument("--preset", action="append", help="使用内置 ETF 观察池，例如 core、bond；可重复传入")
    parser.add_argument("--limit", type=int, help="限制 ETF 数量，便于调试")
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"), help="价格历史缓存目录，默认 cache")
    parser.add_argument("--no-cache", action="store_true", help="禁用价格历史缓存")
    parser.add_argument("--retries", type=int, default=3, help="公开数据源失败重试次数，默认 3")
    parser.add_argument("--retry-sleep", type=float, default=1.0, help="重试间隔秒数，默认 1.0")
    parser.add_argument("--source-timeout", type=int, default=15, help="单次公开数据源调用超时秒数，默认 15")
    parser.add_argument("--strict", action="store_true", help="任一 ETF 数据源失败时直接中止")
    parser.add_argument("--no-proxy", action="store_true", help="忽略系统代理环境变量，直连公开数据源")
    parser.add_argument("--price-pause", type=float, default=0.35, help="逐只请求历史价格的间隔秒数，缓解限流，默认 0.35")
    parser.add_argument("--no-sina-fallback", action="store_true", help="禁用新浪历史行情兜底（默认东财失败时启用）")
    parser.add_argument("--window-set", choices=["full", "short"], default="full", help="窗口集合：full=默认全窗口，short=1D/1W/2W/1M")
    parser.add_argument("--no-beta-pressure", action="store_true", help="跳过 ETF 持仓穿透、个股两融与流通盘数据")
    parser.add_argument("--beta-top-stocks", type=int, default=120, help="β 压强最多输出个股数，默认 120")


def fetch_options_from_args(args: argparse.Namespace) -> FetchOptions:
    as_of = args.as_of or date.today()
    return FetchOptions(
        as_of=as_of,
        start_date=as_of - timedelta(days=args.lookback_days),
        codes=resolve_codes(args.preset, args.codes),
        limit=args.limit,
        cache_dir=None if args.no_cache else args.cache_dir,
        price_retries=args.retries,
        source_retries=args.retries,
        retry_sleep_seconds=args.retry_sleep,
        source_timeout_seconds=args.source_timeout,
        price_pause_seconds=args.price_pause,
        use_sina_fallback=not args.no_sina_fallback,
        strict=args.strict,
        windows=windows_for_set(args.window_set),
        include_beta_pressure=not args.no_beta_pressure,
        beta_top_stocks=max(args.beta_top_stocks, 1),
    )


def fetch_until_complete(
    args: argparse.Namespace,
    *,
    max_passes: int,
    pass_sleep_seconds: float,
    fetch_fn: Any = fetch_snapshot,
) -> dict[str, Any]:
    """多轮抓取直到数据补齐。价格缓存让每一轮只补缺失部分，公开源限流时多跑几轮即可收敛。"""
    snapshot: dict[str, Any] | None = None
    for attempt in range(1, max_passes + 1):
        snapshot = fetch_fn(fetch_options_from_args(args))
        missing = missing_data_codes(snapshot)
        print(f"pass {attempt}/{max_passes}: {len(snapshot['rows'])} rows, missing {len(missing)}")
        if not missing:
            break
        if attempt < max_passes:
            print(f"  missing codes: {' '.join(missing)}")
            if pass_sleep_seconds > 0:
                sleep(pass_sleep_seconds)
    assert snapshot is not None
    return snapshot


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ETF 份额雷达数据管线")
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("sample", help="生成本地预览用示例 snapshot")
    sample.add_argument("--out", type=Path, default=Path("data/dashboard_snapshot.json"))

    fetch = sub.add_parser("fetch", help="通过 AKShare 拉取公开 ETF 数据并生成 snapshot")
    add_fetch_arguments(fetch)

    html = sub.add_parser("build-html", help="把 snapshot 和前端资产打包成单文件 HTML")
    html.add_argument("--snapshot", type=Path, default=Path("data/dashboard_snapshot.json"))
    html.add_argument("--out", type=Path, default=Path("dist/etf-radar.html"))

    pages = sub.add_parser("build-pages", help="组装 GitHub Pages 静态站点目录")
    pages.add_argument("--snapshot", type=Path, default=Path("data/dashboard_snapshot.json"))
    pages.add_argument("--out", type=Path, default=Path("docs"))

    refresh = sub.add_parser("refresh", help="多轮抓取直到数据补齐，并重建单文件 HTML，适合定时任务")
    add_fetch_arguments(refresh)
    refresh.add_argument("--max-passes", type=int, default=3, help="最多抓取轮数，默认 3")
    refresh.add_argument("--pass-sleep", type=float, default=20.0, help="两轮之间的等待秒数，默认 20")
    refresh.add_argument("--html-out", type=Path, default=Path("dist/etf-radar.html"))
    refresh.add_argument("--pages-out", type=Path, default=None, help="同时组装 Pages 站点到该目录，例如 docs")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "sample":
            write_json(sample_snapshot(), args.out)
            print(f"wrote {args.out}")
            return 0
        if args.command == "fetch":
            if args.no_proxy:
                strip_proxy_env()
            snapshot = fetch_snapshot(fetch_options_from_args(args))
            write_json(snapshot, args.out)
            print(f"wrote {args.out}")
            return 0
        if args.command == "build-html":
            build_static_html(args.snapshot, args.out)
            print(f"wrote {args.out}")
            return 0
        if args.command == "build-pages":
            build_pages_site(args.snapshot, args.out)
            print(f"wrote {args.out}/")
            return 0
        if args.command == "refresh":
            if args.no_proxy:
                strip_proxy_env()
            snapshot = fetch_until_complete(args, max_passes=args.max_passes, pass_sleep_seconds=args.pass_sleep)
            write_json(snapshot, args.out)
            print(f"wrote {args.out}")
            build_static_html(args.out, args.html_out)
            print(f"wrote {args.html_out}")
            if args.pages_out is not None:
                build_pages_site(args.out, args.pages_out)
                print(f"wrote {args.pages_out}/")
            missing = missing_data_codes(snapshot)
            if missing:
                print(f"warning: still missing data for {' '.join(missing)}")
            return 0
    except FetchError as exc:
        print(f"fetch failed: {exc}")
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
