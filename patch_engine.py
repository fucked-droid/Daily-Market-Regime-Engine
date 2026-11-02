import src.engine as e
import pandas as pd
import numpy as np
import math

ALL_REGIMES = ["Bearish", "Bullish", "Mixed", "Strong_Bearish", "Strong_Bullish"]

def calculate_probability_calibration(backtest_results):
    \"\"\"
    Evaluate probability calibration from walk-forward backtest results using proper one-vs-rest multiclass calibration.
    For EACH of the five regimes independently:
    1. For every valid walk-forward prediction, extract that regime's predicted probability on the 0-100 scale.
    2. Create a binary outcome:
       1 = actual next regime equals this regime
       0 = actual next regime is another regime.
    3. Bin ALL predictions for that regime into:
       0-10%, 10-20%, 20-30%, 30-40%, 40-50%, 50-60%, 60-70%, 70-80%, 80-90%, 90-100%.
    4. For every bin calculate:
       - count
       - mean predicted probability
       - observed frequency
       - calibration error = mean predicted probability - observed frequency
    5. Also calculate overall multiclass Brier score using the complete five-class probability vector and one-hot actual outcome.
    6. Calculate Brier score by current regime.
    7. Calculate Brier score by reliability.
    8. For each regime, calculate a simple overall calibration summary:
       - total observations
       - positive outcome count
       - mean predicted probability
       - observed frequency
       - mean absolute calibration error across populated bins
    \"\"\"
    if backtest_results is None or not isinstance(backtest_results, pd.DataFrame) or backtest_results.empty:
        return {
            \"overall_brier_score\": np.nan,
            \"brier_by_current_regime\": {},
            \"brier_by_reliability\": {},
            \"probability_bins_by_regime\": {},
            \"calibration_summary_by_regime\": pd.DataFrame(),
            \"total_evaluated\": 0,
            \"total_unique_predictions\": 0,
            \"total_regime_calibration_observations\": 0,
            \"excluded_observations\": [],
        }

    brier_scores = []
    valid_rows = 0
    excluded_rows = []

    valid_predictions_list = []

    for idx, row in backtest_results.iterrows():
        probs = row.get(\"probabilities\")
        actual = row.get(\"actual_next_regime\")

        if probs is None or pd.isna(actual) or not isinstance(probs, (pd.Series, dict)) or len(probs) == 0:
            excluded_rows.append({\"index\": idx, \"reason\": \"empty_or_missing_probabilities\"})
            continue

        if isinstance(probs, pd.Series):
            p_series = probs.copy()
        else:
            p_series = pd.Series(probs)

        # Multiclass Brier score vector (0-1 scale)
        full_p = pd.Series(0.0, index=ALL_REGIMES)
        for cat in p_series.index:
            if cat in full_p.index:
                full_p[cat] = float(p_series[cat])
        
        p_sum = full_p.sum()
        if p_sum > 0:
            full_p = full_p / p_sum
        else:
            full_p[:] = 1.0 / len(ALL_REGIMES)

        one_hot = pd.Series(0.0, index=ALL_REGIMES)
        if actual in one_hot.index:
            one_hot[actual] = 1.0

        brier_row = np.sum((full_p - one_hot) ** 2)
        brier_scores.append(brier_row)

        valid_predictions_list.append({
            \"prediction_date\": row.get(\"prediction_date\"),
            \"current_regime\": row.get(\"current_regime\"),
            \"reliability\": row.get(\"reliability\"),
            \"actual_next_regime\": actual,
            \"probabilities\": p_series,
            \"correct\": row.get(\"correct\"),
        })

        valid_rows += 1

    valid_df = pd.DataFrame(valid_predictions_list)
    overall_brier = float(np.mean(brier_scores)) if len(brier_scores) > 0 else np.nan

    # Brier score by current regime
    brier_by_current_regime = {}
    for reg, group in valid_df.groupby(\"current_regime\"):\n        sub_briers = []\n        for _, row in group.iterrows():\n            p_series = row[\"probabilities\"]\n            actual = row[\"actual_next_regime\"]\n            full_p = pd.Series(0.0, index=ALL_REGIMES)\n            for cat in p_series.index:\n                if cat in full_p.index:\n                    full_p[cat] = float(p_series[cat])\n            p_sum = full_p.sum()\n            if p_sum > 0:\n                full_p = full_p / p_sum\n            one_hot = pd.Series(0.0, index=ALL_REGIMES)\n            if actual in one_hot.index:\n                one_hot[actual] = 1.0\n            sub_briers.append(np.sum((full_p - one_hot) ** 2))\n        brier_by_current_regime[reg] = float(np.mean(sub_briers)) if len(sub_briers) > 0 else np.nan\n\n    # Brier score by reliability\n    brier_by_reliability = {}\n    for rel, group in valid_df.groupby(\"reliability\"):\n        sub_briers = []\n        for _, row in group.iterrows():\n            p_series = row[\"probabilities\"]\n            actual = row[\"actual_next_regime\"]\n            full_p = pd.Series(0.0, index=ALL_REGIMES)\n            for cat in p_series.index:\n                if cat in full_p.index:\n                    full_p[cat] = float(p_series[cat])\n            p_sum = full_p.sum()\n            if p_sum > 0:\n                full_p = full_p / p_sum\n            one_hot = pd.Series(0.0, index=ALL_REGIMES)\n            if actual in one_hot.index:\n                one_hot[actual] = 1.0\n            sub_briers.append(np.sum((full_p - one_hot) ** 2))\n        brier_by_reliability[rel] = float(np.mean(sub_briers)) if len(sub_briers) > 0 else np.nan\n\n    probability_bins_by_regime = {}\n    summary_records = []\n\n    bin_edges = [(i * 10, (i + 1) * 10) for i in range(10)]\n\n    for reg in ALL_REGIMES:\n        if valid_df.empty:\n            reg_preds = np.array([])\n            reg_binary = np.array([])\n        else:\n            reg_preds = valid_df[\"probabilities\"].map(lambda p: float(p.get(reg, 0.0))).to_numpy()\n            reg_binary = (valid_df[\"actual_next_regime\"] == reg).astype(float).to_numpy()\n\n        # Bin index for each prediction\n        bin_indices = []\n        for p in reg_preds:\n            if p >= 100.0:\n                bin_indices.append(9)\n            else:\n                bin_indices.append(min(int(p // 10), 9))\n        bin_indices = np.array(bin_indices)\n\n        bins_data = []\n        abs_errors = []\n\n        for i, (low, high) in enumerate(bin_edges):\n            mask = (bin_indices == i)\n            count = int(mask.sum())\n            if count > 0:\n                sub_preds = reg_preds[mask]\n                sub_binary = reg_binary[mask]\n                avg_pred = float(sub_preds.mean())\n                obs_freq = float(sub_binary.mean() * 100.0)\n                cal_error = avg_pred - obs_freq\n                abs_errors.append(abs(cal_error))\n            else:\n                avg_pred = 0.0\n                obs_freq = 0.0\n                cal_error = 0.0\n\n            bins_data.append({\n                \"bin_range\": f\"{low}-{high}%\",\n                \"observation_count\": count,\n                \"average_predicted_probability\": avg_pred,\n                \"observed_frequency\": obs_freq,\n                \"calibration_error\": cal_error,\n            })\n\n        bins_df = pd.DataFrame(bins_data)\n        probability_bins_by_regime[reg] = bins_df\n\n        total_obs = len(reg_preds)\n        pos_count = int(reg_binary.sum()) if total_obs > 0 else 0\n        mean_pred_prob = float(reg_preds.mean()) if total_obs > 0 else 0.0\n        obs_freq_overall = (pos_count / total_obs * 100.0) if total_obs > 0 else 0.0\n        mean_abs_cal_error = float(np.mean(abs_errors)) if len(abs_errors) > 0 else 0.0\n\n        summary_records.append({\n            \"regime\": reg,\n            \"total_observations\": total_obs,\n            \"positive_outcomes\": pos_count,\n            \"mean_predicted_probability\": mean_pred_prob,\n            \"observed_frequency\": obs_freq_overall,\n            \"mean_absolute_calibration_error\": mean_abs_cal_error,\n        })\n\n    calibration_summary_by_regime = pd.DataFrame(summary_records).set_index(\"regime\")\n\n    total_regime_obs = sum(bins_df[\"observation_count\"].sum() for bins_df in probability_bins_by_regime.values())\n\n    return {\n        \"overall_brier_score\": overall_brier,\n        \"brier_by_current_regime\": brier_by_current_regime,\n        \"brier_by_reliability\": brier_by_reliability,\n        \"probability_bins_by_regime\": probability_bins_by_regime,\n        \"calibration_summary_by_regime\": calibration_summary_by_regime,\n        \"total_evaluated\": valid_rows,\n        \"total_unique_predictions\": valid_rows,\n        \"total_regime_calibration_observations\": total_regime_obs,\n        \"excluded_observations\": excluded_rows,\n    }\n\ne.ALL_REGIMES = ALL_REGIMES\ne.calculate_probability_calibration = calculate_probability_calibration\nprint(\"Engine patched successfully with corrected one-vs-rest calibration methodology.\")\n