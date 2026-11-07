"""
Unit tests for Telegram Bot notification module.
"""

import sys
from pathlib import Path
REPO_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_DIR))

import unittest
from unittest.mock import patch, MagicMock
import json

from src.telegram_bot import (
    format_telegram_compact_update,
    send_telegram_message,
    edit_telegram_message,
    get_telegram_credentials,
)


class TestTelegramBot(unittest.TestCase):

    def test_format_telegram_compact_update(self):
        live_nifty = {
            "price": 24548.10,
            "change_points": 587.50,
            "change_pct": 2.45,
        }
        forecast = {
            "current_regime": "Bullish",
            "trading_bias": "BULLISH (Upward Momentum Favored)",
            "nearest_resistance": {"price": 24774.30},
            "nearest_support": {"price": 22229.17},
            "expected_range": {
                "expected_daily_upper": 24868.48,
                "expected_daily_lower": 24227.72,
            },
            "option_data": {
                "major_call_wall": 24800,
                "major_put_floor": 24400,
            },
        }
        alerts = [{"level": "HIGH", "message": "Resistance approaching"}]

        msg = format_telegram_compact_update(live_nifty, forecast, alerts=alerts, iteration=5)
        self.assertIn("NIFTY 50 LIVE SCANNER", msg)
        self.assertIn("24,548.10", msg)
        self.assertIn("24,774", msg)
        self.assertIn("24,400", msg)
        self.assertIn("LIVE ALERTS", msg)

    @patch("urllib.request.urlopen")
    def test_send_telegram_message_mock(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"ok": True, "result": {"message_id": 999}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = send_telegram_message("Hello Test", bot_token="fake_token", chat_id="123456")
        self.assertEqual(res, 999)

    @patch("urllib.request.urlopen")
    def test_edit_telegram_message_mock(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"ok": True, "result": {"message_id": 999}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = edit_telegram_message(999, "Edited Text", bot_token="fake_token", chat_id="123456")
        self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()
