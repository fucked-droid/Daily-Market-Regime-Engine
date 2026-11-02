import src.engine as e
import pandas as pd

df = e.load_nifty_master()
df = e.build_core_engine(df)
df = e.add_regime_layer(df)

results_df, summary = e.backtest_next_day_regime_estimator(df, min_history=30)
cal = e.calculate_probability_calibration(results_df)

print("=== PROBABILITY CALIBRATION EVALUATION (FULL HISTORICAL WALK-FORWARD) ===")
print(f"Total evaluated predictions: {cal['total_evaluated']}")
print(f"Overall Multiclass Brier Score: {cal['overall_brier_score']:.4f}")

print("\n--- 1. Overall Calibration by Probability Bins ---")
print(cal["probability_bins"].to_string(index=False))

print("\n--- 2. Multiclass Brier Score by Current Regime ---")
for reg, brier in cal["brier_by_current_regime"].items():
    print(f"  - {reg}: Brier Score = {brier:.4f}")

print("\n--- 3. Calibration by Current Regime ---")
for reg, stats in cal["calibration_by_current_regime"].items():
    print(f"  - {reg}: Count = {stats['prediction_count']}, Mean Prob(Actual) = {stats['mean_predicted_probability_for_actual']:.2f}%, Observed Hit Rate = {stats['observed_hit_rate']:.2f}%, Brier = {stats['brier_score']:.4f}")

print("\n--- 4. Calibration by Reliability Category ---")
for rel, stats in cal["calibration_by_reliability"].items():
    print(f"  - {rel}: Count = {stats['prediction_count']}, Mean Prob(Actual) = {stats['mean_predicted_probability_for_actual']:.2f}%, Observed Freq = {stats['observed_frequency']:.2f}%, Brier = {stats['brier_score']:.4f}")
