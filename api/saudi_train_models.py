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
from api.recommendation_policy import evaluate_bars
from api.stock_ai import add_technical_indicators
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
EXCHANGE = "TADAWUL"
COUNTRY = "Saudi Arabia"

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


class SaudiModelTrainer(ModelTrainer):
    """
    Exact Egyptian `ModelTrainer` pipeline adapted strictly for Saudi Tadawul (`TADAWUL`),
    using cached full 2010->2026 Saudi history, `stocks` + `stock_fundamentals` sector/industry
    metadata, and `StrictQualityLabeler` (identical to EGX).
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
        frames: List[pd.DataFrame] = []
        bars_map: Dict[str, pd.DataFrame] = self.history_cache["bars_by_symbol"]
        for sym, df in sorted(bars_map.items()):
            if df is None or df.empty:
                continue
            part = df.reset_index().rename(columns={
                "index": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })
            if "date" not in part.columns and "Date" in part.columns:
                part = part.rename(columns={"Date": "date"})
            part["symbol"] = sym
            frames.append(part[["symbol", "date", "open", "high", "low", "close", "volume"]])
        out = pd.concat(frames, ignore_index=True)
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.dropna(subset=["date"]).sort_values(["symbol", "date"]).reset_index(drop=True)
        self._progress(
            f"Loaded {len(out):,} full-history Saudi bars across {out['symbol'].nunique()} symbols "
            f"({out['date'].min().date()} -> {out['date'].max().date()})"
        )
        return out

    @staticmethod
    def _process_single_symbol(params):
        """Worker identically matching EGX `_process_single_symbol` including `StrictQualityLabeler`."""
        try:
            (
                sym,
                df_sym,
                market_df,
                target_pct,
                stop_loss_pct,
                look_forward_days,
                use_vol_label,
                min_history,
                barrier_mode,
                exchange,
                t_params,
            ) = params

            manager = FeatureEngineeringManager(t_params)
            df_sym = df_sym.copy()
            df_sym["date"] = pd.to_datetime(df_sym["date"], errors="coerce")
            df_sym = df_sym.dropna(subset=["date"]).sort_values("date").set_index("date")
            report = manager.check_data_ready(df_sym, extra_checks=True)
            if not report.is_ready:
                return None

            df = add_technical_indicators(df_sym)
            if df.empty:
                return None

            for _c in (
                "marketCap",
                "peRatio",
                "eps",
                "dividendYield",
                "sector",
                "industry",
                "sector_avg_return",
                "stock_daily_return",
            ):
                if _c in df_sym.columns and _c not in df.columns:
                    try:
                        if len(df_sym[_c]) == len(df):
                            df[_c] = df_sym[_c].values
                        else:
                            df[_c] = df_sym[_c].iloc[-1]
                    except Exception:
                        df[_c] = df_sym[_c].iloc[-1] if len(df_sym) else None

            df = add_massive_features(df)
            df = add_market_context(df, market_df)

            labeler = StrictQualityLabeler(t_params)
            df, _rejection_counts = labeler.label_training_data_strict(
                df, egx30_data=market_df, drop_labels=True
            )

            if len(df) < 10:
                return None
            df["symbol"] = sym
            df["Date"] = pd.to_datetime(df.index, errors="coerce")
            return df
        except Exception as e:
            print(f"Error processing Saudi {params[0]}: {e}")
            return None

    def prepare_training_data(
        self,
        df_all: pd.DataFrame,
        target_pct: float,
        stop_loss_pct: float,
        look_forward_days: int,
        preset: str = "extended",
        use_volatility_label: bool = False,
        barrier_mode: Optional[str] = None,
    ) -> pd.DataFrame:
        self.load_market_data()
        # Fill sector/industry directly from `stocks` if missing in `stock_fundamentals`
        stocks_meta = pd.DataFrame(self.history_cache.get("stocks_rows") or [])
        if not stocks_meta.empty:
            cols = [c for c in ("symbol", "sector", "industry") if c in stocks_meta.columns]
            df_all = df_all.merge(stocks_meta[cols].drop_duplicates("symbol"), on="symbol", how="left")
            for c in ("sector", "industry"):
                if c in df_all.columns and c not in self.categorical_features:
                    self.categorical_features.append(c)

        df_train = super().prepare_training_data(
            df_all=df_all,
            target_pct=target_pct,
            stop_loss_pct=stop_loss_pct,
            look_forward_days=look_forward_days,
            preset=preset,
            use_volatility_label=use_volatility_label,
            barrier_mode=barrier_mode,
        )
        # Ensure min_volume_ratio aligns strictly with EGX (`0.8`) in saved params metadata
        self.params.min_volume_ratio = 0.8
        return df_train


def _optimize_meta_threshold_on_dev(
    probs: np.ndarray,
    y_true: np.ndarray,
    min_support: int = 80,
) -> Tuple[float, Dict[str, float]]:
    """
    Choose meta_threshold strictly on development/tune-or-oof-dev predictions (never test!).
    Prioritizes high precision while maintaining healthy signal support.
    """
    best_th = 0.55
    best_score = -1.0
    best_stats: Dict[str, float] = {}

    for th in np.round(np.arange(0.45, 0.78, 0.02), 2):
        preds = (probs >= th).astype(int)
        cnt = int(preds.sum())
        if cnt < min_support:
            continue
        prec = float(precision_score(y_true, preds, zero_division=0))
        rec = float(recall_score(y_true, preds, zero_division=0))
        f1 = float(f1_score(y_true, preds, zero_division=0))
        base = float(np.mean(y_true))
        lift = prec - base
        # Reward meaningful precision lift with non-trivial trade volume
        score = prec + 0.15 * min(rec, 0.25) + (0.05 if lift > 0.08 else 0.0)
        if score > best_score:
            best_score = score
            best_th = float(th)
            best_stats = {
                "dev_precision": prec,
                "dev_recall": rec,
                "dev_f1": f1,
                "dev_signals": cnt,
                "dev_base_rate": base,
            }

    if not best_stats:
        preds = (probs >= best_th).astype(int)
        best_stats = {
            "dev_precision": float(precision_score(y_true, preds, zero_division=0)),
            "dev_recall": float(recall_score(y_true, preds, zero_division=0)),
            "dev_f1": float(f1_score(y_true, preds, zero_division=0)),
            "dev_signals": int(preds.sum()),
            "dev_base_rate": float(np.mean(y_true)),
        }
    return best_th, best_stats


def _score_meta_system_df(artifact: Dict[str, Any], df_slice: pd.DataFrame) -> np.ndarray:
    """Score rows with exact `meta_labeling_system` runtime alignment (PCA + cats + XGB)."""
    from api.routers.scan_ai_fast import _LgbmBoosterClassifier, _MetaLabelingClassifier, _PcaTransformer

    pm = artifact["primary_model"]
    booster = lgb.Booster(model_str=pm["model_str"])
    pca_transformer = None
    if pm.get("pca") is not None and pm.get("scaler") is not None and pm.get("pca_features"):
        pca_transformer = _PcaTransformer(pm["pca"], pm["scaler"], pm["pca_features"])

    primary_clf = _LgbmBoosterClassifier(booster, 0.5, pca_transformer=pca_transformer)
    meta_clf = _MetaLabelingClassifier(
        primary_clf=primary_clf,
        meta_model=artifact["meta_model"],
        meta_feature_names=artifact["meta_feature_names"],
        meta_threshold=float(artifact.get("meta_threshold", 0.55)),
        return_raw_prob=True,
    )

    f_names = list(pm["feature_names"])
    pca_feats = list(pm.get("pca_features") or [])
    if pca_feats:
        raw_needed = [c for c in f_names if not str(c).startswith("PCA_Momentum_")] + pca_feats
    else:
        raw_needed = f_names

    X = df_slice.copy()
    for c in raw_needed:
        if c not in X.columns:
            X[c] = 0.0
    X = X[raw_needed].copy()

    cat_cols = [c for c in (pm.get("categorical_features") or []) if c in X.columns]
    for c in cat_cols:
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
        X[non_cat] = X[non_cat].fillna(0.0)

    primary_booster = get_primary_booster(meta_clf)
    X = align_pandas_categories_to_booster(
        X,
        cat_cols=cat_cols,
        booster=primary_booster,
        cat_cols_order=list(pm.get("categorical_features") or []),
    )
    if primary_booster is None or not (cat_cols and hasattr(primary_booster, "pandas_categorical")):
        reset_nested_boosters(meta_clf)

    probs = meta_clf.predict_proba(X)[:, 1]
    return np.asarray(probs, dtype=float)


def evaluate_oos_lockbox_backtest(
    artifact: Dict[str, Any],
    bars_by_symbol: Dict[str, pd.DataFrame],
    market_df: pd.DataFrame,
    df_test_raw_features: pd.DataFrame,
    threshold: float,
    target_atr_mult: float = 3.0,
    stop_atr_mult: float = 1.5,
    max_sessions: int = 20,
    top_k_per_day: int = 4,
    market_regime_filter: bool = True,
) -> Dict[str, Any]:
    """
    Strictly causal out-of-sample lockbox trade simulation across unseen test dates
    using `api/recommendation_policy.evaluate_bars` + `StrictQualityLabeler`-aligned barriers.
    """
    probs = _score_meta_system_df(artifact, df_test_raw_features)
    scored = df_test_raw_features[["symbol", "Date", "Close", "ATR_14", "CMF_20", "MM_Distribution", "R_VOL", "RSI", "EMA_50"]].copy()
    scored["Date_str"] = pd.to_datetime(scored["Date"]).dt.strftime("%Y-%m-%d")
    scored["prob"] = probs

    # Compute causal TASI index filter (SMA20 / SMA50 & no panic day)
    mkt_close = market_df["close"].astype(float)
    mkt_sma20 = mkt_close.rolling(20, min_periods=1).mean()
    mkt_ret1 = mkt_close.pct_change().fillna(0.0)
    mkt_ret5 = mkt_close.pct_change(5).fillna(0.0)
    healthy_dates = {
        ts.strftime("%Y-%m-%d")
        for ts in market_df.index[(mkt_close >= mkt_sma20 * 0.99) & (mkt_ret1 > -0.02) & (mkt_ret5 > -0.02)]
    }

    # Build OHLC lists expected by `evaluate_bars`
    bars_dict: Dict[str, List[Dict[str, Any]]] = {}
    date_pos: Dict[str, Dict[str, int]] = {}
    for sym, bdf in bars_by_symbol.items():
        if bdf is None or bdf.empty:
            continue
        recs = []
        pos_map = {}
        for idx_i, (ts, row) in enumerate(bdf.iterrows()):
            d_s = ts.strftime("%Y-%m-%d")
            pos_map[d_s] = idx_i
            recs.append({
                "date": d_s,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row["Volume"]),
            })
        bars_dict[sym] = recs
        date_pos[sym] = pos_map

    cands = scored[scored["prob"] >= threshold].copy()
    cands = cands.sort_values(["Date_str", "prob"], ascending=[True, False])

    trades: List[Dict[str, Any]] = []
    cooldown_until: Dict[str, int] = {}
    unique_dates = sorted(scored["Date_str"].unique())
    date_to_ord = {d: i for i, d in enumerate(unique_dates)}

    for d_str, day_df in cands.groupby("Date_str", sort=True):
        if market_regime_filter and d_str not in healthy_dates:
            continue
        d_ord = date_to_ord.get(d_str, 0)
        day_picks = 0
        for _, row in day_df.iterrows():
            if day_picks >= top_k_per_day:
                break
            sym = str(row["symbol"])
            if sym in cooldown_until and d_ord < cooldown_until[sym]:
                continue
            if float(row.get("MM_Distribution") or 0.0) > 0.5 or float(row.get("CMF_20") or 0.0) < -0.05:
                continue
            close_v = float(row["Close"])
            atr_v = float(row["ATR_14"]) if np.isfinite(row["ATR_14"]) and row["ATR_14"] > 0 else close_v * 0.02
            if close_v <= 0:
                continue
            pos = date_pos.get(sym, {}).get(d_str)
            if pos is None or pos + 2 >= len(bars_dict[sym]):
                continue
            target_v = round(close_v + target_atr_mult * atr_v, 3 if close_v < 2.0 else 2)
            stop_v = round(close_v - stop_atr_mult * atr_v, 3 if close_v < 2.0 else 2)
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
            )
            if outcome["status"] in ("win", "loss"):
                pl_pct = float(outcome["profit_loss_pct"])
                trades.append({
                    "symbol": sym,
                    "entry_date": d_str,
                    "closed_on": outcome["closed_on"],
                    "status": outcome["status"],
                    "pl_pct": pl_pct,
                    "prob": float(row["prob"]),
                    "exit_reason": outcome["exit_reason"],
                })
                cooldown_until[sym] = d_ord + int(outcome.get("sessions_held") or max_sessions) + 1
                day_picks += 1

    if not trades:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_return_pct": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "avg_pl_pct": 0.0,
            "max_drawdown_pct": 0.0,
        }

    wins = [t["pl_pct"] for t in trades if t["status"] == "win"]
    losses = [t["pl_pct"] for t in trades if t["status"] == "loss"]
    gross_win = float(sum(max(0.0, w) for w in wins))
    gross_loss = float(sum(abs(min(0.0, l)) for l in losses))
    pf = round(gross_win / gross_loss, 3) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)

    # Portfolio compounded equity assuming max 10 concurrent equal slots (10% allocation per trade)
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
    }


def _build_pre_pca_raw_lookup(
    trainer: SaudiModelTrainer,
    df_raw: pd.DataFrame,
    target_pct: float,
    stop_loss_pct: float,
    look_forward_days: int,
    barrier_mode: str,
) -> pd.DataFrame:
    """
    Build clean prepared dataframe (before PCA column replacement) so Meta-Labeling
    and runtime scoring preserve raw momentum features cleanly.
    """
    return trainer.prepare_training_data(
        df_raw,
        target_pct=target_pct,
        stop_loss_pct=stop_loss_pct,
        look_forward_days=look_forward_days,
        preset="extended",
        use_volatility_label=False,
        barrier_mode=barrier_mode,
    )


def train_saudi_meta_model(
    history_cache: Dict[str, Any],
    model_filename: str,
    target_pct: float,
    stop_loss_pct: float,
    look_forward_days: int,
    barrier_mode: str = "atr_multiplier",
    n_estimators: int = 700,
    learning_rate: float = 0.015,
    patience: int = 80,
    extra_params: Optional[Dict[str, Any]] = None,
    min_meta_threshold: float = 0.50,
    df_prepared_raw: Optional[pd.DataFrame] = None,
) -> Tuple[str, Dict[str, Any], pd.DataFrame]:
    """
    Train an EGX-matched `meta_labeling_system` model on full Saudi history and
    save `.pkl`, booster `.txt` files, and `AdaptiveModelSelector`-ready `.model_card.json`.
    Returns `(model_path, summary_metrics, df_prepared_raw)`.
    """
    base_url, service_key = get_saudi_credentials()
    trainer = SaudiModelTrainer(base_url, service_key, history_cache=history_cache)
    trainer.load_market_data()

    if df_prepared_raw is None:
        df_raw = trainer.fetch_stock_prices()
        df_prepared_raw = _build_pre_pca_raw_lookup(
            trainer=trainer,
            df_raw=df_raw,
            target_pct=target_pct,
            stop_loss_pct=stop_loss_pct,
            look_forward_days=look_forward_days,
            barrier_mode=barrier_mode,
        )
    else:
        # Still initialize trainer.params & categorical_features identically
        trainer.params = TradingParameters(
            entry_mode="next_open",
            look_forward_days=look_forward_days,
            barrier_mode=barrier_mode,
            target_pct=target_pct,
            stop_loss_pct=stop_loss_pct,
            min_history_needed=120,
            warmup_bars=120,
            require_volume_confirmation=False,
            min_volume_ratio=0.8,
        )
        trainer.fundamentals_loaded = True
        for c in ("sector", "industry"):
            if c in df_prepared_raw.columns and c not in trainer.categorical_features:
                trainer.categorical_features.append(c)

    # Keep untouched copy of raw (pre-PCA) prepared frame for lockbox evaluation
    df_raw_copy = df_prepared_raw.copy()

    trainer.select_predictors(df_raw_copy, preset="extended")
    pre_pca_predictors = list(trainer.predictors)

    primary_model, val_metrics, avg_purged_f1, df_post_pca = trainer.train_model(
        df_raw_copy.copy(),
        n_estimators=n_estimators,
        learning_rate=learning_rate,
        patience=patience,
        look_forward_bars=look_forward_days,
        eval_metric="logloss",
        extra_params=extra_params or {},
        optimized_params=None,
        auto_prune=False,
        target_pct=target_pct,
        stop_loss_pct=stop_loss_pct,
    )

    # Out-of-sample Meta-Labeling trained strictly on `tune_mask` (never train_mask, never test_mask!)
    norm_dates = pd.to_datetime(df_raw_copy["Date"], errors="coerce").dt.normalize()
    tune_start = pd.Timestamp(val_metrics["tune_start_date"])
    tune_end = pd.Timestamp(val_metrics["tune_end_date"])
    test_start = pd.Timestamp(val_metrics["test_start_date"])

    tune_mask = (norm_dates >= tune_start) & (norm_dates <= tune_end)
    test_mask = norm_dates >= test_start

    X_tune_raw = df_raw_copy.loc[tune_mask, pre_pca_predictors].copy()
    y_tune_raw = df_raw_copy.loc[tune_mask, "Target"].astype(int).copy()
    X_test_raw = df_raw_copy.loc[test_mask, pre_pca_predictors].copy()
    y_test_raw = df_raw_copy.loc[test_mask, "Target"].astype(int).copy()

    primary_tune_probs = np.asarray(primary_model.predict_proba(X_tune_raw)[:, 1], dtype=float)
    primary_test_probs = np.asarray(primary_model.predict_proba(X_test_raw)[:, 1], dtype=float)

    # Meta-model numeric features mirror post-PCA predictors (exactly how `_MetaLabelingClassifier` extracts features!)
    meta_feature_names: List[str] = []
    for c in trainer.predictors:
        if c in (trainer.categorical_features or []):
            continue
        if c in df_post_pca.columns and is_numeric_dtype(df_post_pca[c]):
            meta_feature_names.append(c)

    X_meta_tune_all = (
        df_post_pca.loc[tune_mask, meta_feature_names]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
        .copy()
    )
    X_meta_test_all = (
        df_post_pca.loc[test_mask, meta_feature_names]
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
        .copy()
    )

    # Filter candidate entries in `tune` (use primary threshold, relax cleanly inside `tune` ONLY if < 250 candidates)
    opt_th = float(val_metrics.get("optimal_threshold", 0.50))
    cand_mask = primary_tune_probs >= opt_th
    if int(cand_mask.sum()) < 250:
        # Relax to median+ quantile strictly within tune set (never touching train or test!)
        rel_th = float(np.quantile(primary_tune_probs, 0.70))
        cand_mask = primary_tune_probs >= rel_th

    X_meta_train = X_meta_tune_all.loc[cand_mask].copy()
    X_meta_train["primary_prob"] = primary_tune_probs[cand_mask]
    y_meta_train = y_tune_raw.loc[cand_mask].values

    if len(np.unique(y_meta_train)) < 2:
        X_meta_train = X_meta_tune_all.copy()
        X_meta_train["primary_prob"] = primary_tune_probs
        y_meta_train = y_tune_raw.values

    # Fit meta-model with chronological 80/20 split inside `tune` to pick `meta_threshold` leak-free!
    split_idx = int(len(X_meta_train) * 0.75)
    pos = float(np.sum(y_meta_train[:split_idx] == 1))
    neg = float(np.sum(y_meta_train[:split_idx] == 0))
    # Gentle balancing avoids extreme probability inflation while sharpening secondary filter
    spw = min(2.0, max(0.8, (neg / max(pos, 1.0)) * 0.75))

    def _make_xgb():
        if xgb is not None:
            return xgb.XGBClassifier(
                n_estimators=300,
                max_depth=4,
                learning_rate=0.015,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_lambda=2.0,
                reg_alpha=0.5,
                objective="binary:logistic",
                eval_metric="logloss",
                random_state=42,
                n_jobs=-1,
                scale_pos_weight=spw,
            )
        return lgb.LGBMClassifier(
            n_estimators=300,
            learning_rate=0.02,
            num_leaves=23,
            max_depth=4,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )

    dev_meta = _make_xgb()
    dev_meta.fit(X_meta_train.iloc[:split_idx], y_meta_train[:split_idx])
    dev_meta_probs = np.asarray(dev_meta.predict_proba(X_meta_train.iloc[split_idx:])[:, 1], dtype=float)
    meta_threshold, dev_stats = _optimize_meta_threshold_on_dev(
        dev_meta_probs,
        y_meta_train[split_idx:],
        min_support=max(30, int(len(dev_meta_probs) * 0.08)),
    )
    meta_threshold = max(float(min_meta_threshold), float(meta_threshold))

    # Refit final meta_model on full `tune` candidate pool (still strictly disjoint from OOS `test_mask`!)
    full_pos = float(np.sum(y_meta_train == 1))
    full_neg = float(np.sum(y_meta_train == 0))
    meta_model = _make_xgb()
    if hasattr(meta_model, "set_params"):
        meta_model.set_params(scale_pos_weight=min(2.0, max(0.8, (full_neg / max(full_pos, 1.0)) * 0.75)))
    meta_model.fit(X_meta_train, y_meta_train)

    # Save exact EGX meta_labeling_system artifact via trainer.save_meta_labeling_system
    actual_primary = primary_model.model if hasattr(primary_model, "model") else primary_model
    best_it = getattr(actual_primary, "best_iteration_", None)
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
        "feature_preset": "extended",
        "featurePreset": "extended",
        "n_estimators": int(n_estimators),
        "best_iteration": best_it,
        "bestIteration": best_it,
        "learning_rate": float(learning_rate),
        "training_samples": int(val_metrics.get("train_samples_actual", len(df_post_pca))),
        "trainingSamples": int(val_metrics.get("train_samples_actual", len(df_post_pca))),
        "use_intraday": False,
        "timeframe": "1d",
        "training_strategy": "golden",
        "eval_metric": "logloss",
        "base_params": extra_params or {},
        "optimized": False,
        "purged_cv_f1": avg_purged_f1,
        "has_meta_labeling": True,
        "meta_threshold": float(meta_threshold),
        "buyThreshold": float(meta_threshold),
        **val_metrics,
    }

    saved_path = trainer.save_meta_labeling_system(
        primary_model=primary_model,
        meta_model=meta_model,
        filename=model_filename,
        metadata=save_metadata,
        meta_threshold=float(meta_threshold),
        meta_feature_names=meta_feature_names_with_prob,
    )

    with open(saved_path, "rb") as f:
        artifact = pickle.load(f)

    # Honest strict Out-of-Sample evaluation on UNSEEN `test_mask` lockbox!
    df_test_slice = df_raw_copy.loc[test_mask].copy()
    test_probs = _score_meta_system_df(artifact, df_test_slice)
    y_test_arr = y_test_raw.values
    test_preds = (test_probs >= float(meta_threshold)).astype(int)

    oos_auc = float(roc_auc_score(y_test_arr, test_probs)) if len(np.unique(y_test_arr)) > 1 else 0.5
    oos_ap = float(average_precision_score(y_test_arr, test_probs)) if len(np.unique(y_test_arr)) > 1 else 0.0
    oos_prec = float(precision_score(y_test_arr, test_preds, zero_division=0))
    oos_rec = float(recall_score(y_test_arr, test_preds, zero_division=0))
    oos_f1 = float(f1_score(y_test_arr, test_preds, zero_division=0))
    oos_brier = float(brier_score_loss(y_test_arr, np.clip(test_probs, 0.0, 1.0)))
    oos_base_rate = float(np.mean(y_test_arr))
    q90 = float(np.quantile(test_probs, 0.90))
    top_decile_prec = float(y_test_arr[test_probs >= q90].mean()) if np.any(test_probs >= q90) else oos_prec

    bt_res = evaluate_oos_lockbox_backtest(
        artifact=artifact,
        bars_by_symbol=history_cache["bars_by_symbol"],
        market_df=history_cache["market_df"],
        df_test_raw_features=df_test_slice,
        threshold=float(meta_threshold),
        target_atr_mult=target_pct if barrier_mode == "atr_multiplier" else 3.0,
        stop_atr_mult=stop_loss_pct if barrier_mode == "atr_multiplier" else 1.5,
        max_sessions=look_forward_days,
        top_k_per_day=4,
        market_regime_filter=True,
    )

    # Update artifact & card with verified OOS lockbox metrics (primary metric source = unseen test set!)
    summary_metrics = {
        "precision": round(oos_prec, 4),
        "recall": round(oos_rec, 4),
        "f1": round(oos_f1, 4),
        "auc": round(oos_auc, 4),
        "average_precision": round(oos_ap, 4),
        "brier_score": round(oos_brier, 4),
        "base_rate": round(oos_base_rate, 4),
        "top_decile_precision": round(top_decile_prec, 4),
        "optimal_threshold": float(meta_threshold),
        "primary_optimal_threshold": float(opt_th),
        "meta_threshold": float(meta_threshold),
        "signals_in_test": int(test_preds.sum()),
        "test_samples": int(len(y_test_arr)),
        "train_samples": int(val_metrics.get("train_samples_actual", 0)),
        "test_period": f"{val_metrics['test_start_date']} -> {val_metrics['test_end_date']}",
        "train_period": f"{val_metrics['train_start_date']} -> {val_metrics['train_end_date']}",
        "walk_forward_summary": artifact.get("walk_forward_summary") or {},
        "oos_backtest": bt_res,
        "dev_calibration": dev_stats,
    }

    artifact["precision"] = summary_metrics["precision"]
    artifact["recall"] = summary_metrics["recall"]
    artifact["f1"] = summary_metrics["f1"]
    artifact["auc"] = summary_metrics["auc"]
    artifact["optimal_threshold"] = float(meta_threshold)
    artifact["oos_backtest"] = bt_res
    artifact["test_period"] = summary_metrics["test_period"]
    artifact["train_period"] = summary_metrics["train_period"]
    with open(saved_path, "wb") as f:
        pickle.dump(artifact, f)

    # Enrich `.model_card.json` so BOTH EGX trainer consumers and AdaptiveModelSelector read all fields cleanly
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
        "buyThreshold": float(meta_threshold),
        "meta_threshold": float(meta_threshold),
        "optimal_threshold": float(meta_threshold),
        "primary_optimal_threshold": float(opt_th),
        "feature_names": list(trainer.predictors),
        "meta_feature_names": meta_feature_names_with_prob,
        "precision": summary_metrics["precision"],
        "recall": summary_metrics["recall"],
        "f1": summary_metrics["f1"],
        "auc": summary_metrics["auc"],
        "oos_backtest": bt_res,
        "train_period": summary_metrics["train_period"],
        "test_period": summary_metrics["test_period"],
    })
    card["training"]["metrics"] = {
        "precision": summary_metrics["precision"],
        "recall": summary_metrics["recall"],
        "f1": summary_metrics["f1"],
        "auc": summary_metrics["auc"],
        "average_precision": summary_metrics["average_precision"],
        "brier_score": summary_metrics["brier_score"],
        "base_rate": summary_metrics["base_rate"],
        "top_decile_precision": summary_metrics["top_decile_precision"],
    }
    with open(card_path, "w", encoding="utf-8") as cf:
        json.dump(card, cf, indent=2)

    print(
        f"  [DONE] {model_filename} | OOS({summary_metrics['test_period']}) "
        f"AUC={oos_auc:.4f} (base={oos_base_rate:.3f}) | P={oos_prec:.3f} "
        f"(top10%={top_decile_prec:.3f}) | th={meta_threshold:.2f} | "
        f"Backtest: {bt_res['trades']} trades, WR={bt_res['win_rate']}%, "
        f"PF={bt_res['profit_factor']}, Ret={bt_res['total_return_pct']}%"
    )
    return saved_path, summary_metrics, df_raw_copy


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cache = load_saudi_history_cached()
    print(
        f"Saudi cache ready: {sum(len(v) for v in cache['bars_by_symbol'].values()):,} rows "
        f"({cache['min_price_date']} -> {cache['max_price_date']}), "
        f"{len(cache['market_index_rows']):,} TASI rows."
    )
