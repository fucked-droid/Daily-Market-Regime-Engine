"""
Market Breadth & Advance-Decline (A/D) Ratio Divergence Module.

Provides:
1. Ingestion of NIFTY 50 Advance / Decline / Unchanged stock counts.
2. Advance-to-Decline Ratio (ADR) calculation.
3. "Hollow Rally" divergence detection (Index up driven by 1-2 heavyweights while breadth declines).
4. Breadth Momentum Score (-2 to +2) to confirm or refute price breakouts.
"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"
SAMPLE_BREADTH = DATA_DIR / "sample_breadth.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def load_cached_breadth(filepath: Optional[Path] = None) -> Dict[str, Any]:
    """Load cached sample market breadth data."""
    target_path = filepath or SAMPLE_BREADTH
    if not target_path.exists():
        raise FileNotFoundError(f"Market breadth data file not found at {target_path}")
    with open(target_path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_market_breadth(timeout: int = 6) -> Dict[str, Any]:
    """
    Fetch live NIFTY 50 advance/decline breadth from NSE India API.
    Falls back gracefully to cached sample dataset if offline or blocked.
    """
    url = "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.nseindia.com",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, dict):
                advances = int(data.get("advances", 0))
                declines = int(data.get("declines", 0))
                unchanged = int(data.get("unchanged", 0))
                stocks = data.get("data", [])
                
                # Extract top movers if stocks list is available
                top_gainers = []
                top_losers = []
                sorted_stocks = sorted(
                    [s for s in stocks if "pChange" in s and s.get("symbol") != "NIFTY 50"],
                    key=lambda x: float(x.get("pChange", 0.0)),
                    reverse=True
                )
                if sorted_stocks:
                    for s in sorted_stocks[:5]:
                        top_gainers.append({"symbol": s.get("symbol"), "change_pct": round(float(s.get("pChange", 0)), 2)})
                    for s in sorted_stocks[-3:]:
                        top_losers.append({"symbol": s.get("symbol"), "change_pct": round(float(s.get("pChange", 0)), 2)})

                return {
                    "timestamp": datetime.now().isoformat(),
                    "index": "NIFTY 50",
                    "advances": advances,
                    "declines": declines,
                    "unchanged": unchanged,
                    "total": advances + declines + unchanged,
                    "top_gainers": top_gainers,
                    "top_losers": top_losers,
                }
    except Exception:
        pass

    return load_cached_breadth()


class MarketBreadthAnalyzer:
    """Analyzes market breadth statistics and detects divergence traps."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self.data = data or load_cached_breadth()

    def get_adr(self) -> float:
        """Calculate Advance-to-Decline Ratio (ADR)."""
        adv = self.data.get("advances", 0)
        dec = self.data.get("declines", 0)
        if dec == 0:
            return round(float(adv), 2)
        return round(adv / dec, 2)

    def detect_divergence(self, index_change_pct: float = 0.0) -> Dict[str, Any]:
        """
        Detect divergence between Index price performance and internal stock breadth.
        
        Classic Traps:
        - Hollow Rally: Index is up (+0.2%+), but ADR < 0.8 (fewer stocks advancing).
        - Accumulation Dip: Index is down (-0.2%+), but ADR > 1.2 (more stocks advancing).
        """
        adv = self.data.get("advances", 0)
        dec = self.data.get("declines", 0)
        total = self.data.get("total", 50) or 50
        adr = self.get_adr()
        advance_pct = round((adv / total) * 100, 1)

        # Divergence rules
        if index_change_pct >= 0.25 and adr < 0.8:
            status = "HOLLOW_RALLY_WARNING"
            signal = "BEARISH_DIVERGENCE_TRAP"
            desc = (
                f"NIFTY is up (+{index_change_pct:.2f}%), but breadth is weak (ADR: {adr:.2f}, "
                f"Declines: {dec} > Advances: {adv}). Rally driven by select heavyweights."
            )
        elif index_change_pct <= -0.25 and adr > 1.2:
            status = "BULLISH_ABSORPTION_ACCUMULATION"
            signal = "BULLISH_DIVERGENCE"
            desc = (
                f"NIFTY is down ({index_change_pct:.2f}%), but majority stocks advancing (ADR: {adr:.2f}, "
                f"Advances: {adv} > Declines: {dec}). Institutional accumulation on dip."
            )
        elif index_change_pct >= 0.2 and adr >= 1.8:
            status = "BROAD_BASED_EXPANSION"
            signal = "BULLISH_CONFIRMATION"
            desc = (
                f"Healthy rally: Index (+{index_change_pct:.2f}%) confirmed by wide market participation "
                f"(Advances: {adv}/50, ADR: {adr:.2f})."
            )
        elif index_change_pct <= -0.2 and adr <= 0.5:
            status = "BROAD_BASED_LIQUIDATION"
            signal = "BEARISH_CONFIRMATION"
            desc = (
                f"Aggressive selling across sectors (Declines: {dec}/50, ADR: {adr:.2f}). Downside confirmed."
            )
        else:
            status = "BALANCED_PARTICIPATION"
            signal = "NEUTRAL"
            desc = f"Market breadth in equilibrium (Advances: {adv}, Declines: {dec}, ADR: {adr:.2f})."

        return {
            "advances": adv,
            "declines": dec,
            "unchanged": self.data.get("unchanged", 0),
            "total": total,
            "advance_pct": advance_pct,
            "adr": adr,
            "index_change_pct": index_change_pct,
            "status": status,
            "signal": signal,
            "description": desc,
        }

    def compute_breadth_score(self, index_change_pct: float = 0.0) -> Dict[str, Any]:
        """
        Compute normalized Market Breadth Score (-2.0 to +2.0).
        """
        div = self.detect_divergence(index_change_pct)
        adv = div["advances"]
        dec = div["declines"]
        total = div["total"] or 50

        # Net advance proportion: (Adv - Dec) / Total -> range [-1.0, 1.0]
        net_ratio = (adv - dec) / total

        # Map net_ratio to -2.0 to +2.0
        score = round(net_ratio * 2.0, 2)

        # Divergence penalty / bonus
        if div["status"] == "HOLLOW_RALLY_WARNING":
            score = min(score, -0.5)  # Cap score in hollow rally
        elif div["status"] == "BULLISH_ABSORPTION_ACCUMULATION":
            score = max(score, 0.5)

        score = max(-2.0, min(2.0, score))

        if score >= 0.8:
            regime = "STRONG_BULLISH_BREADTH"
        elif score >= 0.25:
            regime = "MODERATE_BULLISH_BREADTH"
        elif score <= -0.8:
            regime = "STRONG_BEARISH_BREADTH"
        elif score <= -0.25:
            regime = "MODERATE_BEARISH_BREADTH"
        else:
            regime = "NEUTRAL_BREADTH"

        return {
            "score": score,
            "regime": regime,
            "divergence_details": div,
        }

    def get_summary_text(self, index_change_pct: float = 0.0) -> str:
        """Format an ASCII report summary of market breadth."""
        res = self.compute_breadth_score(index_change_pct)
        d = res["divergence_details"]
        lines = [
            f"Market Breadth (NIFTY 50):",
            f"  Advances: {d['advances']} | Declines: {d['declines']} | Unchanged: {d['unchanged']} | ADR: {d['adr']:.2f}",
            f"  Signal: {d['signal']} ({d['status']})",
            f"  Breadth Score: {res['score']:+.2f} / 2.00 [{res['regime']}]",
            f"  Insight: {d['description']}",
        ]
        return "\n".join(lines)
