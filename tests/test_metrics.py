from datetime import date
import unittest

from etf_radar.metrics import (
    adjust_close_for_splits,
    build_snapshot,
    classify_flow_tag,
    nearest_on_or_before,
)


class MetricsTest(unittest.TestCase):
    def test_nearest_on_or_before_uses_last_available_trade_day(self):
        dates = [date(2026, 6, 19), date(2026, 6, 22), date(2026, 6, 24)]

        self.assertEqual(nearest_on_or_before(dates, date(2026, 6, 23)), date(2026, 6, 22))
        self.assertEqual(nearest_on_or_before(dates, date(2026, 6, 24)), date(2026, 6, 24))
        self.assertIsNone(nearest_on_or_before(dates, date(2026, 6, 18)))

    def test_classify_flow_tag_covers_direction_and_price_cases(self):
        self.assertEqual(classify_flow_tag(10, 0.05), "追高")
        self.assertEqual(classify_flow_tag(10, -0.03), "抄底")
        self.assertEqual(classify_flow_tag(-10, -0.03), "撤退")
        self.assertEqual(classify_flow_tag(-10, 0.05), "止盈")
        self.assertEqual(classify_flow_tag(10, -0.03, longer_return_pct=0.12), "追高吃套")
        self.assertIsNone(classify_flow_tag(0, 0.05))

    def test_build_snapshot_computes_windows_summary_and_missing_values(self):
        master = [
            {
                "code": "510300",
                "name": "沪深300ETF华泰柏瑞",
                "exchange": "SSE",
                "category": "宽基",
                "manager": "华泰柏瑞",
            },
            {
                "code": "159915",
                "name": "创业板ETF易方达",
                "exchange": "SZSE",
                "category": "科技",
                "manager": "易方达",
            },
        ]
        prices = [
            {"code": "510300", "date": date(2026, 6, 17), "close": 4.0},
            {"code": "510300", "date": date(2026, 6, 22), "close": 4.2},
            {"code": "510300", "date": date(2026, 6, 24), "close": 4.4},
            {"code": "159915", "date": date(2026, 6, 17), "close": 2.0},
            {"code": "159915", "date": date(2026, 6, 24), "close": 1.8},
        ]
        shares = [
            {"code": "510300", "date": date(2026, 6, 17), "shares_yi": 100.0},
            {"code": "510300", "date": date(2026, 6, 22), "shares_yi": 101.0},
            {"code": "510300", "date": date(2026, 6, 24), "shares_yi": 103.0},
            {"code": "159915", "date": date(2026, 6, 17), "shares_yi": 50.0},
            {"code": "159915", "date": date(2026, 6, 24), "shares_yi": 45.0},
        ]

        snapshot = build_snapshot(
            master=master,
            prices=prices,
            shares=shares,
            as_of=date(2026, 6, 24),
            generated_at="2026-06-25T10:00:00+08:00",
            windows=[
                {"key": "1D", "label": "最近1日", "days": 1},
                {"key": "1W", "label": "最近1周", "days": 7},
                {"key": "3M", "label": "最近3月", "days": 90},
            ],
        )

        self.assertEqual(snapshot["meta"]["status"], "ready")
        self.assertEqual(snapshot["meta"]["stale_after_trading_days"], 3)
        self.assertEqual(snapshot["summary"]["etf_count"], 2)
        self.assertAlmostEqual(snapshot["summary"]["total_scale_100m"], 534.2)
        self.assertAlmostEqual(snapshot["summary"]["flow_1w_100m"], 4.2)
        self.assertEqual(snapshot["rotation"]["grouping"], "category")
        rotation_1w = snapshot["rotation"]["windows"]["1W"]
        self.assertAlmostEqual(rotation_1w["inflow_total_100m"], 13.2)
        self.assertAlmostEqual(rotation_1w["outflow_total_100m"], -9.0)
        self.assertAlmostEqual(rotation_1w["net_flow_100m"], 4.2)
        self.assertEqual(rotation_1w["largest_destination"], "宽基")
        self.assertEqual(snapshot["beta_pressure"]["status"], "unavailable")
        self.assertEqual(snapshot["beta_pressure"]["rows"], [])

        first = snapshot["rows"][0]
        self.assertEqual(first["code"], "510300")
        self.assertEqual(first["tag"], "追高")
        self.assertAlmostEqual(first["scale_100m"], 453.2)
        self.assertAlmostEqual(first["windows"]["1D"]["share_delta_yi"], 2.0)
        self.assertAlmostEqual(first["windows"]["1D"]["amount_delta_100m"], 8.8)
        self.assertAlmostEqual(first["windows"]["1D"]["return_pct"], (4.4 / 4.2 - 1) * 100, places=2)

        second = snapshot["rows"][1]
        self.assertEqual(second["tag"], "撤退")
        self.assertAlmostEqual(second["windows"]["1W"]["amount_delta_100m"], -9.0)
        self.assertAlmostEqual(second["windows"]["1W"]["return_pct"], -10.0)

        missing = second["windows"]["1D"]
        self.assertIsNone(missing["share_delta_yi"])
        self.assertIsNone(missing["amount_delta_100m"])
        self.assertIsNone(missing["rank"])

    def test_build_snapshot_keeps_flow_amount_when_anchor_price_is_missing(self):
        snapshot = build_snapshot(
            master=[{"code": "510300", "name": "沪深300ETF华泰柏瑞"}],
            prices=[{"code": "510300", "date": date(2026, 6, 24), "close": 4.4}],
            shares=[
                {"code": "510300", "date": date(2026, 6, 17), "shares_yi": 100.0},
                {"code": "510300", "date": date(2026, 6, 24), "shares_yi": 103.0},
            ],
            as_of=date(2026, 6, 24),
            windows=[{"key": "1W", "label": "最近1周", "days": 7}],
        )

        metric = snapshot["rows"][0]["windows"]["1W"]
        self.assertAlmostEqual(metric["share_delta_yi"], 3.0)
        self.assertAlmostEqual(metric["amount_delta_100m"], 13.2)
        self.assertIsNone(metric["return_pct"])

    def test_adjust_close_for_splits_neutralizes_share_conversion(self):
        # 1:2 折算：价格从 3.0 跳到 1.5，复权后收益率应连续。
        closes = {
            date(2026, 7, 3): 3.0,
            date(2026, 7, 6): 3.01,
            date(2026, 7, 7): 1.5,
            date(2026, 7, 8): 1.53,
        }
        adjusted = adjust_close_for_splits(closes)

        # 折算前价格不变
        self.assertAlmostEqual(adjusted[date(2026, 7, 6)], 3.01, places=4)
        # 折算日抹平：复权价与折算前一日连续（3.01），当日真实涨跌≈0
        self.assertAlmostEqual(adjusted[date(2026, 7, 7)], 3.01, places=2)
        # 折算后的真实涨幅保留：1.53/1.5 - 1 = 2%
        self.assertAlmostEqual(adjusted[date(2026, 7, 8)] / adjusted[date(2026, 7, 7)] - 1, 0.02, places=4)

    def test_adjust_close_for_splits_keeps_normal_moves(self):
        closes = {date(2026, 7, 3): 1.0, date(2026, 7, 4): 1.1, date(2026, 7, 5): 0.95}
        self.assertEqual(adjust_close_for_splits(closes), closes)

    def test_build_snapshot_uses_split_adjusted_return_but_raw_scale(self):
        snapshot = build_snapshot(
            master=[{"code": "159995", "name": "芯片ETF华夏", "category": "科技"}],
            prices=[
                {"code": "159995", "date": date(2026, 7, 6), "close": 3.0},
                {"code": "159995", "date": date(2026, 7, 7), "close": 1.5},
            ],
            shares=[
                {"code": "159995", "date": date(2026, 7, 6), "shares_yi": 100.0},
                {"code": "159995", "date": date(2026, 7, 7), "shares_yi": 200.0},
            ],
            as_of=date(2026, 7, 7),
            windows=[{"key": "1D", "label": "最近1日", "days": 1}],
        )
        row = snapshot["rows"][0]
        # 规模用原始价：200 亿份 × 1.5 元 = 300
        self.assertAlmostEqual(row["scale_100m"], 300.0)
        self.assertAlmostEqual(row["latest_price"], 1.5)
        # 涨跌幅复权后接近 0，而不是 -50%
        self.assertAlmostEqual(row["windows"]["1D"]["return_pct"], 0.0, places=1)

    def test_build_snapshot_emits_price_trends_trimmed_at_as_of(self):
        snapshot = build_snapshot(
            master=[
                {"code": "510300", "name": "沪深300ETF华泰柏瑞"},
                {"code": "511260", "name": "十年国债ETF"},
            ],
            prices=[
                {"code": "510300", "date": date(2026, 6, 22), "close": 4.2},
                {"code": "510300", "date": date(2026, 6, 24), "close": 4.4},
                {"code": "510300", "date": date(2026, 6, 25), "close": 4.5},
                {"code": "511260", "date": date(2026, 6, 24), "close": 134.5},
            ],
            shares=[
                {"code": "510300", "date": date(2026, 6, 24), "shares_yi": 103.0},
                {"code": "511260", "date": date(2026, 6, 24), "shares_yi": 1.4},
            ],
            as_of=date(2026, 6, 24),
            windows=[{"key": "1D", "label": "最近1日", "days": 1}],
        )

        trends = {item["code"]: item for item in snapshot["trends"]}
        # 6/25 晚于 as_of，应被裁掉；511260 只有 1 个点，不产生 trend
        self.assertEqual(trends["510300"]["dates"], ["2026-06-22", "2026-06-24"])
        self.assertEqual(trends["510300"]["closes"], [4.2, 4.4])
        self.assertNotIn("511260", trends)

    def test_build_snapshot_accepts_beta_pressure_payload(self):
        beta_pressure = {
            "status": "ready",
            "as_of": "2026-06-24",
            "holding_as_of": "2026-03-31",
            "share_as_of": "2026-06-24",
            "summary": {"stock_count": 1, "linked_etf_count": 2},
            "rows": [{"code": "300308", "name": "中际旭创", "linked_etf_count": 2}],
            "history": [],
        }
        snapshot = build_snapshot(
            master=[{"code": "510300", "name": "沪深300ETF华泰柏瑞"}],
            prices=[{"code": "510300", "date": date(2026, 6, 24), "close": 4.4}],
            shares=[{"code": "510300", "date": date(2026, 6, 24), "shares_yi": 103.0}],
            as_of=date(2026, 6, 24),
            windows=[{"key": "1D", "label": "最近1日", "days": 1}],
            beta_pressure=beta_pressure,
        )

        self.assertEqual(snapshot["beta_pressure"], beta_pressure)


if __name__ == "__main__":
    unittest.main()
