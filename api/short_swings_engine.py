"""
Short Swings Engine (الصفقات القصيرة ⚡ PRO)
Independent, decoupled swing trading engine for high-conviction momentum & trend-riding setups.
Features:
- 20-Day Base Breakout with Volume Surge (>= 140% of 20MA).
- Power Pullback to EMA10 in strong uptrends.
- Market Breadth Gate (>= 45% of liquid stocks above EMA50).
- Breakeven lock once price reaches +4.5% (effective starting the subsequent session).
- Conservative gap-down stop loss execution.
- EMA10 Trailing Stop (rides runners).
- Dynamic performance KPIs computed directly from executed historical trades.
"""
import os
import sys
import json
import gzip
import threading
import datetime as dt
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from api.short_swing_published import load_published_signals as _load_published_signals
from api.trade_liquidity import (EFFECTIVE_DATE, MIN_AVERAGE_TURNOVER,
                                MIN_MEDIAN_TURNOVER, MIN_CURRENT_TURNOVER,
                                MIN_ACTIVE_SESSIONS, POLICY_VERSION,
                                assess_entry_liquidity, recent_sessions)

CACHE_PATHS = [
    Path(__file__).parent / "data" / "short_swings_cache.json",
    Path("api/data/short_swings_cache.json"),
    Path("scratch/short_swings_cache.json"),
]

SAUDI_CACHE_PATHS = [
    Path(__file__).parent / "data" / "saudi_short_swings_cache.json",
    Path("api/data/saudi_short_swings_cache.json"),
    Path("scratch/saudi_short_swings_cache.json"),
]

SAUDI_SHORT_SWINGS_CACHE_KEY = "saudi_short_swings_v1"
SAUDI_HISTORY_CACHE_PATH = Path(__file__).parent / "data_cache" / "saudi_history_cache.pkl"

# Saudi institutional calibration (mirrors EGX EGP floors scaled to SAR TADAWUL liquidity)
SAUDI_BREADTH_MIN_TURNOVER = 2_000_000.0
SAUDI_ENTRY_AVG_TURNOVER = 25_000_000.0
SAUDI_ENTRY_MEDIAN_TURNOVER = 12_500_000.0
SAUDI_ENTRY_CURRENT_TURNOVER = 6_250_000.0
SAUDI_MIN_BREADTH = 0.65
SAUDI_START_DATE = "2021-01-01"

_SNAPSHOT_BOOTSTRAP_LOCK = threading.Lock()
_SNAPSHOT_BOOTSTRAPPED = False
_SAUDI_SNAPSHOT_BOOTSTRAPPED = False


def _normalize_exchange(exchange: Optional[str]) -> str:
    raw = (exchange or "EGX").strip().upper()
    if raw in ("TASI", "TADAWUL", "SA", "SAUDI"):
        return "TADAWUL"
    return raw or "EGX"


def _write_snapshot_files(result, paths=None):
    """Write shared computed data, never rebuild history from a visitor request."""
    target_paths = paths or CACHE_PATHS
    for cp in target_paths:
        try:
            cp.parent.mkdir(parents=True, exist_ok=True)
            tmp = cp.with_suffix(f".tmp.{os.getpid()}")
            with open(tmp, "w", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False)
            os.replace(tmp, cp)
            return
        except OSError:
            continue


def _restore_saved_snapshot():
    """One bounded read per process restores the durable result after HF rebuilds."""
    from api import stock_ai
    from api.daily_recovery_state import read_checkpoint
    stock_ai._init_supabase()
    row = read_checkpoint(stock_ai.supabase, "short_swings_latest")
    return (row or {}).get("payload", {}).get("swings")


def _persist_saved_snapshot(client, result):
    from api.daily_recovery_state import read_checkpoint, replace_checkpoint
    old = read_checkpoint(client, "short_swings_latest")
    saved = ((old or {}).get("payload") or {}).get("swings") or {}
    version = lambda item: (item.get("as_of") or "", item.get("computed_at") or "")
    if version(saved) > version(result):
        return False
    if not replace_checkpoint(client, "short_swings_latest", {"swings": result}, old):
        raise RuntimeError("Cannot persist shared short-swings display snapshot")
    return True


def _get_saudi_supabase_client():
    """Initialize SAUDI_SUPABASE client safely if configured."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        load_dotenv(Path(__file__).parent / ".env")
    except Exception:
        pass
    url = (os.getenv("SAUDI_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL") or "").strip()
    key = (
        os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SAUDI_SUPABASE_ANON_KEY")
        or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_ANON_KEY")
        or ""
    ).strip()
    if not url or not key:
        return None
    from supabase import create_client
    return create_client(url, key)


def _restore_saudi_snapshot():
    """Read durable Saudi short swings payload from SAUDI_SUPABASE.market_cache."""
    sb = _get_saudi_supabase_client()
    if not sb:
        return None
    try:
        res = (
            sb.table("market_cache")
            .select("payload")
            .eq("cache_key", SAUDI_SHORT_SWINGS_CACHE_KEY)
            .eq("country", "Saudi Arabia")
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if rows and isinstance(rows[0].get("payload"), dict):
            return rows[0]["payload"]
    except Exception as exc:
        print(f"[SHORT_SWINGS] Saudi snapshot restore failed: {type(exc).__name__}")
    return None


def _persist_saudi_snapshot(result: Dict[str, Any]) -> None:
    """Persist Saudi short swings payload into SAUDI_SUPABASE.market_cache."""
    sb = _get_saudi_supabase_client()
    if not sb:
        return
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    sb.table("market_cache").upsert(
        {
            "cache_key": SAUDI_SHORT_SWINGS_CACHE_KEY,
            "country": "Saudi Arabia",
            "payload": result,
            "computed_at": now_iso,
        },
        on_conflict="cache_key,country",
    ).execute()

EXIT_REASON_LABELS = {
    "ema10_break": "كسر متوسط EMA10 (حماية أرباح)",
    "stop_be": "وقف التعادل (حماية رأس المال)",
    "stop_loss": "وقف الخسارة الأولي (-4%)",
    "max_time": "انتهاء المدة الزمنية القصوى (20 جلسة)",
    "delisted_or_halted": "إغلاق لانتهاء المدة / توقف التداول"
}

def _price_date(value):
    """Use one session-date type for archive Timestamps and REST ISO strings."""
    if value is None or isinstance(value, (int, float, bool)):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def compute_kpis_from_trades(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute performance KPIs dynamically from the actual list of closed trades."""
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

    def _date_key(value: Any) -> str:
        if value is None:
            return ""
        parsed = pd.to_datetime(value, errors="coerce")
        return "" if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")

    # The engine publishes closed trades newest-first for the UI.  Performance
    # metrics must still be calculated chronologically or drawdown/compounding
    # changes when the API sort order changes.
    ordered_trades = sorted(trades, key=lambda t: _date_key(t.get("exit_date")))
    returns = [float(t.get("return_pct", 0.0)) for t in ordered_trades]
    sessions = [float(t.get("sessions") or t.get("holding_days") or 1) for t in ordered_trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]

    win_rate = (len(wins) / len(returns)) * 100.0 if returns else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    if gross_loss > 0:
        pf = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        pf = 99.0
    else:
        pf = 0.0

    avg_win = round(float(np.mean(wins)), 2) if wins else 0.0
    avg_loss = round(float(np.mean(losses)), 2) if losses else 0.0
    top_win = round(float(max(returns)), 2) if returns else 0.0
    avg_holding = round(float(np.mean(sessions)), 1) if sessions else 0.0

    # Equity curve calculation assuming equal risk allocation (1/15th max simultaneous slots)
    trade_returns = np.array(returns) / 100.0
    equity_curve = np.cumprod(1.0 + (trade_returns / 15.0))
    total_return = round(float((equity_curve[-1] - 1.0) * 100.0), 1) if len(equity_curve) else 0.0

    # Include the initial cash level as a peak.  Without it, a first losing
    # trade incorrectly reports 0% drawdown.
    curve_with_initial = np.concatenate(([1.0], equity_curve))
    peak = np.maximum.accumulate(curve_with_initial)
    drawdowns = (curve_with_initial - peak) / peak
    max_dd = round(float(abs(np.min(drawdowns)) * 100.0), 1) if len(drawdowns) else 0.0

    # Monthly trades calculation
    exit_dates = [_date_key(t.get("exit_date")) for t in ordered_trades if t.get("exit_date")]
    if exit_dates:
        try:
            min_d = dt.date.fromisoformat(min(exit_dates))
            max_d = dt.date.fromisoformat(max(exit_dates))
            months_count = max(1, (max_d.year - min_d.year) * 12 + (max_d.month - min_d.month) + 1)
            monthly_avg = round(len(trades) / months_count, 1)
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

def _resolve_archive_path() -> Optional[Path]:
    """Dynamically locate the latest valid EGX stock prices snapshot across environments."""
    hf_cache_dir = Path.home() / ".cache" / "huggingface" / "hub" / "datasets--weeasdwee--egx-historical-prices" / "snapshots"
    if hf_cache_dir.exists():
        egx_files = sorted(hf_cache_dir.glob("*/prices/EGX/stock_prices.json.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        if egx_files:
            return egx_files[0]
    
    project_candidates = [
        Path("api/data/stock_prices.json.gz"),
        Path("data/stock_prices.json.gz"),
        Path(__file__).parent / "data" / "stock_prices.json.gz",
    ]
    for p in project_candidates:
        if p.exists():
            return p
    return None

_METADATA_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_SAUDI_METADATA_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def _load_saudi_stock_metadata() -> Dict[str, Dict[str, Any]]:
    """Load Saudi Tadawul Arabic names & sectors from aliases + SAUDI_SUPABASE.stocks."""
    global _SAUDI_METADATA_CACHE
    if _SAUDI_METADATA_CACHE is not None:
        return _SAUDI_METADATA_CACHE

    meta_map: Dict[str, Dict[str, Any]] = {}
    try:
        from api.saudi_stock_aliases import SAUDI_STOCK_NAMES_AR
        for sym, name_ar in (SAUDI_STOCK_NAMES_AR or {}).items():
            ticker = str(sym).upper().split(".")[0]
            if ticker:
                meta_map[ticker] = {
                    "name_ar": name_ar or ticker,
                    "name_en": ticker,
                    "sector": "عام",
                    "logo": "",
                }
    except Exception as exc:
        print(f"[SHORT_SWINGS] Warning loading Saudi aliases: {exc}")

    try:
        sb = _get_saudi_supabase_client()
        if sb:
            res = (
                sb.table("stocks")
                .select("symbol,name,name_ar,sector")
                .eq("exchange", "TADAWUL")
                .limit(500)
                .execute()
            )
            for row in res.data or []:
                ticker = str(row.get("symbol") or "").upper().split(".")[0]
                if not ticker:
                    continue
                entry = meta_map.get(ticker, {"name_ar": ticker, "name_en": ticker, "sector": "عام", "logo": ""})
                if row.get("name_ar"):
                    entry["name_ar"] = row["name_ar"]
                elif row.get("name") and entry["name_ar"] == ticker:
                    entry["name_ar"] = row["name"]
                if row.get("name"):
                    entry["name_en"] = row["name"]
                if row.get("sector"):
                    entry["sector"] = row["sector"]
                meta_map[ticker] = entry
    except Exception as exc:
        print(f"[SHORT_SWINGS] Warning enriching Saudi metadata from SAUDI_SUPABASE: {exc}")

    _SAUDI_METADATA_CACHE = meta_map
    return meta_map


def _load_saudi_price_dataframe(start_date: str = SAUDI_START_DATE) -> pd.DataFrame:
    """Load Saudi TADAWUL historical OHLCV from local pickle cache + live tail from SAUDI_SUPABASE."""
    import pickle
    from concurrent.futures import ThreadPoolExecutor

    frames: List[pd.DataFrame] = []
    max_cached_date: Optional[str] = None
    candidates = [
        SAUDI_HISTORY_CACHE_PATH,
        Path("api/data_cache/saudi_history_cache.pkl"),
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, "rb") as fp:
                    payload = pickle.load(fp)
                bars_map = payload.get("bars_by_symbol") or {}
                for sym, bdf in bars_map.items():
                    if bdf is None or bdf.empty:
                        continue
                    idx_dates = pd.to_datetime(bdf.index, errors="coerce").strftime("%Y-%m-%d")
                    part = pd.DataFrame({
                        "symbol": str(sym).upper().split(".")[0],
                        "exchange": "TADAWUL",
                        "date": idx_dates,
                        "open": pd.to_numeric(bdf["Open"], errors="coerce").values,
                        "high": pd.to_numeric(bdf["High"], errors="coerce").values,
                        "low": pd.to_numeric(bdf["Low"], errors="coerce").values,
                        "close": pd.to_numeric(bdf["Close"], errors="coerce").values,
                        "volume": pd.to_numeric(bdf["Volume"], errors="coerce").values,
                    })
                    part = part[part["date"] >= start_date]
                    if not part.empty:
                        frames.append(part)
                if frames:
                    max_cached_date = str(payload.get("max_price_date") or "")[:10] or None
                break
            except Exception as exc:
                print(f"[SHORT_SWINGS] Saudi pickle load warning ({p}): {exc}")

    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    sb = _get_saudi_supabase_client()
    if sb:
        try:
            tail_start = max_cached_date or start_date
            if max_cached_date:
                # Only fetch incremental tail rows newer/equal to max_cached_date
                all_tail: List[Dict[str, Any]] = []
                page = 0
                page_size = 1000
                while True:
                    res = (
                        sb.table("stock_prices")
                        .select("symbol,exchange,date,open,high,low,close,volume")
                        .eq("exchange", "TADAWUL")
                        .gte("date", tail_start)
                        .range(page * page_size, (page + 1) * page_size - 1)
                        .execute()
                    )
                    rows = res.data or []
                    all_tail.extend(rows)
                    if len(rows) < page_size:
                        break
                    page += 1
                if all_tail:
                    df_tail = pd.DataFrame(all_tail)
                    df = pd.concat([df, df_tail], ignore_index=True) if not df.empty else df_tail
            else:
                # Parallel per-symbol fetch when local pickle cache is absent
                stocks_res = (
                    sb.table("stocks")
                    .select("symbol")
                    .eq("exchange", "TADAWUL")
                    .eq("is_active", True)
                    .limit(500)
                    .execute()
                )
                syms = sorted({
                    str(r.get("symbol") or "").strip()
                    for r in (stocks_res.data or [])
                    if str(r.get("symbol") or "").strip()
                })

                def _fetch_sym(sym: str) -> List[Dict[str, Any]]:
                    out: List[Dict[str, Any]] = []
                    pg = 0
                    while True:
                        r = (
                            sb.table("stock_prices")
                            .select("symbol,exchange,date,open,high,low,close,volume")
                            .eq("exchange", "TADAWUL")
                            .eq("symbol", sym)
                            .gte("date", start_date)
                            .order("date", desc=False)
                            .range(pg * 1000, (pg + 1) * 1000 - 1)
                            .execute()
                        )
                        chunk = r.data or []
                        out.extend(chunk)
                        if len(chunk) < 1000:
                            break
                        pg += 1
                    return out

                sym_rows: List[Dict[str, Any]] = []
                with ThreadPoolExecutor(max_workers=8) as pool:
                    for chunk in pool.map(_fetch_sym, syms):
                        sym_rows.extend(chunk)
                if sym_rows:
                    df = pd.DataFrame(sym_rows)
        except Exception as exc:
            print(f"[SHORT_SWINGS] Saudi Supabase price fetch warning: {exc}")

    return df


def load_stock_metadata(exchange: str = "EGX") -> Dict[str, Dict[str, Any]]:
    """Loads ticker names and sector metadata supporting case-insensitive schemas."""
    if _normalize_exchange(exchange) == "TADAWUL":
        return _load_saudi_stock_metadata()

    global _METADATA_CACHE
    if _METADATA_CACHE is not None:
        return _METADATA_CACHE

    meta_map: Dict[str, Dict[str, Any]] = {}
    
    # 1. Load from local symbol registries
    sym_dir = Path("symbols_data")
    if not sym_dir.exists():
        sym_dir = Path(__file__).parent / "symbols_data"
    if sym_dir.exists():
        for f in sym_dir.glob("Egypt_all_symbols_*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    for item in data:
                        raw_sym = item.get("Symbol") or item.get("symbol") or ""
                        ticker = raw_sym.upper().split(".")[0]
                        if ticker:
                            name_en = item.get("Name") or item.get("name") or item.get("name_en") or ticker
                            name_ar = item.get("ArabicName") or item.get("arabic_name") or item.get("NameAr") or item.get("name_ar") or name_en
                            sector = item.get("Sector") or item.get("sector") or "عام"
                            logo = item.get("Logo") or item.get("logo_url") or item.get("logo") or ""
                            meta_map[ticker] = {
                                "name_ar": name_ar,
                                "name_en": name_en,
                                "sector": sector,
                                "logo": logo
                            }
            except Exception as e:
                print(f"[SHORT_SWINGS] Warning loading metadata from {f}: {e}")

    # 2. Enrich from Supabase stocks table if available
    try:
        from api.stock_ai import _init_supabase, supabase
        _init_supabase()
        if supabase:
            res = supabase.table("stocks").select("symbol,name,name_ar").execute()
            for row in res.data or []:
                raw_sym = row.get("symbol") or ""
                ticker = raw_sym.upper().split(".")[0]
                if ticker:
                    if ticker not in meta_map:
                        meta_map[ticker] = {
                            "name_ar": row.get("name_ar") or row.get("name") or ticker,
                            "name_en": row.get("name") or ticker,
                            "sector": "عام",
                            "logo": ""
                        }
                    else:
                        if row.get("name_ar"):
                            meta_map[ticker]["name_ar"] = row["name_ar"]
                        if row.get("name"):
                            meta_map[ticker]["name_en"] = row["name"]
    except Exception as e:
        print(f"[SHORT_SWINGS] Warning enriching metadata from Supabase: {e}")

    _METADATA_CACHE = meta_map
    return meta_map

def _verified_intraday_quote(quote, now_cairo):
    """Only an audited, fresh current-session observation can initiate a live entry."""
    if not isinstance(quote, dict) or quote.get('verified') is not True:
        return None
    if now_cairo.weekday() in (4, 5) or not 600 <= now_cairo.hour * 60 + now_cairo.minute < 870:
        return None
    try:
        observed = dt.datetime.fromisoformat(str(quote.get('observed_at') or '').replace('Z', '+00:00'))
        price, volume = float(quote.get('price') or 0), float(quote.get('volume') or 0)
        if observed.tzinfo is None or not np.isfinite(price) or not np.isfinite(volume) or price <= 0 or volume <= 0:
            return None
        observed_cairo = observed.astimezone(now_cairo.tzinfo)
        if quote.get('date') != now_cairo.date().isoformat() or observed_cairo.date() != now_cairo.date():
            return None
        age = (now_cairo - observed_cairo).total_seconds()
        if not 0 <= age <= 900:
            return None
        return {'entry_price': price, 'observed_at': observed.isoformat()}
    except (ValueError, TypeError, OverflowError):
        return None


def compute_short_swings(
    *,
    phase: str = None,
    observed_quotes=None,
    exchange: str = "EGX",
    preloaded_df: Optional[pd.DataFrame] = None,
    preloaded_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generates the latest active and closed short swings with dynamic performance stats."""
    from zoneinfo import ZoneInfo

    ex = _normalize_exchange(exchange)
    is_saudi = ex == "TADAWUL"
    tz_name = "Asia/Riyadh" if is_saudi else "Africa/Cairo"
    now_cairo = dt.datetime.now(ZoneInfo(tz_name))
    if phase is None:
        minutes = now_cairo.hour * 60 + now_cairo.minute
        market_close_min = (15 * 60 + 10) if is_saudi else (14 * 60 + 30)
        phase = "midday" if 10 * 60 <= minutes < market_close_min else "close"
    if phase not in {"midday", "close"}:
        raise ValueError("Invalid short-swings phase")
    session_date = now_cairo.date().isoformat()
    df = pd.DataFrame()
    cache_paths = SAUDI_CACHE_PATHS if is_saudi else CACHE_PATHS

    if preloaded_df is not None and not preloaded_df.empty:
        df = preloaded_df.copy()
    elif is_saudi:
        try:
            df = _load_saudi_price_dataframe(SAUDI_START_DATE)
        except Exception as e:
            print(f"[SHORT_SWINGS] Saudi loader failed: {e}")
    else:
        # 1. Try standard history snapshot loader from api.hf_history_cache
        try:
            from api.hf_history_cache import load_history_snapshot
            snapshot_df = load_history_snapshot("EGX")
            if snapshot_df is not None and not snapshot_df.empty:
                df = snapshot_df.copy()
        except Exception as e:
            print(f"[SHORT_SWINGS] Snapshot loader unavailable: {e}")

        # 2. Fall back to resolved archive file
        if df.empty:
            archive_path = _resolve_archive_path()
            if archive_path and archive_path.exists():
                try:
                    with gzip.open(archive_path, "rt", encoding="utf-8") as f:
                        raw = json.load(f)
                    df = pd.DataFrame(raw)
                except Exception as e:
                    print(f"[SHORT_SWINGS] Failed reading archive {archive_path}: {e}")

    # If no data is available at all, return cached result if valid or explicit unavailable state
    if df.empty:
        for cp in cache_paths:
            if cp.exists():
                try:
                    with open(cp, "r", encoding="utf-8") as fp:
                        cached = json.load(fp)
                        if cached and "kpis" in cached and cached.get("closed_trades"):
                            return cached
                except Exception:
                    pass
        unavailable_payload = {
            "status": "unavailable",
            "kpis": compute_kpis_from_trades([]),
            "active_trades": [],
            "closed_trades": [],
            "total_active": 0,
            "total_closed": 0,
            "as_of": dt.date.today().isoformat()
        }
        if is_saudi:
            unavailable_payload.update({"market": "TASI", "currency": "SAR"})
        return unavailable_payload

    # Normalize columns and filter valid prices for target exchange
    # HF parquet/JSON snapshots expose pandas timestamps while Supabase rows
    # usually expose ISO strings.  Normalize both sources before comparing or
    # serializing dates; otherwise the standard loader crashes on Timestamp >=
    # str when building the final closed-trade payload.
    df["date"] = df["date"].map(_price_date)
    df = df.dropna(subset=["date"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    
    # Filter strictly for positive finite prices and valid candle geometry
    valid_mask = (
        np.isfinite(df["open"]) & np.isfinite(df["high"]) & np.isfinite(df["low"]) & np.isfinite(df["close"]) & np.isfinite(df["volume"])
        & (df["open"] > 0) & (df["high"] > 0) & (df["low"] > 0) & (df["close"] > 0) & (df["volume"] >= 0)
        & (df["high"] >= df[["open", "close", "low"]].max(axis=1))
        & (df["low"] <= df[["open", "close", "high"]].min(axis=1))
    )
    if "exchange" in df.columns:
        valid_mask = valid_mask & (df["exchange"].astype(str).str.upper() == ex)
        
    min_date = SAUDI_START_DATE if is_saudi else "2024-01-01"
    df = df[valid_mask].sort_values(["symbol", "date"]).reset_index(drop=True)
    df = df[df["date"] >= min_date].drop_duplicates(subset=["symbol", "date"], keep="last").reset_index(drop=True)

    # Augment with live prices from Supabase strictly for EGX exchange when not preloaded
    if not is_saudi and preloaded_df is None:
        max_archive_date = str(df["date"].max()) if not df.empty else "2024-01-01"
        try:
            from api.stock_ai import _init_supabase, supabase
            _init_supabase()
            if supabase:
                all_new = []
                page = 0
                page_size = 1000
                while True:
                    res = (
                        supabase.table("stock_prices")
                        .select("symbol,exchange,date,open,high,low,close,volume")
                        .eq("exchange", "EGX")
                        .gte("date", max_archive_date)
                        .range(page * page_size, (page + 1) * page_size - 1)
                        .execute()
                    )
                    rows = res.data or []
                    all_new.extend(rows)
                    if len(rows) < page_size:
                        break
                    page += 1
                if all_new:
                    df_new = pd.DataFrame(all_new)
                    df_new["date"] = df_new["date"].map(_price_date)
                    df_new = df_new.dropna(subset=["date"])
                    for col in ["open", "high", "low", "close", "volume"]:
                        df_new[col] = pd.to_numeric(df_new[col], errors="coerce")
                    df_new = df_new.dropna(subset=["open", "high", "low", "close", "volume"])
                    new_valid = (
                        np.isfinite(df_new["open"]) & np.isfinite(df_new["high"]) & np.isfinite(df_new["low"]) & np.isfinite(df_new["close"]) & np.isfinite(df_new["volume"])
                        & (df_new["open"] > 0) & (df_new["high"] > 0) & (df_new["low"] > 0) & (df_new["close"] > 0) & (df_new["volume"] >= 0)
                        & (df_new["high"] >= df_new[["open", "close", "low"]].max(axis=1))
                        & (df_new["low"] <= df_new[["open", "close", "high"]].min(axis=1))
                    )
                    df_new = df_new[new_valid]
                    if not df_new.empty:
                        df = pd.concat([df, df_new], ignore_index=True)
                        df = df.drop_duplicates(subset=["symbol", "date"], keep="last")
                        df = df.sort_values(["symbol", "date"]).reset_index(drop=True)
                        print(f"[SHORT_SWINGS] Merged {len(df_new)} live rows from Supabase (EGX); latest date: {df['date'].max()}")
        except Exception as merge_err:
            print(f"[SHORT_SWINGS] Warning: failed to merge live Supabase prices: {merge_err}")
    else:
        supabase = None

    # Do not let an erroneous future candle enter the current-session replay.
    df = df[df["date"] <= session_date]
    if df.empty:
        return {"status": "unavailable", "as_of": None, "active_trades": [], "closed_trades": []}
    if preloaded_meta is not None:
        meta = preloaded_meta
    elif is_saudi:
        meta = load_stock_metadata(exchange="TADAWUL")
    else:
        meta = load_stock_metadata()  # Keep 0-arg call untouched for EGX monkeypatches
    dates = sorted(df["date"].unique())

    # Build causal features per symbol
    groups = []
    for symbol, g in df.groupby("symbol", sort=False):
        g = g.copy().reset_index(drop=True)
        c = g["close"]
        h = g["high"]
        l = g["low"]
        v = g["volume"]
        o = g["open"]

        g["ema10"] = c.ewm(span=10, adjust=False).mean()
        g["ema20"] = c.ewm(span=20, adjust=False).mean()
        g["ema50"] = c.ewm(span=50, adjust=False).mean()

        prev_c = c.shift(1)
        tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
        g["atr14"] = tr.rolling(14).mean()
        g["atr_pct"] = g["atr14"] / c

        g["vol_ma20"] = v.rolling(20).mean()
        g["turnover"] = (c * v).rolling(20).mean()
        g["median_turnover"] = (c * v).rolling(20).median()
        g["current_turnover"] = c * v
        g["active_days"] = v.gt(0).rolling(20).sum()
        g["high20"] = h.rolling(20).max().shift(1)
        g["ret20"] = c / c.shift(20) - 1.0

        if is_saudi:
            # Saudi: measure market breadth across active liquid TADAWUL stocks (>=2M SAR),
            # and restrict entry signals to institutional leaders (>=25M SAR avg, >=12.5M median, >=6.25M current).
            g["breadth_liquid"] = (
                (np.arange(len(g)) >= 30)
                & (g["turnover"] >= SAUDI_BREADTH_MIN_TURNOVER)
                & (g["active_days"] >= MIN_ACTIVE_SESSIONS)
            )
            g["liquid"] = (
                (np.arange(len(g)) >= 30)
                & (g["turnover"] >= SAUDI_ENTRY_AVG_TURNOVER)
                & (g["median_turnover"] >= SAUDI_ENTRY_MEDIAN_TURNOVER)
                & (g["current_turnover"] >= SAUDI_ENTRY_CURRENT_TURNOVER)
                & (g["active_days"] >= MIN_ACTIVE_SESSIONS)
            )
            g["entry_liquid"] = g["liquid"]
            g["above_ema50"] = g["breadth_liquid"] & (c > g["ema50"])
        else:
            g["liquid"] = (
                (np.arange(len(g)) >= 30)
                & (g["turnover"] >= 1_000_000)
                & (g["active_days"] >= 15)
            )
            # Preserve pre-rollout simulations and published history. New entry
            # decisions require typical and current turnover, not a single spike.
            policy_applies = g["date"].astype(str).str[:10] >= EFFECTIVE_DATE
            g["entry_liquid"] = g["liquid"] & (g["turnover"] >= MIN_AVERAGE_TURNOVER) & (
                g["median_turnover"] >= MIN_MEDIAN_TURNOVER) & (g["current_turnover"] >= MIN_CURRENT_TURNOVER) & (
                g["active_days"] >= MIN_ACTIVE_SESSIONS)
            calendar_rows = {r.date: {'date': r.date, 'close': r.close, 'volume': r.volume}
                             for r in g[['date', 'close', 'volume']].itertuples(index=False)}
            # Sparse histories must be measured over actual exchange sessions, not
            # twenty trades spread over several months. Only prospective decisions
            # use the stronger policy, so historical simulations are not rewritten.
            for index in g.index[policy_applies]:
                day = g.at[index, 'date']
                recent = [calendar_rows[d] for d in recent_sessions(day) if d in calendar_rows]
                g.at[index, 'entry_liquid'] = bool(g.at[index, 'liquid']) and assess_entry_liquidity(recent, day)['eligible']
            g.loc[policy_applies, "liquid"] = g.loc[policy_applies, "entry_liquid"]
            g["above_ema50"] = g["liquid"] & (c > g["ema50"])
            g["breadth_liquid"] = g["liquid"]
        groups.append(g)

    df = pd.concat(groups, ignore_index=True)

    # Market breadth (lagged 1 day)
    breadth_raw = df[df["breadth_liquid"]].groupby("date")["above_ema50"].mean()
    df = df.merge(breadth_raw.shift(1).rename("breadth"), on="date", how="left")
    df["breadth"] = df["breadth"].fillna(0.5)

    mkt_ok = df["breadth"] >= (SAUDI_MIN_BREADTH if is_saudi else 0.45)
    trend_aligned = (
        df["liquid"]
        & (df["close"] > df["ema10"])
        & (df["ema10"] > df["ema20"])
        & (df["ema20"] > df["ema50"])
    )

    day_range = df["high"] - df["low"]
    close_pos = (df["close"] - df["low"]) / (day_range.replace(0, 1e-9))

    # Base Breakout
    sig_base_bo = (
        mkt_ok
        & trend_aligned
        & (df["close"] > df["high20"])
        & (df["volume"] >= df["vol_ma20"] * 1.4)
        & (df["close"] > df["open"])
        & (close_pos >= 0.70)
        & (df["ret20"] >= 0.05)
    )

    # Power Pullback
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

    if is_saudi:
        # On Tadawul, low-breadth defensive (~mkt_ok) counter-trend signals bleed during
        # multi-quarter TASI downtrends (2022/2025-2026); confine entries to healthy bull breadth.
        sig_rs_leader = pd.Series(False, index=df.index)
        sig_defensive_pb = pd.Series(False, index=df.index)
    else:
        # Defensive Relative Strength Leader (when broad breadth is below 45%):
        sig_rs_leader = (
            (~mkt_ok)
            & trend_aligned
            & (df["close"] >= df["high20"] * 0.985)
            & (df["volume"] >= df["vol_ma20"] * 1.25)
            & (df["close"] > df["open"])
            & (close_pos >= 0.70)
            & (df["ret20"] >= 0.07)
        )

        # Defensive Momentum Pullback in low-breadth markets:
        sig_defensive_pb = (
            (~mkt_ok)
            & df["liquid"]
            & (df["close"] > df["ema20"])
            & (df["ema20"] > df["ema50"])
            & (df["ret20"] >= 0.02)
            & (df["low"] <= df["ema10"] * 1.015)
            & (df["close"] > df["ema10"])
            & (df["volume"] >= df["vol_ma20"] * 1.1)
            & (df["close"] > df["open"])
            & (close_pos >= 0.65)
        )

    df["signal"] = sig_base_bo | sig_power_pb | sig_rs_leader | sig_defensive_pb
    df["sig_type"] = np.where(
        sig_rs_leader,
        "اختراق قمة مع قوة نسبية استثنائية (RS Leader)",
        np.where(
            sig_defensive_pb,
            "ارتداد زخم دفاعي في سوق متراجع",
            np.where(sig_base_bo, "اختراق قمة 20 جلسة مع انفجار سيولة", "ارتداد زخم من متوسط 10 أيام")
        )
    )

    next_date_map = dict(zip(dates, dates[1:]))
    market = {}
    for row in df[["symbol", "date", "open", "high", "low", "close", "volume", "turnover", "atr_pct", "ema10", "ema20", "entry_liquid"]].itertuples(index=False):
        market[(row.symbol, row.date)] = row

    sig_map = defaultdict(list)
    active_rows = df[df["signal"]][["symbol", "date", "close", "turnover", "sig_type", "ema10"]]
    for row in active_rows.itertuples(index=False):
        nxt = next_date_map.get(row.date)
        if nxt:
            sig_map[nxt].append({
                "symbol": row.symbol,
                "signal_date": row.date,
                "date": nxt,
                "close": row.close,
                "turnover": row.turnover,
                "sig_type": row.sig_type,
                "ema10": row.ema10
            })

    # Publication is authoritative entry intent. Later history corrections or
    # market-gate recalculations must not silently erase a delivered signal.
    published_signals = _load_published_signals(supabase) if supabase else []
    for published in published_signals:
        signal_date = published['signal_date']
        observed_entry = published.get('entry_kind') == 'intraday_observed' or published.get('entry_mode') == 'intraday'
        nxt = published.get('entry_date') if observed_entry else next_date_map.get(signal_date)
        if not nxt or nxt > session_date:
            continue
        if observed_entry and nxt not in dates:
            dates.append(nxt)
            dates.sort()
        symbol = published['symbol']
        prior_bar = market.get((symbol, signal_date))
        sig_map[nxt] = [s for s in sig_map[nxt] if s['symbol'] != symbol]
        sig_map[nxt].append({
            'symbol': symbol, 'signal_date': signal_date, 'date': nxt,
            'close': published['reference_close'],
            'turnover': prior_bar.turnover if prior_bar else 0,
            'sig_type': published.get('trigger_type') or 'إشارة منشورة محفوظة',
            'published': True,
            **({'entry_kind': 'intraday_observed', 'entry_price': published['entry_price'],
                'observed_at': published['observed_at']} if observed_entry else {}),
        })

    # A day's open/low predates a midday publication and cannot fill a new trade.
    sig_map[session_date] = [signal for signal in sig_map[session_date]
                             if signal.get('entry_kind') == 'intraday_observed' or signal.get('published')]
    if phase == 'midday':
        for _, row in df[(df['date'] == session_date) & df['signal'] & (df['volume'] > 0)].iterrows():
            quotes = observed_quotes or {}
            quote = _verified_intraday_quote(quotes.get(row['symbol']) or quotes.get(row['symbol'].upper().split('.')[0]), now_cairo)
            if quote and not any(s['symbol'] == row['symbol'] for s in sig_map[session_date]):
                sig_map[session_date].append({'symbol': row['symbol'], 'signal_date': session_date,
                    'date': session_date, 'close': row['close'], 'turnover': row['turnover'],
                    'sig_type': row['sig_type'], 'entry_kind': 'intraday_observed', **quote})

    # Run execution simulation
    positions = {}
    closed_trades = []

    for i, day in enumerate(dates):
        # 1. Update breakeven activations scheduled from previous session
        for sym, p in positions.items():
            if p.get("be_pending_activation"):
                p["be_active"] = True
                p["sl_price"] = max(p["sl_price"], p["entry_price"] * 1.003)
                p["be_pending_activation"] = False

        # 2. Check exits at Open for yesterday's pending signals
        for sym in list(positions):
            p = positions[sym]
            b = market.get((sym, day))
            age = i - p["index"]

            # If position has reached max holding limit (20 sessions), schedule/enforce exit
            if age >= 20 and not p.get("pending"):
                p["pending"] = "max_time"

            if not b or b.volume <= 0 or b.high == b.low:
                # Stock is not trading today or missing bar
                p["missing_sessions"] = p.get("missing_sessions", 0) + 1
                # If exit was pending, or max time reached (age >= 20), or stock missing for >= 5 sessions:
                # Close the trade at last recorded price so it does not linger indefinitely as a phantom trade.
                if p.get("pending") or age >= 20 or p["missing_sessions"] >= 5:
                    fill_price = p["last"] * (1 - 0.0015)
                    ret_pct = (fill_price / p["entry_price"] - 1) * 100
                    m_info = meta.get(sym.upper().split(".")[0], {})
                    reason_code = p.get("pending") or ("max_time" if age >= 20 else "delisted_or_halted")
                    closed_trades.append({
                        "symbol": sym,
                        "name_ar": m_info.get("name_ar", sym),
                        "name_en": m_info.get("name_en", sym),
                        "sector": m_info.get("sector", "عام"),
                        "entry_date": p["date"],
                        "exit_date": p.get("last_date") or day,
                        "entry_price": round(p["entry_price"], 3),
                        "exit_price": round(fill_price, 3),
                        "return_pct": round(ret_pct, 2),
                        "max_gain_pct": round(p["max_gain"], 2),
                        "sessions": min(age, 20),
                        "holding_days": min(age, 20),
                        "reason": reason_code,
                        "exit_reason": EXIT_REASON_LABELS.get(reason_code, "إغلاق حسب الخطة"),
                        "trigger_type": p["sig_type"],
                        "entry_mode": p.get('entry_mode'), "observed_at": p.get('observed_at')
                    })
                    del positions[sym]
                continue

            # Stock traded normally today
            p["missing_sessions"] = 0
            p["last_date"] = day

            if age >= 1 and p.get("pending"):
                fill_price = b.open * (1 - 0.0015)
                ret_pct = (fill_price / p["entry_price"] - 1) * 100
                m_info = meta.get(sym.upper().split(".")[0], {})
                reason_code = p["pending"]
                closed_trades.append({
                    "symbol": sym,
                    "name_ar": m_info.get("name_ar", sym),
                    "name_en": m_info.get("name_en", sym),
                    "sector": m_info.get("sector", "عام"),
                    "entry_date": p["date"],
                    "exit_date": day,
                    "entry_price": round(p["entry_price"], 3),
                    "exit_price": round(fill_price, 3),
                    "return_pct": round(ret_pct, 2),
                    "max_gain_pct": round(p["max_gain"], 2),
                    "sessions": age,
                    "holding_days": age,
                    "reason": reason_code,
                    "exit_reason": EXIT_REASON_LABELS.get(reason_code, "إغلاق حسب الخطة"),
                    "trigger_type": p["sig_type"],
                    "entry_mode": p.get('entry_mode'), "observed_at": p.get('observed_at')
                })
                del positions[sym]

        # 3. Enter new positions at today's open based on yesterday's signals
        day_signals = sorted(sig_map.get(day, []), key=lambda s: (not s.get('published', False), -s["turnover"]))
        for s in day_signals:
            if (len(positions) >= 15 and not s.get('published')) or s["symbol"] in positions:
                continue
            # Live policy enforcement: when published signals are active in live era,
            # unpublished signals cannot open ghost trades unless observed intraday.
            if published_signals and str(day)[:10] >= "2026-10-01" and not s.get("published") and s.get("entry_kind") != "intraday_observed":
                continue
            b = market.get((s["symbol"], day))
            preserved_observed = s.get('published') and s.get('entry_kind') == 'intraday_observed'
            if not preserved_observed and (not b or b.volume <= 0 or (b.high == b.low and s.get('entry_kind') != 'intraday_observed')):
                continue
            if str(day)[:10] >= EFFECTIVE_DATE and not b.entry_liquid:
                continue

            limit_price = s["close"]
            # Max opening gap allowed: +2.0% (consistent with Telegram alerts & strategy docs)
            if s.get('entry_kind') == 'intraday_observed':
                exec_price = s['entry_price']
            elif b.open <= limit_price * 1.02:
                exec_price = b.open
            elif b.low <= limit_price:
                exec_price = limit_price
            else:
                continue

            fill = exec_price if s.get('entry_kind') == 'intraday_observed' else exec_price * (1 + 0.0015)
            positions[s["symbol"]] = {
                "symbol": s["symbol"],
                "date": day,
                "signal_date": s["signal_date"],
                "published": bool(s.get('published')),
                "index": i,
                "entry_price": fill,
                "sl_price": fill * (1 - 0.04),
                "highest_high": fill,
                "max_gain": 0.0,
                "be_active": False,
                "be_pending_activation": False,
                "last": b.close if b else fill,
                "sig_type": s["sig_type"],
                "pending": None,
                "entry_kind": s.get('entry_kind'), "observed_at": s.get('observed_at'),
                "entry_mode": 'intraday' if s.get('entry_kind') == 'intraday_observed' else None,
                "is_new_entry": s.get('entry_kind') == 'intraday_observed' and not s.get('published')
            }

        # 4. Intraday defensive stop checks & state updates (Strictly Causal Sequence)
        for sym in list(positions):
            p = positions[sym]
            b = market.get((sym, day))
            if not b:
                continue
            p["last"] = b.close
            p["last_date"] = day
            p["missing_sessions"] = 0
            age = i - p["index"]
            if p.get('entry_kind') == 'intraday_observed' and age == 0:
                # Daily high/low include time before observation. No inferred
                # stop, peak or breakeven from that ambiguous entry-day candle.
                continue

            # First: Evaluate defensive stop loss against current session's low
            # For positions entered in earlier sessions (age >= 1)
            if age >= 1 and b.low <= p["sl_price"]:
                # Realistic Gap Fill Policy:
                # If market opened at or below stop loss (gap-down below stop), execute at open with slippage.
                # Otherwise, execute at stop price. In all cases, fill price cannot exceed b.high.
                if b.open <= p["sl_price"]:
                    raw_fill = min(b.high, b.open) * (1 - 0.0015)
                else:
                    raw_fill = max(b.low, p["sl_price"]) * (1 - 0.0015)
                fill_price = max(b.low * (1 - 0.0015), min(b.high, raw_fill))

                ret_pct = (fill_price / p["entry_price"] - 1) * 100
                m_info = meta.get(sym.upper().split(".")[0], {})
                reason_code = "stop_be" if p["be_active"] else "stop_loss"
                closed_trades.append({
                    "symbol": sym,
                    "name_ar": m_info.get("name_ar", sym),
                    "name_en": m_info.get("name_en", sym),
                    "sector": m_info.get("sector", "عام"),
                    "entry_date": p["date"],
                    "exit_date": day,
                    "entry_price": round(p["entry_price"], 3),
                    "exit_price": round(fill_price, 3),
                    "return_pct": round(ret_pct, 2),
                    "max_gain_pct": round(p["max_gain"], 2),
                    "sessions": age,
                    "holding_days": age,
                    "reason": reason_code,
                    "exit_reason": EXIT_REASON_LABELS.get(reason_code, "وقف خسارة"),
                    "trigger_type": p["sig_type"],
                    "entry_mode": p.get('entry_mode'), "observed_at": p.get('observed_at')
                })
                del positions[sym]
                continue

            # If not stopped out, update highest high and evaluate progression
            if b.high > p["highest_high"]:
                p["highest_high"] = b.high
                p["max_gain"] = max(p["max_gain"], (b.high / p["entry_price"] - 1) * 100)

            # Breakeven target (+4.5%): Schedule breakeven stop activation for the NEXT session
            # Eliminates intra-candle high/low ambiguity.
            gain = (b.high / p["entry_price"] - 1)
            if not p["be_active"] and not p.get("be_pending_activation") and gain >= 0.045:
                p["be_pending_activation"] = True

            # If already breakeven-secured and close falls below EMA10, schedule exit at next open
            if p["be_active"]:
                # Trail only from the next session: today's candle is already
                # past the open-fill decision above.  This keeps the displayed
                # trailing stop and the simulated exit rule consistent.
                p["sl_price"] = max(p["sl_price"], float(b.ema10))
                if b.close < b.ema10:
                    p["pending"] = "ema10_break"

            # Max holding period limit (20 sessions)
            if age >= 20 and not p["pending"]:
                p["pending"] = "max_time"

    last_date = dates[-1] if dates else dt.date.today().isoformat()
    active_output = []

    # 5. New Actionable Pending Signals detected for TOMORROW'S session:
    today_signals_df = df[(df["date"] == last_date) & (df["signal"])].sort_values("turnover", ascending=False)
    seen_symbols = set()
    today_rows = []
    for published in published_signals:
        if published['signal_date'] == last_date and published.get('entry_kind') != 'intraday_observed':
            bar = market.get((published['symbol'], last_date))
            today_rows.append({'symbol': published['symbol'], 'close': published['reference_close'],
                               'ema10': bar.ema10 if bar else published['reference_close'],
                               'sig_type': published.get('trigger_type') or 'إشارة منشورة محفوظة'})
    today_rows.extend(today_signals_df.head(15).to_dict('records'))
    # Allow actionable pending signals for the upcoming open when last_date is session_date,
    # or overnight/weekend before the next session opens (within 4 days, before 15:00 Cairo time).
    is_recent_close = (last_date == session_date) or (
        (dt.date.fromisoformat(session_date) - dt.date.fromisoformat(last_date)).days <= 4 and now_cairo.hour < 15
    )
    if (phase not in ('close', None)) or (not is_recent_close):
        today_rows = []
    for s_row in today_rows:
        sym = s_row["symbol"]
        if sym in positions or sym in seen_symbols:
            continue
        if last_date >= EFFECTIVE_DATE:
            bar = market.get((sym, last_date))
            if not bar or not bar.entry_liquid:
                continue
        seen_symbols.add(sym)
        close_price = round(float(s_row["close"]), 3)
        sl_price = round(close_price * 0.96, 3)
        m_info = meta.get(sym.upper().split(".")[0], {})
        active_output.append({
            "signal_id": f"{sym}_{last_date}",
            "symbol": sym,
            "name_ar": m_info.get("name_ar", sym),
            "name_en": m_info.get("name_en", sym),
            "sector": m_info.get("sector", "عام"),
            "entry_date": "جلسة الغد",
            "signal_date": last_date,
            "entry_price": close_price,
            "current_price": close_price,
            "reference_close": close_price,
            "return_pct": 0.0,
            "stop_loss": sl_price,
            "trailing_stop": sl_price,
            "ema10_trend": round(float(s_row["ema10"]), 3),
            "is_breakeven_protected": False,
            "max_gain_pct": 0.0,
            "trigger_type": s_row["sig_type"],
            "status": "إشارة دخول جديدة (جلسة الغد)",
            "is_pending_entry": True,
            "as_of": last_date
        })

    # 6. Active running positions (Strict separation from pending entries)
    for sym, p in positions.items():
        b = market.get((sym, last_date))
        if not b:
            continue
        curr_price = b.close
        if phase == 'midday' and p.get('entry_kind') == 'intraday_observed' and p['date'] == session_date:
            quotes = observed_quotes or {}
            current_observation = _verified_intraday_quote(quotes.get(sym) or quotes.get(sym.upper().split('.')[0]), now_cairo)
            curr_price = current_observation['entry_price'] if current_observation else p['entry_price']
        curr_gain = (curr_price / p["entry_price"] - 1) * 100
        active_stop = p["sl_price"]
        m_info = meta.get(sym.upper().split(".")[0], {})
        
        active_output.append({
            "signal_id": f"{sym}_{p.get('signal_date', p['date'])}",
            "symbol": sym,
            "name_ar": m_info.get("name_ar", sym),
            "name_en": m_info.get("name_en", sym),
            "sector": m_info.get("sector", "عام"),
            "entry_date": p["date"],
            "signal_date": p.get("signal_date", p["date"]),
            "published": bool(p.get('published')),
            "entry_kind": p.get('entry_kind'), "observed_at": p.get('observed_at'),
            "entry_mode": p.get('entry_mode'),
            "is_new_entry": bool(p.get('is_new_entry')),
            "entry_price": round(p["entry_price"], 3),
            "current_price": round(curr_price, 3) if b else None,
            "price_date": b.date if b else None,
            "reference_close": round(curr_price, 3) if b else None,
            "return_pct": round(curr_gain, 2) if b else None,
            "stop_loss": round(p["entry_price"] * (1 - 0.04), 3),
            "trailing_stop": round(active_stop, 3),
            "ema10_trend": round(float(b.ema10), 3) if b else None,
            "is_breakeven_protected": p["be_active"],
            "max_gain_pct": round(p["max_gain"], 2),
            "trigger_type": p["sig_type"],
            "status": ("مؤمنة بربح" if p["be_active"] else "قيد التداول") if b else "بيانات الجلسة غير متاحة",
            "is_pending_entry": False,
            "as_of": last_date
        })

    # Sort active output: pending signals first, then by return descending
    active_output.sort(key=lambda t: (0 if t.get("is_pending_entry") else 1, -float(t.get("return_pct", 0) or 0)))

    # Sort closed trades descending by exit date
    closed_trades.sort(key=lambda t: t["exit_date"], reverse=True)

    # Calculate dynamic performance metrics directly from all closed trades
    kpis = compute_kpis_from_trades(closed_trades)

    # Keep bounded evidence for operator review of a missing recent signal.
    # This is generated once with the daily calculation, never by visitors.
    audit_dates = dates[-2:]
    audit = df[df['date'].isin(audit_dates) & (df['volume'] >= df['vol_ma20'] * 1.2)].copy()
    signal_audit = []
    for _, row in audit.sort_values(['date', 'turnover'], ascending=False).head(120).iterrows():
        volume_ma20 = float(row['vol_ma20'] or 0.0)
        signal_audit.append({
            'symbol': row['symbol'], 'date': row['date'],
            'breadth': round(float(row['breadth']), 4),
            'volume_ratio': round(float(row['volume']) / volume_ma20, 3) if volume_ma20 > 0 else None,
            'liquid': bool(row['liquid']),
            'trend_aligned': bool(row['close'] > row['ema10'] > row['ema20'] > row['ema50']),
            'breakout': bool(row['close'] > row['high20']),
            'positive_candle': bool(row['close'] > row['open']),
            'return_20': round(float(row['ret20']), 4),
            'signal': bool(row['signal']),
        })

    closed_cutoff = "2025-01-01" if is_saudi else "2026-01-01"
    result = {
        "status": "ok",
        "kpis": kpis,
        "active_trades": active_output,
        "closed_trades": [t for t in closed_trades if str(t.get("exit_date") or "") >= closed_cutoff],
        "total_active": len(active_output),
        "total_closed": len(closed_trades),
        "as_of": last_date,
        "phase": phase,
        "session_complete": phase == "close",
        "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "signal_audit": signal_audit,
    }
    if is_saudi:
        result.update({"market": "TASI", "currency": "SAR", "exchange": "TADAWUL"})

    # Admin repair calculations must survive the next deployment too. Failed
    # persistence remains visible; the daily publisher retries it before sends.
    try:
        if is_saudi:
            _persist_saudi_snapshot(result)
        elif supabase:
            _persist_saved_snapshot(supabase, result)
    except Exception as error:
        print(f"[SHORT_SWINGS] Durable snapshot save failed: {type(error).__name__}")
        result["snapshot_persistence_error"] = type(error).__name__

    # Atomic write to cache files
    for cp in cache_paths:
        try:
            cp.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = cp.with_suffix(f".tmp.{os.getpid()}")
            with open(tmp_path, "w", encoding="utf-8") as fp:
                json.dump(result, fp, indent=2, ensure_ascii=False)
            os.replace(tmp_path, cp)
            break
        except Exception as write_err:
            print(f"[SHORT_SWINGS] Cache write failed for {cp}: {write_err}")
            continue

    return result


def get_cached_short_swings(exchange: str = "EGX") -> Dict[str, Any]:
    global _SNAPSHOT_BOOTSTRAPPED, _SAUDI_SNAPSHOT_BOOTSTRAPPED
    ex = _normalize_exchange(exchange)
    is_saudi = ex == "TADAWUL"
    target_paths = SAUDI_CACHE_PATHS if is_saudi else CACHE_PATHS

    # HF filesystems are ephemeral. A repository-shipped cache must not win
    # over the last successfully computed shared snapshot after a deployment.
    with _SNAPSHOT_BOOTSTRAP_LOCK:
        bootstrapped = _SAUDI_SNAPSHOT_BOOTSTRAPPED if is_saudi else _SNAPSHOT_BOOTSTRAPPED
        if not bootstrapped:
            try:
                saved = _restore_saudi_snapshot() if is_saudi else _restore_saved_snapshot()
                if saved and saved.get("status") == "ok" and saved.get("as_of"):
                    local = []
                    for cp in target_paths:
                        try:
                            with open(cp, encoding="utf-8") as stream:
                                local.append(json.load(stream))
                        except (OSError, ValueError):
                            pass
                    saved_version = (saved["as_of"], saved.get("computed_at") or "")
                    if not local or saved_version >= max((d.get("as_of") or "", d.get("computed_at") or "") for d in local):
                        _write_snapshot_files(saved, paths=target_paths)
            except Exception as error:
                print(f"[SHORT_SWINGS] Durable snapshot restore failed: {type(error).__name__}")
            finally:
                if is_saudi:
                    _SAUDI_SNAPSHOT_BOOTSTRAPPED = True
                else:
                    _SNAPSHOT_BOOTSTRAPPED = True
    for cp in target_paths:
        if cp.exists():
            try:
                with open(cp, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if data and "kpis" in data:
                        return data
            except Exception:
                continue
    fallback = {"status": "unavailable", "as_of": None, "active_trades": [],
                "closed_trades": [], "kpis": compute_kpis_from_trades([])}
    if is_saudi:
        fallback.update({"market": "TASI", "currency": "SAR"})
    return fallback

if __name__ == "__main__":
    res = compute_short_swings()
    print("Computed short swings successfully:")
    print("KPIs:", res.get("kpis"))
    print("Active:", len(res.get("active_trades", [])))
    print("Closed:", len(res.get("closed_trades", [])))
