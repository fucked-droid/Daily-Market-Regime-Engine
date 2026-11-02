import pandas as pd
import numpy as np

def aggregate_daily_to_weekly(daily_df):
    """
    Authenticate daily-to-weekly OHLCV aggregation.
    Resamples daily NIFTY dataframe to weekly bars (Friday/period end).
    """
    if daily_df is None or daily_df.empty:
        raise ValueError("daily_df cannot be empty or None")
        
    df = daily_df.copy()
    
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.set_index('Date')
        else:
            raise ValueError("daily_df must have a DatetimeIndex or a Date column.")
            
    required_ohlc = ['Open', 'High', 'Low', 'Close']
    missing = [col for col in required_ohlc if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required OHLC columns: {missing}")
        
    df = df.sort_index()
    if df.index.duplicated().any():
        df = df[~df.index.duplicated(keep='last')]
        
    if 'Volume' not in df.columns:
        df['Volume'] = 0

    weekly = df.resample('W-FRI').agg({
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }).dropna(subset=['Close'])
    
    return weekly

def add_weekly_regime_features(weekly_df):
    """
    Computes basic weekly trend and regime indicators (e.g. EMA9, EMA21, Trend state).
    """
    if weekly_df is None or weekly_df.empty:
        raise ValueError("weekly_df cannot be empty or None")
    df = weekly_df.copy()
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['Weekly_Trend'] = np.where(df['Close'] > df['EMA_21'], 'Bullish', 'Bearish')
    return df

def align_daily_weekly(daily_df, weekly_df):
    """
    Aligns weekly regime features back to daily bars using forward fill
    preceded by bfill for any leading days before the first weekly close.
    """
    if daily_df is None or daily_df.empty:
        raise ValueError("daily_df cannot be empty or None")
    if weekly_df is None or weekly_df.empty:
        raise ValueError("weekly_df cannot be empty or None")
        
    d_df = daily_df.copy()
    w_df = weekly_df[['EMA_9', 'EMA_21', 'Weekly_Trend']].copy()
    
    # Reindex weekly to daily and forward fill (with bfill for leading period)
    aligned = w_df.reindex(d_df.index).ffill().bfill()
    
    for col in aligned.columns:
        d_df[col] = aligned[col]
        
    if 'Market_Regime' in d_df.columns and 'Weekly_Trend' in d_df.columns:
        d_df['Multi_Timeframe_Aligned'] = (
            (d_df['Market_Regime'] == 'Bullish') & (d_df['Weekly_Trend'] == 'Bullish')
        ) | (
            (d_df['Market_Regime'] == 'Bearish') & (d_df['Weekly_Trend'] == 'Bearish')
        )
    else:
        d_df['Multi_Timeframe_Aligned'] = False
        
    return d_df
