import pandas as pd
import numpy as np
from pathlib import Path

def identify_swing_pivots(df, left=3, right=3):
    """
    Identify swing highs and swing lows with configurable left/right confirmation windows.
    
    Tie handling rule:
    - Swing High: strict inequality on left, non-strict (>=) on right, OR strict on both. 
      To ensure deterministic and robust peak identification in flat tops, we define:
      High at index i is a Swing High if:
      For all k in [i-left, i+1-left ... i-1] and [i+1, ..., i+right]:
      df['High'].iloc[i] >= df['High'].iloc[k], with strict inequality on at least one side 
      (or specifically df['High'].iloc[i] > df['High'].iloc[k] for k < i and >= for k > i, 
      or standard strict: High[i] > High[k] for all k != i).
      Standard strict: High[i] > High[k] for all k in [i-left, i+right] except i.
      For equal highs (ties), we pick the first occurrence (leftmost index).
    """
    df = df.copy()
    n = len(df)
    
    swing_highs = []
    swing_lows = []
    
    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    dates = df.index
    
    if n < (left + right + 1):
        return pd.DataFrame(columns=["pivot_date", "confirmation_date", "type", "price"])
    
    for i in range(left, n - right):
        window_highs = highs[i - left : i + right + 1]
        window_lows = lows[i - left : i + right + 1]
        
        current_high = highs[i]
        current_low = lows[i]
        
        # Check swing high (strict greater on left, >= on right, or strict all around)
        # To handle flat tops deterministically: strict greater than all left neighbors, >= all right neighbors, 
        # and leftmost index wins.
        left_highs = highs[i - left : i]
        right_highs = highs[i + 1 : i + right + 1]
        
        is_swing_high = (current_high > left_highs).all() and (current_high >= right_highs).all()
        
        # Check swing low
        left_lows = lows[i - left : i]
        right_lows = lows[i + 1 : i + right + 1]
        
        is_swing_low = (current_low < left_lows).all() and (current_low <= right_lows).all()
        
        if is_swing_high:
            pivot_date = dates[i]
            confirmation_date = dates[i + right]
            swing_highs.append({
                "pivot_date": pivot_date,
                "confirmation_date": confirmation_date,
                "type": "Resistance",
                "price": current_high,
                "pivot_idx": i
            })
            
        if is_swing_low:
            pivot_date = dates[i]
            confirmation_date = dates[i + right]
            swing_lows.append({
                "pivot_date": pivot_date,
                "confirmation_date": confirmation_date,
                "type": "Support",
                "price": current_low,
                "pivot_idx": i
            })
            
    pivots_df = pd.DataFrame(swing_highs + swing_lows)
    if not pivots_df.empty:
        pivots_df = pivots_df.sort_values("confirmation_date").reset_index(drop=True)
    return pivots_df


def build_support_resistance_zones(df, left=3, right=3, atr_mult=1.0):
    """
    Build chronological support/resistance zones from confirmed swing pivots.
    
    Rules:
    1. Pivots are only available at or after their confirmation_date.
    2. Clustering tolerance: Uses causal ATR (14-period EMA of True Range) at the confirmation date. 
       Zones within `atr_mult * ATR` are merged. When merging, price is averaged or weighted, 
       and earliest pivot_date is preserved, but confirmation_date is max confirmation date.
    3. Retest counting: A zone is retested when price (High/Low) enters the zone band.
    4. Close-based invalidation: A Support zone is invalidated if a candle closes below the zone's lower bound. 
       A Resistance zone is invalidated if a candle closes above the zone's upper bound.
    """
    df = df.copy()
    
    # Ensure causal ATR is available
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    df["ATR_14"] = atr
    
    raw_pivots = identify_swing_pivots(df, left=left, right=right)
    if raw_pivots.empty:
        return []
        
    dates = df.index
    zones = [] # List of zone dicts
    
    # Chronological simulation across each trading day
    for current_date in dates:
        current_row = df.loc[current_date]
        current_atr = current_row["ATR_14"]
        if pd.isna(current_atr):
            current_atr = current_row["Close"] * 0.02 # fallback
            
        tolerance = current_atr * atr_mult
        close_price = current_row["Close"]
        high_price = current_row["High"]
        low_price = current_row["Low"]
        
        # 1. Check newly confirmed pivots at this date
        newly_confirmed = raw_pivots[raw_pivots["confirmation_date"] == current_date]
        for _, pivot in newly_confirmed.iterrows():
            p_price = pivot["price"]
            p_type = pivot["type"]
            p_date = pivot["pivot_date"]
            c_date = pivot["confirmation_date"]
            
            # Check if it clusters with an existing active zone of the same type
            merged = False
            for z in zones:
                if z["status"] == "Active" and z["type"] == p_type:
                    # Check distance
                    if abs(z["price"] - p_price) <= tolerance:
                        # Merge into existing zone
                        z["price"] = (z["price"] + p_price) / 2.0
                        z["lower"] = min(z["lower"], p_price - tolerance * 0.5)
                        z["upper"] = max(z["upper"], p_price + tolerance * 0.5)
                        z["pivot_dates"].append(p_date)
                        z["confirmation_date"] = max(z["confirmation_date"], c_date)
                        merged = True
                        break
                        
            if not merged:
                zones.append({
                    "zone_id": len(zones) + 1,
                    "type": p_type,
                    "price": p_price,
                    "lower": p_price - tolerance * 0.5,
                    "upper": p_price + tolerance * 0.5,
                    "pivot_dates": [p_date],
                    "confirmation_date": c_date,
                    "status": "Active",
                    "retests": 0,
                    "invalidation_date": None
                })
                
        # 2. Update active zones (retests and invalidations) for current_date
        for z in zones:
            if z["status"] != "Active":
                continue
                
            # Do not process zones confirmed after today (shouldn't happen with confirmation_date == current_date check above, but safe guard)
            if z["confirmation_date"] > current_date:
                continue
                
            # Retest check: if price touches the zone band
            # Support zone band: [lower, upper]. Retested if Low <= upper and High >= lower.
            if low_price <= z["upper"] and high_price >= z["lower"]:
                # Count retest if not already counted on this exact bar (or count every touch)
                z["retests"] += 1
                
            # Invalidation check (close-based)
            if z["type"] == "Support":
                if close_price < z["lower"]:
                    z["status"] = "Invalidated"
                    z["invalidation_date"] = current_date
            elif z["type"] == "Resistance":
                if close_price > z["upper"]:
                    z["status"] = "Invalidated"
                    z["invalidation_date"] = current_date
                    
    return zones
