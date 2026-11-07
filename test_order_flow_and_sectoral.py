"""
Unit tests for Advanced Institutional Order Flow (CVD) and Sectoral Rotation:
1. Order Flow & Cumulative Volume Delta (CVD) (`src/order_flow.py`)
2. Sectoral Rotation & Heavyweight Heatmap (`src/sectoral_rotation.py`)
"""

import unittest
from pathlib import Path

from src.order_flow import (
    OrderFlowAnalyzer,
    fetch_order_flow_data,
    load_cached_order_flow,
)
from src.sectoral_rotation import (
    SectoralRotationAnalyzer,
    fetch_sectoral_data,
    load_cached_sectoral,
)


class TestOrderFlow(unittest.TestCase):
    """Test suite for Intraday Order Flow and Cumulative Volume Delta (CVD)."""

    def setUp(self):
        self.data = load_cached_order_flow()
        self.analyzer = OrderFlowAnalyzer(self.data)

    def test_load_cached_order_flow(self):
        self.assertIn("session_stats", self.data)
        self.assertIn("order_book_depth", self.data)
        self.assertIn("intraday_bars_15m", self.data)

    def test_analyze_cumulative_delta(self):
        delta = self.analyzer.analyze_cumulative_delta()
        self.assertEqual(delta["total_volume"], 12850000)
        self.assertEqual(delta["buy_volume"], 7710000)
        self.assertEqual(delta["sell_volume"], 5140000)
        self.assertEqual(delta["cumulative_volume_delta"], 2570000)
        self.assertAlmostEqual(delta["buyer_ratio_pct"], 60.0, places=1)
        self.assertEqual(delta["sentiment"], "STRONG_BUYER_DOMINANCE")

    def test_bearish_absorption_trap_divergence(self):
        """Price makes Higher High, but CVD makes Lower High -> Bearish Absorption."""
        custom_bars = [
            {"high": 24400, "low": 24350, "close": 24390, "cumulative_delta": 500000},
            {"high": 24450, "low": 24380, "close": 24420, "cumulative_delta": 600000},
            {"high": 24500, "low": 24440, "close": 24490, "cumulative_delta": 300000},  # HH, but CVD dropped!
        ]
        div = self.analyzer.detect_delta_divergence(custom_bars=custom_bars)
        self.assertEqual(div["status"], "BEARISH_ABSORPTION_TRAP")
        self.assertEqual(div["divergence_signal"], "BEARISH_DIVERGENCE")

    def test_bullish_absorption_accumulation_divergence(self):
        """Price makes Lower Low, but CVD makes Higher Low -> Bullish Absorption."""
        custom_bars = [
            {"high": 24400, "low": 24350, "close": 24360, "cumulative_delta": -200000},
            {"high": 24380, "low": 24310, "close": 24330, "cumulative_delta": -100000},
            {"high": 24340, "low": 24280, "close": 24290, "cumulative_delta": +150000},  # LL, but CVD higher!
        ]
        div = self.analyzer.detect_delta_divergence(custom_bars=custom_bars)
        self.assertEqual(div["status"], "BULLISH_ABSORPTION_ACCUMULATION")
        self.assertEqual(div["divergence_signal"], "BULLISH_DIVERGENCE")

    def test_bullish_delta_expansion(self):
        """Price HH, CVD HH -> Bullish Trend Continuation."""
        custom_bars = [
            {"high": 24350, "low": 24300, "close": 24340, "cumulative_delta": 100000},
            {"high": 24400, "low": 24330, "close": 24390, "cumulative_delta": 300000},
            {"high": 24480, "low": 24380, "close": 24470, "cumulative_delta": 600000},
        ]
        div = self.analyzer.detect_delta_divergence(custom_bars=custom_bars)
        self.assertEqual(div["status"], "BULLISH_DELTA_EXPANSION")
        self.assertEqual(div["divergence_signal"], "BULLISH_CONFIRMATION")

    def test_order_book_depth_imbalance(self):
        depth = self.analyzer.analyze_order_book_imbalance()
        self.assertAlmostEqual(depth["bid_ask_imbalance_ratio"], 1.50, places=2)
        self.assertEqual(depth["status"], "STRONG_BUY_SIDE_LIQUIDITY")
        self.assertEqual(depth["bias"], "BULLISH_SUPPORT")

    def test_compute_order_flow_score_bounded(self):
        res = self.analyzer.compute_order_flow_score()
        score = res["score"]
        self.assertTrue(-2.0 <= score <= 2.0)
        self.assertEqual(res["verdict"], "STRONG_BULLISH_FLOW")
        self.assertEqual(res["regime"], "AGGRESSIVE_BUYER_EXPANSION")

    def test_zero_volume_resilience(self):
        zero_data = {
            "session_stats": {"total_volume": 0, "buy_volume": 0, "sell_volume": 0},
            "order_book_depth": {"total_bid_quantity": 0, "total_ask_quantity": 0},
            "intraday_bars_15m": [],
        }
        analyzer = OrderFlowAnalyzer(zero_data)
        res = analyzer.compute_order_flow_score()
        self.assertTrue(-2.0 <= res["score"] <= 2.0)
        self.assertEqual(res["verdict"], "NEUTRAL_FLOW")

    def test_get_summary_text(self):
        text = self.analyzer.get_summary_text()
        self.assertIn("Order Flow (CVD) Score:", text)
        self.assertIn("Cumulative Delta", text)
        self.assertIn("Order Book Depth", text)


class TestSectoralRotation(unittest.TestCase):
    """Test suite for Sectoral Rotation and Heavyweight Heatmap Engine."""

    def setUp(self):
        self.data = load_cached_sectoral()
        self.analyzer = SectoralRotationAnalyzer(self.data)

    def test_load_cached_sectoral(self):
        self.assertIn("sectors", self.data)
        self.assertIn("top_heavyweights", self.data)
        self.assertGreaterEqual(len(self.data["sectors"]), 3)

    def test_analyze_sector_performance_and_points(self):
        sec = self.analyzer.analyze_sector_performance()
        self.assertGreater(sec["total_sector_points"], 0)
        self.assertIsNotNone(sec["top_driver"])
        self.assertEqual(sec["top_driver"]["name"], "NIFTY BANK")
        # Nifty Bank ~33.5% weight, +2.85% move on 24548 close -> ~234 points contribution
        self.assertAlmostEqual(sec["top_driver"]["points_contribution"], 234.37, places=0)

    def test_analyze_heavyweight_contribution(self):
        hw = self.analyzer.analyze_heavyweight_contribution()
        self.assertIsNotNone(hw["top_bull_stock"])
        self.assertEqual(hw["top_bull_stock"]["name"], "HDFC Bank")
        self.assertAlmostEqual(hw["top_bull_stock"]["points_contribution"], 81.87, places=0)

    def test_risk_on_expansion_classification(self):
        rot = self.analyzer.classify_rotation_regime()
        self.assertEqual(rot["regime"], "RISK_ON_EXPANSION")
        self.assertEqual(rot["rotation_signal"], "STRONG_BULLISH_ROTATION")
        self.assertIn("Aggressive Risk-On", rot["description"])

    def test_defensive_rotation_warning_classification(self):
        defensive_data = {
            "nifty_close": 24500.0,
            "sectors": [
                {"name": "NIFTY BANK", "weight_pct": 33.5, "change_pct": -1.2, "category": "CYCLICAL_FINANCIAL"},
                {"name": "NIFTY AUTO", "weight_pct": 7.2, "change_pct": -0.8, "category": "CYCLICAL_CONSUMER"},
                {"name": "NIFTY FMCG", "weight_pct": 8.1, "change_pct": 1.4, "category": "DEFENSIVE"},
                {"name": "NIFTY PHARMA", "weight_pct": 4.2, "change_pct": 1.1, "category": "DEFENSIVE"},
            ],
            "top_heavyweights": [],
        }
        analyzer = SectoralRotationAnalyzer(defensive_data)
        rot = analyzer.classify_rotation_regime()
        self.assertEqual(rot["regime"], "DEFENSIVE_ROTATION_WARNING")
        self.assertEqual(rot["rotation_signal"], "BEARISH_RISK_OFF")

    def test_sectoral_tug_of_war_classification(self):
        tug_data = {
            "nifty_close": 24500.0,
            "sectors": [
                {"name": "NIFTY BANK", "weight_pct": 33.5, "change_pct": 2.5, "category": "CYCLICAL_FINANCIAL"},
                {"name": "NIFTY IT", "weight_pct": 13.8, "change_pct": -2.2, "category": "GROWTH_TECH"},
                {"name": "NIFTY FMCG", "weight_pct": 8.1, "change_pct": 0.1, "category": "DEFENSIVE"},
            ],
            "top_heavyweights": [],
        }
        analyzer = SectoralRotationAnalyzer(tug_data)
        rot = analyzer.classify_rotation_regime()
        self.assertEqual(rot["regime"], "SECTORAL_TUG_OF_WAR")
        self.assertEqual(rot["rotation_signal"], "NEUTRAL_DIVERGENCE")

    def test_broad_liquidation_classification(self):
        dump_data = {
            "nifty_close": 24500.0,
            "sectors": [
                {"name": "NIFTY BANK", "weight_pct": 33.5, "change_pct": -2.5, "category": "CYCLICAL_FINANCIAL"},
                {"name": "NIFTY IT", "weight_pct": 13.8, "change_pct": -1.8, "category": "GROWTH_TECH"},
                {"name": "NIFTY AUTO", "weight_pct": 7.2, "change_pct": -2.1, "category": "CYCLICAL_CONSUMER"},
                {"name": "NIFTY FMCG", "weight_pct": 8.1, "change_pct": -0.9, "category": "DEFENSIVE"},
            ],
            "top_heavyweights": [],
        }
        analyzer = SectoralRotationAnalyzer(dump_data)
        rot = analyzer.classify_rotation_regime()
        self.assertEqual(rot["regime"], "BROAD_SECTORAL_LIQUIDATION")
        self.assertEqual(rot["rotation_signal"], "STRONG_BEARISH_ROTATION")

    def test_compute_sectoral_score_bounded(self):
        score_res = self.analyzer.compute_sectoral_score()
        score = score_res["score"]
        self.assertTrue(-2.0 <= score <= 2.0)
        self.assertEqual(score_res["verdict"], "BULLISH_SECTOR_ALIGNMENT")

    def test_empty_sector_resilience(self):
        empty_data = {"nifty_close": 24500.0, "sectors": [], "top_heavyweights": []}
        analyzer = SectoralRotationAnalyzer(empty_data)
        res = analyzer.compute_sectoral_score()
        self.assertTrue(-2.0 <= res["score"] <= 2.0)
        self.assertEqual(res["verdict"], "NEUTRAL_SECTOR_CHURNING")

    def test_get_summary_text(self):
        text = self.analyzer.get_summary_text()
        self.assertIn("Sectoral Rotation Score:", text)
        self.assertIn("Rotation Dynamic", text)
        self.assertIn("Top Sector Driver", text)


if __name__ == "__main__":
    unittest.main()
