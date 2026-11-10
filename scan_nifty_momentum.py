#!/usr/bin/env python3
"""
NIFTY 50 Real-Time Momentum Scanner & Telegram Dispatcher
=========================================================
Scans all 50 Nifty 50 constituents + Nifty 50 Index for:
1. Daily price momentum (% Change, Points)
2. RSI(14) Momentum & Overbought/Oversold dynamics
3. Volume Surge Ratio (Today's Volume vs 20-Day SMA Volume)
4. Moving Average Alignment (Price vs 20, 50, 200 SMA)
5. Intraday Closing Strength (CLV: Range position % from Low to High)
6. Breakout detection (20-Day High, 52-Week High proximity)
7. Composite Momentum Score (0 - 100)
8. Sectoral Momentum performance
9. Market Breadth metrics (Advance/Decline, % Above 20/50 SMA)
10. Automatic Telegram Alert Dispatch to configured Bot & Chat
"""

import json
import math
import os
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Load Telegram credentials
CONFIG_PATH = Path("/root/.telegram_config.json")
def get_telegram_creds():
    token, chat_id = None, None
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                c = json.load(f)
                token = c.get("bot_token")
                chat_id = c.get("chat_id")
        except Exception as e:
            print(f"[WARN] Error loading telegram config: {e}")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", token)
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", chat_id)
    return token, str(chat_id) if chat_id else None

def calc_sma(series, period):
    if len(series) < period:
        return None
    return sum(series[-period:]) / period

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-diff)
    if len(gains) < period:
        return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def fetch_ticker_data(symbol, is_index=False):
    ticker = symbol if is_index else f"{symbol}.NS"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?range=1y&interval=1d"
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            result = data['chart']['result'][0]
            timestamps = result.get('timestamp', [])
            quotes = result['indicators']['quote'][0]
            opens = quotes.get('open', [])
            highs = quotes.get('high', [])
            lows = quotes.get('low', [])
            closes = quotes.get('close', [])
            volumes = quotes.get('volume', [])
            
            clean = []
            for t, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes):
                if c is not None and o is not None and h is not None and l is not None:
                    clean.append({'t': t, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v or 0})
            return symbol, clean
    except Exception as e:
        return symbol, str(e)

def analyze_stock(symbol, candles, meta_info=None):
    if not isinstance(candles, list) or len(candles) < 20:
        return None

    closes = [c['c'] for c in candles]
    highs = [c['h'] for c in candles]
    lows = [c['l'] for c in candles]
    opens = [c['o'] for c in candles]
    volumes = [c['v'] for c in candles]

    ltp = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else ltp
    today_open = opens[-1]
    today_high = highs[-1]
    today_low = lows[-1]
    today_vol = volumes[-1]

    chg_pts = ltp - prev_close
    chg_pct = (chg_pts / prev_close) * 100 if prev_close else 0.0

    # Moving Averages
    sma20 = calc_sma(closes, 20)
    sma50 = calc_sma(closes, 50)
    sma200 = calc_sma(closes, 200)

    # RSI
    rsi = calc_rsi(closes, 14)

    # Volume surge
    vol20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else (sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else today_vol)
    vol_surge = (today_vol / vol20) if vol20 > 0 else 1.0

    # Day range & closing position (Closing Location Value: 0% = closed at Low, 100% = closed at High)
    day_range = today_high - today_low
    clv = ((ltp - today_low) / day_range * 100) if day_range > 0 else 50.0

    # Highs and Breakouts
    high_20d = max(highs[-21:-1]) if len(highs) >= 21 else max(highs)
    breakout_20d = today_high >= high_20d and ltp >= prev_close

    high_52w = max(highs)
    low_52w = min(lows)
    pct_from_52w_high = ((high_52w - ltp) / high_52w) * 100 if high_52w else 0.0
    near_52w_high = pct_from_52w_high <= 3.0

    # Trend alignment
    if sma20 and sma50 and sma200:
        if ltp > sma20 > sma50 > sma200:
            trend = "Strong Uptrend"
        elif ltp > sma20 and ltp > sma50:
            trend = "Uptrend"
        elif ltp < sma20 < sma50 < sma200:
            trend = "Strong Downtrend"
        elif ltp < sma20 and ltp < sma50:
            trend = "Downtrend"
        else:
            trend = "Consolidating"
    elif sma50:
        trend = "Bullish" if ltp > sma50 else "Bearish"
    else:
        trend = "Neutral"

    # Composite Momentum Score (0 to 100)
    # Component 1: % Change (weight 30) - clamped from -3% (0) to +3% (30)
    norm_chg = max(0.0, min(30.0, (chg_pct + 3.0) / 6.0 * 30.0))
    
    # Component 2: RSI (weight 25) - mapped 30->0, 50->12.5, 70->25
    norm_rsi = max(0.0, min(25.0, ((rsi - 30.0) / 40.0 * 25.0))) if rsi else 12.5
    
    # Component 3: Volume Surge (weight 20) - 0.5x -> 0, 1.0x -> 10, 2.0x+ -> 20
    norm_vol = max(0.0, min(20.0, (vol_surge / 2.0) * 20.0))
    
    # Component 4: Moving Average alignment (weight 15)
    ma_score = 0.0
    if sma20 and ltp > sma20: ma_score += 5.0
    if sma50 and ltp > sma50: ma_score += 5.0
    if sma200 and ltp > sma200: ma_score += 5.0
    
    # Component 5: Closing Location Strength (weight 10) - closed near high = 10, near low = 0
    norm_clv = (clv / 100.0) * 10.0

    momentum_score = round(norm_chg + norm_rsi + norm_vol + ma_score + norm_clv, 1)

    company_name = meta_info.get('company', symbol) if meta_info else symbol
    industry = meta_info.get('industry', 'General') if meta_info else 'General'

    return {
        'symbol': symbol,
        'company': company_name,
        'industry': industry,
        'ltp': round(ltp, 2),
        'prev_close': round(prev_close, 2),
        'change_pts': round(chg_pts, 2),
        'change_pct': round(chg_pct, 2),
        'open': round(today_open, 2),
        'high': round(today_high, 2),
        'low': round(today_low, 2),
        'volume': int(today_vol),
        'vol_surge': round(vol_surge, 2),
        'rsi': round(rsi, 2) if rsi else None,
        'clv': round(clv, 1),
        'sma20': round(sma20, 2) if sma20 else None,
        'sma50': round(sma50, 2) if sma50 else None,
        'sma200': round(sma200, 2) if sma200 else None,
        'breakout_20d': breakout_20d,
        'high_20d': round(high_20d, 2),
        'pct_from_52w_high': round(pct_from_52w_high, 2),
        'near_52w_high': near_52w_high,
        'trend': trend,
        'momentum_score': momentum_score
    }

def send_telegram_alert(text: str, token: str, chat_id: str) -> bool:
    """Send formatted Telegram message."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                print(f"✅ Telegram message dispatched successfully! Message ID: {data['result']['message_id']}")
                return True
            else:
                print(f"❌ Telegram API returned error: {data}")
                return False
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")
        return False

def build_telegram_message(nifty_res, analyzed_stocks, breadth, top_gainers, top_losers, breakouts, sector_perf):
    now_ist = datetime.now(IST).strftime("%d-%b-%Y %I:%M %p IST")
    n_sign = "+" if nifty_res['change_pct'] >= 0 else ""
    n_emoji = "🟢" if nifty_res['change_pct'] >= 0 else "🔴"
    
    msg_lines = [
        f"🚀 *NIFTY 50 MOMENTUM RADAR*",
        f"📅 `{now_ist}`",
        f"━━━━━━━━━━━━━━━━━━━",
        f"{n_emoji} *NIFTY 50 INDEX*: `{nifty_res['ltp']:,.2f}` ({n_sign}{nifty_res['change_pct']:.2f}%)",
        f"📊 *Day Range*: `{nifty_res['low']:,.1f}` — `{nifty_res['high']:,.1f}`",
        f"📈 *Index RSI*: `{nifty_res['rsi']:.1f}` | Trend: *{nifty_res['trend']}*",
        f"⚖️ *Breadth*: 🟢 {breadth['advances']} Adv | 🔴 {breadth['declines']} Dec | {breadth['unchanged']} Unch",
        f"⚡ *Above 20 SMA*: `{breadth['pct_above_sma20']:.1f}%` | *Above 50 SMA*: `{breadth['pct_above_sma50']:.1f}%`",
        "",
        f"🔥 *TOP BULLISH MOMENTUM LEADERS*",
    ]
    
    for i, s in enumerate(top_gainers[:5], 1):
        sign = "+" if s['change_pct'] >= 0 else ""
        vol_tag = f" ⚡Vol:{s['vol_surge']}x" if s['vol_surge'] >= 1.3 else ""
        rsi_tag = f"| RSI:{s['rsi']:.0f}" if s['rsi'] else ""
        msg_lines.append(f"{i}. *{s['symbol']}*: `₹{s['ltp']:,.1f}` ({sign}{s['change_pct']:.2f}% {rsi_tag}{vol_tag}) [Score: {s['momentum_score']}]")

    msg_lines.append("")
    msg_lines.append("❄️ *TOP BEARISH MOMENTUM / DRAGGERS*")
    for i, s in enumerate(top_losers[:5], 1):
        sign = "+" if s['change_pct'] >= 0 else ""
        rsi_tag = f"| RSI:{s['rsi']:.0f}" if s['rsi'] else ""
        msg_lines.append(f"{i}. *{s['symbol']}*: `₹{s['ltp']:,.1f}` ({sign}{s['change_pct']:.2f}% {rsi_tag})")

    if breakouts:
        msg_lines.append("")
        msg_lines.append("⚡ *FRESH BREAKOUTS / 20D HIGHS*")
        for b in breakouts[:4]:
            tag = "⭐ 52W High Zone" if b['near_52w_high'] else "💥 20D Breakout"
            msg_lines.append(f"• *{b['symbol']}*: `₹{b['ltp']:,.1f}` (+{b['change_pct']:.2f}%) — {tag}")

    msg_lines.append("")
    msg_lines.append("🏆 *SECTOR MOMENTUM (AVG %)*")
    # Top 3 sectors and bottom 2
    for sec, p in sector_perf[:3]:
        sec_sign = "+" if p >= 0 else ""
        msg_lines.append(f"• {sec}: `{sec_sign}{p:.2f}%` 🟢")
    for sec, p in sector_perf[-2:]:
        if sec not in [s[0] for s in sector_perf[:3]]:
            sec_sign = "+" if p >= 0 else ""
            msg_lines.append(f"• {sec}: `{sec_sign}{p:.2f}%` 🔴")

    msg_lines.append("━━━━━━━━━━━━━━━━━━━")
    msg_lines.append("🤖 *Daily Market Regime Engine*")

    return "\n".join(msg_lines)

def main():
    print("=" * 65)
    print("  NIFTY 50 COMPREHENSIVE MOMENTUM SCANNER & TELEGRAM DISPATCH")
    print("=" * 65)

    # 1. Read Constituents
    constituents_file = Path("/root/nifty50_constituents.csv")
    meta = {}
    symbols = []
    if constituents_file.exists():
        with open(constituents_file, "r", encoding="utf-8") as f:
            lines = [l.strip().split(',') for l in f.readlines() if l.strip()][1:]
            for row in lines:
                c_name, industry, sym = row[0], row[1], row[2]
                symbols.append(sym)
                meta[sym] = {'company': c_name, 'industry': industry}
    else:
        print(f"❌ File {constituents_file} not found!")
        sys.exit(1)

    print(f"Loaded {len(symbols)} constituents from CSV.")
    all_targets = [('^NSEI', True)] + [(s, False) for s in symbols]

    print(f"Fetching 1Y daily data for {len(all_targets)} instruments via concurrent workers...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_ticker_data, target[0], target[1]) for target in all_targets]
        results = [f.result() for f in futures]

    candle_dict = {sym: data for sym, data in results if isinstance(data, list)}
    print(f"Successfully retrieved candle data for {len(candle_dict)} instruments.")

    # 2. Analyze Index
    nifty_candles = candle_dict.get('^NSEI')
    if not nifty_candles:
        print("❌ Could not retrieve ^NSEI candles!")
        sys.exit(1)
    nifty_res = analyze_stock('^NSEI', nifty_candles, {'company': 'NIFTY 50 Index', 'industry': 'Index'})

    # 3. Analyze Constituents
    analyzed_stocks = []
    for s in symbols:
        candles = candle_dict.get(s)
        if candles:
            res = analyze_stock(s, candles, meta.get(s))
            if res:
                analyzed_stocks.append(res)

    print(f"Successfully analyzed {len(analyzed_stocks)} constituent stocks.")

    # 4. Compute Market Breadth
    advances = [s for s in analyzed_stocks if s['change_pct'] > 0]
    declines = [s for s in analyzed_stocks if s['change_pct'] < 0]
    unchanged = [s for s in analyzed_stocks if s['change_pct'] == 0]
    above_sma20 = [s for s in analyzed_stocks if s['sma20'] and s['ltp'] > s['sma20']]
    above_sma50 = [s for s in analyzed_stocks if s['sma50'] and s['ltp'] > s['sma50']]

    breadth = {
        'advances': len(advances),
        'declines': len(declines),
        'unchanged': len(unchanged),
        'pct_above_sma20': round(len(above_sma20) / len(analyzed_stocks) * 100, 1),
        'pct_above_sma50': round(len(above_sma50) / len(analyzed_stocks) * 100, 1),
    }

    # 5. Rankings
    top_gainers = sorted(analyzed_stocks, key=lambda x: (x['change_pct'], x['momentum_score']), reverse=True)
    top_losers = sorted(analyzed_stocks, key=lambda x: x['change_pct'])
    top_momentum = sorted(analyzed_stocks, key=lambda x: x['momentum_score'], reverse=True)
    breakouts = [s for s in analyzed_stocks if s['breakout_20d'] or s['near_52w_high']]
    breakouts = sorted(breakouts, key=lambda x: x['change_pct'], reverse=True)

    # 6. Sector Performance
    sector_map = {}
    for s in analyzed_stocks:
        ind = s['industry']
        sector_map.setdefault(ind, []).append(s['change_pct'])
    sector_perf = []
    for ind, pcts in sector_map.items():
        avg_pct = sum(pcts) / len(pcts)
        sector_perf.append((ind, round(avg_pct, 2)))
    sector_perf = sorted(sector_perf, key=lambda x: x[1], reverse=True)

    # 7. Save output JSON
    scan_output = {
        'timestamp': datetime.now(IST).isoformat(),
        'nifty_index': nifty_res,
        'market_breadth': breadth,
        'top_gainers': top_gainers[:10],
        'top_losers': top_losers[:10],
        'top_momentum_score': top_momentum[:10],
        'breakouts': breakouts,
        'sector_performance': sector_perf,
        'all_stocks': analyzed_stocks
    }
    output_path = Path("/root/nifty_momentum_scan_latest.json")
    with open(output_path, "w", encoding="utf-8") as out:
        json.dump(scan_output, out, indent=2)
    print(f"Saved full scan results to {output_path}")

    # 8. Dispatch Telegram Alert
    token, chat_id = get_telegram_creds()
    tg_text = build_telegram_message(nifty_res, analyzed_stocks, breadth, top_gainers, top_losers, breakouts, sector_perf)
    print("\n--- TELEGRAM MESSAGE PREVIEW ---")
    print(tg_text)
    print("--------------------------------\n")

    if token and chat_id:
        print(f"Dispatching to Telegram (Chat ID: {chat_id})...")
        sent = send_telegram_alert(tg_text, token, chat_id)
        if sent:
            print("Telegram alert delivered successfully.")
        else:
            print("Telegram dispatch failed.")
    else:
        print("⚠️ Telegram token or chat_id not found in /root/.telegram_config.json")

    return scan_output

if __name__ == "__main__":
    main()
