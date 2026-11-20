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
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
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
    from scripts.saudi_backtest_and_systems import (
        ML_WARMUP_START,
        _bars_dict_to_short_swings_df,
        _load_saudi_stocks_meta,
    )
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
            "volume": float(last_bar.get("Volume") or 0.0),
            "date": last_bar.name.strftime("%Y-%m-%d") if hasattr(last_bar.name, "strftime") else str(last_bar.name)[:10],
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
    preloaded_df = _bars_dict_to_short_swings_df(bars_by_symbol, warmup_start=ML_WARMUP_START)
    now_riyadh = dt.datetime.now(RIYADH_TZ)
    today_riyadh = now_riyadh.date().isoformat()
    observed_at = now_riyadh.isoformat()
    observed_quotes = {
        sym: {
            "price": b["close"],
            "volume": float(b.get("volume") or 0.0),
            "observed_at": observed_at,
            "date": b.get("date") or latest_date,
            "verified": (b.get("date") == today_riyadh and float(b.get("volume") or 0.0) > 0),
        }
        for sym, b in bars_map.items()
        if b.get("close")
    }
    swings_payload = compute_short_swings(
        phase=phase,
        exchange="TADAWUL",
        preloaded_df=preloaded_df,
        preloaded_meta=meta_swings,
        observed_quotes=observed_quotes,
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
    resume_job_id: Optional[str] = None,
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
    completed_steps: set[str] = set()

    if resume_job_id and main_sb is not None:
        saved = (
            main_sb.table("daily_job_runs")
            .select("id,job_type,status,started_at,steps,total_symbols")
            .eq("id", resume_job_id)
            .limit(1)
            .execute()
        ).data or []
        if not saved:
            raise ValueError("Saudi continuation job not found")
        original = saved[0]
        session_date = dt.datetime.fromisoformat(str(original["started_at"]).replace("Z", "+00:00")).astimezone(RIYADH_TZ).date()
        if (
            original.get("status") == "running"
            or session_date != dt.datetime.now(RIYADH_TZ).date()
            or original.get("job_type") != job_type
        ):
            raise ValueError("Only a stopped current-session matching Saudi phase may continue")
        job_run_id = original["id"]
        started_at = original["started_at"]
        raw_steps = original.get("steps")
        steps_log = json.loads(raw_steps) if isinstance(raw_steps, str) else list(raw_steps or [])
        total_symbols = int(original.get("total_symbols") or 0)
        completed_steps = {
            str(s.get("step"))
            for s in steps_log
            if isinstance(s, dict) and s.get("status") == "success" and s.get("step")
        }

    def _step_done(name: str) -> bool:
        return name in completed_steps

    _persist_job_run(main_sb, job_run_id, job_type, "running", started_at, steps_log, total_symbols, trigger)

    # 1. Price & Equal-Weight TASI Index Sync
    if not _step_done("saudi_price_sync"):
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
    state_lock = threading.RLock()

    def _safe_record_step(step_name: str, status: str, count: int = 0, details: str = "") -> None:
        with state_lock:
            _record_step(steps_log, step_name, status, count=count, details=details)

    def _safe_add_error(msg: str) -> None:
        with state_lock:
            errors.append(msg)

    def _run_saudi_news_and_disclosures() -> None:
        if not _step_done("saudi_news_sync"):
            try:
                from api.saudi_news_sync import run_saudi_news_sync
                news_res = run_saudi_news_sync(max_symbols=70, days_back=15)
                _safe_record_step(
                    "saudi_news_sync",
                    "success" if news_res.get("ok") else "failed",
                    count=int(news_res.get("rows_saved") or 0),
                    details=f"headlines={news_res.get('total_headlines')}",
                )
            except Exception as exc:
                _safe_record_step("saudi_news_sync", "failed", details=str(exc))
                _safe_add_error(f"saudi_news_sync: {exc}")

        if not _step_done("saudi_disclosures_sync"):
            try:
                from api.saudi_disclosures_sync import run_saudi_disclosures_sync
                disc_res = run_saudi_disclosures_sync(days_back=30)
                _safe_record_step(
                    "saudi_disclosures_sync",
                    "success" if disc_res.get("ok") else "failed",
                    count=int(disc_res.get("saved") or 0),
                    details=f"fetched={disc_res.get('fetched')}",
                )
            except Exception as exc:
                _safe_record_step("saudi_disclosures_sync", "failed", details=str(exc))
                _safe_add_error(f"saudi_disclosures_sync: {exc}")

    def _run_gcc_daily_bundle() -> None:
        if not _step_done("gcc_metals_sync"):
            try:
                from api.gcc_metals_sync import run_gcc_metals_sync
                gcc_res = run_gcc_metals_sync(daily_only=True)
                gcc_summary = gcc_res.get("summary") or {}
                synced_total = sum(int((v or {}).get("symbols_synced") or 0) for v in gcc_summary.values())
                _safe_record_step(
                    "gcc_metals_sync",
                    "success" if gcc_res.get("ok") else "failed",
                    count=synced_total,
                    details=",".join(f"{k}:{v.get('symbols_synced', 0)}" for k, v in gcc_summary.items()),
                )
            except Exception as exc:
                _safe_record_step("gcc_metals_sync", "failed", details=str(exc))
                _safe_add_error(f"gcc_metals_sync: {exc}")

        if not _step_done("gcc_news_sync"):
            try:
                from api.gcc_news_sync import sync_gcc_market_news
                gcc_news_res = sync_gcc_market_news(market="all", max_symbols=50, days_back=15)
                _safe_record_step(
                    "gcc_news_sync",
                    "success" if gcc_news_res.get("ok") else "failed",
                    count=int(gcc_news_res.get("synced_rows") or 0),
                    details=f"matched={gcc_news_res.get('matched_symbols')}",
                )
            except Exception as exc:
                _safe_record_step("gcc_news_sync", "failed", details=str(exc))
                _safe_add_error(f"gcc_news_sync: {exc}")

        if not _step_done("gcc_disclosures_sync"):
            try:
                from api.gcc_disclosures_sync import run_gcc_disclosures_sync
                gcc_disc_res = run_gcc_disclosures_sync(market="all", days_back=30)
                gcc_disc_results = gcc_disc_res.get("results") or {}
                inserted_total = sum(int((v or {}).get("inserted") or 0) for v in gcc_disc_results.values())
                _safe_record_step(
                    "gcc_disclosures_sync",
                    "success" if gcc_disc_res.get("ok") else "failed",
                    count=inserted_total,
                    details=",".join(f"{k}:{(v or {}).get('inserted', 0)}" for k, v in gcc_disc_results.items()),
                )
            except Exception as exc:
                _safe_record_step("gcc_disclosures_sync", "failed", details=str(exc))
                _safe_add_error(f"gcc_disclosures_sync: {exc}")

    with ThreadPoolExecutor(max_workers=2) as io_pool:
        saudi_news_future = io_pool.submit(_run_saudi_news_and_disclosures)
        gcc_future = io_pool.submit(_run_gcc_daily_bundle)

        if norm_phase in {"morning", "midday"}:
            # 2a. Intraday Indicators + Market Status + Short Swings
            if not (_step_done("saudi_intraday_refresh") and _step_done("saudi_short_swings")):
                try:
                    snap = _run_intraday_snapshot_and_short_swings(saudi_sb, phase=norm_phase)
                    latest_date = str(snap.get("latest_date") or latest_date)
                    swings_payload = snap.get("swings_payload") or {}
                    market_status_payload = snap.get("market_status") or {}
                    _safe_record_step(
                        "saudi_intraday_refresh",
                        "success",
                        count=int(snap.get("indicators_count") or 0),
                        details=f"latest_date={latest_date}",
                    )
                    _safe_record_step(
                        "saudi_short_swings",
                        "success",
                        count=len(swings_payload.get("active_trades") or []),
                        details=f"new_entries={len(swings_payload.get('new_entries') or [])}, new_exits={len(swings_payload.get('new_exits') or [])}",
                    )
                except Exception as exc:
                    _safe_record_step("saudi_intraday_refresh", "failed", details=str(exc))
                    _safe_add_error(f"saudi_intraday_refresh: {exc}")
        else:
            # 2b. Close: Full Pipeline Bootstrap (reuse trained KING_TASI & model_TADAWUL models)
            if not _step_done("saudi_pipeline_bootstrap"):
                try:
                    from scripts.saudi_pipeline_bootstrap import main as run_saudi_bootstrap
                    rc = run_saudi_bootstrap(reuse_models=True)
                    _safe_record_step(
                        "saudi_pipeline_bootstrap",
                        "success" if rc == 0 else "failed",
                        count=total_symbols,
                        details="reuse_models=True",
                    )
                    if rc != 0:
                        _safe_add_error(f"saudi_pipeline_bootstrap exited {rc}")
                except Exception as exc:
                    _safe_record_step("saudi_pipeline_bootstrap", "failed", details=str(exc))
                    _safe_add_error(f"saudi_pipeline_bootstrap: {exc}")

                with state_lock:
                    _persist_job_run(main_sb, job_run_id, job_type, "running", started_at, steps_log, total_symbols, trigger)

            # 3b. Close: Backtests + Short Swings + Fast Scanner Systems
            if not _step_done("saudi_systems_backtests"):
                try:
                    from scripts.saudi_backtest_and_systems import main as run_saudi_systems
                    sys_res = run_saudi_systems([])
                    swings_payload = sys_res.get("short_swings") or {}
                    latest_date = str(swings_payload.get("as_of_date") or latest_date)[:10]
                    _safe_record_step(
                        "saudi_systems_backtests",
                        "success",
                        count=len(swings_payload.get("active_trades") or []),
                        details=f"as_of={latest_date}",
                    )
                except Exception as exc:
                    _safe_record_step("saudi_systems_backtests", "failed", details=str(exc))
                    _safe_add_error(f"saudi_systems_backtests: {exc}")
            elif not _step_done("saudi_telegram_vip") and saudi_sb is not None:
                try:
                    sw_res = (
                        saudi_sb.table("market_cache")
                        .select("payload")
                        .eq("cache_key", "saudi_short_swings_v1")
                        .eq("country", SAUDI_COUNTRY)
                        .limit(1)
                        .execute()
                    )
                    sw_rows = getattr(sw_res, "data", None) or []
                    swings_payload = (sw_rows[0] if sw_rows else {}).get("payload") or {}
                    latest_date = str(swings_payload.get("as_of_date") or swings_payload.get("as_of") or latest_date)[:10]
                except Exception:
                    pass

        # Ensure Saudi disclosures & news finish before VIP daily report reads egx_disclosures
        saudi_news_future.result()

        with state_lock:
            _persist_job_run(main_sb, job_run_id, job_type, "running", started_at, steps_log, total_symbols, trigger)

        # 4. VIP-ONLY Telegram Dispatch (Strictly NO Free channel for Saudi)
        if not _step_done("saudi_telegram_vip"):
            try:
                from api.saudi_telegram_dispatch import (
                    dispatch_saudi_daily_vip_report,
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
                        tg_count += (
                            int(sw_tg.get("entries_sent") or 0)
                            + int(sw_tg.get("exits_sent") or 0)
                            + int(sw_tg.get("updates_sent") or 0)
                        )
                        tg_details.append(
                            f"swings_vip(entries={sw_tg.get('entries_sent')}, exits={sw_tg.get('exits_sent')}, updates={sw_tg.get('updates_sent', 0)})"
                        )
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
                                .limit(1)
                                .execute()
                            )
                            ms_rows = getattr(ms_res, "data", None) or []
                            market_status_payload = (ms_rows[0] if ms_rows else {}).get("payload") or {}
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
                    try:
                        vip_report_tg = dispatch_saudi_daily_vip_report(
                            market_date=latest_date,
                            ind_rows=ind_rows,
                            sb=saudi_sb,
                            dry_run=dry_run,
                        )
                        if vip_report_tg.get("ok") and not vip_report_tg.get("skipped"):
                            tg_count += 1
                        elif not vip_report_tg.get("ok"):
                            tg_errors.append(f"report_vip: {vip_report_tg.get('error')}")
                        tg_details.append(f"report_vip(ok={vip_report_tg.get('ok')}, skipped={bool(vip_report_tg.get('skipped'))})")
                    except Exception as rep_exc:
                        tg_errors.append(f"report_vip: {rep_exc}")

                if tg_errors:
                    for tg_err in tg_errors:
                        _safe_add_error(tg_err)
                _safe_record_step(
                    "saudi_telegram_vip",
                    "failed" if tg_errors and tg_count == 0 else "success",
                    count=tg_count,
                    details="; ".join(tg_details + tg_errors) or "no_vip_messages_needed",
                )
            except Exception as exc:
                _safe_record_step("saudi_telegram_vip", "failed", details=str(exc))
                _safe_add_error(f"saudi_telegram_vip: {exc}")

        # Join GCC/Metals parallel lane before cache revalidation
        gcc_future.result()

    # 6. Cache Revalidation
    if not _step_done("cache_revalidation"):
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


def run_gcc_metals_daily_job(
    mode: str = "uae_close",
    trigger: str = "scheduled",
    main_sb=None,
) -> Dict[str, Any]:
    """Run independent daily automation for UAE (DFM/ADX) Fridays and Global Metals (COMMODITIES) Mon-Fri."""
    norm_mode = (mode or "uae_close").strip().lower()
    if norm_mode not in {"uae_close", "metals_close"}:
        raise ValueError("Invalid GCC/Metals mode; expected 'uae_close' or 'metals_close'")

    if main_sb is None:
        try:
            from api.stock_ai import _init_supabase, supabase as _main_supabase
            if not _main_supabase:
                _init_supabase()
                from api.stock_ai import supabase as _main_supabase
            main_sb = _main_supabase
        except Exception:
            main_sb = None

    job_run_id = str(uuid.uuid4())
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    steps_log: List[Dict[str, Any]] = []
    errors: List[str] = []
    total_symbols = 0

    _persist_job_run(main_sb, job_run_id, norm_mode, "running", started_at, steps_log, total_symbols, trigger)

    tags_to_invalidate: List[str] = []
    target_exchanges = ["COMMODITIES"] if norm_mode == "metals_close" else ["DFM", "ADX", "COMMODITIES"]
    try:
        from api.gcc_metals_sync import run_gcc_metals_sync
        gcc_res = run_gcc_metals_sync(exchanges=target_exchanges, daily_only=True)
        gcc_summary = gcc_res.get("summary") or {}
        total_symbols = sum(int((v or {}).get("symbols_synced") or 0) for v in gcc_summary.values())
        ok_sync = bool(gcc_res.get("ok"))
        _record_step(
            steps_log,
            "gcc_metals_sync",
            "success" if ok_sync else "failed",
            count=total_symbols,
            details=",".join(f"{k}:{(v or {}).get('symbols_synced', 0)}" for k, v in gcc_summary.items()) or str(gcc_res.get("error") or ""),
        )
        if ok_sync:
            tags_to_invalidate.extend(["daily-market-data", "daily-symbols"])
        else:
            errors.append(f"gcc_metals_sync: {gcc_res.get('error') or 'sync_failed'}")
    except Exception as exc:
        _record_step(steps_log, "gcc_metals_sync", "failed", details=str(exc))
        errors.append(f"gcc_metals_sync: {exc}")

    if norm_mode == "uae_close":
        try:
            from api.gcc_news_sync import sync_gcc_market_news
            news_res = sync_gcc_market_news(market="uae", max_symbols=50, days_back=15)
            ok_news = bool(news_res.get("ok"))
            _record_step(
                steps_log,
                "gcc_news_sync",
                "success" if ok_news else "failed",
                count=int(news_res.get("synced_rows") or 0),
                details=f"matched={news_res.get('matched_symbols')}",
            )
            if ok_news:
                tags_to_invalidate.append("daily-news-data")
            else:
                errors.append(f"gcc_news_sync: {news_res.get('error') or 'news_failed'}")
        except Exception as exc:
            _record_step(steps_log, "gcc_news_sync", "failed", details=str(exc))
            errors.append(f"gcc_news_sync: {exc}")

        try:
            from api.gcc_disclosures_sync import run_gcc_disclosures_sync
            disc_res = run_gcc_disclosures_sync(market="uae", days_back=30)
            disc_results = disc_res.get("results") or {}
            inserted = sum(int((v or {}).get("inserted") or 0) for v in disc_results.values())
            ok_disc = bool(disc_res.get("ok"))
            _record_step(
                steps_log,
                "gcc_disclosures_sync",
                "success" if ok_disc else "failed",
                count=inserted,
                details=",".join(f"{k}:{(v or {}).get('inserted', 0)}" for k, v in disc_results.items()),
            )
            if ok_disc:
                tags_to_invalidate.append("daily-disclosures")
            else:
                errors.append(f"gcc_disclosures_sync: {disc_res.get('error') or 'disclosures_failed'}")
        except Exception as exc:
            _record_step(steps_log, "gcc_disclosures_sync", "failed", details=str(exc))
            errors.append(f"gcc_disclosures_sync: {exc}")

    if tags_to_invalidate:
        try:
            from api.cache_invalidation import invalidate_cache_tags
            unique_tags = list(dict.fromkeys(tags_to_invalidate))
            cache_res = invalidate_cache_tags(unique_tags) or {}
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

    final_status = (
        "completed"
        if any(s.get("step") != "cache_revalidation" and s.get("status") == "success" for s in steps_log)
        else "failed"
    )
    err_summary = "; ".join(errors) if errors else None
    _persist_job_run(main_sb, job_run_id, norm_mode, final_status, started_at, steps_log, total_symbols, trigger, error=err_summary)

    return {
        "ok": final_status == "completed",
        "job_run_id": job_run_id,
        "job_type": norm_mode,
        "mode": norm_mode,
        "status": final_status,
        "total_symbols": total_symbols,
        "steps": steps_log,
        "error": err_summary,
    }
