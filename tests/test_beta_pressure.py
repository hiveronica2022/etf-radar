from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from etf_radar.beta_pressure import (
    build_beta_pressure,
    normalize_holding_records,
    normalize_margin_rows,
    normalize_stock_market_rows,
    parse_holding_period,
    update_beta_history,
)


class BetaPressureTest(unittest.TestCase):
    def test_parse_holding_period_accepts_quarter_label(self):
        self.assertEqual(parse_holding_period("2026年1季度股票投资明细"), date(2026, 3, 31))
        self.assertEqual(parse_holding_period("2025 年 4 季度"), date(2025, 12, 31))

    def test_normalize_holding_records_converts_wan_units_and_merges_duplicates(self):
        rows = normalize_holding_records(
            [
                {"股票代码": "600000", "股票名称": "浦发银行", "持股数": 100, "持仓市值": 1000, "占净值比例": 2, "季度": "2026年1季度"},
                {"股票代码": "600000", "股票名称": "浦发银行", "持股数": 20, "持仓市值": 200, "占净值比例": 0.4, "季度": "2026年1季度"},
                {"股票代码": "00700", "股票名称": "腾讯控股", "持股数": 10, "持仓市值": 500, "占净值比例": 1, "季度": "2026年1季度"},
            ],
            "510300",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["holding_shares"], 1_200_000)
        self.assertEqual(rows[0]["market_value_yuan"], 12_000_000)
        self.assertAlmostEqual(rows[0]["weight_pct"], 2.4)

    def test_market_and_margin_normalization_preserves_units(self):
        market = normalize_stock_market_rows(
            [{"code": "600000", "name": "浦发银行", "trade": "10", "nmc": 500_000}],
            source="Sina",
        )
        margins = normalize_margin_rows(
            [{"标的证券代码": "600000", "融资余额": 1_000_000_000, "融券余量": 1_000_000}],
            [],
            market,
        )

        self.assertEqual(market[0]["float_market_value_yuan"], 5_000_000_000)
        self.assertEqual(market[0]["float_shares"], 500_000_000)
        self.assertEqual(margins[0]["short_balance_yuan"], 10_000_000)

    def test_build_beta_pressure_estimates_position_and_daily_flow(self):
        as_of = date(2026, 7, 13)
        holdings = normalize_holding_records(
            [
                {
                    "股票代码": "600000",
                    "股票名称": "浦发银行",
                    "持股数": 10_000,
                    "持仓市值": 100_000,
                    "占净值比例": 10,
                    "季度": "2026年1季度股票投资明细",
                }
            ],
            "510300",
        )
        market = normalize_stock_market_rows(
            [{"代码": "600000", "名称": "浦发银行", "最新价": 10, "流通市值": 50_000_000_000}],
            source="Eastmoney",
        )
        margins = normalize_margin_rows(
            [{"标的证券代码": "600000", "融资余额": 1_000_000_000, "融券余量": 1_000_000}],
            [],
            market,
        )
        result = build_beta_pressure(
            master=[{"code": "510300", "name": "沪深300ETF", "category": "宽基"}],
            prices=[{"code": "510300", "date": as_of, "close": 4}],
            shares=[
                {"code": "510300", "date": date(2026, 7, 10), "shares_yi": 99},
                {"code": "510300", "date": as_of, "shares_yi": 100},
            ],
            holdings=holdings,
            stock_market=market,
            margins=margins,
            as_of=as_of,
        )

        row = result["rows"][0]
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["holding_as_of"], "2026-03-31")
        self.assertEqual(row["linked_etf_count"], 1)
        self.assertAlmostEqual(row["penetrated_holding_yi_shares"], 4)
        self.assertAlmostEqual(row["today_change_wan_shares"], 400)
        self.assertAlmostEqual(row["change_amount_100m"], 0.4)
        self.assertAlmostEqual(row["margin_balance_100m"], 10)
        self.assertAlmostEqual(row["short_balance_100m"], 0.1)
        self.assertAlmostEqual(row["float_shares_100m"], 50)
        self.assertAlmostEqual(row["float_market_value_100m"], 500)

    def test_update_beta_history_replaces_same_date_and_keeps_dates_sorted(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            first = {
                "as_of": "2026-07-12",
                "holding_as_of": "2026-03-31",
                "rows": [{"code": "600000", "today_change_wan_shares": 10, "change_amount_100m": 0.1}],
            }
            second = {
                "as_of": "2026-07-13",
                "holding_as_of": "2026-03-31",
                "rows": [{"code": "600000", "today_change_wan_shares": 20, "change_amount_100m": 0.2}],
            }
            update_beta_history(cache_dir, second)
            history = update_beta_history(cache_dir, first)
            history = update_beta_history(cache_dir, {**second, "rows": [{"code": "600000", "today_change_wan_shares": 25}]})

        self.assertEqual([item["date"] for item in history], ["2026-07-12", "2026-07-13"])
        self.assertEqual(history[-1]["rows"][0]["today_change_wan_shares"], 25)


if __name__ == "__main__":
    unittest.main()
