from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"

MASTER_PARQUET = DATA_DIR / "nifty_df_master.parquet"


# ============================================================
# LOAD MASTER DATA
# ============================================================

def load_nifty_master():
    """
    Load the local NIFTY master dataframe.
    """

    if not MASTER_PARQUET.exists():
        raise FileNotFoundError(
            f"Master parquet not found: {MASTER_PARQUET}"
        )

    df = pd.read_parquet(MASTER_PARQUET)

    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    return df


# ============================================================
# ATR
# ============================================================

def add_atr(df, period=14):
    """
    Calculate Average True Range (ATR).

    ATR measures absolute market volatility.
    """

    df = df.copy()

    previous_close = df["Close"].shift(1)

    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - previous_close).abs(),
            (df["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["True_Range"] = true_range

    df["ATR_14"] = (
        true_range
        .ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        )
        .mean()
    )

    return df


# ============================================================
# ATR AS % OF PRICE
# ============================================================

def add_atr_percent(df):
    """
    Express ATR as a percentage of closing price.

    This allows volatility to be compared across different
    price levels.
    """

    df = df.copy()

    df["ATR_Pct"] = (
        df["ATR_14"]
        / df["Close"]
    ) * 100

    return df


# ============================================================
# REALIZED VOLATILITY
# ============================================================

def add_realized_volatility(df, period=20):
    """
    Calculate annualized rolling realized volatility.

    Daily log returns are used.
    """

    df = df.copy()

    log_returns = np.log(
        df["Close"]
        / df["Close"].shift(1)
    )

    df["Log_Return"] = log_returns

    df["Realized_Volatility_20D"] = (
        log_returns
        .rolling(
            period,
            min_periods=period,
        )
        .std()
        * np.sqrt(252)
        * 100
    )

    return df


# ============================================================
# VOLATILITY PERCENTILE
# ============================================================

def add_volatility_percentile(
    df,
    column="Realized_Volatility_20D",
    lookback=252,
):
    """
    Determine where current volatility sits relative to
    its historical distribution.

    Example:

    90 = current volatility is approximately higher than
         90% of observations in the lookback window.
    """

    df = df.copy()

    def percentile_rank(series):
        if pd.isna(series.iloc[-1]):
            return np.nan

        return (
            series.rank(pct=True).iloc[-1]
            * 100
        )

    df["Volatility_Percentile"] = (
        df[column]
        .rolling(
            lookback,
            min_periods=20,
        )
        .apply(
            percentile_rank,
            raw=False,
        )
    )

    return df


# ============================================================
# VOLATILITY REGIME
# ============================================================

def add_volatility_regime(df):
    """
    Classify the current volatility environment.

    LOW
    NORMAL
    ELEVATED
    HIGH
    EXTREME
    """

    df = df.copy()

    df["Volatility_Regime"] = np.select(
        [
            df["Volatility_Percentile"] <= 20,
            df["Volatility_Percentile"] <= 50,
            df["Volatility_Percentile"] <= 75,
            df["Volatility_Percentile"] <= 90,
            df["Volatility_Percentile"] > 90,
        ],
        [
            "Low",
            "Normal",
            "Elevated",
            "High",
            "Extreme",
        ],
        default="Unknown",
    )

    return df


# ============================================================
# COMPLETE VOLATILITY LAYER
# ============================================================

def add_volatility_layer(df):
    """
    Apply the complete volatility engine.
    """

    df = df.copy()

    df = add_atr(df)
    df = add_atr_percent(df)
    df = add_realized_volatility(df)
    df = add_volatility_percentile(df)
    df = add_volatility_regime(df)

    return df


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    df = load_nifty_master()

    df = add_volatility_layer(df)

    latest = df.iloc[-1]

    print("=" * 60)
    print("NIFTY VOLATILITY ENGINE")
    print("=" * 60)

    print("Date:", df.index[-1])
    print("Close:", round(latest["Close"], 2))
    print("ATR(14):", round(latest["ATR_14"], 2))
    print("ATR %:", round(latest["ATR_Pct"], 2))
    print(
        "Realized Volatility 20D:",
        round(
            latest["Realized_Volatility_20D"],
            2,
        ),
    )
    print(
        "Volatility Percentile:",
        round(
            latest["Volatility_Percentile"],
            2,
        ),
    )
    print(
        "Volatility Regime:",
        latest["Volatility_Regime"],
    )

    print("=" * 60)
