import pandas as pd
import numpy as np
import src.engine as e
import src.report as r
import src.support_resistance as sr

print("Running integration tests...")

# 1. Verify existing regime labels and next-day probabilities remain unchanged when S/R feature is enabled
df = e.load_nifty_master()
df_core = e.build_core_engine(df)
df_regime = e.add_regime_layer(df_core)
next_day_before = e.calculate_next_day_regime(df_regime)

report_output = r.generate_daily_regime_report(df)
assert "support_resistance_zones" in report_output
next_day_after = report_output["next_day_info"]

assert next_day_before["current_regime"] == next_day_after["current_regime"]
assert next_day_before["sample_size"] == next_day_after["sample_size"]
pd.testing.assert_series_equal(next_day_before["probabilities"], next_day_after["probabilities"])
print("Regime invariance integration test passed.")

# 2. Verify future candles cannot change support/resistance output at a historical cutoff
np.random.seed(42)
days = 150
dates_long = pd.date_range("2024-01-01", periods=days, freq="B")
c = 100 + np.cumsum(np.random.randn(days) * 0.2)
df_long = pd.DataFrame({
    "Open": c,
    "High": c + 1,
    "Low": c - 1,
    "Close": c,
    "Volume": 1000000
}, index=dates_long)

cutoff_idx = 100
df_prefix = df_long.iloc[:cutoff_idx].copy()

zones_prefix = sr.build_support_resistance_zones(df_prefix, atr_mult=0.0001)
zones_full = sr.build_support_resistance_zones(df_long, atr_mult=0.0001)
cutoff_date = dates_long[cutoff_idx - 1]
zones_full_clipped = [z for z in zones_full if z["confirmation_date"] <= cutoff_date]

assert len(zones_prefix) == len(zones_full_clipped)
for zp, zf in zip(zones_prefix, zones_full_clipped):
    assert zp["price"] == zf["price"]
    assert zp["confirmation_date"] == zf["confirmation_date"]
    assert zp["pivot_dates"] == zf["pivot_dates"]
print("Historical cutoff leakage prevention integration test passed.")

# 3. Test insufficient history and invalid input handling
df_short = df_long.iloc[:2]
zones_short = sr.build_support_resistance_zones(df_short)
assert len(zones_short) == 0
print("Insufficient history test passed.")

print("ALL INTEGRATION TESTS PASSED SUCCESSFULLY.")
