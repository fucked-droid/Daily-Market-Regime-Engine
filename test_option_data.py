#!/usr/bin/env python3
"""
Unit tests for the Option Chain Data & Institutional Positioning Analysis Module.
"""

from pathlib import Path
import sys
import unittest

REPO_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(REPO_DIR / "src"))

from src.option_data import (
    load_cached_option_chain,
    calculate_max_pain,
    analyze_option_chain,
)


class TestOptionData(unittest.TestCase):

    def setUp(self):
        self.sample_data = load_cached_option_chain()
        self.assertIsNotNone(self.sample_data, "sample_option_chain.json must exist and load successfully")

    def test_load_cached_option_chain(self):
        self.assertIn("records", self.sample_data)
        self.assertIn("data", self.sample_data["records"])
        self.assertGreater(len(self.sample_data["records"]["data"]), 0)

    def test_calculate_max_pain(self):
        records_data = self.sample_data["records"]["data"]
        max_pain = calculate_max_pain(records_data)
        self.assertGreater(max_pain, 23000)
        self.assertLess(max_pain, 25000)

    def test_analyze_option_chain_metrics(self):
        result = analyze_option_chain(self.sample_data)

        # Check core keys
        self.assertIn("spot_price", result)
        self.assertIn("atm_strike", result)
        self.assertIn("pcr_oi", result)
        self.assertIn("max_pain", result)
        self.assertIn("major_resistance_wall", result)
        self.assertIn("major_support_floor", result)
        self.assertIn("momentum_score", result)
        self.assertIn("signals", result)

        # Verify Resistance and Support walls based on highest OI in sample
        # 24800 has 325,000 Call OI -> Major Resistance Wall
        self.assertEqual(result["major_resistance_wall"], 24800)
        # 24400 has 310,000 Put OI -> Major Support Floor
        self.assertEqual(result["major_support_floor"], 24400)

        # Verify PCR calculation
        self.assertGreater(result["pcr_oi"], 0.5)
        self.assertLess(result["pcr_oi"], 2.5)

        # Verify expected option move range
        low_bound, high_bound = result["expected_option_range"]
        self.assertLess(low_bound, result["spot_price"])
        self.assertGreater(high_bound, result["spot_price"])

    def test_call_unwinding_signals(self):
        result = analyze_option_chain(self.sample_data)
        # In sample, strikes 24000-24400 have negative Call changeinOpenInterest
        self.assertGreater(len(result["call_unwinding"]), 0)
        unwinding_strikes = [c["strike"] for c in result["call_unwinding"]]
        self.assertTrue(any(s in unwinding_strikes for s in [24000, 24100, 24200, 24300, 24400]))

    def test_zero_division_guard(self):
        # Empty calls should not raise ZeroDivisionError
        empty_chain = {
            "records": {
                "underlyingValue": 24000.0,
                "expiryDates": ["05-Nov-2026"],
                "data": [
                    {
                        "strikePrice": 24000,
                        "expiryDate": "05-Nov-2026",
                        "CE": {"openInterest": 0, "totalTradedVolume": 0, "changeinOpenInterest": 0},
                        "PE": {"openInterest": 10000, "totalTradedVolume": 50000, "changeinOpenInterest": 2000},
                    }
                ],
            }
        }
        res = analyze_option_chain(empty_chain)
        self.assertEqual(res["pcr_oi"], 1.0)
        self.assertEqual(res["pcr_volume"], 1.0)


    def test_live_alerts_with_option_chain(self):
        from src.live_scanner import evaluate_live_alerts
        opt_analysis = analyze_option_chain(self.sample_data, spot_price=24790.0)

        fake_live_nifty = {
            "price": 24790.0,
            "change_pct": 0.8,
            "position_in_range_pct": 75.0,
        }
        fake_forecast = {
            "nearest_resistance": {"price": 24868.0, "range": [24774.0, 24886.0]},
            "nearest_support": {"price": 24228.0, "range": [24100.0, 24400.0]},
            "expected_range": {"expected_daily_upper": 24868.0, "expected_daily_lower": 24228.0},
        }

        alerts = evaluate_live_alerts(
            live_nifty=fake_live_nifty,
            forecast=fake_forecast,
            option_analysis=opt_analysis,
        )

        alert_types = [a["type"] for a in alerts]
        # Spot is 24790 which is within 50 pts of Major Call Wall 24800
        self.assertIn("OPTION_WALL", alert_types)
        wall_alert = next(a for a in alerts if a["type"] == "OPTION_WALL")
        self.assertIn("24,800", wall_alert["message"])


if __name__ == "__main__":
    unittest.main()
