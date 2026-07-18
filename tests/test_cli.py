import unittest

from etf_radar.cli import fetch_until_complete, parse_args
from etf_radar.metrics import missing_data_codes


def snapshot_with(rows, trends):
    return {"rows": rows, "trends": trends}


class CliTest(unittest.TestCase):
    def refresh_args(self):
        return parse_args(["refresh", "--preset", "core", "--no-cache"])

    def test_missing_data_codes_flags_rows_without_scale_or_trend(self):
        snapshot = snapshot_with(
            rows=[
                {"code": "510300", "scale_100m": 100.0},
                {"code": "511260", "scale_100m": None},
                {"code": "511360", "scale_100m": 50.0},
            ],
            trends=[{"code": "510300"}],
        )

        self.assertEqual(missing_data_codes(snapshot), ["511260", "511360"])

    def test_fetch_until_complete_stops_when_data_is_complete(self):
        complete = snapshot_with(
            rows=[{"code": "510300", "scale_100m": 100.0}],
            trends=[{"code": "510300"}],
        )
        incomplete = snapshot_with(
            rows=[{"code": "510300", "scale_100m": None}],
            trends=[],
        )
        results = [incomplete, complete, complete]
        calls = []

        def fake_fetch(options):
            calls.append(options)
            return results[len(calls) - 1]

        snapshot = fetch_until_complete(
            self.refresh_args(),
            max_passes=3,
            pass_sleep_seconds=0,
            fetch_fn=fake_fetch,
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(missing_data_codes(snapshot), [])

    def test_fetch_until_complete_returns_last_snapshot_when_passes_exhausted(self):
        incomplete = snapshot_with(
            rows=[{"code": "511260", "scale_100m": None}],
            trends=[],
        )
        calls = []

        def fake_fetch(options):
            calls.append(options)
            return incomplete

        snapshot = fetch_until_complete(
            self.refresh_args(),
            max_passes=2,
            pass_sleep_seconds=0,
            fetch_fn=fake_fetch,
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(missing_data_codes(snapshot), ["511260"])

    def test_refresh_command_parses_with_defaults(self):
        args = parse_args(["refresh", "--preset", "core", "--preset", "bond", "--no-proxy"])

        self.assertEqual(args.command, "refresh")
        self.assertEqual(args.max_passes, 3)
        self.assertTrue(args.no_proxy)
        self.assertFalse(args.no_beta_pressure)
        self.assertEqual(args.beta_top_stocks, 120)

    def test_fetch_command_can_disable_beta_pressure(self):
        args = parse_args(["fetch", "--no-beta-pressure", "--beta-top-stocks", "50"])

        self.assertTrue(args.no_beta_pressure)
        self.assertEqual(args.beta_top_stocks, 50)


if __name__ == "__main__":
    unittest.main()
