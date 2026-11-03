"""
Market Data Ingestion & Live Scanner Module for NIFTY 50 and India VIX.

Fetches up-to-date daily candles from Yahoo Finance (^NSEI and ^INDIAVIX),
updates local master datasets, and computes expected daily movement ranges.
"""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Dict, Optional, Tuple
import urllib.request

import numpy as np
import pandas as pd

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"
MASTER_PARQUET = DATA_DIR / "nifty_df_master.parquet"
MASTER_CSV = DATA_DIR / "nifty_df_master.csv"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def fetch_yahoo_chart(
    symbol: str = "^NSEI",
    interval: str = "1d",
    range_str: str = "3mo",
    timeout: int = 15,
) -> pd.DataFrame:
    """
    Fetch OHLCV historical daily bars from Yahoo Finance.

    Parameters:
        symbol: Ticker symbol (e.g. '^NSEI' for Nifty 50, '^INDIAVIX' for India VIX).
        interval: Bar interval ('1d', '1wk', etc.).
        range_str: Lookback period ('1mo', '3mo', '6mo', '1y', '2y').
        timeout: HTTP request timeout in seconds.

    Returns:
        pd.DataFrame with columns: [Open, High, Low, Close, Adj Close, Volume]
        and DatetimeIndex.
    """
    encoded_symbol = urllib.request.quote(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?interval={interval}&range={range_str}"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Yahoo Finance returned HTTP status {response.status}")
        raw_json = json.loads(response.read().decode("utf-8"))

    chart = raw_json.get("chart", {})
    results = chart.get("result", [])
    if not results:
        err = chart.get("error", {})
        raise RuntimeError(f"Yahoo Finance API error: {err.get('description', 'No results returned')}")

    data = results[0]
    timestamps = data.get("timestamp", [])
    if not timestamps:
        raise ValueError(f"No price timestamps returned for {symbol}")

    quotes = data.get("indicators", {}).get("quote", [{}])[0]
    adjclose_list = (
        data.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    )

    dates = [
        pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata").date()
        for ts in timestamps
    ]

    df = pd.DataFrame(
        {
            "Open": quotes.get("open", []),
            "High": quotes.get("high", []),
            "Low": quotes.get("low", []),
            "Close": quotes.get("close", []),
            "Adj Close": adjclose_list if adjclose_list else quotes.get("close", []),
            "Volume": quotes.get("volume", []),
        },
        index=pd.to_datetime(dates),
    )

    df.index.name = "Date"

    # Drop null rows where market was closed or holiday
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df = df.sort_index()

    # Fill 0 for null volumes
    df["Volume"] = df["Volume"].fillna(0).astype(int)

    return df


def fetch_india_vix(range_str: str = "1mo") -> Optional[pd.DataFrame]:
    """Fetch recent India VIX (^INDIAVIX) daily values."""
    try:
        return fetch_yahoo_chart("^INDIAVIX", range_str=range_str)
    except Exception as exc:
        print(f"[WARNING] Could not fetch India VIX from Yahoo Finance: {exc}")
        return None


def calculate_expected_daily_range(
    close_price: float,
    atr_14: Optional[float] = None,
    current_vix: Optional[float] = None,
) -> Dict[str, float]:
    """
    Calculate the statistical expected daily movement and price bounds for tomorrow.

    Uses:
    1. India VIX 1-day implied standard deviation:
       daily_move_pct = VIX / (sqrt(252) * 100)
    2. Average True Range (ATR_14) as a volatility benchmark.
    """
    results: Dict[str, float] = {
        "close": close_price,
    }

    if current_vix and current_vix > 0:
        # Annual trading days = 252
        daily_sd_pct = (current_vix / (math.sqrt(252) * 100.0))
        daily_points = close_price * daily_sd_pct

        results["vix"] = round(current_vix, 2)
        results["vix_expected_move_pts"] = round(daily_points, 2)
        results["vix_expected_move_pct"] = round(daily_sd_pct * 100.0, 2)
        results["vix_upper_bound"] = round(close_price + daily_points, 2)
        results["vix_lower_bound"] = round(close_price - daily_points, 2)

    if atr_14 and atr_14 > 0:
        results["atr_14"] = round(atr_14, 2)
        results["atr_upper_bound"] = round(close_price + atr_14, 2)
        results["atr_lower_bound"] = round(close_price - atr_14, 2)
        results["atr_pct"] = round((atr_14 / close_price) * 100.0, 2)

    # Composite range
    upper = results.get("vix_upper_bound") or results.get("atr_upper_bound")
    lower = results.get("vix_lower_bound") or results.get("atr_lower_bound")
    if upper and lower:
        results["expected_daily_upper"] = upper
        results["expected_daily_lower"] = lower
        results["expected_range_points"] = round(upper - lower, 2)

    return results


def update_master_nifty_dataset(
    range_str: str = "3mo",
) -> Tuple[pd.DataFrame, int]:
    """
    Fetch recent NIFTY 50 candles and safely update the master parquet and csv files.

    Returns:
        (updated_dataframe, count_of_new_or_updated_rows)
    """
    from .engine import validate_nifty_df, load_nifty_master

    # 1. Fetch live candles
    fresh_df = fetch_yahoo_chart("^NSEI", range_str=range_str)

    # 2. Load existing master
    try:
        master_df = load_nifty_master()
    except Exception:
        master_df = pd.DataFrame()

    if master_df.empty:
        combined = fresh_df
        new_count = len(combined)
    else:
        # Standardize columns
        base_cols = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
        fresh_clean = fresh_df[[c for c in base_cols if c in fresh_df.columns]].copy()

        # Combine: existing takes historical priority, fresh overrides matching or appends newer dates
        combined = pd.concat([master_df, fresh_clean])
        # Deduplicate: keep the freshest bar for matching dates
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()

        new_count = len(combined) - len(master_df)

    # 3. Validate
    validate_nifty_df(combined)

    # 4. Save to parquet and csv
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(MASTER_PARQUET)
    combined.to_csv(MASTER_CSV)

    return combined, new_count
