import pandas as pd
import numpy as np
import src.engine as e
import src.report as r
import src.support_resistance as sr

print("Running corrected integration & report tests...")

# 1. Test active zones and invalidated zones explicitly using synthetic data
dates_zone = pd.date_range("2024-01-01", periods=30, freq="B")
highs = [100]*30
highs[5] = 110 # Resistance pivot
lows = [90]*30
closes = [100]*30
closes[15] = 112 # Invalidation close above resistance zone at index 15

df_synth = pd.DataFrame({
    "Open": closes,
    "High": highs,
    "Low": lows,
    "Close": closes,
    "Volume": [1000]*30
}, index=dates_zone)

# Report at index 11 (after confirmation on Jan 11, before invalidation on Jan 22)
rep_active = r.generate_daily_regime_report(df_synth.iloc[:11])
assert len(rep_active["support_resistance_zones"]) == 1, "Expected 1 active confirmed zone"
assert rep_active["support_resistance_zones"][0]["status"] == "Active"

# Report at index 20 (after invalidation close at index 15)
rep_invalidated = r.generate_daily_regime_report(df_synth.iloc[:20])
# The zone should be invalidated, so active confirmed zones list should be empty
assert len(rep_invalidated["support_resistance_zones"]) == 0, "Expected 0 active zones after invalidation"
print("Active and invalidated zones filtering tests passed.")

# 2. Run existing integration and test suites
import subprocess
import sys

res1 = subprocess.run([sys.executable, "test_integration.py"], capture_output=True, text=True)
print(res1.stdout)
assert res1.returncode == 0

res2 = subprocess.run([sys.executable, "test_support_resistance.py"], capture_output=True, text=True)
print(res2.stdout)
assert res2.returncode == 0

print("ALL CORRECTED TESTS PASSED SUCCESSFULLY.")
