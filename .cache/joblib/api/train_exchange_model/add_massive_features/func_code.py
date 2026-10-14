# first line: 452
@memory_cache.cache
def add_massive_features(df):
    """
    Generate over 250 features using:
    1. TA library (~90 features)
    2. Rolling Stats
    3. Lagged historical data
    """
    # Create a copy to avoid modifying the original DataFrame
    df = df.copy()
    cols = {c.lower(): c for c in df.columns}
    for key in ("open", "high", "low", "close", "volume"):
        if key in cols and cols[key] != key:
            df.rename(columns={cols[key]: key}, inplace=True)
    if "close" not in df.columns or "volume" not in df.columns:
        import warnings

        missing = []
        if "close" not in df.columns:
            missing.append("close")
        if "volume" not in df.columns:
            missing.append("volume")
        warnings.warn(
            f"add_massive_features: Missing required columns {missing}. Returning DataFrame unprocessed. Feature engineering skipped!"
        )
        return df

    # ---------------------------------------------------------
    # 1. Ready-made Technical Indicators (Base: ~80-90 features)
    # ---------------------------------------------------------
    # This step alone adds RSI, MACD, Bollinger, Ichimoku, etc.
    df = add_all_ta_features(
        df,
        open="open",
        high="high",
        low="low",
        close="close",
        volume="volume",
        fillna=True,
    )

    # 2. Vectorized Rolling Windows & Tags
    windows = [3, 7, 14, 30]
    target_cols = ["close", "volume", "momentum_rsi"]
    extra_cols = {}

    # Pre-calculate rolling objects for each window to reuse
    for w in windows:
        existing = [c for c in target_cols if c in df.columns]
        if not existing:
            continue

        # Grouped rolling operation is faster than individual ones
        roll = df[existing].rolling(window=w)
        means = roll.mean()
        stds = roll.std()
        maxs = roll.max()
        mins = roll.min()

        for col in existing:
            extra_cols[f"{col}_SMA_{w}"] = means[col]
            extra_cols[f"{col}_STD_{w}"] = stds[col]
            extra_cols[f"{col}_MAX_{w}"] = maxs[col]
            extra_cols[f"{col}_MIN_{w}"] = mins[col]

    # 3. Historical Memory (Lag Features)
    # Detect correct column names (case-insensitive)
    close_col = (
        "close" if "close" in df.columns else "Close" if "Close" in df.columns else None
    )
    vol_col = (
        "volume"
        if "volume" in df.columns
        else "Volume"
        if "Volume" in df.columns
        else None
    )

    if close_col and vol_col:
        lags = [1, 2, 3, 5]
        for lag in lags:
            extra_cols[f"Close_Lag_{lag}"] = df[close_col].shift(lag)
            extra_cols[f"Vol_Lag_{lag}"] = df[vol_col].shift(lag)
            extra_cols[f"Return_{lag}d"] = df[close_col].pct_change(lag)

    # 4. Advanced Vectorized Math
    if close_col:
        extra_cols["Log_Ret"] = np.log(
            df[close_col] / df[close_col].shift(1).replace(0, np.nan)
        )

        # Optimizing Z-Score (one rolling object)
        roll20 = df[close_col].rolling(20)
        mu20 = roll20.mean()
        sigma20 = roll20.std()
        extra_cols["Z_Score_20"] = (df[close_col] - mu20) / sigma20.replace(0, np.nan)

        if vol_col:
            extra_cols["PV_Trend"] = (
                df[close_col].pct_change() * df[vol_col].pct_change()
            )

            # --- الإضافات الجديدة (Smart Money Features) ---
            # 1. Amihud Illiquidity (بصمة المؤسسات والسيولة)
            extra_cols["Amihud_Illiquidity"] = (
                df[close_col].pct_change().abs() / (df[close_col] * df[vol_col] + 1e-9)
            ).replace([np.inf, -np.inf], 0)
            extra_cols["Amihud_SMA_10"] = (
                extra_cols["Amihud_Illiquidity"].rolling(10).mean().fillna(0)
            )

            # 2. Volume Acceleration (تسارع الفوليوم)
            vol_sma_3 = df[vol_col].rolling(3).mean()
            vol_sma_20 = df[vol_col].rolling(20).mean()
            extra_cols["Volume_Acceleration"] = (
                (vol_sma_3 / (vol_sma_20 + 1e-9))
                .replace([np.inf, -np.inf], 1.0)
                .fillna(1.0)
            )

    # 5. Regime Features (Hurst & Volume Delta)
    if close_col:
        try:
            # Approximate Hurst via rolling variance ratio
            roll10 = df[close_col].diff().rolling(10)
            roll30 = df[close_col].diff().rolling(30)
            var10 = roll10.var()
            var30 = roll30.var()
            extra_cols["Regime_Hurst_Proxy"] = (var30 / (var10 * 3 + 1e-9)).fillna(1.0)
        except Exception:
            extra_cols["Regime_Hurst_Proxy"] = 1.0

    if vol_col and close_col:
        # Volume Delta: Volume * sign(Close Return)
        extra_cols["Volume_Delta"] = df[vol_col] * np.sign(df[close_col].diff())
        extra_cols["Volume_Delta_SMA_10"] = (
            extra_cols["Volume_Delta"].rolling(10).mean().fillna(0)
        )

    # 3. Gap Anomalies (الفجوات السعرية)
    if ("open" in df.columns or "Open" in df.columns) and close_col:
        open_c = "open" if "open" in df.columns else "Open"
        prev_close = df[close_col].shift(1)
        extra_cols["Overnight_Gap"] = (
            ((df[open_c] - prev_close) / (prev_close + 1e-9))
            .replace([np.inf, -np.inf], 0)
            .fillna(0)
        )
        extra_cols["Intraday_Return"] = (
            ((df[close_col] - df[open_c]) / (df[open_c] + 1e-9))
            .replace([np.inf, -np.inf], 0)
            .fillna(0)
        )
    else:
        extra_cols["Overnight_Gap"] = 0.0
        extra_cols["Intraday_Return"] = 0.0

    # Sector Relative Strength
    if "sector_avg_return" in df.columns:
        if "stock_daily_return" in df.columns:
            extra_cols["feat_sector_rel_strength"] = (
                df["stock_daily_return"] - df["sector_avg_return"]
            )
        elif close_col:
            stock_ret = df[close_col].pct_change().fillna(0.0)
            extra_cols["feat_sector_rel_strength"] = stock_ret - df["sector_avg_return"]
        else:
            extra_cols["feat_sector_rel_strength"] = 0.0
    else:
        extra_cols["feat_sector_rel_strength"] = 0.0

    # ============================================================================
    # 🔥 EGX-Specific Features (Circuit Breaker, Volume Patterns, Bull Days)
    # ============================================================================
    # These features are tuned for Egyptian Exchange trading behavior

    if close_col and ("high" in df.columns or "High" in df.columns):
        high_col = "high" if "high" in df.columns else "High"
        low_col = "low" if "low" in df.columns else "Low"

        # 1. Distance from ±10% Circuit Breaker Limits (EGX Daily Halt Rules)
        prev_close = df[close_col].shift(1)
        circuit_upper = prev_close * 1.10  # +10% daily limit
        circuit_lower = prev_close * 0.90  # -10% daily limit

        current_high = df[high_col]
        current_low = df[low_col]

        # How far from upper limit (as % of circuit range)
        extra_cols["pct_from_circuit_breaker"] = (
            ((circuit_upper - current_high) / (circuit_upper - circuit_lower + 1e-9))
            .fillna(0.5)
            .clip(0, 1)
        )  # 0 = at upper limit, 1 = at lower limit

        # 2. Previous Day Hit Upper Limit (Strong Bullish Signal)
        prev_high = df[high_col].shift(1)
        extra_cols["prev_hit_upper_limit"] = (
            (prev_high >= circuit_upper.shift(1)).astype(int)
        ).fillna(0)

        # 3. Bull Days Percentage in Last 10 Bars
        returns_10 = df[close_col].diff() > 0
        extra_cols["bull_days_10"] = (returns_10.rolling(10).sum() / 10.0).fillna(
            0.5
        )  # % of up days

        # 4. Volume Dry-up Pattern (Low Volume = Accumulation)
        if vol_col:
            vol_ma_20 = df[vol_col].rolling(20).mean()
            extra_cols["volume_dryup"] = (
                (df[vol_col] / (vol_ma_20 + 1e-9))
                .replace([np.inf, -np.inf], 1.0)
                .fillna(1.0)
            )
            # < 0.7 = dry-up, > 1.3 = spike
            extra_cols["feat_volume_dryup"] = extra_cols["volume_dryup"]

        # --- EGX Specific Features ---
        dist_up = (circuit_upper - df[high_col]) / (prev_close + 1e-9)
        dist_down = (df[low_col] - circuit_lower) / (prev_close + 1e-9)
        extra_cols["feat_circuit_breaker_distance"] = np.minimum(
            dist_up, dist_down
        ).fillna(0.10)

        is_green = (
            (df[close_col] > df["open"]).astype(float)
            if "open" in df.columns
            else returns_10.astype(float)
        )
        extra_cols["feat_bull_consistency"] = is_green.rolling(10).mean().fillna(0.5)

        low_250 = df[close_col].rolling(250).min()
        high_250 = df[close_col].rolling(250).max()
        extra_cols["feat_52w_position"] = (
            (df[close_col] - low_250) / (high_250 - low_250 + 1e-9)
        ).fillna(0.5)

    # Maintain Case-Sensitive Columns for other functions
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c.lower() in df.columns:
            extra_cols[c] = df[c.lower()]

    if extra_cols:
        df = pd.concat([df, pd.DataFrame(extra_cols, index=df.index)], axis=1)
        df = df.copy()

    # Clean data (remove NaN values resulting from Lags) - only for numeric columns
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    df[numeric_cols] = df[numeric_cols].replace([np.inf, -np.inf], np.nan).fillna(0)

    return df
