import sys
import json
import shutil
import tempfile
import subprocess
import difflib
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gemini_rest import call_gemini_rest_api


PROTECTED_FILES = {
    "engine.py",
    "agent_helper.py",
    "gemini_rest.py",
    "live_repair.py",
    "universe.py",
    "volatility.py",
    "multi_timeframe.py",
    "support_resistance.py",
    "report.py",
    "verify_accounting.py",
    "run_calibration_report.py",
    "run_full_calibration_tables.py",
    "verify_final_calibration.py",
    "patch_engine.py",
    "run_backtest_report.py",
}


def _failure(error, diagnosed=False, proposal=None):
    result = {
        "diagnosed": diagnosed,
        "patched": False,
        "error": str(error),
        "production_modified": False,
    }
    if proposal is not None:
        result["proposal"] = proposal
    return result


def _parse_json_response(ai_text):
    if not isinstance(ai_text, str) or not ai_text.strip():
        raise ValueError("Gemini returned an empty response")

    text = re.sub(
        r"^\s*```(?:json)?\s*|\s*```\s*$",
        "",
        ai_text.strip(),
        flags=re.IGNORECASE,
    ).strip()

    decoder = json.JSONDecoder()
    result = None

    for match in re.finditer(r"\{", text):
        try:
            candidate, _ = decoder.raw_decode(text[match.start():])
            if isinstance(candidate, dict):
                result = candidate
                break
        except json.JSONDecodeError:
            continue

    if result is None:
        raise ValueError("Gemini response does not contain valid JSON")

    required = {"diagnosis", "target", "diff", "rationale"}
    if not required.issubset(result):
        raise ValueError(f"Missing JSON keys: {required - result.keys()}")

    if not all(isinstance(result[key], str) for key in required):
        raise ValueError("All required JSON fields must be strings")

    if not result["diff"].strip():
        raise ValueError("Gemini returned an empty patch")

    return result


def _apply_patch(original, patch_text):
    patch_text = patch_text.strip()

    if patch_text.startswith("FULL_REPLACEMENT:\n"):
        replacement = patch_text.split("\n", 1)[1]
        if not replacement.strip():
            raise ValueError("Replacement is empty")
        return replacement + "\n"

    if not re.search(r"(?m)^@@\s+-\d+", patch_text):
        raise ValueError(
            "Patch must be a unified diff with @@ headers or a "
            "FULL_REPLACEMENT: block"
        )

    diff_lines = [
        line for line in patch_text.splitlines(keepends=True)
        if not line.startswith(("--- ", "+++ "))
    ]
    original_lines = original.splitlines(keepends=True)
    output = []
    source_index = 0

    for line in diff_lines:
        if line.startswith("@@"):
            match = re.match(
                r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@",
                line,
            )
            if not match:
                raise ValueError("Invalid unified diff header")

            target_index = int(match.group(1)) - 1
            if target_index < source_index:
                raise ValueError("Diff hunks are out of order")

            output.extend(original_lines[source_index:target_index])
            source_index = target_index
            continue

        if line.startswith("\\ No newline"):
            continue

        if line.startswith((" ", "-")):
            if source_index >= len(original_lines):
                raise ValueError("Diff exceeds original file")

            expected = line[1:].rstrip("\r\n")
            actual = original_lines[source_index].rstrip("\r\n")

            if actual != expected:
                raise ValueError(
                    f"Diff does not match original at line {source_index + 1}"
                )

            if line.startswith(" "):
                output.append(original_lines[source_index])

            source_index += 1

        elif line.startswith("+"):
            output.append(line[1:])

        else:
            raise ValueError(f"Unsupported diff line: {line!r}")

    output.extend(original_lines[source_index:])
    return "".join(output)


def live_gemini_diagnose_and_patch(
    script_path,
    category,
    stderr_text,
    model_name="gemini-2.5-flash",
    timeout=30,
):
    project_root = Path(__file__).resolve().parent.parent.resolve()

    try:
        supplied = Path(script_path)

        if ".." in supplied.parts:
            return _failure("Path traversal is not allowed")

        target = supplied.resolve()
        target.relative_to(project_root)

        if not target.is_file():
            return _failure("Target does not exist or is not a file")

        if target.name in PROTECTED_FILES:
            return _failure(f"Protected file: {target.name}")

        original = target.read_text(encoding="utf-8")

    except (OSError, ValueError, TypeError) as exc:
        return _failure(f"Target validation failed: {exc}")

    prompt = f"""
Return ONLY a JSON object with string fields:
diagnosis, target, diff, rationale.

The diff must be a standard unified diff with @@ hunk headers,
or a complete Python file prefixed with FULL_REPLACEMENT:
on its own line.

Do not invent unrelated changes. Preserve existing behavior.
The original file will not be modified automatically.

Target: {target.name}
Error category: {category}
Traceback:
{stderr_text}

Original source:
{original[:12000]}
""".strip()

    try:
        api = call_gemini_rest_api(
            prompt,
            model_name=model_name,
            timeout=timeout,
        )

        if not api.get("success"):
            return _failure(
                f"Gemini API failed: {api.get('error', 'Unknown error')}"
            )

        proposal = _parse_json_response(api.get("text", ""))

    except Exception as exc:
        return _failure(f"Gemini response failed: {exc}")

    proposed = Path(proposal["target"].replace("\\", "/"))

    if (
        proposed.is_absolute()
        or ".." in proposed.parts
        or proposed.name != target.name
    ):
        return _failure(
            "Gemini proposed an invalid target",
            diagnosed=True,
            proposal=proposal,
        )

    try:
        candidate = _apply_patch(original, proposal["diff"])

        with tempfile.TemporaryDirectory(prefix="gemini_repair_") as temp:
            sandbox = Path(temp) / target.name
            sandbox.write_text(candidate, encoding="utf-8")

            python_exe = (
                project_root / ".venv" / "Scripts" / "python.exe"
            )
            if not python_exe.is_file():
                python_exe = Path(sys.executable)

            check = subprocess.run(
                [str(python_exe), "-I", "-m", "py_compile", str(sandbox)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                cwd=temp,
            )

            if check.returncode != 0:
                return _failure(
                    f"Syntax validation failed: {check.stderr}",
                    diagnosed=True,
                    proposal=proposal,
                )

        return {
            "diagnosed": True,
            "patched": True,
            "strategy": "live_gemini_validated_proposal",
            "proposal": proposal,
            "production_modified": False,
            "validation": "Python syntax compilation passed",
        }

    except Exception as exc:
        return _failure(
            f"Patch validation failed: {exc}",
            diagnosed=True,
            proposal=proposal,
        )


def apply_live_gemini_diagnosed_repair(script_path, max_attempts=3):
    result = live_gemini_diagnose_and_patch(
        script_path,
        "PythonError",
        "Diagnose the current Python file and propose a repair.",
    )
    result["attempts"] = 1
    result["repaired"] = False
    return result


if __name__ == "__main__":
    print("Live Gemini secure repair module loaded.")
