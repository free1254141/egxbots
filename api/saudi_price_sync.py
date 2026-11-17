"""
Daily Price & Equal-Weight TASI Index Sync for Saudi Market (TADAWUL).
Fetches latest daily/intraday OHLCV bars from Yahoo Finance (`{symbol}.SR`)
with optional TradingView (`TADAWUL`) fallback, upserts into SAUDI_SUPABASE.stock_prices,
and maintains continuity of SAUDI_SUPABASE.market_index (`source='equal_weight'`).
"""
from __future__ import annotations

import datetime as dt
import math
import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

RIYADH_TZ = ZoneInfo("Asia/Riyadh")
DEFAULT_YAHOO_CHUNK_SIZE = 60
DEFAULT_TV_FALLBACK_LIMIT = 300
DEFAULT_TV_WORKERS = 4
DEFAULT_TV_SYMBOL_TIMEOUT_S = 12
DEFAULT_TV_BATCH_TIMEOUT_S = 240
MAX_ABS_DAILY_RET = 0.35


def _saudi_history_cache_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "api", "data_cache", "saudi_history_cache.pkl")


def _clean_float(val: Any) -> Optional[float]:
    try:
        num = float(val)
        if math.isnan(num) or math.isinf(num):
            return None
        return num
    except (TypeError, ValueError):
        return None


def _clean_volume(val: Any) -> int:
    num = _clean_float(val)
    if num is None or num < 0:
        return 0
    return int(round(num))


def _load_active_saudi_stocks(sb) -> List[Dict[str, Any]]:
    res = (
        sb.table("stocks")
        .select("id,symbol,exchange,is_active")
        .eq("exchange", "TADAWUL")
        .limit(1000)
        .execute()
    )
    rows = res.data or []
    active: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("is_active") is False:
            continue
        sym = str(row.get("symbol") or "").strip().split(".")[0]
        if sym and sym.isdigit():
            active.append({"id": row.get("id"), "symbol": sym})
    active.sort(key=lambda r: r["symbol"])
    return active


def _extract_bars_from_yf_frame(
    frame: pd.DataFrame,
    symbols: List[str],
    max_date_str: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """Parse both single-ticker and MultiIndex group_by='ticker' yfinance frames."""
    parsed: Dict[str, List[Dict[str, Any]]] = {}
    if frame is None or frame.empty:
        return parsed

    def _rows_from_df(sym_df: pd.DataFrame) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if sym_df is None or sym_df.empty:
            return out
        for idx, row in sym_df.iterrows():
            close = _clean_float(row.get("Close"))
            if close is None or close <= 0:
                continue
            date_val = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
            if date_val > max_date_str:
                continue
            open_p = _clean_float(row.get("Open")) or close
            high_p = _clean_float(row.get("High")) or close
            low_p = _clean_float(row.get("Low")) or close
            adj_c = _clean_float(row.get("Adj Close")) or close
            vol = _clean_volume(row.get("Volume"))
            out.append(
                {
                    "date": date_val,
                    "open": round(open_p if open_p > 0 else close, 4),
                    "high": round(max(high_p, close, open_p), 4),
                    "low": round(min(low_p if low_p > 0 else close, close, open_p), 4),
                    "close": round(close, 4),
                    "adjusted_close": round(adj_c if adj_c > 0 else close, 4),
                    "volume": vol,
                    "source": "yahoo",
                }
            )
        return out

    if isinstance(frame.columns, pd.MultiIndex):
        lvl0 = set(frame.columns.get_level_values(0))
        for sym in symbols:
            ticker = f"{sym}.SR"
            if ticker in lvl0:
                rows = _rows_from_df(frame[ticker])
                if rows:
                    parsed[sym] = rows
    elif len(symbols) == 1:
        rows = _rows_from_df(frame)
        if rows:
            parsed[symbols[0]] = rows
    return parsed


def _default_yf_fetcher(symbols: List[str], lookback_days: int, max_date_str: str) -> Dict[str, List[Dict[str, Any]]]:
    import yfinance as yf

    out: Dict[str, List[Dict[str, Any]]] = {}
    period = f"{max(5, int(lookback_days))}d"
    for i in range(0, len(symbols), DEFAULT_YAHOO_CHUNK_SIZE):
        chunk = symbols[i : i + DEFAULT_YAHOO_CHUNK_SIZE]
        tickers = [f"{s}.SR" for s in chunk]
        try:
            df = yf.download(
                tickers=tickers if len(tickers) > 1 else tickers[0],
                period=period,
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
            out.update(_extract_bars_from_yf_frame(df, chunk, max_date_str))
        except Exception as exc:
            print(f"[SAUDI-PRICE-SYNC] Yahoo chunk {i} failed: {exc}")
    return out


def _default_tv_fetcher(
    symbols: List[str],
    lookback_days: int,
    max_date_str: str,
    symbol_timeout_s: float = DEFAULT_TV_SYMBOL_TIMEOUT_S,
    batch_timeout_s: float = DEFAULT_TV_BATCH_TIMEOUT_S,
) -> Dict[str, List[Dict[str, Any]]]:
    if not symbols:
        return {}
    try:
        from tvDatafeed import TvDatafeed, Interval  # type: ignore
    except Exception:
        return {}

    n_bars = max(5, int(lookback_days))
    thread_local = threading.local()

    def _get_tv() -> TvDatafeed:
        tv = getattr(thread_local, "tv", None)
        if tv is None:
            tv = TvDatafeed()
            thread_local.tv = tv
        return tv

    def _fetch_one(sym: str) -> Tuple[str, List[Dict[str, Any]]]:
        for attempt in range(2):
            try:
                df = _get_tv().get_hist(symbol=sym, exchange="TADAWUL", interval=Interval.in_daily, n_bars=n_bars)
                if df is None or df.empty:
                    if attempt == 0:
                        thread_local.tv = TvDatafeed()
                        continue
                    return sym, []
                rows: List[Dict[str, Any]] = []
                for idx, row in df.iterrows():
                    close = _clean_float(row.get("close"))
                    if close is None or close <= 0:
                        continue
                    date_val = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
                    if date_val > max_date_str:
                        continue
                    open_p = _clean_float(row.get("open")) or close
                    high_p = _clean_float(row.get("high")) or close
                    low_p = _clean_float(row.get("low")) or close
                    vol = _clean_volume(row.get("volume"))
                    rows.append(
                        {
                            "date": date_val,
                            "open": round(open_p if open_p > 0 else close, 4),
                            "high": round(max(high_p, close, open_p), 4),
                            "low": round(min(low_p if low_p > 0 else close, close, open_p), 4),
                            "close": round(close, 4),
                            "adjusted_close": round(close, 4),
                            "volume": vol,
                            "source": "tvdatafeed",
                        }
                    )
                return sym, rows
            except Exception:
                if attempt == 0:
                    thread_local.tv = None
                    continue
                return sym, []
        return sym, []

    targets = list(symbols[:DEFAULT_TV_FALLBACK_LIMIT])
    out: Dict[str, List[Dict[str, Any]]] = {}
    pool = ThreadPoolExecutor(max_workers=DEFAULT_TV_WORKERS)
    try:
        pending = {pool.submit(_fetch_one, sym) for sym in targets}
        deadline = time.monotonic() + max(float(symbol_timeout_s), float(batch_timeout_s))
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            done, pending = wait(
                pending,
                timeout=min(float(symbol_timeout_s), remaining),
                return_when=FIRST_COMPLETED,
            )
            if not done:
                # All remaining workers stalled for a full symbol timeout; avoid blocking the pipeline.
                break
            for fut in done:
                try:
                    sym, rows = fut.result()
                    if rows:
                        out[sym] = rows
                except Exception:
                    continue
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return out


def _upsert_in_batches(sb, table: str, rows: List[Dict[str, Any]], on_conflict: str, batch_size: int = 250) -> None:
    for i in range(0, len(rows), batch_size):
        sb.table(table).upsert(rows[i : i + batch_size], on_conflict=on_conflict).execute()


def _fetch_existing_price_ids(sb, min_date: str) -> Dict[Tuple[str, str], Any]:
    """Load existing (symbol, date) -> primary key id for TADAWUL since min_date."""
    existing: Dict[Tuple[str, str], Any] = {}
    offset = 0
    page_size = 1000
    while True:
        res = (
            sb.table("stock_prices")
            .select("id,symbol,date")
            .eq("exchange", "TADAWUL")
            .gte("date", min_date)
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = list(res.data or [])
        for row in rows:
            sym = str(row.get("symbol") or "").strip().split(".")[0]
            d_str = str(row.get("date") or "")[:10]
            rid = row.get("id")
            if sym and d_str and rid is not None:
                existing[(sym, d_str)] = rid
        if len(rows) < page_size:
            break
        offset += page_size
    return existing


def _sync_stock_prices_idempotent(sb, rows: List[Dict[str, Any]], batch_size: int = 250) -> None:
    """SAUDI_SUPABASE.stock_prices only has PK(id), so update matched ids and insert new bars."""
    if not rows:
        return
    min_date = min(str(r["date"])[:10] for r in rows)
    existing_ids = _fetch_existing_price_ids(sb, min_date)

    to_update: List[Dict[str, Any]] = []
    to_insert: List[Dict[str, Any]] = []
    for row in rows:
        key = (str(row["symbol"]).strip(), str(row["date"])[:10])
        rid = existing_ids.get(key)
        if rid is not None:
            to_update.append({"id": rid, **row})
        else:
            to_insert.append(row)

    for i in range(0, len(to_update), batch_size):
        sb.table("stock_prices").upsert(to_update[i : i + batch_size], on_conflict="id").execute()
    for i in range(0, len(to_insert), batch_size):
        sb.table("stock_prices").insert(to_insert[i : i + batch_size]).execute()


def _update_equal_weight_market_index(
    sb,
    bars_by_symbol: Dict[str, List[Dict[str, Any]]],
    target_dates: List[str],
) -> List[Dict[str, Any]]:
    """Continue SAUDI_SUPABASE.market_index equal-weight series seamlessly."""
    if not target_dates:
        return []
    prior_res = (
        sb.table("market_index")
        .select("date,close,ret,source")
        .eq("exchange", "TADAWUL")
        .eq("source", "equal_weight")
        .order("date", desc=True)
        .limit(30)
        .execute()
    )
    prior_rows = list(prior_res.data or [])
    prior_by_date: Dict[str, float] = {
        str(r["date"])[:10]: float(r["close"])
        for r in prior_rows
        if r.get("date") and _clean_float(r.get("close")) is not None
    }

    # Build close[sym][date] lookup from newly fetched bars
    closes_by_sym: Dict[str, Dict[str, float]] = {}
    for sym, bars in bars_by_symbol.items():
        cmap = {}
        for b in bars:
            c = _clean_float(b.get("close"))
            if c is not None and c > 0:
                cmap[str(b["date"])[:10]] = c
        if cmap:
            closes_by_sym[sym] = cmap

    all_bar_dates = sorted({d for cmap in closes_by_sym.values() for d in cmap.keys()})
    updated_index_rows: List[Dict[str, Any]] = []

    for d in sorted(set(target_dates)):
        if d not in all_bar_dates:
            continue
        pos = all_bar_dates.index(d)
        if pos == 0:
            continue
        prev_bar_date = all_bar_dates[pos - 1]
        # Prefer close from an earlier index date strictly before d
        earlier_idx_dates = sorted(k for k in prior_by_date.keys() if k < d)
        if not earlier_idx_dates:
            continue
        base_close = prior_by_date[earlier_idx_dates[-1]]

        rets: List[float] = []
        for cmap in closes_by_sym.values():
            c_cur = cmap.get(d)
            c_prev = cmap.get(prev_bar_date)
            if c_cur and c_prev and c_prev > 0:
                ret = (c_cur / c_prev) - 1.0
                if -MAX_ABS_DAILY_RET <= ret <= MAX_ABS_DAILY_RET:
                    rets.append(ret)

        if len(rets) < 10:
            continue
        avg_ret = sum(rets) / len(rets)
        new_close = base_close * (1.0 + avg_ret)
        row = {
            "exchange": "TADAWUL",
            "date": d,
            "close": round(new_close, 6),
            "ret": round(avg_ret, 6),
            "source": "equal_weight",
        }
        updated_index_rows.append(row)
        prior_by_date[d] = row["close"]

    if updated_index_rows:
        _upsert_in_batches(sb, "market_index", updated_index_rows, on_conflict="exchange,date", batch_size=50)
    return updated_index_rows


def invalidate_saudi_history_cache() -> bool:
    cache_path = _saudi_history_cache_path()
    try:
        if os.path.exists(cache_path):
            os.remove(cache_path)
            return True
    except OSError as exc:
        print(f"[SAUDI-PRICE-SYNC] Failed to remove history cache: {exc}")
    return False


def sync_saudi_daily_prices(
    phase: str = "close",
    lookback_days: int = 7,
    sb=None,
    stock_rows: Optional[List[Dict[str, Any]]] = None,
    yf_fetcher: Optional[Callable[[List[str], int, str], Dict[str, List[Dict[str, Any]]]]] = None,
    tv_fetcher: Optional[Callable[[List[str], int, str], Dict[str, List[Dict[str, Any]]]]] = None,
) -> Dict[str, Any]:
    """Fetch and upsert latest TADAWUL stock bars + equal-weight market_index."""
    if sb is None:
        from api.saudi_telegram_dispatch import get_saudi_supabase
        sb = get_saudi_supabase()

    stocks = stock_rows if stock_rows is not None else _load_active_saudi_stocks(sb)
    if not stocks:
        return {"success": False, "error": "No active TADAWUL stocks", "synced": 0, "total": 0}

    stock_id_by_sym = {str(s["symbol"]).strip(): s.get("id") for s in stocks if s.get("symbol")}
    symbols = sorted(stock_id_by_sym.keys())
    today_riyadh = dt.datetime.now(RIYADH_TZ).date().isoformat()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    bars_by_sym = (yf_fetcher or _default_yf_fetcher)(symbols, lookback_days, today_riyadh)
    max_bar_date = max(
        (str(b["date"])[:10] for rows in bars_by_sym.values() for b in rows),
        default="",
    )

    missing_syms = [
        sym for sym in symbols
        if sym not in bars_by_sym or (max_bar_date and max((b["date"] for b in bars_by_sym[sym]), default="") < max_bar_date)
    ]
    if missing_syms:
        tv_bars = (tv_fetcher or _default_tv_fetcher)(missing_syms, lookback_days, today_riyadh)
        for sym, rows in tv_bars.items():
            existing = {b["date"]: b for b in bars_by_sym.get(sym, [])}
            for r in rows:
                existing.setdefault(r["date"], r)
            if existing:
                bars_by_sym[sym] = sorted(existing.values(), key=lambda x: x["date"])

    upsert_rows: List[Dict[str, Any]] = []
    synced_syms: set[str] = set()
    synced_dates: set[str] = set()
    for sym, rows in bars_by_sym.items():
        sid = stock_id_by_sym.get(sym)
        if not rows:
            continue
        synced_syms.add(sym)
        for b in rows:
            d_str = str(b["date"])[:10]
            synced_dates.add(d_str)
            row_payload: Dict[str, Any] = {
                "symbol": sym,
                "exchange": "TADAWUL",
                "date": d_str,
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
                "volume": b["volume"],
                "adjusted_close": b.get("adjusted_close", b["close"]),
                "source": b.get("source", "yahoo"),
                "updated_at": now_iso,
            }
            if sid is not None:
                row_payload["stock_id"] = sid
            upsert_rows.append(row_payload)

    if upsert_rows:
        _sync_stock_prices_idempotent(sb, upsert_rows)

    latest_date = max(synced_dates, default=None)
    prior_idx_res = (
        sb.table("market_index")
        .select("date")
        .eq("exchange", "TADAWUL")
        .eq("source", "equal_weight")
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    prior_max_idx_date = str((prior_idx_res.data or [{}])[0].get("date") or "")[:10]
    dates_to_index = [
        d for d in sorted(synced_dates)
        if not prior_max_idx_date or d > prior_max_idx_date or d in {today_riyadh, latest_date}
    ]
    index_rows = _update_equal_weight_market_index(sb, bars_by_sym, dates_to_index)

    if upsert_rows:
        invalidate_saudi_history_cache()

    if latest_date:
        latest_synced_syms = {
            s for s in synced_syms
            if any(str(b.get("date") or "")[:10] == latest_date for b in bars_by_sym.get(s, []))
        }
    else:
        latest_synced_syms = synced_syms
    failed_symbols = [s for s in symbols if s not in latest_synced_syms]
    return {
        "success": len(latest_synced_syms) > 0,
        "phase": phase,
        "synced": len(latest_synced_syms),
        "total": len(symbols),
        "bars_upserted": len(upsert_rows),
        "latest_date": latest_date,
        "index_dates_updated": [r["date"] for r in index_rows],
        "failed_symbols": failed_symbols,
    }


if __name__ == "__main__":
    print(sync_saudi_daily_prices())
