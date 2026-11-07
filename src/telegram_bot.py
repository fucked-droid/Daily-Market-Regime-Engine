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
    """Format a clean, mobile-friendly Telegram Markdown message."""
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

    bias = forecast.get("trading_bias", "NEUTRAL")
    trend_emoji = "🟢" if "BULLISH" in bias else ("🔴" if "BEARISH" in bias else "🟡")

    msg = (
        f"{trend_emoji} *NIFTY 50 LIVE SCANNER* (30s Update)\n"
        f"⏰ `{now_str}` | Scan `#{iteration}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *Spot*: `{price:,.2f}` ({pts_sign}{chg_pts:,.1f} | {pct_sign}{chg_pct:.2f}%)\n"
        f"🧭 *Regime*: `{forecast.get('current_regime', 'Unknown')}`\n"
        f"🎯 *Bias*: `{bias.split('(')[0].strip()}`\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔴 *Resistance R1*: `{r1:,.0f}` (Ceiling: `{ceil_p:,.0f}`)\n"
        f"🟢 *Support S1*: `{s1:,.0f}` (Floor: `{floor_p:,.0f}`)\n"
        f"🧱 *Call Wall*: `{call_wall:,.0f}` | *Put Floor*: `{put_floor:,.0f}`\n"
    )

    if alerts:
        msg += f"━━━━━━━━━━━━━━━━━━\n🚨 *LIVE ALERTS*:\n"
        for a in alerts[:3]:
            msg += f"• `{a.get('level')}`: {a.get('message')}\n"

    return msg
