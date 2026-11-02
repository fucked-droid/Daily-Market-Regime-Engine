import src.engine as e
import pandas as pd

df = e.load_nifty_master()
df = e.build_core_engine(df)
df = e.add_regime_layer(df)

results_df, summary = e.backtest_next_day_regime_estimator(df, min_history=30)
cal = e.calculate_probability_calibration(results_df)

print("=== COMPLETE PROBABILITY-BIN CALIBRATION TABLE (OVERALL) ===")
bins_df = cal["probability_bins"]
print(bins_df.to_string(index=False))

# To generate calibration table separately by current regime and reliability,
# let's write a helper function or inspect forecast_df from results_df.
# Since calculate_probability_calibration currently returns overall bins, let's also compute/print bin tables by regime and reliability.

all_categories = ["Strong_Bullish", "Bullish", "Mixed", "Bearish", "Strong_Bearish"]

def get_bins_for_subset(subset_results):
    all_recs = []
    for _, row in subset_results.iterrows():
        probs = row.get("probabilities")
        actual = row.get("actual_next_regime")
        if probs is None or pd.isna(actual) or len(probs) == 0:
            continue
        p_series = pd.Series(probs)
        p_sum = p_series.sum()
        if p_sum > 0:
            p_series = p_series / p_sum
        for cat, p_val in p_series.items():
            p_pct = float(p_val)
            occurred = 1.0 if cat == actual else 0.0
            all_recs.append({
                "predicted_prob_pct": p_pct,
                "occurred": occurred,
            })
    f_df = pd.DataFrame(all_recs)
    if f_df.empty:
        return pd.DataFrame()

    b_data = []
    bin_edges = [(i * 10, (i + 1) * 10) for i in range(10)]
    for low, high in bin_edges:
        if low == 0:
            sub = f_df[(f_df["predicted_prob_pct"] >= low) & (f_df["predicted_prob_pct"] <= high)]
        else:
            sub = f_df[(f_df["predicted_prob_pct"] > low) & (f_df["predicted_prob_pct"] <= high)]
        count = len(sub)
        avg_pred = float(sub["predicted_prob_pct"].mean()) if count > 0 else 0.0
        obs_freq = float(sub["occurred"].mean() * 100.0) if count > 0 else 0.0
        cal_error = avg_pred - obs_freq if count > 0 else 0.0
        b_data.append({
            "bin": f"{low}-{high}%",
            "observation_count": count,
            "mean_predicted_probability": avg_pred,
            "observed_frequency": obs_freq,
            "calibration_error": cal_error,
        })
    return pd.DataFrame(b_data)

print("\n=== CALIBRATION BY CURRENT REGIME ===")
for reg in ["Bearish", "Strong_Bearish", "Mixed", "Bullish", "Strong_Bullish"]:
    sub_res = results_df[results_df["current_regime"] == reg]
    print(f"\n--- Current Regime: {reg} (n={len(sub_res)}) ---")
    reg_bins = get_bins_for_subset(sub_res)
    print(reg_bins.to_string(index=False) if not reg_bins.empty else "No data")

print("\n=== CALIBRATION BY RELIABILITY ===")
for rel in ["Low", "Moderate", "Good", "Strong"]:
    sub_res = results_df[results_df["reliability"] == rel]
    print(f"\n--- Reliability: {rel} (n={len(sub_res)}) ---")
    rel_bins = get_bins_for_subset(sub_res)
    print(rel_bins.to_string(index=False) if not rel_bins.empty else "No data")
