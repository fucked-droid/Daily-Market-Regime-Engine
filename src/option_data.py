"""
Option Chain Data & Institutional Positioning Analysis Module.

Provides:
1. Real-time / cached ingestion of NSE Option Chain data (NIFTY & indices).
2. Institutional Open Interest (OI) concentration (where Call/Put sellers sit).
3. Put-Call Ratio (PCR) analysis across OI, Volume, and Change in OI.
4. Max Pain calculation to determine gravitational expiry strike.
5. Option-implied momentum score (-2 to +2) to forecast daily & intraday momentum.
"""

from datetime import datetime
import http.cookiejar
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import urllib.request

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"
SAMPLE_OPTION_CHAIN = DATA_DIR / "sample_option_chain.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
NSE_HOME = "https://www.nseindia.com"
NSE_OPTION_URL = "https://www.nseindia.com/api/option-chain-indices?symbol="


def create_nse_opener(timeout: int = 8) -> urllib.request.OpenerDirector:
    """Create a urllib opener equipped with cookie jar handling and browser headers."""
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    opener.addheaders = [
        ("User-Agent", USER_AGENT),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"),
        ("Accept-Language", "en-US,en;q=0.9"),
        ("Referer", "https://www.nseindia.com/option-chain"),
        ("Connection", "keep-alive"),
    ]
    return opener


def fetch_nse_option_chain(
    symbol: str = "NIFTY",
    timeout: int = 10,
) -> Optional[Dict[str, Any]]:
    """
    Fetch live option chain data directly from NSE India API.
    Performs handshake to grab session cookies, then requests the option chain.
    Returns None if network is unavailable or blocked, allowing graceful fallback.
    """
    try:
        opener = create_nse_opener(timeout=timeout)
        # Step 1: Warm up session with homepage request to collect session cookies
        req_home = urllib.request.Request(NSE_HOME, headers={"User-Agent": USER_AGENT})
        with opener.open(req_home, timeout=timeout) as resp:
            _ = resp.read(1024)  # Read small chunk to prime cookies

        # Step 2: Request option chain data
        url = f"{NSE_OPTION_URL}{urllib.request.quote(symbol)}"
        req_data = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.nseindia.com/option-chain",
            },
        )
        with opener.open(req_data, timeout=timeout) as resp:
            if resp.status == 200:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
    except Exception:
        pass
    return None


def load_cached_option_chain(filepath: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load local cached or sample option chain JSON for offline execution or testing."""
    target_path = filepath or SAMPLE_OPTION_CHAIN
    if target_path and target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def calculate_max_pain(records_data: List[Dict[str, Any]]) -> float:
    """
    Calculate the Max Pain strike price.
    Max Pain is the strike at which option sellers (writers) collectively
    pay out the minimum amount to option buyers upon expiry.
    """
    if not records_data:
        return 0.0

    strikes = set()
    strike_data = {}

    for row in records_data:
        strike = row.get("strikePrice")
        if not strike:
            continue
        strikes.add(strike)
        ce = row.get("CE", {})
        pe = row.get("PE", {})
        strike_data[strike] = {
            "ce_oi": ce.get("openInterest", 0) if isinstance(ce, dict) else 0,
            "pe_oi": pe.get("openInterest", 0) if isinstance(pe, dict) else 0,
        }

    all_strikes = sorted(list(strikes))
    if not all_strikes:
        return 0.0

    min_loss = float("inf")
    max_pain_strike = all_strikes[0]

    for test_strike in all_strikes:
        total_loss = 0.0
        for strike in all_strikes:
            ce_oi = strike_data[strike]["ce_oi"]
            pe_oi = strike_data[strike]["pe_oi"]

            # Call loss: if test_strike > strike, calls are ITM
            if test_strike > strike:
                total_loss += (test_strike - strike) * ce_oi
            # Put loss: if test_strike < strike, puts are ITM
            elif test_strike < strike:
                total_loss += (strike - test_strike) * pe_oi

        if total_loss < min_loss:
            min_loss = total_loss
            max_pain_strike = test_strike

    return float(max_pain_strike)


def analyze_option_chain(
    data: Dict[str, Any],
    spot_price: Optional[float] = None,
    expiry_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Perform deep quantitative analysis of the option chain:
    - Identifies institutional buyer vs seller walls (Top Call/Put OI).
    - Computes Put-Call Ratio (PCR) across OI, Volume, and Change in OI.
    - Calculates Max Pain and ATM Straddle implied moves.
    - Produces an Option Momentum Score (-2 to +2) with explanatory reasoning.
    """
    records = data.get("records", {})
    all_data = records.get("data", [])
    expiry_dates = records.get("expiryDates", [])

    if not all_data:
        raise ValueError("Option chain contains no data records.")

    # Determine spot price
    if spot_price is None or spot_price <= 0:
        spot_price = float(records.get("underlyingValue", 0.0))
        if spot_price <= 0:
            # Fallback to ATM strike estimate from data
            valid_strikes = [r.get("strikePrice") for r in all_data if r.get("strikePrice")]
            spot_price = float(valid_strikes[len(valid_strikes) // 2]) if valid_strikes else 24000.0

    # Determine targeted expiry date (default to nearest expiry)
    target_expiry = expiry_date or (expiry_dates[0] if expiry_dates else None)

    # Filter data for targeted expiry
    if target_expiry:
        filtered_data = [
            r for r in all_data
            if r.get("expiryDate") == target_expiry or r.get("CE", {}).get("expiryDate") == target_expiry or r.get("PE", {}).get("expiryDate") == target_expiry
        ]
        if not filtered_data:
            filtered_data = all_data
    else:
        filtered_data = all_data

    # Aggregate metrics
    tot_ce_oi = 0
    tot_pe_oi = 0
    tot_ce_vol = 0
    tot_pe_vol = 0
    tot_ce_chg_oi = 0
    tot_pe_chg_oi = 0

    call_strikes = []
    put_strikes = []

    valid_strikes = sorted([float(r.get("strikePrice", 0)) for r in filtered_data if float(r.get("strikePrice", 0)) > 0])
    if valid_strikes:
        atm_strike = min(valid_strikes, key=lambda s: abs(s - spot_price))
    else:
        atm_strike = round(spot_price / 50.0) * 50

    atm_ce_ltp = 0.0
    atm_pe_ltp = 0.0

    for row in filtered_data:
        strike = float(row.get("strikePrice", 0))
        if strike <= 0:
            continue

        ce = row.get("CE", {}) if isinstance(row.get("CE"), dict) else {}
        pe = row.get("PE", {}) if isinstance(row.get("PE"), dict) else {}

        ce_oi = int(ce.get("openInterest", 0) or 0)
        pe_oi = int(pe.get("openInterest", 0) or 0)
        ce_vol = int(ce.get("totalTradedVolume", 0) or 0)
        pe_vol = int(pe.get("totalTradedVolume", 0) or 0)
        ce_chg = int(ce.get("changeinOpenInterest", 0) or 0)
        pe_chg = int(pe.get("changeinOpenInterest", 0) or 0)

        tot_ce_oi += ce_oi
        tot_pe_oi += pe_oi
        tot_ce_vol += ce_vol
        tot_pe_vol += pe_vol
        tot_ce_chg_oi += ce_chg
        tot_pe_chg_oi += pe_chg

        if ce_oi > 0:
            call_strikes.append({
                "strike": strike,
                "oi": ce_oi,
                "chg_oi": ce_chg,
                "ltp": float(ce.get("lastPrice", 0.0) or 0.0),
                "iv": float(ce.get("impliedVolatility", 0.0) or 0.0),
            })
        if pe_oi > 0:
            put_strikes.append({
                "strike": strike,
                "oi": pe_oi,
                "chg_oi": pe_chg,
                "ltp": float(pe.get("lastPrice", 0.0) or 0.0),
                "iv": float(pe.get("impliedVolatility", 0.0) or 0.0),
            })

        if strike == atm_strike or abs(strike - atm_strike) < 25:
            atm_ce_ltp = float(ce.get("lastPrice", 0.0) or 0.0)
            atm_pe_ltp = float(pe.get("lastPrice", 0.0) or 0.0)

    # Put-Call Ratios
    pcr_oi = round(tot_pe_oi / tot_ce_oi, 3) if tot_ce_oi > 0 else 1.0
    pcr_volume = round(tot_pe_vol / tot_ce_vol, 3) if tot_ce_vol > 0 else 1.0

    if tot_ce_chg_oi != 0:
        pcr_chg_oi = round(tot_pe_chg_oi / tot_ce_chg_oi, 3)
    else:
        pcr_chg_oi = 1.0 if tot_pe_chg_oi == 0 else (2.0 if tot_pe_chg_oi > 0 else 0.5)

    # Sort strikes by Open Interest to identify institutional walls
    top_call_walls = sorted(call_strikes, key=lambda x: x["oi"], reverse=True)[:3]
    top_put_floors = sorted(put_strikes, key=lambda x: x["oi"], reverse=True)[:3]

    # Sort strikes by Change in Open Interest to identify intraday build/unwinding
    active_call_buildup = sorted(call_strikes, key=lambda x: x["chg_oi"], reverse=True)[:3]
    active_put_buildup = sorted(put_strikes, key=lambda x: x["chg_oi"], reverse=True)[:3]
    call_unwinding = sorted([c for c in call_strikes if c["chg_oi"] < 0], key=lambda x: x["chg_oi"])[:3]
    put_unwinding = sorted([p for p in put_strikes if p["chg_oi"] < 0], key=lambda x: x["chg_oi"])[:3]

    max_pain = calculate_max_pain(filtered_data)
    atm_straddle = round(atm_ce_ltp + atm_pe_ltp, 2)
    implied_expected_move = round(atm_straddle * 0.85, 2) if atm_straddle > 0 else round(spot_price * 0.0075, 2)

    # Primary Resistance (Major Call Seller Wall) & Primary Support (Major Put Seller Floor)
    major_resistance = top_call_walls[0]["strike"] if top_call_walls else (atm_strike + 300)
    major_support = top_put_floors[0]["strike"] if top_put_floors else (atm_strike - 300)

    # -------------------------------------------------------------
    # Option Momentum Scoring & Sentiment Classification
    # -------------------------------------------------------------
    momentum_score = 0
    signals = []

    # 1. PCR Evaluation
    if pcr_oi >= 1.25:
        momentum_score += 1
        signals.append(f"Bullish PCR ({pcr_oi:.2f}): Heavy Put writing cushions downside.")
    elif pcr_oi <= 0.75:
        momentum_score -= 1
        signals.append(f"Bearish PCR ({pcr_oi:.2f}): Aggressive Call writing caps upside.")
    else:
        signals.append(f"Neutral PCR ({pcr_oi:.2f}): Balanced options distribution.")

    # 2. Intraday OI Shift (Put Additions vs Call Additions)
    if tot_pe_chg_oi > tot_ce_chg_oi and tot_pe_chg_oi > 0:
        momentum_score += 1
        signals.append(f"Bullish writing: Fresh Put OI (+{tot_pe_chg_oi:,}) exceeds Call OI (+{tot_ce_chg_oi:,}).")
    elif tot_ce_chg_oi > tot_pe_chg_oi and tot_ce_chg_oi > 0:
        momentum_score -= 1
        signals.append(f"Bearish writing: Fresh Call OI (+{tot_ce_chg_oi:,}) exceeds Put OI (+{tot_pe_chg_oi:,}).")

    # 3. Short Covering & Unwinding Checks
    if call_unwinding and call_unwinding[0]["strike"] <= (spot_price + 100):
        momentum_score += 1
        signals.append(f"Call unwinding detected near {call_unwinding[0]['strike']} ({call_unwinding[0]['chg_oi']:,}): Potential short squeeze fuel.")

    if put_unwinding and put_unwinding[0]["strike"] >= (spot_price - 100):
        momentum_score -= 1
        signals.append(f"Put unwinding detected near {put_unwinding[0]['strike']} ({put_unwinding[0]['chg_oi']:,}): Buyer floor weakening.")

    # 4. Spot vs Max Pain
    if spot_price > max_pain + 50:
        signals.append(f"Spot ({spot_price:,.1f}) trades above Max Pain ({max_pain:,.1f}): Bullish momentum driver.")
    elif spot_price < max_pain - 50:
        signals.append(f"Spot ({spot_price:,.1f}) trades below Max Pain ({max_pain:,.1f}): Downside drag toward Max Pain.")

    # Clamp score between -2 and +2
    momentum_score = max(-2, min(2, momentum_score))

    if momentum_score >= 2:
        regime_label = "STRONG_BULLISH_PUT_WRITING"
        positioning_summary = "Institutional Put writers are aggressively establishing a firm floor; Call sellers are retreating."
    elif momentum_score == 1:
        regime_label = "MODERATE_BULLISH"
        positioning_summary = "Positive Put-Call skew with steady Put writer defense."
    elif momentum_score == 0:
        regime_label = "NEUTRAL_RANGEBOUND"
        positioning_summary = f"Rangebound between Put floor {major_support:,.0f} and Call ceiling {major_resistance:,.0f}."
    elif momentum_score == -1:
        regime_label = "MODERATE_BEARISH"
        positioning_summary = "Call writing is exerting overhead pressure on spot prices."
    else:
        regime_label = "STRONG_BEARISH_CALL_WRITING"
        positioning_summary = "Institutional Call writers dominate; aggressive overhead supply and Put unwinding present."

    return {
        "spot_price": spot_price,
        "atm_strike": atm_strike,
        "target_expiry": target_expiry,
        "all_expiry_dates": expiry_dates,
        "total_ce_oi": tot_ce_oi,
        "total_pe_oi": tot_pe_oi,
        "total_ce_chg_oi": tot_ce_chg_oi,
        "total_pe_chg_oi": tot_pe_chg_oi,
        "pcr_oi": pcr_oi,
        "pcr_volume": pcr_volume,
        "pcr_chg_oi": pcr_chg_oi,
        "max_pain": max_pain,
        "atm_straddle_price": atm_straddle,
        "implied_expected_move": implied_expected_move,
        "expected_option_range": (round(spot_price - implied_expected_move, 1), round(spot_price + implied_expected_move, 1)),
        "major_resistance_wall": major_resistance,
        "major_support_floor": major_support,
        "top_call_walls": top_call_walls,
        "top_put_floors": top_put_floors,
        "active_call_buildup": active_call_buildup,
        "active_put_buildup": active_put_buildup,
        "call_unwinding": call_unwinding,
        "put_unwinding": put_unwinding,
        "momentum_score": momentum_score,
        "regime_label": regime_label,
        "positioning_summary": positioning_summary,
        "signals": signals,
    }
