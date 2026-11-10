"""
Telegram Alert Dispatcher for NIFTY Market Regime Scanner.
Provides:
1. Smart Live Widget: Silently edits a single pinned message in place every 30s (no notification spam).
2. Actionable Push Alerts: Loud audible pings with high-impact, lockscreen-readable Hinglish text only on key triggers (Breakouts, Order Blocks, VIX spike).
"""

from datetime import datetime, timezone, timedelta
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

IST = timezone(timedelta(hours=5, minutes=30))
CONFIG_FILE = Path("/root/.telegram_config.json")
WIDGET_STATE_FILE = Path("/root/.telegram_widget_state.json")
COOLDOWN_STATE_FILE = Path("/root/.telegram_cooldown_state.json")


def auto_discover_chat_id(bot_token: str) -> Optional[str]:
    """Poll getUpdates to automatically discover chat_id if user sent /start."""
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NiftyRegimeBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok") and data.get("result"):
                for update in reversed(data["result"]):
                    msg = update.get("message") or update.get("channel_post") or update.get("edited_message")
                    if msg and "chat" in msg and "id" in msg["chat"]:
                        found_id = str(msg["chat"]["id"])
                        save_telegram_credentials(bot_token, found_id)
                        print(f"[TELEGRAM] Auto-discovered Chat ID: {found_id}", file=sys.stderr)
                        return found_id
    except Exception:
        pass
    return None


def get_telegram_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Retrieve Telegram Bot Token and Chat ID from environment or config file."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                bot_token = bot_token or data.get("bot_token")
                chat_id = chat_id or data.get("chat_id")
            except Exception:
                pass

    if bot_token and not chat_id:
        chat_id = auto_discover_chat_id(bot_token)

    return bot_token, chat_id


def save_telegram_credentials(bot_token: str, chat_id: str) -> None:
    """Save Telegram Bot Token and Chat ID to local configuration file."""
    CONFIG_FILE.write_text(
        json.dumps({"bot_token": bot_token.strip(), "chat_id": str(chat_id).strip()}, indent=2),
        encoding="utf-8"
    )


def send_telegram_message(
    text: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
    disable_notification: bool = False,
) -> Optional[int]:
    """
    Send a message via Telegram Bot API.
    Returns message_id if sent successfully, None otherwise.
    """
    token, target_chat = bot_token, chat_id
    if not token or not target_chat:
        env_token, env_chat = get_telegram_credentials()
        token = token or env_token
        target_chat = target_chat or env_chat

    if not token or not target_chat:
        return None

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
        "disable_notification": disable_notification,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                return body.get("result", {}).get("message_id")
    except Exception as exc:
        print(f"[TELEGRAM WARNING] Failed to send message: {exc}", file=sys.stderr)
    return None


def edit_telegram_message(
    message_id: int,
    text: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
) -> bool:
    """
    Edit an existing message via Telegram Bot API.
    Handles 'message is not modified' gracefully.
    """
    token, target_chat = bot_token, chat_id
    if not token or not target_chat:
        env_token, env_chat = get_telegram_credentials()
        token = token or env_token
        target_chat = target_chat or env_chat

    if not token or not target_chat or not message_id:
        return False

    url = f"https://api.telegram.org/bot{token}/editMessageText"
    payload = {
        "chat_id": target_chat,
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
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as http_err:
        err_msg = http_err.read().decode("utf-8")
        if "message is not modified" in err_msg:
            # Content is identical, edit is effectively successful
            return True
        print(f"[TELEGRAM WARNING] editMessageText HTTP error: {http_err.code} {err_msg}", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"[TELEGRAM WARNING] Failed to edit message: {exc}", file=sys.stderr)
        return False


def pin_telegram_message(
    message_id: int,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """Pin the live widget message silently at the top of the chat."""
    token, target_chat = bot_token, chat_id
    if not token or not target_chat:
        env_token, env_chat = get_telegram_credentials()
        token = token or env_token
        target_chat = target_chat or env_chat

    if not token or not target_chat:
        return False

    url = f"https://api.telegram.org/bot{token}/pinChatMessage"
    payload = {
        "chat_id": target_chat,
        "message_id": message_id,
        "disable_notification": True,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False


def load_widget_state() -> Dict[str, Any]:
    """Load the current widget message ID from persistent state."""
    if WIDGET_STATE_FILE.exists():
        try:
            return json.loads(WIDGET_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_widget_state(state: Dict[str, Any]) -> None:
    """Save the widget state to persistent file."""
    try:
        WIDGET_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def update_or_send_live_widget(
    text: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    pin: bool = True,
) -> Optional[int]:
    """
    Smart Live Widget Dispatcher:
    - If widget message already exists, silently edit it in place.
    - If it fails (e.g., deleted by user), create a new message, pin it, and save ID.
    - Eliminates all notification spam while keeping the card always 100% live.
    """
    state = load_widget_state()
    msg_id = state.get("widget_message_id")

    if msg_id:
        success = edit_telegram_message(
            message_id=msg_id,
            text=text,
            bot_token=bot_token,
            chat_id=chat_id,
        )
        if success:
            return msg_id

    # Fallback or initial creation
    new_id = send_telegram_message(
        text=text,
        bot_token=bot_token,
        chat_id=chat_id,
        disable_notification=True,
    )
    if new_id:
        state["widget_message_id"] = new_id
        state["created_at"] = time.time()
        save_widget_state(state)
        if pin:
            pin_telegram_message(new_id, bot_token=bot_token, chat_id=chat_id)
        return new_id

    return None


def load_cooldown_state() -> Dict[str, float]:
    """Load alert cooldown timestamps."""
    if COOLDOWN_STATE_FILE.exists():
        try:
            return json.loads(COOLDOWN_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_cooldown_state(state: Dict[str, float]) -> None:
    """Save alert cooldown timestamps."""
    try:
        COOLDOWN_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def send_discrete_alert(
    alert_key: str,
    alert_text: str,
    cooldown_seconds: int = 300,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """
    Send an audible, high-priority push notification.
    Applies cooldown per alert_key (default 5 minutes) so the phone isn't spammed.
    """
    cooldowns = load_cooldown_state()
    now = time.time()
    last_sent = cooldowns.get(alert_key, 0.0)

    if (now - last_sent) < cooldown_seconds:
        # Still within cooldown window; suppress sound ping
        return False

    # Send with audible notification sound (disable_notification=False)
    msg_id = send_telegram_message(
        text=alert_text,
        bot_token=bot_token,
        chat_id=chat_id,
        disable_notification=False,
    )
    if msg_id:
        cooldowns[alert_key] = now
        save_cooldown_state(cooldowns)
        return True
    return False


def format_lockscreen_alert(
    alert: Dict[str, Any],
    live_nifty: Dict[str, Any],
    forecast: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Format a high-impact, lockscreen-readable Hinglish push alert.
    Returns (alert_key, formatted_message).
    Designed so the user understands the COMPLETE status from the notification banner itself!
    """
    alert_type = alert.get("type", "GENERAL")
    price = live_nifty.get("price", 0.0)
    change = live_nifty.get("change_points", 0.0)
    change_pct = live_nifty.get("change_pct", 0.0)
    sign = "+" if change >= 0 else ""
    arrow = "🟢" if change >= 0 else "🔴"

    nr = forecast.get("nearest_resistance", {})
    ns = forecast.get("nearest_support", {})
    r_val = nr.get("price", 0.0) if nr else 0.0
    s_val = ns.get("price", 0.0) if ns else 0.0

    ob_data = forecast.get("order_blocks", {})
    nb = ob_data.get("nearest_bullish") if ob_data else None
    ns_ob = ob_data.get("nearest_bearish") if ob_data else None

    if alert_type == "BREAKOUT":
        key = "BREAKOUT"
        msg = (
            f"🚀 <b>NIFTY ALERT: RESISTANCE BREAKOUT!</b>\n"
            f"💰 <b>Bhaav:</b> <code>{price:,.2f}</code> ({arrow} {sign}{change:,.1f} pts / {sign}{change_pct:.2f}%)\n"
            f"🎯 <b>Status:</b> R1 Resistance (<code>{r_val:,.0f}</code>) tod kar upar nikal gaya!\n"
            f"💡 <b>Action:</b> Call buyers active. Trailing SL <code>{price - 40:,.0f}</code> rakhein."
        )
    elif alert_type == "BREAKDOWN":
        key = "BREAKDOWN"
        msg = (
            f"🔻 <b>NIFTY ALERT: SUPPORT BREAKDOWN!</b>\n"
            f"💰 <b>Bhaav:</b> <code>{price:,.2f}</code> ({arrow} {sign}{change:,.1f} pts / {sign}{change_pct:.2f}%)\n"
            f"🎯 <b>Status:</b> S1 Support (<code>{s_val:,.0f}</code>) toot gaya hai!\n"
            f"💡 <b>Action:</b> Sellers active. Long trades me SL lagayein ya exit karein."
        )
    elif alert_type == "ORDER_BLOCK_DEMAND":
        key = "OB_DEMAND"
        b_range = f"{nb['bottom']:,.0f} - {nb['top']:,.0f}" if nb else "Demand Zone"
        msg = (
            f"🧱 <b>NIFTY ALERT: DEMAND ZONE HIT!</b>\n"
            f"💰 <b>Bhaav:</b> <code>{price:,.2f}</code>\n"
            f"🎯 <b>Status:</b> Institutional Bullish Order Block [<code>{b_range}</code>] test ho raha hai.\n"
            f"💡 <b>Action:</b> Smart Money buying zone! Green bounce candle par Call entry dekhein."
        )
    elif alert_type == "ORDER_BLOCK_SUPPLY":
        key = "OB_SUPPLY"
        s_range = f"{ns_ob['bottom']:,.0f} - {ns_ob['top']:,.0f}" if ns_ob else "Supply Zone"
        msg = (
            f"🧱 <b>NIFTY ALERT: SUPPLY ZONE HIT!</b>\n"
            f"💰 <b>Bhaav:</b> <code>{price:,.2f}</code>\n"
            f"🎯 <b>Status:</b> Institutional Bearish Order Block [<code>{s_range}</code>] test ho raha hai.\n"
            f"💡 <b>Action:</b> Institutional profit booking zone! Top par blind buy na karein."
        )
    elif alert_type == "VIX_SPIKE":
        key = "VIX_SPIKE"
        raw_msg = alert.get("message", "")
        msg = (
            f"⚡ <b>NIFTY ALERT: INDIA VIX SPIKE!</b>\n"
            f"💰 <b>Bhaav:</b> <code>{price:,.2f}</code>\n"
            f"🎯 <b>Status:</b> {raw_msg}\n"
            f"💡 <b>Action:</b> Option premiums me tez jhatke lagenge. Tight Stop-Loss rakhein!"
        )
    elif alert_type == "MOMENTUM" and live_nifty.get("position_in_range_pct", 50) >= 90:
        key = "DAY_HIGH"
        msg = (
            f"🔥 <b>NIFTY ALERT: DAY HIGH TEST!</b>\n"
            f"💰 <b>Bhaav:</b> <code>{price:,.2f}</code> (Day High: <code>{live_nifty.get('day_high', price):,.1f}</code>)\n"
            f"🎯 <b>Status:</b> NIFTY din ke sabse unche level par daud raha hai!\n"
            f"💡 <b>Action:</b> Zabardast tezi. FOMO buy na karein, profits trail karein."
        )
    elif alert_type == "MOMENTUM" and live_nifty.get("position_in_range_pct", 50) <= 10:
        key = "DAY_LOW"
        msg = (
            f"⚠️ <b>NIFTY ALERT: DAY LOW TEST!</b>\n"
            f"💰 <b>Bhaav:</b> <code>{price:,.2f}</code> (Day Low: <code>{live_nifty.get('day_low', price):,.1f}</code>)\n"
            f"🎯 <b>Status:</b> NIFTY din ke sabse nichle level ke paas fisal gaya hai.\n"
            f"💡 <b>Action:</b> Bikwali ka dabav. Support confirmation ke bina buy na karein."
        )
    else:
        key = f"ALERT_{alert_type}"
        msg = (
            f"🔔 <b>NIFTY LIVE ALERT ({alert_type})</b>\n"
            f"💰 <b>Bhaav:</b> <code>{price:,.2f}</code>\n"
            f"🎯 <b>Message:</b> {alert.get('message', '')}"
        )

    return key, msg


def format_live_widget_card(
    live_nifty: Dict[str, Any],
    live_vix: Optional[Dict[str, Any]] = None,
    heavyweights: Optional[List[Dict[str, Any]]] = None,
    forecast: Optional[Dict[str, Any]] = None,
    alerts: Optional[List[Dict[str, Any]]] = None,
    iteration: int = 1,
) -> str:
    """
    Format the silent in-place auto-updating SMC Regime Alert widget.
    Updates every 30 seconds inside Telegram without creating a new message or ping sound.
    Matches the exact NIFTY INTRADAY | SMC REGIME ALERT structure.
    """
    from src.order_block import analyze_smc_regime, format_smc_alert_text

    forecast_dict = forecast or {}
    smc = forecast_dict.get("smc")
    if not smc:
        chart_df = forecast_dict.get("chart_df")
        smc = analyze_smc_regime(
            df_intraday=chart_df,
            live_nifty=live_nifty,
            live_vix=live_vix,
            forecast=forecast_dict,
        )

    now_ist = datetime.now(IST).strftime("%H:%M:%S IST")
    return format_smc_alert_text(smc, iteration=iteration, time_str=now_ist)


def format_general_market_tracker(
    live_nifty: Dict[str, Any],
    live_vix: Optional[Dict[str, Any]],
    heavyweights: List[Dict[str, Any]],
    forecast: Dict[str, Any],
    alerts: List[Dict[str, Any]],
    iteration: int,
) -> str:
    """
    Alternative full market tracker card with heavyweight and breadth overview.
    """
    now_ist = datetime.now(IST).strftime("%H:%M:%S IST")
    price = live_nifty.get("price", 0.0)
    change = live_nifty.get("change_points", 0.0)
    change_pct = live_nifty.get("change_pct", 0.0)
    change_sign = "+" if change >= 0 else ""
    arrow = "🟢" if change >= 0 else "🔴"

    day_low = live_nifty.get("day_low", price)
    day_high = live_nifty.get("day_high", price)
    pos_pct = live_nifty.get("position_in_range_pct", 50.0)

    vix_val = live_vix.get("price", 0.0) if live_vix else 0.0
    vix_chg = live_vix.get("change_pct", 0.0) if live_vix else 0.0
    vix_sign = "+" if vix_chg >= 0 else ""

    if change_pct > 0.8 or pos_pct >= 85:
        mood = "Zabardast Tezi (Strong Bullish) 🚀"
    elif change_pct > 0:
        mood = "Positive / Tezi (Mild Bullish) 🟢"
    elif change_pct < -0.8 or pos_pct <= 15:
        mood = "Badi Girawat (Strong Bearish) 🔻"
    else:
        mood = "Consolidation / Rangebound ⚖️"

    filled = max(0, min(10, int(round(pos_pct / 10.0))))
    bar = "─" * filled + "●" + "─" * (10 - filled)

    lines = [
        f"📊 <b>NIFTY 50 LIVE TRACKER</b> 🟢 <i>({now_ist})</i>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"💰 <b>SPOT BHAAV:</b> <code>{price:,.2f}</code> ({arrow} {change_sign}{change:,.2f} / {change_sign}{change_pct:.2f}%)",
        f"🎯 <b>Day Range:</b> <code>{day_low:,.0f}</code> {bar} <code>{day_high:,.0f}</code> ({pos_pct:.0f}%)",
        f"⚡ <b>India VIX:</b> <code>{vix_val:.2f}</code> ({vix_sign}{vix_chg:.2f}%) | <b>Mood:</b> {mood}",
    ]
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🔄 <i>Auto-refreshing in place (#{iteration})</i>")
    return "\n".join(lines)


# Backwards compatibility alias
format_telegram_market_update = format_live_widget_card
