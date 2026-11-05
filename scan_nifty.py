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
from src.option_data import (
    fetch_nse_option_chain,
    load_cached_option_chain,
    analyze_option_chain,
)
from src.institutional_flow import (
    fetch_fii_dii_data,
    load_cached_fii_dii,
    InstitutionalFlowAnalyzer,
)
from src.market_breadth import (
    fetch_market_breadth,
    load_cached_breadth,
    MarketBreadthAnalyzer,
)
from src.global_cues import (
    fetch_global_cues,
    load_cached_global_cues,
    GlobalCuesAnalyzer,
)


def scan_and_predict(
    update_data: bool = False,
    include_news: bool = False,
    include_options: bool = True,
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

    # 7. Institutional Option Chain & Positioning
    option_data = None
    if include_options:
        try:
            opt_raw = None
            if update_data:
                opt_raw = fetch_nse_option_chain("NIFTY")
            if opt_raw is None:
                opt_raw = load_cached_option_chain()
            if opt_raw:
                option_data = analyze_option_chain(opt_raw, spot_price=close)
        except Exception:
            option_data = None

    # 8. Institutional Smart Money Flow (FII / DII)
    institutional_data = None
    try:
        fii_dii_raw = fetch_fii_dii_data() if update_data else load_cached_fii_dii()
        inst_analyzer = InstitutionalFlowAnalyzer(fii_dii_raw)
        institutional_data = inst_analyzer.compute_smart_money_score()
    except Exception:
        institutional_data = None

    # 9. Market Breadth & Divergence
    breadth_data = None
    try:
        breadth_raw = fetch_market_breadth() if update_data else load_cached_breadth()
        breadth_analyzer = MarketBreadthAnalyzer(breadth_raw)
        breadth_data = breadth_analyzer.compute_breadth_score(index_change_pct=change_pct)
    except Exception:
        breadth_data = None

    # 10. Global Cues & GIFT NIFTY Opening Gap Predictor
    global_cues_data = None
    try:
        global_raw = fetch_global_cues() if update_data else load_cached_global_cues()
        global_analyzer = GlobalCuesAnalyzer(global_raw)
        global_cues_data = global_analyzer.compute_global_sentiment_score(spot_close=close)
    except Exception:
        global_cues_data = None

    # 11. Directional Movement Bias
    # Synthesize Trend Score + Momentum + S/R + Options + Institutional Flows + Breadth + Global Cues
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
        bias_points += 1
    elif nearest_resistance and (nearest_resistance["price"] - close) < (atr_14 * 0.4):
        bias_points -= 1

    if option_data:
        bias_points += option_data.get("momentum_score", 0)

    if institutional_data:
        v = institutional_data.get("verdict", "")
        if v in ("BULLISH", "MILD_BULLISH"):
            bias_points += 1
        elif v in ("BEARISH", "MILD_BEARISH"):
            bias_points -= 1

    if breadth_data:
        r = breadth_data.get("regime", "")
        if "BULLISH" in r:
            bias_points += 1
        elif "BEARISH" in r:
            bias_points -= 1

    if global_cues_data:
        gv = global_cues_data.get("verdict", "")
        if "BULLISH" in gv or "POSITIVE" in gv:
            bias_points += 1
        elif "BEARISH" in gv or "NEGATIVE" in gv:
            bias_points -= 1

    if bias_points >= 3:
        trading_bias = "BULLISH (Upward Momentum Favored)"
        conviction = "High" if bias_points >= 5 else "Moderate"
    elif bias_points <= -3:
        trading_bias = "BEARISH (Downward Momentum Favored)"
        conviction = "High" if bias_points <= -5 else "Moderate"
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
        "option_data": option_data,
        "institutional_data": institutional_data,
        "breadth_data": breadth_data,
        "global_cues_data": global_cues_data,
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

    opt = forecast.get("option_data")
    if opt:
        print("\n 5. INSTITUTIONAL OPTION CHAIN & BUYER/SELLER POSITIONING:")
        print(f"    - Expiry Tracked   : {opt.get('target_expiry')} | Max Pain Strike: {opt.get('max_pain'):,.0f}")
        print(f"    - Put-Call Ratio   : PCR (OI) = {opt.get('pcr_oi'):.2f} | PCR (Vol) = {opt.get('pcr_volume'):.2f} | Chg OI PCR = {opt.get('pcr_chg_oi'):.2f}")
        top_calls = opt.get("top_call_walls", [{}])
        top_puts = opt.get("top_put_floors", [{}])
        c_strike = top_calls[0].get("strike", 0)
        c_oi = top_calls[0].get("oi", 0)
        c_chg = top_calls[0].get("chg_oi", 0)
        p_strike = top_puts[0].get("strike", 0)
        p_oi = top_puts[0].get("oi", 0)
        p_chg = top_puts[0].get("chg_oi", 0)
        print(f"    - Major Call Wall  : {c_strike:,.0f} (OI: {c_oi:,} | Intraday Chg: {c_chg:+,}) -> Institutional Ceiling")
        print(f"    - Major Put Floor  : {p_strike:,.0f} (OI: {p_oi:,} | Intraday Chg: {p_chg:+,}) -> Institutional Floor")
        exp_opt = opt.get("expected_option_range", (0, 0))
        print(f"    - Option Move Band : {exp_opt[0]:,.1f}  <--->  {exp_opt[1]:,.1f}  (ATM Straddle: ~{opt.get('atm_straddle_price', 0):,.1f} pts)")
        print(f"    - Option Bias      : Score {opt.get('momentum_score'):+d}/2 [{opt.get('regime_label')}]")
        print(f"    - Setup Summary    : {opt.get('positioning_summary')}")

    inst = forecast.get("institutional_data")
    if inst:
        cs = inst.get("cash_summary", {})
        ds = inst.get("derivatives_summary", {})
        print("\n 6. FII / DII SMART MONEY & INDEX FUTURES POSITIONING:")
        print(f"    - Cash Market Flow : FII Net: {cs.get('fii_net_crores', 0):+,.1f} Cr | DII Net: {cs.get('dii_net_crores', 0):+,.1f} Cr (Total Net: {cs.get('total_net_crores', 0):+,.1f} Cr)")
        print(f"    - Cash Flow Bias   : {cs.get('regime')} -> {cs.get('commentary')}")
        print(f"    - FII Index Futures: Long {ds.get('long_ratio_pct', 50)}% vs Short {ds.get('short_ratio_pct', 50)}% (Net: {ds.get('net_contracts', 0):+,d} contracts)")
        print(f"    - Smart Money Score: {inst.get('composite_score', 0):+.2f} / 2.00 [{inst.get('verdict')}] ({ds.get('description')})")

    breadth = forecast.get("breadth_data")
    if breadth:
        d = breadth.get("divergence_details", {})
        print("\n 7. MARKET BREADTH & ADVANCE-DECLINE (A/D) CONFIRMATION:")
        print(f"    - NIFTY 50 Breadth : Advances: {d.get('advances')} | Declines: {d.get('declines')} | ADR: {d.get('adr'):.2f}")
        print(f"    - Divergence Status: {d.get('status')} [{d.get('signal')}]")
        print(f"    - Breadth Score    : {breadth.get('score'):+.2f} / 2.00 [{breadth.get('regime')}]")
        print(f"    - Market Health    : {d.get('description')}")

    gc = forecast.get("global_cues_data")
    if gc:
        gap = gc.get("gap_prediction", {})
        macro = gc.get("macro_tailwinds", {})
        us = gc.get("us_markets", {})
        print("\n 8. GLOBAL CUES & GIFT NIFTY OPENING GAP PREDICTION:")
        print(f"    - GIFT NIFTY Spot  : {gap.get('gift_nifty_price', 0):,.1f} (Indicating Gap: {gap.get('gap_points', 0):+,.1f} pts / {gap.get('gap_pct', 0):+.2f}%)")
        print(f"    - Projected Open   : {gap.get('projected_open', 0):,.1f} [{gap.get('category')}]")
        print(f"    - Wall Street Cues : S&P 500: {us.get('sp500_change_pct', 0):+.2f}% | NASDAQ: {us.get('nasdaq_change_pct', 0):+.2f}%")
        print(f"    - Macro Commodities: {macro.get('crude_desc')}")
        print(f"    - Opening Playbook : {gap.get('playbook')}")

    print("\n 9. TRADER'S CHART SETUP & ACTION GUIDE (SIMPLE HINGLISH):")
    print("    [CHART PAR KYA LINES DRAW KARNI HAIN]:")
    if nr:
        print(f"    - LAAL LINE (Resistance R1) : {nr['price']:,.0f} par mark karein (Zone: {nr['range'][0]:,.0f} se {nr['range'][1]:,.0f})")
    if ns:
        print(f"    - HARI LINE (Support S1)    : {ns['price']:,.0f} par mark karein (Zone: {ns['range'][0]:,.0f} se {ns['range'][1]:,.0f})")
    if "expected_daily_upper" in exp and "expected_daily_lower" in exp:
        print(f"    - DOTTED TOP (Day Ceiling)  : {exp['expected_daily_upper']:,.0f} (Kal ka maximum expected high)")
        print(f"    - DOTTED BTM (Day Floor)    : {exp['expected_daily_lower']:,.0f} (Kal ka maximum expected low)")

    print("\n    [KAL TRADE KAISE KAREIN - SIMPLE ACTION PLAYBOOK]:")
    close_val = forecast["nifty_close"]
    r_val = nr["price"] if nr else exp.get("expected_daily_upper", close_val * 1.01)
    r_upper = nr["range"][1] if nr else exp.get("expected_daily_upper", close_val * 1.01)
    s_val = ns["price"] if ns else exp.get("expected_daily_lower", close_val * 0.99)
    s_lower = ns["range"][0] if ns else exp.get("expected_daily_lower", close_val * 0.99)
    ceiling = exp.get("expected_daily_upper", r_upper)
    floor = exp.get("expected_daily_lower", s_lower)

    print(f"    * PLAN A (BREAKOUT BUY): Agar NIFTY 15-minute candle {r_val:,.0f} ke upar close kare,")
    print(f"      toh Call (CE) buy karein. Targets: {r_upper:,.0f} aur {ceiling:,.0f}. Stop-Loss: {close_val:,.0f}.")
    print(f"    * PLAN B (RESISTANCE REJECTION SHORT): Agar NIFTY {r_val:,.0f} touch karke wahan se red candle banaye,")
    print(f"      toh Put (PE) buy karein. Targets: {close_val:,.0f} aur {s_val:,.0f}. Stop-Loss: {r_upper + 20:,.0f}.")
    print(f"    * PLAN C (DIP BUY AT SUPPORT): Agar NIFTY gir kar {s_val:,.0f} (Zone: {s_lower:,.0f} - {s_val:,.0f}) par aaye aur hari bounce candle banaye,")
    print(f"      toh Call (CE) buy karein. Target: {close_val:,.0f}. Stop-Loss: {floor:,.0f}.")

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
    parser.add_argument("--chart", "-c", action="store_true", help="Generate and directly open interactive TradingView chart with levels marked in default browser.")
    parser.add_argument("--web", "-w", action="store_true", help="Redirect and launch interactive chart application in browser.")
    parser.add_argument("--groww", "-g", action="store_true", help="Open Groww live Nifty 50 chart alongside the engine chart.")
    parser.add_argument("--no-chart", action="store_true", help="Do not open browser chart in live scanning mode.")

    args = parser.parse_args()

    try:
        if args.groww:
            import webbrowser
            print("[GROWW] Opening Groww Nifty 50 Live Chart: https://groww.in/charts/stocks/nifty-50", file=sys.stderr)
            webbrowser.open("https://groww.in/charts/stocks/nifty-50")

        if args.live:
            from src.live_scanner import run_live_market_loop
            run_live_market_loop(interval=args.interval, launch_chart=not args.no_chart)
            return 0

        forecast = scan_and_predict(update_data=args.update, include_news=args.news)
        if args.json:
            print(json.dumps(forecast, indent=2))
        else:
            print_dashboard(forecast)

        if args.chart or args.web or args.groww:
            from src.chart_app import launch_chart_application
            launch_chart_application(forecast=forecast, open_browser=True)

        return 0
    except Exception as exc:
        print(f"\n[ERROR] Scan failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
