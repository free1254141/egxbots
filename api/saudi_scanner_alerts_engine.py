"""
Native Python Intraday Scanner Alerts Engine for Saudi Market (TASI / Tadawul).
Mirrors EGX scanner_alerts_engine (System 3 — Fast Scanner) with:
- Tadawul hours (Sun-Thu 10:00-15:00 Asia/Riyadh) via is_saudi_session
- SAUDI_SCANNER_PROFILES (volume_surge, breakout, rsi_oversold) & breadth-adaptive gate
- Active/Closed signal lifecycle (T1, T2, Breakeven lock, Stop-Loss, Max Sessions)
- Durable storage in SAUDI_SUPABASE.market_cache (saudi_scanner_alerts_v1 + saudi_scanner_state)
- VIP-ONLY Telegram alerts in SAR (ر.س) to SAUDI_TELEGRAM_PRO_CHAT_ID (NO Free channel).
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo

from api.saudi_trading_calendar import is_saudi_session
from api.scanner_alerts_engine import (
    SAUDI_SCANNER_PROFILES,
    calculate_trade_plan,
    compute_scanner_signals_kpis,
    evaluate_scanner_candidates,
    step_scanner_lifecycle,
)
from api.web_origin import get_web_origin

RIYADH_TZ = ZoneInfo("Asia/Riyadh")
SAUDI_COUNTRY = "Saudi Arabia"
STATE_CACHE_KEY = "saudi_scanner_state"
PUBLIC_CACHE_KEY = "saudi_scanner_alerts_v1"


def get_riyadh_now() -> Dict[str, Any]:
    now = dt.datetime.now(RIYADH_TZ)
    total_minutes = now.hour * 60 + now.minute
    is_trading_day = is_saudi_session(now)
    # Tadawul regular session: 10:00 (600) .. 15:00 (900)
    is_trading_hours = is_trading_day and (600 <= total_minutes <= 900)
    return {
        "now": now,
        "date_str": now.date().isoformat(),
        "time_str": now.strftime("%H:%M"),
        "is_trading_day": is_trading_day,
        "is_trading_hours": is_trading_hours,
    }


def _read_cache(sb, cache_key: str) -> Dict[str, Any]:
    try:
        res = (
            sb.table("market_cache")
            .select("payload")
            .eq("cache_key", cache_key)
            .eq("country", SAUDI_COUNTRY)
            .maybe_single()
            .execute()
        )
        row = getattr(res, "data", None)
        if isinstance(row, dict) and isinstance(row.get("payload"), dict):
            return dict(row["payload"])
    except Exception:
        pass
    return {}


def _write_cache(sb, cache_key: str, payload: Dict[str, Any]) -> None:
    sb.table("market_cache").upsert(
        {
            "cache_key": cache_key,
            "country": SAUDI_COUNTRY,
            "payload": payload,
            "computed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        on_conflict="cache_key,country",
    ).execute()


def _send_saudi_vip_html(text: str, chat_id: Optional[str] = None, dry_run: bool = False) -> Dict[str, Any]:
    from api.saudi_telegram_dispatch import _send_telegram_message

    return _send_telegram_message(text=text, chat_id=chat_id, parse_mode="HTML", dry_run=dry_run)


def execute_saudi_scanner_alerts_native(
    force: bool = False,
    force_dispatch: bool = False,
    refresh_prices: bool = True,
    dry_run: bool = False,
    sb=None,
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run Saudi intraday scanner (System 3) and send VIP-only SAR alerts."""
    start_ts = time.time()
    riyadh = get_riyadh_now()
    if sb is None:
        from api.saudi_telegram_dispatch import get_saudi_supabase
        sb = get_saudi_supabase()

    state = _read_cache(sb, STATE_CACHE_KEY)
    if not state.get("is_active", True) and not force:
        return {"ok": False, "skipped": True, "reason": "saudi scanner disabled"}
    if state.get("market_hours_only", True) and not riyadh["is_trading_hours"] and not force:
        return {"ok": False, "skipped": True, "reason": "outside tadawul hours", "riyadh_time": riyadh["time_str"]}

    if refresh_prices and riyadh["is_trading_hours"]:
        try:
            from api.saudi_price_sync import sync_saudi_daily_prices
            sync_saudi_daily_prices(phase="intraday", lookback_days=3, sb=sb)
        except Exception as sync_exc:
            print(f"[SAUDI-SCANNER] Intraday price sync warning: {sync_exc}")

    # Load indicators & prices from SAUDI_SUPABASE (newest date first)
    ind_res = (
        sb.table("stock_technical_indicators")
        .select("symbol,date,close,change_pct,volume,vol_sma20,r_vol,rsi_14,bb_upper,ema_20,ema_50")
        .eq("exchange", "TADAWUL")
        .order("date", desc=True)
        .limit(350)
        .execute()
    )
    ind_rows = list(ind_res.data or [])
    if not ind_rows:
        return {"ok": False, "error": "No TADAWUL technical indicators found"}

    as_of_date = max(str(r.get("date") or "")[:10] for r in ind_rows if r.get("date")) or riyadh["date_str"]
    price_res = (
        sb.table("stock_prices")
        .select("symbol,open,high,low,close,volume")
        .eq("exchange", "TADAWUL")
        .eq("date", as_of_date)
        .limit(350)
        .execute()
    )
    price_map: Dict[str, Dict[str, float]] = {}
    for p in price_res.data or []:
        sym = str(p.get("symbol") or "").strip().split(".")[0]
        if sym:
            c = float(p.get("close") or 0.0)
            price_map[sym] = {
                "open": float(p.get("open") or c),
                "high": float(p.get("high") or c),
                "low": float(p.get("low") or c),
                "close": c,
                "volume": float(p.get("volume") or 0.0),
            }

    latest_by_symbol: Dict[str, Dict[str, Any]] = {}
    for r in ind_rows:
        sym = str(r.get("symbol") or "").strip().split(".")[0]
        if not sym:
            continue
        r_date = str(r.get("date") or "")[:10]
        if r_date and r_date != as_of_date:
            continue
        prev = latest_by_symbol.get(sym)
        if prev and r_date and prev.get("_date", "") > r_date:
            continue
        p_info = price_map.get(sym, {})
        c_val = float(p_info.get("close") or r.get("close") or 0.0)
        if c_val <= 0:
            continue
        vol_val = float(p_info.get("volume") or r.get("volume") or 0.0)
        vol_sma20 = float(r.get("vol_sma20") or 0.0)
        chg_pct = float(r.get("change_pct") or 0.0)
        r_vol = float(r.get("r_vol") or 1.0)
        if p_info:
            r_close = float(r.get("close") or 0.0)
            denom = 1.0 + (chg_pct / 100.0)
            if r_close > 0 and denom > 0:
                prev_close = r_close / denom
                if prev_close > 0:
                    chg_pct = round(((c_val / prev_close) - 1.0) * 100.0, 4)
            if vol_sma20 > 0 and vol_val > 0:
                r_vol = round(vol_val / vol_sma20, 4)
        latest_by_symbol[sym] = {
            "_date": r_date,
            "symbol": sym,
            "close": c_val,
            "change_pct": chg_pct,
            "volume": vol_val,
            "vol_sma20": vol_sma20,
            "r_vol": r_vol,
            "rsi_14": float(r.get("rsi_14") or 50.0),
            "ema_20": float(r.get("ema_20") or 0.0),
            "ema_50": float(r.get("ema_50") or 0.0),
            "bb_upper": float(r.get("bb_upper") or 0.0),
            "open": p_info.get("open", c_val),
            "high": p_info.get("high", c_val),
            "low": p_info.get("low", c_val),
        }

    sent_today = state.get("sent_today") or {}
    if sent_today.get("date") != riyadh["date_str"]:
        sent_today = {"date": riyadh["date_str"], "sent_keys": []}
    sent_keys: Set[str] = set(sent_today.get("sent_keys") or [])

    market_status = _read_cache(sb, f"market_status_{SAUDI_COUNTRY}")
    regime = str(market_status.get("regime") or "neutral").lower()
    regime_blocked = regime == "panic"
    has_today_indicators = as_of_date == riyadh["date_str"]
    allow_new_entries = bool((force or (has_today_indicators and riyadh["time_str"] < "14:50")) and (force or not regime_blocked))
    eval_res = evaluate_scanner_candidates(
        latest_by_symbol,
        sent_keys=sent_keys,
        force=force,
        limit_per_category=2,
        exchange="TADAWUL",
    )
    final_vol = eval_res["final_vol"] if allow_new_entries else []
    final_bo = eval_res["final_bo"] if allow_new_entries else []
    final_os = eval_res["final_os"] if allow_new_entries else []

    # Unified causal lifecycle shared with EGX & Saudi Systems Parity (no entry-day OHLC leakage)
    existing_public = _read_cache(sb, PUBLIC_CACHE_KEY)
    public_ts = str(existing_public.get("computed_at") or "")
    state_ts = str(state.get("synced_at") or (state.get("last_scan") or {}).get("timestamp") or "")
    prefer_public = bool(public_ts and (not state_ts or public_ts > state_ts))
    if prefer_public:
        current_active = list(existing_public.get("active_signals") or state.get("active_signals") or [])
        current_closed = list(existing_public.get("closed_signals") or state.get("closed_signals") or [])
    else:
        current_active = list(state.get("active_signals") or existing_public.get("active_signals") or [])
        current_closed = list(state.get("closed_signals") or existing_public.get("closed_signals") or [])
    prev_active_ids = {str(s.get("id") or f"{s.get('symbol')}_{s.get('entry_date')}_{s.get('scanner_type')}") for s in current_active}
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    (
        still_active,
        current_closed,
        hit_target_signals,
        stopped_out_signals,
    ) = step_scanner_lifecycle(
        current_active,
        current_closed,
        latest_by_symbol,
        final_vol=final_vol,
        final_bo=final_bo,
        final_os=final_os,
        as_of_date=as_of_date,
        action_date=riyadh["date_str"],
        action_time=riyadh["time_str"],
        now_iso=now_iso,
        causal_be_prev_only=False,
        intraday_live=True,
        allow_new_entries=allow_new_entries,
        exchange="TADAWUL",
    )

    newly_hit_targets = [s for s in hit_target_signals if s.get("exit_date") == riyadh["date_str"]]
    newly_hit_stops = [s for s in stopped_out_signals if s.get("exit_date") == riyadh["date_str"]]
    new_signals: List[Dict[str, Any]] = []
    for sig in still_active:
        sig_id = str(sig.get("id") or f"{sig.get('symbol')}_{sig.get('entry_date')}_{sig.get('scanner_type')}")
        if sig_id not in prev_active_ids and sig.get("entry_date") == riyadh["date_str"]:
            prof = SAUDI_SCANNER_PROFILES.get(sig.get("scanner_type") or "volume_surge", SAUDI_SCANNER_PROFILES["volume_surge"])
            plan = calculate_trade_plan(float(sig.get("entry_price") or 0.0), sig.get("scanner_type") or "volume_surge", exchange="TADAWUL")
            live_sym = latest_by_symbol.get(str(sig.get("symbol") or ""), {})
            new_signals.append(
                {
                    **sig,
                    "title_ar": prof["title_ar"],
                    "r_vol": round(float(live_sym.get("r_vol") or 1.0), 2),
                    "target_2": sig.get("target_2") or plan["target_2"],
                }
            )

    origin = get_web_origin()
    alerts_dispatched = 0

    # VIP-ONLY Telegram Dispatch (Strictly NO Free channel for Saudi)
    if newly_hit_targets:
        lines = ["🇸🇦 🎯 <b>تحقيق هدف — الرادار اللحظي تداول VIP</b>", f"📅 <code>{as_of_date}</code>", "━━━━━━━━━━━━━━━━━━━━"]
        for s in newly_hit_targets:
            lines.append(
                f"🟢 <b>{s['symbol']}</b> | الدخول: {s['entry_price']:.2f} ر.س → الخروج: {s['exit_price']:.2f} ر.س (<b>{s['return_pct']:+.2f}%</b>)"
            )
        lines.append(f"\n📲 <a href=\"{origin}/scanner/backtests?market=sa&tab=fast_scanner\">لوحة الرادار اللحظي تداول</a>")
        if _send_saudi_vip_html("\n".join(lines), chat_id=chat_id, dry_run=dry_run).get("ok"):
            alerts_dispatched += 1

    if newly_hit_stops:
        lines = ["🇸🇦 🛑 <b>تفعيل وقف الخسارة — الرادار اللحظي تداول VIP</b>", f"📅 <code>{as_of_date}</code>", "━━━━━━━━━━━━━━━━━━━━"]
        for s in newly_hit_stops:
            lines.append(
                f"🔴 <b>{s['symbol']}</b> | الدخول: {s['entry_price']:.2f} ر.س → الوقف: {s['exit_price']:.2f} ر.س (<b>{s['return_pct']:+.2f}%</b>)"
            )
        lines.append(f"\n📲 <a href=\"{origin}/scanner/backtests?market=sa&tab=fast_scanner\">مراجعة السجل اللحظي تداول</a>")
        if _send_saudi_vip_html("\n".join(lines), chat_id=chat_id, dry_run=dry_run).get("ok"):
            alerts_dispatched += 1

    if new_signals:
        lines = [
            "🇸🇦 ⚡ <b>رادار المضاربة اللحظية — تداول VIP</b>",
            f"📅 <code>{as_of_date} {riyadh['time_str']} الرياض</code>",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        for s in new_signals:
            lines.extend(
                [
                    f"🔹 <b>{s['symbol']}</b> ({s['title_ar']}) — سيولة نسبية <b>{s['r_vol']}x</b>",
                    f"   💵 الدخول: <b>{s['entry_price']:.2f} ر.س</b> | 🎯 هدف 1: {s['target_1']:.2f} | هدف 2: {s['target_2']:.2f} | 🛑 وقف: {s['stop_loss']:.2f} ر.س",
                ]
            )
        lines.extend(
            [
                "\n━━━━━━━━━━━━━━━━━━━━",
                f"📲 <a href=\"{origin}/scanner/backtests?market=sa&tab=fast_scanner\">فتح الرادار اللحظي للسوق السعودي</a>",
            ]
        )
        if _send_saudi_vip_html("\n".join(lines), chat_id=chat_id, dry_run=dry_run).get("ok"):
            alerts_dispatched += 1
            for s in new_signals:
                sym = s.get("symbol")
                if sym:
                    sent_keys.add(f"{sym}:volume_surge")
                    sent_keys.add(f"{sym}:breakout")
                    sent_keys.add(f"{sym}:rsi_oversold")

    final_closed = current_closed[:1000]
    kpis = compute_scanner_signals_kpis(final_closed, still_active)
    duration_ms = int((time.time() - start_ts) * 1000)
    stage_results = {
        "volume_surge": [{"symbol": s["symbol"], "close": s["close"], "change_pct": s["change_pct"], "r_vol": s["r_vol"]} for s in final_vol],
        "breakout": [{"symbol": s["symbol"], "close": s["close"], "change_pct": s["change_pct"], "r_vol": s["r_vol"]} for s in final_bo],
        "rsi_oversold": [{"symbol": s["symbol"], "close": s["close"], "change_pct": s["change_pct"], "rsi_14": s["rsi_14"]} for s in final_os],
    }
    last_scan = {
        "timestamp": now_iso,
        "duration_ms": duration_ms,
        "total_symbols_scanned": len(latest_by_symbol),
        "stage_results": stage_results,
        "alerts_dispatched": alerts_dispatched,
        "runner": "python-saudi-native",
    }
    history_entry = {
        "timestamp": now_iso,
        "duration_ms": duration_ms,
        "volume_count": len(final_vol),
        "breakout_count": len(final_bo),
        "oversold_count": len(final_os),
        "recipients_count": alerts_dispatched,
        "triggered_by": "Saudi 15m Scheduler",
        "stage_results": stage_results,
    }
    past_history = list(existing_public.get("history") or state.get("history") or [])
    new_history = [history_entry] + past_history[:59]

    _write_cache(
        sb,
        STATE_CACHE_KEY,
        {
            "is_active": state.get("is_active", True),
            "market_hours_only": state.get("market_hours_only", True),
            "sent_today": {"date": riyadh["date_str"], "sent_keys": list(sent_keys)[-200:]},
            "active_signals": still_active,
            "closed_signals": final_closed,
            "history": new_history,
            "last_scan": last_scan,
        },
    )
    _write_cache(
        sb,
        PUBLIC_CACHE_KEY,
        {
            "ok": True,
            "as_of": as_of_date,
            "is_pro": True,
            "market": "TASI",
            "currency": "SAR",
            "active_signals": still_active,
            "closed_signals": final_closed[:200],
            "history": new_history,
            "signals_kpis": kpis,
            "last_scan": last_scan,
            "computed_at": now_iso,
        },
    )

    return {
        "ok": True,
        "vip_only": True,
        "as_of": as_of_date,
        "alerts_dispatched": alerts_dispatched,
        "new_signals": len(new_signals),
        "targets_hit": len(newly_hit_targets),
        "stops_hit": len(newly_hit_stops),
        "active_count": len(still_active),
        "duration_ms": duration_ms,
    }
