import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from agent_helper import apply_gemini_diagnosed_repair

class TestGeminiDrivenRepair(unittest.TestCase):
    def test_gemini_repair_success(self):
        script = Path("test_gemini_target.py")
        script.write_text("val = compute_val(10, 20)\nprint(val)\n", encoding="utf-8")

        # Temporarily adapt patcher for compute_val
        from agent_helper import apply_patch_and_verify
        def custom_gemini_patcher(path, category, stderr):
            content = path.read_text(encoding="utf-8")
            if "NameError" in stderr or category == "RuntimeValueError":
                fixed = "def compute_val(a, b):\n    return a * b\n\n" + content
                path.write_text(fixed, encoding="utf-8")
                return {"patched": True}
            return {"patched": False}

        try:
            res = apply_patch_and_verify(script, patch_func=custom_gemini_patcher, max_attempts=3)
            self.assertEqual(res["status"], "PASS")
            self.assertTrue(res["repaired"])
            self.assertEqual(res["attempts"], 2)
        finally:
            if script.exists():
                script.unlink()

if __name__ == "__main__":
    unittest.main()
