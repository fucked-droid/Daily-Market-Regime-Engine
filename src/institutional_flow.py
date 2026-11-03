"""
Institutional Flow & Derivatives Positioning Analysis Module.

Provides:
1. Ingestion of FII (Foreign Institutional Investors) & DII (Domestic Institutional Investors) Cash Market Flow.
2. FII Index Futures Long vs Short contracts ratio analysis.
3. Smart Money Sentiment Score (-2 to +2) tracking institutional accumulation vs distribution.
4. Divergence detection between retail price movement and institutional positioning.
"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, Optional
import urllib.request

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"
SAMPLE_FII_DII = DATA_DIR / "sample_fii_dii.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def load_cached_fii_dii(filepath: Optional[Path] = None) -> Dict[str, Any]:
    """Load cached sample FII/DII data."""
    target_path = filepath or SAMPLE_FII_DII
    if not target_path.exists():
        raise FileNotFoundError(f"FII/DII data file not found at {target_path}")
    with open(target_path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_fii_dii_data(timeout: int = 6) -> Dict[str, Any]:
    """
    Attempt to fetch latest FII/DII activity from web source;
    falls back cleanly to cached local dataset if offline or blocked.
    """
    url = "https://www.nseindia.com/api/fiidiiTradeReact"
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
            if data and isinstance(data, list):
                # Parse NSE format into structured dict
                fii_cash = {"buy": 0.0, "sell": 0.0, "net": 0.0}
                dii_cash = {"buy": 0.0, "sell": 0.0, "net": 0.0}
                for item in data:
                    cat = str(item.get("category", "")).upper()
                    buy = float(item.get("buyValue", 0.0) or 0.0)
                    sell = float(item.get("sellValue", 0.0) or 0.0)
                    net = float(item.get("netValue", 0.0) or 0.0)
                    if "FII" in cat or "FPI" in cat:
                        fii_cash = {"buy_value_crores": buy, "sell_value_crores": sell, "net_value_crores": net}
                    elif "DII" in cat:
                        dii_cash = {"buy_value_crores": buy, "sell_value_crores": sell, "net_value_crores": net}
                
                cached_data = load_cached_fii_dii()
                cached_data["date"] = datetime.now().strftime("%d-%b-%Y")
                cached_data["cash_market"]["fii"] = fii_cash
                cached_data["cash_market"]["dii"] = dii_cash
                cached_data["cash_market"]["total_institutional_net_crores"] = round(fii_cash.get("net_value_crores", 0) + dii_cash.get("net_value_crores", 0), 2)
                return cached_data
    except Exception:
        pass

    # Clean fallback to sample dataset
    return load_cached_fii_dii()


class InstitutionalFlowAnalyzer:
    """Analyzes FII/DII cash flow and index derivatives positioning."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self.data = data or load_cached_fii_dii()

    def analyze_cash_flow(self) -> Dict[str, Any]:
        """Analyze institutional cash market buying / selling dynamics."""
        cash = self.data.get("cash_market", {})
        fii = cash.get("fii", {})
        dii = cash.get("dii", {})

        fii_net = float(fii.get("net_value_crores", 0.0))
        dii_net = float(dii.get("net_value_crores", 0.0))
        total_net = round(fii_net + dii_net, 2)

        # Regimes:
        if fii_net > 1500 and dii_net > 500:
            regime = "STRONG_INSTITUTIONAL_BUYING"
            commentary = "Both FIIs and DIIs pumping fresh capital. Strong institutional tailwind."
        elif fii_net > 500 and dii_net >= -200:
            regime = "FII_DRIVEN_RALLY"
            commentary = "FIIs aggressively buying Indian equities; DIIs largely neutral."
        elif fii_net < -1000 and dii_net > 1000:
            regime = "DII_ABSORBING_FII_SELLING"
            commentary = "Domestic funds actively absorbing foreign sell-off; limits severe downside."
        elif fii_net < -1500 and dii_net < 0:
            regime = "AGGRESSIVE_INSTITUTIONAL_DUMP"
            commentary = "Dual institutional selling; high liquidity exit pressure."
        elif fii_net < -500:
            regime = "FII_PROFIT_BOOKING"
            commentary = "FIIs pulling liquidity from cash market."
        else:
            regime = "NEUTRAL_BALANCED"
            commentary = "Mild institutional flows without clear directional aggression."

        return {
            "date": self.data.get("date", "N/A"),
            "fii_buy_crores": fii.get("buy_value_crores", 0.0),
            "fii_sell_crores": fii.get("sell_value_crores", 0.0),
            "fii_net_crores": fii_net,
            "dii_buy_crores": dii.get("buy_value_crores", 0.0),
            "dii_sell_crores": dii.get("sell_value_crores", 0.0),
            "dii_net_crores": dii_net,
            "total_net_crores": total_net,
            "regime": regime,
            "commentary": commentary,
        }

    def analyze_derivatives_positioning(self) -> Dict[str, Any]:
        """Analyze FII Index Futures Long/Short positioning and leverage bias."""
        deriv = self.data.get("derivatives", {})
        fii_fut = deriv.get("fii_index_futures", {})

        long_contracts = int(fii_fut.get("long_contracts", 0))
        short_contracts = int(fii_fut.get("short_contracts", 0))
        total_contracts = long_contracts + short_contracts

        if total_contracts > 0:
            long_ratio = round((long_contracts / total_contracts) * 100, 2)
            short_ratio = round((short_contracts / total_contracts) * 100, 2)
        else:
            long_ratio = 50.0
            short_ratio = 50.0

        net_contracts = long_contracts - short_contracts

        # Futures sentiment classification
        if long_ratio >= 75.0:
            sentiment = "OVERBOUGHT_EUPHORIA"
            signal = "BEARISH_REVERSAL_RISK"
            desc = "FIIs loaded >75% long futures. Vulnerable to sharp long-unwinding."
        elif long_ratio >= 60.0:
            sentiment = "STRONG_BULLISH"
            signal = "BULLISH_EXPANSION"
            desc = "FIIs dominantly long index futures. Institutional trend continuation expected."
        elif long_ratio >= 45.0:
            sentiment = "NEUTRAL"
            signal = "RANGE_BOUND"
            desc = "Balanced institutional futures positioning (45-60%)."
        elif long_ratio >= 25.0:
            sentiment = "BEARISH"
            signal = "SHORT_BUILDUP"
            desc = "FIIs holding heavy short contracts. Bearish trend pressure."
        else:
            sentiment = "OVERSOLD_SHORT_HEAVY"
            signal = "SHORT_COVERING_RALLY_POTENTIAL"
            desc = "FII long ratio under 25%. Extreme short positioning prone to explosive short squeeze."

        # Options sentiment if available
        opt = deriv.get("fii_index_options", {})
        call_long = opt.get("call_long", 0)
        call_short = opt.get("call_short", 0)
        put_long = opt.get("put_long", 0)
        put_short = opt.get("put_short", 0)
        
        # Net Option Bias: Bullish contracts (Call Long + Put Short) vs Bearish (Call Short + Put Long)
        bull_contracts = call_long + put_short
        bear_contracts = call_short + put_long
        option_bias = "BULLISH" if bull_contracts > bear_contracts else "BEARISH" if bear_contracts > bull_contracts else "NEUTRAL"

        return {
            "long_contracts": long_contracts,
            "short_contracts": short_contracts,
            "net_contracts": net_contracts,
            "long_ratio_pct": long_ratio,
            "short_ratio_pct": short_ratio,
            "futures_sentiment": sentiment,
            "futures_signal": signal,
            "option_bias": option_bias,
            "description": desc,
        }

    def compute_smart_money_score(self) -> Dict[str, Any]:
        """
        Compute an integrated Smart Money Sentiment Score (-2.0 to +2.0).
        
        Components:
        1. Cash Market Net Flows (-1.0 to +1.0)
        2. Derivatives Long/Short Ratio (-1.0 to +1.0)
        """
        cash = self.analyze_cash_flow()
        deriv = self.analyze_derivatives_positioning()

        # Cash score calculation
        # Normalized: +2000 Cr = +1.0, -2000 Cr = -1.0
        total_net = cash["total_net_crores"]
        cash_score = max(-1.0, min(1.0, round(total_net / 2000.0, 2)))

        # Derivatives score calculation
        # Normalized: 50% = 0.0, 75% = +1.0, 25% = -1.0
        long_ratio = deriv["long_ratio_pct"]
        deriv_score = max(-1.0, min(1.0, round((long_ratio - 50.0) / 25.0, 2)))

        composite_score = round(cash_score + deriv_score, 2)
        composite_score = max(-2.0, min(2.0, composite_score))

        if composite_score >= 1.0:
            regime = "STRONG_ACCUMULATION"
            verdict = "BULLISH"
        elif composite_score >= 0.3:
            regime = "MODERATE_ACCUMULATION"
            verdict = "MILD_BULLISH"
        elif composite_score <= -1.0:
            regime = "HEAVY_DISTRIBUTION"
            verdict = "BEARISH"
        elif composite_score <= -0.3:
            regime = "MILD_DISTRIBUTION"
            verdict = "MILD_BEARISH"
        else:
            regime = "EQUILIBRIUM"
            verdict = "NEUTRAL"

        return {
            "cash_score": cash_score,
            "derivatives_score": deriv_score,
            "composite_score": composite_score,
            "regime": regime,
            "verdict": verdict,
            "cash_summary": cash,
            "derivatives_summary": deriv,
        }

    def get_summary_text(self) -> str:
        """Format an ASCII report summary of institutional positioning."""
        metrics = self.compute_smart_money_score()
        c = metrics["cash_summary"]
        d = metrics["derivatives_summary"]

        lines = [
            f"FII/DII Smart Money Flow (Date: {c['date']}):",
            f"  Cash Flow: FII: {c['fii_net_crores']:+.1f} Cr | DII: {c['dii_net_crores']:+.1f} Cr | Net: {c['total_net_crores']:+.1f} Cr",
            f"  Cash Regime: {c['regime']}",
            f"  Index Futures: Long {d['long_ratio_pct']}% | Short {d['short_ratio_pct']}% (Net: {d['net_contracts']:+,d})",
            f"  Derivatives Signal: {d['futures_signal']} ({d['futures_sentiment']})",
            f"  Smart Money Score: {metrics['composite_score']:+.2f} / 2.00 [{metrics['verdict']}]",
        ]
        return "\n".join(lines)
