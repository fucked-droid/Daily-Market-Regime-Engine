#!/usr/bin/env python3
"""
NIFTY INTRADAY | SMC REGIME LIVE TELEGRAM DISPATCHER
===================================================
Continuously scans NIFTY 50 price action, computes Smart Money Concepts (SMC):
- BSL / SSL Liquidity Sweeps
- Market Structure Shift (MSS / BOS)
- Unmitigated Fair Value Gaps (FVG)
- Institutional Order Blocks (OB)
- Execution Zone, Laxman Rekha (SL), and Target

Dispatches and EDITS ONE SINGLE MESSAGE IN TELEGRAM every 30 seconds
(No notification spam, live in-place widget).
"""

from datetime import datetime, timezone, timedelta
import argparse
import os
import sys
import time
import signal
import subprocess
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

PID_FILE = ROOT_DIR / "smc_scanner.pid"
LOG_FILE = ROOT_DIR / "smc_scanner.log"

from src.order_block import (
    detect_order_blocks,
    detect_fair_value_gaps,
    analyze_smc_regime,
    format_smc_alert_text,
    format_simple_hindi_alert_text,
)
from src.market_data import fetch_yahoo_chart
from src.live_scanner import fetch_live_quote
from src.telegram_alerts import (
    get_telegram_credentials,
    update_or_send_live_widget,
    load_widget_state,
)

IST = timezone(timedelta(hours=5, minutes=30))


def run_smc_telegram_loop(
    interval: int = 30,
    max_iterations: int = None,
    dry_run: bool = False,
    simple_mode: bool = True,
):
    token, chat_id = get_telegram_credentials()
    if not dry_run and (not token or not chat_id):
        print("❌ [ERROR] Telegram credentials not found.")
        print("Please configure /root/.telegram_config.json with bot_token and chat_id.")
        sys.exit(1)

    print("=" * 65)
    print(" ⚡ NIFTY INTRADAY | SMC REGIME TELEGRAM LIVE ENGINE")
    print("=" * 65)
    print(f" ⏱️  Refresh Interval : {interval} seconds")
    print(f" 🎯 Single Msg Mode  : ON (Edits same message every {interval}s)")
    print(f" 📘 Format Mode      : {'Aasan Bhasha (Simple Hindi)' if simple_mode else 'SMC Technical'}")
    if not dry_run:
        state = load_widget_state()
        existing_id = state.get("widget_message_id")
        print(f" 📲 Telegram Target  : Chat ID {chat_id} (Active Msg ID: {existing_id or 'New'})")
    else:
        print(" 🧪 DRY-RUN MODE    : Telegram API dispatch disabled (Console only)")
    print("=" * 65)

    # Initial 15m chart fetch
    print("📊 Loading NIFTY 50 institutional chart data...")
    try:
        chart_df = fetch_yahoo_chart("^NSEI", interval="15m", range_str="5d")
    except Exception as e:
        print(f"⚠️ Warning: Could not fetch initial chart: {e}")
        chart_df = None

    iteration = 1
    try:
        while True:
            try:
                now_ist = datetime.now(IST).strftime("%H:%M:%S IST")

                # 1. Fetch live tick
                live_nifty = fetch_live_quote("^NSEI")
                live_vix = fetch_live_quote("^INDIAVIX")

                # Periodic chart refresh every 10 iterations (5 mins)
                if iteration % 10 == 0 or chart_df is None:
                    try:
                        chart_df = fetch_yahoo_chart("^NSEI", interval="15m", range_str="5d")
                    except Exception:
                        pass

                # 2. Compute SMC Framework
                smc = analyze_smc_regime(
                    df_intraday=chart_df,
                    live_nifty=live_nifty,
                    live_vix=live_vix,
                )

                # 3. Format Card
                if simple_mode:
                    card_text = format_simple_hindi_alert_text(
                        smc=smc,
                        iteration=iteration,
                        time_str=now_ist,
                    )
                else:
                    card_text = format_smc_alert_text(
                        smc=smc,
                        iteration=iteration,
                        time_str=now_ist,
                    )

                # 4. Dispatch to Telegram (In-Place Edit)
                if dry_run:
                    print(f"\n[#{iteration} - {now_ist}] Console Preview:")
                    print(card_text)
                else:
                    msg_id = update_or_send_live_widget(
                        text=card_text,
                        bot_token=token,
                        chat_id=chat_id,
                        pin=True,
                    )
                    spot_val = smc["spot"]
                    action_val = smc["action"]
                    print(f"[{now_ist}] 📲 [TELEGRAM #{iteration}] Msg ID {msg_id} edited in-place | Spot: {spot_val:,.1f} | {action_val}", flush=True)

                iteration += 1
                if max_iterations and iteration > max_iterations:
                    print(f"Completed {max_iterations} iterations. Exiting.", flush=True)
                    break

            except Exception as loop_err:
                print(f"⚠️ [WARNING] Loop iteration #{iteration} error: {loop_err}", flush=True)

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n🛑 SMC Telegram Engine stopped by user.", flush=True)


def acquire_wake_lock():
    """Acquires Android Termux wake-lock to prevent CPU sleep when screen is off."""
    wake_lock_bin = "/data/data/com.termux/files/usr/bin/termux-wake-lock"
    if os.path.exists(wake_lock_bin):
        try:
            subprocess.run([wake_lock_bin], check=False, timeout=3)
        except Exception:
            pass


def is_process_running(pid: int) -> bool:
    """Checks if a process with given PID is currently active."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_active_daemon_pid() -> int:
    """Reads PID from file and verifies if it is running."""
    if not PID_FILE.exists():
        return 0
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        if is_process_running(pid):
            return pid
        else:
            PID_FILE.unlink(missing_ok=True)
            return 0
    except Exception:
        return 0


def start_daemon(interval: int = 30, technical: bool = False):
    """Starts worker loop as a detached background process."""
    existing_pid = get_active_daemon_pid()
    if existing_pid:
        print(f"[SMC Daemon] Already running with PID {existing_pid}.")
        return

    acquire_wake_lock()

    cmd = [sys.executable, str(Path(__file__).resolve()), "--interval", str(interval)]
    if technical:
        cmd.append("--technical")

    with open(LOG_FILE, "a", encoding="utf-8") as out:
        proc = subprocess.Popen(
            cmd,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

    time.sleep(1)
    if is_process_running(proc.pid):
        print(f"[SMC Daemon] ✓ Started successfully in background! (PID: {proc.pid})")
        print(f"[SMC Daemon] 📜 Log file: {LOG_FILE}")
        print(f"[SMC Daemon] To monitor logs: tail -f {LOG_FILE}")
    else:
        print("[SMC Daemon] ✖ Failed to start background worker. Check logs.")


def stop_daemon():
    """Stops the active background daemon process."""
    pid = get_active_daemon_pid()
    if not pid:
        print("[SMC Daemon] No active daemon found running.")
        PID_FILE.unlink(missing_ok=True)
        return

    print(f"[SMC Daemon] Stopping background worker (PID: {pid})...")
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        if is_process_running(pid):
            os.kill(pid, signal.SIGKILL)
        print("[SMC Daemon] ✓ Stopped successfully.")
    except Exception as e:
        print(f"[SMC Daemon] Stop error: {e}")
    finally:
        PID_FILE.unlink(missing_ok=True)


def status_daemon():
    """Prints status and latest logs of the SMC daemon."""
    pid = get_active_daemon_pid()
    print("=" * 60)
    print("  📊 NIFTY SMC LIVE TELEGRAM ENGINE — DAEMON STATUS")
    print("=" * 60)
    if pid:
        print(f"Status       : 🟢 ACTIVE & RUNNING")
        print(f"Process PID  : {pid}")
    else:
        print(f"Status       : 🔴 INACTIVE / STOPPED")
    print(f"Log File     : {LOG_FILE}")
    print("-" * 60)
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                print("Last 8 Log Entries:")
                for l in lines[-8:]:
                    print(f"  {l.strip()}")
        except Exception:
            pass
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Live SMC Telegram Dispatcher for NIFTY")
    parser.add_argument("action", nargs="?", choices=["start", "stop", "status", "restart"], help="Daemon control: start, stop, status, restart")
    parser.add_argument("--interval", "-i", type=int, default=30, help="Refresh interval in seconds (default: 30)")
    parser.add_argument("--once", "-1", action="store_true", help="Update the message once and exit immediately")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Print card locally without dispatching to Telegram")
    parser.add_argument("--technical", action="store_true", help="Use advanced technical SMC English format instead of simple Hindi")
    args = parser.parse_args()

    if args.action == "start":
        start_daemon(interval=args.interval, technical=args.technical)
        return
    elif args.action == "stop":
        stop_daemon()
        return
    elif args.action == "status":
        status_daemon()
        return
    elif args.action == "restart":
        stop_daemon()
        time.sleep(1)
        start_daemon(interval=args.interval, technical=args.technical)
        return

    max_iter = 1 if args.once else None
    run_smc_telegram_loop(
        interval=args.interval,
        max_iterations=max_iter,
        dry_run=args.dry_run,
        simple_mode=not args.technical,
    )


if __name__ == "__main__":
    main()
