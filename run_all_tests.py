import subprocess
import sys

test_files = ['test_import.py', 'test_run.py', 'test_list_src.py', 'test_engine_next_day.py']
for tf in test_files:
    print(f"--- Running {tf} ---")
    result = subprocess.run([sys.executable, tf], capture_output=True, text=True)
    print("Exit code:", result.returncode)
    print("STDOUT:\n", result.stdout)
    print("STDERR:\n", result.stderr)
