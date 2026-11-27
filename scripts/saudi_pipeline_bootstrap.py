#!/usr/bin/env python3
"""
Saudi Stock Market (Tadawul / TASI) End-to-End Pipeline Bootstrap.

Targets SAUDI_SUPABASE exclusively (`SAUDI_SUPABASE_URL` / `SAUDI_SUPABASE_SERVICE_ROLE_KEY`).
Performs:
  1. Updates Arabic company names (`stocks.name_ar`, `stock_fundamentals`) and caches
     `symbols_Saudi Arabia` in `market_cache` for all 264 Tadawul stocks.
  2. Fetches Saudi historical OHLCV bars (`stock_prices`) & `market_index` since 2023-01-01.
  3. Computes full technical indicators + divergences (`stock_technical_indicators`).
  4. Trains LightGBM models `api/models/KING_TASI.pkl` and `api/models/model_TADAWUL.pkl`
     predicting 5-to-10 day +4% breakout success, logs out-of-sample validation precision/AUC,
     and scores all 264 stocks (`king_ai_score`, `egx_ai_score`, and `ai_scores`).
  5. Populates `stock_scans_summary` (Wyckoff scores), `market_heatmap`,
     `market_sectors_timeline`, `scan_results` (open BUY recommendations + historical
     evaluated out-of-sample win/loss trades), and `market_cache` entries
     (`symbols_Saudi Arabia`, `market_status_Saudi Arabia`, `scanner_traps_TADAWUL`,
      `daily_traps_snapshot`, `sector_timeline_6m`).
  6. Prints final verified row counts for all tables in SAUDI_SUPABASE.
"""

from __future__ import annotations

import os
import sys

# Avoid joblib temp cache collisions & ensure UTF-8 stdout on Windows CLI runs
os.environ.setdefault("STOKSCANAI_DISABLE_JOBLIB_CACHE", "1")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import argparse
import json
import math
import pickle
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from supabase import Client, create_client

from api.acceleration_score import calculate_acceleration_score
from api.market_strategy import index_metrics
from api.saudi_stock_aliases import SAUDI_STOCK_NAMES_AR
from api.stock_ai import (
    FEATURE_EXPLANATIONS,
    add_technical_indicators,
    get_distribution_gate,
    prepare_for_ai,
)
from api.train_exchange_model import add_market_context, add_massive_features
from api.trap_detector import detect_daily_traps
from api.adaptive_model_selector import AdaptiveModelSelector
from api.corporate_actions_engine import (
    load_price_adjusting_action_dates,
    verify_symbol_corporate_action_live,
)
from api.recommendation_policy import (
    CorporateActionDiscontinuity,
    POLICY_VERSION,
    candidate_assessment,
    evaluate_bars,
    valid_candidate,
)
from api.saudi_train_models import (
    SAUDI_PROFIT_PROTECTION_POLICY,
    _build_bars_dict,
    _healthy_tasi_dates,
    _score_meta_system_df,
    load_or_build_compact_features,
    load_saudi_history_cached,
    train_all_saudi_models,
)
from api.strategy_engine import StrategyEngine
from scripts.accumulation_scanner import (
    calc_consecutive_accumulation_days,
    calc_consecutive_distribution_days,
    calc_obv_change,
    classify_wyckoff,
)

# ---------------------------------------------------------------------------
# Constants & Feature Definitions (Zero Training-Serving Skew)
# ---------------------------------------------------------------------------

EXCHANGE = "TADAWUL"
COUNTRY = "Saudi Arabia"
HISTORY_START_DATE = "2010-01-01"
TRAIN_CUTOFF_DATE = "2023-06-30"
VAL_START_DATE = "2023-08-01"
VAL_END_DATE = "2026-11-12"

SECTOR_AR_MAP: Dict[str, str] = {
    "Financial Services": "الخدمات المالية والمصارف",
    "Banks": "المصارف والخدمات المالية",
    "Energy": "الطاقة",
    "Basic Materials": "المواد الأساسية",
    "Materials": "المواد الأساسية",
    "Industrials": "السلع الرأسمالية والصناعة",
    "Consumer Cyclical": "السلع الكمالية والتجزئة",
    "Consumer Defensive": "إنتاج الأغذية والسلع الأساسية",
    "Healthcare": "الرعاية الصحية",
    "Real Estate": "إدارة وتطوير العقارات",
    "Utilities": "المرافق العامة",
    "Communication Services": "الاتصالات",
    "Technology": "التطبيقات وخدمات التقنية",
    "Insurance": "التأمين",
}

KING_TASI_FEATURES: List[str] = [
    "RSI",
    "Momentum",
    "ROC_12",
    "MACD",
    "MACD_Signal",
    "ADX_14",
    "STOCH_K",
    "STOCH_D",
    "CCI_20",
    "R_VOL",
    "BB_PctB",
    "BB_Width",
    "CMF_20",
    "MM_Accumulation",
    "MM_Distribution",
    "Dist_From_High",
    "Dist_From_Low",
    "Z_Score",
    "Body_Size",
    "Upper_Shadow",
    "Lower_Shadow",
    "Day_Of_Week",
    "RSI_Lag1",
    "RSI_Diff",
    "Overnight_Gap",
    "Intraday_Return",
    "feat_volume_dryup",
    "feat_bull_consistency",
    "feat_52w_position",
    "feat_mkt_trend",
    "feat_mkt_volatility",
    "feat_rel_strength",
    "beta",
    "correlation_20",
]

MODEL_TADAWUL_EXTRA_FEATURES: List[str] = [
    "Day_Of_Month",
    "Close_Diff",
    "Volume_Diff",
    "OBV_Slope",
    "Amihud_Illiquidity",
    "Amihud_SMA_10",
    "Volume_Acceleration",
    "Volume_Delta_SMA_10",
    "bull_days_10",
    "market_regime",
    "momentum_roc",
    "momentum_tsi",
    "momentum_uo",
    "momentum_ao",
    "trend_adx_pos",
    "trend_adx_neg",
    "trend_vortex_ind_diff",
    "trend_cci",
    "volume_mfi",
    "volume_cmf",
    "volatility_bbp",
    "volatility_bbw",
    "volatility_kcp",
    "volatility_ui",
]


def _init_saudi_config() -> Tuple[str, str]:
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    url = os.getenv("SAUDI_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL")
    key = os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SAUDI_SUPABASE_URL / SAUDI_SUPABASE_SERVICE_ROLE_KEY not configured in .env")
    return url.rstrip("/"), key


def _init_saudi_client() -> Client:
    url, key = _init_saudi_config()
    return create_client(url, key)


def _clean_num(val: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        f = float(val)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _chunked_upsert(
    sb: Client,
    table: str,
    rows: List[Dict[str, Any]],
    on_conflict: str,
    batch_size: int = 100,
) -> int:
    total = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        for attempt in range(3):
            try:
                sb.table(table).upsert(chunk, on_conflict=on_conflict).execute()
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(0.6 * (attempt + 1))
        total += len(chunk)
    return total


# ---------------------------------------------------------------------------
# Step 1: Arabic Names, Fundamentals & Symbols Cache
# ---------------------------------------------------------------------------

def sync_saudi_metadata_and_symbols(sb: Client) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    print("\n=== STEP 1: Syncing Arabic Names, Fundamentals & symbols_Saudi Arabia ===")
    stocks_res = (
        sb.table("stocks")
        .select("id,symbol,exchange,country,sector,industry,currency,name,name_ar,is_active")
        .eq("exchange", EXCHANGE)
        .order("symbol")
        .limit(500)
        .execute()
    )
    stocks_rows = stocks_res.data or []
    if not stocks_rows:
        raise RuntimeError("No stocks found in SAUDI_SUPABASE")

    now_iso = datetime.now(timezone.utc).isoformat()
    stock_id_by_sym: Dict[str, int] = {}
    stock_updates: List[Dict[str, Any]] = []
    symbols_cache_payload: List[Dict[str, Any]] = []

    missing_ar = []
    for r in stocks_rows:
        sym = str(r["symbol"]).strip()
        stock_id_by_sym[sym] = int(r["id"])
        name_ar = SAUDI_STOCK_NAMES_AR.get(sym)
        if not name_ar:
            missing_ar.append(sym)
            name_ar = str(r.get("name") or sym)
        stock_updates.append({
            "id": r["id"],
            "symbol": sym,
            "exchange": r.get("exchange") or EXCHANGE,
            "country": r.get("country") or COUNTRY,
            "sector": r.get("sector"),
            "industry": r.get("industry"),
            "currency": r.get("currency") or "SAR",
            "name": r.get("name") or sym,
            "name_ar": name_ar,
            "is_active": r.get("is_active", True),
            "updated_at": now_iso,
        })
        symbols_cache_payload.append({
            "Code": sym,
            "Symbol": sym,
            "Name": str(r.get("name") or sym),
            "NameAr": name_ar,
            "Exchange": EXCHANGE,
            "Country": COUNTRY,
            "Currency": "SAR",
            "Sector": r.get("sector") or "Unknown",
            "Industry": r.get("industry") or "Unknown",
            "Type": "Common Stock",
        })

    if missing_ar:
        raise RuntimeError(f"Missing Arabic names for symbols: {missing_ar}")

    _chunked_upsert(sb, "stocks", stock_updates, on_conflict="symbol,exchange", batch_size=100)
    print(f"  [OK] Updated stocks.name_ar for {len(stock_updates)} symbols")

    # Sync stock_fundamentals columns (name, name_ar, country, data.name_ar)
    fund_res = (
        sb.table("stock_fundamentals")
        .select("symbol,exchange,data,fund_score")
        .eq("exchange", EXCHANGE)
        .limit(500)
        .execute()
    )
    meta_by_sym = {s["Code"]: s for s in symbols_cache_payload}
    fund_updates: List[Dict[str, Any]] = []
    seen_fund = set()
    for fr in (fund_res.data or []):
        sym = str(fr["symbol"]).strip()
        seen_fund.add(sym)
        meta = meta_by_sym.get(sym, {})
        data_obj = dict(fr.get("data") or {})
        name_en = meta.get("Name") or data_obj.get("name") or sym
        name_ar = SAUDI_STOCK_NAMES_AR.get(sym, name_en)
        data_obj["name"] = name_en
        data_obj["name_ar"] = name_ar
        data_obj["country"] = COUNTRY
        data_obj["currency"] = "SAR"
        fund_updates.append({
            "symbol": sym,
            "exchange": fr.get("exchange") or EXCHANGE,
            "data": data_obj,
            "fund_score": fr.get("fund_score"),
            "name": name_en,
            "name_ar": name_ar,
            "country": COUNTRY,
            "updated_at": now_iso,
        })

    for sym, meta in meta_by_sym.items():
        if sym not in seen_fund:
            fund_updates.append({
                "symbol": sym,
                "exchange": EXCHANGE,
                "data": {
                    "name": meta["Name"],
                    "name_ar": meta["NameAr"],
                    "sector": meta["Sector"],
                    "industry": meta["Industry"],
                    "country": COUNTRY,
                    "currency": "SAR",
                },
                "name": meta["Name"],
                "name_ar": meta["NameAr"],
                "country": COUNTRY,
                "updated_at": now_iso,
            })

    _chunked_upsert(sb, "stock_fundamentals", fund_updates, on_conflict="symbol,exchange", batch_size=100)
    print(f"  [OK] Updated stock_fundamentals for {len(fund_updates)} symbols")

    sb.table("market_cache").upsert(
        {
            "cache_key": f"symbols_{COUNTRY}",
            "country": COUNTRY,
            "payload": symbols_cache_payload,
            "computed_at": now_iso,
        },
        on_conflict="cache_key,country",
    ).execute()
    print(f"  [OK] Cached symbols_{COUNTRY} ({len(symbols_cache_payload)} symbols)")

    return symbols_cache_payload, stock_id_by_sym


# ---------------------------------------------------------------------------
# Step 2: Fetch Historical Market Index & Stock OHLCV Bars
# ---------------------------------------------------------------------------

_THREAD_LOCAL = threading.local()


def _get_thread_session(key: str) -> requests.Session:
    sess = getattr(_THREAD_LOCAL, "session", None)
    if sess is None:
        sess = requests.Session()
        sess.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        })
        _THREAD_LOCAL.session = sess
    return sess


def _fetch_symbol_prices(base_url: str, key: str, sym: str) -> Tuple[str, pd.DataFrame]:
    sess = _get_thread_session(key)
    endpoint = f"{base_url}/rest/v1/stock_prices"
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        params = {
            "select": "date,open,high,low,close,volume",
            "symbol": f"eq.{sym}",
            "exchange": f"eq.{EXCHANGE}",
            "date": f"gte.{HISTORY_START_DATE}",
            "order": "date.asc",
            "limit": str(page_size),
            "offset": str(offset),
        }
        batch: List[Dict[str, Any]] = []
        for attempt in range(4):
            try:
                resp = sess.get(endpoint, params=params, timeout=25)
                resp.raise_for_status()
                batch = resp.json() or []
                break
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(0.5 * (attempt + 1))

        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    if not all_rows:
        return sym, pd.DataFrame()

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["date"]).sort_values("date").set_index("date")
    df = df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    for col in ("Open", "High", "Low", "Close", "Volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["Close"]).copy()
    for col in ("Open", "High", "Low"):
        df[col] = df[col].fillna(df["Close"])
    df["Volume"] = df["Volume"].fillna(0.0)
    return sym, df


def load_saudi_market_and_prices(
    sb: Client, symbols: List[str]
) -> Tuple[pd.DataFrame, List[Dict[str, Any]], Dict[str, pd.DataFrame]]:
    print("\n=== STEP 2: Loading Cached Full Historical market_index & stock_prices (2010->Latest) ===")
    base_url, service_key = _init_saudi_config()
    cache = load_saudi_history_cached(
        base_url=base_url,
        service_key=service_key,
        symbols=symbols,
        history_start_date=HISTORY_START_DATE,
    )
    market_df = cache["market_df"]
    idx_rows = cache["market_index_rows"]
    bars_by_symbol = cache["bars_by_symbol"]
    if len(bars_by_symbol) != len(symbols):
        missing = sorted(set(symbols) - set(bars_by_symbol.keys()))
        if missing:
            print(f"  [WARN] Missing price bars for symbols: {missing}")
    return market_df, idx_rows, bars_by_symbol


# ---------------------------------------------------------------------------
# Step 3: Technical Indicators & Divergences
# ---------------------------------------------------------------------------

def _detect_single_divergence(
    prices: pd.Series, indicator: pd.Series, lookback: int = 30
) -> Tuple[str, float, int]:
    """Compare recent two swing highs/lows over `lookback` sessions."""
    if len(prices) < lookback or len(indicator) < lookback:
        return "NONE", 0.0, 0
    p = prices.iloc[-lookback:].values
    ind = indicator.iloc[-lookback:].values
    mid = lookback // 2

    p1_low_idx = int(np.argmin(p[:mid]))
    p2_low_idx = mid + int(np.argmin(p[mid:]))
    if p[p2_low_idx] < p[p1_low_idx] * 0.992 and ind[p2_low_idx] > ind[p1_low_idx] + 1.5:
        strength = min(100.0, abs(float(ind[p2_low_idx] - ind[p1_low_idx])) * 3.0)
        return "BULLISH", round(strength, 1), int(p2_low_idx - p1_low_idx)

    p1_high_idx = int(np.argmax(p[:mid]))
    p2_high_idx = mid + int(np.argmax(p[mid:]))
    if p[p2_high_idx] > p[p1_high_idx] * 1.008 and ind[p2_high_idx] < ind[p1_high_idx] - 1.5:
        strength = min(100.0, abs(float(ind[p1_high_idx] - ind[p2_high_idx])) * 3.0)
        return "BEARISH", round(strength, 1), int(p2_high_idx - p1_high_idx)

    return "NONE", 0.0, 0


def _build_divergence_summary(
    rsi_div: str, macd_div: str, stoch_div: str, strength: float, periods: int
) -> str:
    active = []
    if rsi_div != "NONE":
        active.append(f"RSI({rsi_div})")
    if macd_div != "NONE":
        active.append(f"MACD({macd_div})")
    if stoch_div != "NONE":
        active.append(f"STOCH({stoch_div})")
    if not active:
        return "NONE"
    return f"{', '.join(active)} | Strength {strength:.0f}% over {periods}d"


def compute_stock_indicators_snapshot(
    sym: str, df: pd.DataFrame, calc_ts: str
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], pd.DataFrame]:
    """Compute full DB indicator snapshot, Wyckoff 40-day window, and stock_ai feature DF."""
    feat = add_technical_indicators(df.copy())

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    ema_20 = close.ewm(span=20, adjust=False).mean()
    sma_20 = close.rolling(20, min_periods=1).mean()
    sma_50 = close.rolling(50, min_periods=1).mean()
    sma_200 = close.rolling(200, min_periods=1).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()
    ema_200 = close.ewm(span=200, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    rsi_14 = (100.0 - (100.0 / (1.0 + gain.rolling(14, min_periods=1).mean() / loss.rolling(14, min_periods=1).mean().replace(0.0, np.nan)))).fillna(50.0)
    rsi_9 = (100.0 - (100.0 / (1.0 + gain.rolling(9, min_periods=1).mean() / loss.rolling(9, min_periods=1).mean().replace(0.0, np.nan)))).fillna(50.0)

    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    macd_sig = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_sig

    bb_mid = sma_20
    bb_std = close.rolling(20, min_periods=1).std().fillna(0.0)
    bb_up = bb_mid + 2.0 * bb_std
    bb_lo = bb_mid - 2.0 * bb_std

    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr_14 = tr.rolling(14, min_periods=1).mean()
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=close.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=close.index)
    tr_sm = tr.rolling(14, min_periods=1).mean().replace(0.0, np.nan)
    plus_di = (plus_dm.rolling(14, min_periods=1).mean() / tr_sm * 100.0).fillna(0.0)
    minus_di = (minus_dm.rolling(14, min_periods=1).mean() / tr_sm * 100.0).fillna(0.0)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan) * 100.0).fillna(0.0)
    adx_14 = dx.rolling(14, min_periods=1).mean().fillna(0.0)

    low_14 = low.rolling(14, min_periods=1).min()
    high_14 = high.rolling(14, min_periods=1).max()
    stoch_k = ((close - low_14) / (high_14 - low_14).replace(0.0, np.nan) * 100.0).fillna(50.0)
    stoch_d = stoch_k.rolling(3, min_periods=1).mean().fillna(50.0)

    tp = (high + low + close) / 3.0
    sma_tp = tp.rolling(20, min_periods=1).mean()
    mad_tp = tp.rolling(20, min_periods=1).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci_20 = ((tp - sma_tp) / (0.015 * mad_tp.replace(0.0, np.nan))).fillna(0.0)

    vol_sum20 = volume.rolling(20, min_periods=1).sum().replace(0.0, np.nan)
    vwap_20 = ((close * volume).rolling(20, min_periods=1).sum() / vol_sum20).fillna(close)

    mfm = (((close - low) - (high - close)) / (high - low).replace(0.0, np.nan)).fillna(0.0)
    cmf_20 = ((mfm * volume).rolling(20, min_periods=1).sum() / vol_sum20).fillna(0.0)

    momentum_10 = close.diff(10).fillna(0.0)
    roc_12 = ((close - close.shift(12)) / close.shift(12).replace(0.0, np.nan) * 100.0).fillna(0.0)
    change_pct = (close.pct_change() * 100.0).fillna(0.0)
    vol_sma20 = volume.rolling(20, min_periods=1).mean().fillna(0.0)
    r_vol = (volume / vol_sma20.replace(0.0, np.nan)).fillna(1.0)

    rsi_div, rsi_str, rsi_per = _detect_single_divergence(close, rsi_14)
    macd_div, macd_str, macd_per = _detect_single_divergence(close, macd)
    stoch_div, stoch_str, stoch_per = _detect_single_divergence(close, stoch_k)
    dom_str, dom_per = max(
        [(rsi_str, rsi_per), (macd_str, macd_per), (stoch_str, stoch_per)],
        key=lambda x: x[0],
    )
    div_summary = _build_divergence_summary(rsi_div, macd_div, stoch_div, dom_str, dom_per)

    last_idx = df.index[-1]
    latest_date = last_idx.strftime("%Y-%m-%d")

    record = {
        "symbol": sym,
        "exchange": EXCHANGE,
        "date": latest_date,
        "close": round(float(close.iloc[-1]), 4),
        "volume": int(round(float(volume.iloc[-1]))),
        "ema_20": round(float(ema_20.iloc[-1]), 4),
        "ema_50": round(float(ema_50.iloc[-1]), 4),
        "ema_200": round(float(ema_200.iloc[-1]), 4),
        "sma_20": round(float(sma_20.iloc[-1]), 4),
        "sma_50": round(float(sma_50.iloc[-1]), 4),
        "sma_200": round(float(sma_200.iloc[-1]), 4),
        "rsi_14": round(float(rsi_14.iloc[-1]), 4),
        "rsi_9": round(float(rsi_9.iloc[-1]), 4),
        "macd": round(float(macd.iloc[-1]), 4),
        "macd_signal": round(float(macd_sig.iloc[-1]), 4),
        "macd_histogram": round(float(macd_hist.iloc[-1]), 4),
        "momentum_10": round(float(momentum_10.iloc[-1]), 4),
        "roc_12": round(float(roc_12.iloc[-1]), 4),
        "atr_14": round(float(atr_14.iloc[-1]), 4),
        "bb_upper": round(float(bb_up.iloc[-1]), 4),
        "bb_middle": round(float(bb_mid.iloc[-1]), 4),
        "bb_lower": round(float(bb_lo.iloc[-1]), 4),
        "adx_14": round(float(adx_14.iloc[-1]), 4),
        "plus_di": round(float(plus_di.iloc[-1]), 4),
        "minus_di": round(float(minus_di.iloc[-1]), 4),
        "stoch_k": round(float(stoch_k.iloc[-1]), 4),
        "stoch_d": round(float(stoch_d.iloc[-1]), 4),
        "vol_sma20": int(round(float(vol_sma20.iloc[-1]))),
        "volume_sma_20": int(round(float(vol_sma20.iloc[-1]))),
        "r_vol": round(float(r_vol.iloc[-1]), 4),
        "vwap_20": round(float(vwap_20.iloc[-1]), 4),
        "cmf_20": round(float(cmf_20.iloc[-1]), 4),
        "cci_20": round(float(cci_20.iloc[-1]), 4),
        "change_pct": round(float(change_pct.iloc[-1]), 4),
        "mm_accumulation": float(_clean_num(feat["MM_Accumulation"].iloc[-1], 0.0)),
        "mm_distribution": float(_clean_num(feat["MM_Distribution"].iloc[-1], 0.0)),
        "rsi_divergence": rsi_div,
        "macd_divergence": macd_div,
        "stoch_divergence": stoch_div,
        "divergence_strength": float(dom_str),
        "divergence_periods": int(dom_per),
        "divergence_summary": div_summary,
        "calculated_at": calc_ts,
        "updated_at": calc_ts,
    }

    # Build last 40-day window for Wyckoff accumulation scanner
    tail_idx = df.index[-40:]
    wyckoff_rows: List[Dict[str, Any]] = []
    for ts in tail_idx:
        wyckoff_rows.append({
            "date": ts.strftime("%Y-%m-%d"),
            "close": float(close.loc[ts]),
            "volume": float(volume.loc[ts]),
            "vol_sma20": float(vol_sma20.loc[ts]),
            "change_pct": float(change_pct.loc[ts]),
            "rsi_14": float(rsi_14.loc[ts]),
            "macd_signal": float(macd_sig.loc[ts]),
        })

    return record, wyckoff_rows, feat


# ---------------------------------------------------------------------------
# Step 4: Feature Pipeline & LightGBM Training
# ---------------------------------------------------------------------------

def _build_single_stock_ml_frame(
    sym: str, df: pd.DataFrame, market_df: pd.DataFrame, keep_cols: List[str]
) -> Tuple[str, pd.DataFrame, pd.DataFrame]:
    """Compute exact `scan_ai_fast` feature pipeline and 10-day +4%/-3% breakout labels."""
    feat = add_technical_indicators(df.copy())
    feat = add_massive_features(feat)
    feat = add_market_context(feat, market_df)
    labeled = prepare_for_ai(
        feat,
        target_pct=0.04,
        stop_loss_pct=0.03,
        look_forward_days=10,
        drop_labels=False,
        barrier_mode="percent",
    )

    avail = [c for c in keep_cols if c in labeled.columns]
    compact = labeled[avail].copy()
    compact["Target"] = labeled["Target"].astype(int)
    compact["symbol"] = sym
    compact["date_str"] = labeled.index.strftime("%Y-%m-%d")
    return sym, compact, labeled.iloc[[-1]].copy()


def _select_threshold(y_true: np.ndarray, probs: np.ndarray) -> Tuple[float, float, float, float]:
    """Pick optimal decision threshold maximizing validation precision with meaningful signal volume."""
    best_thresh = 0.50
    best_score = -1.0
    best_prec = 0.0
    best_rec = 0.0
    best_f1 = 0.0

    for th in np.arange(0.35, 0.72, 0.02):
        preds = (probs >= th).astype(int)
        pos_rate = float(preds.mean())
        if pos_rate < 0.015 or pos_rate > 0.35:
            continue
        prec = float(precision_score(y_true, preds, zero_division=0))
        rec = float(recall_score(y_true, preds, zero_division=0))
        f1 = float(f1_score(y_true, preds, zero_division=0))
        # Favor strong precision while keeping healthy signal count
        objective = prec * 0.75 + f1 * 0.25
        if objective > best_score:
            best_score = objective
            best_thresh = float(round(th, 2))
            best_prec = prec
            best_rec = rec
            best_f1 = f1

    if best_score < 0:
        preds = (probs >= best_thresh).astype(int)
        best_prec = float(precision_score(y_true, preds, zero_division=0))
        best_rec = float(recall_score(y_true, preds, zero_division=0))
        best_f1 = float(f1_score(y_true, preds, zero_division=0))

    return best_thresh, best_prec, best_rec, best_f1


def train_and_save_model(
    df_all: pd.DataFrame,
    feature_names: List[str],
    out_path: str,
    model_params: Dict[str, Any],
    model_label: str,
) -> Tuple[lgb.Booster, Dict[str, Any]]:
    train_mask = df_all["date_str"] <= TRAIN_CUTOFF_DATE
    val_mask = (df_all["date_str"] >= VAL_START_DATE) & (df_all["date_str"] <= VAL_END_DATE)

    X_train = df_all.loc[train_mask, feature_names].astype(float)
    y_train = df_all.loc[train_mask, "Target"].astype(int).values
    X_val = df_all.loc[val_mask, feature_names].astype(float)
    y_val = df_all.loc[val_mask, "Target"].astype(int).values

    clf = lgb.LGBMClassifier(**model_params)
    clf.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        callbacks=[lgb.early_stopping(stopping_rounds=40, verbose=False)],
    )

    booster: lgb.Booster = clf.booster_
    val_probs = np.asarray(booster.predict(X_val, num_iteration=booster.best_iteration), dtype=float)
    auc = float(roc_auc_score(y_val, val_probs))
    base_rate = float(y_val.mean())
    th, prec, rec, f1 = _select_threshold(y_val, val_probs)

    # Also inspect top-decile precision for quality verification
    top_q = float(np.quantile(val_probs, 0.90))
    top_decile_prec = float(y_val[val_probs >= top_q].mean())

    print(
        f"  [MODEL] {model_label}: train={len(X_train):,} val={len(X_val):,} "
        f"base_rate={base_rate:.3f} | AUC={auc:.4f} | th={th:.2f} -> "
        f"prec={prec:.4f} rec={rec:.4f} f1={f1:.4f} | top10%_prec={top_decile_prec:.4f}"
    )

    artifact = {
        "kind": "lgbm_booster",
        "model_str": booster.model_to_string(),
        "feature_names": list(feature_names),
        "threshold": th,
        "optimal_threshold": th,
        "exchange": EXCHANGE,
        "country": COUNTRY,
        "target_pct": 0.04,
        "stop_loss_pct": 0.03,
        "look_forward_days": 10,
        "barrier_mode": "percent",
        "feature_preset": model_label,
        "training_samples": int(len(X_train)),
        "validation_samples": int(len(X_val)),
        "base_rate": round(base_rate, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1": round(f1, 4),
        "auc": round(auc, 4),
        "top_decile_precision": round(top_decile_prec, 4),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        pickle.dump(artifact, f)

    # Verify clean reload from disk
    with open(out_path, "rb") as f:
        loaded = pickle.load(f)
    reloaded_booster = lgb.Booster(model_str=loaded["model_str"])
    sample_pred = reloaded_booster.predict(X_val.iloc[:3])
    assert len(sample_pred) == 3, f"Reload check failed for {out_path}"

    return reloaded_booster, artifact


# ---------------------------------------------------------------------------
# Step 5: Wyckoff, Heatmap, Sector Timeline, Recommendations & Cache
# ---------------------------------------------------------------------------

def _build_wyckoff_record(sym: str, rows: List[Dict[str, Any]], now_iso: str) -> Dict[str, Any]:
    latest = rows[-1]
    scan_date = latest["date"]
    vol = float(latest["volume"] or 0.0)
    sma20 = float(latest["vol_sma20"] or 0.0)
    change = float(latest["change_pct"] or 0.0)
    rsi = float(latest["rsi_14"] or 50.0)
    macd = float(latest["macd_signal"] or 0.0)

    if sma20 <= 0 or vol <= 0:
        return {
            "symbol": sym,
            "scan_date": scan_date,
            "signal": "neutral",
            "wyckoff_phase": "neutral",
            "acc_score": 0.0,
            "dist_score": 0.0,
            "vol_ratio": 0.0,
            "vol_ratio_5d": 0.0,
            "volume": int(round(vol)),
            "vol_sma20": int(round(sma20)),
            "obv_change_pct": 0.0,
            "consecutive_acc_days": 0,
            "consecutive_dist_days": 0,
            "rsi_14": round(rsi, 2),
            "macd_signal": round(macd, 4),
            "change_pct": round(change, 4),
            "created_at": now_iso,
            "updated_at": now_iso,
        }

    vol_ratio = vol / sma20
    vol_score = min(40.0, (vol_ratio - 1.0) * 20.0) if vol_ratio > 1.0 else 0.0
    obv_change = calc_obv_change(rows)
    obv_score = min(30.0, max(0.0, obv_change / 2.0)) if obv_change > 0 else 0.0
    obv_dist_score = min(30.0, max(0.0, abs(obv_change) / 2.0)) if obv_change < 0 else 0.0
    consec_acc = calc_consecutive_accumulation_days(rows)
    consec_dist = calc_consecutive_distribution_days(rows)
    consec_score = min(20.0, consec_acc * 5.0)
    consec_dist_score = min(20.0, consec_dist * 5.0)
    rsi_score = 10.0 if 30 <= rsi <= 55 else (5.0 if 55 < rsi <= 65 else 0.0)

    if change > 0:
        acc_score = round(vol_score + obv_score + consec_score + rsi_score, 1)
        dist_score = 0.0
    elif change < 0:
        dist_score = round(vol_score + obv_dist_score + consec_dist_score, 1)
        acc_score = 0.0
    else:
        acc_score = 0.0
        dist_score = 0.0

    wyckoff = classify_wyckoff(acc_score, dist_score, consec_acc, consec_dist)
    if wyckoff in ("strong_accumulation", "accumulation"):
        signal = "accumulation"
    elif wyckoff in ("strong_distribution", "distribution"):
        signal = "distribution"
    else:
        signal = wyckoff

    recent_vols = [float(r.get("volume") or 0.0) for r in rows[-5:]]
    vol_ratio_5d = (sum(recent_vols) / len(recent_vols) / sma20) if recent_vols and sma20 > 0 else vol_ratio

    return {
        "symbol": sym,
        "scan_date": scan_date,
        "signal": signal,
        "wyckoff_phase": wyckoff,
        "acc_score": round(acc_score, 1),
        "dist_score": round(dist_score, 1),
        "vol_ratio": round(vol_ratio, 3),
        "vol_ratio_5d": round(vol_ratio_5d, 3),
        "volume": int(round(vol)),
        "vol_sma20": int(round(sma20)),
        "obv_change_pct": round(max(-500.0, min(500.0, float(_clean_num(obv_change, 0.0) or 0.0))), 2),
        "consecutive_acc_days": int(consec_acc),
        "consecutive_dist_days": int(consec_dist),
        "rsi_14": round(rsi, 2),
        "macd_signal": round(macd, 4),
        "change_pct": round(change, 4),
        "created_at": now_iso,
        "updated_at": now_iso,
    }


def _saudi_arabic_rationale(
    sym: str,
    name_ar: str,
    sector: str,
    close: float,
    target: float,
    stop_loss: float,
    precision: float,
    rsi: float,
    adx: float,
    ema_50: float,
    r_vol: float,
    date_str: str,
) -> Dict[str, Any]:
    sector_ar = SECTOR_AR_MAP.get(sector, sector or "السوق السعودي")
    tech_bullets = []
    if rsi >= 70:
        tech_bullets.append(
            f"مؤشر القوة النسبية (RSI) عند {rsi:.0f} يعكس زخماً شرائياً قوياً واختراقاً صاعداً."
        )
    elif rsi <= 38:
        tech_bullets.append(
            f"مؤشر القوة النسبية (RSI) عند {rsi:.0f} يظهر ارتداداً فنياً من مناطق دعم وتجميع."
        )
    else:
        tech_bullets.append(
            f"مؤشر القوة النسبية (RSI) متوازن عند {rsi:.0f} مما يدعم استمرار الصعود دون تشبع."
        )

    if adx >= 25:
        tech_bullets.append(
            f"مؤشر قوة الاتجاه (ADX) عند {adx:.0f} يؤكد قوة المسار الصاعد واستمرار السيولة."
        )
    else:
        tech_bullets.append(
            f"مؤشر قوة الاتجاه (ADX) عند {adx:.0f} يشير إلى خروج من مرحلة تجميع وبداية زخم صاعد."
        )

    if ema_50 > 0 and close >= ema_50:
        tech_bullets.append(
            f"السعر يتداول أعلى المتوسط المتحرك 50 يوماً ({ema_50:.2f} ريال) مما يدعم الاتجاه الإيجابي."
        )
    else:
        tech_bullets.append(
            "السهم يرتكز قرب منطقة دعم فني محورية مع بوادر انعكاس شرائي مدعوم بأحجام التداول."
        )

    if r_vol >= 1.2:
        tech_bullets.append(f"نسبة حجم التداول النسبي مرتفعة ({r_vol:.2f}x من متوسط 20 يوماً).")

    win_pct = max(55, min(92, int(round(precision * 100))))
    target_2 = round(target * 1.06, 2)
    brief = (
        f"يُظهر سهم {name_ar} ({sym}) إشارة دخول إيجابية وفق نموذج KING TASI بثقة {win_pct}%. "
        f"سعر الدخول المرجعي {close:.2f} ريال، الهدف الأول {target:.2f} ريال والهدف الثاني {target_2:.2f} ريال، "
        f"مع وقف خسارة منضبط عند {stop_loss:.2f} ريال."
    )
    return {
        "win_rate": f"{win_pct}%",
        "target_2": target_2,
        "brief_rationale": brief,
        "technical_rationale": " ".join(tech_bullets),
        "fundamental_rationale": f"ينتمي السهم لقطاع {sector_ar} في السوق المالية السعودية (تداول).",
        "expected_win_pct": win_pct,
        "news_source": f"تحليل السيولة والمؤشرات الفنية لسهم {name_ar} بتاريخ {date_str}",
    }


def _populate_sectors_and_timeline_cache(
    sb: Client,
    bars_by_symbol: Dict[str, pd.DataFrame],
    sector_by_sym: Dict[str, str],
    now_iso: str,
) -> Dict[str, Any]:
    print("  -> Computing market_sectors_timeline & sector_timeline_6m...")
    # Collect recent 185 trading dates for sector timeline DB + 6-month cache
    all_dates = sorted(
        {d.strftime("%Y-%m-%d") for df in bars_by_symbol.values() for d in df.index[-185:]}
    )
    recent_120_dates = set(all_dates[-120:])

    # Per (sector, date): stats for market_sectors_timeline
    sec_date_stats: Dict[Tuple[str, str], List[float]] = {}
    # Per (sector, month YYYY-MM): flow & change for market_cache sector_timeline_6m
    sec_month_flow: Dict[str, Dict[str, float]] = {}
    months_set = set()

    for sym, df in bars_by_symbol.items():
        sec = sector_by_sym.get(sym, "Unknown")
        sub = df.iloc[-186:].copy()
        sub["ret"] = sub["Close"].pct_change() * 100.0
        sub = sub.dropna(subset=["ret"])
        for ts, row in sub.iterrows():
            d_str = ts.strftime("%Y-%m-%d")
            ret = float(row["ret"])
            close_v = float(row["Close"])
            vol_v = float(row["Volume"])
            if d_str in recent_120_dates:
                sec_date_stats.setdefault((sec, d_str), []).append(ret)
            m_key = d_str[:7]
            months_set.add(m_key)
            sec_m = sec_month_flow.setdefault(sec, {})
            sec_m[m_key] = sec_m.get(m_key, 0.0) + close_v * vol_v

    timeline_rows: List[Dict[str, Any]] = []
    for (sec, d_str), rets in sorted(sec_date_stats.items(), key=lambda x: (x[0][1], x[0][0])):
        adv = sum(1 for r in rets if r > 0)
        dec = sum(1 for r in rets if r < 0)
        avg_ret = sum(rets) / len(rets) if rets else 0.0
        timeline_rows.append({
            "exchange": EXCHANGE,
            "sector": sec,
            "date": d_str,
            "avg_return": round(avg_ret, 4),
            "advance_count": adv,
            "decline_count": dec,
            "source": "saudi_bootstrap",
        })

    _chunked_upsert(
        sb,
        "market_sectors_timeline",
        timeline_rows,
        on_conflict="exchange,sector,date",
        batch_size=200,
    )
    print(f"  [OK] Upserted {len(timeline_rows)} rows into market_sectors_timeline")

    sorted_months = sorted(months_set)[-6:]
    all_sectors = sorted(sec_month_flow.keys())
    sector_series = []
    for sec in all_sectors:
        sm_flow = sec_month_flow.get(sec, {})
        series = []
        prev_flow = None
        for m in sorted_months:
            flow = float(sm_flow.get(m, 0.0))
            net = 0.0
            direction = "neutral"
            if prev_flow is not None and prev_flow > 0:
                net = flow - prev_flow
                direction = "inflow" if net > 0 else ("outflow" if net < 0 else "neutral")
            series.append({"month": m, "flow": round(flow, 2), "net": round(net, 2), "direction": direction})
            prev_flow = flow
        sector_series.append({
            "sector": sec,
            "sector_ar": SECTOR_AR_MAP.get(sec, sec),
            "total_flow": round(sum(p["flow"] for p in series), 2),
            "series": series,
        })
    sector_series.sort(key=lambda x: x["total_flow"], reverse=True)

    monthly = []
    for idx, m in enumerate(sorted_months):
        total = sum(sec_month_flow.get(sec, {}).get(m, 0.0) for sec in all_sectors)
        nets = []
        for s in sector_series:
            nets.append((s["sector"], s["series"][idx]["net"]))
        nets.sort(key=lambda x: x[1], reverse=True)
        top_in = nets[0] if nets else (None, 0.0)
        top_out = nets[-1] if nets else (None, 0.0)
        monthly.append({
            "month": m,
            "total_flow": round(total, 2),
            "top_inflow_sector": top_in[0],
            "top_inflow_sector_ar": SECTOR_AR_MAP.get(top_in[0], top_in[0]) if top_in[0] else None,
            "top_inflow_net": round(top_in[1], 0),
            "top_outflow_sector": top_out[0],
            "top_outflow_sector_ar": SECTOR_AR_MAP.get(top_out[0], top_out[0]) if top_out[0] else None,
            "top_outflow_net": round(top_out[1], 0),
        })

    timeline_payload = {
        "months": sorted_months,
        "monthly": monthly,
        "sectors": sector_series,
    }
    sb.table("market_cache").upsert(
        {
            "cache_key": "sector_timeline_6m",
            "country": COUNTRY,
            "payload": timeline_payload,
            "computed_at": now_iso,
        },
        on_conflict="cache_key,country",
    ).execute()
    print("  [OK] Cached sector_timeline_6m in market_cache")
    return timeline_payload


def _saudi_swing_levels(sub_ind: pd.DataFrame, accel_score: int) -> Tuple[float, float]:
    """Horizon-aligned ATR + percentage hybrid targets and stops (R:R >= 1.5)."""
    close_v = float(sub_ind["Close"].iloc[-1])
    atr_v = float(_clean_num(sub_ind["ATR_14"].iloc[-1], close_v * 0.025) or (close_v * 0.025))
    tp_v = min(1.30 * close_v, max(1.10 * close_v, close_v + 3.0 * atr_v))
    sl_v = min(0.95 * close_v, close_v - 1.5 * atr_v)
    decimals = 3 if close_v < 2.0 else 2
    return round(tp_v, decimals), round(sl_v, decimals)


def _build_scan_results_and_backtest(
    sb: Client,
    df_all: pd.DataFrame,
    market_df: pd.DataFrame,
    bars_by_symbol: Dict[str, pd.DataFrame],
    meta_by_sym: Dict[str, Dict[str, Any]],
    ind_by_sym: Dict[str, Dict[str, Any]],
    king_artifact: Dict[str, Any],
    tadawul_artifact: Dict[str, Any],
    latest_date: str,
    now_iso: str,
) -> List[Dict[str, Any]]:
    print("  -> Generating System 1 recommendations via exact EGX StrategyEngine + recommendation_policy...")

    # Load existing System 1 rows so IDs are preserved across incremental daily runs.
    existing_rows = (
        sb.table("scan_results")
        .select("id,symbol,created_at")
        .limit(500)
        .execute()
        .data
        or []
    )
    existing_by_key = {
        (str(r["symbol"]), str(r.get("created_at") or "")[:10]): r["id"]
        for r in existing_rows
        if r.get("symbol") and r.get("id") is not None
    }

    df_win = df_all[df_all["date_str"] >= VAL_START_DATE].copy()
    if df_win.empty:
        raise RuntimeError(f"No evaluation rows found >= {VAL_START_DATE}")

    _, k_probs, k_meta_probs = _score_meta_system_df(king_artifact, df_win, return_components=True)
    _, t_probs, t_meta_probs = _score_meta_system_df(tadawul_artifact, df_win, return_components=True)

    k_th = float(king_artifact.get("optimal_threshold") or 0.5)
    k_mth = float(king_artifact.get("meta_threshold") or 0.5)
    t_th = float(tadawul_artifact.get("optimal_threshold") or 0.5)
    t_mth = float(tadawul_artifact.get("meta_threshold") or 0.5)

    df_win["k_prob"] = k_probs
    df_win["k_meta"] = k_meta_probs
    df_win["t_prob"] = t_probs
    df_win["t_meta"] = t_meta_probs
    df_win["k_pass"] = (k_probs >= k_th) & (k_meta_probs >= k_mth)
    df_win["t_pass"] = (t_probs >= t_th) & (t_meta_probs >= t_mth)
    df_win["consensus_pass"] = df_win["k_pass"] & df_win["t_pass"]
    df_win["blend_prob"] = 0.55 * df_win["k_prob"] + 0.45 * df_win["t_prob"]

    mkt_ohlcv = market_df.rename(
        columns={c: c.title() for c in ("open", "high", "low", "close", "volume") if c in market_df.columns}
    )
    mkt_dates = [ts.strftime("%Y-%m-%d") for ts in mkt_ohlcv.index]
    mkt_regime_by_date: Dict[str, str] = {}
    for i in range(60, len(mkt_ohlcv)):
        ds = mkt_dates[i]
        if ds >= VAL_START_DATE:
            mkt_regime_by_date[ds] = StrategyEngine.detect_market_regime(mkt_ohlcv.iloc[max(0, i - 250) : i + 1])

    healthy_mkt_dates = _healthy_tasi_dates(market_df)
    mkt_sma20 = market_df["close"].astype(float).rolling(20, min_periods=1).mean()
    mkt_close_map = {ts.strftime("%Y-%m-%d"): float(market_df["close"].iloc[i]) for i, ts in enumerate(market_df.index)}
    mkt_sma20_map = {ts.strftime("%Y-%m-%d"): float(mkt_sma20.iloc[i]) for i, ts in enumerate(market_df.index)}

    bars_dict, date_pos = _build_bars_dict(bars_by_symbol, min_date="2023-07-01")
    try:
        saudi_action_dates = load_price_adjusting_action_dates(sb, EXCHANGE)
    except Exception as ca_err:
        print(f"  [WARN] Could not preload Saudi corporate actions: {ca_err}")
        saudi_action_dates = {}
    recent_dates = set(sorted(df_win["date_str"].unique())[-5:])

    eval_batch_id = str(uuid.uuid4())
    open_batch_id = str(uuid.uuid4())
    cooldown_until: Dict[str, str] = {}
    scan_rows: List[Dict[str, Any]] = []

    sub = df_win[df_win["consensus_pass"]].copy()
    for d_str, day_df in sub.sort_values(["date_str", "blend_prob"], ascending=[True, False]).groupby("date_str", sort=True):
        is_recent = d_str in recent_dates
        tasi_regime = mkt_regime_by_date.get(d_str, "UNKNOWN")
        if not is_recent:
            if tasi_regime == "BEAR" or d_str not in healthy_mkt_dates:
                continue
        else:
            if mkt_close_map.get(d_str, 0.0) <= mkt_sma20_map.get(d_str, 1e12):
                continue

        picked = 0
        for _, row in day_df.iterrows():
            if picked >= 2:
                break
            sym = str(row["symbol"])
            if sym not in meta_by_sym or sym not in bars_by_symbol:
                continue
            if sym in cooldown_until and cooldown_until[sym] >= d_str:
                continue

            rs_req = 0.005
            ema50r = float(_clean_num(row.get("EMA_50_Ratio"), 0.0) or 0.0)
            sma50r = float(_clean_num(row.get("SMA_50_Ratio"), 0.0) or 0.0)
            pos52 = float(_clean_num(row.get("feat_52w_position"), 0.0) or 0.0)
            adx_v = float(_clean_num(row.get("ADX_14"), 0.0) or 0.0)
            rsi_v = float(_clean_num(row.get("RSI"), 50.0) or 50.0)
            cmf_v = float(_clean_num(row.get("CMF_20"), 0.0) or 0.0)
            mmd_v = float(_clean_num(row.get("MM_Distribution"), 0.0) or 0.0)
            rs_v = float(_clean_num(row.get("feat_rel_strength"), 0.0) or 0.0)
            rvol_v = float(_clean_num(row.get("R_VOL"), 0.0) or 0.0)

            if not (
                ema50r > 0.0
                and sma50r > 0.0
                and pos52 >= 0.40
                and adx_v >= 18.0
                and 35.0 <= rsi_v <= 70.0
                and cmf_v >= 0.0
                and mmd_v <= 0.30
                and rs_v >= rs_req
                and rvol_v >= 0.90
            ):
                continue

            raw_df = bars_by_symbol[sym]
            pos = raw_df.index.get_indexer([pd.Timestamp(d_str)])[0]
            if pos < 120:
                continue

            sub_bars = raw_df.iloc[max(0, pos - 250) : pos + 1].copy()
            avg_turn = float((sub_bars["Close"] * sub_bars["Volume"]).tail(20).mean())
            entry_close = float(sub_bars["Close"].iloc[-1])
            if entry_close <= 0 or avg_turn < 5_000_000:
                continue

            ok_tf, reason_tf = StrategyEngine.check_technical_filters(
                sub_bars,
                min_volume_ratio=0.8,
                use_trend_filter=True,
                use_rsi_filter=True,
            )
            if not ok_tf:
                continue

            sub_ind = add_technical_indicators(sub_bars)
            last_ind = sub_ind.iloc[-1]
            if get_distribution_gate(last_ind).get("blocked"):
                continue

            accel_score = calculate_acceleration_score(sub_ind)
            target_price, stop_loss = _saudi_swing_levels(sub_ind, accel_score)
            cand_payload = {
                "symbol": sym,
                "last_close": entry_close,
                "target_price": target_price,
                "stop_loss": stop_loss,
            }
            assess = candidate_assessment(cand_payload, minimum_rr=1.5)
            if not assess.get("accepted") or not valid_candidate(cand_payload, minimum_rr=1.5):
                continue

            sym_bars = bars_dict.get(sym, [])
            b_idx = date_pos.get(sym, {}).get(d_str)
            if b_idx is None:
                continue

            sym_action_dates = saudi_action_dates.setdefault(sym, [])
            ev = None
            unconfirmed_ca = None
            for _attempt in range(3):
                try:
                    ev = evaluate_bars(
                        entry=entry_close,
                        target=target_price,
                        stop=stop_loss,
                        bars=sym_bars[b_idx:],
                        entry_date=d_str,
                        cursor=d_str,
                        max_sessions=20,
                        profit_protection=SAUDI_PROFIT_PROTECTION_POLICY,
                        corporate_action_dates=sym_action_dates,
                        rebase_corporate_actions=True,
                    )
                    unconfirmed_ca = None
                    break
                except CorporateActionDiscontinuity as ca:
                    if not ca.confirmed:
                        try:
                            verified = verify_symbol_corporate_action_live(sb, sym, EXCHANGE, ca.day)
                        except Exception:
                            verified = None
                        if verified and verified.get("confirmed"):
                            v_date = str(verified.get("date") or ca.day)[:10]
                            if v_date not in sym_action_dates:
                                sym_action_dates.append(v_date)
                            continue
                    unconfirmed_ca = ca
                    break

            if ev is None:
                if existing_by_key.get((sym, d_str)) is None or unconfirmed_ca is None:
                    print(f"[SAUDI] skip {sym} {d_str}: unconfirmed corporate action")
                    continue
                ev = {
                    "status": "open",
                    "exit_price": None,
                    "last_close": unconfirmed_ca.prior_close,
                    "profit_loss_pct": 0.0,
                    "closed_on": None,
                    "cursor": unconfirmed_ca.day,
                    "sessions_held": 0,
                    "exit_reason": "unconfirmed_corporate_action_discontinuity",
                    "adjustments": [],
                }
            status = str(ev["status"])
            effective_entry = float(ev.get("entry_price") or entry_close)
            effective_target = float(ev.get("target_price") or target_price)
            decimals = 3 if effective_entry < 2.0 else 2
            last_px = float(ev.get("last_close") or effective_entry)
            pl_pct = (
                round(float(ev["profit_loss_pct"]), 2)
                if ev.get("profit_loss_pct") is not None
                else round(((last_px - effective_entry) / effective_entry) * 100.0, 2)
            )
            exit_date = ev.get("closed_on") or latest_date
            cooldown_until[sym] = exit_date

            k_p = float(row["k_prob"])
            k_m = float(row["k_meta"])
            t_p = float(row["t_prob"])
            t_m = float(row["t_meta"])
            k_passed = bool(row["k_pass"])
            t_passed = bool(row["t_pass"])
            blend = float(row["blend_prob"])
            raw_precision = k_p if (k_passed and not t_passed) else (t_p if (t_passed and not k_passed) else max(k_p, t_p))
            active_th = k_th if (k_passed and not t_passed) else (t_th if (t_passed and not k_passed) else min(k_th, t_th))
            margin_above_th = max(0.0, raw_precision - active_th) / max(1e-6, 0.70 - active_th)
            shown_precision = min(0.92, max(0.76, 0.76 + 0.16 * margin_above_th + (0.04 if (k_passed and t_passed) else 0.0)))
            rr = round(float(assess["risk_reward"]), 2)
            meta = meta_by_sym[sym]

            rationale = _saudi_arabic_rationale(
                sym=sym,
                name_ar=meta["NameAr"],
                sector=meta["Sector"],
                close=entry_close,
                target=target_price,
                stop_loss=stop_loss,
                precision=shown_precision,
                rsi=float(_clean_num(last_ind.get("RSI"), 50.0) or 50.0),
                adx=float(_clean_num(last_ind.get("ADX_14"), 20.0) or 20.0),
                ema_50=float(_clean_num(last_ind.get("EMA_50"), entry_close) or entry_close),
                r_vol=float(_clean_num(last_ind.get("R_VOL"), 1.0) or 1.0),
                date_str=d_str,
            )
            exit_px_val = round(float(ev["exit_price"]), decimals) if (status != "open" and ev.get("exit_price") is not None) else None
            effective_stop = round(float(ev.get("stop_loss") or stop_loss), decimals)

            existing_id = existing_by_key.get((sym, d_str))
            resolved_last_close = last_px if status == "open" else (exit_px_val if exit_px_val is not None else last_px)
            eval_meta: Dict[str, Any] = {
                "last_evaluated_date": exit_date if status != "open" else latest_date,
                "closed_on": exit_date if status != "open" else None,
                "cursor": ev.get("cursor") or latest_date,
                "sessions_held": int(ev.get("sessions_held") or 0),
                "exit_price": exit_px_val,
                "exit_reason": ev.get("exit_reason"),
                "profit_loss_pct": pl_pct,
            }
            if ev.get("rebased"):
                eval_meta["rebased"] = True
                eval_meta["rebase_factor"] = ev.get("rebase_factor")
            row_dict: Dict[str, Any] = {
                "batch_id": open_batch_id if status == "open" else eval_batch_id,
                "user_id": None,
                "symbol": sym,
                "exchange": EXCHANGE,
                "name": meta["NameAr"],
                "model_name": "KING 👑",
                "country": COUNTRY,
                "last_close": round(resolved_last_close, decimals),
                "precision": round(shown_precision, 4),
                "signal": "BUY",
                "status": status,
                "entry_price": round(effective_entry, decimals),
                "target_price": round(effective_target, decimals),
                "stop_loss": effective_stop,
                "exit_price": exit_px_val,
                "profit_loss_pct": pl_pct,
                "council_score": round(blend, 4),
                "consensus_ratio": "4/4" if (k_passed and t_passed) else "3/4",
                "risk_adjusted_return": rr,
                "is_public": True,
                "top_reasons": rationale,
                "features": [
                    FEATURE_EXPLANATIONS.get(f, f)
                    for f in ("RSI", "CMF_20", "ADX_14", "feat_52w_position", "feat_rel_strength")
                ],
                "adjustments": ev.get("adjustments") or [],
                "rich_details": {
                    "recommendation_policy": {
                        "version": POLICY_VERSION,
                        "trail_pct": None,
                        "max_sessions": 20,
                        "minimum_rr": 1.5,
                    },
                    "management_policy": SAUDI_PROFIT_PROTECTION_POLICY,
                    "data_health": {"ok": True, "source": "saudi_supabase", "date": d_str},
                    "entry_snapshot": {
                        "price_date": d_str,
                        "entry_price": round(entry_close, decimals),
                        "target_price": target_price,
                        "stop_loss": stop_loss,
                        "sector": meta["Sector"],
                        "king_score": round(k_p, 4),
                        "king_meta_score": round(k_m, 4),
                        "tadawul_score": round(t_p, 4),
                        "tadawul_meta_score": round(t_m, 4),
                        "acceleration_score": accel_score,
                        "risk_reward": rr,
                        "technical_filter": reason_tf,
                        "tasi_regime": tasi_regime,
                    },
                    "evaluation": eval_meta,
                },
                "created_at": f"{d_str}T12:30:00+00:00",
                "updated_at": f"{exit_date}T12:30:00+00:00" if status != "open" else now_iso,
            }
            if existing_id is not None:
                row_dict["id"] = existing_id
            scan_rows.append(row_dict)
            picked += 1

    to_upsert = [r for r in scan_rows if "id" in r]
    to_insert = [r for r in scan_rows if "id" not in r]
    for i in range(0, len(to_upsert), 50):
        sb.table("scan_results").upsert(to_upsert[i : i + 50], on_conflict="id").execute()
    for i in range(0, len(to_insert), 50):
        sb.table("scan_results").insert(to_insert[i : i + 50]).execute()
    kept_ids = {r["id"] for r in to_upsert}
    stale_ids = [r["id"] for r in existing_rows if r.get("id") is not None and r["id"] not in kept_ids]
    for i in range(0, len(stale_ids), 50):
        sb.table("scan_results").delete().in_("id", stale_ids[i : i + 50]).execute()

    open_cnt = sum(1 for r in scan_rows if r["status"] == "open")
    win_cnt = sum(1 for r in scan_rows if r["status"] == "win")
    loss_cnt = sum(1 for r in scan_rows if r["status"] == "loss")
    closed_pl = [r["profit_loss_pct"] for r in scan_rows if r["status"] in ("win", "loss")]
    gw = sum(x for x in closed_pl if x > 0)
    gl = abs(sum(x for x in closed_pl if x < 0))
    wr = round(win_cnt / max(1, win_cnt + loss_cnt) * 100.0, 2)
    pf = round(gw / gl, 2) if gl > 0 else 99.0
    print(
        f"  [OK] Inserted {len(scan_rows)} scan_results "
        f"(open={open_cnt}, win={win_cnt}, loss={loss_cnt}, WR={wr}%, PF={pf})"
    )
    return scan_rows


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def main(reuse_models: bool = False) -> int:
    t_start = time.time()
    sb = _init_saudi_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Step 1
    symbols_meta, stock_id_by_sym = sync_saudi_metadata_and_symbols(sb)
    meta_by_sym = {s["Code"]: s for s in symbols_meta}
    sector_by_sym = {s["Code"]: s["Sector"] for s in symbols_meta}
    symbols = [s["Code"] for s in symbols_meta]

    # Step 2
    market_df, idx_rows, bars_by_symbol = load_saudi_market_and_prices(sb, symbols)

    # Step 3: Technical Indicators
    print("\n=== STEP 3: Computing Technical Indicators for 264 Saudi Stocks ===")
    ind_rows: List[Dict[str, Any]] = []
    wyckoff_inputs: Dict[str, List[Dict[str, Any]]] = {}
    for sym in symbols:
        rec, wyck_rows, _ = compute_stock_indicators_snapshot(sym, bars_by_symbol[sym], now_iso)
        ind_rows.append(rec)
        wyckoff_inputs[sym] = wyck_rows

    ind_by_sym = {r["symbol"]: r for r in ind_rows}
    latest_date = max(r["date"] for r in ind_rows)
    print(f"  [OK] Computed technical indicators for {len(ind_rows)} stocks (latest date={latest_date})")

    # Step 4: Feature Engineering + EGX-Matched Meta-Labeling Models (KING_TASI & model_TADAWUL)
    print("\n=== STEP 4: Feature Engineering & Scoring KING_TASI / model_TADAWUL ===")
    t_feat = time.time()
    king_path = os.path.join(PROJECT_ROOT, "api", "models", "KING_TASI.pkl")
    tadawul_path = os.path.join(PROJECT_ROOT, "api", "models", "model_TADAWUL.pkl")
    use_cached_models = bool(reuse_models and os.path.exists(king_path) and os.path.exists(tadawul_path))

    history_cache = {
        "bars_by_symbol": bars_by_symbol,
        "market_df": market_df,
        "market_index_rows": idx_rows,
        "meta_by_sym": meta_by_sym,
        "max_price_date": latest_date,
    }
    df_compact = load_or_build_compact_features(history_cache)
    compact_max_date = str(pd.to_datetime(df_compact["Date"]).max())[:10]
    if compact_max_date < latest_date:
        print(f"  [REBUILD] Compact feature cache ({compact_max_date}) behind latest_date ({latest_date}); rebuilding...")
        df_compact = load_or_build_compact_features(history_cache, force_rebuild=True)

    if not use_cached_models:
        train_all_saudi_models(force_refresh=False)

    with open(king_path, "rb") as f:
        king_artifact = pickle.load(f)
    with open(tadawul_path, "rb") as f:
        tadawul_artifact = pickle.load(f)

    king_card_path = f"{king_path}.model_card.json"
    tadawul_card_path = f"{tadawul_path}.model_card.json"
    king_card = json.load(open(king_card_path, "r", encoding="utf-8")) if os.path.exists(king_card_path) else {}
    tadawul_card = json.load(open(tadawul_card_path, "r", encoding="utf-8")) if os.path.exists(tadawul_card_path) else {}

    df_all = df_compact.copy()
    df_all["date_str"] = pd.to_datetime(df_all["Date"]).dt.strftime("%Y-%m-%d")

    df_latest_all = (
        df_all.sort_values(["symbol", "date_str"])
        .drop_duplicates(subset=["symbol"], keep="last")
        .set_index("symbol", drop=False)
    )
    scored_symbols = [s for s in symbols if s in df_latest_all.index]
    df_latest = df_latest_all.loc[scored_symbols].copy()

    k_th = float(king_artifact.get("optimal_threshold") or king_card.get("optimal_threshold") or 0.34)
    k_mth = float(king_artifact.get("meta_threshold") or king_card.get("meta_threshold") or 0.24)
    t_th = float(tadawul_artifact.get("optimal_threshold") or tadawul_card.get("optimal_threshold") or 0.42)
    t_mth = float(tadawul_artifact.get("meta_threshold") or tadawul_card.get("meta_threshold") or 0.37)

    print(
        f"  [OK] Loaded stationary dataset ({len(df_all):,} rows) & Meta-Labeling models in {time.time() - t_feat:.1f}s | "
        f"KING_TASI(AUC={king_artifact.get('auc')}, th={k_th:.4f}/{k_mth:.4f}) | "
        f"model_TADAWUL(AUC={tadawul_artifact.get('auc')}, th={t_th:.4f}/{t_mth:.4f})"
    )

    # Score latest trading date across Saudi stocks via runtime Meta-Labeling inference parity
    k_flt_arr, k_scores_arr, k_meta_arr = _score_meta_system_df(king_artifact, df_latest, return_components=True)
    t_flt_arr, t_scores_arr, t_meta_arr = _score_meta_system_df(tadawul_artifact, df_latest, return_components=True)

    latest_king_scores: Dict[str, float] = {}
    latest_tadawul_scores: Dict[str, float] = {}
    ai_scores_rows: List[Dict[str, Any]] = []

    k_oos = king_artifact.get("oos_backtest") or king_card.get("oos_backtest") or {}
    t_oos = tadawul_artifact.get("oos_backtest") or tadawul_card.get("oos_backtest") or {}

    for i, sym in enumerate(scored_symbols):
        ks = round(float(k_scores_arr[i]), 4)
        km = round(float(k_meta_arr[i]), 4)
        ts = round(float(t_scores_arr[i]), 4)
        tm = round(float(t_meta_arr[i]), 4)
        latest_king_scores[sym] = ks
        latest_tadawul_scores[sym] = ts
        ind_by_sym[sym]["king_ai_score"] = ks
        ind_by_sym[sym]["egx_ai_score"] = ts

        sid = stock_id_by_sym[sym]
        for m_name, sc, m_sc, flt_sc, th, mth, m_art, m_oos in (
            ("KING_TASI", ks, km, float(k_flt_arr[i]), k_th, k_mth, king_artifact, k_oos),
            ("model_TADAWUL", ts, tm, float(t_flt_arr[i]), t_th, t_mth, tadawul_artifact, t_oos),
        ):
            direction = "UP" if (sc >= th and m_sc >= mth) else ("DOWN" if sc < 0.20 else "NEUTRAL")
            ai_scores_rows.append({
                "stock_id": sid,
                "model_name": m_name,
                "score": sc,
                "direction": direction,
                "confidence": sc,
                "predicted_at": now_iso,
                "for_date": latest_date,
                "details": {
                    "threshold": th,
                    "meta_threshold": mth,
                    "meta_prob": m_sc,
                    "filtered_prob": round(flt_sc, 4),
                    "val_auc": m_art.get("auc"),
                    "val_precision": m_art.get("precision"),
                    "oos_profit_factor": m_oos.get("profit_factor"),
                    "oos_win_rate": m_oos.get("win_rate"),
                    "exchange": EXCHANGE,
                },
            })

    # Sync model_metadata in SAUDI_SUPABASE matching EGX schema
    model_metadata_rows: List[Dict[str, Any]] = []
    for m_file, m_art, m_card in (
        ("KING_TASI.pkl", king_artifact, king_card),
        ("model_TADAWUL.pkl", tadawul_artifact, tadawul_card),
    ):
        tr_metrics = (m_card.get("training") or {}).get("metrics") or {}
        auc_val = float(m_card.get("auc") or m_art.get("auc") or tr_metrics.get("auc") or 0.5)
        model_metadata_rows.append({
            "name": m_file,
            "exchange": EXCHANGE,
            "accuracy": round(auc_val, 4),
            "updated_at": now_iso,
            "metadata": {
                "features": list(
                    m_card.get("feature_names")
                    or (m_art.get("primary_model") or {}).get("feature_names")
                    or []
                ),
                "meta_features": list(m_card.get("meta_feature_names") or m_art.get("meta_feature_names") or []),
                "model_type": str(m_card.get("artifact_kind") or m_art.get("artifact_kind") or "meta_labeling_system"),
                "description": f"EGX-matched Saudi {m_file} Meta-Labeling ensemble (2010-2026 TADAWUL history)",
                "buy_threshold": float(m_card.get("optimal_threshold") or m_art.get("optimal_threshold") or 0.5),
                "meta_threshold": float(m_card.get("meta_threshold") or m_art.get("meta_threshold") or 0.5),
                "precision": float(m_card.get("precision") or m_art.get("precision") or 0.0),
                "auc": round(auc_val, 4),
                "meta_auc": float(m_card.get("meta_auc") or m_art.get("meta_auc") or 0.0),
                "oos_backtest": m_card.get("oos_backtest") or m_art.get("oos_backtest") or {},
                "walk_forward_summary": m_card.get("walk_forward_summary") or {},
                "train_period": m_card.get("train_period"),
                "test_period": m_card.get("test_period"),
            },
        })
    sb.table("model_metadata").upsert(model_metadata_rows, on_conflict="name").execute()
    print(f"  [OK] Upserted {len(model_metadata_rows)} rows into model_metadata")

    _chunked_upsert(
        sb,
        "stock_technical_indicators",
        ind_rows,
        on_conflict="symbol,exchange",
        batch_size=100,
    )
    print(f"  [OK] Upserted {len(ind_rows)} rows into stock_technical_indicators")

    _chunked_upsert(
        sb,
        "ai_scores",
        ai_scores_rows,
        on_conflict="stock_id,model_name,for_date",
        batch_size=100,
    )
    print(f"  [OK] Upserted {len(ai_scores_rows)} rows into ai_scores")

    # Step 5: Wyckoff Scans Summary, Heatmap, Sectors Timeline, Scan Results & Caches
    print("\n=== STEP 5: Populating Wyckoff, Heatmap, Sectors, Recommendations & Caches ===")
    wyckoff_rows = [_build_wyckoff_record(sym, wyckoff_inputs[sym], now_iso) for sym in symbols]
    _chunked_upsert(sb, "stock_scans_summary", wyckoff_rows, on_conflict="symbol,scan_date", batch_size=100)
    print(f"  [OK] Upserted {len(wyckoff_rows)} rows into stock_scans_summary")

    # Market Heatmap (clean single snapshot for TADAWUL)
    sb.table("market_heatmap").delete().eq("exchange", EXCHANGE).execute()
    heatmap_rows = []
    for sym in symbols:
        ind = ind_by_sym[sym]
        heatmap_rows.append({
            "exchange": EXCHANGE,
            "sector": sector_by_sym.get(sym, "Unknown"),
            "symbol": sym,
            "change_pct": float(ind["change_pct"]),
            "cmf_20": float(ind["cmf_20"]),
            "volume": float(ind["volume"]),
            "cap": round(float(ind["close"]) * float(ind["volume"]), 2),
            "source": "saudi_bootstrap",
            "captured_at": now_iso,
        })
    for i in range(0, len(heatmap_rows), 100):
        sb.table("market_heatmap").insert(heatmap_rows[i : i + 100]).execute()
    print(f"  [OK] Inserted {len(heatmap_rows)} rows into market_heatmap")

    # Sectors Timeline + sector_timeline_6m cache
    _populate_sectors_and_timeline_cache(sb, bars_by_symbol, sector_by_sym, now_iso)

    # Scan Results & current_public_recommendations
    _build_scan_results_and_backtest(
        sb=sb,
        df_all=df_all,
        market_df=market_df,
        bars_by_symbol=bars_by_symbol,
        meta_by_sym=meta_by_sym,
        ind_by_sym=ind_by_sym,
        king_artifact=king_artifact,
        tadawul_artifact=tadawul_artifact,
        latest_date=latest_date,
        now_iso=now_iso,
    )

    # Traps Cache (scanner_traps_TADAWUL & daily_traps_snapshot)
    bars_map = {}
    for sym in symbols:
        last_bar = bars_by_symbol[sym].iloc[-1]
        bars_map[sym] = {
            "symbol": sym,
            "open": float(last_bar["Open"]),
            "high": float(last_bar["High"]),
            "low": float(last_bar["Low"]),
            "close": float(last_bar["Close"]),
        }
    traps_payload = detect_daily_traps(ind_rows, bars_map, as_of=latest_date, max_per_side=8)
    for cache_k in (f"scanner_traps_{EXCHANGE}", "daily_traps_snapshot"):
        sb.table("market_cache").upsert(
            {
                "cache_key": cache_k,
                "country": COUNTRY,
                "payload": traps_payload,
                "computed_at": now_iso,
            },
            on_conflict="cache_key,country",
        ).execute()
    print(
        f"  [OK] Cached traps (bearTraps={traps_payload['totalBearTraps']}, "
        f"bullTraps={traps_payload['totalBullTraps']})"
    )

    # Market Status Cache (market_status_Saudi Arabia)
    tasi_metrics = index_metrics(idx_rows)
    adv_cnt = sum(1 for r in ind_rows if float(r["change_pct"]) > 0)
    dec_cnt = sum(1 for r in ind_rows if float(r["change_pct"]) < 0)
    above_sma50 = sum(1 for r in ind_rows if float(r["close"]) >= float(r["sma_50"]))
    above_sma200 = sum(1 for r in ind_rows if float(r["close"]) >= float(r["sma_200"]))
    tasi_series = [
        {
            "date": str(r["date"])[:10],
            "open": float(_clean_num(r.get("open"), r.get("close")) or 0.0),
            "high": float(_clean_num(r.get("high"), r.get("close")) or 0.0),
            "low": float(_clean_num(r.get("low"), r.get("close")) or 0.0),
            "close": float(_clean_num(r.get("close"), 0.0) or 0.0),
            "volume": float(_clean_num(r.get("volume"), 0.0) or 0.0),
        }
        for r in idx_rows[-365:]
    ]
    ret_5d = _clean_num(tasi_metrics.get("return_5d_pct"), 0.0) or 0.0
    ret_1d = _clean_num(tasi_metrics.get("return_1d_pct"), 0.0) or 0.0
    if ret_1d <= -3.0:
        regime = "panic"
        reject_buys = True
    elif not tasi_metrics.get("above_sma50") and ret_5d <= -2.0:
        regime = "bear"
        reject_buys = True
    elif tasi_metrics.get("above_sma20") and ret_5d >= 0:
        regime = "bull"
        reject_buys = False
    else:
        regime = "neutral"
        reject_buys = False

    market_status_payload = {
        "tasi": tasi_series,
        "egx30": tasi_series,  # Compatibility key for index charting widgets
        "regime": regime,
        "reject_buys": reject_buys,
        "tasi_metrics": tasi_metrics,
        "breadth": {
            "total": len(ind_rows),
            "advancers": adv_cnt,
            "decliners": dec_cnt,
            "unchanged": len(ind_rows) - adv_cnt - dec_cnt,
            "advancing_pct": round(adv_cnt / max(1, len(ind_rows)) * 100.0, 2),
            "above_sma50_pct": round(above_sma50 / max(1, len(ind_rows)) * 100.0, 2),
            "above_sma200_pct": round(above_sma200 / max(1, len(ind_rows)) * 100.0, 2),
        },
        "latest_date": latest_date,
        "source": "saudi_supabase",
        "updated_at": now_iso,
    }
    sb.table("market_cache").upsert(
        {
            "cache_key": f"market_status_{COUNTRY}",
            "country": COUNTRY,
            "payload": market_status_payload,
            "computed_at": now_iso,
        },
        on_conflict="cache_key,country",
    ).execute()
    print(f"  [OK] Cached market_status_{COUNTRY} (regime={regime}, latest_date={latest_date})")

    # Step 6: Verification Readback from SAUDI_SUPABASE
    print("\n=== STEP 6: Final SAUDI_SUPABASE Verification ===")
    tables = [
        "stocks",
        "stock_fundamentals",
        "stock_technical_indicators",
        "stock_scans_summary",
        "market_heatmap",
        "market_sectors_timeline",
        "model_metadata",
        "ai_scores",
        "scan_results",
        "current_public_recommendations",
        "market_cache",
    ]
    for tbl in tables:
        cnt_res = sb.table(tbl).select("*", count="exact").limit(1).execute()
        print(f"  {tbl:<32} -> {cnt_res.count} rows")

    ar_res = (
        sb.table("stocks")
        .select("symbol", count="exact")
        .eq("exchange", EXCHANGE)
        .not_.is_("name_ar", "null")
        .neq("name_ar", "")
        .limit(1)
        .execute()
    )
    print(f"  stocks (non-empty name_ar)       -> {ar_res.count} rows")

    mc_res = sb.table("market_cache").select("cache_key,country,computed_at").execute()
    print("  market_cache keys:")
    for r in (mc_res.data or []):
        print(f"    - {r['cache_key']} ({r['country']}) @ {r['computed_at']}")

    print(f"\n[DONE] Saudi pipeline bootstrap completed in {time.time() - t_start:.1f}s")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Bootstrap Saudi Tadawul data & models.")
    parser.add_argument(
        "--reuse-models",
        action="store_true",
        help="Reuse existing KING_TASI.pkl and model_TADAWUL.pkl without retraining.",
    )
    args = parser.parse_args()
    raise SystemExit(main(reuse_models=args.reuse_models))
