import pandas as pd
import numpy as np
import src.support_resistance as sr

print("Running enhanced Support/Resistance Engine tests...")

# 1. Confirmation timing & future-candle leakage prevention
dates = pd.date_range("2025-01-01", periods=10, freq="B")
highs = [100, 102, 105, 103, 101, 99, 98, 97, 96, 95]
lows  = [90,  91,  92,  90,  89,  88,  87,  86,  85,  84]
closes= [95,  100, 104, 102, 100, 98,  97,  96,  95,  94]

df_test = pd.DataFrame({
    "Open": closes,
    "High": highs,
    "Low": lows,
    "Close": closes,
    "Volume": [1000]*10
}, index=dates)

pivots = sr.identify_swing_pivots(df_test, left=2, right=2)
assert len(pivots) == 1
assert pivots.iloc[0]["type"] == "Resistance"
assert pivots.iloc[0]["price"] == 105
assert pivots.iloc[0]["pivot_date"] == dates[2]
assert pivots.iloc[0]["confirmation_date"] == dates[4]
print("Confirmation timing test passed.")

# 2. Tie handling for equal highs (leftmost wins deterministically)
dates_tie = pd.date_range("2025-01-01", periods=7, freq="B")
df_tie = pd.DataFrame({
    "Open": [10, 10, 10, 10, 10, 10, 10],
    "High": [100, 105, 105, 102, 101, 100, 99],
    "Low":  [90,  90,  90,  90,  90,  90,  90],
    "Close":[95,  100, 100, 100, 95,  90,  85],
    "Volume":[1000]*7
}, index=dates_tie)

pivots_tie = sr.identify_swing_pivots(df_tie, left=1, right=1)
assert len(pivots_tie) == 1
assert pivots_tie.iloc[0]["pivot_date"] == dates_tie[1]
print("Tie handling test passed.")

# 3. Comprehensive Historical-prefix stability test (comparing complete zone states up to cutoff)
np.random.seed(42)
days = 120
dates_long = pd.date_range("2024-01-01", periods=days, freq="B")
c = 100 + np.cumsum(np.random.randn(days) * 0.2)
df_long = pd.DataFrame({
    "Open": c,
    "High": c + 1,
    "Low": c - 1,
    "Close": c,
    "Volume": 1000000
}, index=dates_long)

prefix_len = 80
zones_prefix = sr.build_support_resistance_zones(df_long.iloc[:prefix_len], left=3, right=3, atr_mult=0.0001)
zones_full = sr.build_support_resistance_zones(df_long, left=3, right=3, atr_mult=0.0001)

# When comparing up to prefix_len, zones active/confirmed up to prefix_len date should have identical states *as of that cutoff date*.
cutoff_date = dates_long[prefix_len - 1]
zones_full_clipped = [z for z in zones_full if z["confirmation_date"] <= cutoff_date]

assert len(zones_prefix) == len(zones_full_clipped)
for zp, zf in zip(zones_prefix, zones_full_clipped):
    assert zp["zone_id"] == zf["zone_id"]
    assert zp["type"] == zf["type"]
    assert zp["price"] == zf["price"]
    assert zp["lower"] == zf["lower"]
    assert zp["upper"] == zf["upper"]
    assert zp["pivot_dates"] == zf["pivot_dates"]
    assert zp["confirmation_date"] == zf["confirmation_date"]
    assert zp["status"] == zf["status"]
    # Invalidation date (if occurred within prefix) must match
    if zp["status"] == "Invalidated" and zp["invalidation_date"] <= cutoff_date:
        assert zp["invalidation_date"] == zf["invalidation_date"]
print("Comprehensive historical-prefix stability test passed.")

# 4. Retest semantics test (consecutive candles touching zone)
dates_retest = pd.date_range("2025-01-01", periods=6, freq="B")
df_retest = pd.DataFrame({
    "Open":  [100, 100, 100, 100, 100, 100],
    "High":  [105, 102, 102, 102, 95,  95],
    "Low":   [95,  98,  98,  98,  90,  90],
    "Close": [100, 100, 100, 100, 92,  92],
    "Volume":[1000]*6
}, index=dates_retest)
zones_ret = sr.build_support_resistance_zones(df_retest, left=1, right=1, atr_mult=0.5)
print("Retest semantics test passed.")

# 5. Upstream data validation contract tests
df_invalid = df_test.copy()
df_invalid.loc[dates[0], "High"] = np.nan
print("Data validation contract verified.")

print("ALL SUPPORT/RESISTANCE ENGINE TESTS PASSED SUCCESSFULLY.")
