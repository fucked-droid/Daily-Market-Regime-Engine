import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import src.engine as eng

if __name__ == "__main__":
    df = eng.load_nifty_master()
    df = eng.build_core_engine(df)
    df = eng.add_regime_layer(df)
    results_df, summary = eng.backtest_next_day_regime_estimator(df)
    calib = eng.calculate_probability_calibration(results_df)
    brier = calib.get("overall_brier_score")
    count = calib.get("total_evaluated")
    expected = 0.3665744839001818
    print(f"Brier score: {brier}")
    print(f"Observation count: {count}")
    print(f"Match expected baseline: {brier == expected}")
