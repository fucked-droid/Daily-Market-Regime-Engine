"""
Telegram Notification & Live Alert Forwarder for Daily Market Regime Engine.

Supports:
1. Instant Breakout & Level Breach Alerts to Telegram.
2. Live 30-Second Dashboard Updates (via editMessageText to prevent chat spam).
3. Seamless integration with Termux or PC background daemons.
"""

from datetime import datetime, timezone, timedelta
import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

IST = timezone(timedelta(hours=5, minutes=30))


def get_telegram_credentials() -> tuple[Optional[str], Optional[str]]:
    """Retrieve Telegram Bot Token and Chat ID from environment variables or .env file."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        # Check .env in parent directory
        env_paths = [
            os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
            os.path.join(os.path.dirname(__file__), "..", ".env"),
        ]
        for p in env_paths:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("TELEGRAM_BOT_TOKEN="):
                            token = token or line.split("=", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("TELEGRAM_CHAT_ID="):
                            chat_id = chat_id or line.split("=", 1)[1].strip().strip('"').strip("'")

    return token, chat_id


def get_telegram_api_base() -> str:
    """Return Telegram API base URL, supporting custom reverse proxies or mirrors."""
    base = os.environ.get("TELEGRAM_API_BASE")
    if not base:
        env_paths = [
            os.path.join(os.path.dirname(__file__), "..", "..", ".env"),
            os.path.join(os.path.dirname(__file__), "..", ".env"),
        ]
        for p in env_paths:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("TELEGRAM_API_BASE="):
                            base = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
    return base or "https://api.telegram.org"



def send_telegram_message(
    text: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "Markdown",
    timeout: int = 10,
) -> Optional[int]:
    """
    Send a message to a Telegram chat.
    Returns the message_id if successful, or None on failure.
    """
    t, c = get_telegram_credentials()
    bot_token = bot_token or t
    chat_id = chat_id or c

    if not bot_token or not chat_id:
        return None

    base_url = get_telegram_api_base().rstrip("/")
    url = f"{base_url}/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "NiftyRegimeEngine/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                return body.get("result", {}).get("message_id")
    except Exception as exc:
        print(f"[TELEGRAM WARNING] Send failed: {exc}", file=sys.stderr)
        return None
    return None


def edit_telegram_message(
    message_id: int,
    text: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "Markdown",
    timeout: int = 10,
) -> bool:
    """
    Edit an existing message (used for 30-sec live pinboard without spamming new messages).
    """
    t, c = get_telegram_credentials()
    bot_token = bot_token or t
    chat_id = chat_id or c

    if not bot_token or not chat_id or not message_id:
        return False

    base_url = get_telegram_api_base().rstrip("/")
    url = f"{base_url}/bot{bot_token}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "NiftyRegimeEngine/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception as exc:
        # Ignore Telegram 400 'message is not modified' errors gracefully
        if "message is not modified" not in str(exc).lower():
            print(f"[TELEGRAM WARNING] Edit failed: {exc}", file=sys.stderr)
        return False


def format_telegram_compact_update(
    live_nifty: Dict[str, Any],
    forecast: Dict[str, Any],
    alerts: Optional[List[Dict[str, str]]] = None,
    iteration: int = 1,
) -> str:
    """
    Format a high-conviction, professional trader mindset Telegram update.
    Emulates the real-time inner monologue and tactical thinking of an institutional trader.
    """
    now_str = datetime.now(IST).strftime("%H:%M:%S IST")
    price = live_nifty.get("price", 0.0)
    chg_pts = live_nifty.get("change_points", 0.0)
    chg_pct = live_nifty.get("change_pct", 0.0)
    pts_sign = "+" if chg_pts >= 0 else ""
    pct_sign = "+" if chg_pct >= 0 else ""

    r1 = forecast.get("nearest_resistance", {}).get("price", 0.0)
    s1 = forecast.get("nearest_support", {}).get("price", 0.0)
    exp = forecast.get("expected_range", {})
    ceil_p = exp.get("expected_daily_upper", 0.0)
    floor_p = exp.get("expected_daily_lower", 0.0)

    opt = forecast.get("option_data") or {}
    call_wall = opt.get("major_call_wall") or 24800
    put_floor = opt.get("major_put_floor") or 24400
    pcr = opt.get("pcr_oi", 0.91)

    bias = forecast.get("trading_bias", "NEUTRAL")
    conviction = forecast.get("conviction", "Moderate")
    regime = forecast.get("current_regime", "Normal")
    trend_emoji = "🟢" if "BULLISH" in bias else ("🔴" if "BEARISH" in bias else "🟡")

    # Smart money & internal market signals
    inst = forecast.get("institutional_data") or {}
    cs = inst.get("cash_summary", {})
    ds = inst.get("derivatives_summary", {})
    fii_net = cs.get("fii_net_crores", 0.0)
    long_ratio = ds.get("long_ratio_pct", 50.0)

    of = forecast.get("order_flow_data") or {}
    of_delta = of.get("delta_summary", {}).get("cumulative_volume_delta", 0)
    of_div = of.get("divergence_summary", {}).get("status", "NORMAL_FLOW")

    breadth = forecast.get("breadth_data") or {}
    b_adv = breadth.get("divergence_details", {}).get("advances", 25)
    b_dec = breadth.get("divergence_details", {}).get("declines", 25)

    sec = forecast.get("sectoral_data") or {}
    sec_lead = sec.get("sector_details", {}).get("top_driver", {}).get("name", "NIFTY BANK")

    # Trader's tactical inner monologue
    if r1 and price >= (r1 - 100):
        read_note = f"⚠️ *Approaching Resistance R1 (`{r1:,.0f}`)*. Do NOT buy the top blindly; wait for clean 15-m candle close."
        plan_note = (
            f"1. 🚀 *Breakout Long*: If 15-m candle closes *above `{r1:,.0f}`* with positive delta -> Call (CE) buy. Target: `{ceil_p:,.0f}`. SL: `{price:,.0f}`.\n"
            f"2. 🔻 *Rejection Short*: If red rejection wick forms at `{r1:,.0f}` -> Put (PE) buy. Target: `{s1 if s1 else price - 150:,.0f}`. SL: `{r1 + 25:,.0f}`."
        )
    elif s1 and price <= (s1 + 100):
        read_note = f"🛡️ *Testing Major Support S1 (`{s1:,.0f}`)*. Looking for buyer absorption & Put writer defense."
        plan_note = (
            f"1. 🟢 *Dip-Buy Bounce*: If green hammer forms at `{s1:,.0f}` -> Call (CE) buy. Target: `{price + 120:,.0f}`. SL: `{floor_p:,.0f}`.\n"
            f"2. ⚠️ *Breakdown Short*: Only if 15-m closes *below `{s1:,.0f}`* -> Target: `{floor_p:,.0f}`."
        )
    else:
        read_note = f"🧭 *Trend Following Mode* (`{regime}`). Riding momentum toward Resistance R1 (`{r1:,.0f}`)."
        plan_note = (
            f"1. 🟢 *Trend Hold*: Keep trailing stop-loss under Put Floor `{put_floor:,.0f}` / Support `{s1:,.0f}`.\n"
            f"2. 🎯 *Upside Target*: Call Wall `{call_wall:,.0f}` & Day Ceiling `{ceil_p:,.0f}`."
        )

    msg = (
        f"{trend_emoji} *NIFTY 50 LIVE SCANNER | PRO TRADER MINDSET*\n"
        f"⏰ `{now_str}` | Scan `#{iteration}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Spot*: `{price:,.2f}` ({pts_sign}{chg_pts:,.1f} | {pct_sign}{chg_pct:.2f}%)\n"
        f"🧭 *Regime*: `[{regime}]` | *Conviction*: `{conviction}`\n"
        f"🎯 *Bias*: `{bias.split('(')[0].strip()}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 *MY TACTICAL READ (Where We Stand)*:\n"
        f"{read_note}\n"
        f"• *Resistance R1*: `{r1:,.0f}` (Ceiling: `{ceil_p:,.0f}`)\n"
        f"• *Support S1*: `{s1:,.0f}` (Floor: `{floor_p:,.0f}`)\n"
        f"• *Institutional Walls*: Call Wall `{call_wall:,.0f}` | Put Floor `{put_floor:,.0f}`\n\n"
        f"🔍 *SMART MONEY & INTERNAL HEALTH*:\n"
        f"• FII Flow: `{fii_net:+,.0f} Cr` | FII Futures: `{long_ratio:.1f}% Long`\n"
        f"• Order Flow (CVD): `{of_delta:+,d}` delta (`{of_div}`)\n"
        f"• Breadth & Sector: `{b_adv} Advances / {b_dec} Declines` | Leader: `{sec_lead}`\n"
        f"• Put-Call Ratio: `PCR {pcr:.2f}`\n\n"
        f"🎯 *HOW I AM TRADING THIS (Trader's Thinking)*:\n"
        f"{plan_note}\n\n"
        f"🛡️ *TRADER'S GOLDEN RULE*:\n"
        f"_Capital preservation is #1. Never average a loser. Trade the reaction, not prediction._\n"
    )

    if alerts:
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━\n🚨 *LIVE ALERTS*:\n"
        for a in alerts[:3]:
            msg += f"• `{a.get('level')}`: {a.get('message')}\n"

    return msg
