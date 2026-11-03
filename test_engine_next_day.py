import src.engine as e
import pandas as pd
import numpy as np

# 1. Normal / actual sample test from existing engine / dataset
df = e.load_nifty_master()
df = e.build_core_engine(df)
df = e.add_regime_layer(df)

# Regression test against baseline calibration cutoff (2026-10-01)
df_benchmark = df.loc[:"2026-10-01"] if "2026-10-01" in df.index else df
res = e.calculate_next_day_regime(df_benchmark)
assert res["current_regime"] == "Bearish"
assert res["sample_size"] == 22
assert res["reliability"] == "Low"
assert res["most_likely_regime"] == "Strong_Bearish"
assert "confidence_intervals" in res
assert isinstance(res["confidence_intervals"], dict)

# Test execution on live full dataset
live_res = e.calculate_next_day_regime(df)
assert live_res["current_regime"] is not None
assert live_res["sample_size"] > 0
assert isinstance(live_res["probabilities"], pd.Series)
print("Normal sample test passed.")

# 2. Zero observations test
df_zero = pd.DataFrame(columns=["Market_Regime"])
res_zero = e.calculate_next_day_regime(df_zero)
assert res_zero["sample_size"] == 0
assert res_zero["confidence_intervals"] == {}
print("Zero observations test passed.")

# 3. 0% and 100% probability / Wilson interval edge cases
ci_zero = e.calculate_wilson_interval(0, 50, confidence=0.95)
assert ci_zero[0] == 0.0
assert ci_zero[1] >= 0.0

ci_full = e.calculate_wilson_interval(50, 50, confidence=0.95)
assert ci_full[0] <= 100.0
assert ci_full[1] == 100.0
print("Wilson edge case tests passed.")

# 4. Small sample test
res_small = e.calculate_wilson_interval(5, 10, confidence=0.95)
assert len(res_small) == 2
assert 0.0 <= res_small[0] <= res_small[1] <= 100.0
print("Small sample test passed.")

# 5. Walk-forward backtest tests
dates = pd.date_range("2025-01-01", periods=10, freq="B")
synthetic_regimes = ["Bullish", "Bullish", "Bearish", "Bullish", "Mixed", "Bullish", "Bullish", "Bearish", "Strong_Bearish", "Bullish"]
df_syn = pd.DataFrame({"Market_Regime": synthetic_regimes}, index=dates)

results_syn, summary_syn = e.backtest_next_day_regime_estimator(df_syn, min_history=3)
assert isinstance(results_syn, pd.DataFrame)
assert summary_syn["total_predictions"] > 0
print("Synthetic walk-forward backtest test passed.")

# 6. Synthetic test for calibration_by_regime
syn_rows = [
    {"prediction_date": pd.Timestamp("2025-01-02"), "current_regime": "Bullish", "actual_next_regime": "Bullish",
     "probabilities": {"Strong_Bearish": 80.0, "Bearish": 5.0, "Mixed": 5.0, "Bullish": 5.0, "Strong_Bullish": 5.0}, "reliability": "Good", "correct": False, "actual_next_probability": 5.0},
    {"prediction_date": pd.Timestamp("2025-01-03"), "current_regime": "Bullish", "actual_next_regime": "Strong_Bearish",
     "probabilities": {"Strong_Bearish": 70.0, "Bearish": 10.0, "Mixed": 10.0, "Bullish": 5.0, "Strong_Bullish": 5.0}, "reliability": "Good", "correct": False, "actual_next_probability": 70.0},
]
syn_df = pd.DataFrame(syn_rows)
syn_cal = e.calculate_probability_calibration(syn_df)

assert "calibration_by_regime" in syn_cal
sb_summary = syn_cal["calibration_by_regime"]["Strong_Bearish"]
assert sb_summary["observation_count"] == 2, f"Expected 2 observations for Strong_Bearish, got {sb_summary['observation_count']}"
assert sb_summary["positive_outcomes"] == 1, f"Expected 1 positive outcome for Strong_Bearish, got {sb_summary['positive_outcomes']}"
print("Synthetic calibration_by_regime test passed.")

# ==========================================
# REGRESSION CASES FOR AUD-01 FIX
# ==========================================

# Case A: Mixed valid and missing destinations (8 valid, 2 missing)
# We construct a sequence where current regime "Bullish" appears with valid and NaN next states.
mixed_regimes = ["Bullish", "Bearish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish"]
# Introduce NaN at specific positions
mixed_df = pd.DataFrame({"Market_Regime": mixed_regimes}, index=pd.date_range("2025-01-01", periods=len(mixed_regimes), freq="B"))
# Manually inject NaN into regime at index positions corresponding to next states of Bullish
# Let's use a controlled series where we know exact transitions
reg_list = ["Bullish", "Bearish"] * 6 + ["Bullish", "Strong_Bullish"]
# Better yet, construct a dataframe and set specific values to NaN
test_dates = pd.date_range("2025-01-01", periods=15, freq="B")
test_regimes = ["Bullish", "Bearish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish", "Bullish", "Bearish", "Strong_Bearish", "Bullish"]
df_mix = pd.DataFrame({"Market_Regime": test_regimes}, index=test_dates)
# Let's inspect backtest results or call calculate_next_day_regime on a sliced df where we set some next states to NaN
# We can test backtest_next_day_regime_estimator with a dataframe containing NaN in Market_Regime
df_nan_mix = pd.DataFrame({
    "Market_Regime": [
        "Bullish", "Bearish",     # t=0, 1
        "Bullish", np.nan,        # 2, 3 (next is NaN)
        "Bullish", "Bearish",     # 4, 5
        "Bullish", np.nan,        # 6, 7 (next is NaN)
        "Bullish", "Bearish",     # 8, 9
        "Bullish", "Bearish",     # 10, 11
        "Bullish", "Bearish",     # 12, 13
        "Bullish", "Bearish",     # 14, 15
        "Bullish", "Bearish",     # 16, 17
        "Bullish", "Bearish",     # 18, 19
        "Bullish", "Bearish",     # 20, 21
        "Bullish", "Bearish",     # 22, 23
        "Bullish", "Bearish",     # 24, 25
        "Bullish", "Bearish",     # 26, 27
        "Bullish", "Bearish",     # 28, 29
        "Bullish", "Bearish",     # 30, 31 (prediction evaluated here)
    ]
}, index=pd.date_range("2025-01-01", periods=32, freq="B"))

res_mix, sum_mix = e.backtest_next_day_regime_estimator(df_nan_mix, min_history=2)
# Check that probabilities sum to 100% within tolerance for valid predictions
for _, row in res_mix.iterrows():
    probs = row["probabilities"]
    if len(probs) > 0:
        prob_sum = probs.sum()
        assert abs(prob_sum - 100.0) < 1e-5, f"Probabilities sum to {prob_sum}, expected 100.0"
print("Mixed valid and missing destinations regression test passed.")

# Case B: All destinations missing for matching current regime
df_all_nan = pd.DataFrame({
    "Market_Regime": [
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
        "Bullish", np.nan,
    ]
}, index=pd.date_range("2025-01-01", periods=32, freq="B"))

res_all_nan, sum_all_nan = e.backtest_next_day_regime_estimator(df_all_nan, min_history=2)
for _, row in res_all_nan.iterrows():
    assert row["sample_size"] == 0
    assert len(row["probabilities"]) == 0
print("All destinations missing regression test passed.")

# Case C: No matching transitions
df_no_match = pd.DataFrame({
    "Market_Regime": [
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Strong_Bullish", "Bearish",
        "Bullish", "Bearish", # current at t=30 is Bullish, but no historical Bullish transitions
    ]
}, index=pd.date_range("2025-01-01", periods=32, freq="B"))

res_nomatch, sum_nomatch = e.backtest_next_day_regime_estimator(df_no_match, min_history=30)
if len(res_nomatch) > 0:
    row_last = res_nomatch.iloc[-1]
    assert row_last["sample_size"] == 0
print("No matching transitions regression test passed.")

print("ALL TESTS PASSED SUCCESSFULLY.")
