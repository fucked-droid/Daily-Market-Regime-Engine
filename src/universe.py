from pathlib import Path

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

REPO_DIR = Path(__file__).resolve().parent.parent

UNIVERSE_FILE = (
    REPO_DIR
    / "data"
    / "universe"
    / "nifty50_constituents.csv"
)



# ============================================================
# LOAD UNIVERSE
# ============================================================

def load_nifty50_universe(
    universe_file=UNIVERSE_FILE
):
    """
    Load the historical NIFTY 50 constituent universe.

    Required columns:
        Symbol
        Start_Date
        End_Date
        Source
    """

    df = pd.read_csv(
        universe_file
    )

    required_columns = [
        "Symbol",
        "Start_Date",
        "End_Date",
        "Source"
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing universe columns: {missing}"
        )

    df["Symbol"] = (
        df["Symbol"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["Start_Date"] = pd.to_datetime(
        df["Start_Date"],
        errors="coerce"
    )

    df["End_Date"] = pd.to_datetime(
        df["End_Date"],
        errors="coerce"
    )

    return df


# ============================================================
# VALIDATE UNIVERSE
# ============================================================

def validate_nifty50_universe(
    universe_df
):
    """
    Validate the NIFTY 50 historical universe.
    """

    if not isinstance(
        universe_df,
        pd.DataFrame
    ):
        raise TypeError(
            "universe_df must be a pandas DataFrame"
        )

    if universe_df.empty:
        raise ValueError(
            "NIFTY 50 universe is empty"
        )

    required_columns = [
        "Symbol",
        "Start_Date",
        "End_Date",
        "Source"
    ]

    missing = [
        column
        for column in required_columns
        if column not in universe_df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing universe columns: {missing}"
        )

    if universe_df["Symbol"].isna().any():
        raise ValueError(
            "Universe contains missing symbols"
        )

    if universe_df["Start_Date"].isna().any():
        raise ValueError(
            "Universe contains invalid Start_Date values"
        )

    invalid_dates = (
        universe_df["End_Date"].notna()
        &
        (
            universe_df["End_Date"]
            < universe_df["Start_Date"]
        )
    )

    if invalid_dates.any():
        raise ValueError(
            "Universe contains End_Date earlier than Start_Date"
        )

    return True


# ============================================================
# GET CONSTITUENTS FOR A DATE
# ============================================================

def get_nifty50_constituents(
    date,
    universe_df=None
):
    """
    Return NIFTY 50 constituents active on a given date.
    """

    if universe_df is None:
        universe_df = load_nifty50_universe()

    validate_nifty50_universe(
        universe_df
    )

    date = pd.Timestamp(date)

    active = universe_df[
        (universe_df["Start_Date"] <= date)
        &
        (
            universe_df["End_Date"].isna()
            |
            (universe_df["End_Date"] >= date)
        )
    ].copy()

    active = (
        active
        .sort_values("Symbol")
        .reset_index(drop=True)
    )

    return active
