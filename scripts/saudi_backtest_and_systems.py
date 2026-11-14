"""
Saudi Backtests & 3 Trading Systems Engine (TASI / Tadawul).

Connects to SAUDI_SUPABASE, loads historical stock_prices (264 Saudi stocks),
stocks metadata, stock_technical_indicators, and trained LightGBM models
(`api/models/KING_TASI.pkl`, `api/models/model_TADAWUL.pkl`).

Computes and upserts 3 real datasets into SAUDI_SUPABASE.market_cache:
  1. `saudi_backtests_v1`     — Walk-forward backtest simulation of KING_TASI & model_TADAWUL
  2. `saudi_short_swings_v1`  — Saudi Short Swings (20d breakout + EMA10 pullback + trailing EMA10 stop)
  3. `saudi_scanner_alerts_v1`— Saudi Fast Scanner signals (volume_surge, breakout, rsi_oversold)
"""
from __future__ import annotations

import datetime as dt
import os
import pickle
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.saudi_pipeline_bootstrap import (  # noqa: E402
    KING_TASI_FEATURES,
    MODEL_TADAWUL_EXTRA_FEATURES,
    _build_single_stock_ml_frame,
    _clean_num,
    _init_saudi_client,
    _init_saudi_config,
    load_saudi_market_and_prices,
)

COUNTRY_NAME = "Saudi Arabia"
MIN_SAUDI_TURNOVER = 2_000_000.0  # 2M SAR 20-day average daily turnover
SLIPPAGE = 0.0015  # 0.15% conservative execution slippage

SHORT_SWING_EXIT_LABELS = {
    "ema10_break": "كسر متوسط EMA10 (حماية أرباح)",
    "stop_be": "وقف التعادل (حماية رأس المال)",
    "stop_loss": "وقف الخسارة الأولي (-4%)",
    "max_time": "انتهاء المدة الزمنية القصوى (20 جلسة)",
    "delisted_or_halted": "إغلاق لانتهاء المدة / توقف التداول",
}

SCANNER_PROFILES = {
    "volume_surge": {"t1_pct": 4.5, "t2_pct": 7.5, "sl_pct": 3.0, "max_sessions": 4},
    "breakout": {"t1_pct": 6.0, "t2_pct": 9.5, "sl_pct": 3.5, "max_sessions": 5},
    "rsi_oversold": {"t1_pct": 4.0, "t2_pct": 6.5, "sl_pct": 2.8, "max_sessions": 3},
}


def _compute_kpis_from_trades(
    trades: List[Dict[str, Any]],
    return_key: str = "return_pct",
    slots: float = 15.0,
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


def _load_saudi_stocks_meta(sb) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    res = sb.table("stocks").select("symbol,name,name_ar,sector").execute()
    meta: Dict[str, Dict[str, Any]] = {}
    symbols: List[str] = []
    for row in res.data or []:
        sym = str(row.get("symbol") or "").strip()
        if not sym:
            continue
        symbols.append(sym)
        meta[sym] = {
            "name_ar": row.get("name_ar") or row.get("name") or sym,
            "name_en": row.get("name") or sym,
            "sector": row.get("sector") or "عام",
        }
    return sorted(set(symbols)), meta


def _simulate_model_backtest(
    *,
    model_name: str,
    model_meta: Dict[str, Any],
    booster: lgb.Booster,
    feature_names: List[str],
    df_all: pd.DataFrame,
    bars_by_symbol: Dict[str, pd.DataFrame],
    meta: Dict[str, Dict[str, Any]],
    start_date: str = "2025-01-01",
    target_pct: float = 8.0,
    stop_loss_pct: float = 4.5,
    max_sessions: int = 15,
    max_concurrent: int = 10,
    now_iso: str = "",
) -> Dict[str, Any]:
    threshold = float(model_meta.get("threshold") or model_meta.get("optimal_threshold") or 0.40)

    # Filter ML rows to backtest window
    win_df = df_all[df_all["date_str"] >= start_date].copy()
    if win_df.empty:
        raise RuntimeError(f"No ML rows >= {start_date} for {model_name}")

    probs = booster.predict(win_df[feature_names].astype(float))
    win_df["prob"] = probs
    sig_df = win_df[win_df["prob"] >= threshold].copy()

    # Group candidate signals by date sorted by prob descending
    candidates_by_date: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
    for row in sig_df.sort_values(["date_str", "prob"], ascending=[True, False]).itertuples(index=False):
        candidates_by_date[str(row.date_str)].append((str(row.symbol), float(row.prob)))

    all_dates = sorted(win_df["date_str"].unique())
    end_date = all_dates[-1] if all_dates else start_date

    # Precompute 20-day avg turnover and date->position lookup per symbol
    date_pos_by_sym: Dict[str, Dict[str, int]] = {}
    turnover_by_sym: Dict[str, np.ndarray] = {}
    for sym, raw_df in bars_by_symbol.items():
        d_strs = [ts.strftime("%Y-%m-%d") for ts in raw_df.index]
        date_pos_by_sym[sym] = {d: idx for idx, d in enumerate(d_strs)}
        turn = (raw_df["Close"].astype(float) * raw_df["Volume"].astype(float)).rolling(20, min_periods=1).mean().values
        turnover_by_sym[sym] = turn

    active_until_idx: Dict[str, int] = {}
    open_positions_exits: List[int] = []  # global day indices when positions close
    date_to_global_idx = {d: idx for idx, d in enumerate(all_dates)}

    trades: List[Dict[str, Any]] = []
    capital = 100_000.0

    for g_idx, d_str in enumerate(all_dates):
        # Free up closed slots
        open_positions_exits = [ex_i for ex_i in open_positions_exits if ex_i > g_idx]
        if len(open_positions_exits) >= max_concurrent:
            continue

        day_cands = candidates_by_date.get(d_str, [])
        picked_today = 0
        for sym, prob in day_cands:
            if len(open_positions_exits) >= max_concurrent or picked_today >= 3:
                break
            if active_until_idx.get(sym, -1) >= g_idx:
                continue

            raw_df = bars_by_symbol.get(sym)
            pos = date_pos_by_sym.get(sym, {}).get(d_str)
            if raw_df is None or pos is None or pos + 1 >= len(raw_df):
                continue

            avg_turn = float(turnover_by_sym[sym][pos])
            if not np.isfinite(avg_turn) or avg_turn < MIN_SAUDI_TURNOVER:
                continue

            next_bar = raw_df.iloc[pos + 1]
            if float(next_bar["Volume"]) <= 0 or float(next_bar["Open"]) <= 0:
                continue

            entry_price = float(next_bar["Open"]) * (1.0 + SLIPPAGE)
            entry_date = raw_df.index[pos + 1].strftime("%Y-%m-%d")
            target_price = entry_price * (1.0 + target_pct / 100.0)
            stop_price = entry_price * (1.0 - stop_loss_pct / 100.0)

            fwd = raw_df.iloc[pos + 1 : min(len(raw_df), pos + 1 + max_sessions)]
            if len(fwd) < 2:
                continue

            exit_price = float(fwd["Close"].iloc[-1]) * (1.0 - SLIPPAGE)
            exit_date = fwd.index[-1].strftime("%Y-%m-%d")
            exit_reason = "max_time"
            sessions_held = len(fwd)

            for s_idx, (f_ts, f_bar) in enumerate(fwd.iterrows(), start=1):
                f_open = float(f_bar["Open"])
                f_high = float(f_bar["High"])
                f_low = float(f_bar["Low"])
                if s_idx >= 1 and f_low <= stop_price:
                    raw_fill = f_open if f_open <= stop_price else stop_price
                    exit_price = raw_fill * (1.0 - SLIPPAGE)
                    exit_date = f_ts.strftime("%Y-%m-%d")
                    exit_reason = "stop_loss"
                    sessions_held = s_idx
                    break
                if f_high >= target_price:
                    exit_price = target_price * (1.0 - SLIPPAGE)
                    exit_date = f_ts.strftime("%Y-%m-%d")
                    exit_reason = "target_hit"
                    sessions_held = s_idx
                    break

            ret_pct = ((exit_price / entry_price) - 1.0) * 100.0
            status = "win" if ret_pct > 0 else "loss"
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
                "status": status,
                "exit_reason": exit_reason,
                "sessions": sessions_held,
                "confidence": round(prob, 4),
            })

            exit_g_idx = date_to_global_idx.get(exit_date, g_idx + sessions_held)
            active_until_idx[sym] = exit_g_idx + 2  # 2-session cooldown
            open_positions_exits.append(exit_g_idx)
            picked_today += 1

    kpis = _compute_kpis_from_trades(trades, return_key="profit_pct", slots=float(max_concurrent))
    total_trades = len(trades)
    avg_ret = round(float(np.mean([t["profit_pct"] for t in trades])), 2) if trades else 0.0
    profit_pct = kpis["total_return_pct"]
    net_profit = round(capital * (profit_pct / 100.0), 2)

    bt_id = f"saudi_bt_{model_name.lower()}_{start_date.replace('-', '')}_{end_date.replace('-', '')}"
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
        "end_date": end_date,
        "status": "completed",
        "status_msg": f"Walk-forward simulation ({total_trades} trades)",
        "target_pct": target_pct,
        "stop_loss_pct": stop_loss_pct,
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


def _build_saudi_backtests_dataset(
    bars_by_symbol: Dict[str, pd.DataFrame],
    market_df: pd.DataFrame,
    meta: Dict[str, Dict[str, Any]],
    symbols: List[str],
    now_iso: str,
) -> Dict[str, Any]:
    king_path = os.path.join(PROJECT_ROOT, "api", "models", "KING_TASI.pkl")
    tadawul_path = os.path.join(PROJECT_ROOT, "api", "models", "model_TADAWUL.pkl")

    with open(king_path, "rb") as f:
        king_meta = pickle.load(f)
    with open(tadawul_path, "rb") as f:
        tadawul_meta = pickle.load(f)

    king_booster = lgb.Booster(model_str=king_meta["model_str"])
    tadawul_booster = lgb.Booster(model_str=tadawul_meta["model_str"])
    tadawul_features = list(tadawul_meta["feature_names"])

    all_candidate_cols = sorted(set(KING_TASI_FEATURES) | set(MODEL_TADAWUL_EXTRA_FEATURES) | set(tadawul_features))

    # ~700 trailing bars covers 2025-01-01 .. 2026-11-12 + 200-bar indicator warmup
    compact_frames: List[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [
            pool.submit(
                _build_single_stock_ml_frame,
                sym,
                bars_by_symbol[sym].iloc[-750:],
                market_df,
                all_candidate_cols,
            )
            for sym in symbols
            if sym in bars_by_symbol and len(bars_by_symbol[sym]) >= 80
        ]
        for fut in as_completed(futs):
            _, comp_df, _ = fut.result()
            comp_df = comp_df.loc[:, ~comp_df.columns.duplicated()].copy()
            compact_frames.append(comp_df)

    df_all = pd.concat(compact_frames, ignore_index=True)
    for col in all_candidate_cols:
        if col in df_all.columns:
            df_all[col] = pd.to_numeric(df_all[col], errors="coerce").replace([np.inf, -np.inf], 0.0).fillna(0.0)

    bt_king = _simulate_model_backtest(
        model_name="KING_TASI",
        model_meta=king_meta,
        booster=king_booster,
        feature_names=KING_TASI_FEATURES,
        df_all=df_all,
        bars_by_symbol=bars_by_symbol,
        meta=meta,
        start_date="2025-01-01",
        target_pct=8.0,
        stop_loss_pct=4.5,
        max_sessions=15,
        max_concurrent=10,
        now_iso=now_iso,
    )
    bt_tadawul = _simulate_model_backtest(
        model_name="model_TADAWUL",
        model_meta=tadawul_meta,
        booster=tadawul_booster,
        feature_names=tadawul_features,
        df_all=df_all,
        bars_by_symbol=bars_by_symbol,
        meta=meta,
        start_date="2025-01-01",
        target_pct=8.0,
        stop_loss_pct=4.5,
        max_sessions=15,
        max_concurrent=10,
        now_iso=now_iso,
    )

    models_meta = [
        {
            "name": "KING_TASI",
            "exchange": "TADAWUL",
            "market": "TASI",
            "currency": "SAR",
            "type": "LightGBM",
            "num_features": len(KING_TASI_FEATURES),
            "trainingSamples": king_meta.get("training_samples"),
            "validationSamples": king_meta.get("validation_samples"),
            "auc": round(float(king_meta.get("auc") or 0), 4),
            "precision": round(float(king_meta.get("precision") or 0), 4),
            "recall": round(float(king_meta.get("recall") or 0), 4),
            "f1": round(float(king_meta.get("f1") or 0), 4),
            "threshold": round(float(king_meta.get("threshold") or 0.37), 3),
            "target_pct": 8.0,
            "stop_loss_pct": 4.5,
            "look_forward_days": 15,
            "created_at": king_meta.get("timestamp") or now_iso,
        },
        {
            "name": "model_TADAWUL",
            "exchange": "TADAWUL",
            "market": "TASI",
            "currency": "SAR",
            "type": "LightGBM",
            "num_features": len(tadawul_features),
            "trainingSamples": tadawul_meta.get("training_samples"),
            "validationSamples": tadawul_meta.get("validation_samples"),
            "auc": round(float(tadawul_meta.get("auc") or 0), 4),
            "precision": round(float(tadawul_meta.get("precision") or 0), 4),
            "recall": round(float(tadawul_meta.get("recall") or 0), 4),
            "f1": round(float(tadawul_meta.get("f1") or 0), 4),
            "threshold": round(float(tadawul_meta.get("threshold") or 0.41), 3),
            "target_pct": 8.0,
            "stop_loss_pct": 4.5,
            "look_forward_days": 15,
            "created_at": tadawul_meta.get("timestamp") or now_iso,
        },
    ]

    as_of = bt_king["end_date"]
    return {
        "backtests": [bt_king, bt_tadawul],
        "models": models_meta,
        "as_of": as_of,
        "computed_at": now_iso,
        "market": "TASI",
        "currency": "SAR",
    }


def _build_saudi_short_swings_dataset(
    bars_by_symbol: Dict[str, pd.DataFrame],
    meta: Dict[str, Dict[str, Any]],
    now_iso: str,
    start_date: str = "2025-01-01",
) -> Dict[str, Any]:
    frames: List[pd.DataFrame] = []
    for sym, raw_df in bars_by_symbol.items():
        if len(raw_df) < 60:
            continue
        g = raw_df.tail(600).copy()
        g["symbol"] = sym
        g["date"] = [ts.strftime("%Y-%m-%d") for ts in g.index]
        g = g.reset_index(drop=True)
        g = g.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        c = g["close"].astype(float)
        h = g["high"].astype(float)
        l = g["low"].astype(float)
        v = g["volume"].astype(float)

        g["ema10"] = c.ewm(span=10, adjust=False).mean()
        g["ema20"] = c.ewm(span=20, adjust=False).mean()
        g["ema50"] = c.ewm(span=50, adjust=False).mean()
        g["vol_ma20"] = v.rolling(20).mean()
        g["turnover"] = (c * v).rolling(20).mean()
        g["active_days"] = v.gt(0).rolling(20).sum()
        g["high20"] = h.rolling(20).max().shift(1)
        g["ret20"] = c / c.shift(20) - 1.0
        g["liquid"] = (np.arange(len(g)) >= 30) & (g["turnover"] >= MIN_SAUDI_TURNOVER) & (g["active_days"] >= 15)
        g["above_ema50"] = g["liquid"] & (c > g["ema50"])
        frames.append(g)

    df = pd.concat(frames, ignore_index=True)
    breadth_raw = df[df["liquid"]].groupby("date")["above_ema50"].mean()
    df = df.merge(breadth_raw.shift(1).rename("breadth"), on="date", how="left")
    df["breadth"] = df["breadth"].fillna(0.5)

    mkt_ok = df["breadth"] >= 0.45
    trend_aligned = (
        df["liquid"]
        & (df["close"] > df["ema10"])
        & (df["ema10"] > df["ema20"])
        & (df["ema20"] > df["ema50"])
    )
    day_range = df["high"] - df["low"]
    close_pos = (df["close"] - df["low"]) / day_range.replace(0, 1e-9)

    sig_base_bo = (
        mkt_ok
        & trend_aligned
        & (df["close"] > df["high20"])
        & (df["volume"] >= df["vol_ma20"] * 1.4)
        & (df["close"] > df["open"])
        & (close_pos >= 0.70)
        & (df["ret20"] >= 0.05)
    )
    sig_power_pb = (
        mkt_ok
        & trend_aligned
        & (df["ret20"] >= 0.08)
        & (df["low"] <= df["ema10"] * 1.01)
        & (df["close"] > df["ema10"])
        & (df["volume"] >= df["vol_ma20"] * 1.2)
        & (df["close"] > df["open"])
        & (close_pos >= 0.75)
    )
    sig_rs_leader = (
        (~mkt_ok)
        & trend_aligned
        & (df["close"] >= df["high20"] * 0.985)
        & (df["volume"] >= df["vol_ma20"] * 1.25)
        & (df["close"] > df["open"])
        & (close_pos >= 0.70)
        & (df["ret20"] >= 0.07)
    )

    df["signal"] = sig_base_bo | sig_power_pb | sig_rs_leader
    df["sig_type"] = np.where(
        sig_base_bo,
        "اختراق قمة 20 يوم + انفجار سيولة",
        np.where(sig_power_pb, "ارتداد قوة من متوسط EMA10", "قائد قوة نسبية في سوق متذبذب"),
    )

    df = df[df["date"] >= start_date].copy()
    dates = sorted(df["date"].unique())
    last_date = dates[-1] if dates else dt.date.today().isoformat()

    market: Dict[Tuple[str, str], Any] = {}
    for row in df.itertuples(index=False):
        market[(row.symbol, row.date)] = row

    sig_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    sig_rows = df[df["signal"] & (df["volume"] > 0)]
    date_next = {dates[i]: dates[i + 1] for i in range(len(dates) - 1)}
    for row in sig_rows.itertuples(index=False):
        nxt = date_next.get(row.date)
        if nxt:
            sig_map[nxt].append({
                "symbol": row.symbol,
                "signal_date": row.date,
                "date": nxt,
                "close": float(row.close),
                "turnover": float(row.turnover),
                "sig_type": row.sig_type,
            })

    positions: Dict[str, Dict[str, Any]] = {}
    closed_trades: List[Dict[str, Any]] = []

    for i, day in enumerate(dates):
        for sym, p in positions.items():
            if p.get("be_pending_activation"):
                p["be_active"] = True
                p["sl_price"] = max(p["sl_price"], p["entry_price"] * 1.003)
                p["be_pending_activation"] = False

        # Pending exits at Open
        for sym in list(positions):
            p = positions[sym]
            b = market.get((sym, day))
            age = i - p["index"]
            if age >= 20 and not p.get("pending"):
                p["pending"] = "max_time"

            if not b or b.volume <= 0 or b.high == b.low:
                p["missing_sessions"] = p.get("missing_sessions", 0) + 1
                if p.get("pending") or age >= 20 or p["missing_sessions"] >= 5:
                    fill_price = p["last"] * (1.0 - SLIPPAGE)
                    ret_pct = (fill_price / p["entry_price"] - 1.0) * 100.0
                    m_info = meta.get(sym, {})
                    rc = p.get("pending") or ("max_time" if age >= 20 else "delisted_or_halted")
                    closed_trades.append({
                        "symbol": sym,
                        "name_ar": m_info.get("name_ar", sym),
                        "name_en": m_info.get("name_en", sym),
                        "sector": m_info.get("sector", "عام"),
                        "entry_date": p["date"],
                        "exit_date": p.get("last_date") or day,
                        "entry_price": round(p["entry_price"], 2),
                        "exit_price": round(fill_price, 2),
                        "return_pct": round(ret_pct, 2),
                        "max_gain_pct": round(p["max_gain"], 2),
                        "sessions": min(age, 20),
                        "holding_days": min(age, 20),
                        "reason": rc,
                        "exit_reason": SHORT_SWING_EXIT_LABELS.get(rc, "إغلاق حسب الخطة"),
                        "trigger_type": p["sig_type"],
                    })
                    del positions[sym]
                continue

            p["missing_sessions"] = 0
            p["last_date"] = day
            if age >= 1 and p.get("pending"):
                fill_price = float(b.open) * (1.0 - SLIPPAGE)
                ret_pct = (fill_price / p["entry_price"] - 1.0) * 100.0
                m_info = meta.get(sym, {})
                rc = p["pending"]
                closed_trades.append({
                    "symbol": sym,
                    "name_ar": m_info.get("name_ar", sym),
                    "name_en": m_info.get("name_en", sym),
                    "sector": m_info.get("sector", "عام"),
                    "entry_date": p["date"],
                    "exit_date": day,
                    "entry_price": round(p["entry_price"], 2),
                    "exit_price": round(fill_price, 2),
                    "return_pct": round(ret_pct, 2),
                    "max_gain_pct": round(p["max_gain"], 2),
                    "sessions": age,
                    "holding_days": age,
                    "reason": rc,
                    "exit_reason": SHORT_SWING_EXIT_LABELS.get(rc, "إغلاق حسب الخطة"),
                    "trigger_type": p["sig_type"],
                })
                del positions[sym]

        # New entries at today's open
        for s in sorted(sig_map.get(day, []), key=lambda x: -x["turnover"]):
            if len(positions) >= 15 or s["symbol"] in positions:
                continue
            b = market.get((s["symbol"], day))
            if not b or b.volume <= 0 or b.high == b.low:
                continue
            limit_price = s["close"]
            if b.open <= limit_price * 1.02:
                exec_price = float(b.open)
            elif b.low <= limit_price:
                exec_price = limit_price
            else:
                continue
            fill = exec_price * (1.0 + SLIPPAGE)
            positions[s["symbol"]] = {
                "symbol": s["symbol"],
                "date": day,
                "signal_date": s["signal_date"],
                "index": i,
                "entry_price": fill,
                "sl_price": fill * 0.96,
                "highest_high": fill,
                "max_gain": 0.0,
                "be_active": False,
                "be_pending_activation": False,
                "last": float(b.close),
                "last_date": day,
                "sig_type": s["sig_type"],
                "pending": None,
            }

        # Intraday stops & trailing EMA10
        for sym in list(positions):
            p = positions[sym]
            b = market.get((sym, day))
            if not b:
                continue
            p["last"] = float(b.close)
            p["last_date"] = day
            p["missing_sessions"] = 0
            age = i - p["index"]

            if age >= 1 and b.low <= p["sl_price"]:
                raw_fill = (min(b.high, b.open) if b.open <= p["sl_price"] else max(b.low, p["sl_price"])) * (1.0 - SLIPPAGE)
                fill_price = max(b.low * (1.0 - SLIPPAGE), min(b.high, raw_fill))
                ret_pct = (fill_price / p["entry_price"] - 1.0) * 100.0
                m_info = meta.get(sym, {})
                rc = "stop_be" if p["be_active"] else "stop_loss"
                closed_trades.append({
                    "symbol": sym,
                    "name_ar": m_info.get("name_ar", sym),
                    "name_en": m_info.get("name_en", sym),
                    "sector": m_info.get("sector", "عام"),
                    "entry_date": p["date"],
                    "exit_date": day,
                    "entry_price": round(p["entry_price"], 2),
                    "exit_price": round(fill_price, 2),
                    "return_pct": round(ret_pct, 2),
                    "max_gain_pct": round(p["max_gain"], 2),
                    "sessions": age,
                    "holding_days": age,
                    "reason": rc,
                    "exit_reason": SHORT_SWING_EXIT_LABELS.get(rc, "وقف خسارة"),
                    "trigger_type": p["sig_type"],
                })
                del positions[sym]
                continue

            if b.high > p["highest_high"]:
                p["highest_high"] = float(b.high)
                p["max_gain"] = max(p["max_gain"], (b.high / p["entry_price"] - 1.0) * 100.0)

            if not p["be_active"] and not p.get("be_pending_activation") and (b.high / p["entry_price"] - 1.0) >= 0.045:
                p["be_pending_activation"] = True

            if p["be_active"]:
                p["sl_price"] = max(p["sl_price"], float(b.ema10))
                if b.close < b.ema10:
                    p["pending"] = "ema10_break"

            if age >= 20 and not p["pending"]:
                p["pending"] = "max_time"

    active_output: List[Dict[str, Any]] = []
    seen_syms = set()
    # Pending entries detected on last_date for next session
    today_sigs = df[(df["date"] == last_date) & (df["signal"])].sort_values("turnover", ascending=False)
    for _, s_row in today_sigs.head(10).iterrows():
        sym = str(s_row["symbol"])
        if sym in positions or sym in seen_syms:
            continue
        seen_syms.add(sym)
        close_p = round(float(s_row["close"]), 2)
        sl_p = round(close_p * 0.96, 2)
        m_info = meta.get(sym, {})
        active_output.append({
            "signal_id": f"{sym}_{last_date}",
            "symbol": sym,
            "name_ar": m_info.get("name_ar", sym),
            "name_en": m_info.get("name_en", sym),
            "sector": m_info.get("sector", "عام"),
            "entry_date": "جلسة الغد",
            "signal_date": last_date,
            "entry_price": close_p,
            "current_price": close_p,
            "reference_close": close_p,
            "return_pct": 0.0,
            "stop_loss": sl_p,
            "trailing_stop": sl_p,
            "ema10_trend": round(float(s_row["ema10"]), 2),
            "is_breakeven_protected": False,
            "max_gain_pct": 0.0,
            "trigger_type": s_row["sig_type"],
            "status": "إشارة دخول جديدة (جلسة الغد)",
            "is_pending_entry": True,
            "as_of": last_date,
        })

    for sym, p in positions.items():
        b = market.get((sym, last_date))
        curr_p = float(b.close) if b else p["last"]
        curr_gain = (curr_p / p["entry_price"] - 1.0) * 100.0
        m_info = meta.get(sym, {})
        active_output.append({
            "signal_id": f"{sym}_{p.get('signal_date', p['date'])}",
            "symbol": sym,
            "name_ar": m_info.get("name_ar", sym),
            "name_en": m_info.get("name_en", sym),
            "sector": m_info.get("sector", "عام"),
            "entry_date": p["date"],
            "signal_date": p.get("signal_date", p["date"]),
            "entry_price": round(p["entry_price"], 2),
            "current_price": round(curr_p, 2),
            "reference_close": round(curr_p, 2),
            "return_pct": round(curr_gain, 2),
            "stop_loss": round(p["entry_price"] * 0.96, 2),
            "trailing_stop": round(p["sl_price"], 2),
            "ema10_trend": round(float(b.ema10), 2) if b else None,
            "is_breakeven_protected": bool(p["be_active"]),
            "max_gain_pct": round(p["max_gain"], 2),
            "trigger_type": p["sig_type"],
            "status": "مؤمنة بربح" if p["be_active"] else "قيد التداول",
            "is_pending_entry": False,
            "as_of": last_date,
        })

    active_output.sort(key=lambda t: (0 if t.get("is_pending_entry") else 1, -float(t.get("return_pct") or 0)))
    closed_trades.sort(key=lambda t: t["exit_date"], reverse=True)
    kpis = _compute_kpis_from_trades(closed_trades, return_key="return_pct", slots=15.0)

    return {
        "status": "ok",
        "is_pro": True,
        "kpis": kpis,
        "active_trades": active_output,
        "closed_trades": closed_trades,
        "total_active": len(active_output),
        "total_closed": len(closed_trades),
        "as_of": last_date,
        "computed_at": now_iso,
        "market": "TASI",
        "currency": "SAR",
    }


def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1.0 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _build_saudi_scanner_alerts_dataset(
    bars_by_symbol: Dict[str, pd.DataFrame],
    meta: Dict[str, Dict[str, Any]],
    now_iso: str,
    lookback_sessions: int = 65,
) -> Dict[str, Any]:
    active_signals: List[Dict[str, Any]] = []
    closed_signals: List[Dict[str, Any]] = []
    latest_dates: List[str] = []

    for sym, raw_df in bars_by_symbol.items():
        if len(raw_df) < 40:
            continue
        df = raw_df.tail(lookback_sessions + 30).copy()
        c = df["Close"].astype(float)
        h = df["High"].astype(float)
        l = df["Low"].astype(float)
        o = df["Open"].astype(float)
        v = df["Volume"].astype(float)

        df["vol_ma20"] = v.rolling(20).mean()
        df["turnover20"] = (c * v).rolling(20).mean()
        df["high20"] = h.rolling(20).max().shift(1)
        df["rsi14"] = _compute_rsi(c, 14)
        df["prev_c"] = c.shift(1)

        latest_dates.append(df.index[-1].strftime("%Y-%m-%d"))
        start_idx = max(25, len(df) - lookback_sessions)
        cooldown_until = -1
        m_info = meta.get(sym, {})

        for i in range(start_idx, len(df)):
            if i <= cooldown_until:
                continue
            row = df.iloc[i]
            if float(row["turnover20"] or 0) < MIN_SAUDI_TURNOVER or float(row["Volume"] or 0) <= 0:
                continue
            entry_price = float(row["Close"])
            if entry_price <= 0:
                continue

            scanner_type: Optional[str] = None
            if float(row["Volume"]) >= float(row["vol_ma20"] or 0) * 2.0 and entry_price > float(row["Open"]) and entry_price >= float(row["prev_c"] or entry_price) * 1.015:
                scanner_type = "volume_surge"
            elif pd.notna(row["high20"]) and entry_price > float(row["high20"]) and float(row["Volume"]) >= float(row["vol_ma20"] or 0) * 1.3 and entry_price > float(row["Open"]):
                scanner_type = "breakout"
            elif pd.notna(row["rsi14"]) and float(row["rsi14"]) <= 32.0 and entry_price >= float(row["Open"]):
                scanner_type = "rsi_oversold"

            if not scanner_type:
                continue

            prof = SCANNER_PROFILES[scanner_type]
            t1 = round(entry_price * (1.0 + prof["t1_pct"] / 100.0), 2)
            t2 = round(entry_price * (1.0 + prof["t2_pct"] / 100.0), 2)
            sl = round(entry_price * (1.0 - prof["sl_pct"] / 100.0), 2)
            max_sess = prof["max_sessions"]
            entry_date = df.index[i].strftime("%Y-%m-%d")

            fwd = df.iloc[i + 1 : min(len(df), i + 1 + max_sess)]
            status = "active"
            exit_price: Optional[float] = None
            exit_date: Optional[str] = None
            exit_reason: Optional[str] = None
            highest_p = entry_price
            lowest_p = entry_price
            curr_p = entry_price
            sessions = 0

            for s_idx, (f_ts, f_bar) in enumerate(fwd.iterrows(), start=1):
                sessions = s_idx
                f_o = float(f_bar["Open"])
                f_h = float(f_bar["High"])
                f_l = float(f_bar["Low"])
                f_c = float(f_bar["Close"])
                highest_p = max(highest_p, f_h)
                lowest_p = min(lowest_p, f_l)
                curr_p = f_c

                if f_l <= sl:
                    status = "stopped_out"
                    exit_price = round(f_o if f_o <= sl else sl, 2)
                    exit_date = f_ts.strftime("%Y-%m-%d")
                    exit_reason = "تفعيل وقف الخسارة"
                    break
                if f_h >= t1:
                    status = "target_hit"
                    exit_price = t1
                    exit_date = f_ts.strftime("%Y-%m-%d")
                    exit_reason = "تحقق الهدف الأول بنجاح 🎯"
                    break
                if s_idx >= max_sess:
                    status = "expired"
                    exit_price = round(f_c, 2)
                    exit_date = f_ts.strftime("%Y-%m-%d")
                    exit_reason = "انتهاء المدة الزمنية للإشارة"
                    break

            final_p = exit_price if exit_price is not None else curr_p
            ret_pct = round(((final_p / entry_price) - 1.0) * 100.0, 2)
            max_gain = round(((highest_p / entry_price) - 1.0) * 100.0, 2)

            sig_obj = {
                "id": f"{sym}_{entry_date}_{scanner_type}",
                "symbol": sym,
                "name_ar": m_info.get("name_ar", sym),
                "name_en": m_info.get("name_en", sym),
                "sector": m_info.get("sector", "عام"),
                "scanner_type": scanner_type,
                "entry_date": entry_date,
                "entry_time": "14:45",
                "entry_price": round(entry_price, 2),
                "target_1": t1,
                "target_1_pct": prof["t1_pct"],
                "target_2": t2,
                "target_2_pct": prof["t2_pct"],
                "stop_loss": sl,
                "stop_loss_pct": prof["sl_pct"],
                "current_price": round(curr_p, 2),
                "highest_price": round(highest_p, 2),
                "lowest_price": round(lowest_p, 2),
                "exit_date": exit_date,
                "exit_time": "14:55" if exit_date else None,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "return_pct": ret_pct,
                "max_gain_pct": max_gain,
                "status": status,
                "sessions": max(1, sessions) if exit_date else max(1, sessions + 1),
                "sessions_count": max(1, sessions) if exit_date else max(1, sessions + 1),
                "max_sessions": max_sess,
                "updated_at": now_iso,
            }

            if status == "active":
                active_signals.append(sig_obj)
            else:
                closed_signals.append(sig_obj)
            cooldown_until = i + max(2, sessions)

    active_signals.sort(key=lambda x: (x["entry_date"], x["return_pct"]), reverse=True)
    closed_signals.sort(key=lambda x: str(x.get("exit_date") or x["entry_date"]), reverse=True)

    wins = [s for s in closed_signals if (s["return_pct"] or 0) > 0]
    losses = [s for s in closed_signals if (s["return_pct"] or 0) < 0]
    total_closed = len(closed_signals)
    win_rate = round((len(wins) / total_closed) * 100.0, 1) if total_closed else 0.0
    sum_wins = sum(s["return_pct"] for s in wins)
    sum_losses = abs(sum(s["return_pct"] for s in losses))
    avg_win = round(sum_wins / len(wins), 2) if wins else 0.0
    avg_loss = round(sum_losses / len(losses), 2) if losses else 0.0
    pf = round(sum_wins / sum_losses, 2) if sum_losses > 0 else (99.0 if sum_wins > 0 else 0.0)
    top_win = round(max((s["max_gain_pct"] for s in closed_signals), default=0.0), 2)

    as_of = max(latest_dates) if latest_dates else dt.date.today().isoformat()
    return {
        "ok": True,
        "is_pro": True,
        "market": "TASI",
        "currency": "SAR",
        "as_of": as_of,
        "computed_at": now_iso,
        "active_signals": active_signals,
        "closed_signals": closed_signals,
        "signals_kpis": {
            "win_rate_pct": win_rate,
            "total_closed": total_closed,
            "total_active": len(active_signals),
            "avg_win_pct": avg_win,
            "avg_loss_pct": avg_loss,
            "profit_factor": pf,
            "top_win_pct": top_win,
        },
    }


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


def main() -> Dict[str, Any]:
    t0 = time.time()
    sb = _init_saudi_client()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    symbols, meta = _load_saudi_stocks_meta(sb)
    market_df, _, bars_by_symbol = load_saudi_market_and_prices(sb, symbols)
    print(f"[SAUDI-SYSTEMS] Loaded {len(bars_by_symbol)} stocks from SAUDI_SUPABASE in {time.time() - t0:.1f}s")

    ds_backtests = _build_saudi_backtests_dataset(bars_by_symbol, market_df, meta, symbols, now_iso)
    ds_swings = _build_saudi_short_swings_dataset(bars_by_symbol, meta, now_iso)
    ds_scanner = _build_saudi_scanner_alerts_dataset(bars_by_symbol, meta, now_iso)

    _upsert_market_cache(sb, "saudi_backtests_v1", ds_backtests, now_iso)
    _upsert_market_cache(sb, "saudi_short_swings_v1", ds_swings, now_iso)
    _upsert_market_cache(sb, "saudi_scanner_alerts_v1", ds_scanner, now_iso)

    print("\n=== SAUDI SYSTEMS SUMMARY ===")
    for bt in ds_backtests["backtests"]:
        print(
            f"[BACKTEST] {bt['model_name']}: trades={bt['total_trades']} | win_rate={bt['win_rate']}% | "
            f"profit_pct={bt['profit_pct']}% | pf={bt['profit_factor']} | max_dd={bt['max_drawdown_pct']}% | "
            f"range={bt['start_date']}..{bt['end_date']}"
        )
    print(
        f"[SHORT_SWINGS] active={ds_swings['total_active']} | closed={ds_swings['total_closed']} | "
        f"kpis={ds_swings['kpis']}"
    )
    print(
        f"[FAST_SCANNER] active={len(ds_scanner['active_signals'])} | closed={len(ds_scanner['closed_signals'])} | "
        f"kpis={ds_scanner['signals_kpis']}"
    )
    print(f"[DONE] Saved all 3 keys to SAUDI_SUPABASE.market_cache in {time.time() - t0:.1f}s")
    return {
        "backtests": ds_backtests,
        "short_swings": ds_swings,
        "scanner_alerts": ds_scanner,
    }


if __name__ == "__main__":
    main()
