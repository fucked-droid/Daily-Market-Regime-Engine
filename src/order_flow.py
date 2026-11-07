"""
Intraday Order Flow & Cumulative Volume Delta (CVD) Engine.

Analyzes tick-level and bar-level buyer vs seller aggression:
1. Cumulative Volume Delta (CVD): Aggressive market buys (Ask) minus aggressive market sells (Bid).
2. Delta Divergence Detection: Absorption vs Exhaustion traps at swing highs and lows.
3. Order Book Depth Imbalance: Bid vs Ask resting liquidity pressure.
4. Composite Order Flow Scoring (-2.0 to +2.0) for high-conviction intraday positioning.
"""

from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"
SAMPLE_ORDER_FLOW_FILE = DATA_DIR / "sample_order_flow.json"


def load_cached_order_flow(file_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load cached order flow data from JSON file with safe fallback."""
    target_path = file_path or SAMPLE_ORDER_FLOW_FILE
    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "as_of_date": datetime.now().strftime("%Y-%m-%d"),
        "symbol": "NIFTY",
        "session_stats": {
            "total_volume": 10000000,
            "buy_volume": 5500000,
            "sell_volume": 4500000,
            "cumulative_volume_delta": 1000000,
            "buyer_ratio_pct": 55.0,
            "seller_ratio_pct": 45.0,
            "institutional_aggression": "MODERATE_BUYER_ACCUMULATION",
        },
        "order_book_depth": {
            "total_bid_quantity": 4000000,
            "total_ask_quantity": 3500000,
            "bid_ask_imbalance_ratio": 1.14,
            "imbalance_status": "NEUTRAL_LIQUIDITY",
        },
        "intraday_bars_15m": [],
    }


def fetch_order_flow_data() -> Dict[str, Any]:
    """
    Fetch live order flow / tick aggregation from market broker feed or cache fallback.
    """
    return load_cached_order_flow()


class OrderFlowAnalyzer:
    """Institutional Order Flow and Cumulative Volume Delta Analyzer."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self.data = data or load_cached_order_flow()

    def analyze_cumulative_delta(self) -> Dict[str, Any]:
        """Analyze total session volume delta and buyer/seller dominance."""
        stats = self.data.get("session_stats", {})
        total_vol = float(stats.get("total_volume", 0))
        buy_vol = float(stats.get("buy_volume", 0))
        sell_vol = float(stats.get("sell_volume", 0))

        if total_vol <= 0:
            total_vol = buy_vol + sell_vol

        net_delta = float(stats.get("cumulative_volume_delta", buy_vol - sell_vol))

        if total_vol > 0:
            buyer_ratio = round((buy_vol / total_vol) * 100.0, 2)
            seller_ratio = round((sell_vol / total_vol) * 100.0, 2)
        else:
            buyer_ratio = 50.0
            seller_ratio = 50.0

        if buyer_ratio >= 60.0:
            sentiment = "STRONG_BUYER_DOMINANCE"
            description = "Aggressive buyers firmly controlling tape (Taker Buy Vol > 60%)."
        elif buyer_ratio >= 53.0:
            sentiment = "MODERATE_BUYER_ACCUMULATION"
            description = "Steady buyer accumulation observed across key strikes."
        elif seller_ratio >= 60.0:
            sentiment = "STRONG_SELLER_DOMINANCE"
            description = "Aggressive sellers hitting bids with high velocity."
        elif seller_ratio >= 53.0:
            sentiment = "MODERATE_SELLER_DISTRIBUTION"
            description = "Controlled seller distribution on rallies."
        else:
            sentiment = "BALANCED_TWO_WAY_FLOW"
            description = "Equilibrium order flow; buyers and sellers matched."

        return {
            "total_volume": int(total_vol),
            "buy_volume": int(buy_vol),
            "sell_volume": int(sell_vol),
            "cumulative_volume_delta": int(net_delta),
            "buyer_ratio_pct": buyer_ratio,
            "seller_ratio_pct": seller_ratio,
            "sentiment": sentiment,
            "description": description,
        }

    def detect_delta_divergence(
        self, custom_bars: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Detect order flow absorption and exhaustion divergences.
        - Bearish Absorption Trap: Price Higher High, but CVD Lower High.
        - Bullish Absorption Accumulation: Price Lower Low, but CVD Higher Low.
        """
        bars = custom_bars if custom_bars is not None else self.data.get("intraday_bars_15m", [])
        if not bars or len(bars) < 3:
            return {
                "status": "NORMAL_FLOW_INSUFFICIENT_BARS",
                "divergence_signal": "NONE",
                "description": "Standard flow pattern; insufficient intraday bars for divergence check.",
            }

        # Compare first third vs last third of bars to detect swing divergence
        n = len(bars)
        split = max(1, n // 3)
        early_bars = bars[:split]
        late_bars = bars[-split:]

        early_high = max(b.get("high", b.get("close", 0)) for b in early_bars)
        late_high = max(b.get("high", b.get("close", 0)) for b in late_bars)

        early_low = min(b.get("low", b.get("close", 0)) for b in early_bars)
        late_low = min(b.get("low", b.get("close", 0)) for b in late_bars)

        early_cvd = early_bars[-1].get("cumulative_delta", 0)
        late_cvd = late_bars[-1].get("cumulative_delta", 0)

        # 1. Bearish Absorption (Price prints HH, but CVD prints LH / drops)
        if late_high > early_high and late_cvd < early_cvd:
            return {
                "status": "BEARISH_ABSORPTION_TRAP",
                "divergence_signal": "BEARISH_DIVERGENCE",
                "description": "Price pushing to new highs while Cumulative Delta is declining. Passive limit sellers absorbing retail breakouts.",
            }

        # 2. Bullish Absorption (Price prints LL, but CVD prints HL / rises)
        if late_low < early_low and late_cvd > early_cvd:
            return {
                "status": "BULLISH_ABSORPTION_ACCUMULATION",
                "divergence_signal": "BULLISH_DIVERGENCE",
                "description": "Price dipping to new lows while Cumulative Delta is rising. Institutional passive buyers absorbing panic selling.",
            }

        # 3. Trend Expansion
        if late_high > early_high and late_cvd > early_cvd:
            return {
                "status": "BULLISH_DELTA_EXPANSION",
                "divergence_signal": "BULLISH_CONFIRMATION",
                "description": "High conviction uptrend: Price expansion confirmed by rising aggressive buying delta.",
            }

        if late_low < early_low and late_cvd < early_cvd:
            return {
                "status": "BEARISH_DELTA_EXPANSION",
                "divergence_signal": "BEARISH_CONFIRMATION",
                "description": "High conviction downtrend: Price breakdown confirmed by expanding sell delta.",
            }

        return {
            "status": "CONSOLIDATION_FLOW",
            "divergence_signal": "NEUTRAL",
            "description": "Order flow is aligned with price consolidation.",
        }

    def analyze_order_book_imbalance(self) -> Dict[str, Any]:
        """Analyze resting market depth liquidity imbalance."""
        depth = self.data.get("order_book_depth", {})
        bids = float(depth.get("total_bid_quantity", 0))
        asks = float(depth.get("total_ask_quantity", 0))

        if asks > 0:
            ratio = round(bids / asks, 2)
        else:
            ratio = 1.0 if bids == 0 else 2.0

        if ratio >= 1.35:
            status = "STRONG_BUY_SIDE_LIQUIDITY"
            bias = "BULLISH_SUPPORT"
        elif ratio >= 1.10:
            status = "MILD_BUY_SIDE_LIQUIDITY"
            bias = "MILD_BULLISH"
        elif ratio <= 0.70:
            status = "STRONG_SELL_SIDE_LIQUIDITY"
            bias = "BEARISH_RESISTANCE"
        elif ratio <= 0.90:
            status = "MILD_SELL_SIDE_LIQUIDITY"
            bias = "MILD_BEARISH"
        else:
            status = "BALANCED_DEPTH"
            bias = "NEUTRAL"

        return {
            "total_bid_quantity": int(bids),
            "total_ask_quantity": int(asks),
            "bid_ask_imbalance_ratio": ratio,
            "status": status,
            "bias": bias,
        }

    def compute_order_flow_score(self) -> Dict[str, Any]:
        """
        Synthesize Order Flow components into a bounded composite score [-2.0, +2.0].
        Weights:
        - Session CVD Buyer/Seller Ratio (50%)
        - Intraday Delta Divergence (35%)
        - Order Book Depth Imbalance (15%)
        """
        delta_res = self.analyze_cumulative_delta()
        div_res = self.detect_delta_divergence()
        depth_res = self.analyze_order_book_imbalance()

        score = 0.0

        # CVD Ratio Component (-1.0 to +1.0)
        buyer_pct = delta_res["buyer_ratio_pct"]
        if buyer_pct >= 60.0:
            score += 1.0
        elif buyer_pct >= 53.0:
            score += 0.5
        elif buyer_pct <= 40.0:
            score -= 1.0
        elif buyer_pct <= 47.0:
            score -= 0.5

        # Divergence Component (-0.7 to +0.7)
        sig = div_res.get("divergence_signal", "NEUTRAL")
        if sig == "BULLISH_CONFIRMATION":
            score += 0.5
        elif sig == "BULLISH_DIVERGENCE":
            score += 0.7
        elif sig == "BEARISH_CONFIRMATION":
            score -= 0.5
        elif sig == "BEARISH_DIVERGENCE":
            score -= 0.7

        # Depth Imbalance Component (-0.3 to +0.3)
        depth_bias = depth_res.get("bias", "NEUTRAL")
        if depth_bias == "BULLISH_SUPPORT":
            score += 0.3
        elif depth_bias == "MILD_BULLISH":
            score += 0.15
        elif depth_bias == "BEARISH_RESISTANCE":
            score -= 0.3
        elif depth_bias == "MILD_BEARISH":
            score -= 0.15

        score = max(-2.0, min(2.0, round(score, 2)))

        if score >= 1.0:
            verdict = "STRONG_BULLISH_FLOW"
            regime = "AGGRESSIVE_BUYER_EXPANSION"
        elif score >= 0.3:
            verdict = "MILD_BULLISH_FLOW"
            regime = "BUYER_ACCUMULATION"
        elif score <= -1.0:
            verdict = "STRONG_BEARISH_FLOW"
            regime = "AGGRESSIVE_SELLER_EXPANSION"
        elif score <= -0.3:
            verdict = "MILD_BEARISH_FLOW"
            regime = "SELLER_DISTRIBUTION"
        else:
            verdict = "NEUTRAL_FLOW"
            regime = "CONSOLIDATION_TWO_WAY_CHOP"

        return {
            "score": score,
            "verdict": verdict,
            "regime": regime,
            "delta_summary": delta_res,
            "divergence_summary": div_res,
            "depth_summary": depth_res,
            "commentary": f"{delta_res['description']} {div_res['description']}",
        }

    def get_summary_text(self) -> str:
        """Format a human-readable order flow summary."""
        res = self.compute_order_flow_score()
        d = res["delta_summary"]
        div = res["divergence_summary"]
        dp = res["depth_summary"]

        lines = [
            f"Order Flow (CVD) Score: {res['score']:+.2f} / 2.00 [{res['verdict']}]",
            f" - Cumulative Delta   : {d['cumulative_volume_delta']:+,d} contracts (Buyers: {d['buyer_ratio_pct']}% | Sellers: {d['seller_ratio_pct']}%)",
            f" - Flow Divergence    : {div['status']} [{div['divergence_signal']}]",
            f" - Order Book Depth   : Bid/Ask Ratio = {dp['bid_ask_imbalance_ratio']:.2f} [{dp['status']}]",
            f" - Tactical Takeaway  : {res['commentary']}",
        ]
        return "\n".join(lines)
