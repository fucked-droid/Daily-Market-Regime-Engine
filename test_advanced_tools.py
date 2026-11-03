"""
Unit tests for Advanced Institutional Tools:
1. Institutional Flow & Smart Money Positioning (`src/institutional_flow.py`)
2. Market Breadth & Advance-Decline Divergence (`src/market_breadth.py`)
3. Global Cues & Opening Gap Predictor (`src/global_cues.py`)
"""

import unittest
from pathlib import Path

from src.institutional_flow import (
    InstitutionalFlowAnalyzer,
    fetch_fii_dii_data,
    load_cached_fii_dii,
)
from src.market_breadth import (
    MarketBreadthAnalyzer,
    fetch_market_breadth,
    load_cached_breadth,
)
from src.global_cues import (
    GlobalCuesAnalyzer,
    fetch_global_cues,
    load_cached_global_cues,
)


class TestInstitutionalFlow(unittest.TestCase):
    """Test suite for FII/DII cash flows and derivatives positioning."""

    def setUp(self):
        self.data = load_cached_fii_dii()
        self.analyzer = InstitutionalFlowAnalyzer(self.data)

    def test_load_cached_data(self):
        self.assertIn("cash_market", self.data)
        self.assertIn("derivatives", self.data)
        self.assertIn("fii", self.data["cash_market"])
        self.assertIn("dii", self.data["cash_market"])

    def test_cash_flow_analysis(self):
        cash = self.analyzer.analyze_cash_flow()
        self.assertEqual(cash["fii_net_crores"], 2140.5)
        self.assertEqual(cash["dii_net_crores"], 1610.1)
        self.assertEqual(cash["total_net_crores"], 3750.6)
        self.assertEqual(cash["regime"], "STRONG_INSTITUTIONAL_BUYING")

    def test_derivatives_analysis(self):
        deriv = self.analyzer.analyze_derivatives_positioning()
        self.assertEqual(deriv["long_contracts"], 95200)
        self.assertEqual(deriv["short_contracts"], 58400)
        self.assertEqual(deriv["net_contracts"], 36800)
        self.assertAlmostEqual(deriv["long_ratio_pct"], 61.98, places=1)
        self.assertEqual(deriv["futures_sentiment"], "STRONG_BULLISH")
        self.assertEqual(deriv["option_bias"], "BULLISH")

    def test_smart_money_score(self):
        res = self.analyzer.compute_smart_money_score()
        score = res["composite_score"]
        self.assertTrue(-2.0 <= score <= 2.0)
        self.assertEqual(res["verdict"], "BULLISH")
        self.assertIn("STRONG_ACCUMULATION", res["regime"])

    def test_summary_text(self):
        text = self.analyzer.get_summary_text()
        self.assertIn("Smart Money Flow", text)
        self.assertIn("Cash Flow:", text)
        self.assertIn("Index Futures:", text)


class TestMarketBreadth(unittest.TestCase):
    """Test suite for Market Breadth & Advance-Decline divergence engine."""

    def setUp(self):
        self.data = load_cached_breadth()
        self.analyzer = MarketBreadthAnalyzer(self.data)

    def test_adr_calculation(self):
        adr = self.analyzer.get_adr()
        self.assertAlmostEqual(adr, 36 / 13, places=2)

    def test_zero_declines_safe_adr(self):
        custom_data = {"advances": 50, "declines": 0, "unchanged": 0, "total": 50}
        analyzer = MarketBreadthAnalyzer(custom_data)
        self.assertEqual(analyzer.get_adr(), 50.0)

    def test_hollow_rally_divergence(self):
        """Index up +0.6%, but advances only 15 and declines 35 (ADR < 0.8) -> Hollow Rally Trap."""
        divergent_data = {"advances": 15, "declines": 35, "unchanged": 0, "total": 50}
        analyzer = MarketBreadthAnalyzer(divergent_data)
        div = analyzer.detect_divergence(index_change_pct=0.6)
        self.assertEqual(div["status"], "HOLLOW_RALLY_WARNING")
        self.assertEqual(div["signal"], "BEARISH_DIVERGENCE_TRAP")

    def test_bullish_accumulation_divergence(self):
        """Index down -0.5%, but advances 32 and declines 18 (ADR > 1.2) -> Bullish Divergence."""
        divergent_data = {"advances": 32, "declines": 18, "unchanged": 0, "total": 50}
        analyzer = MarketBreadthAnalyzer(divergent_data)
        div = analyzer.detect_divergence(index_change_pct=-0.5)
        self.assertEqual(div["status"], "BULLISH_ABSORPTION_ACCUMULATION")
        self.assertEqual(div["signal"], "BULLISH_DIVERGENCE")

    def test_breadth_score_bounded(self):
        score_res = self.analyzer.compute_breadth_score(index_change_pct=0.5)
        self.assertTrue(-2.0 <= score_res["score"] <= 2.0)
        self.assertEqual(score_res["regime"], "STRONG_BULLISH_BREADTH")

    def test_summary_text(self):
        text = self.analyzer.get_summary_text(index_change_pct=0.5)
        self.assertIn("Market Breadth (NIFTY 50):", text)
        self.assertIn("ADR:", text)


class TestGlobalCues(unittest.TestCase):
    """Test suite for Global Cues & GIFT NIFTY Opening Gap Predictor."""

    def setUp(self):
        self.data = load_cached_global_cues()
        self.analyzer = GlobalCuesAnalyzer(self.data)

    def test_predict_opening_gap(self):
        gap = self.analyzer.predict_opening_gap(spot_close=23990.0)
        self.assertEqual(gap["gap_points"], 95.0)
        self.assertAlmostEqual(gap["gap_pct"], 0.40, places=2)
        self.assertEqual(gap["projected_open"], 24085.0)
        self.assertEqual(gap["category"], "MODERATE_GAP_UP")

    def test_gap_categories(self):
        # Test Strong Gap Up
        large_gap_data = {
            "gift_nifty": {"last_price": 24200.0, "spot_reference_close": 24000.0},
            "us_markets": {},
            "commodities_currencies": {}
        }
        res_up = GlobalCuesAnalyzer(large_gap_data).predict_opening_gap()
        self.assertEqual(res_up["category"], "STRONG_GAP_UP")

        # Test Strong Gap Down
        down_gap_data = {
            "gift_nifty": {"last_price": 23800.0, "spot_reference_close": 24000.0},
            "us_markets": {},
            "commodities_currencies": {}
        }
        res_down = GlobalCuesAnalyzer(down_gap_data).predict_opening_gap()
        self.assertEqual(res_down["category"], "STRONG_GAP_DOWN")

    def test_macro_tailwinds(self):
        macro = self.analyzer.analyze_macro_tailwinds()
        self.assertEqual(macro["crude_bias"], "BULLISH_TAILWIND")
        self.assertEqual(macro["yield_bias"], "BULLISH_FII_FLOW_SUPPORT")

    def test_global_sentiment_score(self):
        res = self.analyzer.compute_global_sentiment_score(spot_close=23990.0)
        self.assertTrue(-2.0 <= res["score"] <= 2.0)
        self.assertEqual(res["verdict"], "BULLISH_GLOBAL_ALIGNMENT")

    def test_summary_text(self):
        text = self.analyzer.get_summary_text(spot_close=23990.0)
        self.assertIn("GIFT NIFTY:", text)
        self.assertIn("Projected Gap:", text)
        self.assertIn("Global Sentiment Score:", text)


if __name__ == "__main__":
    unittest.main()
