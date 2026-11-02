import src.engine as e
import pandas as pd
import numpy as np

print("Running historical stability test...")

# Generate a deterministic OHLCV dataset long enough for indicator warm-ups (e.g., 300 days)
np.random.seed(42)
days = 300
dates = pd.date_range("2024-01-01", periods=days, freq="B")

close_prices = 100 + np.cumsum(np.random.randn(days) * 1.5)
high_prices = close_prices + np.random.rand(days) * 2.0
low_prices = close_prices - np.random.rand(days) * 2.0
open_prices = close_prices + np.random.randn(days) * 0.5
volume = np.random.randint(1000000, 5000000, size=days)

df_base = pd.DataFrame({
    "Open": open_prices,
    "High": high_prices,
    "Low": low_prices,
    "Close": close_prices,
    "Volume": volume
}, index=dates)

# Build pipeline for prefix of dates (e.g., first 200 days)
prefix_len = 200
df_prefix = df_base.iloc[:prefix_len].copy()

df_prefix = e.build_core_engine(df_prefix)
df_prefix = e.add_regime_layer(df_prefix)
regimes_prefix = df_prefix["Market_Regime"].copy()

# Build pipeline for full dataset (all 300 days)
df_full = df_base.copy()
df_full = e.build_core_engine(df_full)
df_full = e.add_regime_layer(df_full)
regimes_full_prefix = df_full["Market_Regime"].iloc[:prefix_len]

# Verify that all regime labels in the original prefix remain identical
pd.testing.assert_series_equal(
    regimes_prefix,
    regimes_full_prefix,
    check_names=True,
    obj="Historical Regime Stability Prefix Check"
)

print("Historical stability regression test passed successfully.")
