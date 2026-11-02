import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from agent_helper import run_python_script, classify_error, apply_patch_and_verify

class TestAutonomousRepair(unittest.TestCase):
    def test_successful_repair_cycle(self):
        script = Path("test_repair_target.py")
        # Initially missing a definition causing NameError
        script.write_text("result = add_two(2, 3)\nprint(result)\n", encoding="utf-8")

        def simple_patcher(path, category, stderr):
            content = path.read_text(encoding="utf-8")
            if "NameError" in stderr or category == "RuntimeValueError":
                # Apply fix by adding definition at top
                fixed = "def add_two(a, b):\n    return a + b\n\n" + content
                path.write_text(fixed, encoding="utf-8")

        try:
            res = apply_patch_and_verify(script, patch_func=simple_patcher)
            self.assertEqual(res["status"], "PASS")
            self.assertTrue(res["repaired"])
            self.assertGreaterEqual(res["attempts"], 2)
        finally:
            if script.exists():
                script.unlink()

    def test_failed_repair_bounded(self):
        script = Path("test_unfixable.py")
        script.write_text("raise SyntaxError('Unfixable syntax')\n", encoding="utf-8")

        def bad_patcher(path, category, stderr):
            # Does nothing to fix the error
            pass

        try:
            res = apply_patch_and_verify(script, patch_func=bad_patcher, max_attempts=2)
            self.assertEqual(res["status"], "MAX_ATTEMPTS_REACHED")
            self.assertEqual(res["attempts"], 2)
            self.assertFalse(res["repaired"])
        finally:
            if script.exists():
                script.unlink()

if __name__ == "__main__":
    unittest.main()
