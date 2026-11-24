"""
api/agentic_chat/quant_engine.py
Institutional Pure-NumPy Quantitative Intelligence Engine (<5ms/stock, $0 LLM cost).

Combines 4 deterministic quantitative modules directly inside Python:
1. Market-Calibrated Fat-Tail Monte Carlo Barrier Simulator (`5,000` paths × `10` sessions)
   with exact exchange circuit-breaker caps (`EGX ±20%`, `TADAWUL/QSE ±10%`, `DFM/ADX ±15%`),
   EWMA volatility, empirical + Student-t(nu=5) mixture shocks, and first-passage stopping times.
2. Self-Learning & Empirical Outcome Calibration Loop:
   - Per-stock rolling barrier backtest on actual recent OHLCV bars.
   - Real scanner empirical outcome priors (`signal_performance_EGX` in `market_cache`).
   - Persistent `chat_quant_eval_ledger_v1` prediction grading & Brier score tracking.
   - Bayesian probability shrinkage + documented mistake penalty (upthrusts / distribution traps).
3. Deterministic Bull vs. Bear Debate & FRA-Compliant Setup Regime Classifier.
4. Macro Contagion Lookup (`macro_correlation_{SYM}` in `market_cache`).

Note: Quantitative probabilistic simulation for personal research & risk education — not financial advice.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import math
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# Exchange daily price-limit circuit breakers
EXCHANGE_DAILY_RETURN_LIMITS: Dict[str, float] = {
    "EGX": 0.20,
    "TADAWUL": 0.10,
    "TASI": 0.10,
    "QSE": 0.10,
    "DFM": 0.15,
    "ADX": 0.15,
    "COMMODITIES": 0.12,
}

DEFAULT_DAILY_LIMIT = 0.15
LEDGER_CACHE_KEY = "chat_quant_eval_ledger_v1"
SIG_PERF_CACHE_KEY = "signal_performance_EGX"

_MEM_LOCK = threading.Lock()
_LEDGER_LOCK = threading.Lock()
_CACHE_STORE: Dict[str, Tuple[float, Any]] = {}
_LAST_LEDGER_FLUSH_TS = 0.0
_LEDGER_FLUSH_COOLDOWN_S = 180.0
_DEFAULT_TTL_S = 900.0  # 15 minutes


def _is_test_env() -> bool:
    return bool(
        "pytest" in sys.modules
        or os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("TESTING")
        or os.getenv("NODE_ENV") == "test"
    )


def _mem_get(key: str) -> Tuple[bool, Any]:
    now = time.monotonic()
    with _MEM_LOCK:
        entry = _CACHE_STORE.get(key)
        if not entry:
            return False, None
        exp, val = entry
        if now >= exp:
            _CACHE_STORE.pop(key, None)
            return False, None
        return True, val


def _mem_set(key: str, val: Any, ttl_s: float = _DEFAULT_TTL_S) -> None:
    exp = time.monotonic() + max(1.0, float(ttl_s))
    with _MEM_LOCK:
        if len(_CACHE_STORE) > 600:
            _CACHE_STORE.clear()
        _CACHE_STORE[key] = (exp, val)


def _sf(v: Any) -> Optional[float]:
    try:
        if v is None or v == "":
            return None
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def get_exchange_daily_limit(exchange: Optional[str]) -> float:
    ex = str(exchange or "EGX").strip().upper()
    return EXCHANGE_DAILY_RETURN_LIMITS.get(ex, DEFAULT_DAILY_LIMIT)


def _extract_sorted_bars(ohlcv_rows: Optional[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Sort OHLCV rows chronologically ascending and keep valid close bars."""
    if not ohlcv_rows:
        return []
    cleaned: List[Dict[str, Any]] = []
    for row in ohlcv_rows:
        if not isinstance(row, dict):
            continue
        close = _sf(row.get("close"))
        if close is None or close <= 0:
            continue
        d_raw = str(row.get("date") or row.get("d") or "")[:10]
        high = _sf(row.get("high"))
        low = _sf(row.get("low"))
        cleaned.append({
            "date": d_raw,
            "close": close,
            "high": high if (high is not None and high > 0) else close,
            "low": low if (low is not None and low > 0) else close,
        })
    cleaned.sort(key=lambda b: b["date"])
    # Deduplicate by date preserving latest entry
    deduped: Dict[str, Dict[str, Any]] = {}
    no_date: List[Dict[str, Any]] = []
    for b in cleaned:
        if b["date"]:
            deduped[b["date"]] = b
        else:
            no_date.append(b)
    if deduped:
        return [deduped[d] for d in sorted(deduped.keys())] + no_date
    return no_date


def _estimate_ewma_vol_and_drift(
    bars: List[Dict[str, Any]],
    daily_limit: float,
) -> Tuple[np.ndarray, float, float]:
    """Compute clipped log returns, EWMA daily volatility (lambda=0.94), and shrunk daily drift."""
    if len(bars) < 3:
        return np.array([], dtype=float), 0.022, 0.0

    closes = np.array([b["close"] for b in bars], dtype=float)
    raw_rets = np.diff(np.log(closes))
    # Ignore split/gap anomalies beyond 1.5x circuit breaker for vol estimation
    sane_mask = np.isfinite(raw_rets) & (np.abs(raw_rets) <= max(daily_limit * 1.5, 0.25))
    log_rets = raw_rets[sane_mask]
    if len(log_rets) < 2:
        return np.array([], dtype=float), 0.022, 0.0

    max_log = math.log(1.0 + daily_limit)
    min_log = math.log(max(1.0 - daily_limit, 0.05))
    log_rets = np.clip(log_rets, min_log, max_log)

    var = float(np.var(log_rets, ddof=1)) if len(log_rets) >= 5 else (0.022 ** 2)
    if not math.isfinite(var) or var <= 0:
        var = 0.022 ** 2
    lam = 0.94
    for r in log_rets:
        var = lam * var + (1.0 - lam) * float(r * r)
    sigma = float(np.clip(math.sqrt(max(var, 1e-8)), 0.004, daily_limit * 0.75))

    drift = 0.0
    if len(log_rets) >= 5:
        drift = float(np.clip(0.25 * float(np.mean(log_rets[-20:])), -0.004, 0.004))

    return log_rets, sigma, drift


def _simulate_paths(
    *,
    symbol: str,
    exchange: str,
    close: float,
    last_date: str,
    bars: List[Dict[str, Any]],
    n_paths: int = 5000,
    horizon_days: int = 10,
) -> Tuple[np.ndarray, float, float]:
    """Vectorized 5,000-path Student-t/Empirical fat-tail simulation with market circuit limits."""
    daily_limit = get_exchange_daily_limit(exchange)
    log_rets, sigma, drift = _estimate_ewma_vol_and_drift(bars, daily_limit)

    seed_str = f"{symbol.upper()}:{str(exchange).upper()}:{last_date}:{close:.4f}"
    seed = int.from_bytes(hashlib.blake2b(seed_str.encode("utf-8"), digest_size=8).digest(), "little")
    rng = np.random.default_rng(seed)

    t_scale = math.sqrt(3.0 / 5.0)  # Standardize Student-t(df=5) to unit variance
    t_shocks = rng.standard_t(df=5.0, size=(n_paths, horizon_days)) * t_scale

    if len(log_rets) >= 15:
        emp_std = float(np.std(log_rets, ddof=1))
        emp_mean = float(np.mean(log_rets))
        if emp_std > 1e-6:
            z_pool = np.clip((log_rets - emp_mean) / emp_std, -4.0, 4.0)
        else:
            z_pool = np.zeros_like(log_rets)
        emp_idx = rng.integers(0, len(z_pool), size=(n_paths, horizon_days))
        emp_shocks = z_pool[emp_idx]
        use_emp = rng.random(size=(n_paths, horizon_days)) < 0.50
        z = np.where(use_emp, emp_shocks, t_shocks)
    else:
        z = t_shocks

    z = np.clip(z, -4.5, 4.5)
    max_log = math.log(1.0 + daily_limit)
    min_log = math.log(max(1.0 - daily_limit, 0.05))
    sim_rets = np.clip(drift + sigma * z, min_log, max_log)
    paths = float(close) * np.exp(np.cumsum(sim_rets, axis=1))
    return paths, sigma, drift


def run_monte_carlo_barrier_sim(
    ohlcv_rows: Optional[Sequence[Dict[str, Any]]],
    *,
    close: float,
    target_price: Optional[float],
    stop_price: Optional[float],
    exchange: str = "EGX",
    symbol: str = "STOCK",
    last_date: str = "",
    n_paths: int = 5000,
    horizon_days: int = 10,
) -> Dict[str, Any]:
    """Run market-calibrated Monte Carlo barrier simulation over `horizon_days` trading sessions."""
    if not close or close <= 0:
        return {}

    eff_target = float(target_price) if (target_price and target_price > close * 1.002) else round(close * 1.06, 3)
    eff_stop = float(stop_price) if (stop_price and 0 < stop_price < close * 0.998) else round(close * 0.96, 3)

    bars = _extract_sorted_bars(ohlcv_rows)
    bar_date = last_date or (bars[-1]["date"] if bars else "")
    paths, sigma, _ = _simulate_paths(
        symbol=symbol,
        exchange=exchange,
        close=close,
        last_date=bar_date,
        bars=bars,
        n_paths=n_paths,
        horizon_days=horizon_days,
    )

    hit_t = paths >= eff_target
    hit_s = paths <= eff_stop
    any_t = hit_t.any(axis=1)
    any_s = hit_s.any(axis=1)
    first_t = np.where(any_t, hit_t.argmax(axis=1), horizon_days + 1)
    first_s = np.where(any_s, hit_s.argmax(axis=1), horizon_days + 1)

    t_first = any_t & (first_t < first_s)
    s_first = any_s & (first_s < first_t)
    ties = any_t & any_s & (first_t == first_s)

    raw_t = round(float(np.mean(t_first) + 0.5 * np.mean(ties)) * 100.0, 1)
    raw_s = round(float(np.mean(s_first) + 0.5 * np.mean(ties)) * 100.0, 1)
    raw_r = round(max(0.0, 100.0 - raw_t - raw_s), 1)
    # Guarantee exact sum = 100.0
    diff = round(100.0 - (raw_t + raw_s + raw_r), 1)
    raw_r = round(max(0.0, raw_r + diff), 1)

    terminal = paths[:, -1]
    dec = 3 if close < 5 else 2
    p10 = round(float(np.percentile(terminal, 10)), dec)
    p50 = round(float(np.percentile(terminal, 50)), dec)
    p90 = round(float(np.percentile(terminal, 90)), dec)

    return {
        "paths_count": n_paths,
        "horizon_days": horizon_days,
        "daily_limit_pct": round(get_exchange_daily_limit(exchange) * 100.0, 1),
        "target_barrier": round(eff_target, dec),
        "stop_barrier": round(eff_stop, dec),
        "raw_target_prob_pct": raw_t,
        "prob_hit_stop_first_pct": raw_s,
        "prob_stay_in_range_pct": raw_r,
        "expected_10d_range": {"p10": p10, "p50": p50, "p90": p90},
        "daily_vol_pct": round(sigma * 100.0, 2),
        "annualized_vol_pct": round(sigma * math.sqrt(252.0) * 100.0, 1),
    }


def prob_touch_level(
    ohlcv_rows: Optional[Sequence[Dict[str, Any]]],
    *,
    close: float,
    target_level: float,
    exchange: str = "EGX",
    symbol: str = "STOCK",
    horizon_days: int = 10,
    n_paths: int = 5000,
) -> float:
    """Estimate probability of touching `target_level` at any point within `horizon_days`."""
    if not close or close <= 0 or not target_level or target_level <= 0:
        return 0.0
    if target_level <= close:
        return 100.0
    bars = _extract_sorted_bars(ohlcv_rows)
    bar_date = bars[-1]["date"] if bars else ""
    paths, _, _ = _simulate_paths(
        symbol=symbol,
        exchange=exchange,
        close=close,
        last_date=bar_date,
        bars=bars,
        n_paths=n_paths,
        horizon_days=horizon_days,
    )
    touched = (paths >= float(target_level)).any(axis=1)
    return round(float(np.mean(touched)) * 100.0, 1)


# ---------------------------------------------------------------------------
# Self-Learning & Empirical Outcome Calibration Loop
# ---------------------------------------------------------------------------

def _rolling_empirical_barrier_hit_rate(
    bars: List[Dict[str, Any]],
    *,
    target_mult: float,
    stop_mult: float,
    horizon_days: int = 10,
) -> Tuple[Optional[float], Optional[float], int]:
    """Slide over this stock's historical bars to measure actual barrier first-hit frequencies."""
    if len(bars) < 12 or target_mult <= 1.0 or stop_mult >= 1.0 or stop_mult <= 0:
        return None, None, 0

    wins = 0.0
    losses = 0.0
    total = 0
    max_start = len(bars) - 3
    for i in range(max_start):
        c0 = bars[i]["close"]
        if c0 <= 0:
            continue
        t_lvl = c0 * target_mult
        s_lvl = c0 * stop_mult
        outcome = 0.5  # range
        end_j = min(len(bars), i + 1 + horizon_days)
        for j in range(i + 1, end_j):
            hi = bars[j]["high"]
            lo = bars[j]["low"]
            hit_t = hi >= t_lvl
            hit_s = lo <= s_lvl
            if hit_t and hit_s:
                outcome = 0.5
                break
            if hit_t:
                outcome = 1.0
                break
            if hit_s:
                outcome = 0.0
                break
        total += 1
        if outcome == 1.0:
            wins += 1.0
        elif outcome == 0.0:
            losses += 1.0
        # Unresolved / same-bar double-hit (outcome == 0.5) stays in range and is not split across wins/losses

    if total < 5:
        return None, None, total
    return round((wins / total) * 100.0, 1), round((losses / total) * 100.0, 1), total


def _fetch_market_cache_payload(cache_key: str) -> Optional[Dict[str, Any]]:
    """Read a JSON payload from RAM cache (15m TTL) or Supabase `market_cache`."""
    hit, val = _mem_get(cache_key)
    if hit:
        return val
    if _is_test_env():
        return None
    try:
        from api.stock_ai import _init_supabase, supabase
        _init_supabase()
        if supabase is None:
            return None
        res = (
            supabase.table("market_cache")
            .select("payload")
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        payload = rows[0].get("payload") if rows and isinstance(rows[0], dict) else None
        if isinstance(payload, dict):
            _mem_set(cache_key, payload)
            return payload
        _mem_set(cache_key, {}, ttl_s=300.0)
        return None
    except Exception:
        return None


def _grade_and_record_ledger(
    *,
    symbol: str,
    exchange: str,
    eval_date: str,
    close: float,
    target_price: float,
    stop_price: float,
    calibrated_prob_pct: float,
    setup_regime: str,
    bars: List[Dict[str, Any]],
) -> Optional[float]:
    """
    Maintain `chat_quant_eval_ledger_v1` in RAM/market_cache:
    - Grade prior ungraded evaluations >= 5 sessions old using real OHLCV subsequent bars.
    - Compute rolling Brier score across graded evaluations.
    - Upsert today's snapshot and flush debounced (>= 180s) in a background daemon thread.
    """
    global _LAST_LEDGER_FLUSH_TS
    if not eval_date or close <= 0:
        return None

    remote_ledger = _fetch_market_cache_payload(LEDGER_CACHE_KEY)

    dates = [b["date"] for b in bars]
    exch_u = str(exchange or "EGX").upper()
    sym_u = str(symbol or "").upper()
    prefix = f"{exch_u}:{sym_u}:"
    flush_payload: Optional[Dict[str, Any]] = None

    with _LEDGER_LOCK:
        hit, ram_ledger = _mem_get(LEDGER_CACHE_KEY)
        ledger = ram_ledger if (hit and isinstance(ram_ledger, dict)) else remote_ledger
        raw_entries = ledger.get("entries") if isinstance(ledger, dict) else None
        entries: Dict[str, Dict[str, Any]] = (
            {k: dict(v) for k, v in raw_entries.items() if isinstance(v, dict)}
            if isinstance(raw_entries, dict)
            else {}
        )
        changed = False

        for k in list(entries.keys()):
            rec = entries.get(k)
            if not isinstance(rec, dict) or not k.startswith(prefix) or rec.get("graded"):
                continue
            edate = str(rec.get("eval_date") or "")
            later = [b for b, d in zip(bars, dates) if d > edate]
            if len(later) < 5:
                continue
            t_lvl = _sf(rec.get("target_price")) or 0.0
            s_lvl = _sf(rec.get("stop_price")) or 0.0
            if t_lvl <= 0 or s_lvl <= 0:
                continue
            outcome = 0.5
            for nb in later[:10]:
                ht = nb["high"] >= t_lvl
                hs = nb["low"] <= s_lvl
                if ht and hs:
                    outcome = 0.5
                    break
                if ht:
                    outcome = 1.0
                    break
                if hs:
                    outcome = 0.0
                    break
            p_pred = max(0.0, min(1.0, float(_sf(rec.get("pred_prob_pct")) or 50.0) / 100.0))
            brier = round((p_pred - outcome) ** 2, 4)
            rec["graded"] = True
            rec["outcome"] = outcome
            rec["brier"] = brier
            rec["graded_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            changed = True

        entry_key = f"{prefix}{eval_date}"
        if entry_key not in entries:
            entries[entry_key] = {
                "symbol": sym_u,
                "exchange": exch_u,
                "eval_date": eval_date,
                "close": round(close, 3),
                "target_price": round(target_price, 3),
                "stop_price": round(stop_price, 3),
                "pred_prob_pct": round(calibrated_prob_pct, 1),
                "regime": setup_regime,
                "graded": False,
            }
            if len(entries) > 400:
                # LRU trim oldest keys
                for old_k in sorted(entries.keys())[: len(entries) - 400]:
                    entries.pop(old_k, None)
            changed = True

        briers = [
            float(v["brier"])
            for v in entries.values()
            if isinstance(v, dict) and v.get("graded") and _sf(v.get("brier")) is not None
        ]
        avg_brier = round(sum(briers) / len(briers), 4) if briers else None

        new_ledger = {
            "entries": entries,
            "graded_count": len(briers),
            "avg_brier_score": avg_brier,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        _mem_set(LEDGER_CACHE_KEY, new_ledger)

        now_m = time.monotonic()
        if changed and not _is_test_env() and (now_m - _LAST_LEDGER_FLUSH_TS) >= _LEDGER_FLUSH_COOLDOWN_S:
            _LAST_LEDGER_FLUSH_TS = now_m
            flush_payload = copy.deepcopy(new_ledger)

    if flush_payload is not None:
        def _bg_save(payload_snapshot: Dict[str, Any]) -> None:
            try:
                from api.stock_ai import _init_supabase, supabase
                _init_supabase()
                if supabase is None:
                    return
                supabase.table("market_cache").upsert({
                    "cache_key": LEDGER_CACHE_KEY,
                    "country": "Egypt",
                    "payload": payload_snapshot,
                    "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                }).execute()
            except Exception:
                pass

        threading.Thread(target=_bg_save, args=(flush_payload,), daemon=True).start()

    return avg_brier


def calibrate_probabilities_with_market_outcomes(
    mc_res: Dict[str, Any],
    bars: List[Dict[str, Any]],
    *,
    symbol: str,
    exchange: str,
    close: float,
    rsi_14: Optional[float] = None,
    r_vol: Optional[float] = None,
    dist_score: Optional[float] = None,
    setup_regime: str = "neutral_watch",
    record_ledger: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Calibrate raw Monte Carlo probabilities using:
    1. Rolling empirical barrier hit-rate on THIS stock's recent OHLCV bars.
    2. Real scanner priors (`signal_performance_EGX`).
    3. Mistake-guard penalty when stock shows institutional distribution or overbought exhaustion.
    Returns updated `(mc_calibrated, self_learning)`.
    """
    if not mc_res:
        return {}, {}

    raw_t = float(mc_res.get("raw_target_prob_pct") or 0.0)
    raw_s = float(mc_res.get("prob_hit_stop_first_pct") or 0.0)
    t_lvl = float(mc_res.get("target_barrier") or close * 1.06)
    s_lvl = float(mc_res.get("stop_barrier") or close * 0.96)

    emp_win, emp_loss, emp_n = _rolling_empirical_barrier_hit_rate(
        bars,
        target_mult=(t_lvl / close) if close > 0 else 1.06,
        stop_mult=(s_lvl / close) if close > 0 else 0.96,
        horizon_days=int(mc_res.get("horizon_days") or 10),
    )

    sig_perf = _fetch_market_cache_payload(SIG_PERF_CACHE_KEY) if str(exchange).upper() == "EGX" else None
    upthrust_win_rate = None
    if isinstance(sig_perf, dict):
        up = sig_perf.get("upthrusts")
        if isinstance(up, dict):
            upthrust_win_rate = _sf(up.get("winRate"))  # bearish win rate = % dropping next session

    cal_t = raw_t
    cal_s = raw_s
    lessons: List[str] = []

    dist_val = _sf(dist_score) or 0.0
    rsi_val = _sf(rsi_14) or 50.0
    rvol_val = _sf(r_vol) if r_vol is not None else 1.0
    is_exhausted = (dist_val >= 65.0) or (rsi_val >= 74.0 and rvol_val < 1.0)

    # 1. Bayesian shrinkage toward stock's real empirical barrier frequency
    # Guard against regime-shift trap: never let an earlier rally's win rate inflate a distributing/exhausted top
    if emp_win is not None and emp_loss is not None and emp_n >= 5:
        if is_exhausted and emp_win > raw_t:
            lessons.append(
                f"تم حجب الرفع التفاؤلي من السجل السابق ({emp_win:.1f}%) لتغيّر نظام السهم نحو التصريف/التشبع"
            )
        else:
            w = min(0.40, emp_n / 80.0)
            cal_t = (1.0 - w) * raw_t + w * emp_win
            cal_s = (1.0 - w) * raw_s + w * emp_loss
            lessons.append(
                f"معايرة بايزية بسجل السهم ({emp_n} نافذة تاريخية بمعدل وصول {emp_win:.1f}%)"
            )

    # 2. Mistake-guard exhaustion/distribution adjustment
    if is_exhausted:
        prior_fail = upthrust_win_rate if upthrust_win_rate is not None else 61.3
        penalty = min(12.0, round(0.25 * cal_t, 1))
        cal_t = max(0.0, cal_t - penalty)
        cal_s = min(92.0, cal_s + penalty)
        reason_lbl = f"تصريف مؤسسي ({dist_val:.0f}/100)" if dist_val >= 65 else f"تشبع شرائي مع ضعف سيولة (RSI={rsi_val:.1f})"
        if penalty > 0.0:
            lessons.append(
                f"⚠️ درس التعلم الذاتي: خفض احتمال الصعود بـ -{penalty:.1f}% بسبب {reason_lbl} "
                f"(معدل فشل الصعود المماثل تاريخياً {prior_fail:.1f}%)"
            )
        else:
            lessons.append(
                f"⚠️ درس التعلم الذاتي: رصد {reason_lbl} يؤكد ضعف فرص الصعود "
                f"(معدل فشل الصعود المماثل تاريخياً {prior_fail:.1f}%)"
            )

    # Normalize cleanly to sum = 100.0
    tot_ts = cal_t + cal_s
    if tot_ts > 98.0:
        scale = 98.0 / tot_ts
        cal_t *= scale
        cal_s *= scale

    cal_t_r = round(cal_t, 1)
    cal_s_r = round(cal_s, 1)
    cal_r_r = round(max(0.0, 100.0 - cal_t_r - cal_s_r), 1)
    fix_diff = round(100.0 - (cal_t_r + cal_s_r + cal_r_r), 1)
    cal_r_r = round(max(0.0, cal_r_r + fix_diff), 1)

    upside_pct = ((t_lvl - close) / close) * 100.0
    downside_pct = ((close - s_lvl) / close) * 100.0
    expectancy_pct = round((cal_t_r / 100.0) * upside_pct - (cal_s_r / 100.0) * downside_pct, 2)

    eval_date = bars[-1]["date"] if bars and bars[-1]["date"] else dt.date.today().isoformat()
    avg_brier = None
    if record_ledger:
        avg_brier = _grade_and_record_ledger(
            symbol=symbol,
            exchange=exchange,
            eval_date=eval_date,
            close=close,
            target_price=t_lvl,
            stop_price=s_lvl,
            calibrated_prob_pct=cal_t_r,
            setup_regime=setup_regime,
            bars=bars,
        )

    mc_out = {
        **mc_res,
        "prob_hit_target_first_pct": cal_t_r,
        "calibrated_target_prob_pct": cal_t_r,
        "prob_hit_stop_first_pct": cal_s_r,
        "prob_stay_in_range_pct": cal_r_r,
        "mathematical_expectancy_pct": expectancy_pct,
    }
    if not lessons:
        lessons.append("المعايرة متوافقة مع التوزيع الإحصائي الحديث دون تحذيرات تصريف.")

    self_learning = {
        "raw_target_prob_pct": raw_t,
        "calibrated_target_prob_pct": cal_t_r,
        "empirical_hit_rate_pct": emp_win,
        "empirical_sample_size": emp_n,
        "brier_score": avg_brier,
        "learned_lesson_ar": " | ".join(lessons),
    }
    return mc_out, self_learning


# ---------------------------------------------------------------------------
# Macro Contagion Lookup (market_cache: macro_correlation_{SYM})
# ---------------------------------------------------------------------------

def get_cached_macro_sensitivity(symbol: str, exchange: str = "EGX") -> Optional[Dict[str, Any]]:
    """Fetch compact cached USD/Gold sensitivity summary for an EGX symbol (zero chart bloat)."""
    if str(exchange or "EGX").upper() != "EGX" or not symbol:
        return None
    sym_u = symbol.strip().upper()
    payload = _fetch_market_cache_payload(f"macro_correlation_{sym_u}")
    if not isinstance(payload, dict) or not payload.get("rating"):
        return None
    c_usd = _sf(payload.get("corr_usd_parallel"))
    c_gold = _sf(payload.get("corr_gold"))
    rating = str(payload.get("rating") or "")
    usd_txt = f"{c_usd:+.2f}" if c_usd is not None else "—"
    gold_txt = f"{c_gold:+.2f}" if c_gold is not None else "—"
    return {
        "rating": rating,
        "corr_usd_parallel": c_usd,
        "corr_gold": c_gold,
        "summary_ar": f"تحوط الماكرو ({rating}): ارتباط الدولار {usd_txt} | الذهب {gold_txt}",
    }


# ---------------------------------------------------------------------------
# Deterministic Bull vs. Bear Debate & FRA-Compliant Setup Regime Builder
# ---------------------------------------------------------------------------

def build_quant_intelligence_for_stock(
    *,
    symbol: str,
    exchange: str = "EGX",
    currency: str = "ج.م",
    close: Optional[float],
    rsi_14: Optional[float] = None,
    macd_histogram: Optional[float] = None,
    ema_50: Optional[float] = None,
    ema_200: Optional[float] = None,
    vwap_20: Optional[float] = None,
    r_vol: Optional[float] = None,
    support_1: Optional[float] = None,
    resistance_1: Optional[float] = None,
    stop_loss: Optional[float] = None,
    tactical_stop_loss: Optional[float] = None,
    support_1_is_distant: bool = False,
    acc_score: Optional[float] = None,
    dist_score: Optional[float] = None,
    king_ai_score: Optional[float] = None,
    fair_value: Optional[float] = None,
    valuation_upside_pct: Optional[float] = None,
    fund_score: Optional[float] = None,
    roe: Optional[float] = None,
    pe_ratio: Optional[float] = None,
    debt_to_equity: Optional[float] = None,
    is_loss_making: Optional[bool] = None,
    is_sharia_compliant: Optional[bool] = None,
    ohlcv_rows: Optional[Sequence[Dict[str, Any]]] = None,
    last_date: str = "",
    record_ledger: bool = True,
) -> Dict[str, Any]:
    """Build full deterministic Bull/Bear scorecard, setup regime, calibrated Monte Carlo, and macro context."""
    close_f = _sf(close)
    if close_f is None or close_f <= 0:
        return {}

    bull_case: List[str] = []
    bear_case: List[str] = []

    # 1. Deterministic Technical Score (0-100)
    tech_pts = 50.0
    above_ema50 = bool(ema_50 and close_f > ema_50)
    above_ema200 = bool(ema_200 and close_f > ema_200)
    above_vwap = bool(vwap_20 and close_f > vwap_20)
    if ema_50:
        if above_ema50:
            tech_pts += 12.0
            bull_case.append(f"فوق متوسط EMA50 ({ema_50}) — اتجاه متوسط داعم")
        else:
            tech_pts -= 12.0
            bear_case.append(f"كسر متوسط EMA50 ({ema_50}) — ضغط بيعي قصير/متوسط")
    if ema_200:
        if above_ema200:
            tech_pts += 10.0
        else:
            tech_pts -= 12.0
            bear_case.append(f"تحت EMA200 ({ema_200}) — مسار هابط رئيسي")
    if vwap_20:
        if above_vwap:
            tech_pts += 6.0
        else:
            tech_pts -= 6.0

    macd_h = _sf(macd_histogram)
    if macd_h is not None:
        if macd_h > 0:
            tech_pts += 6.0
        else:
            tech_pts -= 5.0

    rsi_v = _sf(rsi_14)
    if rsi_v is not None:
        if 48.0 <= rsi_v <= 68.0:
            tech_pts += 7.0
            bull_case.append(f"زخم متوازن RSI عند {rsi_v:.1f} بدون تشبع مفرط")
        elif rsi_v > 75.0:
            tech_pts -= 8.0
            bear_case.append(f"تشبع شرائي مرتفع (RSI={rsi_v:.1f}) يرفع احتمالات جني الأرباح")
        elif rsi_v < 35.0:
            tech_pts -= 6.0
            bear_case.append(f"ضعف زخم حاد قريب من ذروة البيع (RSI={rsi_v:.1f})")

    acc_v = _sf(acc_score) or 0.0
    dist_v = _sf(dist_score) or 0.0
    if acc_v >= 65.0:
        tech_pts += 12.0
        bull_case.append(f"رصد تجميع مؤسسي بقوة {acc_v:.0f}/100")
    if dist_v >= 65.0:
        tech_pts -= 18.0
        bear_case.append(f"تحذير تصريف مؤسسي (Distribution={dist_v:.0f}/100)")

    rvol_v = _sf(r_vol)
    if rvol_v is not None:
        if rvol_v >= 1.5 and (macd_h is None or macd_h >= 0) and dist_v < 65.0:
            tech_pts += 7.0
            bull_case.append(f"سيولة نسبية نشطة {rvol_v:.2f}x أعلى من المتوسط")
        elif rvol_v < 0.7:
            bear_case.append(f"سيولة منخفضة ({rvol_v:.2f}x) تُضعف الثقة في الاختراقات")

    king_v = _sf(king_ai_score)
    if king_v is not None and king_v >= 65.0:
        tech_pts += 6.0

    technical_score = int(round(max(0.0, min(100.0, tech_pts))))

    # 2. Deterministic Fundamental Score (0-100)
    base_fs = _sf(fund_score)
    fund_pts = float(base_fs) if base_fs is not None else 50.0
    up_pct = _sf(valuation_upside_pct)
    if up_pct is None and fair_value and fair_value > 0:
        up_pct = round(((fair_value - close_f) / close_f) * 100.0, 1)

    if up_pct is not None:
        if up_pct >= 20.0:
            if base_fs is None:
                fund_pts += 15.0
            bull_case.append(f"يتداول بأقل من القيمة العادلة بنسبة +{up_pct:.1f}% ({fair_value} {currency})")
        elif up_pct <= -15.0:
            if base_fs is None:
                fund_pts -= 15.0
            bear_case.append(f"مقوّم بأعلى من القيمة العادلة بفجوة {up_pct:.1f}% ({fair_value} {currency})")

    roe_v = _sf(roe)
    if roe_v is not None and roe_v >= 15.0:
        bull_case.append(f"كفاءة ربحية عالية على حقوق الملكية ROE={roe_v:.1f}%")
    if is_loss_making:
        fund_pts = min(fund_pts, 28.0)
        bear_case.append("الشركة تحقق خسائر صافية حالياً (ربحية سلبية)")
    de_v = _sf(debt_to_equity)
    if de_v is not None and de_v >= 1.5:
        bear_case.append(f"رافعة ديون مرتفعة (الديون/الحقوق {de_v:.2f}x)")

    fundamental_score = int(round(max(0.0, min(100.0, fund_pts))))

    # 3. Conflict Detection & FRA-Compliant Setup Regime Classification
    if not bull_case:
        bull_case.append(f"ثبات السعر عند {close_f} {currency} مع مراقبة مستويات الدعم")
    if not bear_case:
        bear_case.append("الالتزام التام بمستوى الوقف المحدد لحماية رأس المال")

    if (
        dist_v >= 65.0
        or (is_loss_making and technical_score < 48)
        or (technical_score < 32 and fundamental_score < 42)
        or (technical_score < 26 and not above_ema50 and not above_ema200 and fundamental_score < 60)
    ):
        setup_regime = "high_risk_avoid"
        regime_label_ar = "🔴 مخاطرة مرتفعة / تصريف — أولوية حماية السيولة"
        conflict_ar = "الأدلة البيعية أو الضعف المالي ترجّح كفة الحذر وتجنب التمركز حتى يثبت العكس."
    elif fundamental_score >= 60 and technical_score < 46:
        setup_regime = "value_in_downtrend"
        if up_pct is not None and up_pct <= -3.0:
            regime_label_ar = "⚖️ جودة مالية عالية مع سعر أعلى من القيمة العادلة ومسار هابط"
            conflict_ar = "تعارض واضح: السهم قوي مالياً لكن سعره الحالي أعلى من القيمة العادلة ومساره الفني ما زال هابطاً — الأفضل انتظار تصحيح أو إشارة انعكاس مؤكدة بدلاً من استباق الهبوط."
        elif up_pct is not None and up_pct >= 5.0:
            regime_label_ar = "⚖️ قيمة مالية في تصحيح فني — مراقبة الانعكاس"
            conflict_ar = "تعارض واضح: السهم جذاب مالياً وتقييمه رخيص مقارنة بالقيمة العادلة، لكن المسار الفني ما زال هابطاً — الأفضل انتظار إشارة انعكاس مؤكدة بدلاً من استباق الهبوط."
        else:
            regime_label_ar = "⚖️ أساسيات قوية في تصحيح فني — مراقبة الانعكاس"
            conflict_ar = "تعارض واضح: السهم قوي مالياً لكن المسار الفني ما زال هابطاً — الأفضل انتظار إشارة انعكاس مؤكدة بدلاً من استباق الهبوط."
    elif technical_score >= 62 and fundamental_score >= 55:
        setup_regime = "aligned_bullish"
        regime_label_ar = "🟢 توافق إيجابي كمي (فني + مالي)"
        conflict_ar = "توافق إيجابي بين الزخم الفني وجودة الأساسيات مع متابعة الالتزام بنقاط الدخول والوقف."
    elif technical_score >= 62 and fundamental_score < 50:
        setup_regime = "speculative_momentum"
        regime_label_ar = "⚡ زخم مضاربي عالي التذبذب — مشروط بالوقف"
        conflict_ar = "حركة مدفوعة بالزخم والسيولة اللحظية مع تقييم مالي ضعيف أو متضخم — تصلح لمتابعة قصيرة الأجل منضبطة بالوقف فقط."
    else:
        setup_regime = "neutral_watch"
        regime_label_ar = "🟡 نطاق عرضي متوازن — انتظار الحسم"
        conflict_ar = "توازن نسبي بين الإشارات الصاعدة والهابطة؛ يُراقَب اختراق المقاومة بسيولة أو التماسك عند الدعم."

    # 4. Market-Calibrated Monte Carlo + Self-Learning Calibration
    eff_stop = tactical_stop_loss if (support_1_is_distant and tactical_stop_loss) else stop_loss
    bars = _extract_sorted_bars(ohlcv_rows)
    raw_mc = run_monte_carlo_barrier_sim(
        bars,
        close=close_f,
        target_price=resistance_1,
        stop_price=eff_stop,
        exchange=exchange,
        symbol=symbol,
        last_date=last_date,
    )
    mc_cal, self_learning = calibrate_probabilities_with_market_outcomes(
        raw_mc,
        bars,
        symbol=symbol,
        exchange=exchange,
        close=close_f,
        rsi_14=rsi_v,
        r_vol=rvol_v,
        dist_score=dist_v,
        setup_regime=setup_regime,
        record_ledger=record_ledger,
    )

    # Conviction score blends technical, fundamental, and calibrated barrier probability
    cal_t_prob = float(mc_cal.get("calibrated_target_prob_pct") or 50.0)
    conviction = int(round(max(5.0, min(95.0, 0.40 * technical_score + 0.35 * fundamental_score + 0.25 * cal_t_prob))))
    if setup_regime == "high_risk_avoid":
        conviction = min(conviction, 35)

    macro = get_cached_macro_sensitivity(symbol, exchange=exchange)

    return {
        "symbol": str(symbol).upper(),
        "exchange": str(exchange).upper(),
        "currency": currency,
        "setup_regime": setup_regime,
        "setup_regime_label_ar": regime_label_ar,
        "conflict_resolution_ar": conflict_ar,
        "technical_score": technical_score,
        "fundamental_score": fundamental_score,
        "conviction_score": conviction,
        "is_sharia_compliant": is_sharia_compliant,
        "bull_case": bull_case[:4],
        "bear_case": bear_case[:4],
        "monte_carlo": mc_cal,
        "self_learning": self_learning,
        "macro_sensitivity": macro,
    }
