import src.engine as e
import pandas as pd

df = e.load_nifty_master()
df = e.build_core_engine(df)
df = e.add_regime_layer(df)

results_df, summary = e.backtest_next_day_regime_estimator(df, min_history=30)
cal = e.calculate_probability_calibration(results_df)

print(f"total_evaluated = {cal['total_evaluated']}")
total_bin_obs = cal['probability_bins']['observation_count'].sum()
print(f"total probability-bin observations = {total_bin_obs}")
print("calibration_by_regime observation_count for all five regimes:")
for reg in e.ALL_REGIMES:
    cnt = cal['calibration_by_regime'][reg]['observation_count']
    print(f"  - {reg} = {cnt}")
