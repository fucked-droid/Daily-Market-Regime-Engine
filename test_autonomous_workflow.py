import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from agent_helper import run_python_script, classify_error, autonomous_debug_loop

class TestAutonomousWorkflow(unittest.TestCase):
    def test_classify_error(self):
        self.assertEqual(classify_error("ModuleNotFoundError: No module named 'foo'"), "ImportError")
        self.assertEqual(classify_error("SyntaxError: invalid syntax"), "SyntaxError")
        self.assertEqual(classify_error("ValueError: invalid literal"), "RuntimeValueError")
        self.assertEqual(classify_error("FileNotFoundError: [Errno 2] No such file"), "FileNotFoundError")

    def test_autonomous_debug_loop_success(self):
        script = Path("test_debug_success.py")
        script.write_text("print('DEBUG SUCCESS')\n", encoding="utf-8")
        try:
            res = autonomous_debug_loop(script)
            self.assertEqual(res["status"], "PASS")
            self.assertEqual(res["attempts"], 1)
        finally:
            if script.exists():
                script.unlink()

    def test_autonomous_debug_loop_failure(self):
        script = Path("test_debug_fail.py")
        script.write_text("raise ValueError('Intentional error')\n", encoding="utf-8")
        try:
            res = autonomous_debug_loop(script)
            self.assertEqual(res["status"], "FAIL_NEEDS_PATCH")
            self.assertEqual(res["result"]["error_category"], "RuntimeValueError")
        finally:
            if script.exists():
                script.unlink()

if __name__ == "__main__":
    unittest.main()
