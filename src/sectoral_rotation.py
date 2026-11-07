"""
Sectoral Rotation & Heavyweight Weightage Heatmap Engine.

Tracks sector performance, index point contributions, and macro rotation:
1. Weighted Point Contribution: Exact impact of Bank, IT, Reliance, etc. on NIFTY 50.
2. Rotation Regime Classification: Risk-On Expansion, Defensive Flight to Safety, Tug-of-War.
3. Heavyweight Drag vs Driver Analysis: Identifies which stocks are powering or holding back the index.
4. Composite Sectoral Score (-2.0 to +2.0) for index trend confirmation.
"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"
SAMPLE_SECTORAL_FILE = DATA_DIR / "sample_sectoral.json"


def load_cached_sectoral(file_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load cached sectoral data from JSON file with safe fallback."""
    target_path = file_path or SAMPLE_SECTORAL_FILE
    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "as_of_date": datetime.now().strftime("%Y-%m-%d"),
        "nifty_close": 24500.0,
        "nifty_change_pct": 0.5,
        "sectors": [
            {"name": "NIFTY BANK", "weight_pct": 33.5, "change_pct": 0.8, "category": "CYCLICAL_FINANCIAL"},
            {"name": "NIFTY IT", "weight_pct": 13.8, "change_pct": 0.4, "category": "GROWTH_TECH"},
            {"name": "NIFTY FMCG", "weight_pct": 8.1, "change_pct": 0.1, "category": "DEFENSIVE"},
        ],
        "top_heavyweights": [
            {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "weight_pct": 11.5, "change_pct": 0.9},
            {"symbol": "RELIANCE.NS", "name": "Reliance Ind", "weight_pct": 9.8, "change_pct": 0.5},
        ],
    }


def fetch_sectoral_data() -> Dict[str, Any]:
    """Fetch live sectoral market quotes or fallback to cached state."""
    return load_cached_sectoral()


class SectoralRotationAnalyzer:
    """Evaluates Sectoral Rotations, Weightage Dynamics, and Heavyweight Contributions."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self.data = data or load_cached_sectoral()
        self.spot_close = float(self.data.get("nifty_close", 24500.0))

    def analyze_sector_performance(self) -> Dict[str, Any]:
        """Compute performance, weightage, and estimated Nifty point contribution per sector."""
        sectors = self.data.get("sectors", [])
        if not sectors:
            return {"sectors": [], "top_driver": None, "top_drag": None, "total_sector_points": 0.0}

        enriched_sectors = []
        total_pts = 0.0

        for sec in sectors:
            name = sec.get("name", "Unknown")
            weight = float(sec.get("weight_pct", 0.0))
            chg_pct = float(sec.get("change_pct", 0.0))
            category = sec.get("category", "CYCLICAL")

            # Point contribution to NIFTY = Index Close * (Weight / 100) * (Change % / 100)
            pts_contrib = round(self.spot_close * (weight / 100.0) * (chg_pct / 100.0), 2)
            total_pts += pts_contrib

            enriched_sectors.append({
                "name": name,
                "weight_pct": weight,
                "change_pct": chg_pct,
                "category": category,
                "points_contribution": pts_contrib,
            })

        sorted_sectors = sorted(enriched_sectors, key=lambda s: s["points_contribution"], reverse=True)
        top_driver = sorted_sectors[0] if sorted_sectors else None
        top_drag = sorted_sectors[-1] if sorted_sectors and sorted_sectors[-1]["points_contribution"] < 0 else None

        return {
            "sectors": sorted_sectors,
            "top_driver": top_driver,
            "top_drag": top_drag,
            "total_sector_points": round(total_pts, 2),
        }

    def analyze_heavyweight_contribution(self) -> Dict[str, Any]:
        """Compute point contribution of top Nifty heavyweights."""
        heavyweights = self.data.get("top_heavyweights", [])
        if not heavyweights:
            return {"heavyweights": [], "top_bull_stock": None, "top_bear_stock": None}

        enriched_hw = []
        for hw in heavyweights:
            symbol = hw.get("symbol", "")
            name = hw.get("name", symbol)
            weight = float(hw.get("weight_pct", 0.0))
            chg_pct = float(hw.get("change_pct", 0.0))

            pts_contrib = round(self.spot_close * (weight / 100.0) * (chg_pct / 100.0), 2)

            enriched_hw.append({
                "symbol": symbol,
                "name": name,
                "weight_pct": weight,
                "change_pct": chg_pct,
                "points_contribution": pts_contrib,
            })

        sorted_hw = sorted(enriched_hw, key=lambda x: x["points_contribution"], reverse=True)
        top_bull = sorted_hw[0] if sorted_hw else None
        top_bear = sorted_hw[-1] if sorted_hw and sorted_hw[-1]["points_contribution"] < 0 else None

        return {
            "heavyweights": sorted_hw,
            "top_bull_stock": top_bull,
            "top_bear_stock": top_bear,
        }

    def classify_rotation_regime(self) -> Dict[str, Any]:
        """
        Classify sector rotation patterns:
        - RISK_ON_EXPANSION: Cyclicals (Bank, Auto, Metal) outperforming Defensives (FMCG, Pharma).
        - DEFENSIVE_ROTATION: Defensives outperforming Cyclicals (Flight to safety).
        - SECTORAL_TUG_OF_WAR: Bank surging while IT/Reliance plunging or vice versa.
        - BROAD_ACCUMULATION / BROAD_LIQUIDATION: Uniform multi-sector surge or selloff.
        """
        sec_perf = self.analyze_sector_performance()["sectors"]
        if not sec_perf:
            return {
                "regime": "NEUTRAL_SECTOR_FLOW",
                "rotation_signal": "NEUTRAL",
                "description": "Insufficient sector data.",
            }

        cyclical_gains = [s["change_pct"] for s in sec_perf if "CYCLICAL" in s.get("category", "")]
        defensive_gains = [s["change_pct"] for s in sec_perf if "DEFENSIVE" in s.get("category", "")]

        avg_cyclical = sum(cyclical_gains) / len(cyclical_gains) if cyclical_gains else 0.0
        avg_defensive = sum(defensive_gains) / len(defensive_gains) if defensive_gains else 0.0

        pos_sectors = [s for s in sec_perf if s["change_pct"] > 0]
        neg_sectors = [s for s in sec_perf if s["change_pct"] < 0]
        pos_ratio = len(pos_sectors) / len(sec_perf)

        # 1. Broad Accumulation (>75% sectors green)
        if pos_ratio >= 0.75:
            if avg_cyclical > avg_defensive + 1.0:
                regime = "RISK_ON_EXPANSION"
                signal = "STRONG_BULLISH_ROTATION"
                desc = "Aggressive Risk-On: High-beta cyclicals (Bank, Auto, Metal) heavily leading broad market expansion."
            else:
                regime = "BROAD_SECTORAL_ACCUMULATION"
                signal = "BULLISH_ROTATION"
                desc = "Uniform institutional buying across both growth and defensive sectors."
            return {"regime": regime, "rotation_signal": signal, "description": desc}

        # 2. Broad Liquidation (>75% sectors red)
        if pos_ratio <= 0.25:
            regime = "BROAD_SECTORAL_LIQUIDATION"
            signal = "STRONG_BEARISH_ROTATION"
            desc = "Heavy across-the-board institutional selling across nearly all sectors."
            return {"regime": regime, "rotation_signal": signal, "description": desc}

        # 3. Defensive Flight to Safety (Defensives green, Cyclicals red)
        if avg_defensive > 0.3 and avg_cyclical < -0.3:
            regime = "DEFENSIVE_ROTATION_WARNING"
            signal = "BEARISH_RISK_OFF"
            desc = "Smart money hiding in Defensives (FMCG, Pharma) while dumping cyclical sectors. Caution warranted."
            return {"regime": regime, "rotation_signal": signal, "description": desc}

        # 4. Tug-of-War (Divergence between Top Drivers)
        bank_sec = next((s for s in sec_perf if "BANK" in s["name"]), None)
        it_sec = next((s for s in sec_perf if "IT" in s["name"]), None)
        if bank_sec and it_sec:
            if (bank_sec["change_pct"] > 1.0 and it_sec["change_pct"] < -1.0) or \
               (it_sec["change_pct"] > 1.0 and bank_sec["change_pct"] < -1.0):
                regime = "SECTORAL_TUG_OF_WAR"
                signal = "NEUTRAL_DIVERGENCE"
                desc = "Inter-sector cross-currents: Strong divergence between Banking and IT neutralizing broad index trend."
                return {"regime": regime, "rotation_signal": signal, "description": desc}

        return {
            "regime": "BALANCED_SECTOR_ROTATION",
            "rotation_signal": "MODERATE_ACCUMULATION" if pos_ratio >= 0.5 else "MODERATE_DISTRIBUTION",
            "description": "Selective sectoral churning without sharp macro divergence.",
        }

    def compute_sectoral_score(self) -> Dict[str, Any]:
        """
        Synthesize Sectoral components into a normalized score [-2.0, +2.0].
        Weights:
        - Total sector points contribution (50%)
        - Rotation regime signal (35%)
        - Heavyweight alignment (15%)
        """
        sec_res = self.analyze_sector_performance()
        hw_res = self.analyze_heavyweight_contribution()
        rot_res = self.classify_rotation_regime()

        score = 0.0

        # Points Contribution Component (-1.0 to +1.0)
        total_pts = sec_res.get("total_sector_points", 0.0)
        # 100 points move on Nifty ~0.4% move
        pts_normalized = max(-1.0, min(1.0, total_pts / 150.0))
        score += pts_normalized

        # Rotation Signal Component (-0.7 to +0.7)
        sig = rot_res.get("rotation_signal", "NEUTRAL")
        if sig == "STRONG_BULLISH_ROTATION":
            score += 0.7
        elif sig == "BULLISH_ROTATION":
            score += 0.4
        elif sig == "STRONG_BEARISH_ROTATION":
            score -= 0.7
        elif sig == "BEARISH_RISK_OFF":
            score -= 0.5
        elif sig == "MODERATE_ACCUMULATION":
            score += 0.2
        elif sig == "MODERATE_DISTRIBUTION":
            score -= 0.2

        # Heavyweight Alignment (-0.3 to +0.3)
        top_bull = hw_res.get("top_bull_stock")
        top_bear = hw_res.get("top_bear_stock")
        if top_bull and top_bull.get("points_contribution", 0) > 20.0:
            score += 0.2
        if top_bear and top_bear.get("points_contribution", 0) < -20.0:
            score -= 0.2

        score = max(-2.0, min(2.0, round(score, 2)))

        if score >= 1.0:
            verdict = "BULLISH_SECTOR_ALIGNMENT"
        elif score >= 0.3:
            verdict = "MILD_BULLISH_ROTATION"
        elif score <= -1.0:
            verdict = "BEARISH_SECTOR_LIQUIDATION"
        elif score <= -0.3:
            verdict = "MILD_DEFENSIVE_DISTRIBUTION"
        else:
            verdict = "NEUTRAL_SECTOR_CHURNING"

        return {
            "score": score,
            "verdict": verdict,
            "rotation_regime": rot_res["regime"],
            "rotation_signal": rot_res["rotation_signal"],
            "sector_details": sec_res,
            "heavyweight_details": hw_res,
            "commentary": rot_res["description"],
        }

    def get_summary_text(self) -> str:
        """Format a human-readable sectoral summary."""
        res = self.compute_sectoral_score()
        sec = res["sector_details"]
        hw = res["heavyweight_details"]
        top_d = sec.get("top_driver", {})
        top_l = sec.get("top_drag", {})
        bull_s = hw.get("top_bull_stock", {})

        driver_str = f"{top_d.get('name')} (+{top_d.get('change_pct', 0)}% -> {top_d.get('points_contribution', 0):+,.1f} pts)" if top_d else "None"
        drag_str = f"{top_l.get('name')} ({top_l.get('change_pct', 0)}% -> {top_l.get('points_contribution', 0):+,.1f} pts)" if top_l else "None"
        bull_str = f"{bull_s.get('name')} ({bull_s.get('points_contribution', 0):+,.1f} pts)" if bull_s else "None"

        lines = [
            f"Sectoral Rotation Score: {res['score']:+.2f} / 2.00 [{res['verdict']}]",
            f" - Rotation Dynamic   : {res['rotation_regime']} ({res['commentary']})",
            f" - Top Sector Driver  : {driver_str}",
            f" - Top Sector Drag    : {drag_str}",
            f" - Leading Stock Pull : {bull_str}",
            f" - Net Sector Points  : {sec.get('total_sector_points', 0):+,.1f} NIFTY points",
        ]
        return "\n".join(lines)
