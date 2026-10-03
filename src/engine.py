
from pathlib import Path
import subprocess
import pandas as pd
import numpy as np


# ============================================================
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


# ============================================================
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


# ============================================================
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


# ============================================================
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


# ============================================================
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


# ============================================================
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


# ============================================================
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


# ============================================================
# APPLY CORE LAYERS
# ============================================================

def build_core_engine(df):
    """
    Rebuild the four core layers from OHLCV data.
    """

    df = df.copy()

    df = add_trend_layer(df)
    df = add_momentum_layer(df)
    df = add_structure_layer(df)
    df = add_participation_layer(df)

    return df


# ============================================================
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


# ============================================================
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


# ============================================================
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


# ============================================================
# MARKET REGIME LAYER
# ============================================================

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


# ============================================================
# REGIME TRANSITION ANALYSIS
# ============================================================

def calculate_regime_transitions(df):
    """
    Calculate regime-to-regime transitions.

    Returns
    -------
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


# ============================================================
# REGIME QUALITY DIAGNOSTICS
# ============================================================

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


# ============================================================
# REGIME SAMPLE QUALITY
# ============================================================

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


# ============================================================
# BACKTEST ENGINE
# ============================================================

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
