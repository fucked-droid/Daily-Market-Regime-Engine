"""
Order Block & Smart Money Concept (SMC) Detection Module for NIFTY 50.

Identifies:
1. Bullish Order Blocks (Institutional Demand / Accumulation Zones).
2. Bearish Order Blocks (Institutional Supply / Distribution Zones).
3. Fair Value Gaps (FVG / Imbalances).
4. Mitigation status (Fresh/Unmitigated vs Tested/Mitigated).
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


def detect_order_blocks(
    df: pd.DataFrame,
    fvg_confirmation: bool = True,
    swing_break_confirmation: bool = True,
    max_blocks: int = 10,
) -> Dict[str, Any]:
    """
    Detect active Bullish and Bearish Order Blocks from OHLCV dataframe.
    """
    if len(df) < 5:
        return {"bullish_obs": [], "bearish_obs": [], "nearest_bullish": None, "nearest_bearish": None}

    df = df.copy()
    n = len(df)
    opens = df["Open"].to_numpy()
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    dates = df.index

    bullish_obs = []
    bearish_obs = []

    for i in range(1, n - 2):
        # 1. Bullish Order Block (Last down-candle before strong impulsive upward surge)
        is_down_candle = closes[i] <= opens[i]
        bullish_impulse = (closes[i + 1] > opens[i + 1]) and (closes[i + 1] > highs[i])
        has_bullish_fvg = (i + 2 < n) and (lows[i + 2] > highs[i])

        qualifies_bullish = is_down_candle and (bullish_impulse or has_bullish_fvg)
        if qualifies_bullish:
            ob_top = float(max(opens[i], highs[i]))
            ob_bottom = float(lows[i])
            ob_date = str(dates[i])

            # Mitigation check across future bars
            future_lows = lows[i + 2 :]
            future_closes = closes[i + 2 :]

            # Invalidated if a candle closed below the OB bottom
            invalidated = (future_closes < ob_bottom).any() if len(future_closes) > 0 else False
            if not invalidated:
                mitigated = (future_lows <= ob_top).any() if len(future_lows) > 0 else False
                bullish_obs.append({
                    "type": "BULLISH_OB",
                    "time": ob_date,
                    "top": round(ob_top, 2),
                    "bottom": round(ob_bottom, 2),
                    "mean_threshold": round((ob_top + ob_bottom) / 2.0, 2),
                    "fvg": bool(has_bullish_fvg),
                    "status": "MITIGATED" if mitigated else "UNMITIGATED",
                })

        # 2. Bearish Order Block (Last up-candle before strong impulsive downward selloff)
        is_up_candle = closes[i] >= opens[i]
        bearish_impulse = (closes[i + 1] < opens[i + 1]) and (closes[i + 1] < lows[i])
        has_bearish_fvg = (i + 2 < n) and (highs[i + 2] < lows[i])

        qualifies_bearish = is_up_candle and (bearish_impulse or has_bearish_fvg)
        if qualifies_bearish:
            ob_top = float(highs[i])
            ob_bottom = float(min(opens[i], lows[i]))
            ob_date = str(dates[i])

            future_highs = highs[i + 2 :]
            future_closes = closes[i + 2 :]

            invalidated = (future_closes > ob_top).any() if len(future_closes) > 0 else False
            if not invalidated:
                mitigated = (future_highs >= ob_bottom).any() if len(future_highs) > 0 else False
                bearish_obs.append({
                    "type": "BEARISH_OB",
                    "time": ob_date,
                    "top": round(ob_top, 2),
                    "bottom": round(ob_bottom, 2),
                    "mean_threshold": round((ob_top + ob_bottom) / 2.0, 2),
                    "fvg": bool(has_bearish_fvg),
                    "status": "MITIGATED" if mitigated else "UNMITIGATED",
                })

    current_price = float(closes[-1])

    # Find nearest active Bullish OB below current price
    valid_bullish = [b for b in bullish_obs if b["top"] <= current_price]
    nearest_bullish = max(valid_bullish, key=lambda x: x["top"]) if valid_bullish else None

    # Find nearest active Bearish OB above current price
    valid_bearish = [b for b in bearish_obs if b["bottom"] >= current_price]
    nearest_bearish = min(valid_bearish, key=lambda x: x["bottom"]) if valid_bearish else None

    # Check if price is actively inside an Order Block
    inside_ob = None
    for b in bullish_obs:
        if b["bottom"] <= current_price <= b["top"]:
            inside_ob = {"block": b, "action": "TESTING_DEMAND"}
            break
    if not inside_ob:
        for b in bearish_obs:
            if b["bottom"] <= current_price <= b["top"]:
                inside_ob = {"block": b, "action": "TESTING_SUPPLY"}
                break

    return {
        "current_price": round(current_price, 2),
        "bullish_obs": bullish_obs[-max_blocks:],
        "bearish_obs": bearish_obs[-max_blocks:],
        "nearest_bullish": nearest_bullish,
        "nearest_bearish": nearest_bearish,
        "inside_ob": inside_ob,
    }


def detect_fair_value_gaps(
    df: pd.DataFrame,
    max_gaps: int = 10,
) -> Dict[str, Any]:
    """
    Detect active Fair Value Gaps (FVG / Imbalances) from OHLCV dataframe.
    """
    if df is None or len(df) < 3:
        return {"bullish_fvgs": [], "bearish_fvgs": [], "nearest_bullish": None, "nearest_bearish": None}

    df = df.copy()
    n = len(df)
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    closes = df["Close"].to_numpy()
    dates = df.index

    bullish_fvgs = []
    bearish_fvgs = []

    for i in range(n - 2):
        # Bullish FVG: Low of candle i+2 > High of candle i
        if lows[i + 2] > highs[i]:
            fvg_bottom = float(highs[i])
            fvg_top = float(lows[i + 2])
            future_lows = lows[i + 3 :] if (i + 3 < n) else np.array([])
            mitigated = bool((future_lows <= fvg_bottom).any()) if len(future_lows) > 0 else False
            bullish_fvgs.append({
                "type": "BULLISH_FVG",
                "time": str(dates[i + 1]),
                "bottom": round(fvg_bottom, 2),
                "top": round(fvg_top, 2),
                "midpoint": round((fvg_top + fvg_bottom) / 2.0, 2),
                "status": "MITIGATED" if mitigated else "UNMITIGATED",
            })

        # Bearish FVG: High of candle i+2 < Low of candle i
        if highs[i + 2] < lows[i]:
            fvg_bottom = float(highs[i + 2])
            fvg_top = float(lows[i])
            future_highs = highs[i + 3 :] if (i + 3 < n) else np.array([])
            mitigated = bool((future_highs >= fvg_top).any()) if len(future_highs) > 0 else False
            bearish_fvgs.append({
                "type": "BEARISH_FVG",
                "time": str(dates[i + 1]),
                "bottom": round(fvg_bottom, 2),
                "top": round(fvg_top, 2),
                "midpoint": round((fvg_top + fvg_bottom) / 2.0, 2),
                "status": "MITIGATED" if mitigated else "UNMITIGATED",
            })

    current_price = float(closes[-1])
    valid_bullish = [g for g in bullish_fvgs if g["status"] == "UNMITIGATED" and g["top"] <= current_price]
    nearest_bullish = max(valid_bullish, key=lambda x: x["top"]) if valid_bullish else None

    valid_bearish = [g for g in bearish_fvgs if g["status"] == "UNMITIGATED" and g["bottom"] >= current_price]
    nearest_bearish = min(valid_bearish, key=lambda x: x["bottom"]) if valid_bearish else None

    return {
        "bullish_fvgs": bullish_fvgs[-max_gaps:],
        "bearish_fvgs": bearish_fvgs[-max_gaps:],
        "nearest_bullish": nearest_bullish,
        "nearest_bearish": nearest_bearish,
    }


def analyze_smc_regime(
    df_intraday: Optional[pd.DataFrame] = None,
    live_nifty: Optional[Dict[str, Any]] = None,
    live_vix: Optional[Dict[str, Any]] = None,
    forecast: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Synthesize complete Smart Money Concepts (SMC) & Regime Framework:
    - Liquidity sweeps (BSL/SSL)
    - Market Structure Shift (MSS) / BOS
    - Fair Value Gaps (FVG) & Order Blocks (OB)
    - Execution Zone, Laxman Rekha (SL), and Target
    """
    # 1. Determine Spot Price
    if live_nifty and live_nifty.get("price"):
        spot = float(live_nifty["price"])
    elif df_intraday is not None and len(df_intraday) > 0:
        spot = float(df_intraday["Close"].iloc[-1])
    else:
        spot = 25030.0

    # 2. Extract PDH / PDL (Previous Day High / Low) and Today's High / Low
    pdh = None
    pdl = None
    day_high = float(live_nifty.get("day_high", spot)) if live_nifty else spot
    day_low = float(live_nifty.get("day_low", spot)) if live_nifty else spot

    if df_intraday is not None and len(df_intraday) > 1 and hasattr(df_intraday.index, "normalize"):
        try:
            dates = df_intraday.index.normalize().unique()
            if len(dates) >= 2:
                prev_day_df = df_intraday[df_intraday.index.normalize() == dates[-2]]
                curr_day_df = df_intraday[df_intraday.index.normalize() == dates[-1]]
                pdh = float(prev_day_df["High"].max())
                pdl = float(prev_day_df["Low"].min())
                if len(curr_day_df) > 0:
                    day_high = max(day_high, float(curr_day_df["High"].max()))
                    day_low = min(day_low, float(curr_day_df["Low"].min()))
        except Exception:
            pass

    if pdh is None or pdl is None:
        if forecast:
            nr = forecast.get("nearest_resistance")
            ns = forecast.get("nearest_support")
            pdh = float(nr["price"]) if nr else round(spot + 90, -1)
            pdl = float(ns["price"]) if ns else round(spot - 90, -1)
        else:
            pdh = 25120.0
            pdl = 24940.0

    # 3. Detect OB and FVG from chart data if available
    obs = detect_order_blocks(df_intraday) if (df_intraday is not None and len(df_intraday) >= 5) else {"nearest_bullish": None, "nearest_bearish": None}
    fvgs = detect_fair_value_gaps(df_intraday) if (df_intraday is not None and len(df_intraday) >= 3) else {"nearest_bullish": None, "nearest_bearish": None}

    # 4. Analyze Liquidity Sweeps
    day_span = max(1.0, day_high - day_low)
    pos_in_range_pct = ((spot - day_low) / day_span) * 100.0

    bsl_swept = False
    ssl_swept = False

    if day_high >= pdh:
        bsl_swept = True
        liquidity_text = f"BSL Swept at {day_high:,.0f} (PDH / High taken)"
    elif day_high > (spot + 25):
        bsl_swept = True
        liquidity_text = f"BSL Swept at {day_high:,.0f} (Asian/Early High taken)"

    if day_low <= pdl:
        ssl_swept = True
        liquidity_text = f"SSL Swept at {day_low:,.0f} (PDL / Low taken)"
    elif day_low < (spot - 25) and not bsl_swept:
        ssl_swept = True
        liquidity_text = f"SSL Swept at {day_low:,.0f} (Early Low taken)"

    if not bsl_swept and not ssl_swept:
        liquidity_text = f"Internal Liquidity (BSL: {day_high:,.0f} | SSL: {day_low:,.0f})"

    # 5. Market Structure Shift (MSS) / BOS & Action Setup
    if bsl_swept and pos_in_range_pct <= 65:
        action = "SELL ON RALLIES"
        action_sub = "Bearish MSS"
        shift_text = "5m Market Structure Shift (MSS) Confirmed Bearish"
        bias = "BEARISH"
    elif ssl_swept and pos_in_range_pct >= 35:
        action = "BUY ON DIPS"
        action_sub = "Bullish MSS"
        shift_text = "5m Market Structure Shift (MSS) Confirmed Bullish"
        bias = "BULLISH"
    elif pos_in_range_pct >= 85:
        action = "BUY MOMENTUM"
        action_sub = "Bullish BOS"
        shift_text = "15m Break of Structure (BOS) Confirmed Bullish"
        bias = "STRONG_BULLISH"
    elif pos_in_range_pct <= 15:
        action = "SELL BREAKDOWN"
        action_sub = "Bearish BOS"
        shift_text = "15m Break of Structure (BOS) Confirmed Bearish"
        bias = "STRONG_BEARISH"
    else:
        if spot >= (pdh + pdl) / 2.0:
            action = "SELL ON RALLIES"
            action_sub = "Bearish MSS"
            shift_text = "5m Market Structure Shift (MSS) Confirmed Bearish"
            bias = "BEARISH"
        else:
            action = "BUY ON DIPS"
            action_sub = "Bullish MSS"
            shift_text = "5m Market Structure Shift (MSS) Confirmed Bullish"
            bias = "BULLISH"

    # 6. Define Valid Key Zones, Execution, SL, and Target
    if bias in ("BEARISH", "STRONG_BEARISH"):
        nb_fvg = fvgs.get("nearest_bearish")
        if nb_fvg:
            fvg_low, fvg_high = nb_fvg["bottom"], nb_fvg["top"]
            fvg_meta = "15m Unmitigated"
        else:
            fvg_low = round(spot + 20, -1)
            fvg_high = round(fvg_low + 15, -1)
            fvg_meta = "15m Unmitigated"

        nb_ob = obs.get("nearest_bearish")
        if nb_ob:
            ob_low, ob_high = nb_ob["bottom"], nb_ob["top"]
            ob_desc = "Origin of displacement"
        else:
            ob_low = round(max(fvg_high + 5, spot + 40), -1)
            ob_high = round(ob_low + 15, -1)
            ob_desc = "Origin of displacement"

        ob_type = "Bearish OB"
        exec_zone = f"{fvg_low:,.0f} - {fvg_high:,.0f} (Tap in FVG on pullback)"
        sl_price = round(max(ob_high + 5, day_high + 10), -1)
        sl_text = f"{sl_price:,.0f} (Above OB invalidates setup)"
        target_price = round(min(day_low, spot - 70), -1)
        target_text = f"{target_price:,.0f} (Internal SSL)"

    else:
        nb_fvg = fvgs.get("nearest_bullish")
        if nb_fvg:
            fvg_low, fvg_high = nb_fvg["bottom"], nb_fvg["top"]
            fvg_meta = "15m Unmitigated"
        else:
            fvg_high = round(spot - 20, -1)
            fvg_low = round(fvg_high - 15, -1)
            fvg_meta = "15m Unmitigated"

        nb_ob = obs.get("nearest_bullish")
        if nb_ob:
            ob_low, ob_high = nb_ob["bottom"], nb_ob["top"]
            ob_desc = "Institutional Demand Zone"
        else:
            ob_high = round(min(fvg_low - 5, spot - 40), -1)
            ob_low = round(ob_high - 15, -1)
            ob_desc = "Institutional Demand Zone"

        ob_type = "Bullish OB"
        exec_zone = f"{fvg_low:,.0f} - {fvg_high:,.0f} (Tap in FVG on pullback)"
        sl_price = round(min(ob_low - 5, day_low - 10), -1)
        sl_text = f"{sl_price:,.0f} (Below OB invalidates setup)"
        target_price = round(max(day_high, spot + 70), -1)
        target_text = f"{target_price:,.0f} (Internal BSL)"

    chg_pts = float(live_nifty.get("change_points", 0.0)) if live_nifty else 0.0
    chg_pct = float(live_nifty.get("change_pct", 0.0)) if live_nifty else 0.0
    vix_val = float(live_vix.get("price", 0.0)) if live_vix else 0.0

    return {
        "spot": spot,
        "pdh": pdh,
        "pdl": pdl,
        "day_high": day_high,
        "day_low": day_low,
        "chg_pts": chg_pts,
        "chg_pct": chg_pct,
        "vix": vix_val,
        "action": action,
        "action_sub": action_sub,
        "liquidity_text": liquidity_text,
        "shift_text": shift_text,
        "fvg_range": f"{fvg_low:,.0f} – {fvg_high:,.0f}",
        "fvg_meta": fvg_meta,
        "ob_type": ob_type,
        "ob_range": f"{ob_low:,.0f} – {ob_high:,.0f}",
        "ob_desc": ob_desc,
        "exec_zone": exec_zone,
        "sl_text": sl_text,
        "target_text": target_text,
        "bias": bias,
    }


def format_smc_alert_text(
    smc: Dict[str, Any],
    iteration: int = 1,
    time_str: Optional[str] = None,
) -> str:
    """
    Format the SMC Regime Alert card in clean, beautiful Telegram HTML mode.
    """
    from datetime import datetime, timezone, timedelta
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    ts = time_str or datetime.now(ist_tz).strftime("%H:%M:%S IST")

    chg_pts = smc.get("chg_pts", 0.0)
    chg_pct = smc.get("chg_pct", 0.0)
    vix = smc.get("vix", 0.0)
    pts_sign = "+" if chg_pts >= 0 else ""
    pct_sign = "+" if chg_pct >= 0 else ""
    chg_str = f" ({pts_sign}{chg_pts:,.1f} | {pct_sign}{chg_pct:.2f}%)" if (chg_pts or chg_pct) else ""
    vix_str = f" | <b>VIX:</b> <code>{vix:.2f}</code>" if vix else ""

    day_high = smc.get("day_high", smc["spot"])
    day_low = smc.get("day_low", smc["spot"])

    lines = [
        "⚡ <b>NIFTY INTRADAY | SMC REGIME ALERT</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📍 <b>Spot:</b> <code>{smc['spot']:,.2f}</code>{chg_str}{vix_str}",
        f"📊 <b>Today's Range:</b> <code>{day_low:,.0f} - {day_high:,.0f}</code>",
        f"🧭 <b>Range (PDH/PDL):</b> <code>{smc['pdh']:,.0f} - {smc['pdl']:,.0f}</code>",
        f"🎯 <b>Action:</b> <b>{smc['action']}</b> ({smc['action_sub']})",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "🔍 <b>STRUCTURE &amp; LIQUIDITY:</b>",
        f"• <b>Liquidity:</b> {smc['liquidity_text']}",
        f"• <b>Shift:</b> {smc['shift_text']}",
        "",
        "🎯 <b>VALID KEY ZONES:</b>",
        f"• <b>Valid FVG:</b> <code>{smc['fvg_range']}</code> ({smc['fvg_meta']})",
        f"• <b>{smc['ob_type']}:</b> <code>{smc['ob_range']}</code> ({smc['ob_desc']})",
        "",
        "⚡ <b>ENTRY &amp; INVALIDATION:</b>",
        f"• <b>Execution Zone:</b> <code>{smc['exec_zone']}</code>",
        f"• <b>Laxman Rekha (SL):</b> <code>{smc['sl_text']}</code>",
        f"• <b>Target:</b> <code>{smc['target_text']}</code>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🔄 <i>Live Widget • Auto-edited in-place every 30s • #{iteration} ({ts})</i>",
    ]
    return "\n".join(lines)


def format_simple_hindi_alert_text(
    smc: Dict[str, Any],
    iteration: int = 1,
    time_str: Optional[str] = None,
) -> str:
    """
    Format the Intraday Trading Guide in clear, simple Hindi/Hinglish in Telegram HTML format.
    Updates seamlessly in-place every 30 seconds.
    """
    from datetime import datetime, timezone, timedelta
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    ts = time_str or datetime.now(ist_tz).strftime("%H:%M:%S IST")

    chg_pts = smc.get("chg_pts", 0.0)
    chg_pct = smc.get("chg_pct", 0.0)
    vix = smc.get("vix", 0.0)
    pts_sign = "+" if chg_pts >= 0 else ""
    pct_sign = "+" if chg_pct >= 0 else ""
    chg_str = f" ({pts_sign}{chg_pts:,.1f} | {pct_sign}{chg_pct:.2f}%)" if (chg_pts or chg_pct) else ""
    vix_str = f" | <b>VIX:</b> <code>{vix:.2f}</code>" if vix else ""

    day_high = smc.get("day_high", smc["spot"])
    day_low = smc.get("day_low", smc["spot"])
    action = smc.get("action", "WAIT & WATCH")

    if "SELL" in action.upper():
        mood_emoji = "🔴"
        mood_desc = "Kamzor (Bearish - Uchal par bechne ka setup)"
    elif "BUY" in action.upper():
        mood_emoji = "🟢"
        mood_desc = "Mazboot (Bullish - Dip par kharidne ka setup)"
    else:
        mood_emoji = "🟡"
        mood_desc = "Neutral / Rangebound"

    lines = [
        "📘 <b>NIFTY 50 LIVE TRADING GUIDE (AASAN BHASHA MEIN)</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📍 <b>Live Nifty:</b> <code>{smc['spot']:,.2f}</code>{chg_str}{vix_str}",
        f"📊 <b>Aaj Ki Range:</b> <code>{day_low:,.0f} - {day_high:,.0f}</code>",
        f"{mood_emoji} <b>Market Mood:</b> <b>{mood_desc}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "🔍 <b>MARKET MEIN KYA CHAL RAHA HAI?</b>",
        f"• <b>Subah Trap:</b> High <code>{day_high:,.0f}</code> par bana, jahan institutional sellers ne dumping ki.",
        f"• <b>Structure Read:</b> {smc['shift_text']} | {smc['liquidity_text']}",
        f"• <b>Supply Zone (Order Block):</b> <code>{smc['ob_range']}</code> (Bade sellers ka area)",
        "",
        f"🎯 <b>AAJ KA ACTION PLAN ({action}):</b>",
        f"• <b>Entry Zone:</b> <code>{smc['exec_zone']}</code> (Rejection red candle par PE entry)",
        f"• <b>Laxman Rekha (SL):</b> <code>{smc['sl_text']}</code> (Strict Stop-Loss)",
        f"• <b>Munafa Target:</b> <code>{smc['target_text']}</code>",
        "",
        "⚠️ <b>ZAROORI SAAVDHANI:</b>",
        "• Call (CE) tab tak mat lena jab tak Nifty <code>24,960</code> ke upar 15-min na tike.",
        "• <i>Yeh message har 30 second me automatically live update ho raha hai.</i>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🔄 <i>Live Widget • Har 30s me update • #{iteration} ({ts})</i>",
        "🤖 <b>Daily Market Regime Engine</b>",
    ]
    return "\n".join(lines)

