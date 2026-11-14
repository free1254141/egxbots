"""
api/scheduled_automations_worker.py — Background Scheduler for User-Defined AI Chat Automations.

Executes on Hugging Face Spaces / Python Backend natively.
Monitors user-scheduled times (Cairo Time), verifies Pro subscription,
consumes quota atomically via consume_ai_chat_quota, generates DeepSeek analysis
backed by live EGX indicators, Wyckoff scans, open recommendations, and user portfolio,
and delivers responses directly to user Telegram channels/chats.

Key architectural rules:
- Zero load on Vercel: Runs natively in Python background thread.
- Zero Supabase log query waste: Targeted lookups with explicit column projections and strict limits.
- HF sleep resilience: In-memory cache + 90-minute catch-up window for cold boots.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    requests = None

try:
    from dotenv import load_dotenv
    _base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_base_dir, ".env"))
    load_dotenv(os.path.join(_base_dir, "web", ".env.local"), override=True)
except Exception:
    pass

logger = logging.getLogger("scheduled_automations_worker")
logger.setLevel(logging.INFO)

CAIRO_TZ = ZoneInfo("Africa/Cairo")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
TELEGRAM_RELAY_BASE = (os.getenv("TELEGRAM_RELAY_URL") or "https://api.telegram.org").rstrip("/")

_worker_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_cached_automations: List[Dict[str, Any]] = []
_cache_lock = threading.Lock()
_last_cache_refresh: float = 0.0
_CACHE_TTL_SECONDS = 300.0  # 5 minutes background refresh, or immediate via sync_automations_cache()

_cached_egx_stocks: List[Dict[str, Any]] = []
_last_stocks_refresh: float = 0.0
_STOCKS_TTL_SECONDS = 3600.0  # 1 hour cache for symbol/Arabic name lookup


def _get_supabase_config() -> tuple[str, str]:
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        or ""
    )
    return url, key


def _supabase_request(
    endpoint: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Optional[Any]:
    url, key = _get_supabase_config()
    if not url or not key:
        return None
    full_url = f"{url}/rest/v1/{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if method in ("POST", "PATCH"):
        headers["Prefer"] = "return=representation"
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(full_url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except Exception as e:
        logger.warning(f"[AUTOMATIONS_WORKER] {method} {endpoint} failed: {e}")
        return None


def get_cairo_time() -> dt.datetime:
    try:
        return dt.datetime.now(CAIRO_TZ)
    except Exception:
        return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)


def sync_automations_cache() -> int:
    """Refreshes the in-memory cache of active scheduled automations from Supabase."""
    global _cached_automations, _last_cache_refresh
    rows = _supabase_request(
        "scheduled_chat_automations?is_active=eq.true&select=id,user_id,name,prompt,scheduled_time,days_of_week,telegram_chat_id,is_active,last_run_at,last_run_date,last_status,created_at,updated_at&limit=500"
    )
    if rows is not None and isinstance(rows, list):
        with _cache_lock:
            _cached_automations = rows
            _last_cache_refresh = time.time()
        logger.info(f"[AUTOMATIONS_WORKER] Cached {len(_cached_automations)} active automations.")
        return len(_cached_automations)
    return len(_cached_automations)


def get_telegram_bot_token() -> str:
    return (
        os.getenv("ARTORO_AI_BOT")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or os.getenv("SUPPORT_BOT_TOKEN")
        or ""
    ).strip()


def _strip_markdown_formatting(text: str) -> str:
    """Removes Markdown markers when retrying plain-text delivery after Telegram parse errors."""
    return text.replace("**", "").replace("__", "").replace("`", "")


def _split_telegram_message(text: str, max_length: int = 3900) -> List[str]:
    """Splits a long message into natural chunks on paragraph or line boundaries without truncation."""
    if len(text) <= max_length:
        return [text]
    chunks: List[str] = []
    remaining = text
    while len(remaining) > max_length:
        # Prefer splitting at a blank line / section break
        cut = remaining.rfind("\n\n", 0, max_length)
        if cut < 1000:
            # Fallback to single newline
            cut = remaining.rfind("\n", 0, max_length)
        if cut < 1000:
            # Fallback to whitespace
            cut = remaining.rfind(" ", 0, max_length)
        if cut < 1000:
            cut = max_length
        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def send_telegram_direct(chat_id: str | int, text: str) -> bool:
    """Delivers message directly to user's Telegram chat or channel with auto-chunking & plain-text fallback."""
    token = get_telegram_bot_token()
    if not token or not chat_id:
        logger.warning("[AUTOMATIONS_WORKER] Missing Telegram Bot Token or chat_id")
        return False

    target_chat_id: str | int = str(chat_id).strip()
    thread_id: Optional[int] = None
    if isinstance(target_chat_id, str) and "_" in target_chat_id and not target_chat_id.startswith("@"):
        parts = target_chat_id.split("_", 1)
        target_chat_id = parts[0]
        try:
            thread_id = int(parts[1])
        except ValueError:
            pass

    if isinstance(target_chat_id, str) and target_chat_id.lstrip("-").isdigit():
        target_chat_id = int(target_chat_id)

    # Deliver all chunks completely without cutting off content
    chunks = _split_telegram_message(text)

    bases = [TELEGRAM_RELAY_BASE]
    if "https://api.telegram.org" not in bases:
        bases.append("https://api.telegram.org")

    all_delivered = True
    for chunk in chunks:
        chunk_delivered = False
        for base in bases:
            if chunk_delivered:
                break
            url = f"{base}/bot{token}/sendMessage"
            # Attempt 1: Markdown parse_mode, Attempt 2: Plain text fallback if Markdown entities fail
            for mode in ("Markdown", None):
                payload: Dict[str, Any] = {
                    "chat_id": target_chat_id,
                    "text": chunk if mode else _strip_markdown_formatting(chunk),
                    "disable_web_page_preview": True,
                }
                if mode:
                    payload["parse_mode"] = mode
                if thread_id is not None:
                    payload["message_thread_id"] = thread_id

                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        res_json = json.loads(resp.read().decode("utf-8"))
                        if res_json.get("ok"):
                            chunk_delivered = True
                            break
                except urllib.error.HTTPError as he:
                    err_body = ""
                    try:
                        err_body = he.read().decode("utf-8", errors="ignore")
                    except Exception:
                        pass
                    if he.code == 400 and mode == "Markdown":
                        logger.info(f"[AUTOMATIONS_WORKER] Markdown parse error for {chat_id}, retrying plain text...")
                        continue
                    logger.warning(f"[AUTOMATIONS_WORKER] Telegram HTTP {he.code} to {chat_id} via {base}: {err_body[:200]}")
                    break
                except Exception as e:
                    logger.warning(f"[AUTOMATIONS_WORKER] Telegram send to {chat_id} via {base} failed: {e}")
                    break

        if not chunk_delivered:
            all_delivered = False

    return all_delivered


ADMIN_USER_IDS = {"ba9c27e8-f62d-452f-8a29-dc77fd092207", "c4b3a6d0-61c5-4f75-97bc-24f486666da0"}
ADMIN_TG_IDS = {"5149631436"}


def _is_user_pro(user_id: str) -> bool:
    """Verifies that the user currently holds an active Pro/Lifetime/Trial subscription or is admin."""
    # 1. Check known admin user IDs
    if user_id in ADMIN_USER_IDS:
        return True

    # 2. Check profile admin Telegram chat IDs
    prof = _supabase_request(f"profiles?id=eq.{user_id}&select=telegram_chat_id&limit=1") or []
    if prof and isinstance(prof, list) and len(prof) > 0:
        if str(prof[0].get("telegram_chat_id") or "") in ADMIN_TG_IDS:
            return True

    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    # 3. Check active or trialing subscriptions
    subs = _supabase_request(
        f"subscriptions?user_id=eq.{user_id}&status=in.(active,trialing)&select=plan_id,current_period_end&order=current_period_end.desc&limit=1"
    ) or []
    if subs and isinstance(subs, list) and len(subs) > 0:
        end_str = str(subs[0].get("current_period_end") or "")
        plan_id = str(subs[0].get("plan_id") or "").lower()
        if not end_str or "lifetime" in plan_id or "2126" in end_str or end_str > now_iso:
            return True

    # 4. Check 3-day Pro trial table if applicable
    trials = _supabase_request(
        f"subscription_trials?user_id=eq.{user_id}&select=expires_at&order=expires_at.desc&limit=1"
    ) or []
    if trials and isinstance(trials, list) and len(trials) > 0:
        exp_str = str(trials[0].get("expires_at") or "")
        if exp_str and exp_str > now_iso:
            return True

    return False


def _resolve_user_telegram(user_id: str, custom_chat_id: Optional[str]) -> Optional[str]:
    """Finds the best Telegram chat or channel ID for delivering the automation."""
    if custom_chat_id and str(custom_chat_id).strip():
        return str(custom_chat_id).strip()

    prof = _supabase_request(f"profiles?id=eq.{user_id}&select=telegram_chat_id&limit=1") or []
    if prof and prof[0].get("telegram_chat_id"):
        return str(prof[0]["telegram_chat_id"])

    invites = _supabase_request(f"pro_telegram_invites?user_id=eq.{user_id}&select=vip_telegram_user_id&limit=1") or []
    if invites and invites[0].get("vip_telegram_user_id"):
        return str(invites[0]["vip_telegram_user_id"])

    state = _supabase_request(f"telegram_vip_chat_state?linked_user_id=eq.{user_id}&select=telegram_user_id&limit=1") or []
    if state and state[0].get("telegram_user_id"):
        return str(state[0]["telegram_user_id"])

    return None


def _consume_user_quota(user_id: str, today_cairo: str) -> bool:
    """Atomically consumes 1 credit from the user's monthly chat quota."""
    url, key = _get_supabase_config()
    if not url or not key:
        return False
    rpc_url = f"{url}/rest/v1/rpc/consume_ai_chat_quota"
    payload = {
        "p_user_id": user_id,
        "p_date": today_cairo,
        "p_limit": 350,  # Pro monthly limit
    }
    req = urllib.request.Request(
        rpc_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 0:
                return bool(data[0].get("allowed"))
            return False
    except Exception as e:
        logger.warning(f"[AUTOMATIONS_WORKER] Quota RPC failed for {user_id}: {e}")
        # Fail safe: allow if transient database RPC error occurs
        return True


def _get_egx_stocks_catalog() -> List[Dict[str, Any]]:
    """Returns cached list of EGX stocks (symbol, name, name_ar) for fast Arabic/English matching."""
    global _cached_egx_stocks, _last_stocks_refresh
    if _cached_egx_stocks and (time.time() - _last_stocks_refresh < _STOCKS_TTL_SECONDS):
        return _cached_egx_stocks

    rows = _supabase_request("stocks?country=eq.Egypt&select=symbol,name,name_ar&limit=300")
    if rows and isinstance(rows, list):
        _cached_egx_stocks = rows
        _last_stocks_refresh = time.time()
    return _cached_egx_stocks


def _normalize_ar(text: str) -> str:
    """Normalizes Arabic text for fuzzy stock name matching."""
    s = re.sub(r"[أإآ]", "ا", text)
    s = s.replace("ة", "ه").replace("ى", "ي")
    return s


def _extract_symbols_from_text(text: str) -> tuple[List[str], Dict[str, str]]:
    """Extracts both English tickers and Arabic stock names from user prompt."""
    catalog = _get_egx_stocks_catalog()
    name_map: Dict[str, str] = {}
    for row in catalog:
        sym = str(row.get("symbol") or "").upper().replace(".CA", "").replace(".EGX", "").strip()
        if sym:
            name_map[sym] = str(row.get("name_ar") or row.get("name") or sym)

    # 1. English tickers
    words = re.findall(r"[A-Za-z]{2,8}", text)
    stop_words = {"THE", "AND", "FOR", "BUY", "SELL", "VIP", "BOT", "EGX", "PRO", "RSI", "EMA", "MACD", "ATR", "SMC"}
    found: List[str] = []
    for w in words:
        u = w.upper()
        if u not in stop_words and (not name_map or u in name_map):
            if u not in found:
                found.append(u)

    # 2. Common Arabic aliases & official Arabic company names
    norm_text = _normalize_ar(text)
    arabic_aliases = {
        "فوري": "FWRY",
        "طلعت مصطفي": "TMGH",
        "التجاري الدولي": "COMI",
        "بلتون": "BTFH",
        "القلعه": "CCAP",
        "هيرميس": "HRHO",
        "السويدي": "SWDY",
        "مصر الجديده": "HELI",
        "مدينه مصر": "MASR",
        "بالم هيلز": "PHDC",
        "سوديك": "OCDI",
        "ابن سينا": "ISPH",
        "ابو قير": "ABUK",
        "موبكو": "MFPC",
        "سيدي كرير": "SKPC",
        "اموك": "AMOC",
        "المصريه للاتصالات": "ETEL",
        "وي للاتصالات": "ETEL",
        "الشرقيه للدخان": "EAST",
        "اي فاينانس": "EFIH",
        "حديد عز": "ESRS",
        "عتاقه": "ATQA",
        "كيما": "EGCH",
        "زهراء المعادي": "ZMID",
        "اعمار": "EMFD",
        "اوراسكوم": "ORAS",
        "جي بي": "GBCO",
        "ايبيكو": "PHAR",
        "ممفيس": "MPCI",
        "جنوب الوادي": "SVCE",
        "العبور للاستثمار": "OBRI",
    }
    for alias, sym in arabic_aliases.items():
        if alias in norm_text and sym not in found:
            found.append(sym)

    for row in catalog:
        sym = str(row.get("symbol") or "").upper().replace(".CA", "").replace(".EGX", "").strip()
        name_ar = str(row.get("name_ar") or "").strip()
        if sym and name_ar and len(name_ar) >= 4:
            norm_name = _normalize_ar(name_ar)
            if norm_name in norm_text and sym not in found:
                found.append(sym)

    return found[:8], name_map


def _fetch_market_indicators_brief(
    symbols: List[str],
    prompt: str = "",
    task_name: str = "",
    user_id: str = "",
) -> str:
    """Fetches rich precalculated technical indicators, open recommendations, Wyckoff scans, and portfolio."""
    combined_text = f"{task_name} {prompt}"
    extracted_syms, name_map = _extract_symbols_from_text(combined_text)
    all_symbols = list(dict.fromkeys([s.upper() for s in (symbols or [])] + extracted_syms))[:8]

    sections: List[str] = []

    # 1. User Portfolio (if prompt asks about portfolio / محفظتي)
    if user_id and any(k in combined_text for k in ("محفظت", "محفظة", "أسهمي", "اسهمي", "مراكزي", "portfolio")):
        pos_rows = _supabase_request(
            f"positions?user_id=eq.{user_id}&status=eq.open&select=symbol,quantity,entry_price&limit=15"
        ) or []
        if not pos_rows:
            pos_rows = _supabase_request(
                f"positions?user_id=eq.{user_id}&status=eq.OPEN&select=symbol,quantity,entry_price&limit=15"
            ) or []
        if isinstance(pos_rows, list) and pos_rows:
            port_lines = ["💼 محفظة المشترك المسجلة حالياً:"]
            for p in pos_rows:
                psym = str(p.get("symbol") or "").upper().replace(".CA", "")
                if psym and psym not in all_symbols and len(all_symbols) < 10:
                    all_symbols.append(psym)
                pname = name_map.get(psym, psym)
                port_lines.append(
                    f"• #{psym} ({pname}): الكمية {p.get('quantity') or 'غير محددة'} | متوسط الشراء {p.get('entry_price') or 0} ج.م"
                )
            sections.append("\n".join(port_lines))

    # 2. Specific Symbols or Top Bullish Market Indicators
    if all_symbols:
        sym_filter = ",".join(all_symbols[:8])
        rows = _supabase_request(
            f"stock_technical_indicators?symbol=in.({sym_filter})&select=symbol,date,close,change_pct,volume,r_vol,rsi_14,ema_20,ema_50,macd,macd_signal,bb_upper,bb_lower,cmf_20,egx_ai_score,divergence_summary&limit=10"
        ) or []
    else:
        latest_ti_rows = _supabase_request(
            "stock_technical_indicators?exchange=eq.EGX&select=date&order=date.desc&limit=1"
        ) or []
        latest_ti_date = (
            latest_ti_rows[0].get("date")
            if isinstance(latest_ti_rows, list) and latest_ti_rows and isinstance(latest_ti_rows[0], dict)
            else None
        )
        ti_date_filter = f"&date=eq.{latest_ti_date}" if latest_ti_date else ""
        rows = _supabase_request(
            f"stock_technical_indicators?exchange=eq.EGX{ti_date_filter}&change_pct=gt.0&rsi_14=gte.45&rsi_14=lte.75&select=symbol,date,close,change_pct,volume,r_vol,rsi_14,ema_20,ema_50,macd,macd_signal,bb_upper,bb_lower,cmf_20,egx_ai_score,divergence_summary&order=egx_ai_score.desc.nullslast,r_vol.desc.nullslast&limit=8"
        ) or []
        if not rows:
            rows = _supabase_request(
                f"stock_technical_indicators?exchange=eq.EGX{ti_date_filter}&select=symbol,close,change_pct,volume,rsi_14,ema_20,bb_upper,bb_lower&order=volume.desc&limit=5"
            ) or []

    if isinstance(rows, list) and rows:
        lines = ["📊 بيانات السوق والمؤشرات الفنية اللحظية المسجلة:"]
        for r in rows:
            sym = str(r.get("symbol") or "").upper()
            ar_name = name_map.get(sym, "")
            label = f"#{sym} ({ar_name})" if ar_name and ar_name != sym else f"#{sym}"
            close = r.get("close")
            chg = float(r.get("change_pct") or 0)
            rsi = float(r.get("rsi_14") or 50)
            ema20 = r.get("ema_20")
            ema50 = r.get("ema_50")
            rvol = r.get("r_vol")
            bb_u = r.get("bb_upper")
            bb_l = r.get("bb_lower")
            ai_sc = r.get("egx_ai_score")
            extra = []
            if ema50:
                extra.append(f"EMA50: {float(ema50):.2f}")
            if bb_l and bb_u:
                extra.append(f"دعم/مقاومة بولينجر: {float(bb_l):.2f} - {float(bb_u):.2f}")
            if rvol:
                extra.append(f"السيولة النسبية: {float(rvol):.1f}x")
            if ai_sc:
                extra.append(f"تقييم AI: {float(ai_sc):.0f}/100")
            extra_str = (" | " + " | ".join(extra)) if extra else ""
            lines.append(
                f"• {label}: إغلاق {close} ج.م ({chg:+.2f}%) | RSI: {rsi:.1f} | EMA20: {ema20}{extra_str}"
            )
        sections.append("\n".join(lines))

    # 3. Open Recommendations (if prompt asks about recommendations / توصيات / إيجابية / صفقات)
    if any(k in combined_text for k in ("توصي", "صفق", "مفتوح", "إشارات", "اشارات", "مرشح", "ايجاب", "إيجاب", "شراء")):
        rec_rows = _supabase_request(
            "scan_results?is_public=eq.true&status=eq.open&select=symbol,name,entry_price,target_price,stop_loss,last_close,profit_loss_pct&limit=10"
        ) or []
        if isinstance(rec_rows, list) and rec_rows:
            rec_lines = ["🎯 التوصيات والصفقات المفتوحة المعتمدة حالياً على المنصة:"]
            for rec in rec_rows:
                rsym = str(rec.get("symbol") or "").upper()
                rname = name_map.get(rsym) or rec.get("name") or rsym
                rec_lines.append(
                    f"• #{rsym} ({rname}): سعر الدخول {rec.get('entry_price')} ج.م | السعر الحالي {rec.get('last_close')} ج.م | المستهدف {rec.get('target_price')} ج.م | وقف الخسارة {rec.get('stop_loss')} ج.م | العائد الحالي {float(rec.get('profit_loss_pct') or 0):+.2f}%"
                )
            sections.append("\n".join(rec_lines))

    # 4. Wyckoff Accumulation & Breakout Scan Summary (if prompt asks about Wyckoff / accumulation / waves / breakouts)
    if any(k in combined_text for k in ("وايكوف", "تجميع", "سيول", "موج", "اخترق", "اختراق", "نموذج", "اليوت", "إليوت", "ارتداد", "ايجاب", "إيجاب")):
        latest_scan_rows = _supabase_request(
            "stock_scans_summary?select=scan_date&order=scan_date.desc&limit=1"
        ) or []
        latest_scan_date = (
            latest_scan_rows[0].get("scan_date")
            if isinstance(latest_scan_rows, list) and latest_scan_rows and isinstance(latest_scan_rows[0], dict)
            else None
        )
        scan_date_filter = f"&scan_date=eq.{latest_scan_date}" if latest_scan_date else ""
        acc_rows = _supabase_request(
            f"stock_scans_summary?acc_score=gte.50{scan_date_filter}&wyckoff_phase=neq.distribution&select=symbol,scan_date,signal,wyckoff_phase,acc_score,vol_ratio,consecutive_acc_days,rsi_14,change_pct&order=acc_score.desc&limit=8"
        ) or []
        if isinstance(acc_rows, list) and acc_rows:
            acc_lines = ["🔍 نتائج مسح التجميع المؤسسي (وايكوف) والسيولة الذكية:"]
            for a in acc_rows:
                asym = str(a.get("symbol") or "").upper()
                aname = name_map.get(asym, asym)
                acc_lines.append(
                    f"• #{asym} ({aname}): مرحلة وايكوف={a.get('wyckoff_phase')} | إشارة={a.get('signal')} | قوة التجميع={a.get('acc_score')}% | أيام تجميع متتالية={a.get('consecutive_acc_days')} | سيولة نسبية={float(a.get('vol_ratio') or 1.0):.2f}x | RSI={float(a.get('rsi_14') or 50):.1f} | تغير={float(a.get('change_pct') or 0):+.2f}%"
                )
            sections.append("\n".join(acc_lines))

    return "\n\n".join(sections)


def _generate_ai_consultation(prompt: str, user_name: str, user_id: str = "") -> str:
    """Generates a professional stock market consultation using DeepSeek."""
    deepseek_key = os.getenv("DEEPSEEK_OFFICIAL_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
    if not deepseek_key:
        return "أهلاً بك! تعذر الاتصال بمحرك الذكاء الاصطناعي حالياً لعدم توفر المفتاح. برجاء المراجعة مع الدعم الفني."

    words = re.findall(r"[A-Za-z]{2,8}", prompt)
    symbols = [w.upper() for w in words if w.upper() not in {"THE", "AND", "FOR", "BUY", "SELL", "VIP", "BOT", "EGX"}]
    indicators_brief = _fetch_market_indicators_brief(symbols, prompt=prompt, task_name=user_name, user_id=user_id)

    system_prompt = (
        "أنت أرتورو (ARTORO AI)، المساعد المالي والتقني الخبير في البورصة المصرية (EGX).\n"
        "تقدم استشارة مجدولة مخصصة وموجزة للمشترك Pro بناءً على طلبه المحدد، وتعمل في أي وقت يختاره المستخدم طوال اليوم وعلى مدار الأسبوع.\n"
        "قواعد الإجابة:\n"
        "1. اعتمد حصرياً على الأرقام، الأسعار، التوصيات المفتوحة، ونتائج مسح وايكوف والمؤشرات الفنية المرفقة في سياق البيانات الحقيقية، واذكر كود السهم واسمه العربي المعتمد.\n"
        "2. قدّم تحليلاً فنياً واقعياً ومحترفاً ومباشراً مقسماً بوضوح حسب نقاط سؤال المشترك بدون حشو.\n"
        "3. ركز على مستويات الدعم، المقاومة، اتجاه السيولة، وحجم التداول.\n"
        "4. إذا كان توقيت الاستشارة خارج ساعات التداول الرسمية بالبورصة أو في عطلة نهاية الأسبوع، اعتمد على أحدث بيانات إغلاق مسجلة وقدّم رؤية استباقية واستعداداً للجلسة القادمة.\n"
        "5. اختم دائماً بنصيحة إدارة مخاطر ذكية ومستوى وقف خسارة محدد (2.5% إلى 3.5%) وخاتمة فنية متكاملة.\n"
        "6. التزم باللغة العربية الواضحة وتنسيق تليجرام أنيق ومرتب مع الإيموجي المناسب للقراءة السريعة.\n"
        "7. احرص على إكمال كل فكرة وجملة بدقة، ولا تترك أي فقرة أو نقطة مقطوعة أو غير مكتملة أبداً."
    )

    user_content = f"طلب الاستشارة المجدولة من المشترك ({user_name}):\n{prompt}"
    if indicators_brief:
        user_content += f"\n\n{indicators_brief}"

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": 3500,
    }

    # 1. Primary engine: DeepSeek Chat with browser-standard User-Agent
    deepseek_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {deepseek_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    if requests is not None:
        try:
            r = requests.post(DEEPSEEK_API_URL, headers=deepseek_headers, json=payload, timeout=35)
            if r.status_code == 200:
                res_data = r.json()
                content = res_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if content:
                    return content
            logger.warning(f"[AUTOMATIONS_WORKER] DeepSeek returned HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            logger.warning(f"[AUTOMATIONS_WORKER] DeepSeek requests error: {e}")
    else:
        req = urllib.request.Request(
            DEEPSEEK_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=deepseek_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if content:
                    return content
        except Exception as e:
            logger.warning(f"[AUTOMATIONS_WORKER] DeepSeek urllib error: {e}")

    # 2. Secondary fallback engine: Nvidia Llama-3.3-70B
    nvidia_key = (os.getenv("NVIDIA_API_KEY") or os.getenv("NVIDIA_SECONDARY_API_KEY") or "").strip()
    if nvidia_key:
        try:
            nv_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {nvidia_key}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            }
            nv_payload = {
                "model": "meta/llama-3.3-70b-instruct",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.3,
                "max_tokens": 3200,
            }
            if requests is not None:
                nv_resp = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=nv_headers, json=nv_payload, timeout=30)
                if nv_resp.status_code == 200:
                    nv_data = nv_resp.json()
                    content = nv_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if content:
                        logger.info("[AUTOMATIONS_WORKER] Generated consultation via Nvidia Llama-3.3-70B fallback.")
                        return content
                logger.warning(f"[AUTOMATIONS_WORKER] Nvidia API returned HTTP {nv_resp.status_code}: {nv_resp.text[:200]}")
        except Exception as e:
            logger.warning(f"[AUTOMATIONS_WORKER] Nvidia fallback error: {e}")

    # 3. Tertiary fallback: Structured technical analysis directly from real market indicators
    fallback_lines = [
        "📊 **تقرير المتابعة الفنية المجدولة — EGX BOTS**",
        f"👤 المشترك: **{user_name}** | الطلب: *{prompt}*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if indicators_brief:
        fallback_lines.append("📈 **أحدث مؤشرات وأسعار السوق:**")
        fallback_lines.append(indicators_brief)
        fallback_lines.append("")
    fallback_lines.extend([
        "⚖️ **إدارة المخاطر:**",
        "• يرجى الالتزام بمستويات وقف الخسارة المحددة (2.5% إلى 3.5%) وتجنب الدخول بكامل السيولة في سهم واحد.",
        "━━━━━━━━━━━━━━━━━━━━",
        "💡 *تحديث دوري مؤتمت صادر عن محرك ARTORO AI للبورصة المصرية.*"
    ])
    return "\n".join(fallback_lines)


def _log_automation_to_chat_history(auto_id: str, user_id: str, name: str, prompt: str, reply_text: str, now_iso: str) -> None:
    """Persists the scheduled consultation into ai_chat_sessions and ai_chat_messages using valid UUID auto_id."""
    try:
        # 1. Upsert session in ai_chat_sessions so foreign key on ai_chat_messages(session_id) is satisfied
        _supabase_request(
            "ai_chat_sessions?on_conflict=id",
            method="POST",
            payload={
                "id": auto_id,
                "user_id": user_id,
                "title": f"⏰ {name}"[:80],
                "updated_at": now_iso,
            },
            extra_headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        # 2. Insert user prompt and assistant response
        _supabase_request(
            "ai_chat_messages",
            method="POST",
            payload={
                "session_id": auto_id,
                "user_id": user_id,
                "role": "user",
                "content": f"[استشارة مجدولة: {name}] {prompt}",
                "created_at": now_iso,
            },
            extra_headers={"Prefer": "return=minimal"},
        )
        _supabase_request(
            "ai_chat_messages",
            method="POST",
            payload={
                "session_id": auto_id,
                "user_id": user_id,
                "role": "assistant",
                "content": reply_text,
                "created_at": now_iso,
            },
            extra_headers={"Prefer": "return=minimal"},
        )
    except Exception as e:
        logger.warning(f"[AUTOMATIONS_WORKER] Chat history log skipped for {auto_id}: {e}")


def execute_single_automation(automation: Dict[str, Any], is_test: bool = False) -> Dict[str, Any]:
    """
    Executes a single scheduled automation:
    Verifies Pro, checks quota, generates AI response, sends to Telegram, and logs to DB.
    Note: Manual test runs (is_test=True) do NOT set last_run_date, so they never block
    the user's daily scheduled slot on the same day.
    """
    auto_id = automation["id"]
    user_id = automation["user_id"]
    name = automation.get("name") or "استشارة مجدولة"
    prompt = automation.get("prompt") or ""
    scheduled_time = automation.get("scheduled_time") or "08:30"
    today_cairo = get_cairo_time().strftime("%Y-%m-%d")

    # 0. Distributed Atomic Claim: Ensure only ONE worker/instance executes this automation today
    # Prevents duplicate runs between HF Space and local dev servers running concurrently
    if not is_test:
        claim_patch = _supabase_request(
            f"scheduled_chat_automations?id=eq.{auto_id}&or=(last_run_date.is.null,last_run_date.neq.{today_cairo})&select=id",
            method="PATCH",
            payload={
                "last_run_date": today_cairo,
                "last_run_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "last_status": "running",
            },
        )
        if not claim_patch or not isinstance(claim_patch, list) or len(claim_patch) == 0:
            logger.info(f"[AUTOMATIONS_WORKER] Automation {auto_id} was already claimed/executed today ({today_cairo}). Skipping duplicate run.")
            return {"ok": True, "reason": "already_claimed_today"}

    # 1. Pro check
    if not _is_user_pro(user_id):
        logger.info(f"[AUTOMATIONS_WORKER] Skipped {auto_id}: user {user_id} is not Pro.")
        _supabase_request(
            f"scheduled_chat_automations?id=eq.{auto_id}",
            method="PATCH",
            payload={"last_status": "pro_required", "last_error": "User does not have an active Pro subscription"},
        )
        return {"ok": False, "reason": "pro_required"}

    # 2. Resolve Telegram Target
    chat_id = _resolve_user_telegram(user_id, automation.get("telegram_chat_id"))
    if not chat_id:
        logger.info(f"[AUTOMATIONS_WORKER] Skipped {auto_id}: user {user_id} has no Telegram connected.")
        _supabase_request(
            f"scheduled_chat_automations?id=eq.{auto_id}",
            method="PATCH",
            payload={"last_status": "no_telegram_linked", "last_error": "No Telegram chat or channel linked to profile"},
        )
        return {"ok": False, "reason": "no_telegram_linked"}

    # 3. Quota check & deduction
    quota_allowed = _consume_user_quota(user_id, today_cairo)
    if not quota_allowed:
        logger.info(f"[AUTOMATIONS_WORKER] Skipped {auto_id}: user {user_id} monthly quota exceeded.")
        msg = (
            f"⚠️ **تنبيه أرتورو AI للاستشارة المجدولة ({name}):**\n\n"
            f"حان موعد استشارتك المجدولة الساعة `{scheduled_time}` بتوقيت القاهرة، ولكن تم استهلاك باقتك الشهرية من الرسائل بالكامل (350 رسالة).\n\n"
            f"لتجديد الرصيد أو الترقية: [اضغط هنا](https://egxbots.com/pricing)\n"
            f"لإدارة مواعيد استشاراتك: [الملف الشخصي](https://egxbots.com/profile)"
        )
        send_telegram_direct(chat_id, msg)
        patch_payload: Dict[str, Any] = {
            "last_status": "quota_exceeded",
            "last_error": "Monthly quota exhausted",
        }
        if not is_test:
            patch_payload["last_run_date"] = today_cairo
        _supabase_request(
            f"scheduled_chat_automations?id=eq.{auto_id}",
            method="PATCH",
            payload=patch_payload,
        )
        return {"ok": False, "reason": "quota_exceeded"}

    # 4. Generate AI consultation
    user_name = automation.get("name") or "المستثمر"
    reply_text = _generate_ai_consultation(prompt, user_name, user_id=user_id)

    # 5. Format Telegram Message
    telegram_message = (
        f"🤖 **استشارة أرتورو AI المجدولة: {name}**\n"
        f"⏰ **الموعد:** `{scheduled_time}` بتوقيت القاهرة {('(تجربة فورية)' if is_test else '')}\n"
        f"📌 **السؤال:** _{prompt}_\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"{reply_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 _تم خصم رسالة واحدة من كوتتك الشهرية | للتحكم وإدارة المواعيد: [egxbots.com/profile](https://egxbots.com/profile)_"
    )

    # 6. Deliver to Telegram
    sent = send_telegram_direct(chat_id, telegram_message)

    # 7. Record in DB (only set last_run_date on real scheduled runs that succeeded)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    status = "success" if sent else "telegram_delivery_failed"
    err = None if sent else "Failed to send message to Telegram"

    update_payload: Dict[str, Any] = {
        "last_run_at": now_iso,
        "last_status": status,
        "last_error": err,
    }
    if not is_test and sent:
        update_payload["last_run_date"] = today_cairo

    _supabase_request(
        f"scheduled_chat_automations?id=eq.{auto_id}",
        method="PATCH",
        payload=update_payload,
    )

    # 8. Log to chat history with valid UUID session
    _log_automation_to_chat_history(auto_id, user_id, name, prompt, reply_text, now_iso)

    return {"ok": sent, "status": status, "chat_id": chat_id, "error": err}


def _was_modified_after_schedule_today(auto: Dict[str, Any], now_cairo: dt.datetime, sh: int, sm: int) -> bool:
    """
    Checks if the automation was newly created or edited TODAY after its scheduled_time.
    Prevents an automation created at 09:00 with default time 08:30 from firing immediately as a false catch-up.
    """
    raw_ts = auto.get("updated_at") or auto.get("created_at")
    if not raw_ts:
        return False
    try:
        mod_dt = dt.datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00")).astimezone(CAIRO_TZ)
        if mod_dt.date() != now_cairo.date():
            return False
        sched_minutes = sh * 60 + sm
        mod_minutes = mod_dt.hour * 60 + mod_dt.minute
        return mod_minutes > sched_minutes + 1
    except Exception:
        return False


def _worker_loop() -> None:
    """Continuous minute-level scheduler loop."""
    logger.info("[AUTOMATIONS_WORKER] Background Scheduler Thread started.")
    time.sleep(5)  # initial brief settle
    sync_automations_cache()

    while not _stop_event.is_set():
        try:
            now_cairo = get_cairo_time()
            current_time_str = now_cairo.strftime("%H:%M")
            today_date_str = now_cairo.strftime("%Y-%m-%d")
            cairo_weekday = now_cairo.weekday()  # Sun=6, Mon=0, Tue=1, Wed=2, Thu=3, Fri=4, Sat=5

            # Refresh cache periodically
            if time.time() - _last_cache_refresh > _CACHE_TTL_SECONDS:
                sync_automations_cache()

            # Find matching automations
            with _cache_lock:
                automations = list(_cached_automations)

            for auto in automations:
                if not auto.get("is_active"):
                    continue

                # Check if already ran today
                if auto.get("last_run_date") == today_date_str:
                    continue

                # Check days of week
                days_type = auto.get("days_of_week") or "trading_days"
                if days_type == "trading_days" and cairo_weekday not in {6, 0, 1, 2, 3}:
                    continue

                sched_time = str(auto.get("scheduled_time") or "").strip()
                if sched_time != current_time_str:
                    # Catch-up window: up to 90 minutes if HF Space restarted or woke up after schedule
                    try:
                        sh, sm = map(int, sched_time.split(":"))
                        ch, cm = now_cairo.hour, now_cairo.minute
                        diff_minutes = (ch * 60 + cm) - (sh * 60 + sm)
                        if diff_minutes < 0:
                            diff_minutes += 1440
                        if not (0 <= diff_minutes <= 90):
                            continue
                        if diff_minutes > 1 and _was_modified_after_schedule_today(auto, now_cairo, sh, sm):
                            continue
                    except Exception:
                        continue

                # Run automation in dedicated background thread
                logger.info(f"[AUTOMATIONS_WORKER] Triggering scheduled automation: {auto.get('id')} - {auto.get('name')}")
                # Mark in memory to prevent re-triggering this minute
                auto["last_run_date"] = today_date_str
                threading.Thread(target=execute_single_automation, args=(auto, False), daemon=True).start()

        except Exception as e:
            logger.error(f"[AUTOMATIONS_WORKER] Worker loop error: {e}")

        # Sleep until the next 30-second boundary
        time.sleep(30)


def start_scheduled_automations_worker() -> None:
    """Starts the background worker thread if not already running."""
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="ScheduledAutomationsWorker")
    _worker_thread.start()
    logger.info("[AUTOMATIONS_WORKER] Worker thread spawned.")


def stop_scheduled_automations_worker() -> None:
    """Stops the background worker thread gracefully."""
    _stop_event.set()
    if _worker_thread is not None:
        _worker_thread.join(timeout=3)
    logger.info("[AUTOMATIONS_WORKER] Worker thread stopped.")
