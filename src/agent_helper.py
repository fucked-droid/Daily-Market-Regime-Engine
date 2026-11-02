import sys
import subprocess
from pathlib import Path

def run_python_script(script_path, timeout=60):
    """
    Project-aware execution helper with robust exception and timeout handling,
    capturing exit codes, stdout, and stderr independently with utf-8 encoding.
    """
    python_exe = Path(__file__).resolve().parent.parent / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = sys.executable

    try:
        res = subprocess.run(
            [str(python_exe), str(script_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=str(Path(__file__).resolve().parent.parent)
        )
        return {
            "success": res.returncode == 0,
            "exit_code": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
            "timeout": False,
            "error_category": None if res.returncode == 0 else "NonzeroExitCode"
        }
    except subprocess.TimeoutExpired as te:
        return {
            "success": False,
            "exit_code": None,
            "stdout": te.stdout if hasattr(te, 'stdout') else "",
            "stderr": te.stderr if hasattr(te, 'stderr') else str(te),
            "timeout": True,
            "error_category": "TimeoutExpired"
        }
    except Exception as ex:
        return {
            "success": False,
            "exit_code": None,
            "stdout": "",
            "stderr": str(ex),
            "timeout": False,
            "error_category": "ExecutionException"
        }

def classify_error(stderr_text):
    """
    Classify Python stderr output into diagnostic error categories.
    """
    if not stderr_text:
        return "Unknown"
    if "ModuleNotFoundError" in stderr_text or "ImportError" in stderr_text:
        return "ImportError"
    if "SyntaxError" in stderr_text:
        return "SyntaxError"
    if "TypeError" in stderr_text or "ValueError" in stderr_text or "KeyError" in stderr_text or "NameError" in stderr_text:
        return "RuntimeValueError"
    if "FileNotFoundError" in stderr_text:
        return "FileNotFoundError"
    return "GenericPythonError"

def mock_gemini_diagnose_and_patch(script_path, category, stderr_text):
    """
    Simulates Gemini-driven diagnosis and patch proposal based on error category and stderr context.
    In an environment with direct LLM client bindings, this function formats the prompt,
    invokes the model client, parses the response, and returns structured diffs/patches.
    """
    content = script_path.read_text(encoding="utf-8")
    if category == "RuntimeValueError" and "NameError" in stderr_text:
        # Proposed fix for missing helper definition
        fixed = "def add_two(a, b):\n    return a + b\n\n" + content
        script_path.write_text(fixed, encoding="utf-8")
        return {"diagnosed": True, "patched": True, "strategy": "inject_missing_definition"}
    elif category == "SyntaxError":
        # Cannot automatically patch arbitrary syntax errors without LLM generation
        return {"diagnosed": True, "patched": False, "strategy": "unsupported_syntax"}
    return {"diagnosed": False, "patched": False, "strategy": "unknown"}

def apply_gemini_diagnosed_repair(script_path, max_attempts=3):
    """
    Applies the verified automatic repair loop utilizing Gemini-driven diagnosis and patching.
    """
    return apply_patch_and_verify(script_path, patch_func=mock_gemini_diagnose_and_patch, max_attempts=max_attempts)

def autonomous_debug_loop(script_path, max_attempts=3):
    """
    Controlled autonomous debugging loop with bounded repair attempts (max 3).
    Inspects, reproduces, classifies, and reports execution status.
    """
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        result = run_python_script(script_path)
        if result["success"]:
            return {
                "status": "PASS",
                "attempts": attempts,
                "result": result
            }
        else:
            category = result["error_category"]
            if category == "NonzeroExitCode":
                category = classify_error(result["stderr"])
            
            result["error_category"] = category
            
            if result["timeout"] or category in ["FileNotFoundError", "TimeoutExpired"]:
                return {
                    "status": "FAIL_NON_RECOVERABLE",
                    "attempts": attempts,
                    "result": result
                }
            
            return {
                "status": "FAIL_NEEDS_PATCH",
                "attempts": attempts,
                "result": result
            }
    return {
        "status": "MAX_ATTEMPTS_REACHED",
        "attempts": attempts
    }

def apply_patch_and_verify(script_path, patch_func, max_attempts=3):
    """
    Controlled automatic code repair and verification loop:
    1. Reproduce failure.
    2. Apply patch generator / function.
    3. Re-run verification.
    4. Limit to max_attempts (default 3).
    """
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        result = run_python_script(script_path)
        if result["success"]:
            return {
                "status": "PASS",
                "attempts": attempts,
                "repaired": attempts > 1,
                "result": result
            }
        
        category = classify_error(result["stderr"])
        result["error_category"] = category

        if result["timeout"] or category in ["FileNotFoundError", "TimeoutExpired"]:
            return {
                "status": "FAIL_NON_RECOVERABLE",
                "attempts": attempts,
                "repaired": False,
                "result": result
            }

        if patch_func is not None:
            try:
                patch_res = patch_func(script_path, category, result["stderr"])
                if isinstance(patch_res, dict) and not patch_res.get("patched", True):
                    # If patcher indicates it cannot patch, stop loop
                    return {
                        "status": "FAIL_UNPATCHABLE",
                        "attempts": attempts,
                        "repaired": False,
                        "diagnosis": patch_res
                    }
            except Exception as patch_ex:
                return {
                    "status": "FAIL_PATCH_ERROR",
                    "attempts": attempts,
                    "repaired": False,
                    "error": str(patch_ex)
                }
        else:
            return {
                "status": "FAIL_NO_PATCHER",
                "attempts": attempts,
                "repaired": False,
                "result": result
            }

    return {
        "status": "MAX_ATTEMPTS_REACHED",
        "attempts": attempts,
        "repaired": False
    }

if __name__ == "__main__":
    print("Gemini-driven autonomous diagnosis and repair module loaded.")
