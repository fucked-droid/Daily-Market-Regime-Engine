#!/usr/bin/env python3
"""
NIFTY 50 Daily Scanner & Movement Predictor CLI.

Comprehensive command-line tool that:
1. Updates or reads the latest NIFTY 50 and India VIX data.
2. Executes the multi-layer regime engine (Trend, Momentum, Structure, Volatility).
3. Evaluates Weekly-to-Daily Multi-Timeframe alignment.
4. Identifies active Support and Resistance zones.
5. Calculates statistical next-day regime probabilities and expected daily price ranges.
6. Displays a high-conviction daily market movement forecast.
"""

import argparse
from datetime import datetime
import json
import math
import os
import sys
from pathlib import Path

# Add project root and src to path
REPO_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_DIR))

import numpy as np
import pandas as pd

from src.engine import (
    load_nifty_master,
    build_core_engine,
    add_regime_layer,
    calculate_next_day_regime,
)
from src.market_data import (
    update_master_nifty_dataset,
    fetch_india_vix,
    calculate_expected_daily_range,
)
from src.multi_timeframe import (
    aggregate_daily_to_weekly,
    add_weekly_regime_features,
    align_daily_weekly,
)
from src.support_resistance import build_support_resistance_zones


def scan_and_predict(
    update_data: bool = False,
    include_news: bool = False,
) -> dict:
    """Run full scan and return structured forecast dictionary."""
    new_rows_count = 0
    if update_data:
        try:
            print("[1/5] Fetching latest market candles from Yahoo Finance (^NSEI)...", file=sys.stderr)
            df, new_rows_count = update_master_nifty_dataset(range_str="3mo")
            print(f"      Master dataset updated successfully (+{new_rows_count} rows).", file=sys.stderr)
        except Exception as exc:
            print(f"      [WARNING] Online fetch failed ({exc}). Using existing local dataset.", file=sys.stderr)
            df = load_nifty_master()
    else:
        df = load_nifty_master()

    # 1. Base Core & Regime Layers
    df = df.sort_index()
    if len(df) < 30:
        raise ValueError(f"Insufficient historical data ({len(df)} rows). Need at least 30.")

    df = build_core_engine(df)
    df = add_regime_layer(df)

    # 2. Multi-Timeframe Weekly Alignment
    weekly_df = aggregate_daily_to_weekly(df)
    weekly_features = add_weekly_regime_features(weekly_df)
    mtf_df = align_daily_weekly(df, weekly_features)

    # 3. Latest State Extraction
    latest_date = df.index[-1].strftime("%Y-%m-%d")
    latest_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    close = float(latest_row["Close"])
    prev_close = float(prev_row["Close"])
    change_pts = close - prev_close
    change_pct = (change_pts / prev_close) * 100.0

    current_regime = str(latest_row["Market_Regime"])
    prev_regime = str(prev_row["Market_Regime"])
    regime_changed = current_regime != prev_regime
    regime_score = int(latest_row.get("Regime_Score", 0))

    trend_score = int(latest_row.get("Trend_Score", 0))
    ema20 = float(latest_row.get("EMA20", np.nan))
    ema50 = float(latest_row.get("EMA50", np.nan))
    ema200 = float(latest_row.get("EMA200", np.nan))

    rsi = float(latest_row.get("RSI_14", np.nan))
    momentum_score = int(latest_row.get("Momentum_Score", 0))
    atr_14 = float(latest_row.get("ATR_14", np.nan))
    atr_pct = float(latest_row.get("ATR_Pct", np.nan))
    volatility_regime = str(latest_row.get("Volatility_Regime", "Normal"))

    # Multi-timeframe trend
    weekly_trend = str(mtf_df.iloc[-1].get("Weekly_Trend", "Unknown"))
    mtf_aligned = bool(mtf_df.iloc[-1].get("Multi_Timeframe_Aligned", False))

    # 4. Next-Day Probability Distribution (Markov Transitions)
    next_day = calculate_next_day_regime(df)
    prob_dict = {}
    if next_day.get("probabilities") is not None and not next_day["probabilities"].empty:
        for reg, prob in next_day["probabilities"].items():
            ci = next_day.get("confidence_intervals", {}).get(reg, (0.0, 0.0))
            prob_dict[reg] = {
                "probability_pct": round(float(prob), 2),
                "ci_lower_pct": round(float(ci[0]), 2),
                "ci_upper_pct": round(float(ci[1]), 2),
            }

    # 5. Support & Resistance Zones
    sr_zones = build_support_resistance_zones(df)
    latest_ts = df.index[-1]
    active_zones = [
        z for z in sr_zones
        if z["confirmation_date"] <= latest_ts
        and z["status"] == "Active"
        and (z["invalidation_date"] is None or z["invalidation_date"] > latest_ts)
    ]

    supports = sorted([z for z in active_zones if z["type"] == "Support" and z["price"] <= close], key=lambda x: x["price"], reverse=True)
    resistances = sorted([z for z in active_zones if z["type"] == "Resistance" and z["price"] >= close], key=lambda x: x["price"])

    nearest_support = supports[0] if supports else None
    nearest_resistance = resistances[0] if resistances else None

    # 6. India VIX & Expected Range
    current_vix = None
    if update_data:
        vix_df = fetch_india_vix(range_str="1mo")
        if vix_df is not None and not vix_df.empty:
            current_vix = float(vix_df.iloc[-1]["Close"])

    expected_range = calculate_expected_daily_range(
        close_price=close,
        atr_14=atr_14,
        current_vix=current_vix,
    )

    # 7. Directional Movement Bias
    # Synthesize Trend Score + Momentum Score + Weekly Trend + Distance to S/R
    bias_points = 0
    if trend_score >= 2:
        bias_points += 2
    elif trend_score <= -2:
        bias_points -= 2

    if momentum_score > 0:
        bias_points += 1
    elif momentum_score < 0:
        bias_points -= 1

    if weekly_trend == "Bullish":
        bias_points += 1
    elif weekly_trend == "Bearish":
        bias_points -= 1

    if nearest_support and (close - nearest_support["price"]) < (atr_14 * 0.4):
        # Bounce zone near support
        bias_points += 1
    elif nearest_resistance and (nearest_resistance["price"] - close) < (atr_14 * 0.4):
        # Resistance overhead
        bias_points -= 1

    if bias_points >= 2:
        trading_bias = "BULLISH (Upward Momentum Favored)"
        conviction = "High" if bias_points >= 4 else "Moderate"
    elif bias_points <= -2:
        trading_bias = "BEARISH (Downward Momentum Favored)"
        conviction = "High" if bias_points <= -4 else "Moderate"
    else:
        trading_bias = "NEUTRAL / RANGEBOUND (Consolidation Favored)"
        conviction = "Moderate"

    # 8. Optional News Headlines
    news_items = []
    if include_news:
        try:
            from fetch_headlines import fetch_rss, parse_rss_items, DEFAULT_FEED_URL
            xml_data = fetch_rss(DEFAULT_FEED_URL)
            news_items = parse_rss_items(xml_data, limit=3)
        except Exception:
            # Fallback to local cached headlines if online fetch fails
            local_headline_files = [
                REPO_DIR.parent / "headlines.json",
                REPO_DIR / "headlines.json",
            ]
            for hf in local_headline_files:
                if hf.exists():
                    try:
                        with open(hf, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if isinstance(data, list) and data:
                                news_items = data[:3]
                                break
                    except Exception:
                        pass

    return {
        "as_of_date": latest_date,
        "nifty_close": close,
        "daily_change_points": round(change_pts, 2),
        "daily_change_pct": round(change_pct, 2),
        "current_regime": current_regime,
        "previous_regime": prev_regime,
        "regime_changed": regime_changed,
        "regime_score": regime_score,
        "trend_score": trend_score,
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema200": round(ema200, 2),
        "rsi_14": round(rsi, 2),
        "momentum_score": momentum_score,
        "volatility_regime": volatility_regime,
        "atr_14": round(atr_14, 2),
        "atr_pct": round(atr_pct, 2),
        "weekly_trend": weekly_trend,
        "mtf_aligned": mtf_aligned,
        "expected_range": expected_range,
        "next_day_probabilities": prob_dict,
        "most_likely_regime": next_day.get("most_likely_regime"),
        "transition_sample_size": next_day.get("sample_size"),
        "transition_reliability": next_day.get("reliability"),
        "nearest_support": {
            "price": round(nearest_support["price"], 2),
            "range": [round(nearest_support["lower"], 2), round(nearest_support["upper"], 2)],
            "retests": nearest_support["retests"],
        } if nearest_support else None,
        "nearest_resistance": {
            "price": round(nearest_resistance["price"], 2),
            "range": [round(nearest_resistance["lower"], 2), round(nearest_resistance["upper"], 2)],
            "retests": nearest_resistance["retests"],
        } if nearest_resistance else None,
        "trading_bias": trading_bias,
        "conviction": conviction,
        "news": news_items,
    }


def print_dashboard(forecast: dict):
    """Render a clean, professional terminal dashboard."""
    print("=" * 72)
    print("           NIFTY 50 DAILY SCANNER & REGIME MOVEMENT PREDICTOR")
    print("=" * 72)
    print(f" As of Market Date : {forecast['as_of_date']}")
    print(f" Current Close      : {forecast['nifty_close']:,.2f} ({forecast['daily_change_points']:+,.2f} pts / {forecast['daily_change_pct']:+.2f}%)")
    print(f" Market Regime      : [{forecast['current_regime']}] (Score: {forecast['regime_score']}/4)")
    print(f" Multi-Timeframe    : Daily [{forecast['current_regime']}] | Weekly [{forecast['weekly_trend']}] (Aligned: {'YES' if forecast['mtf_aligned'] else 'NO'})")
    print("-" * 72)

    print(" 1. TECHNICAL INDICATORS:")
    print(f"    - Trend EMAs    : EMA20={forecast['ema20']:,.1f} | EMA50={forecast['ema50']:,.1f} | EMA200={forecast['ema200']:,.1f}")
    print(f"    - Momentum      : RSI(14)={forecast['rsi_14']} (Score: {forecast['momentum_score']})")
    print(f"    - Volatility    : ATR(14)={forecast['atr_14']} pts ({forecast['atr_pct']}%) | Regime: {forecast['volatility_regime']}")

    print("\n 2. TOMORROW'S EXPECTED TRADING RANGE:")
    exp = forecast.get("expected_range", {})
    if "expected_daily_upper" in exp and "expected_daily_lower" in exp:
        print(f"    - Expected Range: {exp['expected_daily_lower']:,.2f}  <--->  {exp['expected_daily_upper']:,.2f}")
        print(f"    - Range Span    : ~{exp['expected_range_points']:,.1f} points")
    if "vix" in exp:
        print(f"    - India VIX     : {exp['vix']} (Implied 1-day move: +/-{exp['vix_expected_move_pts']} pts / {exp['vix_expected_move_pct']}%)")
    elif "atr_14" in exp:
        print(f"    - Benchmark     : ATR 14-day movement expected: +/-{exp['atr_14']} pts")

    print("\n 3. ACTIVE KEY SUPPORT & RESISTANCE LEVELS:")
    nr = forecast.get("nearest_resistance")
    ns = forecast.get("nearest_support")
    if nr:
        print(f"    - Resistance (R1): {nr['price']:,.2f} [Zone: {nr['range'][0]:,.1f} - {nr['range'][1]:,.1f}] (Retests: {nr['retests']})")
    else:
        print("    - Resistance (R1): None confirmed nearby (Blue sky / Open resistance)")
    if ns:
        print(f"    - Support    (S1): {ns['price']:,.2f} [Zone: {ns['range'][0]:,.1f} - {ns['range'][1]:,.1f}] (Retests: {ns['retests']})")
    else:
        print("    - Support    (S1): None confirmed nearby")

    print("\n 4. HISTORICAL NEXT-DAY REGIME PROBABILITIES:")
    probs = forecast.get("next_day_probabilities", {})
    if probs:
        for reg, p in probs.items():
            print(f"    - {reg:<16}: {p['probability_pct']:>5.1f}%  (95% CI: {p['ci_lower_pct']:>4.1f}% - {p['ci_upper_pct']:>4.1f}%)")
        print(f"    - Most Likely   : {forecast.get('most_likely_regime')} (Historical Reliability: {forecast.get('transition_reliability')}, n={forecast.get('transition_sample_size')})")
    else:
        print("    - Insufficient transition history.")

    print("\n 5. TRADER'S CHART SETUP & ACTION GUIDE (SIMPLE LANGUAGE):")
    print("    [WHAT LINES TO MARK ON YOUR CHART]:")
    if nr:
        print(f"    - RED LINE (Resistance R1) : Mark at {nr['price']:,.0f} (Zone: {nr['range'][0]:,.0f} to {nr['range'][1]:,.0f})")
    if ns:
        print(f"    - GREEN LINE (Support S1)  : Mark at {ns['price']:,.0f} (Zone: {ns['range'][0]:,.0f} to {ns['range'][1]:,.0f})")
    if "expected_daily_upper" in exp and "expected_daily_lower" in exp:
        print(f"    - DOTTED TOP (Day Ceiling) : Mark at {exp['expected_daily_upper']:,.0f} (Tomorrow's max expected high)")
        print(f"    - DOTTED BTM (Day Floor)   : Mark at {exp['expected_daily_lower']:,.0f} (Tomorrow's max expected low)")

    print("\n    [HOW TO TRADE TOMORROW'S SESSION]:")
    close_val = forecast["nifty_close"]
    r_val = nr["price"] if nr else exp.get("expected_daily_upper", close_val * 1.01)
    r_upper = nr["range"][1] if nr else exp.get("expected_daily_upper", close_val * 1.01)
    s_val = ns["price"] if ns else exp.get("expected_daily_lower", close_val * 0.99)
    s_lower = ns["range"][0] if ns else exp.get("expected_daily_lower", close_val * 0.99)
    ceiling = exp.get("expected_daily_upper", r_upper)
    floor = exp.get("expected_daily_lower", s_lower)

    print(f"    * SCENARIO 1 (BREAKOUT BUY): If Nifty crosses and closes a 15-min candle above {r_val:,.0f},")
    print(f"      go LONG (Buy Call/Future). Targets: {r_upper:,.0f} and {ceiling:,.0f}. Stop-Loss: {close_val:,.0f}.")
    print(f"    * SCENARIO 2 (RESISTANCE REJECTION SHORT): If Nifty touches {r_val:,.0f} and fails to cross (makes a red candle),")
    print(f"      go SHORT (Buy Put). Targets: {close_val:,.0f} and {s_val:,.0f}. Stop-Loss: {r_upper + 20:,.0f}.")
    print(f"    * SCENARIO 3 (DIP BUY AT SUPPORT): If Nifty pulls back toward {s_val:,.0f} (Zone: {s_lower:,.0f} - {s_val:,.0f}),")
    print(f"      look for a green bounce candle to BUY. Target: {close_val:,.0f}. Stop-Loss: {floor:,.0f}.")

    print("-" * 72)
    print(f" FORECAST BIAS     : {forecast['trading_bias']}")
    print(f" CONVICTION LEVEL  : {forecast['conviction']}")
    print("=" * 72)

    news = forecast.get("news", [])
    if news:
        print("\n LATEST MARKET HEADLINES:")
        for idx, item in enumerate(news, 1):
            print(f" {idx}. {item.get('title')}")
            print(f"    Source: {item.get('link')}")
        print("=" * 72)


def main():
    parser = argparse.ArgumentParser(description="Scan and predict Nifty 50 daily market movements.")
    parser.add_argument("--update", "-u", action="store_true", help="Fetch latest live market candles from Yahoo Finance before scanning.")
    parser.add_argument("--news", "-n", action="store_true", help="Include latest Indian financial market news headlines.")
    parser.add_argument("--json", "-j", action="store_true", help="Output raw forecast as JSON.")
    parser.add_argument("--live", "-l", action="store_true", help="Start continuous live market scanning and breakout alert loop.")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Polling interval in seconds for live market scanner (default: 30).")

    args = parser.parse_args()

    try:
        if args.live:
            from src.live_scanner import run_live_market_loop
            run_live_market_loop(interval=args.interval)
            return 0

        forecast = scan_and_predict(update_data=args.update, include_news=args.news)
        if args.json:
            print(json.dumps(forecast, indent=2))
        else:
            print_dashboard(forecast)
        return 0
    except Exception as exc:
        print(f"\n[ERROR] Scan failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
