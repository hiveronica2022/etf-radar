from __future__ import annotations

from datetime import date

from .metrics import build_snapshot


def sample_snapshot() -> dict:
    as_of = date(2026, 6, 24)
    master = [
        {"code": "510300", "name": "沪深300ETF华泰柏瑞", "exchange": "SSE", "category": "宽基", "manager": "华泰柏瑞"},
        {"code": "510330", "name": "沪深300ETF华夏", "exchange": "SSE", "category": "宽基", "manager": "华夏"},
        {"code": "159915", "name": "创业板ETF易方达", "exchange": "SZSE", "category": "宽基", "manager": "易方达"},
        {"code": "159600", "name": "科创债ETF嘉实", "exchange": "SZSE", "category": "债券", "manager": "嘉实"},
        {"code": "159516", "name": "半导体设备ETF国泰", "exchange": "SZSE", "category": "科技", "manager": "国泰"},
        {"code": "518880", "name": "黄金ETF华安", "exchange": "SSE", "category": "商品", "manager": "华安"},
        {"code": "512880", "name": "证券ETF国泰", "exchange": "SSE", "category": "金融", "manager": "国泰"},
        {"code": "515880", "name": "通信ETF国泰", "exchange": "SSE", "category": "科技", "manager": "国泰"},
    ]
    prices = []
    shares = []
    rows = {
        "510300": {"price": [4.00, 4.10, 4.24, 4.35, 4.40], "share": [100, 101, 102, 104, 106]},
        "510330": {"price": [4.05, 4.12, 4.25, 4.32, 4.36], "share": [80, 82, 83, 84, 85]},
        "159915": {"price": [2.30, 2.18, 2.08, 2.02, 1.98], "share": [60, 59, 57, 55, 53]},
        "159600": {"price": [1.02, 1.02, 1.02, 1.03, 1.03], "share": [200, 205, 210, 218, 225]},
        "159516": {"price": [0.76, 0.86, 0.92, 0.89, 0.84], "share": [30, 34, 40, 44, 48]},
        "518880": {"price": [5.10, 5.35, 5.28, 5.22, 5.18], "share": [120, 122, 124, 121, 119]},
        "512880": {"price": [1.03, 1.01, 1.00, 1.00, 0.98], "share": [300, 296, 292, 288, 284]},
        "515880": {"price": [1.28, 1.32, 1.38, 1.42, 1.46], "share": [75, 79, 84, 89, 92]},
    }
    dates = [date(2026, 1, 2), date(2026, 3, 24), date(2026, 6, 17), date(2026, 6, 22), as_of]
    for code, series in rows.items():
        for row_date, close, share in zip(dates, series["price"], series["share"], strict=True):
            prices.append({"code": code, "date": row_date, "close": close})
            shares.append({"code": code, "date": row_date, "shares_yi": share})

    snapshot = build_snapshot(
        master=master,
        prices=prices,
        shares=shares,
        as_of=as_of,
        generated_at="2026-06-25T10:00:00+08:00",
        status="fixture",
        beta_pressure={
            "status": "fixture",
            "as_of": as_of.isoformat(),
            "holding_as_of": "2026-03-31",
            "share_as_of": as_of.isoformat(),
            "market_as_of": as_of.isoformat(),
            "source_mode": "periodic_report_estimate",
            "method_label": "定期报告持仓 × ETF 份额变化估算",
            "summary": {
                "stock_count": 3,
                "linked_etf_count": 9,
                "net_position_change_yi_shares": 0.18,
                "margin_balance_100m": 128.5,
                "data_status": "示例数据",
            },
            "coverage": {
                "eligible_etf_count": 5,
                "holding_etf_count": 5,
                "holding_etf_pct": 100.0,
                "market_stock_count": 3,
                "market_stock_pct": 100.0,
                "margin_stock_count": 3,
                "margin_data_available": True,
            },
            "rows": [
                {
                    "code": "300308",
                    "name": "中际旭创",
                    "industry": "通信",
                    "linked_etf_count": 4,
                    "penetrated_holding_yi_shares": 0.83,
                    "today_change_wan_shares": 264.0,
                    "change_amount_100m": 2.26,
                    "margin_balance_100m": 44.4,
                    "short_balance_100m": 1.2,
                    "float_shares_100m": 11.10,
                    "float_market_value_100m": 1229.8,
                    "etf_increase_wan_shares": 213.0,
                    "etf_decrease_wan_shares": -9.3,
                },
                {
                    "code": "688008",
                    "name": "澜起科技",
                    "industry": "半导体",
                    "linked_etf_count": 3,
                    "penetrated_holding_yi_shares": 0.19,
                    "today_change_wan_shares": 96.0,
                    "change_amount_100m": 0.75,
                    "margin_balance_100m": 17.7,
                    "short_balance_100m": 0.5,
                    "float_shares_100m": 11.45,
                    "float_market_value_100m": 289.4,
                    "etf_increase_wan_shares": 82.0,
                    "etf_decrease_wan_shares": -4.1,
                },
                {
                    "code": "600989",
                    "name": "宝丰能源",
                    "industry": "化工",
                    "linked_etf_count": 2,
                    "penetrated_holding_yi_shares": 0.75,
                    "today_change_wan_shares": -28.2,
                    "change_amount_100m": -0.36,
                    "margin_balance_100m": 21.2,
                    "short_balance_100m": 0.1,
                    "float_shares_100m": 73.33,
                    "float_market_value_100m": 1125.0,
                    "etf_increase_wan_shares": 0.7,
                    "etf_decrease_wan_shares": -20.5,
                },
            ],
            "history": [],
        },
        sources=[
            {"label": "示例数据", "href": ""},
            {"label": "AKShare 公募基金数据", "href": "https://akshare.akfamily.xyz/data/fund/fund_public.html"},
            {"label": "上交所 ETF 基金规模", "href": "https://www.sse.com.cn/assortment/fund/etf/list/scale/"},
            {"label": "深交所基金规模日频数据", "href": "http://www.szse.cn/market/fund/volume/etf/index.html"},
        ],
    )
    snapshot["meta"]["note"] = "这是用于本地看板预览的示例数据；运行 fetch 命令后会替换为公开数据快照。"
    return snapshot
