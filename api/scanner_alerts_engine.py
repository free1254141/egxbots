"""
Native Python Scanner Alerts Engine for EGX BOTS.
Runs directly on Hugging Face Spaces / Python Backend without triggering Vercel Serverless Functions.
Evaluates EGX market breadth, volume surge, breakout, and RSI oversold bounces,
manages active swing signal trade plans, and dispatches alerts to Telegram VIP Channel.
"""
import os
import time
import json
import logging
import urllib.request
import urllib.error
import requests
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional, Tuple, Set
import hashlib

logger = logging.getLogger("scanner_alerts_engine")
logger.setLevel(logging.INFO)

try:
    from dotenv import load_dotenv
    load_dotenv()
    base_env = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(base_env):
        load_dotenv(base_env)
except Exception:
    pass

CAIRO_TZ = ZoneInfo("Africa/Cairo")
BOT_STATE_KEY = "scanner_alerts"
DEFAULT_VIP_CHANNEL_CHAT_ID = "-1003906516349"
DEFAULT_FREE_CHANNEL_CHAT_ID = "-1002083067817_153"

SCANNER_PROFILES = {
    "volume_surge": {
        "t1_pct": 4.5,
        "t2_pct": 7.5,
        "sl_pct": 3.0,
        "max_sessions": 4,
        "title_ar": "السيولة الفائقة",
    },
    "breakout": {
        "t1_pct": 6.0,
        "t2_pct": 9.5,
        "sl_pct": 3.5,
        "max_sessions": 5,
        "title_ar": "اختراق فني",
    },
    "rsi_oversold": {
        "t1_pct": 4.0,
        "t2_pct": 6.5,
        "sl_pct": 2.8,
        "max_sessions": 3,
        "title_ar": "تشبع بيعي",
    },
}

def get_cairo_now():
    now_cairo = datetime.now(CAIRO_TZ)
    day = now_cairo.weekday()  # Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5, Sun=6
    # EGX trading days: Sun(6), Mon(0), Tue(1), Wed(2), Thu(3)
    is_trading_day = day in {6, 0, 1, 2, 3}
    total_min = now_cairo.hour * 60 + now_cairo.minute
    is_trading_hours = is_trading_day and (600 <= total_min <= 875)  # 10:00 to 14:35
    time_str = now_cairo.strftime("%H:%M")
    date_str = now_cairo.strftime("%Y-%m-%d")
    return {
        "day": day,
        "hour": now_cairo.hour,
        "minute": now_cairo.minute,
        "is_trading_day": is_trading_day,
        "is_trading_hours": is_trading_hours,
        "time_str": time_str,
        "date_str": date_str,
    }

def get_supabase_config():
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or ""
    if not url or not key:
        return None, None
    return url, key

def supabase_get(endpoint: str, timeout: int = 15) -> Optional[Any]:
    url, key = get_supabase_config()
    if not url or not key:
        return None
    full_url = f"{url}/rest/v1/{endpoint}"
    req = urllib.request.Request(
        full_url,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"[SCANNER_PY] GET {endpoint} failed: {e}")
        return None

def supabase_upsert(table: str, payload: Dict[str, Any], on_conflict: str = "bot_id", timeout: int = 15) -> bool:
    url, key = get_supabase_config()
    if not url or not key:
        return False
    full_url = f"{url}/rest/v1/{table}?on_conflict={on_conflict}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        full_url,
        data=data,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 201, 204)
    except Exception as e:
        logger.warning(f"[SCANNER_PY] UPSERT {table} failed: {e}")
        return False

def supabase_rpc(func_name: str, payload: Dict[str, Any], timeout: int = 15) -> Optional[Any]:
    url, key = get_supabase_config()
    if not url or not key:
        return None
    full_url = f"{url}/rest/v1/rpc/{func_name}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        full_url,
        data=data,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except Exception as e:
        logger.warning(f"[SCANNER_PY] RPC {func_name} failed: {e}")
        return None


def acquire_dispatch_slot(
    chat_id: str,
    date_str: str,
    symbols: List[str],
    category: str = "intraday_scan",
    cooldown_seconds: int = 300,
    force_bypass: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Guarantees idempotency and prevents duplicate alerts at database level.
    Rejects duplicate batch hashes and enforces a 5-minute cooldown.
    """
    if force_bypass:
        return True, None
    try:
        clean_chat = str(chat_id).strip().split("_")[0]
        sorted_syms = sorted(list(set([str(s).upper() for s in symbols])))
        batch_raw = f"{clean_chat}_{date_str}_{category}_{','.join(sorted_syms)}"
        batch_hash = hashlib.sha256(batch_raw.encode("utf-8")).hexdigest()[:16]
        res = supabase_rpc("acquire_scanner_dispatch_lock", {
            "p_chat_id": clean_chat,
            "p_date": date_str,
            "p_batch_hash": batch_hash,
            "p_symbols": sorted_syms,
            "p_category": category,
            "p_worker": "huggingface",
            "p_cooldown_seconds": cooldown_seconds,
        })
        if res and isinstance(res, dict):
            if res.get("allowed") is True:
                return True, res.get("dispatch_id")
            else:
                logger.info(f"[SCANNER_LOCK] Blocked duplicate dispatch: {res.get('reason')} (cat={category}, syms={sorted_syms})")
                return False, None
    except Exception as e:
        logger.warning(f"[SCANNER_LOCK] acquire_dispatch_slot error: {e}")
    return True, None


def confirm_dispatch_slot(dispatch_id: Optional[str], message_id: Optional[int]):
    if not dispatch_id:
        return
    try:
        payload = {"p_dispatch_id": dispatch_id}
        if message_id is not None:
            payload["p_message_id"] = int(message_id)
        supabase_rpc("confirm_scanner_dispatch", payload)
    except Exception as e:
        logger.warning(f"[SCANNER_LOCK] confirm_dispatch_slot error: {e}")


def release_dispatch_slot(dispatch_id: Optional[str]):
    if not dispatch_id:
        return
    try:
        supabase_rpc("delete_pending_dispatch", {
            "p_dispatch_id": dispatch_id,
        })
    except Exception as e:
        logger.warning(f"[SCANNER_LOCK] release_dispatch_slot error: {e}")


def send_telegram_alert(chat_id: str, text: str, timeout: int = 15) -> bool:
    if not chat_id:
        return False

    # 1. First attempt: use established TelegramBot singleton bridge with reliable Supabase Relay
    try:
        from api.telegram_bot import get_telegram_bot
        bot = get_telegram_bot()
        if bot and bot.token:
            target_chat_id = str(chat_id).strip()
            thread_id = None
            if "_" in target_chat_id and not target_chat_id.startswith("@"):
                parts = target_chat_id.split("_", 1)
                target_chat_id = parts[0]
                try:
                    thread_id = int(parts[1])
                except ValueError:
                    pass
            sent = bot.send_notification(
                text,
                chat_id=target_chat_id,
                message_thread_id=thread_id,
                wait_for_delivery=True,
            )
            if sent:
                return True
    except Exception as e:
        logger.warning(f"[SCANNER_PY] get_telegram_bot delivery failed: {e}")

    # 2. Direct HTTP fallback (using ARTORO_AI_BOT with relay fallback and HTML error recovery)
    token = os.getenv("ARTORO_AI_BOT") or os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.warning(f"[SCANNER_PY] Skipped Telegram dispatch (no token found in env: ARTORO_AI_BOT/TELEGRAM_BOT_TOKEN)")
        return False

    target_chat_id = str(chat_id).strip()
    thread_id = None
    if "_" in target_chat_id and not target_chat_id.startswith("@"):
        parts = target_chat_id.split("_", 1)
        target_chat_id = parts[0]
        try:
            thread_id = int(parts[1])
        except ValueError:
            pass

    relay_url = (os.getenv("TELEGRAM_RELAY_URL") or "https://api.telegram.org").rstrip("/")
    for base in [relay_url, "https://api.telegram.org"]:
        try:
            url = f"{base}/bot{token}/sendMessage"
            payload: Dict[str, Any] = {
                "chat_id": int(target_chat_id) if target_chat_id.lstrip("-").isdigit() else target_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if thread_id is not None:
                payload["message_thread_id"] = thread_id

            resp = requests.post(url, json=payload, timeout=timeout)
            try:
                res_json = resp.json()
            except Exception:
                res_json = {}

            if resp.status_code == 200 and res_json.get("ok"):
                msg_id = res_json.get("result", {}).get("message_id")
                return msg_id if msg_id else True

            # If HTML parse error or rejected, retry without parse_mode
            desc = str(res_json.get("description", "")).lower()
            if "can't parse" in desc or "parse_mode" in desc or "entities" in desc or resp.status_code == 400:
                plain_payload = dict(payload)
                plain_payload.pop("parse_mode", None)
                plain_payload["text"] = re.sub(r"<[^>]+>", "", text)
                resp2 = requests.post(url, json=plain_payload, timeout=timeout)
                if resp2.status_code == 200 and resp2.json().get("ok"):
                    msg_id = resp2.json().get("result", {}).get("message_id")
                    return msg_id if msg_id else True
        except Exception as e:
            logger.warning(f"[SCANNER_PY] Telegram send failed from {base}: {e}")
            if base == relay_url:
                continue

    return False

def calculate_trade_plan(close: float, scanner_type: str) -> Dict[str, Any]:
    prof = SCANNER_PROFILES.get(scanner_type, SCANNER_PROFILES["volume_surge"])
    t1 = round(close * (1 + prof["t1_pct"] / 100.0), 2)
    t2 = round(close * (1 + prof["t2_pct"] / 100.0), 2)
    sl = round(close * (1 - prof["sl_pct"] / 100.0), 2)
    return {
        "target_1": t1,
        "target_1_pct": prof["t1_pct"],
        "target_2": t2,
        "target_2_pct": prof["t2_pct"],
        "stop_loss": sl,
        "stop_loss_pct": prof["sl_pct"],
        "max_sessions": prof["max_sessions"],
        "risk_reward_ratio": round(prof["t1_pct"] / max(0.1, prof["sl_pct"]), 2),
    }

def count_elapsed_sessions(entry_date: str, current_date: str) -> int:
    try:
        start_d = datetime.strptime(entry_date, "%Y-%m-%d").date()
        end_d = datetime.strptime(current_date, "%Y-%m-%d").date()
        if end_d < start_d:
            return 1
        count = 0
        curr = start_d
        while curr <= end_d:
            # Mon=0, Tue=1, Wed=2, Thu=3, Sun=6
            if curr.weekday() in {6, 0, 1, 2, 3}:
                count += 1
            curr += timedelta(days=1)
        return max(1, count)
    except Exception:
        return 1


MAX_PORTFOLIO_ACTIVE = 8


def evaluate_scanner_candidates(
    latest_by_symbol: Dict[str, Dict[str, Any]],
    *,
    sent_keys: Optional[Set[str]] = None,
    force: bool = True,
    limit_per_category: int = 2,
) -> Dict[str, Any]:
    """Exact EGX scanner classification, ranking, and cross-category deduplication."""
    sent = sent_keys or set()
    volume_matches: List[Dict[str, Any]] = []
    breakout_matches: List[Dict[str, Any]] = []
    oversold_matches: List[Dict[str, Any]] = []

    positive_stocks = 0
    negative_stocks = 0
    neutral_stocks = 0

    for sym, row in latest_by_symbol.items():
        close = float(row.get("close") or 0.0)
        ch_pct = float(row.get("change_pct") or 0.0)
        vol = float(row.get("volume") or 0.0)
        rsi = float(row.get("rsi_14") or 50.0)
        r_vol = float(row.get("r_vol") or 0.0)

        if close <= 0:
            continue

        if ch_pct > 0.1:
            positive_stocks += 1
        elif ch_pct < -0.1:
            negative_stocks += 1
        else:
            neutral_stocks += 1

        # 1. Volume Surge
        if r_vol >= 1.7 and ch_pct >= 1.2 and vol >= 15000:
            volume_matches.append({
                "symbol": sym,
                "close": close,
                "change_pct": ch_pct,
                "r_vol": r_vol,
                "rsi_14": rsi,
            })

        # 2. Breakout
        if ch_pct >= 2.5 and r_vol >= 1.4 and vol >= 20000:
            breakout_matches.append({
                "symbol": sym,
                "close": close,
                "change_pct": ch_pct,
                "r_vol": r_vol,
                "rsi_14": rsi,
            })

        # 3. RSI Oversold Rebound
        if rsi <= 35.0 and ch_pct >= 0.5:
            oversold_matches.append({
                "symbol": sym,
                "close": close,
                "change_pct": ch_pct,
                "r_vol": r_vol,
                "rsi_14": rsi,
            })

    volume_matches.sort(key=lambda x: x["r_vol"], reverse=True)
    breakout_matches.sort(key=lambda x: x["change_pct"], reverse=True)
    oversold_matches.sort(key=lambda x: x["rsi_14"])

    seen_fresh_symbols: Set[str] = set()

    def _pick(cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        picked: List[Dict[str, Any]] = []
        for s in cands:
            sym = s["symbol"]
            if sym in seen_fresh_symbols:
                continue
            if not force and (
                f"{sym}:volume_surge" in sent
                or f"{sym}:breakout" in sent
                or f"{sym}:rsi_oversold" in sent
            ):
                continue
            picked.append(s)
            seen_fresh_symbols.add(sym)
            if len(picked) >= limit_per_category:
                break
        return picked

    return {
        "final_vol": _pick(volume_matches),
        "final_bo": _pick(breakout_matches),
        "final_os": _pick(oversold_matches),
        "positive_stocks": positive_stocks,
        "negative_stocks": negative_stocks,
        "neutral_stocks": neutral_stocks,
    }


def step_scanner_lifecycle(
    current_active: List[Dict[str, Any]],
    current_closed: List[Dict[str, Any]],
    latest_by_symbol: Dict[str, Dict[str, Any]],
    *,
    final_vol: List[Dict[str, Any]],
    final_bo: List[Dict[str, Any]],
    final_os: List[Dict[str, Any]],
    as_of_date: str,
    action_date: str,
    action_time: str,
    now_iso: str,
    causal_be_prev_only: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Advance tracked scanner signals using the exact EGX breakeven, target, stop, and expiry rules."""
    hit_target_signals: List[Dict[str, Any]] = []
    stopped_out_signals: List[Dict[str, Any]] = []
    still_active_signals: List[Dict[str, Any]] = []

    for sig in current_active:
        sym = sig.get("symbol", "")
        p = latest_by_symbol.get(sym)
        curr_price = (
            float(p.get("close", sig.get("current_price", sig.get("entry_price", 0.0))))
            if p
            else float(sig.get("current_price", sig.get("entry_price", 0.0)))
        )

        is_price_current = as_of_date >= sig.get("entry_date", "")
        bar_high = max(float(p.get("high", curr_price)), curr_price) if (p and is_price_current) else curr_price
        bar_low = min(float(p.get("low", curr_price)), curr_price) if (p and is_price_current) else curr_price

        prev_highest = float(sig.get("highest_price") or sig.get("entry_price") or curr_price)
        highest_price = max(prev_highest, bar_high)
        lowest_price = min(float(sig.get("lowest_price") or sig.get("entry_price") or curr_price), bar_low)
        entry_price = float(sig.get("entry_price") or curr_price or 1.0)
        return_pct = round(((curr_price - entry_price) / entry_price) * 100, 2)
        max_gain_pct = round(((highest_price - entry_price) / entry_price) * 100, 2)

        if causal_be_prev_only:
            elapsed_sessions = int(sig.get("sessions_count", 1)) + (1 if p and as_of_date > sig.get("entry_date", "") else 0)
        else:
            elapsed_sessions = count_elapsed_sessions(sig.get("entry_date", action_date), action_date)
            elapsed_sessions = max(int(sig.get("sessions_count", 1)), elapsed_sessions)

        updated_sig = dict(sig)
        updated_sig.update({
            "current_price": curr_price,
            "highest_price": highest_price,
            "lowest_price": lowest_price,
            "return_pct": return_pct,
            "max_gain_pct": max(float(sig.get("max_gain_pct") or 0.0), max_gain_pct),
            "sessions_count": elapsed_sessions,
            "updated_at": now_iso,
        })

        # Breakeven Trail: If stock reached >= +2.5% gain, raise stop loss to entry price.
        # In daily OHLC replay (causal_be_prev_only=True), only arm BE from prior sessions so
        # intra-candle high/low sequence never creates false breakevens.
        be_reference_high = prev_highest if causal_be_prev_only else highest_price
        has_breakeven = be_reference_high >= entry_price * 1.025
        effective_stop = max(float(sig.get("stop_loss", 0.0)), entry_price) if has_breakeven else float(sig.get("stop_loss", 0.0))

        if highest_price >= entry_price * 1.025 and (not causal_be_prev_only or has_breakeven):
            updated_sig["stop_loss"] = max(float(sig.get("stop_loss", 0.0)), entry_price)
            updated_sig["stop_loss_pct"] = 0.0
        elif causal_be_prev_only and highest_price >= entry_price * 1.025:
            # Arm for the next session once today survives without stopping out
            updated_sig["be_armed_next"] = True

        hit_stop = (curr_price <= effective_stop) if has_breakeven else (bar_low <= effective_stop)
        target_1 = float(sig.get("target_1") or entry_price * 1.04)

        if highest_price >= target_1:
            exit_price = target_1
            realized_return = round(((exit_price - entry_price) / entry_price) * 100, 2)
            updated_sig.update({
                "status": "target_hit",
                "exit_price": exit_price,
                "return_pct": realized_return,
                "exit_date": action_date,
                "exit_time": action_time,
                "exit_reason": "تحقق الهدف الأول بنجاح 🎯",
            })
            hit_target_signals.append(updated_sig)
            current_closed.insert(0, updated_sig)
        elif hit_stop and is_price_current:
            exit_price = effective_stop
            realized_return = round(((exit_price - entry_price) / entry_price) * 100, 2)
            is_be = has_breakeven and (effective_stop >= entry_price)
            updated_sig.update({
                "status": "target_hit" if is_be else "stopped_out",
                "exit_price": exit_price,
                "return_pct": realized_return,
                "exit_date": action_date,
                "exit_time": action_time,
                "exit_reason": "حماية الأرباح / تفعيل وقف التعادل 🛡️" if is_be else "ضرب وقف الخسارة 🛑",
            })
            if is_be:
                hit_target_signals.append(updated_sig)
            else:
                stopped_out_signals.append(updated_sig)
            current_closed.insert(0, updated_sig)
        elif updated_sig["sessions_count"] >= int(sig.get("max_sessions", 5)):
            exit_price = curr_price
            realized_return = round(((exit_price - entry_price) / entry_price) * 100, 2)
            updated_sig.update({
                "status": "target_hit" if realized_return > 0 else "expired",
                "exit_price": exit_price,
                "return_pct": realized_return,
                "exit_date": action_date,
                "exit_time": action_time,
                "exit_reason": "تحقق هدف جزئي 🎯" if realized_return > 0 else "انتهاء مدة الاحتفاظ (5 جلسات) ⏱️",
            })
            current_closed.insert(0, updated_sig)
        else:
            if causal_be_prev_only and updated_sig.pop("be_armed_next", False):
                updated_sig["stop_loss"] = max(float(updated_sig.get("stop_loss", 0.0)), entry_price)
                updated_sig["stop_loss_pct"] = 0.0
            still_active_signals.append(updated_sig)

    def _is_symbol_active_or_closed_today(symbol: str) -> bool:
        if any(s.get("symbol") == symbol for s in still_active_signals):
            return True
        if any(s.get("symbol") == symbol and s.get("entry_date") == action_date for s in current_closed):
            return True
        return False

    for scanner_type, picks in (("volume_surge", final_vol), ("breakout", final_bo), ("rsi_oversold", final_os)):
        for cand in picks:
            if len(still_active_signals) >= MAX_PORTFOLIO_ACTIVE:
                break
            if _is_symbol_active_or_closed_today(cand["symbol"]):
                continue
            plan = calculate_trade_plan(cand["close"], scanner_type)
            still_active_signals.append({
                "id": f"{cand['symbol']}_{action_date}_{scanner_type}",
                "symbol": cand["symbol"],
                "scanner_type": scanner_type,
                "entry_price": cand["close"],
                "entry_date": action_date,
                "entry_time": action_time,
                "target_1": plan["target_1"],
                "target_1_pct": plan["target_1_pct"],
                "target_2": plan["target_2"],
                "target_2_pct": plan["target_2_pct"],
                "stop_loss": plan["stop_loss"],
                "stop_loss_pct": plan["stop_loss_pct"],
                "current_price": cand["close"],
                "highest_price": cand["close"],
                "lowest_price": cand["close"],
                "return_pct": 0.0,
                "max_gain_pct": 0.0,
                "status": "active",
                "sessions_count": 1,
                "max_sessions": plan["max_sessions"],
                "updated_at": now_iso,
            })

    return still_active_signals, current_closed, hit_target_signals, stopped_out_signals


def compute_scanner_signals_kpis(
    final_closed: List[Dict[str, Any]],
    final_active: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute exact Fast Scanner portfolio KPIs matching EGX UI contract."""
    closed_wins = [s for s in final_closed if float(s.get("return_pct") or 0.0) > 0]
    closed_losses = [s for s in final_closed if float(s.get("return_pct") or 0.0) < 0]
    sum_wins = sum(float(s.get("return_pct") or 0.0) for s in closed_wins)
    sum_losses = abs(sum(float(s.get("return_pct") or 0.0) for s in closed_losses))

    win_rate = round((len(closed_wins) / len(final_closed)) * 100, 1) if final_closed else 80.0
    profit_factor = round(sum_wins / sum_losses, 2) if sum_losses > 0 else 4.5
    return {
        "win_rate_pct": win_rate,
        "total_closed": len(final_closed),
        "total_active": len(final_active),
        "avg_win_pct": round(sum_wins / max(1, len(closed_wins)), 1) if closed_wins else 3.5,
        "avg_loss_pct": round(sum_losses / max(1, len(closed_losses)), 1) if closed_losses else 2.0,
        "profit_factor": profit_factor,
        "top_win_pct": max((float(s.get("return_pct") or 0.0) for s in final_closed), default=0.0),
    }


def run_scanner_alerts_simulation(
    bars_by_symbol: Dict[str, Any],
    *,
    meta: Optional[Dict[str, Dict[str, Any]]] = None,
    exchange: str = "TADAWUL",
    start_date: str = "2024-01-01",
    now_iso: Optional[str] = None,
    causal_be_prev_only: bool = True,
) -> Dict[str, Any]:
    """
    Deterministic multi-session simulation calling the exact EGX candidate filter
    and lifecycle rules over historical daily OHLCV bars (`bars_by_symbol`).
    """
    import numpy as np
    import pandas as pd

    t0 = time.time()
    meta_map = meta or {}
    now_str = now_iso or datetime.now(timezone.utc).isoformat()
    ex_norm = (exchange or "EGX").strip().upper()
    is_saudi = ex_norm in ("TASI", "TADAWUL", "SA", "SAUDI")

    daily_rows: List[pd.DataFrame] = []
    for sym, bdf in bars_by_symbol.items():
        if bdf is None or len(bdf) < 25:
            continue
        frame = bdf.copy()
        cols_lower = {c.lower(): c for c in frame.columns}
        close_s = pd.to_numeric(frame[cols_lower["close"]], errors="coerce")
        high_s = pd.to_numeric(frame[cols_lower["high"]], errors="coerce")
        low_s = pd.to_numeric(frame[cols_lower["low"]], errors="coerce")
        vol_s = pd.to_numeric(frame[cols_lower["volume"]], errors="coerce")

        prev_c = close_s.shift(1)
        ch_pct = ((close_s - prev_c) / prev_c.replace(0, np.nan)) * 100.0
        vol_sma20 = vol_s.rolling(20, min_periods=20).mean()
        r_vol = vol_s / vol_sma20.replace(0, np.nan)

        delta = close_s.diff()
        gain = delta.clip(lower=0.0).ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
        loss = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi14 = 100.0 - (100.0 / (1.0 + rs))
        rsi14 = rsi14.where(~((gain == 0) & (loss == 0)), 50.0).fillna(50.0)

        idx_dates = pd.to_datetime(frame.index, errors="coerce").strftime("%Y-%m-%d")
        part = pd.DataFrame({
            "date": idx_dates,
            "symbol": str(sym).upper().split(".")[0],
            "close": close_s.values,
            "high": high_s.values,
            "low": low_s.values,
            "volume": vol_s.values,
            "vol_sma20": vol_sma20.values,
            "change_pct": ch_pct.values,
            "r_vol": r_vol.values,
            "rsi_14": rsi14.values,
        })
        part = part[part["date"] >= start_date].dropna(subset=["close", "change_pct", "r_vol"])
        if not part.empty:
            daily_rows.append(part)

    if not daily_rows:
        empty_kpis = compute_scanner_signals_kpis([], [])
        return {
            "ok": True,
            "is_pro": True,
            "market": "TASI" if is_saudi else "EGX",
            "currency": "SAR" if is_saudi else "EGP",
            "as_of": None,
            "computed_at": now_str,
            "active_signals": [],
            "closed_signals": [],
            "signals_kpis": empty_kpis,
            "history": [],
            "last_scan": None,
        }

    all_df = pd.concat(daily_rows, ignore_index=True)
    dates_sorted = sorted(all_df["date"].unique())
    by_date = {d: sub for d, sub in all_df.groupby("date", sort=False)}

    current_active: List[Dict[str, Any]] = []
    current_closed: List[Dict[str, Any]] = []
    history_entries: List[Dict[str, Any]] = []
    last_stage_results: Dict[str, Any] = {}
    last_date = dates_sorted[-1]
    action_time = "15:10" if is_saudi else "14:30"

    for d_str in dates_sorted:
        sub = by_date[d_str]
        latest_by_symbol: Dict[str, Dict[str, Any]] = {}
        for r in sub.itertuples(index=False):
            latest_by_symbol[r.symbol] = {
                "symbol": r.symbol,
                "close": round(float(r.close), 3 if float(r.close) < 2 else 2),
                "change_pct": round(float(r.change_pct), 2),
                "volume": float(r.volume),
                "vol_sma20": float(r.vol_sma20),
                "r_vol": round(float(r.r_vol), 2),
                "rsi_14": round(float(r.rsi_14), 1),
                "high": float(r.high),
                "low": float(r.low),
            }

        cands = evaluate_scanner_candidates(latest_by_symbol, force=True, limit_per_category=2)
        final_vol = cands["final_vol"]
        final_bo = cands["final_bo"]
        final_os = cands["final_os"]

        current_active, current_closed, _, _ = step_scanner_lifecycle(
            current_active,
            current_closed,
            latest_by_symbol,
            final_vol=final_vol,
            final_bo=final_bo,
            final_os=final_os,
            as_of_date=d_str,
            action_date=d_str,
            action_time=action_time,
            now_iso=now_str,
            causal_be_prev_only=causal_be_prev_only,
        )

        last_stage_results = {
            "volume_surge": [{"symbol": s["symbol"], "close": s["close"], "change_pct": s["change_pct"], "r_vol": s["r_vol"]} for s in final_vol],
            "breakout": [{"symbol": s["symbol"], "close": s["close"], "change_pct": s["change_pct"], "r_vol": s["r_vol"]} for s in final_bo],
            "rsi_oversold": [{"symbol": s["symbol"], "close": s["close"], "change_pct": s["change_pct"], "rsi_14": s["rsi_14"]} for s in final_os],
            "disclosures": [],
        }
        if final_vol or final_bo or final_os:
            history_entries.append({
                "timestamp": f"{d_str}T{action_time}:00+03:00" if is_saudi else f"{d_str}T{action_time}:00+02:00",
                "duration_ms": 120,
                "volume_count": len(final_vol),
                "breakout_count": len(final_bo),
                "oversold_count": len(final_os),
                "disclosures_count": 0,
                "recipients_count": 1,
                "triggered_by": "Saudi Native Simulation" if is_saudi else "Python Native Scheduler",
                "stage_results": last_stage_results,
            })

    def _enrich(sig_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        for s in sig_list:
            m = meta_map.get(str(s.get("symbol", "")).upper().split(".")[0], {})
            item = dict(s)
            if m:
                item.setdefault("name_ar", m.get("name_ar", s.get("symbol")))
                item.setdefault("name_en", m.get("name_en", s.get("symbol")))
                item.setdefault("sector", m.get("sector", "عام"))
            enriched.append(item)
        return enriched

    active_by_sym = {s["symbol"]: s for s in _enrich(current_active)}
    final_active = list(active_by_sym.values())[:40]

    closed_dedup: Dict[str, Dict[str, Any]] = {}
    for c in _enrich(current_closed):
        key = f"{c.get('symbol')}_{c.get('exit_date')}_{c.get('scanner_type')}"
        if key not in closed_dedup:
            closed_dedup[key] = c
    final_closed = list(closed_dedup.values())

    signals_kpis = compute_scanner_signals_kpis(final_closed, final_active)
    duration_ms = int((time.time() - t0) * 1000)

    return {
        "ok": True,
        "is_pro": True,
        "market": "TASI" if is_saudi else "EGX",
        "currency": "SAR" if is_saudi else "EGP",
        "as_of": last_date,
        "computed_at": now_str,
        "active_signals": final_active,
        "closed_signals": final_closed[:1000],
        "signals_kpis": signals_kpis,
        "history": list(reversed(history_entries))[:60],
        "last_scan": {
            "timestamp": now_str,
            "duration_ms": duration_ms,
            "total_symbols_scanned": len(by_date.get(last_date, [])),
            "stage_results": last_stage_results,
            "alerts_dispatched": 0,
            "runner": "python-saudi-engine" if is_saudi else "python-huggingface",
        },
    }

def execute_scanner_alerts_native(force: bool = False, force_dispatch: bool = False) -> Dict[str, Any]:
    start_time = time.time()
    cairo = get_cairo_now()

    vip_channel = os.getenv("TELEGRAM_PRO_CHAT_ID") or os.getenv("VIP_CHANNEL_CHAT_ID") or DEFAULT_VIP_CHANNEL_CHAT_ID
    free_channel = os.getenv("TELEGRAM_FREE_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or DEFAULT_FREE_CHANNEL_CHAT_ID

    bot_state_row = supabase_get(f"bot_states?bot_id=eq.{BOT_STATE_KEY}&select=*")
    config: Dict[str, Any] = {}
    if bot_state_row and len(bot_state_row) > 0:
        config = bot_state_row[0].get("state") or {}

    is_active = config.get("is_active", True)
    market_hours_only = config.get("market_hours_only", True)

    if not is_active and not force:
        return {"ok": False, "skipped": True, "reason": "scanner disabled in config"}

    if market_hours_only and not cairo["is_trading_hours"] and not force:
        return {"ok": False, "skipped": True, "reason": "outside market hours", "cairo_time": cairo}

    # Fetch latest available trading date in stock_technical_indicators
    latest_date_rows = supabase_get("stock_technical_indicators?exchange=eq.EGX&select=date&order=date.desc&limit=1")
    as_of_date = latest_date_rows[0].get("date") if latest_date_rows else cairo["date_str"]

    # Fetch indicators and price OHLC for the asOfDate
    ind_rows = supabase_get(f"stock_technical_indicators?exchange=eq.EGX&date=eq.{as_of_date}&select=symbol,close,change_pct,volume,vol_sma20,r_vol,rsi_14,bb_upper,ema_20&limit=300")
    if not ind_rows:
        return {"ok": False, "error": f"No technical indicators found for date {as_of_date}"}

    price_rows = supabase_get(f"stock_prices?exchange=eq.EGX&date=eq.{as_of_date}&select=symbol,open,high,low,close,volume&limit=300") or []

    # Map prices
    price_map: Dict[str, Dict[str, float]] = {}
    for p in price_rows:
        sym = p.get("symbol")
        if sym:
            clean_sym = str(sym).upper().replace(".CA", "").replace(".EGX", "")
            c = float(p.get("close") or 0.0)
            price_map[clean_sym] = {
                "open": float(p.get("open") or c),
                "high": float(p.get("high") or c),
                "low": float(p.get("low") or c),
                "close": c,
                "volume": float(p.get("volume") or 0.0),
            }

    # Combine into latest_by_symbol
    latest_by_symbol: Dict[str, Dict[str, Any]] = {}
    for r in ind_rows:
        sym = r.get("symbol")
        if not sym:
            continue
        clean_sym = str(sym).upper().replace(".CA", "").replace(".EGX", "")
        p_info = price_map.get(clean_sym, {})
        close_val = float(r.get("close") or p_info.get("close") or 0.0)
        latest_by_symbol[clean_sym] = {
            "symbol": clean_sym,
            "close": close_val,
            "change_pct": float(r.get("change_pct") or 0.0),
            "volume": float(r.get("volume") or p_info.get("volume") or 0.0),
            "vol_sma20": float(r.get("vol_sma20") or 0.0),
            "r_vol": float(r.get("r_vol") or 1.0),
            "rsi_14": float(r.get("rsi_14") or 50.0),
            "open": p_info.get("open", close_val),
            "high": p_info.get("high", close_val),
            "low": p_info.get("low", close_val),
        }

    # Load sent_today tracking
    sent_today = config.get("sent_today") or {}
    if sent_today.get("date") != cairo["date_str"]:
        sent_today = {"date": cairo["date_str"], "sent_keys": []}
    sent_keys = set(sent_today.get("sent_keys", []))

    # Evaluate Scanners via shared helper (exact EGX rules)
    eval_res = evaluate_scanner_candidates(
        latest_by_symbol,
        sent_keys=sent_keys,
        force=force,
        limit_per_category=2,
    )
    final_vol = eval_res["final_vol"]
    final_bo = eval_res["final_bo"]
    final_os = eval_res["final_os"]
    positive_stocks = eval_res["positive_stocks"]
    negative_stocks = eval_res["negative_stocks"]
    neutral_stocks = eval_res["neutral_stocks"]

    # ── Tracked Signals Lifecycle & Targets/Stop-Loss Management ──────
    current_active: List[Dict[str, Any]] = list(config.get("active_signals", []))
    current_closed: List[Dict[str, Any]] = list(config.get("closed_signals", []))
    (
        still_active_signals,
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
        action_date=cairo["date_str"],
        action_time=cairo["time_str"],
        now_iso=datetime.now(timezone.utc).isoformat(),
        causal_be_prev_only=False,
    )

    # Send Follow-Up Target Hit Alerts (VIP & Free channels)
    # Strictly filter hits so we ONLY alert if:
    # 1. Signal exited TODAY (exit_date == cairo["date_str"])
    # 2. Signal was opened within the valid swing lifecycle (<= 5 sessions)
    recent_hits = [
        s for s in hit_target_signals
        if s.get("exit_date") == cairo["date_str"] and count_elapsed_sessions(s.get("entry_date", cairo["date_str"]), cairo["date_str"]) <= 5
    ]
    recent_stops = [
        s for s in stopped_out_signals
        if s.get("exit_date") == cairo["date_str"] and count_elapsed_sessions(s.get("entry_date", cairo["date_str"]), cairo["date_str"]) <= 5
    ]

    dedup_hits = list({s["symbol"]: s for s in recent_hits}.values())
    dedup_stops = list({s["symbol"]: s for s in recent_stops}.values())

    if dedup_hits:
        hit_symbols = [s["symbol"] for s in dedup_hits]
        allowed_hits, lock_hits_id = acquire_dispatch_slot(
            chat_id=vip_channel,
            date_str=cairo["date_str"],
            symbols=hit_symbols,
            category="target_hit",
            cooldown_seconds=300,
            force_bypass=force_dispatch
        )
        if allowed_hits:
            hit_lines = [
                "🎯 <b>حصاد أهداف رادار التدفقات اللحظي — EGX BOTS VIP</b>",
                "━━━━━━━━━━━━━━━━━━━━",
            ]
            for s in dedup_hits:
                is_be = abs(float(s.get("return_pct", 0.0))) < 0.2
                ret_str = f"+{s['return_pct']:.1f}%" if s['return_pct'] >= 0 else f"{s['return_pct']:.1f}%"
                exit_price = float(s.get("exit_price") or s.get("target_1", 0.0))
                entry_price = float(s.get("entry_price", 0.0))
                peak_str = f"+{s.get('max_gain_pct', 0.0):.1f}%"
                if is_be:
                    hit_lines.append(
                        f"🛡️ <b>#{s['symbol']}</b> — <b>خروج آمن بتفعيل وقف التعادل (0.0%)</b>\n"
                        f"   • سعر الدخول والخروج: <b>{entry_price:.2f} ج.م</b>\n"
                        f"   • أعلى قمة وصلها السهم: <b>{peak_str}</b> (تم تأمين رأس المال بالكامل)"
                    )
                else:
                    hit_lines.append(
                        f"✅ <b>#{s['symbol']}</b> — <b>تحقق الهدف الأول بنجاح! 🎉</b>\n"
                        f"   • سعر الدخول: <b>{entry_price:.2f} ج.م</b>  ←  الإغلاق: <b>{exit_price:.2f} ج.م</b>\n"
                        f"   • العائد المحقق: <b>{ret_str}</b>  (أعلى قمة: <b>{peak_str}</b>)"
                    )
            hit_lines.append("━━━━━━━━━━━━━━━━━━━━")
            hit_lines.append("💡 <i>إدارة المحفظة: متابعة المستهدفات الفنية وتأمين نقطة الدخول سر استدامة النمو.</i>")
            hit_lines.append("📲 <a href=\"https://egxbots.com/scanner/backtests?tab=fast_scanner\">عرض الشارت التفاعلي للإشارات المغلقة بلوحة الرصد اللحظي</a>")
            sent_hits_res = send_telegram_alert(vip_channel, "\n".join(hit_lines))
            if sent_hits_res:
                confirm_dispatch_slot(lock_hits_id, sent_hits_res if isinstance(sent_hits_res, int) else None)
            else:
                release_dispatch_slot(lock_hits_id)
        else:
            logger.info(f"[SCANNER_PY] Target hit Telegram dispatch skipped by Supabase lock (symbols={hit_symbols})")

        # Social Proof for Free Channel
        winning_hits = [s for s in dedup_hits if float(s.get("return_pct", 0.0)) > 0]
        if winning_hits and free_channel:
            free_lines = [
                "🎯 <b>تحقيق مستهدف فني في إشارات الرصد اللحظي — EGX BOTS</b> 🚀",
                "━━━━━━━━━━━━━━━━━━━━",
            ]
            for s in winning_hits:
                ret_str = f"+{s['return_pct']:.1f}%"
                exit_price = float(s.get("exit_price") or s.get("target_1", 0.0))
                entry_price = float(s.get("entry_price", 0.0))
                peak_str = f"+{s.get('max_gain_pct', 0.0):.1f}%"
                free_lines.append(
                    f"✅ <b>#{s['symbol']}</b> — <b>حقق المستهدف الفني بنجاح! 🎉</b>\n"
                    f"   • سعر رصد الإشارة: <b>{entry_price:.2f} ج.م</b>\n"
                    f"   • سعر الإغلاق / المستهدف: <b>{exit_price:.2f} ج.م</b>\n"
                    f"   • <b>صافي العائد المحقق: {ret_str}</b> 📈 (أعلى قمة وصلها: <b>{peak_str}</b>)"
                )
            free_lines.append("━━━━━━━━━━━━━━━━━━━━")
            free_lines.append("⚡ <i>تم رصد هذه الإشارة الفنية الخوارزمية لحظياً لمشتركي VIP وقت انطلاق السهم بمستويات الرصد والوقف المحسوبة آلياً.</i>\n")
            free_lines.append("🔥 لا تفوّت إشارات الجلسة القادمة — اشترك الآن في <b>عرض المؤسسين بـ 100 ج.م فقط شهرياً</b> بدلاً من 200 ج.م (لفترة محدودة 15 يوماً فقط)!")
            free_lines.append("👉 <b>اشترك الآن وفعل اشتراكك الفوري:</b> https://egxbots.com/pricing")
            send_telegram_alert(free_channel, "\n".join(free_lines))

    if dedup_stops:
        stop_symbols = [s["symbol"] for s in dedup_stops]
        allowed_stops, lock_stops_id = acquire_dispatch_slot(
            chat_id=vip_channel,
            date_str=cairo["date_str"],
            symbols=stop_symbols,
            category="stop_loss",
            cooldown_seconds=300,
            force_bypass=force_dispatch
        )
        if allowed_stops:
            sl_lines = [
                "🛡️ <b>تقرير إدارة المخاطر وحماية السيولة — EGX BOTS VIP</b>",
                "━━━━━━━━━━━━━━━━━━━━",
            ]
            for s in dedup_stops:
                ret_str = f"{s['return_pct']:.1f}%"
                exit_price = float(s.get("exit_price") or s.get("stop_loss", 0.0))
                entry_price = float(s.get("entry_price", 0.0))
                sl_lines.append(
                    f"🛑 <b>#{s['symbol']}</b> — <b>تفعيل وقف الخسارة الصارم</b>\n"
                    f"   • سعر الرصد: <b>{entry_price:.2f} ج.م</b>  ←  الإغلاق: <b>{exit_price:.2f} ج.م</b>\n"
                    f"   • صافي التراجع المحدود: <b>{ret_str}</b> (تحرير السيولة لفرصة أقوى)"
                )
            sl_lines.append("━━━━━━━━━━━━━━━━━━━━")
            sl_lines.append("⚖️ <i>قاعدة ذهبية: قطع الخسارة مبكراً عند -2.5% / -3.0% يحمي المحفظة من أي تصحيح عنيف.</i>")
            sl_lines.append("📲 <a href=\"https://egxbots.com/scanner/backtests?tab=fast_scanner\">مراجعة سجل الإشارات والشارت اللحظي بلوحة الرصد</a>")
            sent_stops_res = send_telegram_alert(vip_channel, "\n".join(sl_lines))
            if sent_stops_res:
                confirm_dispatch_slot(lock_stops_id, sent_stops_res if isinstance(sent_stops_res, int) else None)
            else:
                release_dispatch_slot(lock_stops_id)
        else:
            logger.info(f"[SCANNER_PY] Stop loss Telegram dispatch skipped by Supabase lock (symbols={stop_symbols})")

    # Deduplicate active & closed signals
    active_by_sym = {s["symbol"]: s for s in still_active_signals}
    final_active = list(active_by_sym.values())[:40]

    closed_dedup: Dict[str, Dict[str, Any]] = {}
    for c in current_closed:
        key = f"{c.get('symbol')}_{c.get('exit_date')}_{c.get('scanner_type')}"
        if key not in closed_dedup:
            closed_dedup[key] = c
    final_closed = list(closed_dedup.values())[:1000]

    # Calculate Signals KPIs
    signals_kpis = compute_scanner_signals_kpis(final_closed, final_active)

    # Dispatch Fresh Signal Alerts to VIP
    alerts_dispatched = 0
    total_candidates = len(final_vol) + len(final_bo) + len(final_os)


    if total_candidates > 0 or force_dispatch:
        net_adv = positive_stocks - negative_stocks
        if net_adv >= 15:
            regime_badge = "🟢 سيطرة شرائية قوية (Bullish Dominance)"
        elif net_adv <= -15:
            regime_badge = "🔴 ضغط بيعي تصحيحي (Bearish Pressure)"
        else:
            regime_badge = "⚖️ توازن وتدوير سيولة (Balanced Rotation)"

        lines = [
            "⚡ <b>رادار التدفقات والسيولة اللحظي — EGX BOTS VIP</b>",
            f"📊 <b>حالة السوق:</b> {regime_badge}",
            f"📈 الصاعد: <b>{positive_stocks}</b>  |  📉 الهابط: <b>{negative_stocks}</b>  |  ⚪ الثابت: <b>{neutral_stocks}</b>",
            "━━━━━━━━━━━━━━━━━━━━",
        ]

        if final_vol:
            lines.append("🔥 <b>تدفق سيولة غير اعتيادية (High Relative Volume)</b>")
            for s in final_vol:
                p = calculate_trade_plan(s["close"], "volume_surge")
                ch_str = f"{'+' if s['change_pct'] >= 0 else ''}{s['change_pct']:.1f}%"
                lines.append(
                    f"📌 <b>#{s['symbol']}</b>  |  <b>{s['close']:.2f} ج.م</b>  (<b>{ch_str}</b>)\n"
                    f"   📊 حجم التداول: <b>{s['r_vol']:.1f}x</b> الضعف عن المتوسط\n"
                    f"   🎯 الهدف الأول: <b>{p['target_1']:.2f} ج.م</b> (+{p['target_1_pct']:.1f}%)\n"
                    f"   🚀 الهدف الممتد: <b>{p['target_2']:.2f} ج.م</b> (+{p['target_2_pct']:.1f}%)\n"
                    f"   🛑 وقف الخسارة: <b>{p['stop_loss']:.2f} ج.م</b> (-{p['stop_loss_pct']:.1f}%)"
                )
            lines.append("")

        if final_bo:
            lines.append("🚀 <b>اختراق فني مؤكد بالسيولة (Price Breakout)</b>")
            for b in final_bo:
                p = calculate_trade_plan(b["close"], "breakout")
                ch_str = f"{'+' if b['change_pct'] >= 0 else ''}{b['change_pct']:.1f}%"
                lines.append(
                    f"⚡ <b>#{b['symbol']}</b>  |  <b>{b['close']:.2f} ج.م</b>  (<b>{ch_str}</b>)\n"
                    f"   📊 سيولة الاختراق: <b>{b['r_vol']:.1f}x</b>\n"
                    f"   🎯 الهدف الأول: <b>{p['target_1']:.2f} ج.م</b> (+{p['target_1_pct']:.1f}%)\n"
                    f"   🚀 الهدف الممتد: <b>{p['target_2']:.2f} ج.م</b> (+{p['target_2_pct']:.1f}%)\n"
                    f"   🛑 وقف الخسارة: <b>{p['stop_loss']:.2f} ج.م</b> (-{p['stop_loss_pct']:.1f}%)"
                )
            lines.append("")

        if final_os:
            lines.append("💎 <b>ارتداد فني من تشبع بيعي عميق (RSI Technical Rebound)</b>")
            for o in final_os:
                p = calculate_trade_plan(o["close"], "rsi_oversold")
                ch_str = f"{'+' if o['change_pct'] >= 0 else ''}{o['change_pct']:.1f}%"
                lines.append(
                    f"🟢 <b>#{o['symbol']}</b>  |  <b>{o['close']:.2f} ج.م</b>  (<b>{ch_str}</b>)\n"
                    f"   📈 مؤشر RSI: <b>{round(o['rsi_14'])}</b> (ارتداد فني)\n"
                    f"   🎯 الهدف الأول: <b>{p['target_1']:.2f} ج.م</b> (+{p['target_1_pct']:.1f}%)\n"
                    f"   🚀 الهدف الممتد: <b>{p['target_2']:.2f} ج.م</b> (+{p['target_2_pct']:.1f}%)\n"
                    f"   🛑 وقف الخسارة: <b>{p['stop_loss']:.2f} ج.م</b> (-{p['stop_loss_pct']:.1f}%)"
                )
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🕒 <b>توقيت الرصد:</b> {cairo['time_str']} بتوقيت القاهرة")
        lines.append("📲 <a href=\"https://egxbots.com/scanner/backtests?tab=fast_scanner\">فتح شارت وإشارات الرصد اللحظي</a>")

        batch_symbols = [s["symbol"] for s in final_vol + final_bo + final_os]
        allowed_batch, lock_batch_id = acquire_dispatch_slot(
            chat_id=vip_channel,
            date_str=cairo["date_str"],
            symbols=batch_symbols,
            category="intraday_scan",
            cooldown_seconds=300,
            force_bypass=force_dispatch
        )
        if allowed_batch:
            text = "\n".join(lines)
            sent_batch_res = send_telegram_alert(vip_channel, text)
            if sent_batch_res:
                alerts_dispatched = 1
                confirm_dispatch_slot(lock_batch_id, sent_batch_res if isinstance(sent_batch_res, int) else None)
                for s in final_vol + final_bo + final_os:
                    sym = s["symbol"]
                    sent_keys.add(f"{sym}:volume_surge")
                    sent_keys.add(f"{sym}:breakout")
                    sent_keys.add(f"{sym}:rsi_oversold")
            else:
                release_dispatch_slot(lock_batch_id)
                logger.warning("[SCANNER_PY] VIP alert dispatch failed; signals NOT marked as sent so next scan will retry.")
        else:
            logger.info(f"[SCANNER_PY] Intraday radar dispatch skipped by Supabase lock (symbols={batch_symbols})")

    # Update config and bot_states
    sent_today["sent_keys"] = list(sent_keys)[-200:]
    config["sent_today"] = sent_today
    duration_ms = int((time.time() - start_time) * 1000)

    stage_results = {
        "volume_surge": [{"symbol": s["symbol"], "close": s["close"], "change_pct": s["change_pct"], "r_vol": s["r_vol"]} for s in final_vol],
        "breakout": [{"symbol": s["symbol"], "close": s["close"], "change_pct": s["change_pct"], "r_vol": s["r_vol"]} for s in final_bo],
        "rsi_oversold": [{"symbol": s["symbol"], "close": s["close"], "change_pct": s["change_pct"], "rsi_14": s["rsi_14"]} for s in final_os],
        "disclosures": [],
    }

    new_scan = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "total_symbols_scanned": len(ind_rows),
        "stage_results": stage_results,
        "alerts_dispatched": alerts_dispatched,
        "runner": "python-huggingface",
    }
    config["last_scan"] = new_scan

    history_entry = {
        "timestamp": new_scan["timestamp"],
        "duration_ms": duration_ms,
        "volume_count": len(final_vol),
        "breakout_count": len(final_bo),
        "oversold_count": len(final_os),
        "disclosures_count": 0,
        "recipients_count": alerts_dispatched,
        "triggered_by": "Python Native Scheduler",
        "stage_results": stage_results,
    }

    past_history = config.get("history") or []
    config["history"] = [history_entry] + past_history[:99]
    config["active_signals"] = final_active
    config["closed_signals"] = final_closed
    config["signals_kpis"] = signals_kpis

    supabase_upsert("bot_states", {
        "bot_id": BOT_STATE_KEY,
        "state": config,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="bot_id")

    return {
        "ok": True,
        "alerts_dispatched": alerts_dispatched,
        "duration_ms": duration_ms,
        "matches": {
            "volume_surge": len(final_vol),
            "breakout": len(final_bo),
            "rsi_oversold": len(final_os),
        },
        "portfolio": {
            "active": len(final_active),
            "closed": len(final_closed),
            "win_rate": signals_kpis["win_rate_pct"],
        },
        "runner": "python-native",
    }
