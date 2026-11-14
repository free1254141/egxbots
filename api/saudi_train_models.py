#!/usr/bin/env python3
"""
Saudi (Tadawul / TASI) Full-History ML Pipeline using Exact EGX Architecture.

Mirrors Egypt (EGX) production ML engineering (`api/train_exchange_model.py`,
`api/strict_quality_labeler.py`, `api/unified_labeling.py`,
`api/adaptive_model_selector.py`) for Saudi stocks (`exchange="TADAWUL"`):
  1. Loads ALL historical Saudi OHLCV (2010 -> latest) and TASI `market_index`,
     with incremental disk caching under `api/data_cache/saudi_history_cache.pkl`.
  2. Builds exact EGX indicators, massive features, TASI market context,
     causal lagged sector relative strength, and `StrictQualityLabeler`
     triple-barrier targets (`next_open` entry, causal signal-bar `ATR_14`,
     circuit-breaker & market-panic filtering, soft `vol_below_avg` flag).
  3. Trains `KING_TASI.pkl` and `model_TADAWUL.pkl` using purged chronological
     60/10/10/20 splits, train-only `PCA(3)` + `StandardScaler`
     (`QuantitativeModelPipeline`), purged 5-split walk-forward diagnostics,
     XGBoost out-of-sample Meta-Labeling (`meta_model` trained strictly on the
     tune period), and `AdaptiveModelSelector`-compatible `.model_card.json` files.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("STOKSCANAI_DISABLE_JOBLIB_CACHE", "1")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json
import pickle
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from pandas.api.types import is_numeric_dtype
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from supabase import Client, create_client

from api.egx30_fetcher import get_market_regime
from api.model_utils import align_pandas_categories_to_booster, get_primary_booster, reset_nested_boosters
from api.recommendation_policy import evaluate_bars, profit_protection_stop
from api.stock_ai import add_technical_indicators
from api.strategy_engine import StrategyEngine
from api.strict_quality_labeler import StrictQualityLabeler
from api.structured_logger import StructuredLogger
from api.trading_config import TradingParameters
from api.train_exchange_model import (
    ModelTrainer,
    add_market_context,
    add_massive_features,
    xgb,
)
from api.unified_features import FeatureEngineeringManager

DEFAULT_HISTORY_START = "2010-01-01"
DEFAULT_CACHE_PATH = os.path.join(PROJECT_ROOT, "api", "data_cache", "saudi_history_cache.pkl")
DEFAULT_FEATURES_CACHE_PATH = os.path.join(PROJECT_ROOT, "api", "data_cache", "saudi_compact_features.pkl")
EXCHANGE = "TADAWUL"
COUNTRY = "Saudi Arabia"

STATIONARY_EXCLUDE_COLS = {
    "symbol",
    "Date",
    "date",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "ATR_14",
    "industry",
    "Target",
}

META_CORE_CANDIDATES = (
    "ADX_14",
    "CMF_20",
    "R_VOL",
    "MM_Accumulation",
    "MM_Distribution",
    "feat_mkt_trend",
    "feat_mkt_volatility",
    "feat_rel_strength",
    "feat_sector_rel_strength",
    "ATR_pct",
    "RSI",
    "MACD_Hist",
    "BB_PctB",
    "Price_vs_SMA200",
    "feat_52w_position",
    "feat_bull_consistency",
    "volatility_ui",
    "volume_mfi",
)

_THREAD_LOCAL = threading.local()


def get_saudi_credentials() -> Tuple[str, str]:
    load_dotenv(os.path.join(PROJECT_ROOT, "api", ".env"))
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    url = (os.getenv("SAUDI_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL") or "").strip()
    key = (os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("SAUDI_SUPABASE_URL / SAUDI_SUPABASE_SERVICE_ROLE_KEY not configured")
    return url.rstrip("/"), key


def _get_session(service_key: str) -> requests.Session:
    sess = getattr(_THREAD_LOCAL, "session", None)
    if sess is None:
        sess = requests.Session()
        sess.headers.update({
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        })
        _THREAD_LOCAL.session = sess
    return sess


def _fetch_paginated_table(
    sb: Client,
    table: str,
    select_cols: str,
    filters: Optional[List[Tuple[str, str, Any]]] = None,
    order_col: Optional[str] = None,
    page_size: int = 1000,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        q = sb.table(table).select(select_cols)
        if filters:
            for op, col, val in filters:
                if op == "eq":
                    q = q.eq(col, val)
                elif op == "gte":
                    q = q.gte(col, val)
                elif op == "gt":
                    q = q.gt(col, val)
        if order_col:
            q = q.order(order_col, desc=False)
        res = q.range(offset, offset + page_size - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _fetch_symbol_prices_rest(
    base_url: str,
    service_key: str,
    sym: str,
    start_date: str,
    date_op: str = "gte",
) -> Tuple[str, pd.DataFrame]:
    sess = _get_session(service_key)
    endpoint = f"{base_url}/rest/v1/stock_prices"
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        params = {
            "select": "date,open,high,low,close,volume",
            "symbol": f"eq.{sym}",
            "exchange": f"eq.{EXCHANGE}",
            "date": f"{date_op}.{start_date}",
            "order": "date.asc",
            "limit": str(page_size),
            "offset": str(offset),
        }
        batch: List[Dict[str, Any]] = []
        for attempt in range(5):
            try:
                resp = sess.get(endpoint, params=params, timeout=30)
                resp.raise_for_status()
                batch = resp.json() or []
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(0.5 * (2 ** attempt))
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    if not all_rows:
        return sym, pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).drop_duplicates(subset=["date"]).sort_values("date").set_index("date")
    df = df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })
    for col in ("Open", "High", "Low", "Close", "Volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Close"]).copy()
    df = df[df["Close"] > 0].copy()
    for col in ("Open", "High", "Low"):
        df[col] = df[col].fillna(df["Close"])
    df["Volume"] = df["Volume"].fillna(0.0).clip(lower=0.0)
    return sym, df


def _build_market_df(idx_rows: List[Dict[str, Any]]) -> pd.DataFrame:
    mdf = pd.DataFrame(idx_rows)
    mdf["date"] = pd.to_datetime(mdf["date"], errors="coerce")
    mdf = mdf.dropna(subset=["date"]).drop_duplicates(subset=["date"]).sort_values("date").set_index("date")
    mdf["close"] = pd.to_numeric(mdf["close"], errors="coerce").ffill().fillna(0.0)
    mdf["open"] = mdf["close"]
    mdf["high"] = mdf["close"]
    mdf["low"] = mdf["close"]
    mdf["volume"] = 0.0
    mdf["atr"] = mdf["close"].pct_change().rolling(20).std().fillna(0.0)
    mdf["egx30_return"] = mdf["close"].pct_change().fillna(0.0)
    mdf["market_regime"] = mdf["egx30_return"].apply(get_market_regime)
    return mdf


def load_saudi_history_cached(
    base_url: Optional[str] = None,
    service_key: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    history_start_date: str = DEFAULT_HISTORY_START,
    cache_path: str = DEFAULT_CACHE_PATH,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Load full Saudi Tadawul historical prices (2010 -> latest), market index,
    stock metadata, and fundamentals with smart local cache + tail-only refresh.
    """
    t0 = time.time()
    if not base_url or not service_key:
        base_url, service_key = get_saudi_credentials()
    sb = create_client(base_url, service_key)

    # Check latest index date via single-row query
    latest_idx_res = (
        sb.table("market_index")
        .select("date")
        .eq("exchange", EXCHANGE)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    remote_max_date = str((latest_idx_res.data or [{}])[0].get("date") or "")[:10]

    cached: Optional[Dict[str, Any]] = None
    if not force_refresh and os.path.exists(cache_path):
        try:
            with open(cache_path, "rb") as f:
                cached = pickle.load(f)
        except Exception:
            cached = None

    if (
        cached
        and cached.get("history_start_date") <= history_start_date
        and cached.get("max_price_date")
        and remote_max_date
        and str(cached["max_price_date"])[:10] >= remote_max_date
        and len(cached.get("bars_by_symbol") or {}) >= 250
    ):
        bars_by_symbol = cached["bars_by_symbol"]
        if symbols:
            bars_by_symbol = {s: bars_by_symbol[s] for s in symbols if s in bars_by_symbol}
        cached_copy = dict(cached)
        cached_copy["bars_by_symbol"] = bars_by_symbol
        total_rows = sum(len(v) for v in bars_by_symbol.values())
        print(
            f"  [CACHE HIT] Loaded {total_rows:,} historical Saudi price bars "
            f"({cached['min_price_date']} -> {cached['max_price_date']}) "
            f"across {len(bars_by_symbol)} symbols + {len(cached['market_index_rows']):,} TASI bars "
            f"in {time.time() - t0:.2f}s"
        )
        return cached_copy

    # Fetch stocks metadata, fundamentals, and market_index cleanly
    stocks_rows = _fetch_paginated_table(
        sb,
        "stocks",
        "id,symbol,exchange,sector,industry,name,name_ar,is_active",
        filters=[("eq", "exchange", EXCHANGE), ("eq", "is_active", True)],
        order_col="symbol",
    )
    stocks_rows = [
        r for r in stocks_rows if str(r.get("symbol") or "").isdigit() and len(str(r.get("symbol"))) == 4
    ]
    target_symbols = sorted({str(r["symbol"]) for r in stocks_rows})
    if symbols:
        target_symbols = sorted(set(target_symbols) & set(symbols) or set(symbols))

    idx_rows = _fetch_paginated_table(
        sb,
        "market_index",
        "exchange,date,close,ret",
        filters=[("eq", "exchange", EXCHANGE), ("gte", "date", history_start_date)],
        order_col="date",
    )
    market_df = _build_market_df(idx_rows)

    fund_rows = _fetch_paginated_table(
        sb,
        "stock_fundamentals",
        "symbol,fund_score,data",
        filters=[("eq", "exchange", EXCHANGE)],
        order_col="symbol",
    )

    bars_by_symbol: Dict[str, pd.DataFrame] = {}
    tail_mode = bool(
        cached
        and not force_refresh
        and cached.get("history_start_date") <= history_start_date
        and isinstance(cached.get("bars_by_symbol"), dict)
        and len(cached["bars_by_symbol"]) >= 200
        and cached.get("max_price_date")
    )
    tail_cutoff = str(cached["max_price_date"])[:10] if tail_mode else history_start_date
    date_op = "gt" if tail_mode else "gte"
    if tail_mode:
        bars_by_symbol = {s: df.copy() for s, df in cached["bars_by_symbol"].items()}
        print(f"  [CACHE TAIL] Refreshing incremental Saudi bars after {tail_cutoff}...")
    else:
        print(f"  [CACHE MISS] Downloading full Saudi price history since {history_start_date} for {len(target_symbols)} symbols...")

    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [
            pool.submit(_fetch_symbol_prices_rest, base_url, service_key, sym, tail_cutoff, date_op)
            for sym in target_symbols
        ]
        for fut in as_completed(futs):
            sym, new_df = fut.result()
            if tail_mode and sym in bars_by_symbol:
                if not new_df.empty:
                    merged = pd.concat([bars_by_symbol[sym], new_df])
                    merged = merged[~merged.index.duplicated(keep="last")].sort_index()
                    bars_by_symbol[sym] = merged
            elif not new_df.empty:
                bars_by_symbol[sym] = new_df

    min_date = min(df.index.min().strftime("%Y-%m-%d") for df in bars_by_symbol.values() if not df.empty)
    max_date = max(df.index.max().strftime("%Y-%m-%d") for df in bars_by_symbol.values() if not df.empty)
    total_rows = sum(len(df) for df in bars_by_symbol.values())

    payload = {
        "stocks_rows": stocks_rows,
        "fund_rows": fund_rows,
        "market_index_rows": idx_rows,
        "market_df": market_df,
        "bars_by_symbol": bars_by_symbol,
        "history_start_date": history_start_date,
        "min_price_date": min_date,
        "max_price_date": max_date,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    print(
        f"  [OK] Cached {total_rows:,} Saudi price bars ({min_date} -> {max_date}) "
        f"across {len(bars_by_symbol)} symbols + {len(idx_rows):,} TASI index bars in {time.time() - t0:.1f}s -> {cache_path}"
    )
    return payload


def load_or_build_compact_features(
    history_cache: Dict[str, Any],
    features_cache_path: str = DEFAULT_FEATURES_CACHE_PATH,
    force_rebuild: bool = False,
) -> pd.DataFrame:
    """
    Load or compute causal stationary EGX feature frame for all 264 Saudi symbols
    with float32 downcasting so training stays fast and low-memory (~175 MB).
    """
    max_price_date = str(history_cache.get("max_price_date") or "")[:10]
    if not force_rebuild and os.path.exists(features_cache_path):
        try:
            df_cached = pd.read_pickle(features_cache_path)
            if (
                isinstance(df_cached, pd.DataFrame)
                and len(df_cached) >= 700_000
                and "Date" in df_cached.columns
                and str(pd.to_datetime(df_cached["Date"]).max())[:10] >= max_price_date
            ):
                print(
                    f"  [FEAT CACHE] Loaded compact stationary features: "
                    f"{len(df_cached):,} rows x {df_cached.shape[1]} cols "
                    f"(-> {str(pd.to_datetime(df_cached['Date']).max())[:10]})"
                )
                return df_cached
        except Exception as exc:
            print(f"  [FEAT CACHE] Cache reload fallback: {exc}")

    print("  [FEAT BUILD] Computing stationary EGX features for all Saudi symbols...")
    mdf = history_cache["market_df"]
    sector_map = {
        str(r["symbol"]): str(r.get("sector") or "Unknown")
        for r in (history_cache.get("stocks_rows") or [])
    }
    industry_map = {
        str(r["symbol"]): str(r.get("industry") or "Unknown")
        for r in (history_cache.get("stocks_rows") or [])
    }
    raw_frames: List[pd.DataFrame] = []
    for sym, bdf in sorted(history_cache["bars_by_symbol"].items()):
        if bdf is None or len(bdf) < 120:
            continue
        sub = bdf.copy()
        sub.index = pd.to_datetime(sub.index)
        sub = sub.sort_index()
        df_ind = add_technical_indicators(sub)
        if df_ind.empty:
            continue
        df_ind = add_massive_features(df_ind)
        df_ind = add_market_context(df_ind, mdf)
        close_s = df_ind["Close"].astype(float).replace(0.0, np.nan)
        df_ind["ATR_pct"] = (df_ind.get("ATR_14", pd.Series(0.0, index=df_ind.index)) / close_s).fillna(0.02)
        if "SMA_50" in df_ind.columns:
            df_ind["SMA_50_Ratio"] = (close_s / df_ind["SMA_50"].replace(0.0, np.nan) - 1.0).fillna(0.0)
        if "EMA_50" in df_ind.columns:
            df_ind["EMA_50_Ratio"] = (close_s / df_ind["EMA_50"].replace(0.0, np.nan) - 1.0).fillna(0.0)
        df_ind["sector"] = sector_map.get(sym, "Unknown")
        df_ind["industry"] = industry_map.get(sym, "Unknown")
        df_ind["symbol"] = sym
        df_ind["Date"] = pd.to_datetime(df_ind.index)
        df_ind["stock_ret_1d"] = df_ind["Close"].astype(float).pct_change().fillna(0.0)
        raw_frames.append(df_ind.reset_index(drop=True))

    df_full = pd.concat(raw_frames, ignore_index=True)
    # Causal lagged sector relative strength (lagged by 1 session - zero same-day leakage!)
    sec_daily = (
        df_full.groupby(["Date", "sector"], as_index=False)["stock_ret_1d"]
        .mean()
        .rename(columns={"stock_ret_1d": "sec_ret"})
        .sort_values(["sector", "Date"])
    )
    sec_daily["sec_ret_lag1"] = sec_daily.groupby("sector")["sec_ret"].shift(1).fillna(0.0)
    df_full = df_full.merge(sec_daily[["Date", "sector", "sec_ret_lag1"]], on=["Date", "sector"], how="left")
    df_full["stock_ret_lag1"] = df_full.groupby("symbol")["stock_ret_1d"].shift(1).fillna(0.0)
    df_full["feat_sector_rel_strength"] = (df_full["stock_ret_lag1"] - df_full["sec_ret_lag1"].fillna(0.0)).clip(-0.3, 0.3)

    keep_cols = ["symbol", "Date", "Open", "High", "Low", "Close", "Volume", "ATR_14", "sector", "industry"]
    for c in df_full.columns:
        if c in keep_cols or c in ("stock_ret_1d", "stock_ret_lag1", "sec_ret_lag1"):
            continue
        if is_numeric_dtype(df_full[c]) and c not in STATIONARY_EXCLUDE_COLS:
            # Exclude raw price/volume level columns that break stationarity
            if any(bad in c for bad in ("_SMA", "SMA_", "EMA_", "BB_Upper", "BB_Lower", "BB_Middle", "Lag")) and "Ratio" not in c and "Price_vs" not in c:
                if c not in ("Amihud_SMA_10", "RSI_Lag1"):
                    continue
            if c in ("OBV", "VWAP"):
                continue
            keep_cols.append(c)
    keep_cols = list(dict.fromkeys(keep_cols))
    out = df_full[keep_cols].copy()
    for c in out.columns:
        if c in ("symbol", "sector", "industry"):
            out[c] = out[c].astype(str).astype("category")
        elif c != "Date" and is_numeric_dtype(out[c]):
            out[c] = pd.to_numeric(out[c], errors="coerce").astype(np.float32)

    os.makedirs(os.path.dirname(features_cache_path), exist_ok=True)
    out.to_pickle(features_cache_path)
    print(f"  [FEAT CACHE] Saved {len(out):,} rows x {out.shape[1]} cols -> {features_cache_path}")
    return out


class SaudiModelTrainer(ModelTrainer):
    """
    EGX-matched `ModelTrainer` pipeline adapted strictly for Saudi Tadawul (`TADAWUL`):
      - Full 2010->2026 Saudi price + TASI index history
      - Strictly stationary EGX indicators + `sector` (no raw Close/Volume/industry overfit)
      - Exact `StrictQualityLabeler` barriers (`next_open` entry, causal signal-bar ATR)
      - Exact `meta_labeling_system` + `.model_card.json` compatible with `backtest_radar`,
        `scan_ai_fast`, and `AdaptiveModelSelector`.
    """

    def __init__(
        self,
        supabase_url: str,
        supabase_key: str,
        history_cache: Optional[Dict[str, Any]] = None,
        progress_cb=None,
    ):
        super().__init__(
            exchange=EXCHANGE,
            supabase_url=supabase_url,
            supabase_key=supabase_key,
            progress_cb=progress_cb,
        )
        self.history_cache = history_cache or load_saudi_history_cached(supabase_url, supabase_key)
        self.categorical_features = ["sector"]

    def load_market_data(self):
        mdf = self.history_cache["market_df"].copy()
        self.market_df = mdf
        self.market_index_symbol = "TASI.INDX"
        self.market_index_loaded = True
        self._progress(
            f"Loaded TASI market index context ({len(mdf):,} rows: "
            f"{mdf.index.min().date()} -> {mdf.index.max().date()})"
        )

    def fetch_stock_prices(self, use_intraday: bool = False, timeframe: str = "1d") -> pd.DataFrame:
        return load_or_build_compact_features(self.history_cache)

    def select_predictors(self, df: pd.DataFrame, preset: str = "stationary") -> List[str]:
        cols: List[str] = []
        for c in df.columns:
            if c in STATIONARY_EXCLUDE_COLS:
                continue
            if c == "sector" or is_numeric_dtype(df[c]):
                cols.append(c)
        self.predictors = cols
        self.categorical_features = ["sector"] if "sector" in cols else []
        return self.predictors


def label_saudi_dataset(
    df_compact: pd.DataFrame,
    market_df: pd.DataFrame,
    params: TradingParameters,
) -> pd.DataFrame:
    """Apply EGX `StrictQualityLabeler` cleanly across all Saudi symbols."""
    labeler = StrictQualityLabeler(params)
    tparts: List[pd.DataFrame] = []
    for sym, grp in df_compact.groupby("symbol", observed=True):
        g = grp.sort_values("Date").copy()
        g = g.set_index("Date")
        res, _rej = labeler.label_training_data_strict(g, egx30_data=market_df, drop_labels=True)
        if len(res) < 10:
            continue
        res["symbol"] = sym
        res["Date"] = pd.to_datetime(res.index)
        tparts.append(res[["symbol", "Date", "Target"]])
    targets_df = pd.concat(tparts, ignore_index=True)
    labeled = df_compact.merge(targets_df, on=["symbol", "Date"], how="inner")
    return labeled.sort_values(["Date", "symbol"]).reset_index(drop=True)


def _prepare_model_matrix(
    df_slice: pd.DataFrame,
    feature_names: List[str],
    cat_cols: List[str],
    booster: Optional[lgb.Booster] = None,
) -> pd.DataFrame:
    X = df_slice.copy()
    for c in feature_names:
        if c not in X.columns:
            X[c] = "Unknown" if c in cat_cols else 0.0
    X = X[feature_names].copy()
    for c in cat_cols:
        if c in X.columns:
            X[c] = (
                X[c]
                .astype(str)
                .replace(["nan", "None", "", "0", "0.0"], "Unknown")
                .fillna("Unknown")
                .astype("category")
            )
    non_cat = [c for c in X.columns if c not in set(cat_cols)]
    for c in non_cat:
        if not is_numeric_dtype(X[c]):
            X[c] = pd.to_numeric(X[c], errors="coerce")
    X = X.replace([np.inf, -np.inf], np.nan)
    if non_cat:
        X[non_cat] = X[non_cat].fillna(0.0).astype(np.float32)
    if booster is not None and cat_cols:
        X = align_pandas_categories_to_booster(
            X,
            cat_cols=cat_cols,
            booster=booster,
            cat_cols_order=cat_cols,
        )
    return X


def _score_meta_system_df(
    artifact: Dict[str, Any],
    df_slice: pd.DataFrame,
    return_components: bool = False,
) -> Any:
    """
    Score rows with exact `_MetaLabelingClassifier(return_raw_prob=False)` runtime parity
    so `backtest_radar.reconstruct_meta_model` and `scan_ai_fast._load_model` match identically.
    """
    from api.stock_ai import _LgbmBoosterClassifier, _MetaLabelingClassifier, _PcaTransformer

    pm = artifact["primary_model"]
    booster = lgb.Booster(model_str=pm["model_str"])
    pca_transformer = None
    if pm.get("pca") is not None and pm.get("scaler") is not None and pm.get("pca_features"):
        pca_transformer = _PcaTransformer(pm["pca"], pm["scaler"], pm["pca_features"])

    primary_clf = _LgbmBoosterClassifier(booster, 0.5, pca_transformer=pca_transformer)
    meta_clf = _MetaLabelingClassifier(
        primary_model=primary_clf,
        meta_model=artifact["meta_model"],
        meta_feature_names=artifact["meta_feature_names"],
        meta_threshold=float(artifact.get("meta_threshold", 0.50)),
        return_raw_prob=False,
    )

    f_names = list(pm["feature_names"])
    pca_feats = list(pm.get("pca_features") or [])
    raw_needed = [c for c in f_names if not str(c).startswith("PCA_Momentum_")] + pca_feats if pca_feats else f_names
    cat_cols = [c for c in (pm.get("categorical_features") or []) if c in raw_needed]

    X = _prepare_model_matrix(df_slice, raw_needed, cat_cols, booster=booster)
    filtered_probs = np.asarray(meta_clf.predict_proba(X)[:, 1], dtype=float)
    if not return_components:
        return filtered_probs

    primary_probs = np.asarray(primary_clf.predict_proba(X)[:, 1], dtype=float)
    mf = [c for c in artifact["meta_feature_names"] if c != "primary_prob"]
    X_meta = pd.DataFrame(index=df_slice.index)
    for c in mf:
        X_meta[c] = pd.to_numeric(df_slice[c], errors="coerce").fillna(0.0) if c in df_slice.columns else 0.0
    X_meta = X_meta.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    X_meta["primary_prob"] = primary_probs
    cols = [c for c in artifact["meta_feature_names"] if c in X_meta.columns]
    X_meta = X_meta[cols]
    meta_probs = np.asarray(artifact["meta_model"].predict_proba(X_meta)[:, 1], dtype=float)
    return filtered_probs, primary_probs, meta_probs


def _build_bars_dict(
    bars_by_symbol: Dict[str, pd.DataFrame],
    min_date: Optional[str] = None,
    max_date: Optional[str] = None,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, int]]]:
    bars_dict: Dict[str, List[Dict[str, Any]]] = {}
    date_pos: Dict[str, Dict[str, int]] = {}
    for sym, bdf in bars_by_symbol.items():
        if bdf is None or bdf.empty:
            continue
        sub = bdf
        if min_date:
            sub = sub[sub.index >= pd.Timestamp(min_date)]
        if max_date:
            sub = sub[sub.index <= pd.Timestamp(max_date)]
        if sub.empty:
            continue
        d_strs = sub.index.strftime("%Y-%m-%d").tolist()
        o = sub["Open"].astype(float).values
        h = sub["High"].astype(float).values
        l = sub["Low"].astype(float).values
        c = sub["Close"].astype(float).values
        v = sub["Volume"].astype(float).values
        valid = (c > 0) & (l <= o) & (o <= h) & (l <= c) & (c <= h)
        recs: List[Dict[str, Any]] = []
        pos_map: Dict[str, int] = {}
        for i in range(len(d_strs)):
            if not valid[i]:
                continue
            pos_map[d_strs[i]] = len(recs)
            recs.append({
                "date": d_strs[i],
                "open": float(o[i]),
                "high": float(h[i]),
                "low": float(l[i]),
                "close": float(c[i]),
                "volume": float(v[i]),
            })
        if recs:
            bars_dict[sym] = recs
            date_pos[sym] = pos_map
    return bars_dict, date_pos


def _profit_protection_callback(entry_price: float, bars: List[Dict[str, Any]], bar_index: int, current_stop: Optional[float]):
    if bar_index < 0:
        return None
    return profit_protection_stop(
        entry=entry_price,
        bars=bars[: bar_index + 1],
        current_stop=current_stop,
        trigger_pct=5.0,
        atr_multiple=2.0,
        trend_atr_multiple=2.5,
        atr_window=14,
        minimum_distance_pct=3.0,
    )


def _healthy_tasi_dates(market_df: pd.DataFrame) -> set:
    mkt_close = market_df["close"].astype(float)
    mkt_sma20 = mkt_close.rolling(20, min_periods=1).mean()
    mkt_ret1 = mkt_close.pct_change().fillna(0.0)
    mkt_ret5 = mkt_close.pct_change(5).fillna(0.0)
    return {
        ts.strftime("%Y-%m-%d")
        for ts in market_df.index[(mkt_close >= mkt_sma20 * 0.99) & (mkt_ret1 > -0.02) & (mkt_ret5 > -0.02)]
    }


def _simulate_slice_trades(
    df_slice: pd.DataFrame,
    primary_probs: np.ndarray,
    meta_probs: np.ndarray,
    primary_threshold: float,
    meta_threshold: float,
    bars_dict: Dict[str, List[Dict[str, Any]]],
    date_pos: Dict[str, Dict[str, int]],
    healthy_dates: set,
    barrier_mode: str,
    target_pct: float,
    stop_loss_pct: float,
    max_sessions: int,
    top_k_per_day: int = 3,
    market_regime_filter: bool = True,
) -> Dict[str, Any]:
    mask = (primary_probs >= primary_threshold) & (meta_probs >= meta_threshold)
    if not np.any(mask):
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "total_return_pct": 0.0, "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
            "avg_pl_pct": 0.0, "max_drawdown_pct": 0.0, "signals_raw": 0,
        }

    scored = df_slice.loc[mask, ["symbol", "Date", "Close", "ATR_14", "CMF_20", "MM_Distribution", "RSI", "R_VOL", "ADX_14"]].copy()
    scored["Date_str"] = pd.to_datetime(scored["Date"]).dt.strftime("%Y-%m-%d")
    scored["p_prob"] = primary_probs[mask]
    scored["m_prob"] = meta_probs[mask]
    scored["score"] = 0.65 * scored["p_prob"] + 0.35 * scored["m_prob"]

    trades: List[Dict[str, Any]] = []
    cooldown_until: Dict[str, str] = {}
    for d_str, day_df in scored.sort_values(["Date_str", "score"], ascending=[True, False]).groupby("Date_str", sort=True):
        if market_regime_filter and d_str not in healthy_dates:
            continue
        day_picks = 0
        for _, row in day_df.iterrows():
            if day_picks >= top_k_per_day:
                break
            sym = str(row["symbol"])
            if sym in cooldown_until and d_str <= cooldown_until[sym]:
                continue
            if float(row.get("MM_Distribution") or 0.0) > 0.35 or float(row.get("CMF_20") or 0.0) < -0.02 or float(row.get("RSI") or 50.0) > 78.0:
                continue
            close_v = float(row["Close"])
            atr_v = float(row["ATR_14"]) if np.isfinite(row["ATR_14"]) and row["ATR_14"] > 0 else close_v * 0.02
            if close_v <= 0 or sym not in bars_dict:
                continue
            pos = date_pos.get(sym, {}).get(d_str)
            if pos is None or pos + 2 >= len(bars_dict[sym]):
                continue
            if barrier_mode == "atr_multiplier":
                target_v = round(close_v + target_pct * atr_v, 3 if close_v < 2.0 else 2)
                stop_v = round(close_v - stop_loss_pct * atr_v, 3 if close_v < 2.0 else 2)
            else:
                target_v = round(close_v * (1.0 + target_pct), 3 if close_v < 2.0 else 2)
                stop_v = round(close_v * (1.0 - stop_loss_pct), 3 if close_v < 2.0 else 2)
            if stop_v <= 0 or target_v <= close_v or (target_v - close_v) / max(close_v - stop_v, 1e-6) < 1.5:
                continue

            outcome = evaluate_bars(
                entry=close_v,
                target=target_v,
                stop=stop_v,
                bars=bars_dict[sym],
                entry_date=d_str,
                cursor=d_str,
                max_sessions=max_sessions,
                profit_protection=_profit_protection_callback,
            )
            if outcome["status"] in ("win", "loss"):
                pl_pct = float(outcome["profit_loss_pct"])
                trades.append({
                    "symbol": sym,
                    "entry_date": d_str,
                    "closed_on": outcome["closed_on"],
                    "status": outcome["status"],
                    "pl_pct": pl_pct,
                    "prob": float(row["p_prob"]),
                    "exit_reason": outcome["exit_reason"],
                })
                cooldown_until[sym] = str(outcome["closed_on"])
                day_picks += 1

    if not trades:
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "total_return_pct": 0.0, "avg_win_pct": 0.0, "avg_loss_pct": 0.0,
            "avg_pl_pct": 0.0, "max_drawdown_pct": 0.0, "signals_raw": int(mask.sum()),
        }

    wins = [t["pl_pct"] for t in trades if t["status"] == "win"]
    losses = [t["pl_pct"] for t in trades if t["status"] == "loss"]
    gross_win = float(sum(max(0.0, w) for w in wins))
    gross_loss = float(sum(abs(min(0.0, l)) for l in losses))
    pf = round(gross_win / gross_loss, 3) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)

    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: x["entry_date"]):
        equity *= (1.0 + 0.10 * (t["pl_pct"] / 100.0))
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak * 100.0)

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100.0, 2),
        "profit_factor": pf,
        "total_return_pct": round((equity - 1.0) * 100.0, 2),
        "avg_win_pct": round(float(np.mean(wins)), 2) if wins else 0.0,
        "avg_loss_pct": round(float(np.mean(losses)), 2) if losses else 0.0,
        "avg_pl_pct": round(float(np.mean([t["pl_pct"] for t in trades])), 2),
        "max_drawdown_pct": round(max_dd, 2),
        "signals_raw": int(mask.sum()),
    }


def evaluate_oos_lockbox_backtest(
    artifact: Dict[str, Any],
    bars_by_symbol: Dict[str, pd.DataFrame],
    market_df: pd.DataFrame,
    df_test_raw_features: pd.DataFrame,
    threshold: float,
    target_atr_mult: float = 3.0,
    stop_atr_mult: float = 1.5,
    max_sessions: int = 20,
    top_k_per_day: int = 3,
    market_regime_filter: bool = True,
    barrier_mode: str = "atr_multiplier",
    meta_threshold_override: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Strictly causal out-of-sample lockbox trade simulation across unseen test dates
    using `api/recommendation_policy.evaluate_bars` + `profit_protection_stop`.
    """
    _filt, primary_probs, meta_probs = _score_meta_system_df(artifact, df_test_raw_features, return_components=True)
    m_th = float(meta_threshold_override if meta_threshold_override is not None else artifact.get("meta_threshold", 0.50))
    bars_dict, date_pos = _build_bars_dict(bars_by_symbol)
    healthy_dates = _healthy_tasi_dates(market_df)
    return _simulate_slice_trades(
        df_slice=df_test_raw_features,
        primary_probs=primary_probs,
        meta_probs=meta_probs,
        primary_threshold=float(threshold),
        meta_threshold=m_th,
        bars_dict=bars_dict,
        date_pos=date_pos,
        healthy_dates=healthy_dates,
        barrier_mode=barrier_mode,
        target_pct=float(target_atr_mult),
        stop_loss_pct=float(stop_atr_mult),
        max_sessions=int(max_sessions),
        top_k_per_day=top_k_per_day,
        market_regime_filter=market_regime_filter,
    )


def _optimize_dual_thresholds_on_dev(
    df_dev: pd.DataFrame,
    y_dev: np.ndarray,
    p_dev: np.ndarray,
    m_dev: np.ndarray,
    p_tune_ref: np.ndarray,
    m_tune_ref: np.ndarray,
    bars_by_symbol: Dict[str, pd.DataFrame],
    market_df: pd.DataFrame,
    barrier_mode: str,
    target_pct: float,
    stop_loss_pct: float,
    look_forward_days: int,
) -> Tuple[float, float, Dict[str, Any]]:
    """
    Choose `(optimal_threshold, meta_threshold)` strictly on pre-test `dev_cal`
    (`2022-11 -> 2023-06`) optimizing label precision AND trade Profit Factor.
    """
    bars_dict, date_pos = _build_bars_dict(bars_by_symbol, max_date="2023-07-01")
    healthy_dates = _healthy_tasi_dates(market_df)
    base_rate = float(np.mean(y_dev))

    best_score = -1e9
    best_p_th = float(np.quantile(p_tune_ref, 0.85))
    best_m_th = float(np.quantile(m_tune_ref, 0.60))
    best_stats: Dict[str, Any] = {}

    for p_q in (0.75, 0.80, 0.85, 0.88):
        p_th = float(np.quantile(p_tune_ref, p_q))
        for m_q in (0.50, 0.60, 0.70):
            m_th = float(np.quantile(m_tune_ref, m_q))
            mask = (p_dev >= p_th) & (m_dev >= m_th)
            sig_n = int(mask.sum())
            if sig_n < 150:
                continue
            prec = float(y_dev[mask].mean())
            sim = _simulate_slice_trades(
                df_slice=df_dev,
                primary_probs=p_dev,
                meta_probs=m_dev,
                primary_threshold=p_th,
                meta_threshold=m_th,
                bars_dict=bars_dict,
                date_pos=date_pos,
                healthy_dates=healthy_dates,
                barrier_mode=barrier_mode,
                target_pct=target_pct,
                stop_loss_pct=stop_loss_pct,
                max_sessions=look_forward_days,
                top_k_per_day=3,
                market_regime_filter=True,
            )
            if sim["trades"] < 25:
                continue
            score = (
                (prec - base_rate) * 3.0
                + min(sim["profit_factor"], 4.0) * 0.25
                + (sim["win_rate"] / 100.0) * 0.6
            )
            if score > best_score:
                best_score = score
                best_p_th = round(p_th, 4)
                best_m_th = round(m_th, 4)
                best_stats = {
                    "dev_precision": round(prec, 4),
                    "dev_base_rate": round(base_rate, 4),
                    "dev_signals": sig_n,
                    "dev_sim_trades": sim["trades"],
                    "dev_sim_wr": sim["win_rate"],
                    "dev_sim_pf": sim["profit_factor"],
                    "p_q": p_q,
                    "m_q": m_q,
                }

    if not best_stats:
        best_stats = {
            "dev_precision": round(float(y_dev[(p_dev >= best_p_th) & (m_dev >= best_m_th)].mean()), 4),
            "dev_base_rate": round(base_rate, 4),
        }
    return best_p_th, best_m_th, best_stats



def _run_purged_walk_forward_stationary(
    df_dev: pd.DataFrame,
    feature_cols: List[str],
    cat_cols: List[str],
    n_splits: int = 5,
    embargo_days: int = 25,
) -> Tuple[List[Dict[str, Any]], float]:
    """Run 5 expanding purged chronological walk-forward folds strictly within pre-lockbox dev data."""
    dates = pd.to_datetime(df_dev["Date"]).sort_values().unique()
    if len(dates) < 400:
        return [], 0.0

    # Reserve first 35% of timeline for initial fold training, split remaining 65% into n_splits windows
    start_idx = int(len(dates) * 0.35)
    fold_span = max(60, (len(dates) - start_idx) // n_splits)
    results: List[Dict[str, Any]] = []
    f1s: List[float] = []

    for i in range(n_splits):
        val_start_pos = start_idx + i * fold_span
        val_end_pos = len(dates) - 1 if i == n_splits - 1 else min(len(dates) - 1, val_start_pos + fold_span - 1)
        if val_start_pos <= embargo_days + 50 or val_end_pos <= val_start_pos:
            continue
        train_end_date = pd.Timestamp(dates[val_start_pos - embargo_days])
        val_start_date = pd.Timestamp(dates[val_start_pos])
        val_end_date = pd.Timestamp(dates[val_end_pos])

        d_series = pd.to_datetime(df_dev["Date"])
        tr_mask = d_series <= train_end_date
        va_mask = (d_series >= val_start_date) & (d_series <= val_end_date)
        if tr_mask.sum() < 5000 or va_mask.sum() < 2000:
            continue

        X_tr = _prepare_model_matrix(df_dev.loc[tr_mask], feature_cols, cat_cols)
        y_tr = df_dev.loc[tr_mask, "Target"].astype(int).values
        X_va = _prepare_model_matrix(df_dev.loc[va_mask], feature_cols, cat_cols)
        y_va = df_dev.loc[va_mask, "Target"].astype(int).values

        fold_clf = lgb.LGBMClassifier(
            n_estimators=500,
            learning_rate=0.025,
            num_leaves=23,
            max_depth=5,
            min_child_samples=150,
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.7,
            reg_alpha=2.0,
            reg_lambda=5.0,
            cat_smooth=40.0,
            random_state=42 + i,
            n_jobs=-1,
            verbose=-1,
        )
        fold_clf.fit(X_tr, y_tr)
        probs = np.asarray(fold_clf.predict_proba(X_va)[:, 1], dtype=float)
        th = float(np.quantile(probs, 0.85))
        preds = (probs >= th).astype(int)
        prec = float(precision_score(y_va, preds, zero_division=0))
        rec = float(recall_score(y_va, preds, zero_division=0))
        f1_v = float(f1_score(y_va, preds, zero_division=0))
        auc_v = float(roc_auc_score(y_va, probs)) if len(np.unique(y_va)) > 1 else 0.5
        f1s.append(f1_v)
        results.append({
            "split_index": len(results),
            "train_period": f"{pd.Timestamp(dates[0]).strftime('%Y-%m-%d')} to {train_end_date.strftime('%Y-%m-%d')}",
            "test_period": f"{val_start_date.strftime('%Y-%m-%d')} to {val_end_date.strftime('%Y-%m-%d')}",
            "train_samples": int(tr_mask.sum()),
            "test_samples": int(va_mask.sum()),
            "train_positive_rate": float(np.mean(y_tr)),
            "test_positive_rate": float(np.mean(y_va)),
            "precision": prec,
            "recall": rec,
            "f1": f1_v,
            "auc": auc_v,
        })

    avg_f1 = float(np.mean(f1s)) if f1s else 0.0
    return results, avg_f1


def train_saudi_meta_model(
    history_cache: Dict[str, Any],
    model_filename: str,
    target_pct: float,
    stop_loss_pct: float,
    look_forward_days: int,
    barrier_mode: str = "atr_multiplier",
    n_estimators: int = 1200,
    learning_rate: float = 0.02,
    patience: int = 70,
    df_compact: Optional[pd.DataFrame] = None,
) -> Tuple[str, Dict[str, Any], pd.DataFrame]:
    """
    Train an EGX-matched stationary `meta_labeling_system` on full 2010->2026 Saudi history
    using purged chronological splits (zero test lockbox contamination) and save `.pkl`,
    booster `.txt`, and `AdaptiveModelSelector`-ready `.model_card.json`.
    """
    t0 = time.time()
    base_url, service_key = get_saudi_credentials()
    trainer = SaudiModelTrainer(base_url, service_key, history_cache=history_cache)
    trainer.load_market_data()

    if df_compact is None:
        df_compact = load_or_build_compact_features(history_cache)

    params = TradingParameters(
        entry_mode="next_open",
        look_forward_days=int(look_forward_days),
        barrier_mode=barrier_mode,
        target_pct=float(target_pct),
        stop_loss_pct=float(stop_loss_pct),
        min_history_needed=120,
        warmup_bars=120,
        require_volume_confirmation=False,
        min_volume_ratio=0.8,
    )
    trainer.params = params
    trainer.fundamentals_loaded = True

    df_labeled = label_saudi_dataset(df_compact, history_cache["market_df"], params)
    feature_cols = trainer.select_predictors(df_labeled, preset="stationary")
    cat_cols = list(trainer.categorical_features)
    meta_feature_names = [c for c in META_CORE_CANDIDATES if c in feature_cols]

    # Purged Chronological Splits (strictly zero leakage into 2023-08 -> 2026-11 test lockbox!)
    d = pd.to_datetime(df_labeled["Date"])
    train_mask = d <= pd.Timestamp("2019-11-30")
    ea_mask = (d >= pd.Timestamp("2020-01-01")) & (d <= pd.Timestamp("2021-05-31"))
    tune_fit_mask = (d >= pd.Timestamp("2021-07-01")) & (d <= pd.Timestamp("2022-09-30"))
    dev_cal_mask = (d >= pd.Timestamp("2022-11-01")) & (d <= pd.Timestamp("2023-06-30"))
    tune_all_mask = (d >= pd.Timestamp("2021-07-01")) & (d <= pd.Timestamp("2023-06-30"))
    test_mask = d >= pd.Timestamp("2023-08-01")
    dev_full_mask = d <= pd.Timestamp("2023-06-30")

    wf_results, avg_purged_f1 = _run_purged_walk_forward_stationary(
        df_labeled.loc[dev_full_mask], feature_cols, cat_cols, n_splits=5, embargo_days=25
    )
    trainer.wf_splits_results = wf_results

    X_tr = _prepare_model_matrix(df_labeled.loc[train_mask], feature_cols, cat_cols)
    y_tr = df_labeled.loc[train_mask, "Target"].astype(int).values
    X_ea = _prepare_model_matrix(df_labeled.loc[ea_mask], feature_cols, cat_cols)
    y_ea = df_labeled.loc[ea_mask, "Target"].astype(int).values
    X_tf = _prepare_model_matrix(df_labeled.loc[tune_fit_mask], feature_cols, cat_cols)
    y_tf = df_labeled.loc[tune_fit_mask, "Target"].astype(int).values
    X_dc = _prepare_model_matrix(df_labeled.loc[dev_cal_mask], feature_cols, cat_cols)
    y_dc = df_labeled.loc[dev_cal_mask, "Target"].astype(int).values
    X_tu = _prepare_model_matrix(df_labeled.loc[tune_all_mask], feature_cols, cat_cols)
    y_tu = df_labeled.loc[tune_all_mask, "Target"].astype(int).values

    primary_model = lgb.LGBMClassifier(
        n_estimators=int(n_estimators),
        learning_rate=float(learning_rate),
        num_leaves=23,
        max_depth=5,
        min_child_samples=150,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.7,
        reg_alpha=2.0,
        reg_lambda=5.0,
        cat_smooth=40.0,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    primary_model.fit(
        X_tr,
        y_tr,
        eval_set=[(X_ea, y_ea)],
        callbacks=[lgb.early_stopping(int(patience), verbose=False)],
    )

    p_tf = np.asarray(primary_model.predict_proba(X_tf)[:, 1], dtype=float)
    p_dc = np.asarray(primary_model.predict_proba(X_dc)[:, 1], dtype=float)
    p_tu = np.asarray(primary_model.predict_proba(X_tu)[:, 1], dtype=float)

    def _build_meta_df(df_sub: pd.DataFrame, p_arr: np.ndarray) -> pd.DataFrame:
        xm = pd.DataFrame(index=df_sub.index)
        for c in meta_feature_names:
            xm[c] = pd.to_numeric(df_sub[c], errors="coerce").fillna(0.0)
        xm = xm.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        xm["primary_prob"] = p_arr
        return xm[meta_feature_names + ["primary_prob"]]

    Xm_tf = _build_meta_df(df_labeled.loc[tune_fit_mask], p_tf)
    Xm_dc = _build_meta_df(df_labeled.loc[dev_cal_mask], p_dc)
    Xm_tu = _build_meta_df(df_labeled.loc[tune_all_mask], p_tu)

    # Calibrated shallow XGBoost Meta-Labeler (early-stopped on `dev_cal`)
    dev_meta = xgb.XGBClassifier(
        n_estimators=400,
        max_depth=2,
        min_child_weight=100,
        learning_rate=0.02,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=10.0,
        reg_alpha=3.0,
        scale_pos_weight=1.0,
        objective="binary:logistic",
        eval_metric="logloss",
        early_stopping_rounds=40,
        random_state=42,
        n_jobs=-1,
    )
    dev_meta.fit(Xm_tf, y_tf, eval_set=[(Xm_dc, y_dc)], verbose=False)
    m_dc = np.asarray(dev_meta.predict_proba(Xm_dc)[:, 1], dtype=float)
    m_tu_ref = np.asarray(dev_meta.predict_proba(Xm_tu)[:, 1], dtype=float)

    opt_p_th, meta_th, dev_stats = _optimize_dual_thresholds_on_dev(
        df_dev=df_labeled.loc[dev_cal_mask],
        y_dev=y_dc,
        p_dev=p_dc,
        m_dev=m_dc,
        p_tune_ref=p_tu,
        m_tune_ref=m_tu_ref,
        bars_by_symbol=history_cache["bars_by_symbol"],
        market_df=history_cache["market_df"],
        barrier_mode=barrier_mode,
        target_pct=float(target_pct),
        stop_loss_pct=float(stop_loss_pct),
        look_forward_days=int(look_forward_days),
    )

    best_meta_rounds = max(60, int(getattr(dev_meta, "best_iteration", 120) or 120) + 1)
    meta_model = xgb.XGBClassifier(
        n_estimators=best_meta_rounds,
        max_depth=2,
        min_child_weight=100,
        learning_rate=0.02,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=10.0,
        reg_alpha=3.0,
        scale_pos_weight=1.0,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    meta_model.fit(Xm_tu, y_tu, verbose=False)

    best_it = getattr(primary_model, "best_iteration_", None)
    if isinstance(best_it, int) and best_it <= 0:
        best_it = None

    meta_feature_names_with_prob = list(meta_feature_names) + ["primary_prob"]
    save_metadata: Dict[str, Any] = {
        "target_pct": float(target_pct),
        "stop_loss_pct": float(stop_loss_pct),
        "barrier_mode": barrier_mode,
        "barrierMode": barrier_mode,
        "look_forward_days": int(look_forward_days),
        "use_volatility_label": False,
        "feature_preset": "stationary",
        "featurePreset": "stationary",
        "n_estimators": int(n_estimators),
        "best_iteration": best_it,
        "bestIteration": best_it,
        "learning_rate": float(learning_rate),
        "training_samples": int(train_mask.sum()),
        "trainingSamples": int(train_mask.sum()),
        "use_intraday": False,
        "timeframe": "1d",
        "training_strategy": "purged_stationary_meta",
        "eval_metric": "logloss",
        "purged_cv_f1": avg_purged_f1,
        "has_meta_labeling": True,
        "optimal_threshold": float(opt_p_th),
        "meta_threshold": float(meta_th),
        "buyThreshold": float(opt_p_th),
        "precision": dev_stats.get("dev_precision", 0.5),
        "auc": 0.65,
    }

    saved_path = trainer.save_meta_labeling_system(
        primary_model=primary_model,
        meta_model=meta_model,
        filename=model_filename,
        metadata=save_metadata,
        meta_threshold=float(meta_th),
        meta_feature_names=meta_feature_names_with_prob,
    )

    with open(saved_path, "rb") as f:
        artifact = pickle.load(f)

    # Single honest OOS evaluation on UNSEEN lockbox (2023-08 -> 2026-11)
    df_test_slice = df_labeled.loc[test_mask].copy()
    filtered_probs, primary_test_probs, meta_test_probs = _score_meta_system_df(
        artifact, df_test_slice, return_components=True
    )
    y_test_arr = df_test_slice["Target"].astype(int).values
    test_preds = (filtered_probs >= float(opt_p_th)).astype(int)

    oos_p_auc = float(roc_auc_score(y_test_arr, primary_test_probs)) if len(np.unique(y_test_arr)) > 1 else 0.5
    oos_m_auc = float(roc_auc_score(y_test_arr, meta_test_probs)) if len(np.unique(y_test_arr)) > 1 else 0.5
    oos_ap = float(average_precision_score(y_test_arr, primary_test_probs)) if len(np.unique(y_test_arr)) > 1 else 0.0
    oos_prec = float(precision_score(y_test_arr, test_preds, zero_division=0))
    oos_rec = float(recall_score(y_test_arr, test_preds, zero_division=0))
    oos_f1 = float(f1_score(y_test_arr, test_preds, zero_division=0))
    oos_brier = float(brier_score_loss(y_test_arr, np.clip(primary_test_probs, 0.0, 1.0)))
    oos_base_rate = float(np.mean(y_test_arr))
    q90 = float(np.quantile(primary_test_probs, 0.90))
    top_decile_prec = float(y_test_arr[primary_test_probs >= q90].mean()) if np.any(primary_test_probs >= q90) else oos_prec

    bt_res = evaluate_oos_lockbox_backtest(
        artifact=artifact,
        bars_by_symbol=history_cache["bars_by_symbol"],
        market_df=history_cache["market_df"],
        df_test_raw_features=df_test_slice,
        threshold=float(opt_p_th),
        target_atr_mult=float(target_pct),
        stop_atr_mult=float(stop_loss_pct),
        max_sessions=int(look_forward_days),
        top_k_per_day=3,
        market_regime_filter=True,
        barrier_mode=barrier_mode,
        meta_threshold_override=float(meta_th),
    )

    train_period = f"{pd.to_datetime(df_labeled.loc[train_mask, 'Date']).min().strftime('%Y-%m-%d')} -> {pd.to_datetime(df_labeled.loc[tune_all_mask, 'Date']).max().strftime('%Y-%m-%d')}"
    test_period = f"{pd.to_datetime(df_test_slice['Date']).min().strftime('%Y-%m-%d')} -> {pd.to_datetime(df_test_slice['Date']).max().strftime('%Y-%m-%d')}"

    summary_metrics = {
        "precision": round(oos_prec, 4),
        "recall": round(oos_rec, 4),
        "f1": round(oos_f1, 4),
        "auc": round(oos_p_auc, 4),
        "meta_auc": round(oos_m_auc, 4),
        "average_precision": round(oos_ap, 4),
        "brier_score": round(oos_brier, 4),
        "base_rate": round(oos_base_rate, 4),
        "top_decile_precision": round(top_decile_prec, 4),
        "optimal_threshold": float(opt_p_th),
        "meta_threshold": float(meta_th),
        "signals_in_test": int(test_preds.sum()),
        "test_samples": int(len(y_test_arr)),
        "train_samples": int(train_mask.sum()),
        "tune_samples": int(tune_all_mask.sum()),
        "test_period": test_period,
        "train_period": train_period,
        "walk_forward_summary": artifact.get("walk_forward_summary") or {},
        "oos_backtest": bt_res,
        "dev_calibration": dev_stats,
        "duration_s": round(time.time() - t0, 1),
    }

    artifact["precision"] = summary_metrics["precision"]
    artifact["recall"] = summary_metrics["recall"]
    artifact["f1"] = summary_metrics["f1"]
    artifact["auc"] = summary_metrics["auc"]
    artifact["optimal_threshold"] = float(opt_p_th)
    artifact["meta_threshold"] = float(meta_th)
    artifact["oos_backtest"] = bt_res
    artifact["test_period"] = test_period
    artifact["train_period"] = train_period
    artifact["primary_model"]["optimal_threshold"] = float(opt_p_th)
    with open(saved_path, "wb") as f:
        pickle.dump(artifact, f)

    card_path = saved_path + ".model_card.json"
    with open(card_path, "r", encoding="utf-8") as cf:
        card = json.load(cf)
    card.update({
        "exchange": EXCHANGE,
        "country": COUNTRY,
        "target_pct": float(target_pct),
        "stop_loss_pct": float(stop_loss_pct),
        "barrier_mode": barrier_mode,
        "look_forward_days": int(look_forward_days),
        "buyThreshold": float(opt_p_th),
        "meta_threshold": float(meta_th),
        "optimal_threshold": float(opt_p_th),
        "feature_names": list(feature_cols),
        "meta_feature_names": meta_feature_names_with_prob,
        "precision": summary_metrics["precision"],
        "recall": summary_metrics["recall"],
        "f1": summary_metrics["f1"],
        "auc": summary_metrics["auc"],
        "meta_auc": summary_metrics["meta_auc"],
        "oos_backtest": bt_res,
        "train_period": train_period,
        "test_period": test_period,
    })
    card["training"]["metrics"] = {
        "precision": summary_metrics["precision"],
        "recall": summary_metrics["recall"],
        "f1": summary_metrics["f1"],
        "auc": summary_metrics["auc"],
        "meta_auc": summary_metrics["meta_auc"],
        "average_precision": summary_metrics["average_precision"],
        "brier_score": summary_metrics["brier_score"],
        "base_rate": summary_metrics["base_rate"],
        "top_decile_precision": summary_metrics["top_decile_precision"],
    }
    with open(card_path, "w", encoding="utf-8") as cf:
        json.dump(card, cf, indent=2)

    print(
        f"  [DONE] {model_filename} | OOS({test_period}) "
        f"AUC={oos_p_auc:.4f} (metaAUC={oos_m_auc:.4f}, base={oos_base_rate:.3f}) | "
        f"P={oos_prec:.3f} (top10%={top_decile_prec:.3f}) | th=({opt_p_th:.3f}/{meta_th:.3f}) | "
        f"OOS_SIM: {bt_res['trades']} tr WR={bt_res['win_rate']}% PF={bt_res['profit_factor']} "
        f"Ret={bt_res['total_return_pct']}% DD={bt_res['max_drawdown_pct']}% | {summary_metrics['duration_s']}s",
        flush=True,
    )
    return saved_path, summary_metrics, df_compact


def train_all_saudi_models(force_refresh: bool = False) -> Dict[str, Any]:
    """Train both EGX-matched Saudi Meta-Labeling systems: `model_TADAWUL.pkl` and `KING_TASI.pkl`."""
    history_cache = load_saudi_history_cached(force_refresh=force_refresh)
    df_compact = load_or_build_compact_features(history_cache, force_rebuild=force_refresh)

    tad_path, tad_metrics, _ = train_saudi_meta_model(
        history_cache=history_cache,
        model_filename="model_TADAWUL.pkl",
        target_pct=3.0,
        stop_loss_pct=1.5,
        look_forward_days=20,
        barrier_mode="atr_multiplier",
        df_compact=df_compact,
    )
    king_path, king_metrics, _ = train_saudi_meta_model(
        history_cache=history_cache,
        model_filename="KING_TASI.pkl",
        target_pct=0.08,
        stop_loss_pct=0.04,
        look_forward_days=20,
        barrier_mode="percent",
        df_compact=df_compact,
    )
    return {
        "model_TADAWUL": {"path": tad_path, "metrics": tad_metrics},
        "KING_TASI": {"path": king_path, "metrics": king_metrics},
    }


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if "--train-all" in sys.argv:
        train_all_saudi_models(force_refresh="--refresh" in sys.argv)
    else:
        cache = load_saudi_history_cached()
        print(
            f"Saudi cache ready: {sum(len(v) for v in cache['bars_by_symbol'].values()):,} rows "
            f"({cache['min_price_date']} -> {cache['max_price_date']}), "
            f"{len(cache['market_index_rows']):,} TASI rows."
        )
