
from pathlib import Path
import subprocess
import pandas as pd
import numpy as np
import math

from .volatility import add_volatility_layer



# ===========================================================
# CONFIGURATION
# ============================================================

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"

MASTER_PARQUET = DATA_DIR / "nifty_df_master.parquet"
MASTER_CSV = DATA_DIR / "nifty_df_master.csv"

MASTER_URL = (
    "https://raw.githubusercontent.com/"
    "fucked-droid/"
    "Daily-Market-Regime-Engine/"
    "main/data/nifty_df_master.parquet"
)

ALL_REGIMES = ["Bearish", "Bullish", "Mixed", "Strong_Bearish", "Strong_Bullish"]


# ===========================================================
# LOAD MASTER DATA
# ============================================================

def load_nifty_master():
    """
    Load the latest NIFTY master dataframe from GitHub.
    """

    df = pd.read_parquet(MASTER_URL)

    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    return df


# ===========================================================
# VALIDATE MASTER DATA
# ============================================================

def validate_nifty_df(df):
    """
    Validate the master dataframe before saving.
    """

    if not isinstance(df, pd.DataFrame):
        raise TypeError("nifty_df must be a pandas DataFrame")

    if df.empty:
        raise ValueError("nifty_df is empty")

    if df.index.duplicated().any():
        raise ValueError("Duplicate dates found in nifty_df")

    required_base = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume"
    ]

    missing = [
        col for col in required_base
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing base columns: {missing}"
        )

    # Detect accidental Ellipsis values.
    for column in df.columns:
        if df[column].dtype == "object":
            if df[column].map(
                lambda x: x is Ellipsis
            ).any():
                raise ValueError(
                    f"Ellipsis value found in column: {column}"
                )

    return True


# ===========================================================
# TREND LAYER
# ============================================================

def add_trend_layer(df):
    df = df.copy()

    df["EMA20"] = df["Close"].ewm(
        span=20,
        adjust=False,
        min_periods=20
    ).mean()

    df["EMA50"] = df["Close"].ewm(
        span=50,
        adjust=False,
        min_periods=50
    ).mean()

    df["EMA200"] = df["Close"].ewm(
        span=200,
        adjust=False,
        min_periods=200
    ).mean()

    df["Price_vs_EMA20"] = np.where(
        df["Close"] > df["EMA20"],
        1,
        -1
    )

    df["EMA20_vs_EMA50"] = np.where(
        df["EMA20"] > df["EMA50"],
        1,
        -1
    )

    df["EMA50_vs_EMA200"] = np.where(
        df["EMA50"] > df["EMA200"],
        1,
        -1
    )

    df["Trend_Score"] = (
        df["Price_vs_EMA20"]
        + df["EMA20_vs_EMA50"]
        + df["EMA50_vs_EMA200"]
    )

    return df


# ===========================================================
# MOMENTUM LAYER
# ============================================================

def add_momentum_layer(df):
    df = df.copy()

    delta = df["Close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / 14,
        adjust=False,
        min_periods=14
    ).mean()

    rs = avg_gain / avg_loss

    df["RSI_14"] = 100 - (
        100 / (1 + rs)
    )

    df["Momentum_Score"] = np.select(
        [
            df["RSI_14"] >= 60,
            df["RSI_14"] <= 40
        ],
        [
            1,
            -1
        ],
        default=0
    )

    return df


# ===========================================================
# STRUCTURE LAYER
# ============================================================

def add_structure_layer(
    df,
    lookback=20
):
    df = df.copy()

    df["High_20D"] = (
        df["High"]
        .rolling(
            lookback,
            min_periods=lookback
        )
        .max()
    )

    df["Low_20D"] = (
        df["Low"]
        .rolling(
            lookback,
            min_periods=lookback
        )
        .min()
    )

    df["Distance_From_20D_High_Pct"] = (
        (df["Close"] / df["High_20D"]) - 1
    ) * 100

    df["Distance_From_20D_Low_Pct"] = (
        (df["Close"] / df["Low_20D"]) - 1
    ) * 100

    df["Condition_Score"] = np.select(
        [
            df["Distance_From_20D_High_Pct"] >= -3,
            df["Distance_From_20D_High_Pct"] < -7
        ],
        [
            1,
            -1
        ],
        default=0
    )

    return df


# ===========================================================
# PARTICIPATION LAYER
# ============================================================

def add_participation_layer(
    df,
    lookback=20,
    high_threshold=1.5
):
    df = df.copy()

    df["Volume_MA20"] = (
        df["Volume"]
        .rolling(
            lookback,
            min_periods=lookback
        )
        .mean()
    )

    df["Volume_Ratio"] = (
        df["Volume"] /
        df["Volume_MA20"]
    )

    df["High_Participation"] = np.where(
        df["Volume_Ratio"] > high_threshold,
        1,
        0
    )

    return df


# ===========================================================
# APPLY CORE LAYERS
# ============================================================

def build_core_engine(df):
    """
    Rebuild the core market-analysis layers from OHLCV data.
    """

    df = df.copy()

    df = add_trend_layer(df)
    df = add_momentum_layer(df)
    df = add_structure_layer(df)
    df = add_participation_layer(df)
    df = add_volatility_layer(df)

    return df



# ===========================================================
# BACKUP
# ============================================================

def backup_nifty_df(
    df,
    commit_message="Update NIFTY master dataframe"
):
    """
    Validate, save, commit and push the master dataframe.
    """

    validate_nifty_df(df)

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    df.to_parquet(
        MASTER_PARQUET,
        index=True
    )

    df.to_csv(
        MASTER_CSV,
        index=True
    )

    subprocess.run(
        [
            "git",
            "-C",
            str(REPO_DIR),
            "add",
            "data/nifty_df_master.parquet",
            "data/nifty_df_master.csv"
        ],
        check=True
    )

    status = subprocess.run(
        [
            "git",
            "-C",
            str(REPO_DIR),
            "status",
            "--porcelain"
        ],
        capture_output=True,
        text=True,
        check=True
    )

    if not status.stdout.strip():
        print("No data changes detected.")
        return True

    subprocess.run(
        [
            "git",
            "-C",
            str(REPO_DIR),
            "commit",
            "-m",
            commit_message
        ],
        check=True
    )

    subprocess.run(
        [
            "git",
            "-C",
            str(REPO_DIR),
            "push",
            "origin",
            "main"
        ],
        check=True
    )

    print("=" * 60)
    print("NIFTY MASTER BACKUP SUCCESSFUL")
    print("=" * 60)

    return True


# ===========================================================
# ONLINE VERIFICATION
# ============================================================

def verify_online_backup():
    """
    Download the public master file and verify it.
    """

    online_df = pd.read_parquet(
        MASTER_URL
    )

    validate_nifty_df(
        online_df
    )

    print("=" * 60)
    print("ONLINE BACKUP VERIFIED")
    print("=" * 60)
    print("Rows:", len(online_df))
    print("Columns:", len(online_df.columns))
    print("Latest:", online_df.index.max())

    return online_df


# ===========================================================
# BREADTH LAYER
# ============================================================

def calculate_breadth(
    close_data
):
    """
    Calculate historical breadth from constituent closing prices.

    Parameters
    ----------
    close_data : pandas.DataFrame
        Columns = individual constituent symbols
        Index   = trading dates

    Returns
    -------
    pandas.DataFrame
        Historical breadth measurements.
    """

    close_data = close_data.copy()

    # --------------------------------------------
    # Daily returns
    # --------------------------------------------

    daily_returns = close_data.pct_change()

    # --------------------------------------------
    # Advances / declines
    # --------------------------------------------

    advances = (
        daily_returns > 0
    ).sum(axis=1)

    declines = (
        daily_returns < 0
    ).sum(axis=1)

    unchanged = (
        daily_returns == 0
    ).sum(axis=1)

    breadth = pd.DataFrame(
        index=close_data.index
    )

    breadth["Advances"] = advances
    breadth["Declines"] = declines
    breadth["Unchanged"] = unchanged

    breadth["Net_Advances"] = (
        advances - declines
    )

    # --------------------------------------------
    # Advance / Decline ratio
    # --------------------------------------------

    breadth["AD_Ratio"] = np.where(
        declines > 0,
        advances / declines,
        np.nan
    )

    # --------------------------------------------
    # EMA20 breadth
    # --------------------------------------------

    ema20 = close_data.ewm(
        span=20,
        adjust=False,
        min_periods=20
    ).mean()

    above_ema20 = (
        close_data > ema20
    )

    valid_stocks = (
        close_data.notna().sum(axis=1)
    )

    breadth["Stocks_Above_EMA20"] = (
        above_ema20.sum(axis=1)
    )

    breadth["Stocks_Above_EMA20_Pct"] = (
        breadth["Stocks_Above_EMA20"]
        / valid_stocks
    ) * 100

    # --------------------------------------------
    # EMA200 breadth
    # --------------------------------------------

    ema200 = close_data.ewm(
        span=200,
        adjust=False,
        min_periods=200
    ).mean()

    above_ema200 = (
        close_data > ema200
    )

    breadth["Stocks_Above_EMA200"] = (
        above_ema200.sum(axis=1)
    )

    breadth["Stocks_Above_EMA200_Pct"] = (
        breadth["Stocks_Above_EMA200"]
        / valid_stocks
    ) * 100

    return breadth


def add_breadth_layer(
    nifty_df,
    breadth_df
):
    """
    Merge historical breadth measurements
    into the NIFTY master dataframe.
    """

    nifty_df = nifty_df.copy()
    breadth_df = breadth_df.copy()

    nifty_df.index = pd.to_datetime(
        nifty_df.index
    )

    breadth_df.index = pd.to_datetime(
        breadth_df.index
    )

    breadth_columns = [
        "Advances",
        "Declines",
        "Unchanged",
        "Net_Advances",
        "AD_Ratio",
        "Stocks_Above_EMA20",
        "Stocks_Above_EMA20_Pct",
        "Stocks_Above_EMA200",
        "Stocks_Above_EMA200_Pct"
    ]

    missing = [
        col
        for col in breadth_columns
        if col not in breadth_df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing breadth columns: {missing}"
        )

    # Remove existing versions so rerunning
    # the function does not create duplicates.
    existing = [
        col
        for col in breadth_columns
        if col in nifty_df.columns
    ]

    if existing:
        nifty_df = nifty_df.drop(
            columns=existing
        )

    nifty_df = nifty_df.join(
        breadth_df[breadth_columns],
        how="left"
    )

    return nifty_df


# ===========================================================
# MARKET REGIME LAYER
# ===========================================================

def add_regime_layer(df):
    """
    Combine the existing trend, momentum, structure and
    participation layers into descriptive market states.

    This layer does NOT generate buy/sell signals.
    """

    df = df.copy()

    # --------------------------------------------------------
    # Trend state
    # --------------------------------------------------------

    df["Trend_State"] = np.select(
        [
            df["Trend_Score"] >= 2,
            df["Trend_Score"] <= -2
        ],
        [
            "Bullish",
            "Bearish"
        ],
        default="Neutral"
    )

    # --------------------------------------------------------
    # Momentum state
    # --------------------------------------------------------

    df["Momentum_State"] = np.select(
        [
            df["RSI_14"] >= 60,
            df["RSI_14"] <= 40
        ],
        [
            "Positive",
            "Negative"
        ],
        default="Neutral"
    )

    # --------------------------------------------------------
    # Structure state
    # --------------------------------------------------------

    df["Structure_State"] = np.select(
        [
            df["Condition_Score"] > 0,
            df["Condition_Score"] < 0
        ],
        [
            "Strong",
            "Weak"
        ],
        default="Neutral"
    )

    # --------------------------------------------------------
    # Participation state
    # --------------------------------------------------------

    df["Participation_State"] = np.select(
        [
            df["High_Participation"] == 1,
            df["Volume_Ratio"] < 0.75
        ],
        [
            "High",
            "Low"
        ],
        default="Normal"
    )

    # --------------------------------------------------------
    # Numeric regime score
    # --------------------------------------------------------

    trend_component = np.sign(
        df["Trend_Score"]
    )

    momentum_component = np.sign(
        df["Momentum_Score"]
    )

    structure_component = np.sign(
        df["Condition_Score"]
    )

    participation_component = np.where(
        df["High_Participation"] == 1,
        1,
        0
    )

    df["Regime_Score"] = (
        trend_component
        + momentum_component
        + structure_component
        + participation_component
    )

    # --------------------------------------------------------
    # Descriptive regime
    # --------------------------------------------------------

    df["Market_Regime"] = np.select(
        [
            df["Regime_Score"] >= 3,
            df["Regime_Score"] <= -2,
            (
                (df["Regime_Score"] >= 1)
                &
                (df["Momentum_Score"] >= 0)
            ),
            (
                (df["Regime_Score"] <= -1)
                &
                (df["Momentum_Score"] < 0)
            )
        ],
        [
            "Strong_Bullish",
            "Strong_Bearish",
            "Bullish",
            "Bearish"
        ],
        default="Mixed"
    )

    return df


# ===========================================================
# REGIME TRANSITION ANALYSIS
# ===========================================================

def calculate_regime_transitions(df):
    """
    Calculate regime-to-regime transitions.

    Returns
    ------
    transition_matrix : pandas.DataFrame
        Counts of transitions from current regime to next regime.

    transition_probability : pandas.DataFrame
        Row-normalized transition probabilities.
    """

    regimes = df["Market_Regime"].dropna()

    current_regime = regimes.iloc[:-1].to_numpy()
    next_regime = regimes.iloc[1:].to_numpy()

    transition_matrix = pd.crosstab(
        pd.Series(
            current_regime,
            name="From"
        ),
        pd.Series(
            next_regime,
            name="To"
        )
    )

    transition_probability = (
        transition_matrix
        .div(
            transition_matrix.sum(axis=1),
            axis=0
        )
        * 100
    )

    return (
        transition_matrix,
        transition_probability
    )


def calculate_regime_duration(df):
    """
    Calculate consecutive duration of each regime.
    """

    regimes = (
        df["Market_Regime"]
        .dropna()
        .copy()
    )

    group_id = (
        regimes != regimes.shift()
    ).cumsum()

    runs = pd.DataFrame({
        "Market_Regime": regimes,
        "Run_ID": group_id
    })

    durations = (
        runs
        .groupby(
            ["Run_ID", "Market_Regime"]
        )
        .size()
        .reset_index(
            name="Duration_Days"
        )
    )

    duration_summary = (
        durations
        .groupby("Market_Regime")[
            "Duration_Days"
        ]
        .agg(
            [
                "count",
                "mean",
                "median",
                "min",
                "max"
            ]
        )
    )

    return durations, duration_summary

def calculate_wilson_interval(successes, total, confidence=0.95):
    """
    Calculate the Wilson Score Interval for a binomial proportion.
    Returns (lower_bound, upper_bound) as percentages (0-100 scale).
    """
    if total <= 0 or successes < 0 or successes > total:
        return (0.0, 0.0)

    alpha = 1.0 - confidence
    try:
        z = math.sqrt(2.0) * math.erfinv(1.0 - alpha)
    except Exception:
        z = 1.959963984540054

    p = successes / total

    denominator = 1.0 + (z**2) / total
    center = (p + (z**2) / (2.0 * total)) / denominator
    margin = (z / denominator) * math.sqrt((p * (1.0 - p) / total) + ((z**2) / (4.0 * (total**2))))

    lower = max(0.0, (center - margin) * 100.0)
    upper = min(100.0, (center + margin) * 100.0)

    return (lower, upper)


def calculate_next_day_regime(df):
    """
    Estimate the historical next-day regime distribution
    for the latest available market regime.
    """

    regimes = df["Market_Regime"].dropna()

    if len(regimes) < 2:
        return {
            "current_regime": None,
            "sample_size": 0,
            "reliability": classify_regime_reliability(0),
            "probabilities": pd.Series(dtype=float),
            "most_likely_regime": None,
            "confidence_intervals": {},
        }

    current_regime = regimes.iloc[-1]

    current_values = regimes.iloc[:-1].to_numpy()
    next_values = regimes.iloc[1:].to_numpy()

    transition_data = pd.DataFrame({
        "Current": current_values,
        "Next": next_values,
    })

    matching = transition_data[
        transition_data["Current"] == current_regime
    ]

    sample_size = len(matching)
    reliability = classify_regime_reliability(sample_size)

    if sample_size == 0:
        return {
            "current_regime": current_regime,
            "sample_size": 0,
            "reliability": reliability,
            "probabilities": pd.Series(dtype=float),
            "most_likely_regime": None,
            "confidence_intervals": {},
        }

    counts = matching["Next"].value_counts()
    probabilities = (
        counts
        .div(sample_size)
        .mul(100)
        .sort_values(ascending=False)
    )

    confidence_intervals = {}
    for reg, count in counts.items():
        confidence_intervals[reg] = calculate_wilson_interval(count, sample_size, confidence=0.95)

    most_likely_regime = probabilities.index[0]

    return {
        "current_regime": current_regime,
        "sample_size": sample_size,
        "reliability": reliability,
        "probabilities": probabilities,
        "most_likely_regime": most_likely_regime,
        "confidence_intervals": confidence_intervals,
    }


def classify_regime_reliability(sample_size):
    """
    Classify the reliability of a next-day regime estimate
    based on the number of historical transitions available.
    """

    if sample_size < 30:
        return "Low"

    if sample_size < 100:
        return "Moderate"

    if sample_size < 300:
        return "Good"

    return "Strong"


# ===========================================================
# WALK-FORWARD BACKTEST OF NEXT-DAY REGIME ESTIMATOR
# ===========================================================

def backtest_next_day_regime_estimator(df, min_history=30):
    """
    Perform a walk-forward backtest of the next-day regime estimator
    without look-ahead bias.

    For each date t index from min_history onwards:
    - Current regime available at t is df.iloc[t]["Market_Regime\"].
    - Actual next regime is df.iloc[t+1]["Market_Regime\"].
    - Training transitions available at t include ONLY transitions
      whose next regime is known by date t (i.e. transitions ending at or before t,
      meaning transitions from index 0 up to t-1).
    - Excludes the transition ending at t+1 (t -> t+1).
    """
    df = df.copy()
    regimes = df["Market_Regime"]

    n = len(df)
    results = []

    start_t = max(1, min_history)
    for t in range(start_t, n - 1):
        current_regime = regimes.iloc[t]
        actual_next_regime = regimes.iloc[t+1]

        if pd.isna(current_regime) or pd.isna(actual_next_regime):
            continue

        if t < 1:
            continue

        # Training transitions: all pairs (regimes.iloc[k], regimes.iloc[k+1])
        # where the next state is known by date t (i.e. k+1 <= t).
        # This means k ranges from 0 up to t-1, so next states are indices 1 up to t.
        # Thus, transitions ending at or before t use data from index 0 to t.
        if t >= 2:
            c_vals = regimes.iloc[:t].to_numpy()[:-1]
            n_vals = regimes.iloc[1:t].to_numpy()
            trans_df = pd.DataFrame({"Current": c_vals, "Next": n_vals})
        else:
            trans_df = pd.DataFrame(columns=["Current", "Next"])

        matching = trans_df[trans_df["Current"] == current_regime]
        valid_matching = matching.dropna(subset=["Next"])
        sample_size = len(valid_matching)
        reliability = classify_regime_reliability(sample_size)

        if sample_size == 0:
            probabilities = pd.Series(dtype=float)
            predicted_regime = None
            predicted_probability = 0.0
            actual_next_probability = 0.0
            correct = False
        else:
            counts = valid_matching["Next"].value_counts()
            probabilities = counts.div(sample_size).mul(100).sort_values(ascending=False)
            predicted_regime = probabilities.index[0]
            predicted_probability = probabilities.iloc[0]
            actual_next_probability = probabilities.get(actual_next_regime, 0.0)
            correct = (predicted_regime == actual_next_regime)

        prediction_date = df.index[t]

        results.append({
            "prediction_date": prediction_date,
            "current_regime": current_regime,
            "predicted_regime": predicted_regime,
            "actual_next_regime": actual_next_regime,
            "predicted_probability": predicted_probability,
            "actual_next_probability": actual_next_probability,
            "probabilities": probabilities,
            "sample_size": sample_size,
            "reliability": reliability,
            "correct": correct,
        })

    results_df = pd.DataFrame(results)

    total_predictions = len(results_df)
    if total_predictions == 0:
        summary = {
            "total_predictions": 0,
            "correct_predictions": 0,
            "overall_accuracy": 0.0,
            "average_actual_next_probability": 0.0,
            "accuracy_by_current_regime": {},
            "prediction_count_by_current_regime": {},
            "accuracy_by_reliability": {},
            "prediction_count_by_reliability": {},
            "results_df": results_df,
        }
        return results_df, summary

    correct_predictions = int(results_df["correct"].sum())
    overall_accuracy = (correct_predictions / total_predictions) * 100.0
    average_actual_next_probability = float(results_df["actual_next_probability"].mean())

    accuracy_by_current_regime = {}
    prediction_count_by_current_regime = {}
    for reg, group in results_df.groupby("current_regime"):
        count = len(group)
        corr = int(group["correct"].sum())
        acc = (corr / count) * 100.0 if count > 0 else 0.0
        accuracy_by_current_regime[reg] = acc
        prediction_count_by_current_regime[reg] = count

    accuracy_by_reliability = {}
    prediction_count_by_reliability = {}
    for rel, group in results_df.groupby("reliability"):
        count = len(group)
        corr = int(group["correct"].sum())
        acc = (corr / count) * 100.0 if count > 0 else 0.0
        accuracy_by_reliability[rel] = acc
        prediction_count_by_reliability[rel] = count

    summary = {
        "total_predictions": total_predictions,
        "correct_predictions": correct_predictions,
        "overall_accuracy": overall_accuracy,
        "average_actual_next_probability": average_actual_next_probability,
        "accuracy_by_current_regime": accuracy_by_current_regime,
        "prediction_count_by_current_regime": prediction_count_by_current_regime,
        "accuracy_by_reliability": accuracy_by_reliability,
        "prediction_count_by_reliability": prediction_count_by_reliability,
        "results_df": results_df,
    }

    return results_df, summary


# ===========================================================
# PROBABILITY CALIBRATION EVALUATION
# ===========================================================

def calculate_probability_calibration(backtest_results):
    """
    Evaluate probability calibration from walk-forward backtest results using one-vs-rest for all five regimes.
    """
    if backtest_results is None or not isinstance(backtest_results, pd.DataFrame) or backtest_results.empty:
        return {
            "overall_brier_score": np.nan,
            "brier_by_current_regime": {},
            "brier_by_reliability": {},
            "probability_bins": pd.DataFrame(),
            "calibration_by_current_regime": {},
            "calibration_by_reliability": {},
            "calibration_by_regime": {},
            "total_evaluated": 0,
            "excluded_observations": [],
        }

    all_categories = ALL_REGIMES

    brier_scores = []
    bin_records = []

    valid_rows = 0
    excluded_rows = []

    for idx, row in backtest_results.iterrows():
        probs = row.get("probabilities")
        actual = row.get("actual_next_regime")

        if probs is None or pd.isna(actual) or not isinstance(probs, (pd.Series, dict)) or len(probs) == 0:
            excluded_rows.append({"index": idx, "reason": "empty_or_missing_probabilities"})
            continue

        if isinstance(probs, pd.Series):
            p_series = probs.copy()
        else:
            p_series = pd.Series(probs)

        # 1. One-vs-rest calibration observations for ALL five regimes
        for reg in all_categories:
            reg_prob_100 = float(p_series.get(reg, 0.0))
            if reg_prob_100 >= 100.0:
                bin_idx = 9
            else:
                bin_idx = min(int(reg_prob_100 // 10), 9)

            actual_outcome = 1.0 if (actual == reg) else 0.0

            bin_records.append({
                "prediction_date": row.get("prediction_date"),
                "current_regime": row.get("current_regime"),
                "reliability": row.get("reliability"),
                "regime": reg,
                "predicted_probability": reg_prob_100,
                "bin_idx": bin_idx,
                "actual_outcome": actual_outcome,
            })

        # 2. Multiclass Brier score vector (0-1 scale)
        full_p = pd.Series(0.0, index=all_categories)
        for cat in p_series.index:
            if cat in full_p.index:
                full_p[cat] = float(p_series[cat])
        
        p_sum = full_p.sum()
        if p_sum > 0:
            full_p = full_p / p_sum
        else:
            full_p[:] = 1.0 / len(all_categories)

        one_hot = pd.Series(0.0, index=all_categories)
        if actual in one_hot.index:
            one_hot[actual] = 1.0

        brier_row = np.sum((full_p - one_hot) ** 2)
        brier_scores.append(brier_row)

        valid_rows += 1

    bins_df_raw = pd.DataFrame(bin_records)

    # Build 10 bins (0-10%, 10-20%, ..., 90-100%) across all 14,290 observations
    bins_data = []
    bin_edges = [(i * 10, (i + 1) * 10) for i in range(10)]
    
    for i, (low, high) in enumerate(bin_edges):
        if bins_df_raw.empty:
            count, avg_pred, obs_freq, cal_error = 0, 0.0, 0.0, 0.0
        else:
            sub = bins_df_raw[bins_df_raw["bin_idx"] == i]
            count = len(sub)
            avg_pred = float(sub["predicted_probability"].mean()) if count > 0 else 0.0
            obs_freq = float(sub["actual_outcome"].mean() * 100.0) if count > 0 else 0.0
            cal_error = avg_pred - obs_freq if count > 0 else 0.0

        bins_data.append({
            "bin_range": f"{low}-{high}%",
            "observation_count": count,
            "average_predicted_probability": avg_pred,
            "observed_frequency": obs_freq,
            "calibration_error": cal_error,
        })

    bins_df = pd.DataFrame(bins_data)

    overall_brier = float(np.mean(brier_scores)) if len(brier_scores) > 0 else np.nan

    # Calibration by regime (one-vs-rest evaluation for each of the 5 regimes across 2,858 predictions each)
    calibration_by_regime = {}
    for reg in all_categories:
        if bins_df_raw.empty:
            obs_count = 0
            pos_outcomes = 0
            mean_pred = 0.0
            obs_freq = 0.0
            cal_err = 0.0
        else:
            sub_reg = bins_df_raw[bins_df_raw["regime"] == reg]
            obs_count = len(sub_reg)
            pos_outcomes = int(sub_reg["actual_outcome"].sum())
            mean_pred = float(sub_reg["predicted_probability"].mean()) if obs_count > 0 else 0.0
            obs_freq = float(sub_reg["actual_outcome"].mean() * 100.0) if obs_count > 0 else 0.0
            cal_err = mean_pred - obs_freq if obs_count > 0 else 0.0

        # Brier score component for this regime
        reg_briers = []
        for _, row in backtest_results.iterrows():
            probs = row.get("probabilities")
            actual = row.get("actual_next_regime")
            if probs is None or pd.isna(actual) or len(probs) == 0:
                continue
            p_series = pd.Series(probs)
            full_p = pd.Series(0.0, index=all_categories)
            for cat in p_series.index:
                if cat in full_p.index:
                    full_p[cat] = float(p_series[cat])
            p_sum = full_p.sum()
            if p_sum > 0:
                full_p = full_p / p_sum
            else:
                full_p[:] = 1.0 / len(all_categories)
            actual_val = 1.0 if actual == reg else 0.0
            reg_briers.append((full_p[reg] - actual_val) ** 2)

        reg_brier_score = float(np.mean(reg_briers)) if len(reg_briers) > 0 else np.nan

        calibration_by_regime[reg] = {
            "observation_count": obs_count,
            "positive_outcomes": pos_outcomes,
            "mean_predicted_probability": mean_pred,
            "observed_frequency": obs_freq,
            "calibration_error": cal_err,
            "brier_score": reg_brier_score,
        }

    # Brier and calibration by current regime
    brier_by_current_regime = {}
    calibration_by_current_regime = {}
    for reg, group in backtest_results.groupby("current_regime"):
        sub_briers = []
        for _, row in group.iterrows():
            probs = row.get("probabilities")
            actual = row.get("actual_next_regime")
            if probs is None or pd.isna(actual) or len(probs) == 0:
                continue
            p_series = pd.Series(probs)
            full_p = pd.Series(0.0, index=all_categories)
            for cat in p_series.index:
                if cat in full_p.index:
                    full_p[cat] = float(p_series[cat])
            p_sum = full_p.sum()
            if p_sum > 0:
                full_p = full_p / p_sum
            one_hot = pd.Series(0.0, index=all_categories)
            if actual in one_hot.index:
                one_hot[actual] = 1.0
            sub_briers.append(np.sum((full_p - one_hot) ** 2))
        
        brier_by_current_regime[reg] = float(np.mean(sub_briers)) if len(sub_briers) > 0 else np.nan
        
        count = len(group)
        mean_actual_prob = float(group["actual_next_probability"].mean()) if count > 0 else 0.0
        hit_rate = float(group["correct"].mean() * 100.0) if count > 0 else 0.0
        calibration_by_current_regime[reg] = {
            "prediction_count": count,
            "mean_predicted_probability_for_actual": mean_actual_prob,
            "observed_hit_rate": hit_rate,
            "brier_score": brier_by_current_regime.get(reg, np.nan),
        }

    # Brier and calibration by reliability
    brier_by_reliability = {}
    calibration_by_reliability = {}
    for rel, group in backtest_results.groupby("reliability"):
        sub_briers = []
        for _, row in group.iterrows():
            probs = row.get("probabilities")
            actual = row.get("actual_next_regime")
            if probs is None or pd.isna(actual) or len(probs) == 0:
                continue
            p_series = pd.Series(probs)
            full_p = pd.Series(0.0, index=all_categories)
            for cat in p_series.index:
                if cat in full_p.index:
                    full_p[cat] = float(p_series[cat])
            p_sum = full_p.sum()
            if p_sum > 0:
                full_p = full_p / p_sum
            one_hot = pd.Series(0.0, index=all_categories)
            if actual in one_hot.index:
                one_hot[actual] = 1.0
            sub_briers.append(np.sum((full_p - one_hot) ** 2))
        
        brier_by_reliability[rel] = float(np.mean(sub_briers)) if len(sub_briers) > 0 else np.nan
        
        count = len(group)
        mean_actual_prob = float(group["actual_next_probability"].mean()) if count > 0 else 0.0
        hit_rate = float(group["correct"].mean() * 100.0) if count > 0 else 0.0
        calibration_by_reliability[rel] = {
            "prediction_count": count,
            "mean_predicted_probability_for_actual": mean_actual_prob,
            "observed_frequency": hit_rate,
            "brier_score": brier_by_reliability.get(rel, np.nan),
        }

    return {
        "overall_brier_score": overall_brier,
        "brier_by_current_regime": brier_by_current_regime,
        "brier_by_reliability": brier_by_reliability,
        "probability_bins": bins_df,
        "calibration_by_current_regime": calibration_by_current_regime,
        "calibration_by_reliability": calibration_by_reliability,
        "calibration_by_regime": calibration_by_regime,
        "total_evaluated": valid_rows,
        "excluded_observations": excluded_rows,
    }


# ===========================================================
# REGIME QUALITY DIAGNOSTICS
# ===========================================================

def calculate_regime_diagnostics(df):
    """
    Calculate historical performance and risk diagnostics
    for each market regime.
    """

    df = df.copy()

    # Daily NIFTY return
    df["Daily_Return"] = (
        df["Close"].pct_change() * 100
    )

    # 20-day rolling volatility
    df["Volatility_20D"] = (
        df["Daily_Return"]
        .rolling(20)
        .std()
    )

    # Maximum drawdown over the next 20 trading days
    future_drawdowns = []

    closes = df["Close"].to_numpy()

    for i in range(len(df)):

        future = closes[
            i + 1:
            i + 21
        ]

        if len(future) == 0:
            future_drawdowns.append(np.nan)
            continue

        start_price = closes[i]

        drawdown = (
            future / start_price - 1
        ) * 100

        future_drawdowns.append(
            np.min(drawdown)
        )

    df["Forward_Max_Drawdown_20D"] = (
        future_drawdowns
    )

    return df


def summarize_regime_diagnostics(df):
    """
    Summarize performance and risk by market regime.
    """

    summary = (
        df
        .groupby("Market_Regime")
        .agg(
            Observations=(
                "Close",
                "count"
            ),

            Mean_Daily_Return=(
                "Daily_Return",
                "mean"
            ),

            Daily_Volatility=(
                "Daily_Return",
                "std"
            ),

            Mean_20D_Volatility=(
                "Volatility_20D",
                "mean"
            ),

            Mean_Forward_5D=(
                "Forward_Return_5D",
                "mean"
            ),

            Mean_Forward_20D=(
                "Forward_Return_20D",
                "mean"
            ),

            Median_Forward_20D=(
                "Forward_Return_20D",
                "median"
            ),

            Mean_Forward_Drawdown_20D=(
                "Forward_Max_Drawdown_20D",
                "mean"
            ),

            Worst_Forward_Drawdown_20D=(
                "Forward_Max_Drawdown_20D",
                "min"
            )
        )
    )

    return summary


# ===========================================================
# REGIME SAMPLE QUALITY
# ===========================================================

def add_regime_sample_quality(
    df,
    minimum_observations=50
):
    """
    Flag regimes based only on historical sample size.

    This is a data-quality indicator, not a prediction.
    """

    df = df.copy()

    counts = (
        df["Market_Regime"]
        .value_counts()
    )

    df["Regime_Observations"] = (
        df["Market_Regime"]
        .map(counts)
    )

    df["Regime_Sample_Quality"] = np.where(
        df["Regime_Observations"]
        >= minimum_observations,
        "Well_Observed",
        "Limited"
    )

    return df


# ===========================================================
# BACKTEST ENGINE
# ===========================================================

def prepare_backtest(df):
    """
    Prepare a simple regime-based historical exposure series.

    IMPORTANT:
    The regime is shifted by one trading day so that today's
    regime cannot use tomorrow's return.
    """

    df = df.copy()
    df = df.sort_index()

    # Close-to-close market return
    df["Market_Return"] = (
        df["Close"].pct_change()
    )

    # Exposure determined from the PREVIOUS day's regime.
    #
    # This is deliberately simple and descriptive:
    #
    # Strong_Bullish / Bullish -> +1
    # Mixed                    -> 0
    # Bearish / Strong_Bearish -> -1
    #
    # We are not claiming these exposures are optimal.

    exposure_map = {
        "Strong_Bullish": 1.0,
        "Bullish": 1.0,
        "Mixed": 0.0,
        "Bearish": -1.0,
        "Strong_Bearish": -1.0
    }

    df["Raw_Exposure"] = (
        df["Market_Regime"]
        .map(exposure_map)
    )

    # Shift exposure by one day.
    df["Backtest_Exposure"] = (
        df["Raw_Exposure"].shift(1)
    )

    # Strategy daily return
    df["Strategy_Return"] = (
        df["Backtest_Exposure"]
        * df["Market_Return"]
    )

    # Equity curves
    df["Market_Equity"] = (
        1 + df["Market_Return"].fillna(0)
    ).cumprod()

    df["Strategy_Equity"] = (
        1 + df["Strategy_Return"].fillna(0)
    ).cumprod()

    return df


def calculate_backtest_metrics(df):
    """
    Calculate descriptive backtest statistics.
    """

    strategy_returns = (
        df["Strategy_Return"]
        .dropna()
    )

    market_returns = (
        df["Market_Return"]
        .dropna()
    )

    def annualized_return(returns):
        if len(returns) == 0:
            return np.nan

        cumulative = (
            1 + returns
        ).prod()

        years = len(returns) / 252

        if years <= 0:
            return np.nan

        return (
            cumulative ** (1 / years)
        ) - 1

    def max_drawdown(returns):
        equity = (
            1 + returns
        ).cumprod()

        peak = equity.cummax()

        drawdown = (
            equity / peak - 1
        )

        return drawdown.min()

    metrics = pd.Series({
        "Strategy_Total_Return":
            (1 + strategy_returns).prod() - 1,

        "Market_Total_Return":
            (1 + market_returns).prod() - 1,

        "Strategy_Annualized_Return":
            annualized_return(strategy_returns),

        "Market_Annualized_Return":
            annualized_return(market_returns),

        "Strategy_Volatility":
            strategy_returns.std()
            * np.sqrt(252),

        "Market_Volatility":
            market_returns.std()
            * np.sqrt(252),

        "Strategy_Max_Drawdown":
            max_drawdown(strategy_returns),

        "Market_Max_Drawdown":
            max_drawdown(market_returns),

        "Strategy_Positive_Days":
            (strategy_returns > 0).mean(),

        "Market_Positive_Days":
            (market_returns > 0).mean()
    })

    return metrics
