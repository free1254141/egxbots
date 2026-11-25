#!/usr/bin/env python3
"""
Retrain EGX ML models (`model_EGX_v2` & `KING_v2`) with the modern stationary
LightGBM + XGBoost Meta-Labeling architecture (matching `api/saudi_train_models.py`),
run a STRICT zero-leakage Out-Of-Sample (OOS) benchmark on `2026-06-01 -> 2026-11-24`
month-by-month against the old `.bin` models and live `scan_results`, and save
fresh production-candidate artifacts strictly under `api/models/candidates/`.

Live production models (`api/models/*.bin` / `*.pkl`) are NEVER overwritten.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("STOKSCANAI_DISABLE_JOBLIB_CACHE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import gzip
import json
import pickle
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from huggingface_hub import hf_hub_download
from pandas.api.types import is_numeric_dtype
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from supabase import create_client

from api.egx30_fetcher import get_market_regime
from api.model_utils import align_pandas_categories_to_booster
from api.recommendation_policy import CorporateActionDiscontinuity, candidate_assessment, evaluate_bars
from api.saudi_train_models import (
    META_CORE_CANDIDATES,
    SAUDI_PROFIT_PROTECTION_POLICY,
    STATIONARY_EXCLUDE_COLS,
    _build_bars_dict,
    _healthy_tasi_dates,
    _prepare_model_matrix,
    _run_purged_walk_forward_stationary,
)
from api.stock_ai import (
    _LgbmBoosterClassifier,
    _MetaLabelingClassifier,
    _PcaTransformer,
    add_technical_indicators,
)
from api.strict_quality_labeler import StrictQualityLabeler
from api.trading_config import TradingParameters
from api.train_exchange_model import ModelTrainer, add_market_context, add_massive_features, xgb

HISTORY_START = "2010-01-01"
EGX_CACHE_PATH = os.path.join(PROJECT_ROOT, "api", "data_cache", "egx_history_cache.pkl")
EGX_COMPACT_FEAT_PATH = os.path.join(PROJECT_ROOT, "api", "data_cache", "egx_compact_features.pkl")
EGX_EVAL_FULL_PATH = os.path.join(PROJECT_ROOT, "api", "data_cache", "egx_eval_full_202606.pkl")
CANDIDATES_DIR = os.path.join(PROJECT_ROOT, "api", "models", "candidates")


def _get_egx_supabase():
    load_dotenv(os.path.join(PROJECT_ROOT, "api", ".env"))
    load_dotenv(os.path.join(PROJECT_ROOT, "web", ".env.local"))
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").strip()
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
    return url.rstrip("/"), key, create_client(url, key)


def load_egx_history_cached(force_refresh: bool = False) -> Dict[str, Any]:
    """Load EGX prices (HF dataset 2010->2026-11-24) + EGX30 index + EGX metadata."""
    t0 = time.time()
    url, key, sb = _get_egx_supabase()
    hf_token = (os.getenv("HF_TOKEN") or "").strip() or None

    if not force_refresh and os.path.exists(EGX_CACHE_PATH):
        try:
            with open(EGX_CACHE_PATH, "rb") as f:
                cached = pickle.load(f)
            if (
                isinstance(cached, dict)
                and len(cached.get("bars_by_symbol") or {}) >= 150
                and str(cached.get("max_price_date") or "") >= "2026-11-24"
            ):
                total_rows = sum(len(v) for v in cached["bars_by_symbol"].values())
                print(
                    f"[CACHE HIT] Loaded {total_rows:,} EGX bars ({cached['min_price_date']} -> "
                    f"{cached['max_price_date']}) across {len(cached['bars_by_symbol'])} symbols in {time.time()-t0:.1f}s"
                )
                return cached
        except Exception:
            pass

    print("[DATA] Downloading HF EGX historical prices & index...")
    egx_gz = hf_hub_download("weeasdwee/egx-historical-prices", "prices/EGX/stock_prices.json.gz", repo_type="dataset", token=hf_token)
    idx_gz = hf_hub_download("weeasdwee/egx-historical-prices", "prices/INDX/stock_prices.json.gz", repo_type="dataset", token=hf_token)

    with gzip.open(egx_gz, "rt", encoding="utf-8") as f:
        egx_raw = json.load(f)
    with gzip.open(idx_gz, "rt", encoding="utf-8") as f:
        idx_raw = json.load(f)

    # Filter EGX stock prices >= HISTORY_START
    df_p = pd.DataFrame(egx_raw)
    df_p = df_p[df_p["date"] >= HISTORY_START].copy()
    df_p["dt"] = pd.to_datetime(df_p["date"], errors="coerce")
    df_p = df_p.dropna(subset=["dt"])

    bars_by_symbol: Dict[str, pd.DataFrame] = {}
    for sym, grp in df_p.groupby("symbol", sort=False):
        sub = pd.DataFrame({
            "Open": pd.to_numeric(grp["open"], errors="coerce").values,
            "High": pd.to_numeric(grp["high"], errors="coerce").values,
            "Low": pd.to_numeric(grp["low"], errors="coerce").values,
            "Close": pd.to_numeric(grp["close"], errors="coerce").values,
            "Volume": pd.to_numeric(grp["volume"], errors="coerce").values,
        }, index=pd.DatetimeIndex(grp["dt"], name="date")).sort_index()
        sub = sub[~sub.index.duplicated(keep="last")]
        sub = sub.dropna(subset=["Close"])
        sub = sub[sub["Close"] > 0].copy()
        for c in ("Open", "High", "Low"):
            sub[c] = sub[c].fillna(sub["Close"])
        sub["Volume"] = sub["Volume"].fillna(0.0).clip(lower=0.0)
        if len(sub) >= 120:
            bars_by_symbol[str(sym)] = sub

    # Filter EGX30 index and merge tail from Supabase (2026-09-20 -> 2026-11-25)
    egx30_rows = [
        {"date": r["date"], "close": r["close"]}
        for r in idx_raw
        if str(r.get("symbol") or "").upper() == "EGX30" and str(r.get("date") or "") >= HISTORY_START
    ]
    supa_idx = (
        sb.table("stock_prices")
        .select("date,close")
        .eq("symbol", "EGX30")
        .gte("date", "2026-09-20")
        .order("date", desc=False)
        .limit(200)
        .execute()
        .data
        or []
    )
    egx30_rows.extend(supa_idx)
    mdf = pd.DataFrame(egx30_rows)
    mdf["date"] = pd.to_datetime(mdf["date"], errors="coerce")
    mdf = mdf.dropna(subset=["date"]).sort_values("date").drop_duplicates(subset=["date"], keep="last").set_index("date")
    mdf["close"] = pd.to_numeric(mdf["close"], errors="coerce").ffill().fillna(0.0)
    mdf["open"] = mdf["close"]
    mdf["high"] = mdf["close"]
    mdf["low"] = mdf["close"]
    mdf["volume"] = 0.0
    mdf["atr"] = mdf["close"].pct_change().rolling(20).std().fillna(0.0)
    mdf["egx30_return"] = mdf["close"].pct_change().fillna(0.0)
    mdf["market_regime"] = mdf["egx30_return"].apply(get_market_regime)

    # Fetch compact EGX metadata & fundamentals (1 call each)
    stocks_rows = (
        sb.table("stocks")
        .select("symbol,is_active")
        .eq("exchange", "EGX")
        .limit(1000)
        .execute()
        .data
        or []
    )
    fund_rows = (
        sb.table("stock_fundamentals")
        .select("symbol,fund_score,data")
        .eq("exchange", "EGX")
        .limit(1000)
        .execute()
        .data
        or []
    )

    all_dates = [df.index.max().strftime("%Y-%m-%d") for df in bars_by_symbol.values() if not df.empty]
    min_dates = [df.index.min().strftime("%Y-%m-%d") for df in bars_by_symbol.values() if not df.empty]
    payload = {
        "stocks_rows": stocks_rows,
        "fund_rows": fund_rows,
        "market_df": mdf,
        "bars_by_symbol": bars_by_symbol,
        "min_price_date": min(min_dates),
        "max_price_date": max(all_dates),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(os.path.dirname(EGX_CACHE_PATH), exist_ok=True)
    with open(EGX_CACHE_PATH, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    total_rows = sum(len(v) for v in bars_by_symbol.values())
    print(
        f"[DATA OK] {total_rows:,} EGX bars ({payload['min_price_date']} -> {payload['max_price_date']}) "
        f"across {len(bars_by_symbol)} symbols | EGX30 ({mdf.index.min().date()} -> {mdf.index.max().date()}) in {time.time()-t0:.1f}s"
    )
    return payload


def load_or_build_egx_features(history_cache: Dict[str, Any], force_rebuild: bool = False) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (df_compact_stationary_2010_2026, df_eval_full_202606_202611)."""
    max_date = str(history_cache["max_price_date"])[:10]
    if not force_refresh_needed(force_rebuild, max_date):
        try:
            df_compact = pd.read_pickle(EGX_COMPACT_FEAT_PATH)
            df_eval_full = pd.read_pickle(EGX_EVAL_FULL_PATH)
            print(
                f"[FEAT CACHE HIT] compact={len(df_compact):,}x{df_compact.shape[1]}, "
                f"eval_full={len(df_eval_full):,}x{df_eval_full.shape[1]}"
            )
            return df_compact, df_eval_full
        except Exception as exc:
            print(f"[FEAT CACHE WARN] {exc}")

    print("[FEAT BUILD] Computing EGX technical + market + sector features (2010 -> 2026-11)...")
    t0 = time.time()
    mdf = history_cache["market_df"]
    sector_map: Dict[str, str] = {}
    industry_map: Dict[str, str] = {}
    for r in history_cache.get("stocks_rows") or []:
        sym = str(r.get("symbol") or "").upper()
        if sym:
            sector_map[sym] = str(r.get("sector") or "Unknown")
            industry_map[sym] = str(r.get("industry") or "Unknown")

    fund_map: Dict[str, Dict[str, float]] = {}
    for r in history_cache.get("fund_rows") or []:
        sym = str(r.get("symbol") or "").upper()
        d = r.get("data") or {}
        if sym and isinstance(d, dict):
            fund_map[sym] = {
                "marketCap": float(d.get("marketCap") or d.get("market_cap") or 0.0),
                "peRatio": float(d.get("peRatio") or d.get("pe_ratio") or 0.0),
                "eps": float(d.get("eps") or 0.0),
                "dividendYield": float(d.get("dividendYield") or d.get("dividend_yield") or 0.0),
            }
            if sector_map.get(sym, "Unknown") == "Unknown" and d.get("sector"):
                sector_map[sym] = str(d["sector"])
            if industry_map.get(sym, "Unknown") == "Unknown" and d.get("industry"):
                industry_map[sym] = str(d["industry"])

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
        fm = fund_map.get(sym, {})
        df_ind["marketCap"] = fm.get("marketCap", 0.0)
        df_ind["peRatio"] = fm.get("peRatio", 0.0)
        df_ind["eps"] = fm.get("eps", 0.0)
        df_ind["dividendYield"] = fm.get("dividendYield", 0.0)
        df_ind["symbol"] = sym
        df_ind["Date"] = pd.to_datetime(df_ind.index)
        df_ind["stock_ret_1d"] = df_ind["Close"].astype(float).pct_change().fillna(0.0)
        raw_frames.append(df_ind.reset_index(drop=True))

    df_full = pd.concat(raw_frames, ignore_index=True)

    # Strictly causal 1-day lagged sector relative strength (matching saudi_train_models)
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

    # Build OOS evaluation frame for 2026-06-01+ keeping ALL raw/old columns for old .bin scoring
    eval_mask = df_full["Date"] >= pd.Timestamp("2026-06-01")
    drop_helper = [c for c in ("stock_ret_1d", "stock_ret_lag1", "sec_ret_lag1") if c in df_full.columns]
    df_eval_full = df_full.loc[eval_mask].drop(columns=drop_helper).copy()
    for c in df_eval_full.columns:
        if c in ("symbol", "sector", "industry"):
            df_eval_full[c] = df_eval_full[c].astype(str).astype("category")
        elif c != "Date" and is_numeric_dtype(df_eval_full[c]):
            df_eval_full[c] = pd.to_numeric(df_eval_full[c], errors="coerce").astype(np.float32)

    # Build stationary compact training frame (matching Saudi stationary feature preset)
    keep_cols = ["symbol", "Date", "Open", "High", "Low", "Close", "Volume", "ATR_14", "sector", "industry"]
    for c in df_full.columns:
        if c in keep_cols or c in ("stock_ret_1d", "stock_ret_lag1", "sec_ret_lag1", "marketCap", "peRatio", "eps", "dividendYield"):
            continue
        if is_numeric_dtype(df_full[c]) and c not in STATIONARY_EXCLUDE_COLS:
            if any(bad in c for bad in ("_SMA", "SMA_", "EMA_", "BB_Upper", "BB_Lower", "BB_Middle", "Lag")) and "Ratio" not in c and "Price_vs" not in c:
                if c not in ("Amihud_SMA_10", "RSI_Lag1"):
                    continue
            if c in ("OBV", "VWAP"):
                continue
            keep_cols.append(c)
    keep_cols = list(dict.fromkeys(keep_cols))
    df_compact = df_full[keep_cols].copy()
    for c in df_compact.columns:
        if c in ("symbol", "sector", "industry"):
            df_compact[c] = df_compact[c].astype(str).astype("category")
        elif c != "Date" and is_numeric_dtype(df_compact[c]):
            df_compact[c] = pd.to_numeric(df_compact[c], errors="coerce").astype(np.float32)

    df_compact.to_pickle(EGX_COMPACT_FEAT_PATH)
    df_eval_full.to_pickle(EGX_EVAL_FULL_PATH)
    print(f"[FEAT BUILT] compact={len(df_compact):,}x{df_compact.shape[1]}, eval_full={len(df_eval_full):,}x{df_eval_full.shape[1]} in {time.time()-t0:.1f}s")
    return df_compact, df_eval_full


def force_refresh_needed(force_rebuild: bool, max_date: str) -> bool:
    if force_rebuild or not os.path.exists(EGX_COMPACT_FEAT_PATH) or not os.path.exists(EGX_EVAL_FULL_PATH):
        return True
    try:
        df = pd.read_pickle(EGX_EVAL_FULL_PATH)
        return str(pd.to_datetime(df["Date"]).max())[:10] < max_date
    except Exception:
        return True


def label_egx_dataset(df_compact: pd.DataFrame, market_df: pd.DataFrame, params: TradingParameters) -> pd.DataFrame:
    labeler = StrictQualityLabeler(params)
    tparts: List[pd.DataFrame] = []
    for sym, grp in df_compact.groupby("symbol", observed=True):
        g = grp.sort_values("Date").copy().set_index("Date")
        res, _rej = labeler.label_training_data_strict(g, egx30_data=market_df, drop_labels=True)
        if len(res) < 10:
            continue
        res["symbol"] = sym
        res["Date"] = pd.to_datetime(res.index)
        tparts.append(res[["symbol", "Date", "Target"]])
    targets_df = pd.concat(tparts, ignore_index=True)
    labeled = df_compact.merge(targets_df, on=["symbol", "Date"], how="inner")
    return labeled.sort_values(["Date", "symbol"]).reset_index(drop=True)


def score_artifact_df(artifact: Dict[str, Any], df_slice: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Score any `meta_labeling_system` artifact (old .bin or new v2) identically to production."""
    pm = artifact["primary_model"]
    booster = lgb.Booster(model_str=pm["model_str"])
    pca_transformer = None
    if pm.get("pca") is not None and pm.get("scaler") is not None and pm.get("pca_features"):
        pca_transformer = _PcaTransformer(pm["pca"], pm["scaler"], pm["pca_features"])

    primary_clf = _LgbmBoosterClassifier(booster, 0.5, pca_transformer=pca_transformer)
    meta_feature_names = list(artifact.get("meta_feature_names") or [])
    meta_threshold = float(artifact.get("meta_threshold", 0.50))

    f_names = list(pm.get("feature_names") or booster.feature_name())
    pca_feats = list(pm.get("pca_features") or [])
    extra_meta = [c for c in meta_feature_names if c != "primary_prob" and not str(c).startswith("PCA_Momentum_")]
    raw_needed = list(dict.fromkeys(
        ([c for c in f_names if not str(c).startswith("PCA_Momentum_")] if pca_feats else f_names)
        + pca_feats
        + extra_meta
    ))
    cat_cols = [c for c in (pm.get("categorical_features") or []) if c in raw_needed]

    X = _prepare_model_matrix(df_slice, raw_needed, cat_cols, booster=booster)
    # _MetaLabelingClassifier expects all meta features (non-PCA) to exist on X
    for c in extra_meta:
        if c not in X.columns:
            X[c] = 0.0

    meta_clf = _MetaLabelingClassifier(
        primary_model=primary_clf,
        meta_model=artifact["meta_model"],
        meta_feature_names=meta_feature_names,
        meta_threshold=meta_threshold,
        return_raw_prob=False,
    )
    filtered_probs = np.asarray(meta_clf.predict_proba(X)[:, 1], dtype=float)
    primary_probs = np.asarray(primary_clf.predict_proba(X)[:, 1], dtype=float)

    X_trans = pca_transformer(X) if pca_transformer is not None else X
    mf = [c for c in meta_feature_names if c != "primary_prob"]
    X_meta = pd.DataFrame(index=X.index)
    for c in mf:
        X_meta[c] = pd.to_numeric(X_trans[c], errors="coerce").fillna(0.0) if c in X_trans.columns else 0.0
    X_meta = X_meta.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    X_meta["primary_prob"] = primary_probs
    cols = [c for c in meta_feature_names if c in X_meta.columns]
    X_meta = X_meta[cols]
    meta_probs = np.asarray(artifact["meta_model"].predict_proba(X_meta)[:, 1], dtype=float)
    return filtered_probs, primary_probs, meta_probs


def simulate_trades_detailed(
    df_slice: pd.DataFrame,
    primary_probs: np.ndarray,
    meta_probs: np.ndarray,
    primary_threshold: float,
    meta_threshold: float,
    bars_dict: Dict[str, List[Dict[str, Any]]],
    date_pos: Dict[str, Dict[str, int]],
    healthy_dates: set,
    max_sessions: int = 20,
    top_k_per_day: int = 3,
    market_regime_filter: bool = True,
    exec_tp_pct: float = 0.10,
    exec_sl_pct: float = 0.05,
    exec_atr_tp_mult: float = 3.0,
    exec_atr_sl_mult: float = 1.5,
) -> Dict[str, Any]:
    """Simulate trades & compute both overall + monthly breakdown."""
    mask = (primary_probs >= primary_threshold) & (meta_probs >= meta_threshold)
    if not np.any(mask):
        return {
            "trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "total_return_pct": 0.0, "avg_pl_pct": 0.0, "max_drawdown_pct": 0.0,
            "signals_raw": 0, "by_month": {}, "trade_list": [],
        }

    keep_cols = [
        c for c in (
            "symbol", "Date", "Close", "ATR_14", "CMF_20", "MM_Distribution",
            "RSI", "R_VOL", "ADX_14", "EMA_50_Ratio", "SMA_50_Ratio",
            "feat_52w_position", "feat_rel_strength", "feat_sector_rel_strength",
        )
        if c in df_slice.columns
    ]
    scored = df_slice.loc[mask, keep_cols].copy()
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
            if (
                float(row.get("EMA_50_Ratio") or 0.0) <= 0.0
                or float(row.get("SMA_50_Ratio") or 0.0) <= 0.0
                or float(row.get("feat_52w_position") or 0.0) < 0.45
            ):
                continue
            rsi_v = float(row.get("RSI") or 50.0)
            if (
                float(row.get("MM_Distribution") or 0.0) > 0.30
                or float(row.get("CMF_20") or 0.0) < 0.0
                or rsi_v > 70.0
                or rsi_v < 35.0
                or float(row.get("ADX_14") or 0.0) < 18.0
                or float(row.get("R_VOL") or 0.0) < 1.0
                or float(row.get("feat_rel_strength") or 0.0) < 0.01
                or float(row.get("feat_sector_rel_strength") or 0.0) < 0.0
            ):
                continue
            close_v = float(row["Close"])
            atr_v = float(row["ATR_14"]) if np.isfinite(row["ATR_14"]) and row["ATR_14"] > 0 else close_v * 0.02
            if close_v <= 0 or sym not in bars_dict:
                continue
            pos = date_pos.get(sym, {}).get(d_str)
            if pos is None or pos + 2 >= len(bars_dict[sym]):
                continue
            dec = 3 if close_v < 2.0 else 2
            target_v = round(min(close_v * 1.30, max(close_v * (1.0 + exec_tp_pct), close_v + exec_atr_tp_mult * atr_v)), dec)
            stop_v = round(min(close_v * (1.0 - exec_sl_pct), close_v - exec_atr_sl_mult * atr_v), dec)
            if not candidate_assessment({"symbol": sym, "last_close": close_v, "target_price": target_v, "stop_loss": stop_v}, minimum_rr=1.5)["accepted"]:
                continue

            bars_win = bars_dict[sym][max(0, pos - 35) : pos + max_sessions + 35]
            try:
                outcome = evaluate_bars(
                    entry=close_v,
                    target=target_v,
                    stop=stop_v,
                    bars=bars_win,
                    entry_date=d_str,
                    cursor=d_str,
                    max_sessions=max_sessions,
                    profit_protection=SAUDI_PROFIT_PROTECTION_POLICY,
                )
            except CorporateActionDiscontinuity:
                continue
            if outcome["status"] in ("win", "loss"):
                trades.append({
                    "symbol": sym,
                    "entry_date": d_str,
                    "month": d_str[:7],
                    "closed_on": outcome["closed_on"],
                    "status": outcome["status"],
                    "pl_pct": float(outcome["profit_loss_pct"]),
                    "exit_reason": outcome["exit_reason"],
                })
                cooldown_until[sym] = str(outcome["closed_on"])
                day_picks += 1

    return _summarize_trades(trades, signals_raw=int(mask.sum()))


def _summarize_trades(trades: List[Dict[str, Any]], signals_raw: int = 0) -> Dict[str, Any]:
    def _agg(sub: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not sub:
            return {"trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0, "profit_factor": 0.0, "total_return_pct": 0.0, "avg_pl_pct": 0.0, "max_drawdown_pct": 0.0}
        wins = [t["pl_pct"] for t in sub if t["status"] == "win"]
        losses = [t["pl_pct"] for t in sub if t["status"] == "loss"]
        gw = float(sum(max(0.0, w) for w in wins))
        gl = float(sum(abs(min(0.0, l)) for l in losses))
        pf = round(gw / gl, 3) if gl > 0 else (99.0 if gw > 0 else 0.0)
        eq = 1.0; pk = 1.0; dd = 0.0
        for t in sorted(sub, key=lambda x: x["entry_date"]):
            eq *= (1.0 + 0.10 * (t["pl_pct"] / 100.0))
            pk = max(pk, eq)
            dd = max(dd, (pk - eq) / pk * 100.0)
        return {
            "trades": len(sub),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(sub) * 100.0, 1),
            "profit_factor": pf,
            "total_return_pct": round((eq - 1.0) * 100.0, 2),
            "avg_pl_pct": round(float(np.mean([t["pl_pct"] for t in sub])), 2),
            "max_drawdown_pct": round(dd, 2),
        }

    overall = _agg(trades)
    by_m_raw: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in trades:
        by_m_raw[t["month"]].append(t)
    by_month = {m: _agg(by_m_raw[m]) for m in sorted(by_m_raw.keys())}
    overall["signals_raw"] = signals_raw
    overall["by_month"] = by_month
    return overall


def _select_stationary_predictors(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    cols: List[str] = []
    for c in df.columns:
        if c in STATIONARY_EXCLUDE_COLS:
            continue
        if c == "sector" or is_numeric_dtype(df[c]):
            cols.append(c)
    cat_cols = ["sector"] if "sector" in cols else []
    return cols, cat_cols


def _optimize_egx_thresholds(
    df_dev: pd.DataFrame,
    y_dev: np.ndarray,
    p_dev: np.ndarray,
    m_dev: np.ndarray,
    p_tune_ref: np.ndarray,
    m_tune_ref: np.ndarray,
    bars_dict: Dict[str, List[Dict[str, Any]]],
    date_pos: Dict[str, Dict[str, int]],
    healthy_dates: set,
    look_forward_days: int,
) -> Tuple[float, float, Dict[str, Any]]:
    base_rate = float(np.mean(y_dev))
    best_score = -1e9
    best_p_th = float(np.quantile(p_tune_ref, 0.90))
    best_m_th = float(np.quantile(m_tune_ref, 0.50))
    best_stats: Dict[str, Any] = {}

    for p_q in (0.88, 0.90, 0.92, 0.94):
        p_th = float(np.quantile(p_tune_ref, p_q))
        for m_q in (0.45, 0.55, 0.65):
            m_th = float(np.quantile(m_tune_ref, m_q))
            mask = (p_dev >= p_th) & (m_dev >= m_th)
            sig_n = int(mask.sum())
            if sig_n < 60:
                continue
            prec = float(y_dev[mask].mean())
            sim = simulate_trades_detailed(
                df_slice=df_dev,
                primary_probs=p_dev,
                meta_probs=m_dev,
                primary_threshold=p_th,
                meta_threshold=m_th,
                bars_dict=bars_dict,
                date_pos=date_pos,
                healthy_dates=healthy_dates,
                max_sessions=look_forward_days,
                top_k_per_day=3,
                market_regime_filter=True,
            )
            if sim["trades"] < 5:
                continue
            score = (prec - base_rate) * 3.0 + min(sim["profit_factor"], 4.0) * 0.30 + (sim["win_rate"] / 100.0) * 0.70
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
        best_stats = {"dev_precision": round(float(y_dev[(p_dev >= best_p_th) & (m_dev >= best_m_th)].mean() if np.any((p_dev >= best_p_th) & (m_dev >= best_m_th)) else base_rate), 4), "dev_base_rate": round(base_rate, 4)}
    return round(best_p_th, 4), round(best_m_th, 4), best_stats


def train_egx_meta_model(
    history_cache: Dict[str, Any],
    df_compact: pd.DataFrame,
    model_rel_path: str,
    target_pct: float,
    stop_loss_pct: float,
    look_forward_days: int,
    splits: Dict[str, Tuple[str, str]],
    run_wf: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Train stationary EGX LightGBM + XGBoost Meta-Labeler within strictly specified purged splits."""
    t0 = time.time()
    url, key, _ = _get_egx_supabase()
    trainer = ModelTrainer(exchange="EGX", supabase_url=url, supabase_key=key)
    trainer.market_df = history_cache["market_df"].copy()
    trainer.market_index_symbol = "EGX30.INDX"
    trainer.market_index_loaded = True
    params = TradingParameters(
        entry_mode="next_open",
        look_forward_days=int(look_forward_days),
        barrier_mode="percent",
        target_pct=float(target_pct),
        stop_loss_pct=float(stop_loss_pct),
        min_history_needed=120,
        warmup_bars=120,
        require_volume_confirmation=False,
        min_volume_ratio=0.8,
    )
    trainer.params = params
    trainer.fundamentals_loaded = True

    df_labeled = label_egx_dataset(df_compact, history_cache["market_df"], params)
    feature_cols, cat_cols = _select_stationary_predictors(df_labeled)
    trainer.predictors = feature_cols
    trainer.categorical_features = cat_cols
    meta_feature_names = [c for c in META_CORE_CANDIDATES if c in feature_cols]

    d = pd.to_datetime(df_labeled["Date"])
    train_mask = d <= pd.Timestamp(splits["train_end"])
    ea_mask = (d >= pd.Timestamp(splits["ea_start"])) & (d <= pd.Timestamp(splits["ea_end"]))
    tune_fit_mask = (d >= pd.Timestamp(splits["tune_fit_start"])) & (d <= pd.Timestamp(splits["tune_fit_end"]))
    dev_cal_mask = (d >= pd.Timestamp(splits["dev_cal_start"])) & (d <= pd.Timestamp(splits["dev_cal_end"]))
    tune_all_mask = (d >= pd.Timestamp(splits["tune_fit_start"])) & (d <= pd.Timestamp(splits["dev_cal_end"]))
    dev_full_mask = d <= pd.Timestamp(splits["dev_cal_end"])

    if run_wf:
        wf_results, avg_wf_f1 = _run_purged_walk_forward_stationary(
            df_labeled.loc[dev_full_mask], feature_cols, cat_cols, n_splits=5, embargo_days=25
        )
        trainer.wf_splits_results = wf_results
    else:
        avg_wf_f1 = 0.0
        trainer.wf_splits_results = []

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
        n_estimators=1200,
        learning_rate=0.02,
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
        X_tr, y_tr,
        eval_set=[(X_ea, y_ea)],
        callbacks=[lgb.early_stopping(70, verbose=False)],
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

    dev_meta = xgb.XGBClassifier(
        n_estimators=400, max_depth=2, min_child_weight=100, learning_rate=0.02,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=10.0, reg_alpha=3.0,
        scale_pos_weight=1.0, objective="binary:logistic", eval_metric="logloss",
        early_stopping_rounds=40, random_state=42, n_jobs=-1,
    )
    dev_meta.fit(Xm_tf, y_tf, eval_set=[(Xm_dc, y_dc)], verbose=False)
    m_dc = np.asarray(dev_meta.predict_proba(Xm_dc)[:, 1], dtype=float)
    m_tu = np.asarray(dev_meta.predict_proba(Xm_tu)[:, 1], dtype=float)

    bars_dev, pos_dev = _build_bars_dict(
        history_cache["bars_by_symbol"],
        min_date=splits["dev_cal_start"],
        max_date=splits["dev_bars_max"],
    )
    healthy_dates = _healthy_tasi_dates(history_cache["market_df"])

    opt_p_th, meta_th, dev_stats = _optimize_egx_thresholds(
        df_dev=df_labeled.loc[dev_cal_mask],
        y_dev=y_dc,
        p_dev=p_dc,
        m_dev=m_dc,
        p_tune_ref=p_tu,
        m_tune_ref=m_tu,
        bars_dict=bars_dev,
        date_pos=pos_dev,
        healthy_dates=healthy_dates,
        look_forward_days=int(look_forward_days),
    )

    best_meta_rounds = max(60, int(getattr(dev_meta, "best_iteration", 120) or 120) + 1)
    meta_model = xgb.XGBClassifier(
        n_estimators=best_meta_rounds, max_depth=2, min_child_weight=100, learning_rate=0.02,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=10.0, reg_alpha=3.0,
        scale_pos_weight=1.0, objective="binary:logistic", eval_metric="logloss",
        random_state=42, n_jobs=-1,
    )
    meta_model.fit(Xm_tu, y_tu, verbose=False)

    best_it = getattr(primary_model, "best_iteration_", None)
    meta_feature_names_with_prob = list(meta_feature_names) + ["primary_prob"]
    save_metadata: Dict[str, Any] = {
        "target_pct": float(target_pct),
        "stop_loss_pct": float(stop_loss_pct),
        "barrier_mode": "percent",
        "barrierMode": "percent",
        "look_forward_days": int(look_forward_days),
        "use_volatility_label": False,
        "feature_preset": "stationary",
        "featurePreset": "stationary",
        "n_estimators": 1200,
        "best_iteration": best_it,
        "bestIteration": best_it,
        "learning_rate": 0.02,
        "training_samples": int(train_mask.sum()),
        "trainingSamples": int(train_mask.sum()),
        "use_intraday": False,
        "timeframe": "1d",
        "training_strategy": "purged_stationary_meta",
        "eval_metric": "logloss",
        "purged_cv_f1": avg_wf_f1,
        "has_meta_labeling": True,
        "optimal_threshold": float(opt_p_th),
        "meta_threshold": float(meta_th),
        "buyThreshold": float(opt_p_th),
        "precision": dev_stats.get("dev_precision", 0.5),
        "auc": 0.60,
    }

    os.makedirs(CANDIDATES_DIR, exist_ok=True)
    saved_path = trainer.save_meta_labeling_system(
        primary_model=primary_model,
        meta_model=meta_model,
        filename=model_rel_path,
        metadata=save_metadata,
        meta_threshold=float(meta_th),
        meta_feature_names=meta_feature_names_with_prob,
    )
    with open(saved_path, "rb") as f:
        artifact = pickle.load(f)

    info = {
        "saved_path": saved_path,
        "optimal_threshold": float(opt_p_th),
        "meta_threshold": float(meta_th),
        "train_samples": int(train_mask.sum()),
        "tune_samples": int(tune_all_mask.sum()),
        "dev_calibration": dev_stats,
        "best_iteration": best_it,
        "walk_forward_summary": artifact.get("walk_forward_summary") or {},
        "duration_s": round(time.time() - t0, 1),
    }
    print(
        f"[TRAINED] {model_rel_path} | th=({opt_p_th:.3f}/{meta_th:.3f}) | "
        f"dev_prec={dev_stats.get('dev_precision')} dev_WR={dev_stats.get('dev_sim_wr')}% "
        f"dev_PF={dev_stats.get('dev_sim_pf')} | best_it={best_it} | {info['duration_s']}s"
    )
    return artifact, info


def fetch_live_scan_results_summary() -> Dict[str, Any]:
    _, _, sb = _get_egx_supabase()
    rows = (
        sb.table("scan_results")
        .select("symbol,model_name,status,profit_loss_pct,created_at,updated_at")
        .eq("is_public", True)
        .gte("created_at", "2026-06-01")
        .order("created_at", desc=False)
        .limit(1000)
        .execute()
        .data
        or []
    )
    trades = []
    for r in rows:
        st = (r.get("status") or "").lower()
        if st not in ("win", "loss"):
            continue
        pl = float(r.get("profit_loss_pct") or 0.0)
        ed = str(r.get("created_at") or "")[:10]
        trades.append({
            "symbol": r.get("symbol"),
            "entry_date": ed,
            "month": ed[:7],
            "closed_on": str(r.get("updated_at") or "")[:10],
            "status": st,
            "pl_pct": pl,
            "exit_reason": r.get("model_name"),
        })
    return _summarize_trades(trades, signals_raw=len(rows))


def compute_classification_metrics(
    y_true: np.ndarray,
    primary_probs: np.ndarray,
    meta_probs: np.ndarray,
    p_th: float,
    m_th: float,
) -> Dict[str, Any]:
    mask = (primary_probs >= p_th) & (meta_probs >= m_th)
    p_auc = float(roc_auc_score(y_true, primary_probs)) if len(np.unique(y_true)) > 1 else 0.5
    m_auc = float(roc_auc_score(y_true, meta_probs)) if len(np.unique(y_true)) > 1 else 0.5
    ap = float(average_precision_score(y_true, primary_probs)) if len(np.unique(y_true)) > 1 else 0.0
    base = float(np.mean(y_true))
    q90 = float(np.quantile(primary_probs, 0.90))
    top10 = float(y_true[primary_probs >= q90].mean()) if np.any(primary_probs >= q90) else base
    prec = float(y_true[mask].mean()) if np.any(mask) else 0.0
    return {
        "auc": round(p_auc, 4),
        "meta_auc": round(m_auc, 4),
        "average_precision": round(ap, 4),
        "base_rate": round(base, 4),
        "precision": round(prec, 4),
        "top_decile_precision": round(top10, 4),
        "raw_signals": int(mask.sum()),
    }


def main():
    history_cache = load_egx_history_cached()
    df_compact, df_eval_full = load_or_build_egx_features(history_cache)

    # Strict OOS splits: ZERO rows >= 2026-05-01 touch training/tuning/calibration
    oos_splits = {
        "train_end": "2023-06-30",
        "ea_start": "2023-08-01",
        "ea_end": "2024-06-30",
        "tune_fit_start": "2024-08-01",
        "tune_fit_end": "2025-09-30",
        "dev_cal_start": "2025-11-01",
        "dev_cal_end": "2026-04-30",
        "dev_bars_max": "2026-05-31",
    }

    print("\n=== STEP A: Training Strict OOS Models (trained <= 2026-04-30, May purged) ===")
    egx_v2_oos_art, egx_v2_oos_info = train_egx_meta_model(
        history_cache, df_compact,
        model_rel_path="candidates/model_EGX_v2_oos.pkl",
        target_pct=0.08, stop_loss_pct=0.045, look_forward_days=20,
        splits=oos_splits, run_wf=True,
    )
    king_v2_oos_art, king_v2_oos_info = train_egx_meta_model(
        history_cache, df_compact,
        model_rel_path="candidates/KING_v2_oos.pkl",
        target_pct=0.10, stop_loss_pct=0.05, look_forward_days=20,
        splits=oos_splits, run_wf=False,
    )

    print("\n=== STEP B: Preparing Unseen Lockbox Labels & Scoring (2026-06-01 -> 2026-11-24) ===")
    lockbox_params = TradingParameters(
        entry_mode="next_open", look_forward_days=20, barrier_mode="percent",
        target_pct=0.08, stop_loss_pct=0.045, min_history_needed=120, warmup_bars=120,
        require_volume_confirmation=False, min_volume_ratio=0.8,
    )
    # Use eval bars window from 2026-04-01 so labeler has warmup + lookforward
    df_eval_slice = df_eval_full.sort_values(["Date", "symbol"]).reset_index(drop=True)
    # Build labels using full history for each symbol to keep warmup intact, then filter Date >= 2026-06-01
    df_labeled_eval = label_egx_dataset(df_compact, history_cache["market_df"], lockbox_params)
    df_labeled_eval = df_labeled_eval[df_labeled_eval["Date"] >= pd.Timestamp("2026-06-01")][["symbol", "Date", "Target"]].copy()
    df_oos_eval = df_eval_slice.merge(df_labeled_eval, on=["symbol", "Date"], how="inner").sort_values(["Date", "symbol"]).reset_index(drop=True)
    y_oos = df_oos_eval["Target"].astype(int).values
    print(f"OOS Lockbox rows (2026-06-01 -> 2026-11-24): {len(df_oos_eval):,} | Base Rate: {y_oos.mean():.3f}")

    old_egx_art = joblib.load(os.path.join(PROJECT_ROOT, "api", "models", "model_EGX.bin"))
    old_king_art = joblib.load(os.path.join(PROJECT_ROOT, "api", "models", "KING.bin"))

    bars_oos, pos_oos = _build_bars_dict(history_cache["bars_by_symbol"], min_date="2026-04-01")
    healthy_dates = _healthy_tasi_dates(history_cache["market_df"])

    models_to_eval = [
        ("old_model_EGX.bin", old_egx_art, float(old_egx_art.get("optimal_threshold", 0.667)), float(old_egx_art.get("meta_threshold", 0.60))),
        ("old_KING.bin", old_king_art, float(old_king_art.get("optimal_threshold", 0.615)), float(old_king_art.get("meta_threshold", 0.60))),
        ("new_model_EGX_v2_oos", egx_v2_oos_art, egx_v2_oos_info["optimal_threshold"], egx_v2_oos_info["meta_threshold"]),
        ("new_KING_v2_oos", king_v2_oos_art, king_v2_oos_info["optimal_threshold"], king_v2_oos_info["meta_threshold"]),
    ]

    comparison: Dict[str, Any] = {
        "live_scan_results": fetch_live_scan_results_summary(),
        "oos_lockbox_period": "2026-06-01 -> 2026-11-24",
        "models": {},
    }

    scored_cache: Dict[str, Tuple[np.ndarray, np.ndarray, float, float]] = {}
    for label, art, p_th, m_th in models_to_eval:
        _filt, p_probs, m_probs = score_artifact_df(art, df_oos_eval)
        scored_cache[label] = (p_probs, m_probs, p_th, m_th)
        clf_metrics = compute_classification_metrics(y_oos, p_probs, m_probs, p_th, m_th)
        sim_unfiltered = simulate_trades_detailed(
            df_oos_eval, p_probs, m_probs, p_th, m_th,
            bars_oos, pos_oos, healthy_dates,
            max_sessions=20, top_k_per_day=3, market_regime_filter=False,
        )
        sim_regime = simulate_trades_detailed(
            df_oos_eval, p_probs, m_probs, p_th, m_th,
            bars_oos, pos_oos, healthy_dates,
            max_sessions=20, top_k_per_day=3, market_regime_filter=True,
        )
        comparison["models"][label] = {
            "primary_threshold": p_th,
            "meta_threshold": m_th,
            "classification": clf_metrics,
            "sim_no_regime_filter": sim_unfiltered,
            "sim_with_regime_filter": sim_regime,
        }

    # Combined New Council v2 OOS (confirmation_boost style: primary passes EGX_v2, score boosted if KING_v2 also passes)
    p_e, m_e, pe_th, me_th = scored_cache["new_model_EGX_v2_oos"]
    p_k, m_k, pk_th, mk_th = scored_cache["new_KING_v2_oos"]
    both_mask_p = np.where((p_e >= pe_th) & (m_e >= me_th) & (p_k >= pk_th) & (m_k >= mk_th), 0.5 * (p_e + p_k), 0.0)
    both_mask_m = np.where(both_mask_p > 0, np.minimum(m_e, m_k), 0.0)
    comparison["models"]["new_council_consensus_oos"] = {
        "primary_threshold": 0.01,
        "meta_threshold": 0.01,
        "sim_no_regime_filter": simulate_trades_detailed(df_oos_eval, both_mask_p, both_mask_m, 0.01, 0.01, bars_oos, pos_oos, healthy_dates, max_sessions=20, top_k_per_day=3, market_regime_filter=False),
        "sim_with_regime_filter": simulate_trades_detailed(df_oos_eval, both_mask_p, both_mask_m, 0.01, 0.01, bars_oos, pos_oos, healthy_dates, max_sessions=20, top_k_per_day=3, market_regime_filter=True),
    }

    print("\n=== STEP C: Training Fresh Full-History Candidate Artifacts (Through 2026-10-20) ===")
    fresh_splits = {
        "train_end": "2024-06-30",
        "ea_start": "2024-08-01",
        "ea_end": "2025-04-30",
        "tune_fit_start": "2025-06-01",
        "tune_fit_end": "2026-05-31",
        "dev_cal_start": "2026-06-01",
        "dev_cal_end": "2026-10-20",
        "dev_bars_max": "2026-11-24",
    }
    _, fresh_egx_info = train_egx_meta_model(
        history_cache, df_compact,
        model_rel_path="candidates/model_EGX_v2_20261125.pkl",
        target_pct=0.08, stop_loss_pct=0.045, look_forward_days=20,
        splits=fresh_splits, run_wf=True,
    )
    _, fresh_king_info = train_egx_meta_model(
        history_cache, df_compact,
        model_rel_path="candidates/KING_v2_20261125.pkl",
        target_pct=0.10, stop_loss_pct=0.05, look_forward_days=20,
        splits=fresh_splits, run_wf=False,
    )
    comparison["fresh_candidates_20261125"] = {
        "note": "Trained through 2026-10-20 (NOT OOS on June-Oct 2026; saved strictly in api/models/candidates/)",
        "model_EGX_v2_20261125": fresh_egx_info,
        "KING_v2_20261125": fresh_king_info,
    }

    out_json = os.path.join(CANDIDATES_DIR, "egx_retrain_comparison_20261125.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)

    print("\n================ OOS COMPARISON SUMMARY (2026-06 -> 2026-11) ================")
    months = ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
    live = comparison["live_scan_results"]
    print(f"\n[LIVE scan_results] trades={live['trades']} W={live['wins']} L={live['losses']} WR={live['win_rate']}% Avg={live['avg_pl_pct']}% PF={live['profit_factor']}")
    for m in months:
        mm = live["by_month"].get(m)
        if mm:
            print(f"  {m}: tr={mm['trades']:2d} W={mm['wins']:2d} L={mm['losses']:2d} WR={mm['win_rate']:5.1f}% Avg={mm['avg_pl_pct']:+6.2f}% PF={mm['profit_factor']}")

    for label, mdata in comparison["models"].items():
        clf = mdata.get("classification") or {}
        print(f"\n[{label}] AUC={clf.get('auc')} metaAUC={clf.get('meta_auc')} Prec={clf.get('precision')} Top10%={clf.get('top_decile_precision')}")
        for mode_key in ("sim_no_regime_filter", "sim_with_regime_filter"):
            sim = mdata[mode_key]
            print(f"  {mode_key:23s}: tr={sim['trades']:3d} W={sim['wins']:2d} L={sim['losses']:2d} WR={sim['win_rate']:5.1f}% Avg={sim['avg_pl_pct']:+6.2f}% PF={sim['profit_factor']:5.2f} Ret={sim['total_return_pct']:+6.2f}% DD={sim['max_drawdown_pct']:5.2f}%")
            for m in months:
                mm = sim["by_month"].get(m)
                if mm:
                    print(f"    {m}: tr={mm['trades']:2d} W={mm['wins']:2d} L={mm['losses']:2d} WR={mm['win_rate']:5.1f}% Avg={mm['avg_pl_pct']:+6.2f}% PF={mm['profit_factor']}")

    print(f"\n[SAVED] Full comparison report -> {out_json}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
