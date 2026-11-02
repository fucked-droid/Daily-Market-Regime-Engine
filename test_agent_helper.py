import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from agent_helper import run_python_script

class TestAgentHelper(unittest.TestCase):
    def test_successful_execution(self):
        script = Path("test_success_temp.py")
        script.write_text("print('SUCCESS TEST')\n", encoding="utf-8")
        try:
            res = run_python_script(script)
            self.assertTrue(res["success"])
            self.assertEqual(res["exit_code"], 0)
            self.assertIn("SUCCESS TEST", res["stdout"])
            self.assertFalse(res["timeout"])
            self.assertIsNone(res["error_category"])
        finally:
            if script.exists():
                script.unlink()

    def test_nonzero_exit_code(self):
        script = Path("test_error_temp.py")
        script.write_text("import sys; sys.exit(7)\n", encoding="utf-8")
        try:
            res = run_python_script(script)
            self.assertFalse(res["success"])
            self.assertEqual(res["exit_code"], 7)
            self.assertEqual(res["error_category"], "NonzeroExitCode")
        finally:
            if script.exists():
                script.unlink()

    def test_timeout_handling(self):
        script = Path("test_timeout_temp.py")
        script.write_text("import time; time.sleep(5)\n", encoding="utf-8")
        try:
            res = run_python_script(script, timeout=1)
            self.assertFalse(res["success"])
            self.assertTrue(res["timeout"])
            self.assertEqual(res["error_category"], "TimeoutExpired")
        finally:
            if script.exists():
                script.unlink()

    def test_script_path_with_spaces(self):
        script = Path("test space script.py")
        script.write_text("print('SPACES OK')\n", encoding="utf-8")
        try:
            res = run_python_script(script)
            self.assertTrue(res["success"])
            self.assertIn("SPACES OK", res["stdout"])
        finally:
            if script.exists():
                script.unlink()

    def test_invalid_script_path(self):
        script = Path("nonexistent_script_99999.py")
        res = run_python_script(script)
        self.assertFalse(res["success"])
        self.assertIsNotNone(res["stderr"])

    def test_unicode_output_and_stderr(self):
        script = Path("test_unicode.py")
        script.write_text("import sys\nprint('Unicode Test: ABC')\nsys.stderr.write('Error Test: WARN\\n')\n", encoding="utf-8")
        try:
            res = run_python_script(script)
            self.assertTrue(res["success"])
            self.assertIn("Unicode Test: ABC", res["stdout"])
            self.assertIn("Error Test: WARN", res["stderr"])
        finally:
            if script.exists():
                script.unlink()

    def test_large_output(self):
        script = Path("test_large.py")
        script.write_text("print('LINE')\n" * 5000, encoding="utf-8")
        try:
            res = run_python_script(script)
            self.assertTrue(res["success"])
            non_empty_lines = [l for l in res["stdout"].splitlines() if l == "LINE"]
            self.assertEqual(len(non_empty_lines), 5000)
        finally:
            if script.exists():
                script.unlink()

if __name__ == "__main__":
    unittest.main()
