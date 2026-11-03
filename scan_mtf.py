#!/usr/bin/env python3
"""
NIFTY 50 Multi-Timeframe (MTF) Regime Scanner & Confluence Engine.

Analyzes market structure across three distinct timeframes:
1. Daily (Tactical / Immediate Momentum & S/R)
2. Weekly (Intermediate Swing Trend & EMA Structure)
3. Monthly (Macro / Secular Market Direction)

Computes cross-timeframe alignment matrix, pivot confluence, and actionable trading setups.
"""

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
)
from src.multi_timeframe import (
    aggregate_daily_to_weekly,
    add_weekly_regime_features,
    align_daily_weekly,
)
from src.support_resistance import build_support_resistance_zones
from src.option_data import (
    fetch_nse_option_chain,
    load_cached_option_chain,
    analyze_option_chain,
)


def compute_monthly_timeframe(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily bars into monthly bars and compute macro indicators."""
    df = daily_df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.set_index('Date')
        else:
            raise ValueError("daily_df must have a DatetimeIndex or a Date column.")

    df = df.sort_index()
    monthly = df.resample('ME').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum',
    }).dropna(subset=['Close'])

    monthly['EMA_10'] = monthly['Close'].ewm(span=10, adjust=False).mean()
    monthly['EMA_20'] = monthly['Close'].ewm(span=20, adjust=False).mean()
    monthly['Macro_Trend'] = np.where(monthly['Close'] > monthly['EMA_10'], 'Bullish', 'Bearish')

    # Monthly RSI
    delta = monthly['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=14, min_periods=14).mean()
    avg_loss = loss.rolling(window=14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    monthly['RSI_14'] = 100 - (100 / (1 + rs))

    return monthly


def run_multitimeframe_scan() -> dict:
    """Execute complete multi-timeframe analysis across Daily, Weekly, and Monthly horizons."""
    # 1. Base Daily Dataset
    daily_df = load_nifty_master().sort_index()
    daily_df = build_core_engine(daily_df)
    daily_df = add_regime_layer(daily_df)

    latest_date = daily_df.index[-1].strftime("%Y-%m-%d")
    latest_daily = daily_df.iloc[-1]
    prev_daily = daily_df.iloc[-2]

    spot_close = float(latest_daily["Close"])
    daily_chg_pts = spot_close - float(prev_daily["Close"])
    daily_chg_pct = (daily_chg_pts / float(prev_daily["Close"])) * 100.0

    daily_regime = str(latest_daily.get("Market_Regime", "Unknown"))
    daily_score = int(latest_daily.get("Regime_Score", 0))
    daily_trend_score = int(latest_daily.get("Trend_Score", 0))
    daily_rsi = float(latest_daily.get("RSI_14", np.nan))
    daily_atr = float(latest_daily.get("ATR_14", np.nan))
    daily_ema20 = float(latest_daily.get("EMA20", np.nan))
    daily_ema50 = float(latest_daily.get("EMA50", np.nan))
    daily_ema200 = float(latest_daily.get("EMA200", np.nan))

    # 2. Weekly Timeframe
    weekly_df = aggregate_daily_to_weekly(daily_df)
    weekly_df = add_weekly_regime_features(weekly_df)
    weekly_df['EMA_50'] = weekly_df['Close'].ewm(span=50, adjust=False).mean()

    # Weekly RSI
    w_delta = weekly_df['Close'].diff()
    w_gain = w_delta.clip(lower=0)
    w_loss = -w_delta.clip(upper=0)
    w_avg_gain = w_gain.rolling(window=14, min_periods=14).mean()
    w_avg_loss = w_loss.rolling(window=14, min_periods=14).mean()
    w_rs = w_avg_gain / w_avg_loss.replace(0, np.nan)
    weekly_df['RSI_14'] = 100 - (100 / (1 + w_rs))

    latest_weekly = weekly_df.iloc[-1]
    prev_weekly = weekly_df.iloc[-2]

    weekly_trend = str(latest_weekly.get("Weekly_Trend", "Unknown"))
    weekly_ema9 = float(latest_weekly.get("EMA_9", np.nan))
    weekly_ema21 = float(latest_weekly.get("EMA_21", np.nan))
    weekly_ema50 = float(latest_weekly.get("EMA_50", np.nan))
    weekly_rsi = float(latest_weekly.get("RSI_14", np.nan))
    weekly_high = float(latest_weekly.get("High", np.nan))
    weekly_low = float(latest_weekly.get("Low", np.nan))
    weekly_span = weekly_high - weekly_low

    # 3. Monthly Timeframe
    monthly_df = compute_monthly_timeframe(daily_df)
    latest_monthly = monthly_df.iloc[-1]
    monthly_trend = str(latest_monthly.get("Macro_Trend", "Unknown"))
    monthly_ema10 = float(latest_monthly.get("EMA_10", np.nan))
    monthly_ema20 = float(latest_monthly.get("EMA_20", np.nan))
    monthly_rsi = float(latest_monthly.get("RSI_14", np.nan))
    monthly_high = float(latest_monthly.get("High", np.nan))
    monthly_low = float(latest_monthly.get("Low", np.nan))

    # 4. Support and Resistance Zones (Daily)
    sr_zones = build_support_resistance_zones(daily_df)
    latest_ts = daily_df.index[-1]
    active_zones = [
        z for z in sr_zones
        if z["confirmation_date"] <= latest_ts
        and z["status"] == "Active"
        and (z["invalidation_date"] is None or z["invalidation_date"] > latest_ts)
    ]
    supports = sorted([z for z in active_zones if z["type"] == "Support" and z["price"] <= spot_close], key=lambda x: x["price"], reverse=True)
    resistances = sorted([z for z in active_zones if z["type"] == "Resistance" and z["price"] >= spot_close], key=lambda x: x["price"])
    nearest_support = {
        "price": round(supports[0]["price"], 2),
        "range": [round(supports[0]["lower"], 2), round(supports[0]["upper"], 2)],
        "retests": supports[0]["retests"],
    } if supports else None
    nearest_resistance = {
        "price": round(resistances[0]["price"], 2),
        "range": [round(resistances[0]["lower"], 2), round(resistances[0]["upper"], 2)],
        "retests": resistances[0]["retests"],
    } if resistances else None

    # 5. Institutional Option Chain Confluence
    opt_raw = fetch_nse_option_chain("NIFTY") or load_cached_option_chain()
    option_data = analyze_option_chain(opt_raw, spot_price=spot_close) if opt_raw else None

    # 6. Multi-Timeframe Alignment & Confluence Scoring
    # Determine alignment points across Daily (40%), Weekly (35%), Monthly (25%)
    bullish_votes = 0
    bearish_votes = 0

    # Daily check
    if daily_regime in ("Bullish", "Strong_Bullish"):
        bullish_votes += 1
    elif daily_regime in ("Bearish", "Strong_Bearish"):
        bearish_votes += 1

    # Weekly check
    if weekly_trend == "Bullish":
        bullish_votes += 1
    else:
        bearish_votes += 1

    # Monthly check
    if monthly_trend == "Bullish":
        bullish_votes += 1
    else:
        bearish_votes += 1

    # Synthesis & Confluence Diagnosis
    if bullish_votes == 3:
        confluence_state = "TRIPLE_BULLISH_CONFLUENCE"
        confluence_desc = "All 3 Timeframes (Daily, Weekly, Monthly) are locked in Bullish Alignment. Maximum trend conviction."
        strategy_action = "MOMENTUM LONG: Aggressive trend-following; buy breakouts and trail stop-loss under Daily EMA20."
    elif bearish_votes == 3:
        confluence_state = "TRIPLE_BEARISH_CONFLUENCE"
        confluence_desc = "All 3 Timeframes (Daily, Weekly, Monthly) are locked in Bearish Alignment. Major structural downtrend."
        strategy_action = "DEFENSIVE / SHORT: Sell on pullbacks toward declining Weekly EMA21; avoid unconfirmed bottom-fishing."
    elif daily_regime in ("Bullish", "Strong_Bullish") and weekly_trend == "Bearish":
        confluence_state = "PULLBACK_AGAINST_WEEKLY_TREND"
        confluence_desc = "Daily is Bullish but fighting against an ongoing Weekly Bearish trend (Counter-Trend Bear Market Rally)."
        strategy_action = f"CAUTION ON LONGS: Watch for resistance at Weekly EMA21 ({weekly_ema21:,.1f}) or Option Wall ({option_data['major_resistance_wall'] if option_data else 'N/A'}). Book quick intraday profits."
    elif daily_regime in ("Bearish", "Strong_Bearish") and weekly_trend == "Bullish":
        confluence_state = "TACTICAL_DIP_IN_BULL_MARKET"
        confluence_desc = "Daily is Bearish but Weekly remains structurally Bullish (Buy-the-Dip Zone)."
        strategy_action = f"ACCUMULATE ON CONFIRMED SUPPORT: Look for reversal candles near Weekly EMA21 ({weekly_ema21:,.1f}) or Support S1 ({nearest_support['price'] if nearest_support else 'N/A':,.1f})."
    else:
        confluence_state = "MIXED_CROSS_CURRENTS"
        confluence_desc = "Timeframes are divergent with conflicting signals. Typical of consolidation or inflection turning points."
        strategy_action = "RANGEBOUND PLAYBOOK: Trade between confirmed Support and Resistance bands. Avoid holding heavy overnight directional bets."

    return {
        "as_of_date": latest_date,
        "spot_close": spot_close,
        "daily_chg_pts": daily_chg_pts,
        "daily_chg_pct": daily_chg_pct,
        "daily": {
            "regime": daily_regime,
            "regime_score": daily_score,
            "trend_score": daily_trend_score,
            "rsi_14": round(daily_rsi, 1),
            "atr_14": round(daily_atr, 1),
            "ema20": round(daily_ema20, 1),
            "ema50": round(daily_ema50, 1),
            "ema200": round(daily_ema200, 1),
            "nearest_resistance": nearest_resistance,
            "nearest_support": nearest_support,
        },
        "weekly": {
            "trend": weekly_trend,
            "ema9": round(weekly_ema9, 1),
            "ema21": round(weekly_ema21, 1),
            "ema50": round(weekly_ema50, 1),
            "rsi_14": round(weekly_rsi, 1) if not np.isnan(weekly_rsi) else None,
            "high": round(weekly_high, 1),
            "low": round(weekly_low, 1),
            "span": round(weekly_span, 1),
        },
        "monthly": {
            "trend": monthly_trend,
            "ema10": round(monthly_ema10, 1),
            "ema20": round(monthly_ema20, 1),
            "rsi_14": round(monthly_rsi, 1) if not np.isnan(monthly_rsi) else None,
            "high": round(monthly_high, 1),
            "low": round(monthly_low, 1),
        },
        "confluence": {
            "state": confluence_state,
            "description": confluence_desc,
            "strategy": strategy_action,
            "alignment_score": f"{bullish_votes}/3 Bullish | {bearish_votes}/3 Bearish",
        },
        "option_confluence": option_data,
    }


def print_mtf_dashboard(report: dict):
    """Render an aesthetic, high-density Multi-Timeframe terminal dashboard."""
    d = report["daily"]
    w = report["weekly"]
    m = report["monthly"]
    c = report["confluence"]
    opt = report.get("option_confluence")

    print("=" * 76)
    print("         NIFTY 50 MULTI-TIMEFRAME (MTF) REGIME & CONFLUENCE SCAN")
    print("=" * 76)
    print(f" As of Market Date : {report['as_of_date']}")
    sign_pts = "+" if report['daily_chg_pts'] >= 0 else ""
    sign_pct = "+" if report['daily_chg_pct'] >= 0 else ""
    print(f" NIFTY 50 Close     : {report['spot_close']:,.2f} [{sign_pts}{report['daily_chg_pts']:,.2f} pts / {sign_pct}{report['daily_chg_pct']:.2f}%]")
    print(f" Confluence Status  : [{c['state']}] ({c['alignment_score']})")
    print("-" * 76)

    # Timeframe Summary Matrix Table
    print(" 1. MULTI-TIMEFRAME CONFLUENCE MATRIX:")
    print(" +-------------+----------------+----------+----------+--------------+")
    print(" | Timeframe   | Regime / Trend | RSI(14)  | Key EMA  | Key Target   |")
    print(" +-------------+----------------+----------+----------+--------------+")
    print(f" | Daily       | {d['regime']:<14} | {str(d['rsi_14']):<8} | EMA50={d['ema50']:<5.0f}| R1={d['nearest_resistance']['price'] if d['nearest_resistance'] else 24394:<8.0f}|")
    print(f" | Weekly      | {w['trend']:<14} | {str(w['rsi_14']):<8} | EMA21={w['ema21']:<5.0f}| Span={w['span']:<7.0f} |")
    print(f" | Monthly     | {m['trend']:<14} | {str(m['rsi_14']):<8} | EMA10={m['ema10']:<5.0f}| High={m['high']:<7.0f} |")
    print(" +-------------+----------------+----------+----------+--------------+")
    print(f" Diagnosis: {c['description']}")
    print("-" * 76)

    # Detailed Timeframe Breakdown
    print(" 2. DETAILED TIMEFRAME INDICATOR BREAKDOWN:")
    print("    [DAILY TIMEFRAME (TACTICAL)]")
    print(f"     * Regime Score   : {d['regime_score']}/4 (Trend Score: {d['trend_score']})")
    print(f"     * Moving Averages: EMA20={d['ema20']:,.1f} | EMA50={d['ema50']:,.1f} | EMA200={d['ema200']:,.1f}")
    print(f"     * Volatility     : ATR(14) = {d['atr_14']} pts")
    if d['nearest_resistance']:
        print(f"     * Resistance (R1): {d['nearest_resistance']['price']:,.1f} [Zone: {d['nearest_resistance']['range'][0]:,.0f} - {d['nearest_resistance']['range'][1]:,.0f}]")
    if d['nearest_support']:
        print(f"     * Support    (S1): {d['nearest_support']['price']:,.1f} [Zone: {d['nearest_support']['range'][0]:,.0f} - {d['nearest_support']['range'][1]:,.0f}]")

    print("\n    [WEEKLY TIMEFRAME (INTERMEDIATE SWING)]")
    print(f"     * Trend State    : {w['trend']} (Close vs Weekly EMA21)")
    print(f"     * Weekly EMAs    : EMA9={w['ema9']:,.1f} | EMA21={w['ema21']:,.1f} | EMA50={w['ema50']:,.1f}")
    print(f"     * Current Week   : Low {w['low']:,.1f}  <--->  High {w['high']:,.1f} (Span: {w['span']:,.1f} pts)")

    print("\n    [MONTHLY TIMEFRAME (MACRO SECULAR)]")
    print(f"     * Macro Trend    : {m['trend']} (Close vs Monthly EMA10)")
    print(f"     * Monthly EMAs   : EMA10={m['ema10']:,.1f} | EMA20={m['ema20']:,.1f}")
    print(f"     * Month High/Low : Low {m['low']:,.1f}  <--->  High {m['high']:,.1f}")
    print("-" * 76)

    # Option Confluence
    if opt:
        print(" 3. OPTION CHAIN CONFLUENCE WITH MTF PIVOTS:")
        print(f"    - Expiry Tracked   : {opt['target_expiry']} | Max Pain: {opt['max_pain']:,.0f}")
        print(f"    - PCR (OI / Vol)   : {opt['pcr_oi']:.2f} / {opt['pcr_volume']:.2f} (Chg OI PCR: {opt['pcr_chg_oi']:.2f})")
        print(f"    - Call Ceiling (R) : {opt['major_resistance_wall']:,.0f} (Call Sellers Wall) vs Weekly EMA21 ({w['ema21']:,.0f})")
        print(f"    - Put Floor (S)    : {opt['major_support_floor']:,.0f} (Put Sellers Floor) vs Daily Support ({d['nearest_support']['price'] if d['nearest_support'] else 22229:,.0f})")
        print(f"    - Option Bias      : Score {opt['momentum_score']:+d}/2 [{opt['regime_label']}]")
        print("-" * 76)

    # Actionable Blueprint
    print(" 4. MULTI-TIMEFRAME STRATEGY & EXECUTION BLUEPRINT:")
    print(f"  * CORE STRATEGY : {c['strategy']}")
    print("  * TACTICAL RULES:")
    if w['trend'] == "Bearish" and d['regime'] == "Bullish":
        print(f"    1. Daily momentum is pushing upward, but the Weekly trend ({w['ema21']:,.0f}) is overhead resistance.")
        print(f"    2. DO NOT hold aggressive long calls into the Weekly EMA21 / Call Wall at {w['ema21']:,.0f} - {opt['major_resistance_wall'] if opt else 24200:,.0f}.")
        print("    3. If price rejects at the Weekly EMA21 with red reversal candles, look for high-probability short scalps.")
    elif w['trend'] == "Bullish" and d['regime'] == "Bullish":
        print("    1. Full alignment between Daily and Weekly timeframes confirms strong trend momentum.")
        print("    2. Buy on intraday pullbacks towards Daily EMA20 with tight stop-loss.")
    else:
        print("    1. Timeframes are non-aligned; expect choppy, rangebound conditions.")
        print(f"    2. Trade edges between Support ({d['nearest_support']['price'] if d['nearest_support'] else 22229:,.0f}) and Resistance ({d['nearest_resistance']['price'] if d['nearest_resistance'] else 24394:,.0f}).")
    print("=" * 76)


def main():
    try:
        report = run_multitimeframe_scan()
        print_mtf_dashboard(report)
        return 0
    except Exception as exc:
        print(f"[ERROR] MTF scan failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
