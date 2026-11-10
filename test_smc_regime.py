import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

from src.order_block import (
    detect_order_blocks,
    detect_fair_value_gaps,
    analyze_smc_regime,
    format_smc_alert_text,
)
from src.telegram_alerts import format_live_widget_card


class TestSMCRegime(unittest.TestCase):
    def setUp(self):
        # Create synthetic OHLCV dataframe with 10 bars
        dates = pd.date_range("2026-11-06 09:15", periods=10, freq="15min")
        self.df = pd.DataFrame({
            "Open": [25000, 25020, 25050, 25080, 25060, 25040, 25020, 25030, 25025, 25030],
            "High": [25025, 25055, 25085, 25095, 25075, 25050, 25035, 25045, 25035, 25035],
            "Low":  [24990, 25010, 25040, 25050, 25030, 25015, 25005, 25010, 25015, 25020],
            "Close": [25020, 25050, 25080, 25060, 25035, 25020, 25030, 25025, 25030, 25030],
            "Volume": [1000] * 10
        }, index=dates)

    def test_detect_fair_value_gaps(self):
        res = detect_fair_value_gaps(self.df)
        self.assertIn("bullish_fvgs", res)
        self.assertIn("bearish_fvgs", res)
        self.assertIn("nearest_bullish", res)
        self.assertIn("nearest_bearish", res)

    def test_analyze_smc_regime_bearish_mss(self):
        live_nifty = {
            "price": 25030.0,
            "day_high": 25080.0,
            "day_low": 24960.0,
            "change_points": -20.0,
            "change_pct": -0.08,
            "position_in_range_pct": 58.0,
        }
        smc = analyze_smc_regime(df_intraday=self.df, live_nifty=live_nifty)
        self.assertEqual(smc["spot"], 25030.0)
        self.assertEqual(smc["action"], "SELL ON RALLIES")
        self.assertIn("Bearish MSS", smc["action_sub"])
        self.assertIn("BSL Swept", smc["liquidity_text"])
        self.assertIn("MSS", smc["shift_text"])
        self.assertIn("FVG", smc["exec_zone"])
        self.assertIn("Above OB", smc["sl_text"])
        self.assertIn("SSL", smc["target_text"])

    def test_format_smc_alert_text(self):
        smc_data = {
            "spot": 25030.0,
            "pdh": 25120.0,
            "pdl": 24940.0,
            "day_high": 25080.0,
            "day_low": 24960.0,
            "action": "SELL ON RALLIES",
            "action_sub": "Bearish MSS",
            "liquidity_text": "BSL Swept at 25,080 (Asian/Early High taken)",
            "shift_text": "5m Market Structure Shift (MSS) Confirmed Bearish",
            "fvg_range": "25,050 – 25,065",
            "fvg_meta": "15m Unmitigated",
            "ob_type": "Bearish OB",
            "ob_range": "25,070 – 25,085",
            "ob_desc": "Origin of displacement",
            "exec_zone": "25,050 - 25,060 (Tap in FVG on pullback)",
            "sl_text": "25,090 (Above OB invalidates setup)",
            "target_text": "24,960 (Internal SSL)",
            "bias": "BEARISH",
        }
        text = format_smc_alert_text(smc_data, iteration=1, time_str="12:00:00 IST")
        self.assertIn("NIFTY INTRADAY | SMC REGIME ALERT", text)
        self.assertIn("SELL ON RALLIES", text)
        self.assertIn("25,030", text)
        self.assertIn("25,120 - 24,940", text)
        self.assertIn("25,050 – 25,065", text)
        self.assertIn("25,070 – 25,085", text)
        self.assertIn("25,090", text)
        self.assertIn("24,960", text)
        self.assertIn("Auto-edited in-place every 30s", text)

    def test_format_live_widget_card_uses_smc(self):
        live_nifty = {"price": 25030.0, "day_high": 25080.0, "day_low": 24960.0}
        card = format_live_widget_card(live_nifty=live_nifty, iteration=1)
        self.assertIn("SMC REGIME ALERT", card)
        self.assertIn("Spot:", card)
        self.assertIn("VALID KEY ZONES", card)


if __name__ == "__main__":
    unittest.main()
