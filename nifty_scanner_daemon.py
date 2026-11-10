#!/usr/bin/env python3
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

ARTIFACT_PATH = "/root/.gemini/antigravity-cli/brain/0ace3426-d19b-4aa7-aa88-f672cbb777b8/nifty_live_prediction.md"
IST_OFFSET = timedelta(hours=5, minutes=30)

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

def compute_ema(series, period):
    if len(series) < period:
        return [None] * len(series)
    ema = [None] * (period - 1)
    sma = sum(series[:period]) / period
    ema.append(sma)
    multiplier = 2.0 / (period + 1)
    for price in series[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema

def compute_rsi(series, period=14):
    if len(series) <= period:
        return 50.0
    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = series[i] - series[i - 1]
        gains.append(diff if diff > 0 else 0.0)
        losses.append(abs(diff) if diff < 0 else 0.0)
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period + 1, len(series)):
        diff = series[i] - series[i - 1]
        gain = diff if diff > 0 else 0.0
        loss = abs(diff) if diff < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def compute_macd(series, fast=12, slow=26, signal=9):
    if len(series) < slow + signal:
        return 0.0, 0.0, 0.0
    ema_fast = compute_ema(series, fast)
    ema_slow = compute_ema(series, slow)
    macd_line = []
    for f, s in zip(ema_fast, ema_slow):
        if f is not None and s is not None:
            macd_line.append(f - s)
    if len(macd_line) < signal:
        return 0.0, 0.0, 0.0
    sig_line = compute_ema(macd_line, signal)
    curr_macd = macd_line[-1]
    curr_sig = sig_line[-1] if sig_line[-1] is not None else curr_macd
    hist = curr_macd - curr_sig
    return curr_macd, curr_sig, hist

def compute_atr(highs, lows, closes, period=14):
    if len(closes) < 2:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        h = highs[i]
        l = lows[i]
        pc = closes[i - 1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < period:
        return sum(trs) / len(trs) if trs else 0.0
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr

def compute_bollinger(series, period=20, std_mul=2.0):
    if len(series) < period:
        mean = sum(series) / len(series)
        return mean, mean, mean
    subset = series[-period:]
    mean = sum(subset) / period
    variance = sum((x - mean) ** 2 for x in subset) / period
    std = math.sqrt(variance)
    return mean + std_mul * std, mean, mean - std_mul * std

def generate_report(iteration=1):
    now_utc = datetime.now(timezone.utc)
    now_ist = now_utc + IST_OFFSET
    timestamp_str = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")

    # 1. Fetch 5m intraday bars
    url_5m = "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=5m&range=1d"
    data_5m = fetch_json(url_5m)
    res_5m = data_5m["chart"]["result"][0]
    meta = res_5m["meta"]

    ltp = meta.get("regularMarketPrice", 0.0)
    prev_close = meta.get("chartPreviousClose", ltp)
    day_high = meta.get("regularMarketDayHigh", ltp)
    day_low = meta.get("regularMarketDayLow", ltp)
    change = ltp - prev_close
    p_change = (change / prev_close) * 100 if prev_close else 0.0

    raw_quote = res_5m["indicators"]["quote"][0]
    raw_closes = [c for c in raw_quote.get("close", []) if c is not None]
    raw_highs = [h for h in raw_quote.get("high", []) if h is not None]
    raw_lows = [l for l in raw_quote.get("low", []) if l is not None]
    raw_opens = [o for o in raw_quote.get("open", []) if o is not None]
    day_open = raw_opens[0] if raw_opens else ltp

    # 2. Fetch Daily bars for context
    url_daily = "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1d&range=3mo"
    data_daily = fetch_json(url_daily)
    res_daily = data_daily["chart"]["result"][0]
    d_quote = res_daily["indicators"]["quote"][0]
    d_closes = [c for c in d_quote.get("close", []) if c is not None]

    # Indicators
    ema9 = compute_ema(raw_closes, 9)[-1] if len(raw_closes) >= 9 else ltp
    ema21 = compute_ema(raw_closes, 21)[-1] if len(raw_closes) >= 21 else ltp
    ema50 = compute_ema(raw_closes, 50)[-1] if len(raw_closes) >= 50 else ltp

    rsi_5m = compute_rsi(raw_closes, 14)
    rsi_daily = compute_rsi(d_closes, 14)

    macd_line, macd_sig, macd_hist = compute_macd(raw_closes, 12, 26, 9)
    bb_upper, bb_mid, bb_lower = compute_bollinger(raw_closes, 20, 2.0)
    atr = compute_atr(raw_highs, raw_lows, raw_closes, 14)
    if atr == 0.0:
        atr = (day_high - day_low) / 10 if day_high > day_low else 30.0

    # Daily SMA 20 & SMA 50
    daily_sma20 = sum(d_closes[-20:]) / 20 if len(d_closes) >= 20 else ltp
    daily_sma50 = sum(d_closes[-50:]) / 50 if len(d_closes) >= 50 else ltp

    # Floor Pivots & CPR
    P = (day_high + day_low + prev_close) / 3.0
    BC = (day_high + day_low) / 2.0
    TC = (P - BC) + P
    cpr_top = max(TC, BC)
    cpr_bottom = min(TC, BC)
    cpr_width = abs(TC - BC)
    cpr_type = "Narrow (High Trend Potential)" if cpr_width < 40 else ("Average" if cpr_width < 80 else "Wide (Rangebound Expected)")

    R1 = 2 * P - day_low
    S1 = 2 * P - day_high
    R2 = P + (day_high - day_low)
    S2 = P - (day_high - day_low)
    R3 = day_high + 2 * (P - day_low)
    S3 = day_low - 2 * (day_high - P)

    # Fibonacci from day swing
    rng = day_high - day_low
    fib_236 = day_high - 0.236 * rng
    fib_382 = day_high - 0.382 * rng
    fib_500 = day_high - 0.500 * rng
    fib_618 = day_high - 0.618 * rng
    fib_786 = day_high - 0.786 * rng
    fib_ext_up_127 = day_high + 0.272 * rng
    fib_ext_up_161 = day_high + 0.618 * rng
    fib_ext_dn_127 = day_low - 0.272 * rng

    # Confluence & Prediction Scoring
    score = 0
    factors = []

    # 1. Price vs EMA9 & EMA21
    if ltp > ema9 and ema9 > ema21:
        score += 2
        factors.append("Bullish EMA stack (Price > EMA9 > EMA21)")
    elif ltp < ema9 and ema9 < ema21:
        score -= 2
        factors.append("Bearish EMA stack (Price < EMA9 < EMA21)")
    elif ltp > ema21:
        score += 1
        factors.append("Price holding above 21 EMA")
    else:
        score -= 1
        factors.append("Price struggling below 21 EMA")

    # 2. Pivot & CPR
    if ltp > cpr_top:
        score += 2
        factors.append(f"Trading above CPR Top ({cpr_top:.1f})")
    elif ltp < cpr_bottom:
        score -= 2
        factors.append(f"Trading below CPR Bottom ({cpr_bottom:.1f})")
    else:
        factors.append("Consolidating inside CPR Range")

    # 3. RSI
    if rsi_5m >= 60:
        score += 1
        factors.append(f"Strong 5m momentum (RSI {rsi_5m:.1f} > 60)")
    elif rsi_5m <= 40:
        score -= 1
        factors.append(f"Weak 5m momentum (RSI {rsi_5m:.1f} < 40)")
    else:
        factors.append(f"Neutral 5m momentum (RSI {rsi_5m:.1f})")

    # 4. MACD
    if macd_hist > 0 and macd_line > macd_sig:
        score += 1
        factors.append(f"MACD bullish expansion (Hist: +{macd_hist:.2f})")
    elif macd_hist < 0 and macd_line < macd_sig:
        score -= 1
        factors.append(f"MACD bearish contraction (Hist: {macd_hist:.2f})")

    # 5. Daily Trend alignment
    if ltp > daily_sma20:
        score += 1
        factors.append("Macro bias Bullish (Above Daily SMA20)")
    else:
        score -= 1
        factors.append("Macro bias Bearish (Below Daily SMA20)")

    # Normalize prediction
    # Max possible score = +7, min = -7
    bull_prob = int(min(max((score + 7) / 14.0 * 100, 15), 85))
    bear_prob = 100 - bull_prob

    if bull_prob >= 65:
        bias_str = "BULLISH"
        bias_color = "🟢"
        expected_move = f"Upward test towards R1 ({R1:.1f}) and Day High ({day_high:.1f})"
    elif bull_prob <= 35:
        bias_str = "BEARISH"
        bias_color = "🔴"
        expected_move = f"Downward test towards S1 ({S1:.1f}) and Day Low ({day_low:.1f})"
    else:
        bias_str = "NEUTRAL / RANGEBOUND"
        bias_color = "🟡"
        expected_move = f"Consolidation between {cpr_bottom:.1f} and {cpr_top:.1f}"

    # Trade Scenarios
    bull_trigger = max(ltp, ema9) + 5.0
    bull_stop = min(ltp, ema21) - 15.0
    bull_t1 = round(R1 if R1 > bull_trigger else day_high, 1)
    bull_t2 = round(R2 if R2 > bull_t1 else fib_ext_up_127, 1)
    bull_rr = round((bull_t1 - bull_trigger) / max((bull_trigger - bull_stop), 1.0), 2)

    bear_trigger = min(ltp, ema9) - 5.0
    bear_stop = max(ltp, ema21) + 15.0
    bear_t1 = round(S1 if S1 < bear_trigger else day_low, 1)
    bear_t2 = round(S2 if S2 < bear_t1 else fib_ext_dn_127, 1)
    bear_rr = round((bear_trigger - bear_t1) / max((bear_stop - bear_trigger), 1.0), 2)

    # Next update in 30 seconds
    next_update = (now_ist + timedelta(seconds=30)).strftime("%H:%M:%S IST")

    # Progress bar for probability
    bar_len = 20
    bull_bars = int(bar_len * (bull_prob / 100.0))
    bear_bars = bar_len - bull_bars
    bias_bar = f"`[{'█' * bull_bars}{'░' * bear_bars}]` {bull_prob}% Bullish / {bear_prob}% Bearish"

    md = f"""# NIFTY 50 Live Scanner & Prediction

> [!IMPORTANT]
> **Live Auto-Refresh Active (30-second interval)**  
> **Last Updated:** `{timestamp_str}` (Scan #{iteration})  
> **Next Refresh:** `{next_update}` • *This single view updates in-place automatically.*

---

## 1. Live Market Snapshot

| Metric | Current Value | Day Reference | Status |
| :--- | :--- | :--- | :--- |
| **NIFTY 50 LTP** | **`{ltp:.2f}`** | **Open:** `{day_open:.2f}` | {'🟢 +' if change >= 0 else '🔴 '}`{change:+.2f} ({p_change:+.2f}%)` |
| **Day Range** | **Low:** `{day_low:.2f}` | **High:** `{day_high:.2f}` | Spread: `{day_high - day_low:.2f} pts` |
| **Previous Close** | `{prev_close:.2f}` | **52-Wk Range:** `22,179 - 26,373` | Baseline |
| **Intraday Volatility (ATR 14)** | `{atr:.2f} pts` | Expected 15m move: `~{atr * 1.2:.1f}` | Volatility: {'Elevated' if atr > 40 else 'Moderate'} |

---

## 2. Technical Indicators & Trend Signals

| Category | Indicator | Current Reading | Signal / Bias |
| :--- | :--- | :--- | :--- |
| **Moving Averages (5m)** | EMA 9 / EMA 21 | `{ema9:.1f}` / `{ema21:.1f}` | {'🟢 Bullish Cross (EMA9 > EMA21)' if ema9 >= ema21 else '🔴 Bearish Cross (EMA9 < EMA21)'} |
| **Trend Baseline (5m)** | EMA 50 | `{ema50:.1f}` | {'🟢 Above 50 EMA' if ltp >= ema50 else '🔴 Below 50 EMA'} |
| **Momentum (5m)** | RSI (14) | **`{rsi_5m:.2f}`** | {'🟢 Bullish Momentum (>60)' if rsi_5m >= 60 else ('🔴 Bearish Momentum (<40)' if rsi_5m <= 40 else '🟡 Neutral (40-60)')} |
| **MACD (12, 26, 9)** | Line / Signal / Hist | `{macd_line:.2f}` / `{macd_sig:.2f}` / `{macd_hist:+.2f}` | {'🟢 Bullish Expansion' if macd_hist >= 0 else '🔴 Bearish Contraction'} |
| **Bollinger Bands (20, 2)** | Upper / Mid / Lower | `{bb_upper:.1f}` / `{bb_mid:.1f}` / `{bb_lower:.1f}` | Bandwidth: `{(bb_upper - bb_lower):.1f}` |
| **Macro Trend (Daily)** | RSI / 20 SMA / 50 SMA | `{rsi_daily:.1f}` / `{daily_sma20:.1f}` / `{daily_sma50:.1f}` | {'🟢 Daily Uptrend' if ltp >= daily_sma20 else '🔴 Daily Pullback'} |

---

## 3. Algorithmic Prediction & Probability

### Overall Directional Bias: {bias_color} **{bias_str}**
{bias_bar}

> **Forecast Summary:** {expected_move}  
> **Key Driver:** {factors[0] if factors else 'Consolidation at key pivot levels'}.

### Key Confluence Factors
"""
    for f in factors:
        md += f"- {f}\n"

    md += f"""
---

## 4. Key Price Levels & CPR / Fibonacci Structure

```
                  LEVEL MAP & CONFLUENCE
  [R3 Extension]  -----------------------------  {R3:.1f}
  [R2 Target]     -----------------------------  {R2:.1f}
  [R1 Resistance] -----------------------------  {R1:.1f}
  [Day High]      =============================  {day_high:.1f}
  [Fib 61.8%]     .............................  {fib_618:.1f}
  [Fib 50.0%]     .............................  {fib_500:.1f}
  [CPR Top (TC)]  -----------------------------  {cpr_top:.1f}
  >>> CURRENT LTP >>>>>>>>>>>>>>>>>>>>>>>>>>>>>  {ltp:.2f}
  [CPR Pivot (P)] -----------------------------  {P:.1f}
  [CPR Bot (BC)]  -----------------------------  {cpr_bottom:.1f}
  [Fib 38.2%]     .............................  {fib_382:.1f}
  [Day Low]       =============================  {day_low:.1f}
  [S1 Support]    -----------------------------  {S1:.1f}
  [S2 Target]     -----------------------------  {S2:.1f}
  [S3 Extension]  -----------------------------  {S3:.1f}
```

- **CPR Status:** `{cpr_type}` (Width: `{cpr_width:.1f} pts`, Range: `{cpr_bottom:.1f}` to `{cpr_top:.1f}`)
- **Primary Support Cluster:** `{max(S1, fib_382):.1f}` - `{cpr_bottom:.1f}`
- **Primary Resistance Cluster:** `{cpr_top:.1f}` - `{min(R1, day_high):.1f}`

---

## 5. Actionable Intraday Trade Scenarios

| Setup | Trigger Level | Target 1 | Target 2 | Invalidation Stop | Risk : Reward | Condition |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Long (Call)** | Break above `{bull_trigger:.1f}` | `{bull_t1:.1f}` | `{bull_t2:.1f}` | `{bull_stop:.1f}` | `1 : {bull_rr}` | Sustained 5m candle close above EMA 9 |
| **Short (Put)** | Breakdown below `{bear_trigger:.1f}` | `{bear_t1:.1f}` | `{bear_t2:.1f}` | `{bear_stop:.1f}` | `1 : {bear_rr}` | Rejection at CPR Top or break below EMA 21 |

---

*Auto-refreshing every 30 seconds. Managed by autonomous background daemon.*
"""
    return md

if __name__ == "__main__":
    iteration = 1
    os.makedirs(os.path.dirname(ARTIFACT_PATH), exist_ok=True)
    while True:
        try:
            report_md = generate_report(iteration)
            with open(ARTIFACT_PATH, "w", encoding="utf-8") as f:
                f.write(report_md)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Iteration {iteration} updated successfully.")
            sys.stdout.flush()
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error updating: {e}")
            sys.stdout.flush()
        iteration += 1
        time.sleep(30)
