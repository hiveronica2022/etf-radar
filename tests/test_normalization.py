from datetime import date
import unittest

from etf_radar.normalization import (
    detect_exchange,
    normalize_date,
    normalize_share_to_yi,
    parse_number,
)


class NormalizationTest(unittest.TestCase):
    def test_parse_number_handles_commas_percent_and_empty_values(self):
        self.assertEqual(parse_number("1,234.50"), 1234.5)
        self.assertEqual(parse_number("+3.2%"), 3.2)
        self.assertIsNone(parse_number("--"))
        self.assertIsNone(parse_number(""))

    def test_normalize_share_to_yi_uses_column_units(self):
        self.assertEqual(normalize_share_to_yi(120000, "基金份额(万份)"), 12.0)
        self.assertEqual(normalize_share_to_yi(12.5, "基金份额(亿份)"), 12.5)
        self.assertEqual(normalize_share_to_yi(3300000000, "基金份额"), 33.0)

    def test_normalize_date_accepts_common_public_data_shapes(self):
        self.assertEqual(normalize_date("2026-06-24"), date(2026, 6, 24))
        self.assertEqual(normalize_date("20260624"), date(2026, 6, 24))

    def test_detect_exchange_from_code_prefix(self):
        self.assertEqual(detect_exchange("510300"), "SSE")
        self.assertEqual(detect_exchange("588000"), "SSE")
        self.assertEqual(detect_exchange("159915"), "SZSE")
        self.assertEqual(detect_exchange("560780"), "SSE")
        self.assertEqual(detect_exchange("551520"), "SSE")  # 科创债跨市 ETF


if __name__ == "__main__":
    unittest.main()
