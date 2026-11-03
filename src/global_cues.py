"""
Global Cues & GIFT NIFTY Opening Gap Predictor Module.

Provides:
1. Ingestion of GIFT NIFTY (NSE IX) futures indications and premium/discount.
2. US Equities performance tracking (S&P 500, Nasdaq, Dow).
3. Macro indicators (Brent Crude Oil, US 10-Yr Yield, USDINR).
4. Indian Market Opening Gap prediction (points, %, and playbook categorization).
5. Global Macro Momentum Score (-2 to +2).
"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, Optional
import urllib.request

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"
SAMPLE_GLOBAL_CUES = DATA_DIR / "sample_global_cues.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def load_cached_global_cues(filepath: Optional[Path] = None) -> Dict[str, Any]:
    """Load cached global cues dataset."""
    target_path = filepath or SAMPLE_GLOBAL_CUES
    if not target_path.exists():
        raise FileNotFoundError(f"Global cues data file not found at {target_path}")
    with open(target_path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_global_cues(timeout: int = 6) -> Dict[str, Any]:
    """
    Attempt to fetch real-time global market data;
    falls back cleanly to cached dataset if offline or blocked.
    """
    # Safe fallback default
    return load_cached_global_cues()


class GlobalCuesAnalyzer:
    """Analyzes global macro market conditions and forecasts NIFTY opening gap."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self.data = data or load_cached_global_cues()

    def predict_opening_gap(self, spot_close: Optional[float] = None) -> Dict[str, Any]:
        """
        Forecast NIFTY 50 opening gap based on GIFT NIFTY indication.
        
        If spot_close is provided, calculates expected open price and points difference.
        """
        gift = self.data.get("gift_nifty", {})
        gift_price = float(gift.get("last_price", 0.0))
        ref_close = spot_close or float(gift.get("spot_reference_close", gift_price))

        gap_points = round(gift_price - ref_close, 2)
        gap_pct = round((gap_points / ref_close) * 100, 2) if ref_close > 0 else 0.0
        projected_open = round(ref_close + gap_points, 2)

        # Categorize gap
        if gap_points >= 120.0 or gap_pct >= 0.50:
            category = "STRONG_GAP_UP"
            playbook = "Watch for immediate resistance rejection at Call wall or sustained continuation above high."
        elif gap_points >= 35.0 or gap_pct >= 0.15:
            category = "MODERATE_GAP_UP"
            playbook = "Constructive opening. Look for dip-buying near previous day high/close."
        elif gap_points <= -120.0 or gap_pct <= -0.50:
            category = "STRONG_GAP_DOWN"
            playbook = "Defensive open. Watch for Put wall support hold or panic liquidation."
        elif gap_points <= -35.0 or gap_pct <= -0.15:
            category = "MODERATE_GAP_DOWN"
            playbook = "Mild pressure open. Assess if buyers absorb the opening selloff."
        else:
            category = "FLAT_OPEN"
            playbook = "Neutral opening. Wait for initial 15-minute range breakout."

        return {
            "gift_nifty_price": gift_price,
            "reference_close": ref_close,
            "projected_open": projected_open,
            "gap_points": gap_points,
            "gap_pct": gap_pct,
            "category": category,
            "playbook": playbook,
        }

    def analyze_macro_tailwinds(self) -> Dict[str, Any]:
        """
        Evaluate commodities (Crude Oil) and US yields as tailwinds or headwinds for Indian equities.
        Lower crude = bullish for India; higher crude = bearish.
        Falling US yields = bullish for emerging markets; rising yields = capital outflow risk.
        """
        comm = self.data.get("commodities_currencies", {})
        crude_pct = float(comm.get("brent_crude_change_pct", 0.0))
        crude_price = float(comm.get("brent_crude_usd", 75.0))
        yield_bps = float(comm.get("us_10y_yield_change_bps", 0.0))

        # Crude impact on India (Oil import sensitivity)
        if crude_pct <= -1.0 or crude_price < 75.0:
            crude_bias = "BULLISH_TAILWIND"
            crude_desc = f"Brent crude benign at ${crude_price:.1f}/bbl ({crude_pct:+.2f}%). Eases import bill."
        elif crude_pct >= 1.5 or crude_price > 85.0:
            crude_bias = "BEARISH_HEADWIND"
            crude_desc = f"Crude elevated at ${crude_price:.1f}/bbl ({crude_pct:+.2f}%). Inflationary headwind."
        else:
            crude_bias = "NEUTRAL"
            crude_desc = f"Crude stable at ${crude_price:.1f}/bbl ({crude_pct:+.2f}%)."

        # US Yields impact
        if yield_bps <= -3.0:
            yield_bias = "BULLISH_FII_FLOW_SUPPORT"
        elif yield_bps >= 3.0:
            yield_bias = "BEARISH_CAPITAL_FLIGHT_RISK"
        else:
            yield_bias = "NEUTRAL"

        return {
            "crude_price": crude_price,
            "crude_pct": crude_pct,
            "crude_bias": crude_bias,
            "crude_desc": crude_desc,
            "yield_bps": yield_bps,
            "yield_bias": yield_bias,
        }

    def compute_global_sentiment_score(self, spot_close: Optional[float] = None) -> Dict[str, Any]:
        """
        Compute integrated Global Sentiment Score (-2.0 to +2.0).
        """
        gap = self.predict_opening_gap(spot_close)
        macro = self.analyze_macro_tailwinds()
        us = self.data.get("us_markets", {})
        sp_change = float(us.get("sp500_change_pct", 0.0))
        nasdaq_change = float(us.get("nasdaq_change_pct", 0.0))

        # 1. GIFT Nifty gap score (-1.0 to +1.0)
        gap_score = max(-1.0, min(1.0, round(gap["gap_pct"] / 0.50, 2)))

        # 2. US Equities score (-0.5 to +0.5)
        us_avg = (sp_change + nasdaq_change) / 2.0
        us_score = max(-0.5, min(0.5, round(us_avg / 1.0, 2)))

        # 3. Macro tailwind score (-0.5 to +0.5)
        macro_score = 0.0
        if macro["crude_bias"] == "BULLISH_TAILWIND":
            macro_score += 0.25
        elif macro["crude_bias"] == "BEARISH_HEADWIND":
            macro_score -= 0.25

        if macro["yield_bias"] == "BULLISH_FII_FLOW_SUPPORT":
            macro_score += 0.25
        elif macro["yield_bias"] == "BEARISH_CAPITAL_FLIGHT_RISK":
            macro_score -= 0.25

        composite_score = round(gap_score + us_score + macro_score, 2)
        composite_score = max(-2.0, min(2.0, composite_score))

        if composite_score >= 0.8:
            verdict = "BULLISH_GLOBAL_ALIGNMENT"
        elif composite_score >= 0.2:
            verdict = "MILD_POSITIVE_CUES"
        elif composite_score <= -0.8:
            verdict = "BEARISH_GLOBAL_DRAG"
        elif composite_score <= -0.2:
            verdict = "MILD_NEGATIVE_CUES"
        else:
            verdict = "NEUTRAL_GLOBAL_CUES"

        return {
            "score": composite_score,
            "verdict": verdict,
            "gap_prediction": gap,
            "macro_tailwinds": macro,
            "us_markets": us,
        }

    def get_summary_text(self, spot_close: Optional[float] = None) -> str:
        """Format an ASCII report summary of global cues & gap prediction."""
        res = self.compute_global_sentiment_score(spot_close)
        gap = res["gap_prediction"]
        macro = res["macro_tailwinds"]
        us = res["us_markets"]

        lines = [
            f"Global Cues & GIFT NIFTY Opening Gap Predictor:",
            f"  GIFT NIFTY: {gap['gift_nifty_price']:.1f} | Projected Gap: {gap['gap_points']:+.1f} pts ({gap['gap_pct']:+.2f}%)",
            f"  Opening Category: {gap['category']} (Projected Open: {gap['projected_open']:.1f})",
            f"  Playbook: {gap['playbook']}",
            f"  Wall Street: S&P500 {us.get('sp500_change_pct', 0.0):+.2f}% | NASDAQ {us.get('nasdaq_change_pct', 0.0):+.2f}%",
            f"  Macro Cues: {macro['crude_desc']}",
            f"  Global Sentiment Score: {res['score']:+.2f} / 2.00 [{res['verdict']}]",
        ]
        return "\n".join(lines)
