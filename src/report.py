import pandas as pd
import numpy as np
from pathlib import Path

from .engine import load_nifty_master, build_core_engine, add_regime_layer, calculate_next_day_regime
from .support_resistance import build_support_resistance_zones

def generate_daily_regime_report(df=None):
    """
    Generate a clean daily regime report for the Daily-Market-Regime-Engine,
    including standalone Support/Resistance zones confirmed by the report's decision timestamp.
    """
    if df is None:
        df = load_nifty_master()
    
    # Ensure index is chronologically sorted and valid
    df = df.sort_index()
    
    # Ensure all layers are present
    df = build_core_engine(df)
    df = add_regime_layer(df)
    
    if len(df) < 2:
        raise ValueError("Insufficient data to generate report.")
        
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    latest_date = df.index[-1].strftime("%Y-%m-%d")
    current_regime = latest.get("Market_Regime")
    previous_regime = prev.get("Market_Regime")
    regime_changed = current_regime != previous_regime
    
    regime_score = latest.get("Regime_Score")
    trend_score = latest.get("Trend_Score")
    rsi = latest.get("RSI_14")
    momentum_score = latest.get("Momentum_Score")
    participation_info = latest.get("Participation_State")
    volume_ratio = latest.get("Volume_Ratio")
    volatility_regime = latest.get("Volatility_Regime")
    atr = latest.get("ATR_14")
    atr_pct = latest.get("ATR_Pct")
    
    next_day_info = calculate_next_day_regime(df)
    
    # Generate standalone Support/Resistance zones up to latest date (decision timestamp)
    sr_zones = build_support_resistance_zones(df)
    
    # Filter zones to only include those confirmed by or before the latest date
    # and strictly active at or before the latest date (invalidation_date must be None or strictly > latest_ts).
    latest_ts = df.index[-1]
    active_confirmed_zones = [
        z for z in sr_zones 
        if z["confirmation_date"] <= latest_ts 
        and z["status"] == "Active"
        and (z["invalidation_date"] is None or z["invalidation_date"] > latest_ts)
    ]
    
    print("=" * 60)
    print("DAILY MARKET REGIME REPORT")
    print("=" * 60)
    print(f"1. Latest available market date       : {latest_date}")
    print(f"2. Current market regime               : {current_regime}")
    print(f"3. Previous regime                     : {previous_regime}")
    print(f"4. Whether the regime changed          : {regime_changed}")
    print(f"5. Regime score                        : {regime_score}")
    print(f"6. Trend score                         : {trend_score}")
    print(f"7. RSI                                 : {round(rsi, 2) if pd.notna(rsi) else rsi}")
    print(f"8. Momentum score                      : {momentum_score}")
    print(f"9. Participation information           : {participation_info}")
    print(f"10. Volume ratio                       : {round(volume_ratio, 2) if pd.notna(volume_ratio) else volume_ratio}")
    print(f"11. Volatility regime                  : {volatility_regime}")
    print(f"12. ATR                                : {round(atr, 2) if pd.notna(atr) else atr}")
    print(f"13. ATR percentage                     : {round(atr_pct, 2) if pd.notna(atr_pct) else atr_pct}%")
    print("-" * 60)
    print("14. Next-day historical regime probabilities:")
    probs = next_day_info.get("probabilities")
    cis = next_day_info.get("confidence_intervals", {})
    if probs is not None and not probs.empty:
        for reg, prob in probs.items():
            ci = cis.get(reg, (0.0, 0.0))
            print(f"    - {reg}: {round(prob, 2)}% (95% CI: {round(ci[0], 2)}% - {round(ci[1], 2)}%)")
    else:
        print("    - None")
    print(f"15. Most likely next regime            : {next_day_info.get('most_likely_regime')}")
    print(f"16. Historical sample size used        : {next_day_info.get('sample_size')}")
    print(f"17. Reliability classification         : {next_day_info.get('reliability')}")
    print("-" * 60)
    print("18. Confirmed Support/Resistance Zones (Standalone Output):")
    if active_confirmed_zones:
        for z in active_confirmed_zones:
            p_dates_str = ", ".join([ts.strftime("%Y-%m-%d") for ts in z["pivot_dates"]])
            c_date_str = z["confirmation_date"].strftime("%Y-%m-%d")
            print(f"    - [{z['type']}] Price: {round(z['price'], 2)} | Range: [{round(z['lower'], 2)} - {round(z['upper'], 2)}] | Status: {z['status']} | Retests: {z['retests']} | Pivot Date(s): {p_dates_str} | Confirmed Date: {c_date_str}")
    else:
        print("    - None confirmed")
    print("-" * 60)
    print("NOTE: The next-day section reflects historical transition")
    print("frequencies, NOT guaranteed predictions.")
    print("=" * 60)
    
    return {
        "latest_date": latest_date,
        "current_regime": current_regime,
        "previous_regime": previous_regime,
        "regime_changed": regime_changed,
        "regime_score": regime_score,
        "trend_score": trend_score,
        "rsi": rsi,
        "momentum_score": momentum_score,
        "participation_info": participation_info,
        "volume_ratio": volume_ratio,
        "volatility_regime": volatility_regime,
        "atr": atr,
        "atr_pct": atr_pct,
        "next_day_info": next_day_info,
        "support_resistance_zones": active_confirmed_zones,
    }

if __name__ == "__main__":
    generate_daily_regime_report()
