import src.engine as e
import pandas as pd
import numpy as np

df = e.load_nifty_master()
df = e.build_core_engine(df)
df = e.add_regime_layer(df)
results_df, summary = e.backtest_next_day_regime_estimator(df, min_history=30)
cal = e.calculate_probability_calibration(results_df)

print("A. Overall multiclass Brier score:", cal["overall_brier_score"])
print("\\nB. Brier score by current regime:")
for reg, brier in cal["brier_by_current_regime"].items():
    print(f"  - {reg}: {brier}")

print("\\nC. Brier score by reliability:")
for rel, brier in cal["brier_by_reliability"].items():
    print(f"  - {rel}: {brier}")

print("\\nD. For each of the five regimes, complete calibration table:")
for reg, table in cal["regime_calibration_tables"].items():
    print(f"\\n--- Regime: {reg} ---")
    print(table.to_string(index=False))

print("\\nE. Regime summary statistics:")
for reg, stats in cal["regime_calibration"].items():
    print(f"  - {reg}:")
    print(f"      observation count: {stats['observation_count']}")
    print(f"      positive outcome count: {stats['positive_outcome_count']}")
    print(f"      mean predicted probability: {stats['mean_predicted_probability']:.4f}%")
    print(f"      observed frequency: {stats['observed_frequency']:.4f}%")
    print(f"      mean absolute calibration error: {stats['mean_absolute_calibration_error']:.4f}%")

print(f"\\nTotal unique predictions: {cal['total_unique_predictions']}")
print(f"Total regime-level observations: {cal['total_regime_calibration_observations']}")
