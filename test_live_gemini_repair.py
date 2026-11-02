import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from live_repair import live_gemini_diagnose_and_patch, PROTECTED_FILES

class TestLiveGeminiRepairSecurityAndParsing(unittest.TestCase):
    def test_project_root_containment(self):
        outside_path = Path("C:/Windows/System32/calc.py")
        res = live_gemini_diagnose_and_patch(outside_path, "SyntaxError", "error")
        self.assertFalse(res["patched"])
        self.assertIn("outside project root", res["error"])

    def test_protected_file_restrictions(self):
        for protected in PROTECTED_FILES:
            target = Path(__file__).resolve().parent / "src" / protected
            res = live_gemini_diagnose_and_patch(target, "RuntimeError", "error")
            self.assertFalse(res["patched"])
            self.assertIn("protected", res["error"])

    @patch("live_repair.call_gemini_rest_api")
    def test_successful_structured_parsing(self, mock_call_api):
        mock_call_api.return_value = {
            "success": True,
            "text": '{"diagnosis": "Missing definition", "target": "test_target.py", "diff": "def test_func(): return True", "rationale": "Adds missing function"}'
        }

        target = Path("test_target_sandbox.py")
        target.write_text("print(test_func())\n", encoding="utf-8")

        try:
            res = live_gemini_diagnose_and_patch(target, "NameError", "NameError: name 'test_func' is not defined")
            self.assertTrue(res["diagnosed"])
            self.assertTrue(res["patched"])
            self.assertEqual(res["strategy"], "live_gemini_structured_proposal")
            self.assertFalse(res["production_modified"])
            
            # Verify production file is unchanged
            self.assertIn("print(test_func())", target.read_text(encoding="utf-8"))
        finally:
            if target.exists():
                target.unlink()

    @patch("live_repair.call_gemini_rest_api")
    def test_invalid_json_response(self, mock_call_api):
        mock_call_api.return_value = {
            "success": True,
            "text": 'NOT JSON CONTENT'
        }

        target = Path("test_target_sandbox.py")
        target.write_text("x = 1\n", encoding="utf-8")

        try:
            res = live_gemini_diagnose_and_patch(target, "SyntaxError", "SyntaxError")
            self.assertTrue(res["diagnosed"])
            self.assertFalse(res["patched"])
            self.assertIn("Failed to parse structured JSON", res["error"])
        finally:
            if target.exists():
                target.unlink()

    @patch("live_repair.call_gemini_rest_api")
    def test_malformed_diff_syntax_failure(self, mock_call_api):
        mock_call_api.return_value = {
            "success": True,
            "text": '{"diagnosis": "Syntax error", "target": "test_target.py", "diff": "INVALID PYTHON SYNTAX ::::", "rationale": "bad fix"}'
        }

        target = Path("test_target_sandbox.py")
        target.write_text("x = 1\n", encoding="utf-8")

        try:
            res = live_gemini_diagnose_and_patch(target, "SyntaxError", "SyntaxError")
            self.assertTrue(res["diagnosed"])
            self.assertFalse(res["patched"])
            self.assertIn("Static syntax validation failed", res["error"])
        finally:
            if target.exists():
                target.unlink()

    @patch("live_repair.call_gemini_rest_api")
    def test_api_failure_fail_closed(self, mock_call_api):
        mock_call_api.return_value = {
            "success": False,
            "error": "API timeout"
        }

        target = Path("test_target_sandbox.py")
        target.write_text("x = 1\n", encoding="utf-8")

        try:
            res = live_gemini_diagnose_and_patch(target, "RuntimeError", "error")
            self.assertFalse(res["diagnosed"])
            self.assertFalse(res["patched"])
            self.assertIn("Gemini API call failed", res["error"])
        finally:
            if target.exists():
                target.unlink()

if __name__ == "__main__":
    unittest.main()
