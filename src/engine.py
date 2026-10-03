
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
