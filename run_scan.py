import urllib.request, json, math, datetime
from concurrent.futures import ThreadPoolExecutor

def calc_sma(series, period):
    if len(series) < period:
        return None
    return sum(series[-period:]) / period

def calc_ema(series, period):
    if len(series) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(series[:period]) / period
    for val in series[period:]:
        ema = val * k + ema * (1 - k)
    return ema

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
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

def calc_macd(closes):
    if len(closes) < 35:
        return None, None, None
    k12 = 2 / 13
    k26 = 2 / 27
    k9 = 2 / 10
    
    ema12 = sum(closes[:12]) / 12
    for c in closes[12:]:
        ema12 = c * k12 + ema12 * (1 - k12)
        
    ema26 = sum(closes[:26]) / 26
    macd_series = []
    
    # We need a series of MACD values to compute signal line
    cur12 = sum(closes[:12]) / 12
    cur26 = sum(closes[:26]) / 26
    
    for i, c in enumerate(closes):
        if i >= 12:
            cur12 = c * k12 + cur12 * (1 - k12)
        if i >= 26:
            cur26 = c * k26 + cur26 * (1 - k26)
            macd_series.append(cur12 - cur26)
            
    if len(macd_series) < 9:
        return None, None, None
        
    sig = sum(macd_series[:9]) / 9
    for m in macd_series[9:]:
        sig = m * k9 + sig * (1 - k9)
        
    macd_val = macd_series[-1]
    hist = macd_val - sig
    return macd_val, sig, hist

def calc_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    tr_list = []
    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        prev_c = closes[i-1]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        tr_list.append(tr)
        
    if len(tr_list) < period:
        return None
    atr = sum(tr_list[:period]) / period
    for tr in tr_list[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr

def calc_bollinger(closes, period=20, mult=2.0):
    if len(closes) < period:
        return None, None, None
    sub = closes[-period:]
    mid = sum(sub) / period
    variance = sum((x - mid) ** 2 for x in sub) / period
    std = math.sqrt(variance)
    upper = mid + mult * std
    lower = mid - mult * std
    return upper, mid, lower

def fetch_data(symbol):
    ticker = f"{symbol}.NS" if not symbol.startswith("^") else symbol
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
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

def analyze_ticker(symbol, candles):
    if not isinstance(candles, list) or len(candles) < 30:
        return None
        
    closes = [c['c'] for c in candles]
    highs = [c['h'] for c in candles]
    lows = [c['l'] for c in candles]
    volumes = [c['v'] for c in candles]
    
    ltp = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else ltp
    chg_1d = ((ltp - prev_close) / prev_close) * 100
    
    chg_5d = ((ltp - closes[-6]) / closes[-6]) * 100 if len(closes) >= 6 else 0.0
    chg_20d = ((ltp - closes[-21]) / closes[-21]) * 100 if len(closes) >= 21 else 0.0
    
    sma20 = calc_sma(closes, 20)
    sma50 = calc_sma(closes, 50)
    sma200 = calc_sma(closes, 200)
    
    rsi = calc_rsi(closes, 14)
    macd_val, macd_sig, macd_hist = calc_macd(closes)
    atr = calc_atr(highs, lows, closes, 14)
    bb_upper, bb_mid, bb_lower = calc_bollinger(closes, 20, 2.0)
    
    vol20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else (sum(volumes) / len(volumes))
    vol_surge = (volumes[-1] / vol20) if vol20 > 0 else 1.0
    
    high_52w = max(highs)
    low_52w = min(lows)
    pct_from_52w_high = ((high_52w - ltp) / high_52w) * 100
    
    high_20d = max(highs[-20:])
    low_20d = min(lows[-20:])
    
    # Alignment
    if sma20 and sma50 and sma200:
        if ltp > sma20 > sma50 > sma200:
            trend = "Strong Uptrend"
        elif ltp > sma50 and ltp > sma200:
            trend = "Uptrend"
        elif ltp < sma20 < sma50 < sma200:
            trend = "Strong Downtrend"
        elif ltp < sma50 and ltp < sma200:
            trend = "Downtrend"
        else:
            trend = "Mixed / Choppy"
    elif sma50:
        trend = "Bullish" if ltp > sma50 else "Bearish"
    else:
        trend = "N/A"
        
    return {
        'symbol': symbol,
        'ltp': round(ltp, 2),
        'chg_1d': round(chg_1d, 2),
        'chg_5d': round(chg_5d, 2),
        'chg_20d': round(chg_20d, 2),
        'sma20': round(sma20, 2) if sma20 else None,
        'sma50': round(sma50, 2) if sma50 else None,
        'sma200': round(sma200, 2) if sma200 else None,
        'rsi': round(rsi, 2) if rsi else None,
        'macd': round(macd_val, 2) if macd_val else None,
        'macd_sig': round(macd_sig, 2) if macd_sig else None,
        'macd_hist': round(macd_hist, 2) if macd_hist else None,
        'atr': round(atr, 2) if atr else None,
        'bb_upper': round(bb_upper, 2) if bb_upper else None,
        'bb_lower': round(bb_lower, 2) if bb_lower else None,
        'vol_surge': round(vol_surge, 2),
        'high_52w': round(high_52w, 2),
        'low_52w': round(low_52w, 2),
        'pct_from_52w_high': round(pct_from_52w_high, 2),
        'high_20d': round(high_20d, 2),
        'low_20d': round(low_20d, 2),
        'trend': trend
    }

def main():
    with open('/root/nifty50_constituents.csv') as f:
        lines = [line.strip().split(',') for line in f.readlines() if line.strip()][1:]
    symbols = [row[2] for row in lines]
    all_symbols = ['^NSEI'] + symbols
    
    print(f"Scanning {len(all_symbols)} tickers...")
    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(fetch_data, all_symbols))
        
    analyzed = {}
    for sym, res in results:
        an = analyze_ticker(sym, res)
        if an:
            analyzed[sym] = an
            
    with open('/root/scan_results.json', 'w') as out:
        json.dump(analyzed, out, indent=2)
    print(f"Successfully analyzed {len(analyzed)} tickers.")

if __name__ == '__main__':
    main()
