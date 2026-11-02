import src.engine as e
import pandas as pd

df = e.load_nifty_master()
df = e.build_core_engine(df)
df = e.add_regime_layer(df)

results_df, summary = e.backtest_next_day_regime_estimator(df, min_history=30)

print("=== BACKTEST SUMMARY ===")
print("1. Total predictions:", summary["total_predictions"])
print("2. Correct predictions:", summary["correct_predictions"])
print(f"3. Overall accuracy: {summary['overall_accuracy']:.2f}%")
print(f"4. Average probability assigned to the actual next regime: {summary['average_actual_next_probability']:.2f}%")

print("\n--- Accuracy and Prediction Count by Current Regime ---")
acc_reg = summary["accuracy_by_current_regime"]
cnt_reg = summary["prediction_count_by_current_regime"]
for reg in ["Bearish", "Strong_Bearish", "Mixed", "Bullish", "Strong_Bullish"]:
    print(f"  - {reg}: Count = {cnt_reg.get(reg, 0)}, Accuracy = {acc_reg.get(reg, 0.0):.2f}%")

print("\n--- Accuracy and Prediction Count by Reliability ---")
acc_rel = summary["accuracy_by_reliability"]
cnt_rel = summary["prediction_count_by_reliability"]
for rel in ["Low", "Moderate", "Good", "Strong"]:
    print(f"  - {rel}: Count = {cnt_rel.get(rel, 0)}, Accuracy = {acc_rel.get(rel, 0.0):.2f}%")

# Number of historical predictions where:
# - current regime was Bearish
# - estimator predicted Strong_Bearish
# - actual next regime was Strong_Bearish
subset = results_df[
    (results_df["current_regime"] == "Bearish") &
    (results_df["predicted_regime"] == "Strong_Bearish") &
    (results_df["actual_next_regime"] == "Strong_Bearish")
]
print(f"\n--- Specific Bearish Condition Count ---")
print(f"Count of predictions where current=Bearish, predicted=Strong_Bearish, actual=Strong_Bearish: {len(subset)}")
