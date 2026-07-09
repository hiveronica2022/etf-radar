import unittest

from etf_radar.presets import ETF_PRESETS, resolve_codes


class PresetsTest(unittest.TestCase):
    def test_core_preset_covers_major_broad_and_tech_exposures(self):
        codes = resolve_codes(["core"], None)

        expected = {
            "510050",  # 上证50
            "510300",  # 沪深300
            "510500",  # 中证500
            "512100",  # 中证1000
            "159352",  # 中证A500
            "159901",  # 深证100
            "159915",  # 创业板
            "159949",  # 创业板50
            "588000",  # 科创50
            "588120",  # 科创100
            "588400",  # 双创50
            "512480",  # 半导体（芯片半导体）
            "159995",  # 芯片（芯片半导体）
            "512760",  # 芯片国泰（芯片半导体）
            "159516",  # 半导体设备
            "560780",  # 半导体设备广发
            "588200",  # 科创芯片
            "588170",  # 科创半导体
            "515880",  # 通信
            "159819",  # 人工智能
            "516510",  # 云计算
            "515230",  # 软件
            "159792",  # 港股通互联网
            "513180",  # 恒生科技
        }

        self.assertTrue(expected <= set(codes))
        self.assertEqual(len(codes), len(set(codes)))

    def test_bond_preset_covers_rate_credit_convertible_and_short_bills(self):
        codes = resolve_codes(["bond"], None)

        expected = {
            "511010",  # 国债(5年)
            "511260",  # 十年国债
            "511090",  # 30年国债
            "511520",  # 政金债
            "511030",  # 公司债
            "159600",  # 科创债
            "511380",  # 可转债
            "511360",  # 短融
        }

        self.assertTrue(expected <= set(codes))

    def test_dividend_preset_covers_broad_lowvol_soe_and_hk_dividend(self):
        codes = resolve_codes(["dividend"], None)

        expected = {
            "510880",  # 上证红利
            "515180",  # 中证红利
            "512890",  # 红利低波
            "510720",  # 国企红利
            "561580",  # 央企红利
            "513530",  # 港股通红利
        }

        self.assertTrue(expected <= set(codes))

    def test_core_bond_dividend_presets_combine_without_duplicates(self):
        codes = resolve_codes(["core", "bond", "dividend"], None)

        self.assertEqual(len(codes), len(set(codes)))
        self.assertIn("510300", codes)
        self.assertIn("511260", codes)
        self.assertIn("510880", codes)

    def test_resolve_codes_merges_user_codes_after_presets(self):
        self.assertEqual(resolve_codes(["core"], ["510300", "159600"])[-1], "159600")

    def test_unknown_preset_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_codes(["unknown"], None)

    def test_core_preset_has_description(self):
        self.assertIn("description", ETF_PRESETS["core"])


if __name__ == "__main__":
    unittest.main()
