from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from etf_radar.akshare_fetcher import (
    append_missing_code_masters,
    call_with_retries,
    choose_effective_as_of,
    classify_category,
    classify_subcategory,
    date_probe_ranges,
    enrich_master_from_shares,
    fetch_beta_holdings,
    fetch_price_history,
    FetchOptions,
    price_fetch_range,
    sina_symbol,
    spot_price_rows_for_as_of,
    windows_for_set,
)
from etf_radar.price_cache import save_cached_prices


class FetcherTest(unittest.TestCase):
    def test_empty_beta_holdings_are_cached(self):
        class FakeAk:
            def __init__(self):
                self.calls = 0

            def fund_portfolio_hold_em(self, **kwargs):
                self.calls += 1
                return []

        with TemporaryDirectory() as tmp:
            fake = FakeAk()
            options = FetchOptions(
                as_of=date(2026, 7, 14),
                start_date=date(2026, 1, 1),
                cache_dir=Path(tmp),
                source_retries=1,
                retry_sleep_seconds=0,
            )
            master = [{"code": "513530", "name": "港股通红利ETF", "category": "红利"}]
            self.assertEqual(fetch_beta_holdings(fake, master, options, options.as_of), [])
            self.assertEqual(fake.calls, 2)
            self.assertEqual(fetch_beta_holdings(fake, master, options, options.as_of), [])

        self.assertEqual(fake.calls, 2)

    def test_choose_effective_as_of_uses_latest_common_complete_share_date(self):
        self.assertEqual(
            choose_effective_as_of(
                requested_as_of=date(2026, 6, 25),
                price_dates=[date(2026, 6, 24), date(2026, 6, 25)],
                share_dates=[date(2026, 6, 24)],
            ),
            date(2026, 6, 24),
        )

    def test_choose_effective_as_of_ignores_future_share_dates(self):
        self.assertEqual(
            choose_effective_as_of(
                requested_as_of=date(2026, 6, 24),
                price_dates=[date(2026, 6, 24)],
                share_dates=[date(2026, 6, 24), date(2026, 6, 25)],
            ),
            date(2026, 6, 24),
        )

    def test_date_probe_ranges_keep_exchange_queries_bounded(self):
        self.assertEqual(
            date_probe_ranges([date(2026, 6, 24), date(2026, 6, 17)], lookback_days=3),
            [
                (date(2026, 6, 14), date(2026, 6, 17)),
                (date(2026, 6, 21), date(2026, 6, 24)),
            ],
        )

    def test_append_missing_code_masters_preserves_explicit_code_requests(self):
        master = [{"code": "510300", "name": "沪深300ETF华泰柏瑞"}]

        append_missing_code_masters(master, {"510300", "159600"})

        self.assertEqual([item["code"] for item in master], ["510300", "159600"])
        self.assertEqual(master[1]["exchange"], "SZSE")
        self.assertEqual(master[1]["name"], "159600")

    def test_enrich_master_from_shares_backfills_placeholder_names(self):
        master = [{"code": "159600", "name": "159600", "category": "未分类", "manager": None}]
        shares = [{"code": "159600", "name": "科创债ETF嘉实"}]

        enrich_master_from_shares(master, shares)

        self.assertEqual(master[0]["name"], "科创债ETF嘉实")
        self.assertEqual(master[0]["category"], "债券")
        self.assertEqual(master[0]["manager"], "嘉实")

    def test_price_fetch_range_skips_network_when_cache_covers_request(self):
        self.assertIsNone(
            price_fetch_range(
                requested_start=date(2026, 1, 1),
                requested_end=date(2026, 6, 25),
                cached_start=date(2025, 12, 31),
                cached_end=date(2026, 6, 25),
            )
        )

    def test_price_fetch_range_fetches_full_request_when_cache_has_gap(self):
        self.assertEqual(
            price_fetch_range(
                requested_start=date(2026, 1, 1),
                requested_end=date(2026, 6, 25),
                cached_start=date(2026, 1, 2),
                cached_end=date(2026, 6, 24),
            ),
            (date(2026, 1, 1), date(2026, 6, 25)),
        )

    def test_fetch_price_history_retries_transient_failures(self):
        class FakeAk:
            def __init__(self):
                self.calls = 0

            def fund_etf_hist_em(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise OSError("temporary ssl eof")
                return [{"日期": "2026-06-24", "收盘": "4.967"}]

        with TemporaryDirectory() as tmp:
            fake = FakeAk()
            rows = fetch_price_history(
                fake,
                [{"code": "510300"}],
                FetchOptions(
                    as_of=date(2026, 6, 24),
                    start_date=date(2026, 6, 1),
                    cache_dir=Path(tmp),
                    price_retries=2,
                    retry_sleep_seconds=0,
                ),
            )

        self.assertEqual(fake.calls, 2)
        self.assertEqual(rows, [{"code": "510300", "date": date(2026, 6, 24), "close": 4.967}])

    def test_fetch_price_history_continues_after_one_code_failure_by_default(self):
        class FakeAk:
            def fund_etf_hist_em(self, **kwargs):
                if kwargs["symbol"] == "159995":
                    raise OSError("temporary proxy failure")
                return [{"日期": "2026-06-24", "收盘": "4.967"}]

        rows = fetch_price_history(
            FakeAk(),
            [{"code": "159995"}, {"code": "510300"}],
            FetchOptions(
                as_of=date(2026, 6, 24),
                start_date=date(2026, 6, 1),
                cache_dir=None,
                price_retries=1,
                retry_sleep_seconds=0,
            ),
        )

        self.assertEqual(rows, [{"code": "510300", "date": date(2026, 6, 24), "close": 4.967}])

    def test_fetch_price_history_falls_back_to_cache_when_incremental_fetch_fails(self):
        class FakeAk:
            def fund_etf_hist_em(self, **kwargs):
                raise OSError("temporary throttling")

        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            save_cached_prices(cache_dir, "511260", [{"code": "511260", "date": date(2026, 6, 20), "close": 134.5}])
            options = FetchOptions(
                as_of=date(2026, 6, 24),
                start_date=date(2026, 6, 1),
                cache_dir=cache_dir,
                price_retries=1,
                retry_sleep_seconds=0,
                price_pause_seconds=0,
            )
            rows = fetch_price_history(FakeAk(), [{"code": "511260"}], options)

        self.assertEqual(rows, [{"code": "511260", "date": date(2026, 6, 20), "close": 134.5}])
        self.assertEqual(len(options.source_errors), 1)

    def test_fetch_price_history_uses_sina_fallback_when_eastmoney_fails(self):
        class FakeAk:
            def fund_etf_hist_em(self, **kwargs):
                raise OSError("eastmoney throttled")

            def fund_etf_hist_sina(self, symbol):
                # 新浪一次返回全历史，含区间外的日期，应被过滤掉。
                assert symbol == "sh511260"
                return [
                    {"date": date(2026, 5, 1), "close": 130.0},
                    {"date": date(2026, 6, 20), "close": 134.5},
                    {"date": date(2026, 6, 24), "close": 135.0},
                ]

        options = FetchOptions(
            as_of=date(2026, 6, 24),
            start_date=date(2026, 6, 1),
            cache_dir=None,
            price_retries=1,
            retry_sleep_seconds=0,
            price_pause_seconds=0,
        )
        rows = fetch_price_history(FakeAk(), [{"code": "511260"}], options)

        self.assertEqual(
            rows,
            [
                {"code": "511260", "date": date(2026, 6, 20), "close": 134.5},
                {"code": "511260", "date": date(2026, 6, 24), "close": 135.0},
            ],
        )
        self.assertEqual(options.source_errors, [])

    def test_fetch_price_history_skips_sina_fallback_when_disabled(self):
        class FakeAk:
            def __init__(self):
                self.sina_calls = 0

            def fund_etf_hist_em(self, **kwargs):
                raise OSError("eastmoney throttled")

            def fund_etf_hist_sina(self, symbol):
                self.sina_calls += 1
                return [{"date": date(2026, 6, 24), "close": 135.0}]

        fake = FakeAk()
        options = FetchOptions(
            as_of=date(2026, 6, 24),
            start_date=date(2026, 6, 1),
            cache_dir=None,
            price_retries=1,
            retry_sleep_seconds=0,
            price_pause_seconds=0,
            use_sina_fallback=False,
        )
        rows = fetch_price_history(fake, [{"code": "511260"}], options)

        self.assertEqual(rows, [])
        self.assertEqual(fake.sina_calls, 0)
        self.assertEqual(len(options.source_errors), 1)

    def test_sina_symbol_maps_exchange_prefix(self):
        self.assertEqual(sina_symbol("511260"), "sh511260")
        self.assertEqual(sina_symbol("551520"), "sh551520")
        self.assertEqual(sina_symbol("159600"), "sz159600")
        self.assertIsNone(sina_symbol("999999"))

    def test_classify_category_covers_bond_and_tech_names(self):
        self.assertEqual(classify_category("科创债ETF嘉实"), "债券")
        self.assertEqual(classify_category("短融ETF"), "债券")
        self.assertEqual(classify_category("十年国债ETF"), "债券")
        self.assertEqual(classify_category("人工智能ETF易方达"), "科技")
        self.assertEqual(classify_category("恒生科技ETF华夏"), "科技")
        self.assertEqual(classify_category("深证100ETF易方达"), "宽基")
        self.assertEqual(classify_category("科创50ETF华夏"), "宽基")

    def test_append_missing_code_masters_uses_name_overrides(self):
        master = []
        append_missing_code_masters(master, {"511260"})

        self.assertEqual(master[0]["name"], "十年国债ETF")
        self.assertEqual(master[0]["category"], "债券")
        self.assertEqual(master[0]["subcategory"], "利率债")

    def test_classify_subcategory_splits_dividend_subflavors(self):
        cases = {
            "红利ETF华泰柏瑞": "宽口径红利",
            "中证红利ETF招商": "宽口径红利",
            "红利低波ETF华泰柏瑞": "红利低波",
            "红利国企ETF国泰": "国企央企红利",
            "央企红利ETF华泰柏瑞": "国企央企红利",
            "港股通红利ETF华泰柏瑞": "港股红利",
        }
        for name, expected in cases.items():
            self.assertEqual(classify_subcategory(name, "红利"), expected, name)

    def test_classify_subcategory_splits_semiconductor_subflavors(self):
        self.assertEqual(classify_subcategory("芯片ETF华夏", "科技"), "芯片半导体")
        self.assertEqual(classify_subcategory("半导体ETF国联安", "科技"), "芯片半导体")
        self.assertEqual(classify_subcategory("半导体设备ETF国泰", "科技"), "半导体设备")
        self.assertEqual(classify_subcategory("科创芯片ETF嘉实", "科技"), "科创芯片")
        self.assertEqual(classify_subcategory("科创半导体ETF华夏", "科技"), "科创芯片")

    def test_classify_subcategory_covers_tech_bond_broad(self):
        self.assertEqual(classify_subcategory("通信ETF国泰", "科技"), "通信")
        self.assertEqual(classify_subcategory("人工智能ETF易方达", "科技"), "人工智能")
        self.assertEqual(classify_subcategory("十年国债ETF", "债券"), "利率债")
        self.assertEqual(classify_subcategory("可转债ETF", "债券"), "可转债")
        self.assertEqual(classify_subcategory("科创债ETF嘉实", "债券"), "科创债")
        self.assertEqual(classify_subcategory("沪深300ETF华泰柏瑞", "宽基"), "沪深300")
        self.assertEqual(classify_subcategory("中证1000ETF南方", "宽基"), "中证1000")

    def test_classify_subcategory_falls_back_to_category(self):
        self.assertEqual(classify_subcategory("某医药ETF", "医药"), "医药")

    def test_fetch_price_history_uses_sina_fallback_when_eastmoney_throttled(self):
        class FakeAk:
            def fund_etf_hist_em(self, **kwargs):
                raise OSError("RemoteDisconnected")

            def fund_etf_hist_sina(self, **kwargs):
                assert kwargs["symbol"] == "sh512100"
                return [
                    {"date": date(2026, 6, 20), "close": 3.3},
                    {"date": date(2026, 6, 24), "close": 3.4},
                ]

        rows = fetch_price_history(
            FakeAk(),
            [{"code": "512100"}],
            FetchOptions(
                as_of=date(2026, 6, 24),
                start_date=date(2026, 6, 1),
                cache_dir=None,
                price_retries=1,
                retry_sleep_seconds=0,
                price_pause_seconds=0,
            ),
        )

        self.assertEqual(
            rows,
            [
                {"code": "512100", "date": date(2026, 6, 20), "close": 3.3},
                {"code": "512100", "date": date(2026, 6, 24), "close": 3.4},
            ],
        )

    def test_fetch_price_history_respects_disabled_sina_fallback(self):
        class FakeAk:
            def __init__(self):
                self.sina_calls = 0

            def fund_etf_hist_em(self, **kwargs):
                raise OSError("RemoteDisconnected")

            def fund_etf_hist_sina(self, **kwargs):
                self.sina_calls += 1
                return [{"date": date(2026, 6, 24), "close": 3.4}]

        fake = FakeAk()
        rows = fetch_price_history(
            fake,
            [{"code": "512100"}],
            FetchOptions(
                as_of=date(2026, 6, 24),
                start_date=date(2026, 6, 1),
                cache_dir=None,
                price_retries=1,
                retry_sleep_seconds=0,
                price_pause_seconds=0,
                use_sina_fallback=False,
            ),
        )

        self.assertEqual(rows, [])
        self.assertEqual(fake.sina_calls, 0)

    def test_fetch_price_history_raises_in_strict_mode(self):
        class FakeAk:
            def fund_etf_hist_em(self, **kwargs):
                raise OSError("temporary proxy failure")

        with self.assertRaises(Exception):
            fetch_price_history(
                FakeAk(),
                [{"code": "159995"}],
                FetchOptions(
                    as_of=date(2026, 6, 24),
                    start_date=date(2026, 6, 1),
                    cache_dir=None,
                    price_retries=1,
                    retry_sleep_seconds=0,
                    strict=True,
                ),
            )

    def test_spot_price_rows_use_previous_close_for_last_complete_share_date(self):
        rows = spot_price_rows_for_as_of(
            [
                {
                    "code": "510300",
                    "date": date(2026, 6, 25),
                    "close": 5.025,
                    "previous_close": 4.967,
                }
            ],
            date(2026, 6, 24),
        )

        self.assertEqual(rows, [{"code": "510300", "date": date(2026, 6, 24), "close": 4.967}])

    def test_windows_for_set_supports_short_recent_view(self):
        self.assertEqual([item["key"] for item in windows_for_set("short")], ["1D", "1W", "2W", "1M"])

    def test_call_with_retries_wraps_transient_source_errors(self):
        calls = {"count": 0}

        def flaky_source(value):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("temporary ssl eof")
            return value

        result = call_with_retries(
            flaky_source,
            label="测试源",
            retries=2,
            sleep_seconds=0,
            value="ok",
        )

        self.assertEqual(result, "ok")
        self.assertEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()
