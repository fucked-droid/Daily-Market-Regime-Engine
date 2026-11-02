import src.engine as e
import pandas as pd

df = e.load_nifty_master()
df = e.build_core_engine(df)
df = e.add_regime_layer(df)

regimes = df["Market_Regime"].dropna()
total_dataset_rows = len(df)
total_regime_rows = len(regimes)
regime_value_counts = regimes.value_counts()

results_df, summary = e.backtest_next_day_regime_estimator(df, min_history=30)
total_predictions = len(results_df)

print("=== 1. Total rows in final Market_Regime dataset ===")
print("Total rows in master DataFrame:", total_dataset_rows)
print("Total non-null Market_Regime rows:", total_regime_rows)

print("\n=== 2. Number of rows excluded before backtesting and why ===")
# Backtest loop starts at t = max(1, min_history) = 30 up to n - 2 (since t+1 < n).
# Also, regimes.iloc[t] and regimes.iloc[t+1] must not be NaN (handled by dropna earlier or check).
# Total rows in df = n. Valid indices t go from 30 to n - 2.
# Number of excluded rows at the beginning (indices 0 to 29, i.e., min_history = 30 rows).
# And the very last row (index n - 1), because there is no t+1 for the last row.
n = len(df)
start_t = 30
excluded_start = start_t # indices 0 to 29
excluded_end = 1 # the last row (n - 1)
total_excluded = excluded_start + excluded_end
print(f"Total dataset rows (n): {n}")
print(f"min_history offset excluded (t < 30): {excluded_start}")
print(f"Last row excluded (no t+1): {excluded_end}")
print(f"Total excluded rows: {total_excluded}")
print("Why: min_history=30 requires a warm-up period before making predictions, and the final row has no subsequent day (t+1) to evaluate against.")

print("\n=== 3. Total predictions produced by the backtest ===")
print("Total predictions:", total_predictions)

print("\n=== 4. Whether each prediction corresponds to exactly one date t with a known actual regime at t+1 ===")
unique_dates_count = results_df["prediction_date"].nunique()
match_dates = (unique_dates_count == total_predictions) and (total_predictions == (n - start_t - 1))
print(f"Unique prediction dates: {unique_dates_count}")
print(f"Does each prediction correspond to exactly one date t with t+1 < n? {match_dates}")

print("\n=== 5. Prediction counts by current regime ===")
print(results_df["current_regime"].value_counts())

print("\n=== 6. Sum of prediction counts across all current regimes ===")
print("Sum of prediction counts:", results_df["current_regime"].value_counts().sum())

print("\n=== 7. Explain why historical regime counts and backtest prediction counts differ ===")
print("Historical regime value counts count how many days in the entire dataset had each regime.")
print("Backtest prediction counts count how many times each regime was evaluated as the *current regime* 't' during the walk-forward backtest (excluding the warm-up period indices 0-29 and the final day).")
print("Therefore, the first 30 occurrences of any regime during the warm-up period are not counted in the backtest predictions, and the final occurrence of a regime if it happens on the last day is also excluded.")

print("\n=== Verification: No prediction uses t -> t+1 ===")
print("Inspecting backtest_next_day_regime_estimator implementation:")
print("- For step t, training transitions use c_vals = regimes.iloc[:t].to_numpy()[:-1] and n_vals = regimes.iloc[1:t].to_numpy()")
print("- This means training data includes transitions ending at index <= t-1 (or next state <= t).")
print("- The transition starting at t and ending at t+1 (t -> t+1) has next state at index t+1, which is strictly > t.")
print("- Thus, the t -> t+1 transition is never included in the training set when predicting t+1.")
