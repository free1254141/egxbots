"""
api/agentic_chat/intraday_volume.py
Deterministic Time-of-Day Intraday Volume Pacing & Missing-Liquidity Guard (<1ms, $0 LLM cost).

Solves intraday liquidity distortion across EGX & GCC exchanges:
1. During active trading sessions, cumulative exchange volume is partial (0% at open -> 100% at close).
   Raw `r_vol = today_cum_vol / vol_sma20` is mechanically tiny early/mid-session (`0.00x–0.45x`), or `0.00x`
   before the intraday quote feed populates volume.
2. Uses a piecewise U-shaped cumulative intraday volume curve calibrated for opening auction & closing surges
   to compute a Bayesian time-paced projected `r_vol` once reliable partial volume (`>= 0.05x`, `>= 10m`) exists.
3. Falls back to the previous completed session's `r_vol` (computed from OHLCV bars excluding today) when
   today's intraday volume feed is missing/unpopulated (`< 0.05x`), while STILL preserving `0.00x` for genuinely
   illiquid/suspended stocks whose prior 10–20 completed sessions show dead/zero volume.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

# Empirical U-shaped intraday cumulative volume knots: (session_progress_u, expected_cum_volume_fraction)
# Captures opening auction surge (~1.45x rate), mid-morning (~0.96x), midday lull (~0.725x), closing ramp (~1.28x).
_USHAPE_KNOTS: Tuple[Tuple[float, float], ...] = (
    (0.00, 0.00),
    (0.11, 0.16),
    (0.35, 0.39),
    (0.75, 0.68),
    (1.00, 1.00),
)

# Exchange trading hours in local timezone: (tz_name, open_hhmm_mins, close_hhmm_mins, trading_weekdays_set)
# Python weekday(): Mon=0 .. Thu=3, Fri=4, Sat=5, Sun=6
_EXCHANGE_SCHEDULES: Dict[str, Tuple[str, int, int, frozenset[int]]] = {
    "EGX": ("Africa/Cairo", 10 * 60, 14 * 60 + 30, frozenset({6, 0, 1, 2, 3})),
    "TADAWUL": ("Asia/Riyadh", 10 * 60, 15 * 60, frozenset({6, 0, 1, 2, 3})),
    "TASI": ("Asia/Riyadh", 10 * 60, 15 * 60, frozenset({6, 0, 1, 2, 3})),
    "QSE": ("Asia/Qatar", 9 * 60 + 30, 13 * 60 + 15, frozenset({6, 0, 1, 2, 3})),
    "DFM": ("Asia/Dubai", 10 * 60, 15 * 60, frozenset({0, 1, 2, 3, 4})),
    "ADX": ("Asia/Dubai", 10 * 60, 15 * 60, frozenset({0, 1, 2, 3, 4})),
    "KSE": ("Asia/Kuwait", 9 * 60, 12 * 60 + 40, frozenset({6, 0, 1, 2, 3})),
    "COMMODITIES": ("UTC", 0, 23 * 60 + 59, frozenset({0, 1, 2, 3, 4})),
}
_DEFAULT_SCHEDULE = ("Africa/Cairo", 10 * 60, 14 * 60 + 30, frozenset({6, 0, 1, 2, 3}))


def _sf(val: Any) -> Optional[float]:
    try:
        if val is None or val == "":
            return None
        f = float(val)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def expected_cumulative_volume_fraction(progress_u: float) -> float:
    """Piecewise linear U-shaped cumulative volume fraction in [0.0, 1.0] for session progress u in [0, 1]."""
    u = max(0.0, min(1.0, float(progress_u)))
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    for idx in range(len(_USHAPE_KNOTS) - 1):
        u0, f0 = _USHAPE_KNOTS[idx]
        u1, f1 = _USHAPE_KNOTS[idx + 1]
        if u <= u1:
            span = max(u1 - u0, 1e-9)
            alpha = (u - u0) / span
            return f0 + alpha * (f1 - f0)
    return 1.0


def get_exchange_session_state(
    exchange: str = "EGX",
    now_dt: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    """Return deterministic local exchange trading session state and expected cumulative volume fraction."""
    raw_exch = str(exchange or "EGX").strip().upper()
    utc_offset_hours = 2
    try:
        from api.agentic_chat.market_registry import get_market_config

        cfg = get_market_config(raw_exch)
        exch_u = cfg.exchange
        tz_name = cfg.timezone_name
        open_mins = int(cfg.session_open_min)
        close_mins = int(cfg.session_close_min)
        allowed_days = frozenset(cfg.trading_weekdays)
        utc_offset_hours = int(cfg.utc_offset_hours)
    except Exception:
        exch_u = raw_exch or "EGX"
        tz_name, open_mins, close_mins, allowed_days = _EXCHANGE_SCHEDULES.get(exch_u, _DEFAULT_SCHEDULE)

    try:
        tz: dt.tzinfo = ZoneInfo(tz_name)
    except Exception:
        tz = dt.timezone(dt.timedelta(hours=utc_offset_hours))

    if now_dt is None:
        local_now = dt.datetime.now(tz)
    elif now_dt.tzinfo is None:
        local_now = now_dt.replace(tzinfo=tz)
    else:
        local_now = now_dt.astimezone(tz)

    today_str = local_now.strftime("%Y-%m-%d")
    is_trading_day = local_now.weekday() in allowed_days
    if exch_u == "EGX":
        try:
            from api.egx_trading_calendar import is_egx_session
            is_trading_day = bool(is_egx_session(local_now))
        except Exception:
            pass

    now_mins = local_now.hour * 60 + local_now.minute
    session_len_min = max(1, close_mins - open_mins)
    is_live = bool(is_trading_day and (open_mins <= now_mins < close_mins))

    if not is_trading_day:
        elapsed_min = 0
        progress_u = 0.0
    elif now_mins < open_mins:
        elapsed_min = 0
        progress_u = 0.0
    elif now_mins >= close_mins:
        elapsed_min = session_len_min
        progress_u = 1.0
    else:
        elapsed_min = now_mins - open_mins
        progress_u = elapsed_min / float(session_len_min)

    cum_frac = expected_cumulative_volume_fraction(progress_u)
    return {
        "exchange": exch_u,
        "today_str": today_str,
        "timezone_name": tz_name,
        "open_min": open_mins,
        "close_min": close_mins,
        "is_trading_day": is_trading_day,
        "is_live_session": is_live,
        "elapsed_min": elapsed_min,
        "session_len_min": session_len_min,
        "progress_u": round(progress_u, 4),
        "expected_cum_vol_frac": round(cum_frac, 4),
    }


def compute_prev_completed_r_vol(
    ohlcv_rows: Optional[Sequence[Dict[str, Any]]],
    *,
    exclude_date: Optional[str] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Compute (prev_completed_r_vol, avg_vol_20) from OHLCV history, skipping `exclude_date` (today's incomplete bar).
    Preserves `0.0` when prior completed sessions were genuinely dead/illiquid (>= 4 zero-vol days in last 10).
    """
    if not ohlcv_rows:
        return None, None

    ex_d = str(exclude_date or "")[:10]
    by_date: Dict[str, float] = {}
    undated_vols: List[float] = []

    for row in ohlcv_rows:
        if not isinstance(row, dict):
            continue
        v = _sf(row.get("volume"))
        if v is None or v < 0:
            continue
        d_str = str(row.get("date") or "")[:10]
        if d_str:
            if ex_d and d_str == ex_d:
                continue
            by_date[d_str] = v
        else:
            undated_vols.append(v)

    if by_date:
        ordered_dates = sorted(by_date.keys(), reverse=True)
        vols = [by_date[d] for d in ordered_dates[:21]]
    elif undated_vols:
        vols = undated_vols[:21]
    else:
        return None, None

    if len(vols) < 2:
        return None, None

    prev_vol = vols[0]
    recent_10 = vols[: min(10, len(vols))]
    zero_vol_days_10 = sum(1 for v in recent_10 if v <= 0)
    baseline = [v for v in vols[1:21] if v > 0]
    if not baseline or zero_vol_days_10 >= 4:
        avg_20 = sum(vols[: min(20, len(vols))]) / max(1, min(20, len(vols)))
        return 0.0, round(avg_20, 2)

    avg_vol_20 = sum(baseline) / float(len(baseline))
    if avg_vol_20 <= 0:
        return 0.0, 0.0
    if prev_vol <= 0:
        return 0.0, round(avg_vol_20, 2)
    return round(prev_vol / avg_vol_20, 2), round(avg_vol_20, 2)


def resolve_intraday_r_vol(
    raw_r_vol: Optional[float],
    row_date: Optional[str],
    *,
    exchange: str = "EGX",
    ohlcv_rows: Optional[Sequence[Dict[str, Any]]] = None,
    prev_r_vol: Optional[float] = None,
    now_dt: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    """
    Normalize relative volume (`r_vol`) during active intraday sessions and feed warmup gaps.

    Modes returned:
    - `eod`: completed session or end-of-session row (`progress >= 95%`), no intraday pacing adjustment needed.
    - `intraday_paced`: Bayesian-shrunk U-shaped time-paced projection of partial intraday volume.
    - `prev_close_fallback`: active session with unpopulated/tiny intraday `r_vol` (< 0.05) on an otherwise liquid stock;
      falls back cleanly to prior completed session's `r_vol`.
    - `intraday_unavailable`: active session with unpopulated intraday `r_vol` and no prior baseline available.
    """
    raw = _sf(raw_r_vol)
    sess = get_exchange_session_state(exchange=exchange, now_dt=now_dt)
    # Continuous 24-hour global markets (e.g. COMMODITIES) are not governed by discrete equity opening/closing auctions.
    if int(sess.get("session_len_min") or 0) >= 1400:
        return {
            "effective_r_vol": round(raw, 2) if raw is not None else None,
            "raw_r_vol": round(raw, 2) if raw is not None else None,
            "r_vol_mode": "eod",
            "is_intraday_adjusted": False,
            "session_progress_pct": None,
            "r_vol_note_ar": None,
        }
    today_str = sess["today_str"]
    row_d = str(row_date or "")[:10]
    is_today_row = bool(row_d and row_d == today_str)
    is_live = bool(sess["is_live_session"])
    elapsed_min = int(sess["elapsed_min"])
    cum_frac = float(sess["expected_cum_vol_frac"])
    prog_pct = round(float(sess["progress_u"]) * 100.0, 1) if is_live else None

    prev_rv, avg_vol_20 = compute_prev_completed_r_vol(ohlcv_rows, exclude_date=today_str)
    if prev_rv is None and prev_r_vol is not None:
        prev_rv = _sf(prev_r_vol)

    genuinely_illiquid = bool(
        (avg_vol_20 is not None and avg_vol_20 <= 0)
        or (prev_rv == 0.0 and avg_vol_20 is not None and avg_vol_20 < 5_000.0)
    )

    if genuinely_illiquid:
        return {
            "effective_r_vol": round(raw, 2) if raw is not None else 0.0,
            "raw_r_vol": round(raw, 2) if raw is not None else None,
            "r_vol_mode": "eod",
            "is_intraday_adjusted": False,
            "session_progress_pct": prog_pct,
            "r_vol_note_ar": None,
        }

    # Case A: Not in live trading hours
    if not is_live:
        if (
            is_today_row
            and (raw is None or raw < 0.05)
            and (avg_vol_20 is not None and avg_vol_20 >= 20_000.0)
        ):
            if prev_rv is not None and prev_rv >= 0.05:
                raw_txt = f"{raw:.2f}x" if raw is not None else "غير مكتمل"
                return {
                    "effective_r_vol": round(prev_rv, 2),
                    "raw_r_vol": round(raw, 2) if raw is not None else None,
                    "r_vol_mode": "prev_close_fallback",
                    "is_intraday_adjusted": True,
                    "session_progress_pct": None,
                    "r_vol_note_ar": (
                        f"بيانات حجم تداول جلسة اليوم قيد المزامنة ({raw_txt})؛ "
                        f"الرقم {prev_rv:.2f}x يمثل آخر جلسة مكتملة ولا يعني انعدام السيولة."
                    ),
                }
            return {
                "effective_r_vol": None,
                "raw_r_vol": round(raw, 2) if raw is not None else None,
                "r_vol_mode": "intraday_unavailable",
                "is_intraday_adjusted": True,
                "session_progress_pct": None,
                "r_vol_note_ar": "بيانات السيولة النسبية لليوم قيد التحديث ولا يُستدل منها على انعدام السيولة.",
            }
        return {
            "effective_r_vol": round(raw, 2) if raw is not None else None,
            "raw_r_vol": round(raw, 2) if raw is not None else None,
            "r_vol_mode": "eod",
            "is_intraday_adjusted": False,
            "session_progress_pct": None,
            "r_vol_note_ar": None,
        }

    # Case B: In live session, but indicator row is from a previous closed session (e.g. before intraday snapshot runs)
    if not is_today_row:
        return {
            "effective_r_vol": round(raw, 2) if raw is not None else None,
            "raw_r_vol": round(raw, 2) if raw is not None else None,
            "r_vol_mode": "eod",
            "is_intraday_adjusted": False,
            "session_progress_pct": prog_pct,
            "r_vol_note_ar": None,
        }

    # Case C: Live session AND today's row — check feed warmup / missing volume vs measurable partial volume
    if raw is None or raw < 0.05 or elapsed_min < 10:
        if prev_rv is not None and prev_rv >= 0.05:
            raw_txt = f"{raw:.2f}x" if raw is not None else "0.00x"
            eff_prev = round(prev_rv, 2)
            return {
                "effective_r_vol": eff_prev,
                "raw_r_vol": round(raw, 2) if raw is not None else None,
                "r_vol_mode": "prev_close_fallback",
                "is_intraday_adjusted": True,
                "session_progress_pct": prog_pct,
                "r_vol_note_ar": (
                    f"السيولة اللحظية للجلسة الحالية قيد التحديث (التراكمي المسجل {raw_txt})؛ "
                    f"الرقم {eff_prev:.2f}x يمثل آخر إغلاق مكتمل ولا يعني ضعف أو انعدام السيولة."
                ),
            }
        return {
            "effective_r_vol": None,
            "raw_r_vol": round(raw, 2) if raw is not None else None,
            "r_vol_mode": "intraday_unavailable",
            "is_intraday_adjusted": True,
            "session_progress_pct": prog_pct,
            "r_vol_note_ar": "بيانات السيولة النسبية اللحظية قيد التحديث أثناء الجلسة الحالية ولا يُستدل منها على انعدام السيولة قبل الإغلاق.",
        }

    # Measurable partial volume during live session -> Bayesian U-shaped time pacing
    if cum_frac < 0.95:
        projected = raw / max(cum_frac, 0.12)
        shrink = min(1.0, elapsed_min / 45.0)
        paced = shrink * projected + (1.0 - shrink) * max(raw, 1.0)
        paced = max(raw, min(paced, min(max(raw * 6.0, 4.0), 12.0)))
        paced_r = round(paced, 2)
        prog_int = int(round(sess["progress_u"] * 100.0))
        return {
            "effective_r_vol": paced_r,
            "raw_r_vol": round(raw, 2),
            "r_vol_mode": "intraday_paced",
            "is_intraday_adjusted": True,
            "session_progress_pct": prog_pct,
            "r_vol_note_ar": (
                f"السيولة النسبية المُعايرة زمنياً {paced_r:.2f}x "
                f"(التراكمي اللحظي {raw:.2f}x عند انقضاء {prog_int}% من الجلسة)"
            ),
        }

    # Final closing minutes (cum_frac >= 0.95)
    return {
        "effective_r_vol": round(raw, 2),
        "raw_r_vol": round(raw, 2),
        "r_vol_mode": "eod",
        "is_intraday_adjusted": False,
        "session_progress_pct": prog_pct,
        "r_vol_note_ar": None,
    }
