"""Compatibility helpers for callers that still request one archived symbol.

EGX historical series lives in the private HF Dataset; Saudi/GCC/Commodities
historical series lives in SAUDI_SUPABASE Storage (`market-history`).
The Supabase client argument is retained for Storage-backed markets and
backward compatibility with older callers.
"""

from typing import Optional

import pandas as pd

from api.hf_history_cache import load_symbol_history_snapshot

_SAUDI_STORAGE_EXCHANGES = frozenset({"TADAWUL", "TASI", "DFM", "ADX", "QSE", "COMMODITIES"})


def fetch_archived_stock_prices(
    supabase,
    symbol: str,
    exchange: str = "EGX",
) -> Optional[pd.DataFrame]:
    ex = str(exchange or "EGX").strip().upper()
    if ex == "TASI":
        ex = "TADAWUL"
    if ex in _SAUDI_STORAGE_EXCHANGES:
        from api.saudi_storage_history import load_storage_symbol_bars

        sb = supabase
        if sb is None:
            try:
                from api.saudi_telegram_dispatch import get_saudi_supabase
                sb = get_saudi_supabase()
            except Exception:
                sb = None
        if sb is None:
            return None
        bars = load_storage_symbol_bars(sb, ex, symbol)
        if not bars:
            return None
        return pd.DataFrame(bars).reset_index(drop=True)

    snapshot = load_symbol_history_snapshot("EGX", symbol)
    if snapshot.empty:
        return None
    return snapshot.drop(columns=["symbol", "exchange"]).reset_index(drop=True)


def merge_with_archive(
    supabase,
    symbol: str,
    db_df: pd.DataFrame,
    exchange: str = "EGX",
) -> pd.DataFrame:
    archived = fetch_archived_stock_prices(supabase, symbol, exchange=exchange)
    if archived is None or archived.empty:
        return db_df
    if db_df is None or db_df.empty:
        return archived
    combined = pd.concat([archived, db_df], ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
    return (combined.dropna(subset=["date"])
            .drop_duplicates(subset=["date"], keep="last")
            .sort_values("date").reset_index(drop=True))
