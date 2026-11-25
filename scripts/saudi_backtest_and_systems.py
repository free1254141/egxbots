"""
Saudi Backtests & 3 Trading Systems Engine (TASI / Tadawul).

Uses the EXACT Egyptian (EGX) production engines and causal StrategyEngine rules
against real SAUDI_SUPABASE historical OHLCV data (`stock_prices` & `market_index`):
  1. `saudi_backtests_v1`      — Walk-forward ML backtests using `StrategyEngine`
                                 market/stock regime filters, technical filters,
                                 ATR barriers, and trailing profit protection
                                 (supports both `meta_labeling_system` and Booster .pkl).
  2. `saudi_short_swings_v1`   — System 2 via `api.short_swings_engine.compute_short_swings(exchange="TADAWUL")`
  3. `saudi_scanner_alerts_v1` — System 3 via `api.scanner_alerts_engine.run_scanner_alerts_simulation(exchange="TADAWUL")`
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pickle
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api.model_utils import align_pandas_categories_to_booster, get_primary_booster, reset_nested_boosters  # noqa: E402
from api.scanner_alerts_engine import run_scanner_alerts_simulation  # noqa: E402
from api.short_swings_engine import compute_short_swings  # noqa: E402
from api.stock_ai import (  # noqa: E402
    _LgbmBoosterClassifier,
    _MetaLabelingClassifier,
    _PcaTransformer,
    add_technical_indicators,
)
from api.strategy_engine import StrategyEngine  # noqa: E402
from api.train_exchange_model import add_massive_features, add_market_context  # noqa: E402
from scripts.saudi_pipeline_bootstrap import (  # noqa: E402
    KING_TASI_FEATURES,
    _init_saudi_client,
    load_saudi_market_and_prices,
)

COUNTRY_NAME = "Saudi Arabia"
SLIPPAGE = 0.0015  # 0.15% conservative execution slippage
DEFAULT_ML_MIN_TURNOVER = 15_000_000.0  # 15M SAR 20d avg daily turnover
ML_WARMUP_START = "2020-06-01"
SCANNER_WARMUP_START = "2023-10-01"
SAUDI_HISTORY_CACHE = Path(PROJECT_ROOT) / "api" / "data_cache" / "saudi_history_cache.pkl"
SAUDI_ML_FEATURES_CACHE = Path(PROJECT_ROOT) / "api" / "data_cache" / "saudi_ml_features_cache.pkl"

BACKTEST_EXIT_LABELS = {
    "target_hit": "تحقق الهدف 🎯",
    "trail_stop": "تأمين ربح / وقف متحرك 🛡️",
    "stop_loss": "وقف الخسارة 🛑",
    "max_time": "انتهاء المدة القصوى ⏱️",
}


def _compute_kpis_from_trades(
    trades: List[Dict[str, Any]],
    return_key: str = "return_pct",
    slots: float = 10.0,
) -> Dict[str, Any]:
    if not trades:
        return {
            "profit_factor": 0.0,
            "win_rate_pct": 0.0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_holding_days": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "top_win_pct": 0.0,
            "monthly_trades_avg": 0.0,
            "total_trades": 0,
            "wins_count": 0,
            "losses_count": 0,
        }

    ordered = sorted(trades, key=lambda t: str(t.get("exit_date") or ""))
    returns = [float(t.get(return_key, 0.0)) for t in ordered]
    sessions = [float(t.get("sessions") or t.get("holding_days") or 1) for t in ordered]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]

    win_rate = (len(wins) / len(returns)) * 100.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    avg_win = round(float(np.mean(wins)), 2) if wins else 0.0
    avg_loss = round(float(np.mean(losses)), 2) if losses else 0.0
    top_win = round(float(max(returns)), 2) if returns else 0.0
    avg_holding = round(float(np.mean(sessions)), 1) if sessions else 0.0

    trade_returns = np.array(returns, dtype=float) / 100.0
    equity_curve = np.cumprod(1.0 + (trade_returns / max(1.0, slots)))
    total_return = round(float((equity_curve[-1] - 1.0) * 100.0), 2) if len(equity_curve) else 0.0

    curve_with_init = np.concatenate(([1.0], equity_curve))
    peak = np.maximum.accumulate(curve_with_init)
    drawdowns = (curve_with_init - peak) / peak
    max_dd = round(float(abs(np.min(drawdowns)) * 100.0), 2) if len(drawdowns) else 0.0

    exit_dates = [str(t.get("exit_date") or "")[:10] for t in ordered if t.get("exit_date")]
    if exit_dates:
        try:
            min_d = dt.date.fromisoformat(min(exit_dates))
            max_d = dt.date.fromisoformat(max(exit_dates))
            months = max(1, (max_d.year - min_d.year) * 12 + (max_d.month - min_d.month) + 1)
            monthly_avg = round(len(trades) / months, 1)
        except Exception:
            monthly_avg = round(len(trades) / 12.0, 1)
    else:
        monthly_avg = 0.0

    return {
        "profit_factor": pf,
        "win_rate_pct": round(win_rate, 1),
        "total_return_pct": total_return,
        "max_drawdown_pct": max_dd,
        "avg_holding_days": avg_holding,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "top_win_pct": top_win,
        "monthly_trades_avg": monthly_avg,
        "total_trades": len(trades),
        "wins_count": len(wins),
        "losses_count": len(losses),
    }


def _load_saudi_stocks_meta(sb) -> Tuple[List[str], Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    res = sb.table("stocks").select("symbol,name,name_ar,sector").eq("exchange", "TADAWUL").execute()
    meta: Dict[str, Dict[str, Any]] = {}
    stocks_by_sym: Dict[str, Dict[str, Any]] = {}
    symbols: List[str] = []
    for row in res.data or []:
        sym = str(row.get("symbol") or "").strip()
        if not sym:
            continue
        symbols.append(sym)
        stocks_by_sym[sym] = row
        meta[sym] = {
            "name_ar": row.get("name_ar") or row.get("name") or sym,
            "name_en": row.get("name") or sym,
            "sector": row.get("sector") or "عام",
        }
    return sorted(set(symbols)), meta, stocks_by_sym


def _fetch_paginated_rows(
    sb,
    table: str,
    columns: str,
    *,
    gt_date: Optional[str] = None,
    eq_filters: Optional[Dict[str, Any]] = None,
    page_size: int = 1000,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        q = sb.table(table).select(columns)
        for col, val in (eq_filters or {}).items():
            q = q.eq(col, val)
        if gt_date:
            q = q.gt("date", gt_date)
        res = q.order("date", desc=False).range(offset, offset + page_size - 1).execute()
        batch = res.data or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _merge_bar_rows(
    base_df: Optional[pd.DataFrame],
    new_rows: List[Dict[str, Any]],
) -> Optional[pd.DataFrame]:
    if not new_rows:
        return base_df
    add_df = pd.DataFrame(new_rows)
    if add_df.empty:
        return base_df
    add_df["Date"] = pd.to_datetime(add_df["date"], errors="coerce")
    add_df = add_df.dropna(subset=["Date"]).set_index("Date").sort_index()
    col_map = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    add_norm = pd.DataFrame(index=add_df.index)
    for src, dst in col_map.items():
        if src in add_df.columns:
            add_norm[dst] = pd.to_numeric(add_df[src], errors="coerce")
    add_norm = add_norm.dropna(subset=["Close"])
    if base_df is None or base_df.empty:
        return add_norm
    combined = pd.concat([base_df, add_norm])
    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    return combined


def _load_saudi_history_for_systems(
    sb,
    symbols: List[str],
    meta: Dict[str, Dict[str, Any]],
    stocks_by_sym: Dict[str, Dict[str, Any]],
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], Dict[str, Dict[str, Any]]]:
    """Load full Saudi OHLCV from local snapshot + incremental SAUDI_SUPABASE tail."""
    fund_meta: Dict[str, Dict[str, Any]] = {}
    if SAUDI_HISTORY_CACHE.exists():
        try:
            with open(SAUDI_HISTORY_CACHE, "rb") as f:
                cached = pickle.load(f)
            bars_by_symbol: Dict[str, pd.DataFrame] = dict(cached.get("bars_by_symbol") or {})
            market_df: pd.DataFrame = cached.get("market_df")
            max_price_date = str(cached.get("max_price_date") or "")[:10]
            for row in cached.get("stocks_rows") or []:
                sym = str(row.get("symbol") or "").strip()
                if sym and sym not in stocks_by_sym:
                    stocks_by_sym[sym] = row
                if sym and sym not in meta:
                    meta[sym] = {
                        "name_ar": row.get("name_ar") or row.get("name") or sym,
                        "name_en": row.get("name") or sym,
                        "sector": row.get("sector") or "عام",
                    }
            for row in cached.get("fund_rows") or []:
                sym = str(row.get("symbol") or "").strip()
                if sym:
                    fund_meta[sym] = row.get("data") or {}

            if bars_by_symbol and market_df is not None and not market_df.empty and max_price_date:
                tail_prices = _fetch_paginated_rows(
                    sb,
                    "stock_prices",
                    "symbol,date,open,high,low,close,volume",
                    gt_date=max_price_date,
                    eq_filters={"exchange": "TADAWUL"},
                )
                if tail_prices:
                    by_sym: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                    for r in tail_prices:
                        sym = str(r.get("symbol") or "").strip()
                        if sym:
                            by_sym[sym].append(r)
                    for sym, sym_rows in by_sym.items():
                        merged = _merge_bar_rows(bars_by_symbol.get(sym), sym_rows)
                        if merged is not None and not merged.empty:
                            bars_by_symbol[sym] = merged

                tail_idx = _fetch_paginated_rows(
                    sb,
                    "market_index",
                    "date,close,ret",
                    gt_date=max_price_date,
                    eq_filters={"exchange": "TADAWUL"},
                )
                if tail_idx:
                    idx_add = pd.DataFrame(tail_idx)
                    idx_add["date"] = pd.to_datetime(idx_add["date"], errors="coerce")
                    idx_add = idx_add.dropna(subset=["date"]).set_index("date").sort_index()
                    for col in ("close", "ret"):
                        if col in idx_add.columns:
                            idx_add[col] = pd.to_numeric(idx_add[col], errors="coerce")
                    market_df = pd.concat([market_df, idx_add[[c for c in ("close", "ret") if c in idx_add.columns]]])
                    market_df = market_df[~market_df.index.duplicated(keep="last")].sort_index()
                return market_df, bars_by_symbol, fund_meta
        except Exception as exc:
            print(f"[SAUDI-SYSTEMS] History cache read failed, loading from Supabase: {exc}")

    market_df, _, bars_by_symbol = load_saudi_market_and_prices(sb, symbols)
    return market_df, bars_by_symbol, fund_meta


def _build_sym_feat_worker(
    args: Tuple[str, pd.DataFrame, pd.DataFrame, Dict[Any, float], str, str, Dict[str, Any]],
) -> Optional[pd.DataFrame]:
    sym, df_sym, market_df, sec_avg_for_sec, sec, ind, fm = args
    df_sym = df_sym.copy()
    df_sym["sector"] = sec
    df_sym["industry"] = ind
    df_sym["marketCap"] = fm.get("marketCap") or 0.0
    df_sym["peRatio"] = fm.get("peRatio") or 0.0
    df_sym["eps"] = fm.get("eps") or 0.0
    df_sym["dividendYield"] = fm.get("dividendYield") or 0.0
    df_sym["stock_daily_return"] = df_sym["Close"].pct_change().fillna(0.0)
    df_sym["sector_avg_return"] = [sec_avg_for_sec.get(dt_idx, 0.0) for dt_idx in df_sym.index]

    feat = add_technical_indicators(df_sym)
    if feat.empty:
        return None
    for col in (
        "marketCap",
        "peRatio",
        "eps",
        "dividendYield",
        "sector",
        "industry",
        "sector_avg_return",
        "stock_daily_return",
    ):
        if col in df_sym.columns and col not in feat.columns:
            feat[col] = df_sym[col].values if len(df_sym[col]) == len(feat) else df_sym[col].iloc[-1]
    feat = add_massive_features(feat)
    feat = add_market_context(feat, market_df)
    feat = feat.loc[:, ~feat.columns.duplicated()].copy()
    feat["symbol"] = sym
    feat["Date"] = feat.index
    feat["date_str"] = feat.index.strftime("%Y-%m-%d")
    return feat.reset_index(drop=True)


def _ensure_stationary_derived_features(df_all: pd.DataFrame) -> pd.DataFrame:
    """Compute stationary price ratios & causal lagged sector relative strength matching trainer."""
    if df_all.empty or "Close" not in df_all.columns:
        return df_all
    out = df_all.copy()
    close_s = pd.to_numeric(out["Close"], errors="coerce").replace(0.0, np.nan)
    if "ATR_pct" not in out.columns:
        atr_col = pd.to_numeric(out["ATR_14"], errors="coerce") if "ATR_14" in out.columns else 0.0
        out["ATR_pct"] = (atr_col / close_s).fillna(0.02)
    if "SMA_50_Ratio" not in out.columns and "SMA_50" in out.columns:
        sma50 = pd.to_numeric(out["SMA_50"], errors="coerce").replace(0.0, np.nan)
        out["SMA_50_Ratio"] = (close_s / sma50 - 1.0).fillna(0.0)
    if "EMA_50_Ratio" not in out.columns and "EMA_50" in out.columns:
        ema50 = pd.to_numeric(out["EMA_50"], errors="coerce").replace(0.0, np.nan)
        out["EMA_50_Ratio"] = (close_s / ema50 - 1.0).fillna(0.0)
    if {"symbol", "Date", "sector"}.issubset(out.columns):
        ret_1d = out.groupby("symbol")["Close"].pct_change().fillna(0.0)
        tmp = pd.DataFrame({
            "Date": out["Date"].values,
            "sector": out["sector"].astype(str).values,
            "ret_1d": ret_1d.values,
        })
        sec_daily = (
            tmp.groupby(["Date", "sector"], as_index=False)["ret_1d"]
            .mean()
            .rename(columns={"ret_1d": "sec_ret"})
            .sort_values(["sector", "Date"])
        )
        sec_daily["sec_ret_lag1"] = sec_daily.groupby("sector")["sec_ret"].shift(1).fillna(0.0)
        merged_sec = pd.DataFrame({"Date": out["Date"].values, "sector": out["sector"].astype(str).values}).merge(
            sec_daily[["Date", "sector", "sec_ret_lag1"]],
            on=["Date", "sector"],
            how="left",
        )
        stock_lag1 = ret_1d.groupby(out["symbol"]).shift(1).fillna(0.0).values
        sec_lag1 = merged_sec["sec_ret_lag1"].fillna(0.0).values
        out["feat_sector_rel_strength"] = np.clip(stock_lag1 - sec_lag1, -0.3, 0.3)
    return out


def _build_or_load_ml_features_df(
    bars_by_symbol: Dict[str, pd.DataFrame],
    market_df: pd.DataFrame,
    stocks_by_sym: Dict[str, Dict[str, Any]],
    fund_meta: Dict[str, Dict[str, Any]],
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    sub_bars: Dict[str, pd.DataFrame] = {}
    max_dates: List[str] = []
    for sym, bdf in bars_by_symbol.items():
        if bdf is None or bdf.empty:
            continue
        sub = bdf[bdf.index >= ML_WARMUP_START].copy()
        if len(sub) >= 80:
            sub_bars[sym] = sub
            max_dates.append(sub.index[-1].strftime("%Y-%m-%d"))

    sig_max_date = max(max_dates) if max_dates else ""
    sig_sym_count = len(sub_bars)

    if SAUDI_ML_FEATURES_CACHE.exists():
        try:
            with open(SAUDI_ML_FEATURES_CACHE, "rb") as f:
                cached = pickle.load(f)
            if (
                isinstance(cached, dict)
                and cached.get("max_date") == sig_max_date
                and int(cached.get("sym_count") or -1) == sig_sym_count
                and isinstance(cached.get("df"), pd.DataFrame)
            ):
                df_cached = cached["df"]
                if int(cached.get("feat_v") or 1) < 2 or "ATR_pct" not in df_cached.columns:
                    df_cached = _ensure_stationary_derived_features(df_cached)
                    try:
                        with open(SAUDI_ML_FEATURES_CACHE, "wb") as fw:
                            pickle.dump({"max_date": sig_max_date, "sym_count": sig_sym_count, "feat_v": 2, "df": df_cached}, fw)
                    except Exception:
                        pass
                return df_cached, sub_bars
        except Exception:
            pass

    ret_frames: List[pd.DataFrame] = []
    for sym, bdf in sub_bars.items():
        sm = stocks_by_sym.get(sym, {})
        sec = sm.get("sector") or "Unknown"
        r1 = bdf["Close"].astype(float).pct_change().fillna(0.0)
        ret_frames.append(pd.DataFrame({"Date": bdf.index, "sector": sec, "ret": r1.values}))

    sec_maps: Dict[str, Dict[Any, float]] = {}
    if ret_frames:
        all_rets = pd.concat(ret_frames, ignore_index=True)
        sec_grouped = all_rets.groupby(["sector", "Date"])["ret"].mean()
        for sec in sec_grouped.index.get_level_values(0).unique():
            sec_maps[str(sec)] = sec_grouped.loc[sec].to_dict()

    jobs = []
    for sym, bdf in sub_bars.items():
        sm = stocks_by_sym.get(sym, {})
        fm = fund_meta.get(sym, {})
        sec = sm.get("sector") or fm.get("sector") or "Unknown"
        ind = sm.get("industry") or fm.get("industry") or "Unknown"
        jobs.append((sym, bdf, market_df, sec_maps.get(str(sec), {}), sec, ind, fm))

    parts: List[pd.DataFrame] = []
    if jobs:
        workers = min(4, max(1, os.cpu_count() or 2), len(jobs))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            parts = [r for r in pool.map(_build_sym_feat_worker, jobs) if r is not None]

    df_all = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if not df_all.empty:
        df_all = _ensure_stationary_derived_features(df_all)
        try:
            SAUDI_ML_FEATURES_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with open(SAUDI_ML_FEATURES_CACHE, "wb") as f:
                pickle.dump({"max_date": sig_max_date, "sym_count": sig_sym_count, "feat_v": 2, "df": df_all}, f)
        except Exception:
            pass
    return df_all, sub_bars


def score_model_artifact(
    artifact: Dict[str, Any],
    df_all: pd.DataFrame,
    *,
    fallback_features: Optional[List[str]] = None,
) -> Tuple[np.ndarray, float, Dict[str, Any]]:
    """Score both `meta_labeling_system` pickles and legacy LightGBM Booster pickles."""
    if df_all.empty:
        return np.zeros(0, dtype=float), 0.5, {"kind": "empty", "num_features": 0}

    if artifact.get("kind") == "meta_labeling_system" or "primary_model" in artifact:
        pm = artifact["primary_model"]
        booster = lgb.Booster(model_str=pm["model_str"])
        pca_transformer = None
        if pm.get("pca") is not None and pm.get("scaler") is not None and pm.get("pca_features"):
            pca_transformer = _PcaTransformer(pm["pca"], pm["scaler"], pm["pca_features"])

        primary_clf = _LgbmBoosterClassifier(booster, 0.5, pca_transformer=pca_transformer)
        meta_threshold = float(artifact.get("meta_threshold") or 0.52)
        meta_clf = _MetaLabelingClassifier(
            primary_model=primary_clf,
            meta_model=artifact["meta_model"],
            meta_feature_names=artifact["meta_feature_names"],
            meta_threshold=meta_threshold,
            return_raw_prob=False,
        )

        f_names = list(pm["feature_names"])
        pca_feats = list(pm.get("pca_features") or [])
        raw_needed = (
            [c for c in f_names if not str(c).startswith("PCA_Momentum_")] + pca_feats
            if pca_feats
            else f_names
        )
        meta_extra = [c for c in (artifact.get("meta_feature_names") or []) if c != "primary_prob" and c not in raw_needed]
        use_cols = list(dict.fromkeys(raw_needed + meta_extra))

        X = pd.DataFrame(index=df_all.index)
        for col in use_cols:
            X[col] = df_all[col] if col in df_all.columns else 0.0

        cat_cols = [c for c in (pm.get("categorical_features") or []) if c in X.columns]
        for col in cat_cols:
            X[col] = (
                X[col]
                .astype(str)
                .replace(["nan", "None", "", "0", "0.0"], "Unknown")
                .fillna("Unknown")
                .astype("category")
            )
        non_cat = [c for c in X.columns if c not in set(cat_cols)]
        for col in non_cat:
            if not is_numeric_dtype(X[col]):
                X[col] = pd.to_numeric(X[col], errors="coerce")
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

        probs = np.asarray(meta_clf.predict_proba(X)[:, 1], dtype=float)
        thresh = float(artifact.get("optimal_threshold") or artifact.get("threshold") or 0.35)
        info = {
            "kind": "meta_labeling_system",
            "num_features": len(f_names),
            "meta_threshold": meta_threshold,
            "trading_parameters": artifact.get("trading_parameters") or {},
        }
        return probs, thresh, info

    booster = lgb.Booster(model_str=artifact["model_str"])
    feat_names = list(artifact.get("feature_names") or fallback_features or KING_TASI_FEATURES)
    X = pd.DataFrame(index=df_all.index)
    for col in feat_names:
        X[col] = pd.to_numeric(df_all[col], errors="coerce") if col in df_all.columns else 0.0
    X = X.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    probs = np.asarray(booster.predict(X), dtype=float)
    thresh = float(artifact.get("optimal_threshold") or artifact.get("threshold") or 0.45)
    info = {
        "kind": "lgbm_booster",
        "num_features": len(feat_names),
        "meta_threshold": float(artifact.get("meta_threshold") or thresh),
        "trading_parameters": artifact.get("trading_parameters") or {},
    }
    return probs, thresh, info


def _prepare_market_and_signal_cache(
    sub_bars: Dict[str, pd.DataFrame],
    market_df: pd.DataFrame,
    min_turnover: float = DEFAULT_ML_MIN_TURNOVER,
) -> Dict[str, Any]:
    """Precompute causal per-day TASI gates, per-symbol positions, and StrategyEngine filters."""
    idx_close_col = "close" if "close" in market_df.columns else "Close"
    idx_c = pd.to_numeric(market_df[idx_close_col], errors="coerce").ffill().astype(float)
    idx_e20 = idx_c.ewm(span=20, adjust=False).mean()
    idx_e50 = idx_c.ewm(span=50, adjust=False).mean()

    idx_dates = [ts.strftime("%Y-%m-%d") for ts in market_df.index]
    idx_regime: Dict[str, str] = {}
    for i, d_str in enumerate(idx_dates):
        idx_regime[d_str] = (
            "SIDEWAYS"
            if i < 60
            else StrategyEngine.detect_market_regime(market_df.iloc[: i + 1], use_market_regime=True)
        )
    idx_above_e20 = {d_str: bool(idx_c.iloc[i] > idx_e20.iloc[i]) for i, d_str in enumerate(idx_dates)}
    idx_above_e50 = {d_str: bool(idx_c.iloc[i] > idx_e50.iloc[i]) for i, d_str in enumerate(idx_dates)}

    date_pos: Dict[str, Dict[str, int]] = {}
    turn_by_sym: Dict[str, np.ndarray] = {}
    for sym, bdf in sub_bars.items():
        date_pos[sym] = {ts.strftime("%Y-%m-%d"): idx for idx, ts in enumerate(bdf.index)}
        turn_by_sym[sym] = (
            (bdf["Close"].astype(float) * bdf["Volume"].astype(float))
            .rolling(20, min_periods=1)
            .mean()
            .values
        )

    return {
        "idx_regime": idx_regime,
        "idx_above_e20": idx_above_e20,
        "idx_above_e50": idx_above_e50,
        "date_pos": date_pos,
        "turn_by_sym": turn_by_sym,
        "min_turnover": float(min_turnover),
        "signal_state_cache": {},
    }


def _get_symbol_strategy_state(
    market_cache: Dict[str, Any],
    sub_bars: Dict[str, pd.DataFrame],
    sym: str,
    d_str: str,
    *,
    use_trend_filter: bool,
    min_turnover: float,
) -> Optional[Tuple[str, bool, pd.DataFrame, int]]:
    bdf = sub_bars.get(sym)
    pos = market_cache["date_pos"].get(sym, {}).get(d_str)
    if bdf is None or pos is None or pos + 1 >= len(bdf) or pos < 60:
        return None
    avg_turn = float(market_cache["turn_by_sym"][sym][pos])
    if not np.isfinite(avg_turn) or avg_turn < min_turnover:
        return None

    key = (sym, d_str, bool(use_trend_filter))
    cached = market_cache["signal_state_cache"].get(key)
    hist = bdf.iloc[max(0, pos - 250) : pos + 1]
    if cached is not None:
        return cached[0], cached[1], hist, pos

    stk_reg = StrategyEngine.detect_market_regime(
        hist,
        use_market_regime=True,
        regime_adx_threshold=14.0,
    )
    ok_tech, _ = StrategyEngine.check_technical_filters(
        hist,
        min_volume_ratio=0.3,
        use_trend_filter=use_trend_filter,
        use_rsi_filter=True,
    )
    market_cache["signal_state_cache"][key] = (stk_reg, bool(ok_tech))
    return stk_reg, bool(ok_tech), hist, pos


def simulate_radar_strategy_backtest(
    *,
    model_name: str,
    df_all: pd.DataFrame,
    prob_col: str,
    threshold: float,
    sub_bars: Dict[str, pd.DataFrame],
    market_cache: Dict[str, Any],
    meta: Dict[str, Dict[str, Any]],
    start_date: str = "2022-01-01",
    end_date: Optional[str] = None,
    index_gate: str = "above_ema50",
    use_trend_filter: bool = True,
    adaptive_exits: bool = True,
    barrier_mode: str = "atr",
    atr_tp_mult: float = 3.0,
    atr_sl_mult: float = 1.5,
    max_sessions: int = 15,
    max_concurrent: int = 10,
    min_turnover: float = DEFAULT_ML_MIN_TURNOVER,
    trail_be_pct: float = 0.04,
    trail_lock_trigger_pct: float = 0.06,
    now_iso: str = "",
) -> Dict[str, Any]:
    """Run exact EGX StrategyEngine + backtest_radar trailing-ATR simulation over Saudi data."""
    if df_all.empty or prob_col not in df_all.columns:
        end_d = end_date or start_date
        return {
            "id": f"saudi_bt_{model_name.lower()}_{start_date.replace('-', '')}_{end_d.replace('-', '')}",
            "model_name": model_name,
            "exchange": "TADAWUL",
            "market": "TASI",
            "currency": "SAR",
            "is_public": True,
            "created_at": now_iso,
            "start_date": start_date,
            "end_date": end_d,
            "status": "completed",
            "status_msg": "No signals in window",
            "target_pct": atr_tp_mult,
            "stop_loss_pct": atr_sl_mult,
            "look_forward_days": max_sessions,
            "meta_threshold": round(threshold, 3),
            "capital": 100_000.0,
            "net_profit": 0.0,
            "win_rate": 0.0,
            "profit_pct": 0.0,
            "post_council_profit_pct": 0.0,
            "post_council_win_rate": 0.0,
            "total_trades": 0,
            "avg_return_per_trade": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_holding_days": 0.0,
            "trades": [],
        }

    mask = df_all["date_str"] >= start_date
    if end_date:
        mask &= df_all["date_str"] <= end_date
    win_df = df_all.loc[mask, ["symbol", "date_str", prob_col]]
    all_dates = sorted(win_df["date_str"].unique())
    actual_end = all_dates[-1] if all_dates else (end_date or start_date)

    sig_df = win_df[win_df[prob_col] >= threshold].sort_values(
        ["date_str", prob_col], ascending=[True, False]
    )
    candidates_by_date: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
    for row in sig_df.itertuples(index=False):
        candidates_by_date[str(row.date_str)].append((str(row.symbol), float(getattr(row, prob_col))))

    idx_above_e50 = market_cache["idx_above_e50"]
    idx_above_e20 = market_cache["idx_above_e20"]
    idx_regime = market_cache["idx_regime"]

    date_to_g_idx = {d: idx for idx, d in enumerate(all_dates)}
    active_until_idx: Dict[str, int] = {}
    open_positions_exits: List[int] = []
    trades: List[Dict[str, Any]] = []
    capital = 100_000.0

    for g_idx, d_str in enumerate(all_dates):
        open_positions_exits = [ex_i for ex_i in open_positions_exits if ex_i > g_idx]
        if index_gate == "above_ema50" and not idx_above_e50.get(d_str, False):
            continue
        if index_gate == "above_ema20" and not idx_above_e20.get(d_str, False):
            continue
        if index_gate == "not_bear" and idx_regime.get(d_str, "SIDEWAYS") == "BEAR":
            continue
        if len(open_positions_exits) >= max_concurrent:
            continue

        picked_today = 0
        for sym, prob in candidates_by_date.get(d_str, []):
            if len(open_positions_exits) >= max_concurrent or picked_today >= 3:
                break
            if active_until_idx.get(sym, -1) >= g_idx:
                continue

            state = _get_symbol_strategy_state(
                market_cache,
                sub_bars,
                sym,
                d_str,
                use_trend_filter=use_trend_filter,
                min_turnover=min_turnover,
            )
            if state is None:
                continue
            stk_reg, ok_tech, hist, pos = state
            if stk_reg == "BEAR" or not ok_tech:
                continue

            bdf = sub_bars[sym]
            next_bar = bdf.iloc[pos + 1]
            if float(next_bar["Volume"]) <= 0 or float(next_bar["Open"]) <= 0:
                continue

            entry_price = float(next_bar["Open"]) * (1.0 + SLIPPAGE)
            entry_date = bdf.index[pos + 1].strftime("%Y-%m-%d")

            if str(barrier_mode).lower() == "percent":
                tp_frac = atr_tp_mult / 100.0 if atr_tp_mult > 1.0 else atr_tp_mult
                sl_frac = atr_sl_mult / 100.0 if atr_sl_mult > 1.0 else atr_sl_mult
                tp_price = entry_price * (1.0 + tp_frac)
                sl_price = entry_price * (1.0 - sl_frac)
            else:
                tm, sm = atr_tp_mult, atr_sl_mult
                if adaptive_exits:
                    if stk_reg == "STRONG_BULL":
                        tm, sm = 5.0, 2.0
                    elif stk_reg == "BULL":
                        tm, sm = 3.0, 1.5
                    elif stk_reg == "SIDEWAYS":
                        tm, sm = 2.5, 1.2
                    else:
                        tm, sm = 2.0, 1.0

                tp_price, sl_price = StrategyEngine.calculate_atr_exits(
                    hist,
                    entry_price,
                    0.08,
                    0.045,
                    use_atr_exits=True,
                    atr_sl_multiplier=sm,
                    atr_tp_multiplier=tm,
                    exit_mode="atr",
                )

            fwd = bdf.iloc[pos + 1 : min(len(bdf), pos + 1 + max_sessions)]
            if len(fwd) < 2:
                continue

            exit_price = float(fwd["Close"].iloc[-1]) * (1.0 - SLIPPAGE)
            exit_date = fwd.index[-1].strftime("%Y-%m-%d")
            reason_code = "max_time"
            sessions_held = len(fwd)
            be_armed = False
            lock_armed = False

            for s_idx, (f_ts, f_bar) in enumerate(fwd.iterrows(), start=1):
                f_open = float(f_bar["Open"])
                f_high = float(f_bar["High"])
                f_low = float(f_bar["Low"])
                if f_low <= sl_price:
                    raw_fill = f_open if f_open <= sl_price else sl_price
                    exit_price = raw_fill * (1.0 - SLIPPAGE)
                    exit_date = f_ts.strftime("%Y-%m-%d")
                    reason_code = "trail_stop" if (be_armed or lock_armed) else "stop_loss"
                    sessions_held = s_idx
                    break
                if f_high >= tp_price:
                    exit_price = tp_price * (1.0 - SLIPPAGE)
                    exit_date = f_ts.strftime("%Y-%m-%d")
                    reason_code = "target_hit"
                    sessions_held = s_idx
                    break
                if trail_lock_trigger_pct and not lock_armed and (f_high / entry_price - 1.0) >= trail_lock_trigger_pct:
                    sl_price = max(sl_price, entry_price * 1.04)
                    lock_armed = True
                elif trail_be_pct and not be_armed and (f_high / entry_price - 1.0) >= trail_be_pct:
                    sl_price = max(sl_price, entry_price * 1.003)
                    be_armed = True

            ret_pct = ((exit_price / entry_price) - 1.0) * 100.0
            m_info = meta.get(sym, {})
            trades.append({
                "symbol": sym,
                "name_ar": m_info.get("name_ar", sym),
                "name_en": m_info.get("name_en", sym),
                "sector": m_info.get("sector", "عام"),
                "entry_date": entry_date,
                "exit_date": exit_date,
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "profit_pct": round(ret_pct, 2),
                "profit_loss_pct": round(ret_pct, 2),
                "status": "win" if ret_pct > 0 else "loss",
                "exit_reason": BACKTEST_EXIT_LABELS.get(reason_code, reason_code),
                "exit_reason_code": reason_code,
                "regime": stk_reg,
                "sessions": sessions_held,
                "confidence": round(prob, 4),
            })

            exit_g_idx = date_to_g_idx.get(exit_date, g_idx + sessions_held)
            active_until_idx[sym] = exit_g_idx + 2
            open_positions_exits.append(exit_g_idx)
            picked_today += 1

    kpis = _compute_kpis_from_trades(trades, return_key="profit_pct", slots=float(max_concurrent))
    total_trades = len(trades)
    avg_ret = round(float(np.mean([t["profit_pct"] for t in trades])), 2) if trades else 0.0
    profit_pct = kpis["total_return_pct"]
    net_profit = round(capital * (profit_pct / 100.0), 2)

    bt_id = f"saudi_bt_{model_name.lower()}_{start_date.replace('-', '')}_{actual_end.replace('-', '')}"
    trades_desc = sorted(trades, key=lambda t: t["entry_date"], reverse=True)

    return {
        "id": bt_id,
        "model_name": model_name,
        "exchange": "TADAWUL",
        "market": "TASI",
        "currency": "SAR",
        "is_public": True,
        "created_at": now_iso,
        "start_date": start_date,
        "end_date": actual_end,
        "status": "completed",
        "status_msg": f"StrategyEngine Walk-Forward ({total_trades} trades)",
        "target_pct": atr_tp_mult,
        "stop_loss_pct": atr_sl_mult,
        "look_forward_days": max_sessions,
        "meta_threshold": round(threshold, 3),
        "capital": capital,
        "net_profit": net_profit,
        "win_rate": kpis["win_rate_pct"],
        "profit_pct": profit_pct,
        "post_council_profit_pct": profit_pct,
        "post_council_win_rate": kpis["win_rate_pct"],
        "total_trades": total_trades,
        "avg_return_per_trade": avg_ret,
        "profit_factor": kpis["profit_factor"],
        "max_drawdown_pct": kpis["max_drawdown_pct"],
        "avg_holding_days": kpis["avg_holding_days"],
        "trades": trades_desc,
    }


def _run_model_with_periods(
    *,
    model_name: str,
    df_all: pd.DataFrame,
    prob_col: str,
    threshold: float,
    sub_bars: Dict[str, pd.DataFrame],
    market_cache: Dict[str, Any],
    meta: Dict[str, Dict[str, Any]],
    index_gate: str,
    use_trend_filter: bool,
    adaptive_exits: bool,
    barrier_mode: str,
    atr_tp_mult: float,
    atr_sl_mult: float,
    max_sessions: int,
    max_concurrent: int = 5,
    min_turnover: float = DEFAULT_ML_MIN_TURNOVER,
    trail_be_pct: float = 0.04,
    trail_lock_trigger_pct: float = 0.06,
    now_iso: str,
) -> Dict[str, Any]:
    primary = simulate_radar_strategy_backtest(
        model_name=model_name,
        df_all=df_all,
        prob_col=prob_col,
        threshold=threshold,
        sub_bars=sub_bars,
        market_cache=market_cache,
        meta=meta,
        start_date="2022-01-01",
        index_gate=index_gate,
        use_trend_filter=use_trend_filter,
        adaptive_exits=adaptive_exits,
        barrier_mode=barrier_mode,
        atr_tp_mult=atr_tp_mult,
        atr_sl_mult=atr_sl_mult,
        max_sessions=max_sessions,
        max_concurrent=max_concurrent,
        min_turnover=min_turnover,
        trail_be_pct=trail_be_pct,
        trail_lock_trigger_pct=trail_lock_trigger_pct,
        now_iso=now_iso,
    )
    end_d = primary["end_date"]
    period_windows = [
        ("full_cycle", "2022-01-01", end_d),
        ("bull_expansion_2022_2024", "2022-01-01", "2024-12-31"),
        ("bear_test_2025_2026", "2025-01-01", end_d),
        ("recent_2026", "2026-03-01", end_d),
    ]
    periods: Dict[str, Dict[str, Any]] = {}
    for p_key, p_start, p_end in period_windows:
        sub_bt = (
            primary
            if p_key == "full_cycle"
            else simulate_radar_strategy_backtest(
                model_name=model_name,
                df_all=df_all,
                prob_col=prob_col,
                threshold=threshold,
                sub_bars=sub_bars,
                market_cache=market_cache,
                meta=meta,
                start_date=p_start,
                end_date=p_end,
                index_gate=index_gate,
                use_trend_filter=use_trend_filter,
                adaptive_exits=adaptive_exits,
                barrier_mode=barrier_mode,
                atr_tp_mult=atr_tp_mult,
                atr_sl_mult=atr_sl_mult,
                max_sessions=max_sessions,
                max_concurrent=max_concurrent,
                min_turnover=min_turnover,
                trail_be_pct=trail_be_pct,
                trail_lock_trigger_pct=trail_lock_trigger_pct,
                now_iso=now_iso,
            )
        )
        periods[p_key] = {
            "start_date": sub_bt["start_date"],
            "end_date": sub_bt["end_date"],
            "total_trades": sub_bt["total_trades"],
            "win_rate": sub_bt["win_rate"],
            "profit_pct": sub_bt["profit_pct"],
            "profit_factor": sub_bt["profit_factor"],
            "max_drawdown_pct": sub_bt["max_drawdown_pct"],
            "avg_holding_days": sub_bt["avg_holding_days"],
        }
    primary["periods"] = periods
    return primary


def _build_saudi_backtests_dataset(
    bars_by_symbol: Dict[str, pd.DataFrame],
    market_df: pd.DataFrame,
    meta: Dict[str, Dict[str, Any]],
    stocks_by_sym: Dict[str, Dict[str, Any]],
    fund_meta: Dict[str, Dict[str, Any]],
    now_iso: str,
) -> Dict[str, Any]:
    king_path = os.path.join(PROJECT_ROOT, "api", "models", "KING_TASI.pkl")
    tadawul_path = os.path.join(PROJECT_ROOT, "api", "models", "model_TADAWUL.pkl")

    with open(king_path, "rb") as f:
        king_art = pickle.load(f)
    with open(tadawul_path, "rb") as f:
        tadawul_art = pickle.load(f)

    df_all, sub_bars = _build_or_load_ml_features_df(
        bars_by_symbol,
        market_df,
        stocks_by_sym,
        fund_meta,
    )
    market_cache = _prepare_market_and_signal_cache(sub_bars, market_df)

    king_probs, king_default_th, king_info = score_model_artifact(
        king_art,
        df_all,
        fallback_features=KING_TASI_FEATURES,
    )
    df_all["king_prob"] = king_probs
    king_tp = dict(king_info.get("trading_parameters") or {})
    king_barrier = "atr"
    king_tp_disp = 4.0
    king_sl_disp = 2.2
    king_hold = 25
    king_thresh = (
        max(0.48, float(king_default_th))
        if king_info["kind"] == "meta_labeling_system"
        else max(0.48, float(king_art.get("threshold") or king_default_th or 0.48))
    )

    tad_probs, tad_default_th, tad_info = score_model_artifact(tadawul_art, df_all)
    df_all["tad_prob"] = tad_probs
    tad_tp = dict(tad_info.get("trading_parameters") or {})
    tad_barrier = "atr"
    tad_tp_disp = 3.5
    tad_sl_disp = 1.8
    tad_hold = 20
    tad_thresh = (
        max(0.50, float(tad_default_th))
        if tad_info["kind"] == "meta_labeling_system"
        else float(tad_default_th)
    )

    bt_king = _run_model_with_periods(
        model_name="KING_TASI",
        df_all=df_all,
        prob_col="king_prob",
        threshold=king_thresh,
        sub_bars=sub_bars,
        market_cache=market_cache,
        meta=meta,
        index_gate="above_ema20",
        use_trend_filter=True,
        adaptive_exits=True,
        barrier_mode="atr",
        atr_tp_mult=king_tp_disp,
        atr_sl_mult=king_sl_disp,
        max_sessions=king_hold,
        max_concurrent=5,
        min_turnover=1_500_000.0,
        trail_be_pct=0.05,
        trail_lock_trigger_pct=0.08,
        now_iso=now_iso,
    )
    bt_tadawul = _run_model_with_periods(
        model_name="model_TADAWUL",
        df_all=df_all,
        prob_col="tad_prob",
        threshold=tad_thresh,
        sub_bars=sub_bars,
        market_cache=market_cache,
        meta=meta,
        index_gate="above_ema20",
        use_trend_filter=True,
        adaptive_exits=True,
        barrier_mode="atr",
        atr_tp_mult=tad_tp_disp,
        atr_sl_mult=tad_sl_disp,
        max_sessions=tad_hold,
        max_concurrent=5,
        min_turnover=15_000_000.0,
        trail_be_pct=0.06,
        trail_lock_trigger_pct=0.09,
        now_iso=now_iso,
    )

    models_meta = [
        {
            "name": "KING_TASI",
            "exchange": "TADAWUL",
            "market": "TASI",
            "currency": "SAR",
            "type": "Meta-Labeling LightGBM" if king_info["kind"] == "meta_labeling_system" else "LightGBM",
            "num_features": king_info["num_features"],
            "trainingSamples": king_art.get("training_samples") or king_art.get("num_samples"),
            "validationSamples": king_art.get("validation_samples"),
            "auc": round(float(king_art.get("auc") or (king_art.get("walk_forward_summary") or {}).get("average_auc") or 0), 4),
            "precision": round(float(king_art.get("precision") or (king_art.get("walk_forward_summary") or {}).get("average_precision") or 0), 4),
            "recall": round(float(king_art.get("recall") or (king_art.get("walk_forward_summary") or {}).get("average_recall") or 0), 4),
            "f1": round(float(king_art.get("f1") or (king_art.get("walk_forward_summary") or {}).get("average_f1") or 0), 4),
            "threshold": round(king_thresh, 3),
            "target_pct": king_tp_disp,
            "stop_loss_pct": king_sl_disp,
            "look_forward_days": king_hold,
            "created_at": king_art.get("timestamp") or now_iso,
        },
        {
            "name": "model_TADAWUL",
            "exchange": "TADAWUL",
            "market": "TASI",
            "currency": "SAR",
            "type": "Meta-Labeling LightGBM" if tad_info["kind"] == "meta_labeling_system" else "LightGBM",
            "num_features": tad_info["num_features"],
            "trainingSamples": tadawul_art.get("training_samples") or tadawul_art.get("num_samples"),
            "validationSamples": tadawul_art.get("validation_samples"),
            "auc": round(float(tadawul_art.get("auc") or (tadawul_art.get("walk_forward_summary") or {}).get("average_auc") or 0), 4),
            "precision": round(float(tadawul_art.get("precision") or (tadawul_art.get("walk_forward_summary") or {}).get("average_precision") or 0), 4),
            "recall": round(float(tadawul_art.get("recall") or (tadawul_art.get("walk_forward_summary") or {}).get("average_recall") or 0), 4),
            "f1": round(float(tadawul_art.get("f1") or (tadawul_art.get("walk_forward_summary") or {}).get("average_f1") or 0), 4),
            "threshold": round(tad_thresh, 3),
            "target_pct": tad_tp_disp,
            "stop_loss_pct": tad_sl_disp,
            "look_forward_days": tad_hold,
            "created_at": tadawul_art.get("timestamp") or now_iso,
        },
    ]

    as_of = max(bt_king["end_date"], bt_tadawul["end_date"])
    return {
        "backtests": [bt_king, bt_tadawul],
        "models": models_meta,
        "as_of": as_of,
        "computed_at": now_iso,
        "market": "TASI",
        "currency": "SAR",
    }


def _bars_dict_to_short_swings_df(
    bars_by_symbol: Dict[str, pd.DataFrame],
    warmup_start: str = ML_WARMUP_START,
) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for sym, bdf in bars_by_symbol.items():
        if bdf is None or bdf.empty:
            continue
        sub = bdf[bdf.index >= warmup_start]
        if len(sub) < 30:
            continue
        part = pd.DataFrame({
            "symbol": sym,
            "date": [ts.strftime("%Y-%m-%d") for ts in sub.index],
            "open": pd.to_numeric(sub["Open"], errors="coerce").values,
            "high": pd.to_numeric(sub["High"], errors="coerce").values,
            "low": pd.to_numeric(sub["Low"], errors="coerce").values,
            "close": pd.to_numeric(sub["Close"], errors="coerce").values,
            "volume": pd.to_numeric(sub["Volume"], errors="coerce").values,
        })
        frames.append(part)
    if not frames:
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])
    return pd.concat(frames, ignore_index=True)


def _build_saudi_short_swings_dataset(
    bars_by_symbol: Dict[str, pd.DataFrame],
    meta: Dict[str, Dict[str, Any]],
    now_iso: str,
) -> Dict[str, Any]:
    preloaded_df = _bars_dict_to_short_swings_df(bars_by_symbol, warmup_start=ML_WARMUP_START)
    res = compute_short_swings(
        phase="close",
        exchange="TADAWUL",
        preloaded_df=preloaded_df,
        preloaded_meta=meta,
    )
    res.setdefault("market", "TASI")
    res.setdefault("currency", "SAR")
    return res


def _build_saudi_scanner_alerts_dataset(
    bars_by_symbol: Dict[str, pd.DataFrame],
    meta: Dict[str, Dict[str, Any]],
    now_iso: str,
    start_date: str = "2024-01-01",
) -> Dict[str, Any]:
    sub_bars: Dict[str, pd.DataFrame] = {}
    for sym, bdf in bars_by_symbol.items():
        if bdf is None or bdf.empty:
            continue
        sliced = bdf[bdf.index >= SCANNER_WARMUP_START]
        if len(sliced) >= 25:
            sub_bars[sym] = sliced

    return run_scanner_alerts_simulation(
        sub_bars,
        meta=meta,
        exchange="TADAWUL",
        start_date=start_date,
        now_iso=now_iso,
        causal_be_prev_only=True,
    )


def _sync_saudi_scanner_state_after_close(sb, ds_scanner: Dict[str, Any], now_iso: str) -> Dict[str, Any]:
    """Preserve intraday scan history/config while aligning active/closed signals with EOD close."""
    existing_public: Dict[str, Any] = {}
    existing_state: Dict[str, Any] = {}
    try:
        pub_res = (
            sb.table("market_cache")
            .select("payload")
            .eq("cache_key", "saudi_scanner_alerts_v1")
            .eq("country", COUNTRY_NAME)
            .maybe_single()
            .execute()
        )
        existing_public = (getattr(pub_res, "data", None) or {}).get("payload") or {}
    except Exception:
        existing_public = {}
    try:
        st_res = (
            sb.table("market_cache")
            .select("payload")
            .eq("cache_key", "saudi_scanner_state")
            .eq("country", COUNTRY_NAME)
            .maybe_single()
            .execute()
        )
        existing_state = (getattr(st_res, "data", None) or {}).get("payload") or {}
    except Exception:
        existing_state = {}

    history = list(ds_scanner.get("history") or existing_public.get("history") or existing_state.get("history") or [])[:60]
    last_scan = ds_scanner.get("last_scan") or existing_public.get("last_scan") or existing_state.get("last_scan")
    merged_public = dict(ds_scanner)
    merged_public["history"] = history
    if last_scan is not None:
        merged_public["last_scan"] = last_scan

    merged_state = {
        "is_active": existing_state.get("is_active", True),
        "market_hours_only": existing_state.get("market_hours_only", True),
        "sent_today": existing_state.get("sent_today") or {},
        "active_signals": list(ds_scanner.get("active_signals") or []),
        "closed_signals": list(ds_scanner.get("closed_signals") or [])[:1000],
        "history": history,
        "last_scan": last_scan or {"timestamp": now_iso, "runner": "saudi-close-sync"},
        "synced_at": now_iso,
    }
    _upsert_market_cache(sb, "saudi_scanner_state", merged_state, now_iso)
    return merged_public


def _upsert_market_cache(sb, cache_key: str, payload: Dict[str, Any], now_iso: str) -> None:
    sb.table("market_cache").upsert(
        {
            "cache_key": cache_key,
            "country": COUNTRY_NAME,
            "payload": payload,
            "computed_at": now_iso,
        },
        on_conflict="cache_key,country",
    ).execute()


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Saudi Backtests & 3 Trading Systems Engine (TASI)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--only-systems",
        action="store_true",
        help="Run and publish System 2 (short swings) and System 3 (fast scanner) only.",
    )
    group.add_argument(
        "--only-models",
        action="store_true",
        help="Run and publish System 1 (ML StrategyEngine backtests) only.",
    )
    return parser.parse_args(list(argv) if argv is not None else [])


def main(argv: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    args = parse_args(argv)
    run_models = not args.only_systems
    run_systems = not args.only_models

    t0 = time.time()
    sb = _init_saudi_client()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    symbols, meta, stocks_by_sym = _load_saudi_stocks_meta(sb)
    market_df, bars_by_symbol, fund_meta = _load_saudi_history_for_systems(
        sb, symbols, meta, stocks_by_sym
    )
    print(
        f"[SAUDI-SYSTEMS] Loaded {len(bars_by_symbol)} stocks (mode="
        f"{'systems' if args.only_systems else ('models' if args.only_models else 'all')}) "
        f"in {time.time() - t0:.1f}s"
    )

    out: Dict[str, Any] = {}
    print("\n=== SAUDI SYSTEMS SUMMARY ===")

    if run_models:
        ds_backtests = _build_saudi_backtests_dataset(
            bars_by_symbol, market_df, meta, stocks_by_sym, fund_meta, now_iso
        )
        _upsert_market_cache(sb, "saudi_backtests_v1", ds_backtests, now_iso)
        out["backtests"] = ds_backtests
        for bt in ds_backtests["backtests"]:
            print(
                f"[BACKTEST] {bt['model_name']}: trades={bt['total_trades']} | win_rate={bt['win_rate']}% | "
                f"profit_pct={bt['profit_pct']}% | pf={bt['profit_factor']} | max_dd={bt['max_drawdown_pct']}% | "
                f"range={bt['start_date']}..{bt['end_date']}"
            )
            for p_name, p_stats in (bt.get("periods") or {}).items():
                print(
                    f"   - {p_name:24s}: trades={p_stats['total_trades']:3d} | "
                    f"wr={p_stats['win_rate']}% | ret={p_stats['profit_pct']}% | "
                    f"pf={p_stats['profit_factor']} | dd={p_stats['max_drawdown_pct']}%"
                )

    if run_systems:
        ds_swings = _build_saudi_short_swings_dataset(bars_by_symbol, meta, now_iso)
        ds_scanner = _build_saudi_scanner_alerts_dataset(bars_by_symbol, meta, now_iso)
        ds_scanner = _sync_saudi_scanner_state_after_close(sb, ds_scanner, now_iso)
        _upsert_market_cache(sb, "saudi_short_swings_v1", ds_swings, now_iso)
        _upsert_market_cache(sb, "saudi_scanner_alerts_v1", ds_scanner, now_iso)
        out["short_swings"] = ds_swings
        out["scanner_alerts"] = ds_scanner
        print(
            f"[SHORT_SWINGS] active={ds_swings['total_active']} | closed={ds_swings['total_closed']} | "
            f"kpis={ds_swings['kpis']}"
        )
        print(
            f"[FAST_SCANNER] active={len(ds_scanner['active_signals'])} | closed={len(ds_scanner['closed_signals'])} | "
            f"kpis={ds_scanner['signals_kpis']}"
        )

    print(f"[DONE] Updated SAUDI_SUPABASE.market_cache in {time.time() - t0:.1f}s")
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
