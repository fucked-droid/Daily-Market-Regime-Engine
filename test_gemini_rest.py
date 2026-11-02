import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from gemini_rest import call_gemini_rest_api

class TestGeminiRestExpanded(unittest.TestCase):
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key_123"})
    @patch("urllib.request.urlopen")
    def test_successful_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "DIAGNOSIS_OK"}]}}] }'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = call_gemini_rest_api("Diagnose this error")
        self.assertTrue(res["success"])
        self.assertEqual(res["text"], "DIAGNOSIS_OK")

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key(self):
        res = call_gemini_rest_api("Diagnose this error")
        self.assertFalse(res["success"])
        self.assertIn("Missing GEMINI_API_KEY", res["error"])

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key_123"})
    @patch("urllib.request.urlopen")
    def test_http_error(self, mock_urlopen):
        err = urllib.error.HTTPError("http://test", 403, "Forbidden", {}, None)
        err.fp = MagicMock()
        err.fp.read.return_value = b"Access denied"
        mock_urlopen.side_effect = err

        res = call_gemini_rest_api("Diagnose this error")
        self.assertFalse(res["success"])
        self.assertIn("HTTPError 403", res["error"])
        # Non-503 HTTPError should not retry
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("time.sleep", return_value=None)
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key_123"})
    @patch("urllib.request.urlopen")
    def test_http_503_retry_success(self, mock_urlopen, mock_sleep):
        err = urllib.error.HTTPError("http://test", 503, "Service Unavailable", {}, None)
        err.fp = MagicMock()
        err.fp.read.return_value = b"Overloaded"

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "RETRY_OK"}]}}] }'
        mock_response.__enter__.return_value = mock_response

        mock_urlopen.side_effect = [err, mock_response]

        res = call_gemini_rest_api("Diagnose this error")
        self.assertTrue(res["success"])
        self.assertEqual(res["text"], "RETRY_OK")
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @patch("time.sleep", return_value=None)
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key_123"})
    @patch("urllib.request.urlopen")
    def test_http_503_exhausted_retries(self, mock_urlopen, mock_sleep):
        err = urllib.error.HTTPError("http://test", 503, "Service Unavailable", {}, None)
        err.fp = MagicMock()
        err.fp.read.return_value = b"Overloaded"

        mock_urlopen.side_effect = [err, err, err]

        res = call_gemini_rest_api("Diagnose this error")
        self.assertFalse(res["success"])
        self.assertIn("HTTPError 503", res["error"])
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key_123"})
    @patch("urllib.request.urlopen")
    def test_url_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        res = call_gemini_rest_api("Diagnose this error")
        self.assertFalse(res["success"])
        self.assertIn("URLError", res["error"])
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("time.sleep", return_value=None)
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key_123"})
    @patch("urllib.request.urlopen")
    def test_timeout_retry_success(self, mock_urlopen, mock_sleep):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "TIMEOUT_RETRY_OK"}]}}] }'
        mock_response.__enter__.return_value = mock_response

        mock_urlopen.side_effect = [socket.timeout("timed out"), mock_response]

        res = call_gemini_rest_api("Diagnose this error")
        self.assertTrue(res["success"])
        self.assertEqual(res["text"], "TIMEOUT_RETRY_OK")
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @patch("time.sleep", return_value=None)
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key_123"})
    @patch("urllib.request.urlopen")
    def test_url_error_timeout_retry_success(self, mock_urlopen, mock_sleep):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "URL_TIMEOUT_OK"}]}}] }'
        mock_response.__enter__.return_value = mock_response

        mock_urlopen.side_effect = [urllib.error.URLError(socket.timeout("timed out")), mock_response]

        res = call_gemini_rest_api("Diagnose this error")
        self.assertTrue(res["success"])
        self.assertEqual(res["text"], "URL_TIMEOUT_OK")
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key_123"})
    @patch("urllib.request.urlopen")
    def test_oversized_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'x' * 600_000
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = call_gemini_rest_api("Diagnose this error")
        self.assertFalse(res["success"])
        self.assertIn("exceeded maximum size limit", res["error"])

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key_123"})
    @patch("urllib.request.urlopen")
    def test_missing_candidates(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{\"candidates\": []}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = call_gemini_rest_api("Diagnose this error")
        self.assertFalse(res["success"])
        self.assertIn("No candidates returned", res["error"])

    @patch.dict("os.environ", {"GEMINI_API_KEY": "test_key_123"})
    @patch("urllib.request.urlopen")
    def test_invalid_json_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'INVALID JSON'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = call_gemini_rest_api("Diagnose this error")
        self.assertFalse(res["success"])

if __name__ == "__main__":
    unittest.main()
