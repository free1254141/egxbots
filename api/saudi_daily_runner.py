"""
Saudi Market (TASI / Tadawul) Multi-Phase Daily Orchestrator.
Runs independent of EGX on Asia/Riyadh Tadawul hours:
  - morning (10:20 Riyadh): intraday price sync, technical indicators/traps/market status,
    Short Swings monitoring + VIP Telegram alerts, news, disclosures, cache invalidation.
  - midday  (12:45 Riyadh): intraday price sync, technical indicators/traps/market status,
    Short Swings monitoring + VIP Telegram alerts, news, disclosures, cache invalidation.
  - close   (15:25 Riyadh): full price sync, saudi_pipeline_bootstrap(reuse_models=True),
    saudi_backtest_and_systems, VIP-only Telegram (Short Swings + Open Recs + Market Outlook),
    news, disclosures, full cache invalidation.

Records runs durably into main SUPABASE.daily_job_runs using job_type in
("saudi_morning", "saudi_midday", "saudi_close") so /admin Jobs history tracks them
while keeping EGX daily_bot queries untouched.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import uuid
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

RIYADH_TZ = ZoneInfo("Asia/Riyadh")
SAUDI_COUNTRY = "Saudi Arabia"
SAUDI_CACHE_TAGS = [
    "daily-market-data",
    "daily-symbols",
    "daily-recommendations",
    "daily-short-swings",
    "daily-news-data",
    "daily-disclosures",
]


def saudi_job_type_for_phase(phase: str) -> str:
    norm = (phase or "close").strip().lower()
    if norm == "morning":
        return "saudi_morning"
    if norm == "midday":
        return "saudi_midday"
    return "saudi_close"


def _persist_job_run(
    main_sb,
    job_run_id: str,
    job_type: str,
    status: str,
    started_at: str,
    steps_log: List[Dict[str, Any]],
    total_symbols: int,
    trigger: str,
    error: Optional[str] = None,
) -> None:
    if not main_sb:
        return
    try:
        main_sb.table("daily_job_runs").upsert(
            {
                "id": job_run_id,
                "job_type": job_type,
                "status": status,
                "started_at": started_at,
                "completed_at": dt.datetime.now(dt.timezone.utc).isoformat()
                if status in ("completed", "failed")
                else None,
                "steps": json.dumps(steps_log),
                "total_symbols": total_symbols,
                "trigger": "manual" if str(trigger).lower() == "manual" else "scheduled",
                "error": error,
            }
        ).execute()
    except Exception as exc:
        print(f"[SAUDI-DAILY] Failed to persist daily_job_runs row: {exc}")


def _record_step(
    steps_log: List[Dict[str, Any]],
    step_name: str,
    status: str,
    count: int = 0,
    details: str = "",
) -> None:
    steps_log.append(
        {
            "step": step_name,
            "status": status,
            "count": int(count or 0),
            "details": details,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )


def _run_intraday_snapshot_and_short_swings(
    saudi_sb,
    phase: str,
) -> Dict[str, Any]:
    """Lightweight intraday refresh for morning/midday without retraining ML models."""
    from api.short_swings_engine import compute_short_swings
    from scripts.saudi_backtest_and_systems import _bars_dict_to_short_swings_df, _load_saudi_stocks_meta
    from scripts.saudi_pipeline_bootstrap import (
        COUNTRY,
        EXCHANGE,
        _chunked_upsert,
        _clean_num,
        compute_stock_indicators_snapshot,
        detect_daily_traps,
        index_metrics,
        load_saudi_market_and_prices,
        sync_saudi_metadata_and_symbols,
    )

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    symbols_meta, _ = sync_saudi_metadata_and_symbols(saudi_sb)
    symbols = [s["Code"] for s in symbols_meta]
    _, idx_rows, bars_by_symbol = load_saudi_market_and_prices(saudi_sb, symbols)

    ind_rows: List[Dict[str, Any]] = []
    for sym in symbols:
        if sym in bars_by_symbol and not bars_by_symbol[sym].empty:
            rec, _, _ = compute_stock_indicators_snapshot(sym, bars_by_symbol[sym], now_iso)
            ind_rows.append(rec)

    if ind_rows:
        _chunked_upsert(
            saudi_sb,
            "stock_technical_indicators",
            ind_rows,
            on_conflict="symbol,exchange",
            batch_size=100,
        )

    latest_date = max((r["date"] for r in ind_rows), default=dt.datetime.now(RIYADH_TZ).date().isoformat())

    bars_map = {}
    for sym in symbols:
        bdf = bars_by_symbol.get(sym)
        if bdf is None or bdf.empty:
            continue
        last_bar = bdf.iloc[-1]
        bars_map[sym] = {
            "symbol": sym,
            "open": float(last_bar["Open"]),
            "high": float(last_bar["High"]),
            "low": float(last_bar["Low"]),
            "close": float(last_bar["Close"]),
        }
    traps_payload = detect_daily_traps(ind_rows, bars_map, as_of=latest_date, max_per_side=8)
    for cache_k in (f"scanner_traps_{EXCHANGE}", "daily_traps_snapshot"):
        saudi_sb.table("market_cache").upsert(
            {"cache_key": cache_k, "country": COUNTRY, "payload": traps_payload, "computed_at": now_iso},
            on_conflict="cache_key,country",
        ).execute()

    tasi_metrics = index_metrics(idx_rows)
    adv_cnt = sum(1 for r in ind_rows if float(r.get("change_pct") or 0) > 0)
    dec_cnt = sum(1 for r in ind_rows if float(r.get("change_pct") or 0) < 0)
    above_sma50 = sum(1 for r in ind_rows if float(r.get("close") or 0) >= float(r.get("sma_50") or 0))
    above_sma200 = sum(1 for r in ind_rows if float(r.get("close") or 0) >= float(r.get("sma_200") or 0))
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
        regime, reject_buys = "panic", True
    elif not tasi_metrics.get("above_sma50") and ret_5d <= -2.0:
        regime, reject_buys = "bear", True
    elif tasi_metrics.get("above_sma20") and ret_5d >= 0:
        regime, reject_buys = "bull", False
    else:
        regime, reject_buys = "neutral", False

    market_status_payload = {
        "tasi": tasi_series,
        "egx30": tasi_series,
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
    saudi_sb.table("market_cache").upsert(
        {"cache_key": f"market_status_{COUNTRY}", "country": COUNTRY, "payload": market_status_payload, "computed_at": now_iso},
        on_conflict="cache_key,country",
    ).execute()

    _, meta_swings, _ = _load_saudi_stocks_meta(saudi_sb)
    preloaded_df = _bars_dict_to_short_swings_df(bars_by_symbol, warmup_start="2025-06-01")
    swings_payload = compute_short_swings(
        phase=phase,
        exchange="TADAWUL",
        preloaded_df=preloaded_df,
        preloaded_meta=meta_swings,
    )
    swings_payload.setdefault("market", "TASI")
    swings_payload.setdefault("currency", "SAR")
    saudi_sb.table("market_cache").upsert(
        {"cache_key": "saudi_short_swings_v1", "country": COUNTRY, "payload": swings_payload, "computed_at": now_iso},
        on_conflict="cache_key,country",
    ).execute()

    return {
        "indicators_count": len(ind_rows),
        "latest_date": latest_date,
        "market_status": market_status_payload,
        "swings_payload": swings_payload,
    }


def _invalidate_saudi_caches(phase: str) -> Dict[str, Any]:
    from api.cache_invalidation import invalidate_cache_tags

    tags = (
        ["daily-market-data", "daily-symbols", "daily-short-swings", "daily-news-data", "daily-disclosures"]
        if phase in {"morning", "midday"}
        else SAUDI_CACHE_TAGS
    )
    return invalidate_cache_tags(tags)


def run_saudi_daily_job(
    phase: str = "close",
    trigger: str = "scheduled",
    dry_run: bool = False,
    main_sb=None,
    saudi_sb=None,
) -> Dict[str, Any]:
    """Run Saudi daily job (morning / midday / close) with durable daily_job_runs logging."""
    norm_phase = (phase or "close").strip().lower()
    if norm_phase not in {"morning", "midday", "close"}:
        raise ValueError(f"Unsupported Saudi phase: {phase}")

    if main_sb is None:
        try:
            from api.stock_ai import _init_supabase, supabase as _main_supabase
            if not _main_supabase:
                _init_supabase()
                from api.stock_ai import supabase as _main_supabase
            main_sb = _main_supabase
        except Exception:
            main_sb = None

    if saudi_sb is None:
        from api.saudi_telegram_dispatch import get_saudi_supabase
        saudi_sb = get_saudi_supabase()

    job_run_id = str(uuid.uuid4())
    job_type = saudi_job_type_for_phase(norm_phase)
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    steps_log: List[Dict[str, Any]] = []
    total_symbols = 0
    errors: List[str] = []

    _persist_job_run(main_sb, job_run_id, job_type, "running", started_at, steps_log, total_symbols, trigger)

    # 1. Price & Equal-Weight TASI Index Sync
    try:
        from api.saudi_price_sync import sync_saudi_daily_prices
        price_res = sync_saudi_daily_prices(phase=norm_phase, lookback_days=10 if norm_phase == "close" else 7, sb=saudi_sb)
        total_symbols = int(price_res.get("total") or 0)
        ok = bool(price_res.get("success"))
        _record_step(
            steps_log,
            "saudi_price_sync",
            "success" if ok else "failed",
            count=int(price_res.get("synced") or 0),
            details=f"synced={price_res.get('synced')}/{total_symbols} latest={price_res.get('latest_date')}",
        )
        if not ok:
            errors.append(str(price_res.get("error") or "saudi_price_sync returned 0 synced"))
    except Exception as exc:
        _record_step(steps_log, "saudi_price_sync", "failed", details=str(exc))
        errors.append(f"saudi_price_sync: {exc}")

    _persist_job_run(main_sb, job_run_id, job_type, "running", started_at, steps_log, total_symbols, trigger)

    swings_payload: Dict[str, Any] = {}
    market_status_payload: Dict[str, Any] = {}
    ind_rows: List[Dict[str, Any]] = []
    latest_date = dt.datetime.now(RIYADH_TZ).date().isoformat()

    if norm_phase in {"morning", "midday"}:
        # 2a. Intraday Indicators + Market Status + Short Swings
        try:
            snap = _run_intraday_snapshot_and_short_swings(saudi_sb, phase=norm_phase)
            latest_date = str(snap.get("latest_date") or latest_date)
            swings_payload = snap.get("swings_payload") or {}
            market_status_payload = snap.get("market_status") or {}
            _record_step(
                steps_log,
                "saudi_intraday_refresh",
                "success",
                count=int(snap.get("indicators_count") or 0),
                details=f"latest_date={latest_date}",
            )
            _record_step(
                steps_log,
                "saudi_short_swings",
                "success",
                count=len(swings_payload.get("active_trades") or []),
                details=f"new_entries={len(swings_payload.get('new_entries') or [])}, new_exits={len(swings_payload.get('new_exits') or [])}",
            )
        except Exception as exc:
            _record_step(steps_log, "saudi_intraday_refresh", "failed", details=str(exc))
            errors.append(f"saudi_intraday_refresh: {exc}")
    else:
        # 2b. Close: Full Pipeline Bootstrap (reuse trained KING_TASI & model_TADAWUL models)
        try:
            from scripts.saudi_pipeline_bootstrap import main as run_saudi_bootstrap
            rc = run_saudi_bootstrap(reuse_models=True)
            _record_step(
                steps_log,
                "saudi_pipeline_bootstrap",
                "success" if rc == 0 else "failed",
                count=total_symbols,
                details="reuse_models=True",
            )
            if rc != 0:
                errors.append(f"saudi_pipeline_bootstrap exited {rc}")
        except Exception as exc:
            _record_step(steps_log, "saudi_pipeline_bootstrap", "failed", details=str(exc))
            errors.append(f"saudi_pipeline_bootstrap: {exc}")

        # 3b. Close: Backtests + Short Swings + Fast Scanner Systems
        try:
            from scripts.saudi_backtest_and_systems import main as run_saudi_systems
            sys_res = run_saudi_systems([])
            swings_payload = sys_res.get("short_swings") or {}
            latest_date = str(swings_payload.get("as_of_date") or latest_date)[:10]
            _record_step(
                steps_log,
                "saudi_systems_backtests",
                "success",
                count=len(swings_payload.get("active_trades") or []),
                details=f"as_of={latest_date}",
            )
        except Exception as exc:
            _record_step(steps_log, "saudi_systems_backtests", "failed", details=str(exc))
            errors.append(f"saudi_systems_backtests: {exc}")

    _persist_job_run(main_sb, job_run_id, job_type, "running", started_at, steps_log, total_symbols, trigger)

    # 4. VIP-ONLY Telegram Dispatch (Strictly NO Free channel for Saudi)
    try:
        from api.saudi_telegram_dispatch import (
            dispatch_saudi_market_outlook_vip,
            dispatch_saudi_open_recommendations,
            dispatch_saudi_short_swings_vip,
        )

        tg_details: List[str] = []
        tg_errors: List[str] = []
        tg_count = 0
        if swings_payload:
            try:
                sw_tg = dispatch_saudi_short_swings_vip(swings_payload, phase=norm_phase, sb=saudi_sb, dry_run=dry_run)
                tg_count += int(sw_tg.get("entries_sent") or 0) + int(sw_tg.get("exits_sent") or 0)
                tg_details.append(f"swings_vip(entries={sw_tg.get('entries_sent')}, exits={sw_tg.get('exits_sent')})")
                if not sw_tg.get("ok"):
                    tg_errors.append(f"saudi_short_swings_vip: {sw_tg.get('errors')}")
            except Exception as sw_exc:
                tg_errors.append(f"saudi_short_swings_vip: {sw_exc}")

        if norm_phase == "close":
            rec_count = 0
            try:
                rec_tg = dispatch_saudi_open_recommendations(dedup_date=latest_date, sb=saudi_sb, dry_run=dry_run)
                rec_count = int(rec_tg.get("sent_count") or 0)
                if rec_tg.get("ok") and not rec_tg.get("skipped"):
                    tg_count += 1
                elif not rec_tg.get("ok"):
                    tg_errors.append(f"recs_vip: {rec_tg.get('error')}")
                tg_details.append(f"recs_vip(ok={rec_tg.get('ok')}, skipped={bool(rec_tg.get('skipped'))})")
            except Exception as rec_exc:
                tg_errors.append(f"recs_vip: {rec_exc}")

            # Read market_status & latest indicators from SAUDI_SUPABASE if not already in memory
            try:
                if not market_status_payload:
                    ms_res = (
                        saudi_sb.table("market_cache")
                        .select("payload")
                        .eq("cache_key", f"market_status_{SAUDI_COUNTRY}")
                        .eq("country", SAUDI_COUNTRY)
                        .maybe_single()
                        .execute()
                    )
                    market_status_payload = (getattr(ms_res, "data", None) or {}).get("payload") or {}
                if not ind_rows:
                    ind_res = (
                        saudi_sb.table("stock_technical_indicators")
                        .select("symbol,close,change_pct")
                        .eq("exchange", "TADAWUL")
                        .eq("date", latest_date)
                        .limit(300)
                        .execute()
                    )
                    ind_rows = list(ind_res.data or [])
                    if not ind_rows:
                        ind_res = (
                            saudi_sb.table("stock_technical_indicators")
                            .select("symbol,close,change_pct")
                            .eq("exchange", "TADAWUL")
                            .limit(300)
                            .execute()
                        )
                        ind_rows = list(ind_res.data or [])

                outlook_tg = dispatch_saudi_market_outlook_vip(
                    market_status=market_status_payload,
                    ind_rows=ind_rows,
                    recommendations_count=rec_count,
                    market_date=latest_date,
                    sb=saudi_sb,
                    dry_run=dry_run,
                )
                if outlook_tg.get("ok") and not outlook_tg.get("skipped"):
                    tg_count += 1
                elif not outlook_tg.get("ok"):
                    tg_errors.append(f"outlook_vip: {outlook_tg.get('error')}")
                tg_details.append(f"outlook_vip(ok={outlook_tg.get('ok')}, skipped={bool(outlook_tg.get('skipped'))})")
            except Exception as out_exc:
                tg_errors.append(f"outlook_vip: {out_exc}")

        if tg_errors:
            errors.extend(tg_errors)
        _record_step(
            steps_log,
            "saudi_telegram_vip",
            "failed" if tg_errors and tg_count == 0 else "success",
            count=tg_count,
            details="; ".join(tg_details + tg_errors) or "no_vip_messages_needed",
        )
    except Exception as exc:
        _record_step(steps_log, "saudi_telegram_vip", "failed", details=str(exc))
        errors.append(f"saudi_telegram_vip: {exc}")

    # 5. News & Disclosures
    try:
        from api.saudi_news_sync import run_saudi_news_sync
        news_res = run_saudi_news_sync(max_symbols=70, days_back=15)
        _record_step(
            steps_log,
            "saudi_news_sync",
            "success" if news_res.get("ok") else "failed",
            count=int(news_res.get("rows_saved") or 0),
            details=f"headlines={news_res.get('total_headlines')}",
        )
    except Exception as exc:
        _record_step(steps_log, "saudi_news_sync", "failed", details=str(exc))
        errors.append(f"saudi_news_sync: {exc}")

    try:
        from api.saudi_disclosures_sync import run_saudi_disclosures_sync
        disc_res = run_saudi_disclosures_sync(days_back=30)
        _record_step(
            steps_log,
            "saudi_disclosures_sync",
            "success" if disc_res.get("ok") else "failed",
            count=int(disc_res.get("saved") or 0),
            details=f"fetched={disc_res.get('fetched')}",
        )
    except Exception as exc:
        _record_step(steps_log, "saudi_disclosures_sync", "failed", details=str(exc))
        errors.append(f"saudi_disclosures_sync: {exc}")

    # 6. Cache Revalidation
    try:
        cache_res = _invalidate_saudi_caches(norm_phase)
        cache_ok = not cache_res.get("error") and (
            bool(cache_res.get("invalidated"))
            or bool(cache_res.get("skipped"))
            or cache_res.get("status") == 200
        )
        _record_step(
            steps_log,
            "cache_revalidation",
            "success" if cache_ok else "failed",
            count=len(cache_res.get("invalidated") or []),
            details=str(cache_res.get("error") or f"invalidated={len(cache_res.get('invalidated') or [])} tags"),
        )
        if not cache_ok:
            errors.append(f"cache_revalidation: {cache_res.get('error') or 'revalidation_failed'}")
    except Exception as exc:
        _record_step(steps_log, "cache_revalidation", "failed", details=str(exc))
        errors.append(f"cache_revalidation: {exc}")

    final_status = "completed" if any(s.get("status") == "success" for s in steps_log) else "failed"
    err_summary = "; ".join(errors) if errors else None
    _persist_job_run(main_sb, job_run_id, job_type, final_status, started_at, steps_log, total_symbols, trigger, error=err_summary)

    return {
        "ok": final_status == "completed",
        "job_run_id": job_run_id,
        "job_type": job_type,
        "phase": norm_phase,
        "status": final_status,
        "total_symbols": total_symbols,
        "latest_date": latest_date,
        "steps": steps_log,
        "error": err_summary,
    }
