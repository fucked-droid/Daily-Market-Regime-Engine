#!/usr/bin/env python3
import json
import urllib.request
from pathlib import Path

with open('/root/.telegram_config.json') as f:
    cfg = json.load(f)

token = cfg['bot_token']
chat_id = cfg['chat_id']

msg = """🎯 *NIFTY 50 INTRADAY PLAN | TOMORROW*
📅 `Monday, 09-Nov-2026`
━━━━━━━━━━━━━━━━━━━━
📍 *Spot Close:* `24,986.40` (-0.18%)
📊 *CPR Range:* `25,010 – 25,059` (*Narrow CPR* ⚡ Trending Day Setup)
🛡️ *Current Bias:* *SELL ON PULLBACK* (Below CPR & Bearish MSS)

🔍 *SMC & STRUCTURAL ALIGNMENT*
• *Liquidity:* BSL Swept at `25,132` (High cleared, displacement lower)
• *Bearish FVG & OB:* `25,010 – 25,040` (Immediate supply block)
• *CPR Position:* Spot closed *below* CPR -> CPR acts as strong ceiling

⚡ *INTRADAY TRADE SCENARIOS*

🔹 *Scenario 1: Bearish Pullback Rejection (Primary - 65% Odds)*
• *Entry / Rejection Zone:* Pullback to `25,010 – 25,035`
• *Laxman Rekha (SL):* `25,140` (above Day High)
• *Target 1:* `24,920` (Internal SSL)
• *Target 2:* `24,850` (Support Base)
• *Target 3:* `24,800` (Major Put Wall)

🔹 *Scenario 2: Bullish Reclaim (Secondary - 35% Odds)*
• *Trigger:* Strong 15m candle close *above* `25,060` (Above CPR)
• *SL:* `24,980`
• *Targets:* `25,132` (Day High) -> `25,200` -> `25,276` (VIX Upper Band)

📊 *EXPECTED RANGE (VIX 18.43)*
• *Ceiling:* `25,276` | *Floor:* `24,696`
━━━━━━━━━━━━━━━━━━━━
🤖 *Daily Market Regime Engine*"""

url = f"https://api.telegram.org/bot{token}/sendMessage"
payload = json.dumps({
    "chat_id": chat_id,
    "text": msg,
    "parse_mode": "Markdown",
    "disable_web_page_preview": True
}).encode("utf-8")

req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=10) as resp:
    res = json.loads(resp.read().decode("utf-8"))
    print("Delivered! Message ID:", res["result"]["message_id"])
