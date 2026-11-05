"""
Live Market Scanner & Real-Time Alert Engine for NIFTY 50.

Provides continuous intraday monitoring, live tick extraction,
heavyweight stock tracking, breakout alerts, and real-time regime surveillance.
"""

from datetime import datetime, timezone, timedelta
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request

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

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

# Indian Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Top 5 NIFTY 50 Heavyweights (comprising ~40% index weight)
TOP_HEAVYWEIGHTS = [
    ("HDFCBANK.NS", "HDFC Bank", 11.5),
    ("RELIANCE.NS", "Reliance Ind", 9.8),
    ("ICICIBANK.NS", "ICICI Bank", 8.1),
    ("INFY.NS", "Infosys", 5.9),
    ("TCS.NS", "TCS", 4.1),
]


def get_market_status(dt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Evaluate current Indian Market (NSE) status in Indian Standard Time (IST).

    Normal trading: Monday - Friday, 09:15 AM - 03:30 PM IST.
    Pre-market: 09:00 AM - 09:15 AM IST.
    Post-market: 03:30 PM - 04:00 PM IST.
    """
    if dt is None:
        dt = datetime.now(IST)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)

    weekday = dt.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
    time_minutes = dt.hour * 60 + dt.minute

    pre_open = 9 * 60         # 09:00
    market_open = 9 * 60 + 15  # 09:15
    market_close = 15 * 60 + 30 # 15:30
    post_close = 16 * 60       # 16:00

    if weekday in (5, 6):
        return {
            "is_open": False,
            "session": "WEEKEND",
            "status_text": "CLOSED (Weekend)",
            "time_ist": dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        }

    if time_minutes < pre_open:
        return {
            "is_open": False,
            "session": "PRE_MARKET_CLOSED",
            "status_text": "CLOSED (Pre-Market opens at 09:00 AM IST)",
            "time_ist": dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        }
    elif pre_open <= time_minutes < market_open:
        return {
            "is_open": False,
            "session": "PRE_MARKET",
            "status_text": "PRE-MARKET SESSION (09:00 - 09:15 AM IST)",
            "time_ist": dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        }
    elif market_open <= time_minutes <= market_close:
        return {
            "is_open": True,
            "session": "LIVE",
            "status_text": "LIVE (Regular Trading Session: 09:15 - 15:30 IST)",
            "time_ist": dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        }
    elif market_close < time_minutes <= post_close:
        return {
            "is_open": False,
            "session": "POST_MARKET",
            "status_text": "POST-MARKET SESSION (15:30 - 16:00 IST)",
            "time_ist": dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        }
    else:
        return {
            "is_open": False,
            "session": "CLOSED",
            "status_text": "CLOSED (After Hours)",
            "time_ist": dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        }


def fetch_live_quote(symbol: str = "^NSEI", timeout: int = 8) -> Optional[Dict[str, Any]]:
    """Fetch live quote and intraday metadata from Yahoo Finance."""
    encoded = urllib.request.quote(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?interval=5m&range=1d"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read().decode("utf-8"))
        results = data.get("chart", {}).get("result", [])
        if not results:
            return None
        meta = results[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose")
        if price is None:
            return None

        chg_pts = price - prev if prev else 0.0
        chg_pct = (chg_pts / prev * 100.0) if prev else 0.0

        day_high = meta.get("regularMarketDayHigh", price)
        day_low = meta.get("regularMarketDayLow", price)
        day_range = day_high - day_low if (day_high and day_low) else 0.0

        pos_in_range = (
            ((price - day_low) / day_range * 100.0)
            if day_range > 0
            else 50.0
        )

        return {
            "symbol": symbol,
            "price": round(price, 2),
            "prev_close": round(prev, 2) if prev else None,
            "change_points": round(chg_pts, 2),
            "change_pct": round(chg_pct, 2),
            "day_high": round(day_high, 2) if day_high else None,
            "day_low": round(day_low, 2) if day_low else None,
            "day_range": round(day_range, 2),
            "position_in_range_pct": round(pos_in_range, 1),
            "volume": meta.get("regularMarketVolume", 0),
            "timestamp": meta.get("regularMarketTime"),
        }
    except Exception as exc:
        return None


def fetch_heavyweight_quotes(timeout: int = 5) -> List[Dict[str, Any]]:
    """Fetch live prices and price changes for the top NIFTY heavyweights."""
    quotes = []
    for ticker, name, weight in TOP_HEAVYWEIGHTS:
        q = fetch_live_quote(ticker, timeout=timeout)
        if q:
            quotes.append({
                "ticker": ticker,
                "name": name,
                "weight_pct": weight,
                "price": q["price"],
                "change_pct": q["change_pct"],
                "change_points": q["change_points"],
            })
    return quotes


def evaluate_live_alerts(
    live_nifty: Dict[str, Any],
    forecast: Dict[str, Any],
    live_vix: Optional[Dict[str, Any]] = None,
    option_analysis: Optional[Dict[str, Any]] = None,
    breadth_analysis: Optional[Dict[str, Any]] = None,
    institutional_analysis: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """
    Generate actionable real-time trading alerts based on live price action
    interacting with Support, Resistance, Range bounds, VIX, and Option Chain.
    """
    alerts = []
    price = live_nifty["price"]
    chg_pct = live_nifty["change_pct"]
    pos_in_range = live_nifty["position_in_range_pct"]

    # 1. Day's Intraday Extreme Alerts
    if pos_in_range >= 90:
        alerts.append({
            "type": "MOMENTUM",
            "level": "INFO",
            "message": f"NIFTY is trading near the HIGH OF THE DAY ({pos_in_range}% of range). Bullish intraday pressure.",
        })
    elif pos_in_range <= 10:
        alerts.append({
            "type": "MOMENTUM",
            "level": "INFO",
            "message": f"NIFTY is trading near the LOW OF THE DAY ({pos_in_range}% of range). Bearish intraday pressure.",
        })

    # 2. Key Resistance Interaction
    nr = forecast.get("nearest_resistance")
    if nr:
        r_level = nr["price"]
        r_low, r_high = nr["range"]
        if price >= r_level:
            alerts.append({
                "type": "BREAKOUT",
                "level": "HIGH",
                "message": f"BREAKOUT: Spot ({price:,.2f}) has crossed above Resistance R1 ({r_level:,.2f})! Watch for continuation above {r_high:,.2f}.",
            })
        elif r_low <= price < r_level:
            alerts.append({
                "type": "TESTING_RESISTANCE",
                "level": "MEDIUM",
                "message": f"TESTING ZONE: Spot ({price:,.2f}) is testing Resistance Zone [{r_low:,.1f} - {r_high:,.1f}]. Watch for rejection or breakout.",
            })

    # 3. Key Support Interaction
    ns = forecast.get("nearest_support")
    if ns:
        s_level = ns["price"]
        s_low, s_high = ns["range"]
        if price <= s_level:
            alerts.append({
                "type": "BREAKDOWN",
                "level": "HIGH",
                "message": f"BREAKDOWN: Spot ({price:,.2f}) has broken below Support S1 ({s_level:,.2f})! Risk of downward acceleration below {s_low:,.2f}.",
            })
        elif s_level < price <= s_high:
            alerts.append({
                "type": "TESTING_SUPPORT",
                "level": "MEDIUM",
                "message": f"TESTING ZONE: Spot ({price:,.2f}) is testing Support Zone [{s_low:,.1f} - {s_high:,.1f}]. Watch for buyer defense / bounce.",
            })

    # 4. Expected Range Outlier
    exp = forecast.get("expected_range", {})
    exp_high = exp.get("expected_daily_upper")
    exp_low = exp.get("expected_daily_lower")
    if exp_high and price > exp_high:
        alerts.append({
            "type": "OUTLIER_MOVE",
            "level": "WARNING",
            "message": f"EXTREME MOVE: Spot ({price:,.2f}) exceeded expected statistical high ({exp_high:,.2f}). Overextended territory.",
        })
    elif exp_low and price < exp_low:
        alerts.append({
            "type": "OUTLIER_MOVE",
            "level": "WARNING",
            "message": f"EXTREME MOVE: Spot ({price:,.2f}) breached expected statistical low ({exp_low:,.2f}). High downside volatility.",
        })

    # 5. Volatility Shock Alert
    if live_vix and live_vix.get("price"):
        vix_price = live_vix["price"]
        vix_chg = live_vix["change_pct"]
        if vix_chg >= 5.0:
            alerts.append({
                "type": "VIX_SPIKE",
                "level": "HIGH",
                "message": f"VOLATILITY SPIKE: India VIX jumped +{vix_chg:.1f}% to {vix_price:.2f}. Option premiums expanding; heightened tail risk.",
            })
        elif vix_chg <= -5.0:
            alerts.append({
                "type": "VIX_CRUSH",
                "level": "INFO",
                "message": f"VOLATILITY CRUSH: India VIX dropped {vix_chg:.1f}% to {vix_price:.2f}. Complacency / steady grind favored.",
            })

    # 6. Institutional Option Chain & Buyer/Seller Alerts
    if option_analysis:
        c_wall = option_analysis.get("major_resistance_wall")
        p_floor = option_analysis.get("major_support_floor")

        if c_wall and abs(price - c_wall) <= 50:
            alerts.append({
                "type": "OPTION_WALL",
                "level": "HIGH",
                "message": f"INSTITUTIONAL CEILING: Spot ({price:,.2f}) approaching Call Seller Wall at {c_wall:,.0f}. Watch for heavy selling defense or short squeeze if broken.",
            })
        if p_floor and abs(price - p_floor) <= 50:
            alerts.append({
                "type": "OPTION_WALL",
                "level": "HIGH",
                "message": f"INSTITUTIONAL FLOOR: Spot ({price:,.2f}) near Put Seller Floor at {p_floor:,.0f}. High probability buyer defense bounce zone.",
            })
        for unw in option_analysis.get("call_unwinding", []):
            if abs(price - unw["strike"]) <= 75 and unw["chg_oi"] < -5000:
                alerts.append({
                    "type": "SHORT_COVERING",
                    "level": "MEDIUM",
                    "message": f"SHORT COVERING SQUEEZE: Call unwinding at {unw['strike']:,.0f} ({unw['chg_oi']:,} OI). Sellers exiting, fueling bullish upside.",
                })
        for unw in option_analysis.get("put_unwinding", []):
            if abs(price - unw["strike"]) <= 75 and unw["chg_oi"] < -5000:
                alerts.append({
                    "type": "LONG_UNWINDING",
                    "level": "WARNING",
                    "message": f"PUT UNWINDING SLIP: Put writers exiting at {unw['strike']:,.0f} ({unw['chg_oi']:,} OI). Buyer floor deteriorating.",
                })

    # 7. Market Breadth Divergence Alerts
    if breadth_analysis:
        div = breadth_analysis.get("divergence_details", {})
        if div.get("status") == "HOLLOW_RALLY_WARNING":
            alerts.append({
                "type": "BREADTH_DIVERGENCE",
                "level": "WARNING",
                "message": f"HOLLOW RALLY TRAP: Index is up (+{chg_pct:.2f}%) but declines ({div.get('declines')}) dominate advances ({div.get('advances')}). ADR: {div.get('adr'):.2f}.",
            })
        elif div.get("status") == "BULLISH_ABSORPTION_ACCUMULATION":
            alerts.append({
                "type": "BREADTH_ACCUMULATION",
                "level": "INFO",
                "message": f"BULLISH ACCUMULATION: Index dip is being strongly absorbed across {div.get('advances')}/50 stocks. ADR: {div.get('adr'):.2f}.",
            })

    return alerts


def render_live_screen(
    live_nifty: Dict[str, Any],
    live_vix: Optional[Dict[str, Any]],
    heavyweights: List[Dict[str, Any]],
    forecast: Dict[str, Any],
    market_status: Dict[str, Any],
    alerts: List[Dict[str, str]],
    option_analysis: Optional[Dict[str, Any]] = None,
    institutional_analysis: Optional[Dict[str, Any]] = None,
    breadth_analysis: Optional[Dict[str, Any]] = None,
    global_analysis: Optional[Dict[str, Any]] = None,
    iteration: int = 1,
):
    """Render real-time live market surveillance view."""
    # Clear screen on Windows / POSIX only if running in an interactive terminal
    if sys.stdout.isatty():
        os.system("cls" if os.name == "nt" else "clear")

    print("=" * 76)
    print("           NIFTY 50 LIVE MARKET SCANNER & REGIME SURVEILLANCE")
    print("=" * 76)
    print(f" Current IST Time : {market_status['time_ist']}")
    print(f" Market Status    : {market_status['status_text']}")
    print(f" Scan Iteration   : #{iteration}")
    print("-" * 76)

    # Spot Price Action
    pts_sign = "+" if live_nifty["change_points"] >= 0 else ""
    pct_sign = "+" if live_nifty["change_pct"] >= 0 else ""
    print(f" NIFTY 50 SPOT    : {live_nifty['price']:,.2f}  [{pts_sign}{live_nifty['change_points']:,.2f} pts / {pct_sign}{live_nifty['change_pct']:.2f}%]")
    if live_nifty.get("day_high") and live_nifty.get("day_low"):
        print(f" Intraday Range   : Low {live_nifty['day_low']:,.2f}  <----({live_nifty['position_in_range_pct']}%)---->  High {live_nifty['day_high']:,.2f} (Span: {live_nifty['day_range']:,.1f} pts)")

    if live_vix:
        v_sign = "+" if live_vix["change_pct"] >= 0 else ""
        print(f" India VIX        : {live_vix['price']:.2f} [{v_sign}{live_vix['change_pct']:.2f}%]")

    print(f" Daily Regime     : [{forecast['current_regime']}] (Score: {forecast['regime_score']}/4) | Bias: {forecast['trading_bias']}")
    print("-" * 76)

    # Support / Resistance & Targets
    nr = forecast.get("nearest_resistance")
    ns = forecast.get("nearest_support")
    exp = forecast.get("expected_range", {})

    print(" KEY PRICE BOUNDS & TARGETS:")
    if nr:
        dist_r = nr['price'] - live_nifty['price']
        print(f"  - Resistance R1 : {nr['price']:,.2f} [Zone: {nr['range'][0]:,.1f} - {nr['range'][1]:,.1f}]  (Distance: {dist_r:+,.1f} pts)")
    if ns:
        dist_s = live_nifty['price'] - ns['price']
        print(f"  - Support S1    : {ns['price']:,.2f} [Zone: {ns['range'][0]:,.1f} - {ns['range'][1]:,.1f}]  (Distance: {dist_s:+,.1f} pts)")
    if "expected_daily_upper" in exp and "expected_daily_lower" in exp:
        print(f"  - Expected Range: {exp['expected_daily_lower']:,.2f}  <--->  {exp['expected_daily_upper']:,.2f}  (Span: ~{exp['expected_range_points']:,.1f} pts)")

    print("-" * 76)
    # Heavyweight Contributors
    if heavyweights:
        print(" TOP 5 INDEX MOVERS (MARKET BREADTH IMPACT):")
        hw_line = "  "
        for hw in heavyweights:
            h_sign = "+" if hw["change_pct"] >= 0 else ""
            hw_line += f"[{hw['name']}: {hw['price']:,.1f} ({h_sign}{hw['change_pct']:.2f}%)]  "
        print(hw_line)
        print("-" * 76)

    # Institutional Option Chain & Positioning
    if option_analysis:
        print(" INSTITUTIONAL OPTION CHAIN & BUYER/SELLER POSITIONING:")
        print(f"  - PCR Ratio (OI): {option_analysis.get('pcr_oi'):.2f} | Volume PCR: {option_analysis.get('pcr_volume'):.2f} | Max Pain: {option_analysis.get('max_pain'):,.0f}")
        top_c = option_analysis.get("top_call_walls", [{}])[0]
        top_p = option_analysis.get("top_put_floors", [{}])[0]
        print(f"  - Call Ceiling  : {top_c.get('strike', 0):,.0f} (OI: {top_c.get('oi', 0):,} | Chg: {top_c.get('chg_oi', 0):+,}) -> Major Resistance")
        print(f"  - Put Floor     : {top_p.get('strike', 0):,.0f} (OI: {top_p.get('oi', 0):,} | Chg: {top_p.get('chg_oi', 0):+,}) -> Major Support")
        exp_opt = option_analysis.get("expected_option_range", (0, 0))
        print(f"  - Implied Move  : {exp_opt[0]:,.1f}  <--->  {exp_opt[1]:,.1f} (ATM Straddle: ~{option_analysis.get('atm_straddle_price', 0):,.1f} pts)")
        print(f"  - Option Bias   : Score {option_analysis.get('momentum_score'):+d}/2 [{option_analysis.get('regime_label')}]")
        print(f"  - Positioning   : {option_analysis.get('positioning_summary')}")
        print("-" * 76)

    # Institutional Smart Money & Market Breadth & Global Cues
    if institutional_analysis:
        cs = institutional_analysis.get("cash_summary", {})
        ds = institutional_analysis.get("derivatives_summary", {})
        print(" INSTITUTIONAL SMART MONEY & DERIVATIVES FLOW:")
        print(f"  - Cash Net Flow : FII: {cs.get('fii_net_crores', 0):+,.1f} Cr | DII: {cs.get('dii_net_crores', 0):+,.1f} Cr (Total: {cs.get('total_net_crores', 0):+,.1f} Cr)")
        print(f"  - Index Futures : Long {ds.get('long_ratio_pct', 50):.1f}% vs Short {ds.get('short_ratio_pct', 50):.1f}% (Net: {ds.get('net_contracts', 0):+,d})")
        print(f"  - Smart Sentiment: Score {institutional_analysis.get('composite_score', 0):+.2f} / 2.00 [{institutional_analysis.get('verdict')}]")
        print("-" * 76)

    if breadth_analysis:
        d = breadth_analysis.get("divergence_details", {})
        print(" MARKET BREADTH (NIFTY 50) & ADVANCE-DECLINE HEALTH:")
        print(f"  - A/D Count     : Advances: {d.get('advances')} | Declines: {d.get('declines')} | ADR: {d.get('adr'):.2f}")
        print(f"  - Health Status : {d.get('status')} [{d.get('signal')}]")
        print("-" * 76)

    if global_analysis:
        gap = global_analysis.get("gap_prediction", {})
        macro = global_analysis.get("macro_tailwinds", {})
        print(" GLOBAL CUES & GIFT NIFTY OPENING INDICATION:")
        print(f"  - GIFT NIFTY    : {gap.get('gift_nifty_price', 0):,.1f} (Indicating Gap: {gap.get('gap_points', 0):+,.1f} pts / {gap.get('gap_pct', 0):+.2f}%)")
        print(f"  - Macro Status  : {macro.get('crude_desc')}")
        print("-" * 76)

    # Live Alerts
    print(" LIVE ACTIONABLE ALERTS:")
    if alerts:
        for a in alerts:
            lvl = a["level"]
            print(f"  * [{lvl}] {a['message']}")
    else:
        print("  * No critical breakout or boundary breaches active. Normal regime flow.")

    print("-" * 76)
    # Simple Language Chart Setup Guide
    print(" CHART MARKINGS & ACTION BLUEPRINT (SIMPLE GUIDE):")
    if nr:
        print(f"  * Draw RED LINE (Resistance) at {nr['price']:,.0f} [Zone: {nr['range'][0]:,.0f} to {nr['range'][1]:,.0f}]")
    if ns:
        print(f"  * Draw GREEN LINE (Support)   at {ns['price']:,.0f} [Zone: {ns['range'][0]:,.0f} to {ns['range'][1]:,.0f}]")
    if "expected_daily_upper" in exp and "expected_daily_lower" in exp:
        print(f"  * Draw DOTTED CEILING         at {exp['expected_daily_upper']:,.0f} & DOTTED FLOOR at {exp['expected_daily_lower']:,.0f}")

    if nr and live_nifty['price'] >= (nr['price'] - 100):
        print(f"  * TRADE RULE: Spot ({live_nifty['price']:,.0f}) is testing Resistance ({nr['price']:,.0f}). Do NOT buy blindly.")
        print(f"    - BUY CALL only if a 15-min candle closes above {nr['price']:,.0f} (Target: {exp.get('expected_daily_upper', nr['range'][1]):,.0f}).")
        print(f"    - BUY PUT if you see red rejection candles below {nr['price']:,.0f} (Target: {ns['price'] if ns else live_nifty['price'] - 200:,.0f}).")
    else:
        print(f"  * TRADE RULE: Buy on dips near Support ({ns['price'] if ns else 22229:,.0f}) or breakout above {nr['price'] if nr else 24394:,.0f}.")

    print("=" * 76)
    print(" Press Ctrl+C to stop live scanning.")
    sys.stdout.flush()


def run_live_market_loop(
    interval: int = 30,
    max_iterations: Optional[int] = None,
    launch_chart: bool = True,
):
    """
    Main live scanning loop.
    Polls the live market every `interval` seconds.
    """
    from scan_nifty import scan_and_predict

    print(f"Initializing Live Market Regime Scanner (Polling every {interval}s)...", flush=True)
    # Initial forecast generation
    forecast = scan_and_predict(update_data=False, include_news=False)

    if launch_chart:
        from src.chart_app import launch_chart_application
        try:
            launch_chart_application(forecast=forecast, open_browser=True)
        except Exception as e:
            print(f"[WARNING] Could not launch browser chart: {e}", flush=True)

    iteration = 1
    last_slow_data_time = 0.0
    slow_data_interval = 300.0  # Refresh option chain & macro data every 5 mins

    opt_raw = None
    inst_raw = None
    breadth_raw = None
    global_raw = None

    try:
        while True:
            now_ts = time.time()
            market_status = get_market_status()
            live_nifty = fetch_live_quote("^NSEI")
            live_vix = fetch_live_quote("^INDIAVIX")
            heavyweights = fetch_heavyweight_quotes()

            if live_nifty:
                # Refresh higher-latency datasets every 5 minutes (or on initial run)
                if (now_ts - last_slow_data_time > slow_data_interval) or opt_raw is None:
                    opt_raw = fetch_nse_option_chain("NIFTY") or load_cached_option_chain()
                    inst_raw = fetch_fii_dii_data() or load_cached_fii_dii()
                    breadth_raw = fetch_market_breadth() or load_cached_breadth()
                    global_raw = fetch_global_cues() or load_cached_global_cues()
                    last_slow_data_time = now_ts

                option_analysis = analyze_option_chain(opt_raw, spot_price=live_nifty["price"]) if opt_raw else None
                institutional_analysis = InstitutionalFlowAnalyzer(inst_raw).compute_smart_money_score() if inst_raw else None
                breadth_analysis = MarketBreadthAnalyzer(breadth_raw).compute_breadth_score(index_change_pct=live_nifty["change_pct"]) if breadth_raw else None
                global_analysis = GlobalCuesAnalyzer(global_raw).compute_global_sentiment_score(spot_close=live_nifty["price"]) if global_raw else None

                alerts = evaluate_live_alerts(
                    live_nifty=live_nifty,
                    forecast=forecast,
                    live_vix=live_vix,
                    option_analysis=option_analysis,
                    breadth_analysis=breadth_analysis,
                    institutional_analysis=institutional_analysis,
                )

                if launch_chart:
                    from src.chart_app import launch_chart_application
                    try:
                        live_fc = dict(forecast)
                        live_fc["nifty_close"] = live_nifty["price"]
                        live_fc["live_tick"] = live_nifty
                        live_fc["alerts"] = alerts
                        if option_analysis:
                            live_fc["option_data"] = option_analysis
                        launch_chart_application(forecast=live_fc, open_browser=False)
                    except Exception:
                        pass

                render_live_screen(
                    live_nifty=live_nifty,
                    live_vix=live_vix,
                    heavyweights=heavyweights,
                    forecast=forecast,
                    market_status=market_status,
                    alerts=alerts,
                    option_analysis=option_analysis,
                    institutional_analysis=institutional_analysis,
                    breadth_analysis=breadth_analysis,
                    global_analysis=global_analysis,
                    iteration=iteration,
                )
            else:
                print(f"[{datetime.now(IST).strftime('%H:%M:%S')}] Live tick fetch failed; retrying in {interval}s...", flush=True)

            iteration += 1
            if max_iterations and iteration > max_iterations:
                break

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nLive Market Scanner stopped by user.", flush=True)
