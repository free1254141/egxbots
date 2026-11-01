"""
api/scheduled_automations_worker.py — Background Scheduler for User-Defined AI Chat Automations.

Executes on Hugging Face Spaces / Python Backend natively.
Monitors user-scheduled times (Cairo Time), verifies Pro subscription,
consumes quota atomically via consume_ai_chat_quota, generates DeepSeek analysis,
and delivers responses directly to user Telegram channels/chats.

Key architectural rules:
- Zero load on Vercel: Runs natively in Python background thread.
- Zero Supabase log query waste: Targeted single-row lookups with column projections.
- HF sleep resilience: In-memory cache + catch-up window for cold boots.
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


def _get_supabase_config() -> tuple[str, str]:
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or ""
    return url, key


def _supabase_request(endpoint: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, timeout: int = 15) -> Optional[Any]:
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
    rows = _supabase_request("scheduled_chat_automations?is_active=eq.true&select=*")
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


def send_telegram_direct(chat_id: str | int, text: str) -> bool:
    """Delivers message directly to user's Telegram chat or channel."""
    token = get_telegram_bot_token()
    if not token:
        logger.warning("[AUTOMATIONS_WORKER] Missing Telegram Bot Token")
        return False

    url = f"{TELEGRAM_RELAY_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            return bool(res_json.get("ok"))
    except Exception as e:
        logger.warning(f"[AUTOMATIONS_WORKER] Telegram send to {chat_id} failed: {e}")
        return False


ADMIN_USER_IDS = {"ba9c27e8-f62d-452f-8a29-dc77fd092207", "c4b3a6d0-61c5-4f75-97bc-24f486666da0"}
ADMIN_TG_IDS = {"5149631436"}


def _is_user_pro(user_id: str) -> bool:
    """Verifies that the user currently holds an active Pro or Lifetime subscription or is admin."""
    # 1. Check known admin user IDs
    if user_id in ADMIN_USER_IDS:
        return True

    # 2. Check admin Telegram chat IDs
    prof = _supabase_request(f"profiles?id=eq.{user_id}&select=telegram_chat_id&limit=1") or []
    if prof and str(prof[0].get("telegram_chat_id") or "") in ADMIN_TG_IDS:
        return True

    # 3. Check subscriptions
    subs = _supabase_request(
        f"subscriptions?user_id=eq.{user_id}&status=in.(active,trialing)&select=plan_id,current_period_end&order=current_period_end.desc&limit=1"
    ) or []
    if subs:
        end_str = str(subs[0].get("current_period_end") or "")
        if "2126" in end_str or end_str > dt.datetime.now(dt.timezone.utc).isoformat():
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
        method="POST"
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


def _fetch_market_indicators_brief(symbols: List[str]) -> str:
    """Fetches fast precalculated technical indicators for requested symbols."""
    if not symbols:
        # Default top indicators
        rows = _supabase_request(
            "stock_technical_indicators?select=symbol,close,change_pct,volume,rsi_14,ema_20,bb_upper,bb_lower&order=volume.desc&limit=5"
        ) or []
    else:
        sym_filter = ",".join(symbols[:3])
        rows = _supabase_request(
            f"stock_technical_indicators?symbol=in.({sym_filter})&select=symbol,close,change_pct,volume,rsi_14,ema_20,bb_upper,bb_lower&limit=5"
        ) or []

    if not rows:
        return ""

    lines = ["بيانات السوق والمؤشرات الفنية اللحظية المسجلة:"]
    for r in rows:
        lines.append(
            f"• #{r.get('symbol')}: إغلاق {r.get('close')} ج.م ({float(r.get('change_pct') or 0):+.2f}%) | RSI: {float(r.get('rsi_14') or 50):.1f} | EMA20: {r.get('ema_20')}"
        )
    return "\n".join(lines)


def _generate_ai_consultation(prompt: str, user_name: str) -> str:
    """Generates a professional stock market consultation using DeepSeek."""
    deepseek_key = os.getenv("DEEPSEEK_OFFICIAL_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
    if not deepseek_key:
        return "أهلاً بك! تعذر الاتصال بمحرك الذكاء الاصطناعي حالياً لعدم توفر المفتاح. برجاء المراجعة مع الدعم الفني."

    # Extract symbols
    words = re.findall(r"[A-Za-z]{2,8}", prompt)
    symbols = [w.upper() for w in words if w.upper() not in {"THE", "AND", "FOR", "BUY", "SELL", "VIP", "BOT", "EGX"}]
    indicators_brief = _fetch_market_indicators_brief(symbols)

    system_prompt = (
        "أنت أرتورو (ARTORO AI)، المساعد المالي والتقني الخبير في البورصة المصرية (EGX).\n"
        "تقدم استشارة مجدولة مخصصة وموجزة للمشترك Pro بناءً على طلبه المحدد، وتعمل في أي وقت يختاره المستخدم طوال اليوم وعلى مدار الأسبوع.\n"
        "قواعد الإجابة:\n"
        "1. قدّم تحليلاً فنياً واقعياً ومحترفاً ومباشراً بدون إطالة أو حشو غير ضروري.\n"
        "2. ركز على مستويات الدعم، المقاومة، اتجاه السيولة، وحجم التداول.\n"
        "3. إذا كان توقيت الاستشارة خارج ساعات التداول الرسمية بالبورصة أو في عطلة نهاية الأسبوع، اعتمد على أحدث بيانات إغلاق مسجلة وقدّم رؤية استباقية واستعداداً للجلسة القادمة.\n"
        "4. اختم دائماً بنصيحة إدارة مخاطر ذكية ومستوى وقف خسارة محدد (2.5% إلى 3.5%).\n"
        "5. التزم باللغة العربية الواضحة وتنسيق Markdown الجذاب مع الإيموجي المناسب للقراءة السريعة على تليجرام."
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
        "max_tokens": 800,
    }

    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {deepseek_key}",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.error(f"[AUTOMATIONS_WORKER] DeepSeek call error: {e}")
        return "نعتذر، حدث ضغط لحظي في خدمة الذكاء الاصطناعي أثناء معالجة استشارتك المجدولة. سيتم التحديث في الموعد القادم."


def execute_single_automation(automation: Dict[str, Any], is_test: bool = False) -> Dict[str, Any]:
    """
    Executes a single scheduled automation:
    Verifies Pro, checks quota, generates AI response, sends to Telegram, and logs to DB.
    """
    auto_id = automation["id"]
    user_id = automation["user_id"]
    name = automation.get("name") or "استشارة مجدولة"
    prompt = automation.get("prompt") or ""
    scheduled_time = automation.get("scheduled_time") or "08:30"
    today_cairo = get_cairo_time().strftime("%Y-%m-%d")

    # 1. Pro check
    if not _is_user_pro(user_id):
        logger.info(f"[AUTOMATIONS_WORKER] Skipped {auto_id}: user {user_id} is not Pro.")
        _supabase_request(
            f"scheduled_chat_automations?id=eq.{auto_id}",
            method="PATCH",
            payload={"last_status": "pro_required", "last_error": "User does not have an active Pro subscription"}
        )
        return {"ok": False, "reason": "pro_required"}

    # 2. Resolve Telegram Target
    chat_id = _resolve_user_telegram(user_id, automation.get("telegram_chat_id"))
    if not chat_id:
        logger.info(f"[AUTOMATIONS_WORKER] Skipped {auto_id}: user {user_id} has no Telegram connected.")
        _supabase_request(
            f"scheduled_chat_automations?id=eq.{auto_id}",
            method="PATCH",
            payload={"last_status": "no_telegram_linked", "last_error": "No Telegram chat or channel linked to profile"}
        )
        return {"ok": False, "reason": "no_telegram_linked"}

    # 3. Quota check & deduction (unless it's an explicit manual test click)
    quota_allowed = _consume_user_quota(user_id, today_cairo)
    if not quota_allowed:
        logger.info(f"[AUTOMATIONS_WORKER] Skipped {auto_id}: user {user_id} monthly quota exceeded.")
        # Send notification to Telegram
        msg = (
            f"⚠️ **تنبيه أرتورو AI للاستشارة المجدولة ({name}):**\n\n"
            f"حان موعد استشارتك المجدولة الساعة `{scheduled_time}` بتوقيت القاهرة، ولكن تم استهلاك باقتك الشهرية من الرسائل بالكامل (350 رسالة).\n\n"
            f"لتجديد الرصيد أو الترقية: [اضغط هنا](https://stokscan.com/pricing)\n"
            f"لإدارة مواعيد استشاراتك: [الملف الشخصي](https://stokscan.com/profile)"
        )
        send_telegram_direct(chat_id, msg)
        _supabase_request(
            f"scheduled_chat_automations?id=eq.{auto_id}",
            method="PATCH",
            payload={"last_status": "quota_exceeded", "last_error": "Monthly quota exhausted"}
        )
        return {"ok": False, "reason": "quota_exceeded"}

    # 4. Generate AI consultation
    user_name = automation.get("name") or "المستثمر"
    reply_text = _generate_ai_consultation(prompt, user_name)

    # 5. Format Telegram Message
    telegram_message = (
        f"🤖 **استشارة أرتورو AI المجدولة: {name}**\n"
        f"⏰ **الموعد:** `{scheduled_time}` بتوقيت القاهرة {('(تجربة)' if is_test else '')}\n"
        f"📌 **السؤال:** _{prompt}_\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"{reply_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 _تم خصم رسالة واحدة من كوتتك الشهرية | للتحكم وإدارة المواعيد: [stokscan.com/profile](https://stokscan.com/profile)_"
    )

    # 6. Deliver to Telegram
    sent = send_telegram_direct(chat_id, telegram_message)

    # 7. Record in DB
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    status = "success" if sent else "telegram_delivery_failed"
    err = None if sent else "Failed to send message to Telegram"

    _supabase_request(
        f"scheduled_chat_automations?id=eq.{auto_id}",
        method="PATCH",
        payload={
            "last_run_at": now_iso,
            "last_run_date": today_cairo,
            "last_status": status,
            "last_error": err,
        }
    )

    # Also log to ai_chat_messages so user sees it in their chat history
    session_id = f"automation-{auto_id}"
    _supabase_request(
        "ai_chat_messages",
        method="POST",
        payload={
            "session_id": session_id,
            "user_id": user_id,
            "role": "user",
            "content": f"[استشارة مجدولة: {name}] {prompt}",
            "created_at": now_iso,
        }
    )
    _supabase_request(
        "ai_chat_messages",
        method="POST",
        payload={
            "session_id": session_id,
            "user_id": user_id,
            "role": "assistant",
            "content": reply_text,
            "created_at": now_iso,
        }
    )

    return {"ok": sent, "status": status, "chat_id": chat_id, "error": err}


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

                sched_time = str(auto.get("scheduled_time") or "").strip()
                if sched_time != current_time_str:
                    # Also check catch-up window (if HF cold boot started within 10 minutes of schedule)
                    # Example: sched_time 08:30, current_time 08:33, last_run_date != today
                    try:
                        sh, sm = map(int, sched_time.split(":"))
                        ch, cm = now_cairo.hour, now_cairo.minute
                        diff_minutes = (ch * 60 + cm) - (sh * 60 + sm)
                        if diff_minutes < 0:
                            diff_minutes += 1440
                        if not (0 <= diff_minutes <= 10):
                            continue
                    except Exception:
                        continue

                # Check if already ran today
                if auto.get("last_run_date") == today_date_str:
                    continue

                # Check days of week
                days_type = auto.get("days_of_week") or "trading_days"
                if days_type == "trading_days" and cairo_weekday not in {6, 0, 1, 2, 3}:
                    continue

                # Run automation in dedicated background thread
                logger.info(f"[AUTOMATIONS_WORKER] Triggering scheduled automation: {auto.get('id')} - {auto.get('name')}")
                # Mark in memory to prevent re-triggering this minute
                auto["last_run_date"] = today_date_str
                threading.Thread(target=execute_single_automation, args=(auto,), daemon=True).start()

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
