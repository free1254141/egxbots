"""Hybrid archive & rolling Postgres retention for Saudi/GCC/Commodities markets.

Mirrors EGX's Storage-first history architecture for SAUDI_SUPABASE:
- Supabase Storage bucket `market-history` (`prices/{EXCHANGE}/stock_prices.json.gz`,
  `prices/{EXCHANGE}/symbols/{SYMBOL}.json.gz`, `prices/{EXCHANGE}/metadata.json`)
  stores full multi-year OHLCV history (2010 -> latest).
- Postgres `stock_prices` retains only the recent rolling operational tail (~400 calendar
  days) so free-tier database storage stays compact while charts, ML pipelines, and
  Short Swings continue accessing complete multi-year history cleanly.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import math
import threading
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd

from api.perf_utils import BoundedTTLCache, SingleFlight

STORAGE_BUCKET = "market-history"
DB_RETENTION_CALENDAR_DAYS = 400

_SYMBOL_BARS_CACHE = BoundedTTLCache(max_entries=512, default_ttl=3600.0)
_SYMBOL_BARS_SF = SingleFlight()
_EXCHANGE_DF_CACHE = BoundedTTLCache(max_entries=8, default_ttl=3600.0)
_EXCHANGE_DF_SF = SingleFlight()
_CACHE_CLEAR_LOCK = threading.Lock()


def _finite_pos(val: Any) -> Optional[float]:
    try:
        num = float(val)
        return num if math.isfinite(num) and num > 0 else None
    except (TypeError, ValueError):
        return None


def _clean_vol(val: Any) -> float:
    try:
        num = float(val or 0)
        return float(round(num)) if math.isfinite(num) and num >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def _norm_bar(row: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    raw_date = row.get("date")
    if raw_date is None:
        return None
    d_str = str(raw_date)[:10]
    if len(d_str) != 10 or d_str[4] != "-":
        return None
    close = _finite_pos(row.get("close"))
    if close is None:
        return None
    open_p = _finite_pos(row.get("open")) or close
    high_raw = _finite_pos(row.get("high")) or close
    low_raw = _finite_pos(row.get("low")) or close
    return {
        "date": d_str,
        "open": round(open_p, 4),
        "high": round(max(high_raw, open_p, close), 4),
        "low": round(min(low_raw, open_p, close), 4),
        "close": round(close, 4),
        "volume": _clean_vol(row.get("volume")),
    }


def invalidate_storage_history_cache(exchange: Optional[str] = None) -> None:
    """Clear cached in-memory Storage frames/symbol bars for one or all exchanges."""
    ex = str(exchange or "").strip().upper()
    with _CACHE_CLEAR_LOCK:
        if not ex:
            _EXCHANGE_DF_CACHE.clear()
            _SYMBOL_BARS_CACHE.clear()
            return
        _EXCHANGE_DF_CACHE.clear()
        _SYMBOL_BARS_CACHE.clear()


def _download_with_retry(sb: Any, path: str, retries: int = 3) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return sb.storage.from_(STORAGE_BUCKET).download(path)
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(0.4 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    return b""


def _upload_with_retry(sb: Any, path: str, data: bytes, content_type: str, retries: int = 3) -> None:
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            sb.storage.from_(STORAGE_BUCKET).upload(
                path,
                data,
                {"content-type": content_type, "upsert": "true"},
            )
            return
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(0.4 * (attempt + 1))
    if last_exc is not None:
        raise last_exc


def _upload_gzip_json(sb: Any, path: str, payload: Any) -> None:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz = gzip.compress(raw, compresslevel=6)
    _upload_with_retry(sb, path, gz, "application/gzip")


def _upload_json(sb: Any, path: str, payload: Any) -> None:
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    _upload_with_retry(sb, path, raw, "application/json")


def load_storage_metadata(sb: Any, exchange: str) -> Dict[str, Any]:
    """Read `prices/{EXCHANGE}/metadata.json` from Supabase Storage, or `{}`."""
    if sb is None or not hasattr(sb, "storage"):
        return {}
    ex = str(exchange or "").strip().upper()
    if not ex:
        return {}
    try:
        raw = sb.storage.from_(STORAGE_BUCKET).download(f"prices/{ex}/metadata.json")
        parsed = json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def load_storage_symbol_bars(sb: Any, exchange: str, symbol: str) -> List[Dict[str, Any]]:
    """Load per-symbol gzipped OHLCV archive from Storage with LRU + SingleFlight caching."""
    if sb is None or not hasattr(sb, "storage"):
        return []
    ex = str(exchange or "").strip().upper()
    sym = str(symbol or "").strip().upper()
    if not ex or not sym:
        return []
    cache_key = f"{ex}:{sym}"
    found, cached = _SYMBOL_BARS_CACHE.get(cache_key)
    if found:
        return list(cached)

    def _fetch() -> List[Dict[str, Any]]:
        try:
            raw = sb.storage.from_(STORAGE_BUCKET).download(f"prices/{ex}/symbols/{sym}.json.gz")
            records = json.loads(gzip.decompress(raw))
        except Exception:
            return []
        if not isinstance(records, list):
            return []
        by_date: Dict[str, Dict[str, Any]] = {}
        for item in records:
            if not isinstance(item, Mapping):
                continue
            bar = _norm_bar(item)
            if bar is not None:
                by_date[bar["date"]] = bar
        return [by_date[d] for d in sorted(by_date.keys())]

    bars = _SYMBOL_BARS_SF.do(cache_key, _fetch)
    if bars:
        _SYMBOL_BARS_CACHE.set(cache_key, bars)
    return list(bars)


def load_storage_exchange_df(sb: Any, exchange: str) -> pd.DataFrame:
    """Load combined exchange gzipped history (`prices/{EXCHANGE}/stock_prices.json.gz`)."""
    cols = ["symbol", "exchange", "date", "open", "high", "low", "close", "volume"]
    if sb is None or not hasattr(sb, "storage"):
        return pd.DataFrame(columns=cols)
    ex = str(exchange or "").strip().upper()
    if not ex:
        return pd.DataFrame(columns=cols)

    found, cached_df = _EXCHANGE_DF_CACHE.get(ex)
    if found:
        return cached_df.copy()

    def _fetch() -> pd.DataFrame:
        try:
            raw = sb.storage.from_(STORAGE_BUCKET).download(f"prices/{ex}/stock_prices.json.gz")
            records = json.loads(gzip.decompress(raw))
        except Exception:
            return pd.DataFrame(columns=cols)
        if not isinstance(records, list) or not records:
            return pd.DataFrame(columns=cols)
        df = pd.DataFrame(records)
        if df.empty or "date" not in df.columns or "symbol" not in df.columns:
            return pd.DataFrame(columns=cols)
        df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
        df["exchange"] = ex
        df["date"] = df["date"].astype(str).str.slice(0, 10)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["symbol", "date", "close"])
        df = df[df["close"] > 0]
        df["open"] = df["open"].fillna(df["close"])
        df["high"] = df[["high", "open", "close"]].max(axis=1)
        df["low"] = df[["low", "open", "close"]].min(axis=1)
        df["volume"] = df["volume"].fillna(0.0).clip(lower=0.0)
        df = df[cols].drop_duplicates(subset=["symbol", "date"], keep="last").sort_values(["symbol", "date"]).reset_index(drop=True)
        return df

    df_out = _EXCHANGE_DF_SF.do(ex, _fetch)
    if not df_out.empty:
        _EXCHANGE_DF_CACHE.set(ex, df_out)
    return df_out.copy()


def merge_bars_storage_with_live(
    storage_bars: Iterable[Mapping[str, Any]],
    live_rows: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge Storage archive bars with live DB rows; live DB wins on date collisions."""
    by_date: Dict[str, Dict[str, Any]] = {}
    for row in storage_bars or ():
        if isinstance(row, Mapping):
            bar = _norm_bar(row)
            if bar is not None:
                by_date[bar["date"]] = bar
    for row in live_rows or ():
        if isinstance(row, Mapping):
            bar = _norm_bar(row)
            if bar is not None:
                by_date[bar["date"]] = bar
    return [by_date[d] for d in sorted(by_date.keys())]


def refresh_exchange_storage_archive(
    sb: Any,
    exchange: str,
    recent_bars_by_sym: Mapping[str, Iterable[Mapping[str, Any]]],
) -> Dict[str, Any]:
    """Merge recent bars into `prices/{EXCHANGE}/` gzipped archives and metadata.json."""
    if sb is None or not hasattr(sb, "storage"):
        return {"ok": False, "reason": "storage_unavailable"}
    ex = str(exchange or "").strip().upper()
    if not ex:
        return {"ok": False, "reason": "invalid_exchange"}

    prior_meta = load_storage_metadata(sb, ex)
    prior_rows = int(prior_meta.get("rows") or 0)
    prior_first = str(prior_meta.get("first_date") or "")[:10]

    by_sym_date: Dict[str, Dict[str, Dict[str, Any]]] = {}
    try:
        raw = _download_with_retry(sb, f"prices/{ex}/stock_prices.json.gz")
        existing = json.loads(gzip.decompress(raw))
        if isinstance(existing, list):
            for row in existing:
                if not isinstance(row, Mapping):
                    continue
                sym = str(row.get("symbol") or "").strip().upper()
                bar = _norm_bar(row)
                if sym and bar is not None:
                    by_sym_date.setdefault(sym, {})[bar["date"]] = {
                        "symbol": sym,
                        "exchange": ex,
                        **bar,
                    }
    except Exception as dl_exc:
        if prior_rows > 0:
            return {
                "ok": False,
                "exchange": ex,
                "reason": "existing_archive_download_failed",
                "error": str(dl_exc),
            }

    if prior_rows > 0 and not by_sym_date:
        return {
            "ok": False,
            "exchange": ex,
            "reason": "existing_archive_download_failed",
        }

    changed_syms: List[str] = []
    for raw_sym, bars in (recent_bars_by_sym or {}).items():
        sym = str(raw_sym or "").strip().upper()
        if not sym:
            continue
        sym_map = by_sym_date.setdefault(sym, {})
        sym_changed = False
        for row in bars or ():
            if not isinstance(row, Mapping):
                continue
            bar = _norm_bar(row)
            if bar is None:
                continue
            rec = {"symbol": sym, "exchange": ex, **bar}
            prev = sym_map.get(bar["date"])
            if prev != rec:
                sym_map[bar["date"]] = rec
                sym_changed = True
        if sym_changed:
            changed_syms.append(sym)

    if not changed_syms and by_sym_date:
        return {
            "ok": True,
            "exchange": ex,
            "skipped": True,
            "symbols_changed": 0,
        }

    all_rows: List[Dict[str, Any]] = []
    min_date = "9999-12-31"
    max_date = "0000-01-01"
    for sym in sorted(by_sym_date.keys()):
        sym_map = by_sym_date[sym]
        for d in sorted(sym_map.keys()):
            all_rows.append(sym_map[d])
            if d < min_date:
                min_date = d
            if d > max_date:
                max_date = d

    if not all_rows:
        return {"ok": False, "exchange": ex, "reason": "empty_archive"}

    if prior_rows > 0 and (
        len(all_rows) < int(prior_rows * 0.90)
        or (prior_first and min_date > prior_first)
    ):
        return {
            "ok": False,
            "exchange": ex,
            "reason": "archive_regression_blocked",
            "merged_rows": len(all_rows),
            "prior_rows": prior_rows,
            "merged_first_date": min_date,
            "prior_first_date": prior_first,
        }

    # Upload only updated per-symbol archives sequentially over single HTTP/2 connection
    for sym in changed_syms:
        sym_map = by_sym_date.get(sym) or {}
        ordered = [sym_map[d] for d in sorted(sym_map.keys())]
        _upload_gzip_json(sb, f"prices/{ex}/symbols/{sym}.json.gz", ordered)

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    _upload_gzip_json(sb, f"prices/{ex}/stock_prices.json.gz", all_rows)
    metadata = {
        "exchange": ex,
        "rows": len(all_rows),
        "symbols": len(by_sym_date),
        "first_date": min_date,
        "last_date": max_date,
        "published_at": now_iso,
        "format": "json.gz",
        "symbol_files": len(by_sym_date),
    }
    _upload_json(sb, f"prices/{ex}/metadata.json", metadata)
    invalidate_storage_history_cache(ex)
    return {
        "ok": True,
        "exchange": ex,
        "symbols_changed": len(changed_syms),
        "metadata": metadata,
    }


def prune_old_stock_prices(
    sb: Any,
    exchange: str,
    keep_days: int = DB_RETENTION_CALENDAR_DAYS,
    *,
    verify_storage: bool = True,
    max_staleness_days: int = 21,
) -> Dict[str, Any]:
    """Prune Postgres `stock_prices` older than `keep_days` once Storage archive is verified."""
    if sb is None:
        return {"pruned": False, "reason": "supabase_unavailable"}
    ex = str(exchange or "").strip().upper()
    if not ex:
        return {"pruned": False, "reason": "invalid_exchange"}
    eff_keep = max(int(keep_days), 180)
    today = dt.date.today()
    cutoff_date = (today - dt.timedelta(days=eff_keep)).isoformat()

    if verify_storage:
        meta = load_storage_metadata(sb, ex)
        last_str = str(meta.get("last_date") or "")[:10]
        rows_cnt = int(meta.get("rows") or 0)
        try:
            last_dt = dt.date.fromisoformat(last_str)
        except ValueError:
            last_dt = None
        if not last_dt or rows_cnt <= 0 or (today - last_dt).days > max_staleness_days:
            return {
                "pruned": False,
                "exchange": ex,
                "reason": "storage_archive_missing_or_stale",
                "metadata_last_date": last_str,
                "metadata_rows": rows_cnt,
            }

    earliest_res = (
        sb.table("stock_prices")
        .select("date")
        .eq("exchange", ex)
        .lt("date", cutoff_date)
        .order("date", desc=False)
        .limit(1)
        .execute()
    )
    earliest_rows = getattr(earliest_res, "data", None) or []
    if not earliest_rows:
        return {"pruned": True, "exchange": ex, "chunks": 0, "cutoff_date": cutoff_date, "deleted_chunks": 0}

    earliest_date = str(earliest_rows[0]["date"])[:10]
    try:
        start_year = int(earliest_date[:4])
        end_year = int(cutoff_date[:4])
    except ValueError:
        return {"pruned": False, "exchange": ex, "reason": "invalid_earliest_date"}

    # Delete quarterly (<17k rows per statement) so Postgres never hits PostgREST statement timeout.
    chunks = 0
    quarter_bounds = (
        ("01-01", "04-01"),
        ("04-01", "07-01"),
        ("07-01", "10-01"),
        ("10-01", None),
    )
    for yr in range(start_year, end_year + 1):
        for idx, (q_start_md, q_end_md) in enumerate(quarter_bounds):
            q_start = f"{yr}-{q_start_md}"
            q_end = f"{yr}-{q_end_md}" if q_end_md else f"{yr + 1}-01-01"
            if q_start >= cutoff_date:
                break
            upper = min(q_end, cutoff_date)
            q = sb.table("stock_prices").delete().eq("exchange", ex)
            if not (yr == start_year and idx == 0):
                q = q.gte("date", q_start)
            q.lt("date", upper).execute()
            chunks += 1

    return {"pruned": True, "exchange": ex, "cutoff_date": cutoff_date, "deleted_chunks": chunks}
