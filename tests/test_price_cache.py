from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from etf_radar.price_cache import (
    cached_date_range,
    load_cached_spot_rows,
    load_cached_prices,
    merge_price_rows,
    save_cached_spot_rows,
    save_cached_prices,
)


class PriceCacheTest(unittest.TestCase):
    def test_save_and_load_cached_prices_round_trips_dates(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            rows = [
                {"code": "510300", "date": date(2026, 6, 24), "close": 4.967},
                {"code": "510300", "date": date(2026, 6, 25), "close": 5.025},
            ]

            save_cached_prices(cache_dir, "510300", rows)
            loaded = load_cached_prices(cache_dir, "510300")

            self.assertEqual(loaded, rows)

    def test_merge_price_rows_dedupes_by_code_and_date(self):
        existing = [
            {"code": "510300", "date": date(2026, 6, 24), "close": 4.9},
            {"code": "510300", "date": date(2026, 6, 25), "close": 5.0},
        ]
        incoming = [
            {"code": "510300", "date": date(2026, 6, 25), "close": 5.025},
            {"code": "510300", "date": date(2026, 6, 26), "close": 5.1},
        ]

        merged = merge_price_rows(existing, incoming)

        self.assertEqual([row["date"] for row in merged], [date(2026, 6, 24), date(2026, 6, 25), date(2026, 6, 26)])
        self.assertEqual(merged[1]["close"], 5.025)

    def test_cached_date_range_reports_coverage(self):
        rows = [
            {"code": "510300", "date": date(2026, 6, 24), "close": 4.967},
            {"code": "510300", "date": date(2026, 6, 25), "close": 5.025},
        ]

        self.assertEqual(cached_date_range(rows), (date(2026, 6, 24), date(2026, 6, 25)))
        self.assertEqual(cached_date_range([]), (None, None))

    def test_spot_rows_are_cached_by_as_of_date(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            rows = [{"代码": "510300", "名称": "沪深300ETF华泰柏瑞", "最新价": 5.025}]

            save_cached_spot_rows(cache_dir, date(2026, 6, 25), rows)

            self.assertEqual(load_cached_spot_rows(cache_dir, date(2026, 6, 25)), rows)
            self.assertEqual(load_cached_spot_rows(cache_dir, date(2026, 6, 24)), [])


if __name__ == "__main__":
    unittest.main()
