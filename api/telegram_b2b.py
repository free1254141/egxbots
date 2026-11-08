"""
B2B Telegram Group Bot Licensing Handler.
Enables channel and VIP group owners to add the EGX BOTS Telegram bot to their groups,
answering member stock questions with group daily limits, anti-spam cooldowns,
and custom signature branding.
"""

import html
import os
import re
import threading
from typing import Any, Dict, Optional, Tuple

import requests

from api.stock_ai import _init_supabase, supabase

_B2B_SEMAPHORE = threading.BoundedSemaphore(int(os.getenv("TELEGRAM_B2B_MAX_CONCURRENCY", "8") or 8))
_PROCESSED_B2B_EVENTS: Dict[str, float] = {}
_DEDUP_LOCK = threading.Lock()

# Supported trigger command prefixes
TRIGGER_COMMANDS = (
    "/ask",
    "/analyze",
    "/bot",
    "/stock",
    "/compare",
    "/artoro",
    "!سهم",
    "/help",
    "/start",
    "/price",
    "/fairvalue",
)


def _mark_b2b_processed(event_key: str, window_seconds: float = 300.0) -> bool:
    """Return True if this event was NOT processed yet (and marks it processed)."""
    import time
    now = time.time()
    with _DEDUP_LOCK:
        # Prune old entries
        cutoff = now - window_seconds
        stale = [k for k, t in _PROCESSED_B2B_EVENTS.items() if t < cutoff]
        for k in stale:
            _PROCESSED_B2B_EVENTS.pop(k, None)

        if event_key in _PROCESSED_B2B_EVENTS:
            return False
        _PROCESSED_B2B_EVENTS[event_key] = now
        return True


def _call_telegram_api(token: str, method: str, payload: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    """Helper to dispatch Telegram Bot API calls."""
    try:
        url = f"https://api.telegram.org/bot{token}/{method}"
        resp = requests.post(url, json=payload, timeout=timeout)
        return resp.json() if resp.ok else (resp.json() if resp.status_code < 500 else {})
    except Exception as exc:
        print(f"[TELEGRAM_B2B] Telegram API call {method} error: {exc}")
        return {}


def is_explicit_group_trigger(text: str, msg: Dict[str, Any], bot_username: str = "") -> Tuple[bool, str]:
    """
    Check if a message in a group or supergroup explicitly triggers the bot.
    Returns (is_triggered, cleaned_query_text).
    """
    raw_text = (text or "").strip()
    if not raw_text:
        return False, ""

    expected_username = (bot_username or os.getenv("TELEGRAM_BOT_USERNAME") or "egxbots_bot").lstrip("@").lower()

    # 1. Mention trigger: @egxbots_bot ...
    mention_pattern = re.compile(rf"@({expected_username}|artoro_ai_bot|artorobot)\b", re.IGNORECASE)
    has_mention = bool(mention_pattern.search(raw_text))

    # 2. Command trigger: /ask ..., /analyze ...
    words = raw_text.split()
    first_word = words[0].lower() if words else ""
    first_cmd = first_word.split("@")[0]  # Handles /ask@egxbots_bot
    has_cmd = any(first_cmd == cmd for cmd in TRIGGER_COMMANDS)

    # 3. Reply trigger: user replied directly to one of the bot's messages
    reply_to = msg.get("reply_to_message") or {}
    reply_from_bot = bool((reply_to.get("from") or {}).get("is_bot"))

    if not (has_mention or has_cmd or reply_from_bot):
        return False, ""

    # Clean the query text
    cleaned = raw_text
    if has_mention:
        cleaned = mention_pattern.sub("", cleaned).strip()

    if has_cmd:
        # Strip the first command token
        cmd_tokens = cleaned.split(maxsplit=1)
        cleaned = cmd_tokens[1].strip() if len(cmd_tokens) > 1 else ""

    return True, cleaned


def handle_b2b_group_message(
    bot_token: str,
    chat_id: int,
    text: str,
    msg: Dict[str, Any],
    raw_update: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Main entrypoint for B2B Telegram group / channel message handling.
    Returns True if handled (or ignored as general chatter).
    """
    msg_id = msg.get("message_id")
    thread_id = msg.get("message_thread_id")
    from_obj = msg.get("from") or {}

    # Ignore bot-generated messages
    if from_obj.get("is_bot"):
        return True

    user_id = int(from_obj.get("id") or 0)
    user_name = str(from_obj.get("first_name") or from_obj.get("username") or "عضو المجموعة").strip()

    # 1. Check if the message is an explicit trigger for the bot
    triggered, clean_query = is_explicit_group_trigger(text, msg)
    if not triggered:
        # Strictly ignore non-triggered group chatter
        return False

    # Prevent processing duplicate update delivery
    if msg_id and not _mark_b2b_processed(f"b2b:{chat_id}:{msg_id}"):
        return True

    _init_supabase()
    if not supabase:
        print("[TELEGRAM_B2B] Supabase not initialized; skipping B2B message.")
        return False

    # 2. Check & consume B2B group quota atomically via RPC
    try:
        rpc_res = supabase.rpc(
            "check_and_consume_b2b_group_quota",
            {"p_chat_id": chat_id, "p_user_id": user_id},
        ).execute()
        result = rpc_res.data or {}
    except Exception as exc:
        print(f"[TELEGRAM_B2B] Error checking B2B quota: {exc}")
        result = {"allowed": False, "reason": "db_error"}

    allowed = bool(result.get("allowed"))
    reason = str(result.get("reason") or "")

    # 3. Handle unlicensed group
    if not allowed and reason == "not_licensed":
        welcome_unlicensed = (
            "🤖 <b>مرحباً بكم في منصة EGX BOTS للبورصة المصرية!</b>\n\n"
            "لتفعيل هذا البوت داخل المجموعة والرد الآلي على استفسارات الأعضاء برخصة رسمية وتوقيع مخصص باسم قناتكم:\n\n"
            "• 🔗 <b>صفحة باقات أصحاب القنوات والشركات:</b>\n"
            "https://egxbots.com/pricing?mode=b2b\n\n"
            "• 💬 <b>أو تواصل مباشرة مع فريق الإدارة عبر واتساب:</b>\n"
            "https://wa.me/201024359109?text=استفسار+عن+تفعيل+بوت+التليجرام+للمجموعات\n\n"
            "<i>(البوت يحلل أكثر من 280 سهماً مصرياً ويوفر إشارات الدعم والمقاومة، السعر العادل، ورادار التجميع)</i>"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "💳 باقات ترخيص البوت B2B", "url": "https://egxbots.com/pricing?mode=b2b"},
                    {"text": "💬 واتساب الدعم الفني", "url": "https://wa.me/201024359109"},
                ]
            ]
        }
        _call_telegram_api(
            bot_token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": welcome_unlicensed,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_to_message_id": msg_id,
                "message_thread_id": thread_id,
                "reply_markup": keyboard,
            },
        )
        return True

    # 4. Handle daily group quota reached
    if not allowed and reason == "group_daily_limit_reached":
        limit = result.get("daily_limit", 50)
        limit_msg = (
            f"🎯 <b>عذراً، وصلت المجموعة للحد اليومي المخصص ({limit}/{limit} استفسار).</b>\n\n"
            "يتجدد الرصيد تلقائياً مع بداية جلسة الغد في تمام 00:00 بتوقيت القاهرة.\n\n"
            "👑 <i>لترقية باقة المجموعة لسعة أكبر، يمكن لمالك القناة الترقية من لوحة التحكم أو التواصل مع إدارة المنصة.</i>"
        )
        _call_telegram_api(
            bot_token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": limit_msg,
                "parse_mode": "HTML",
                "reply_to_message_id": msg_id,
                "message_thread_id": thread_id,
            },
        )
        return True

    # 5. Handle member cooldown
    if not allowed and reason == "member_cooldown":
        cooldown = result.get("cooldown_remaining", 90)
        cooldown_msg = (
            f"⏳ <b>يرجى الانتظار {cooldown} ثانية</b> يا {html.escape(user_name)} قبل طرح استفسار جديد "
            "لإتاحة الفرصة لباقي أعضاء المجموعة."
        )
        _call_telegram_api(
            bot_token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": cooldown_msg,
                "parse_mode": "HTML",
                "reply_to_message_id": msg_id,
                "message_thread_id": thread_id,
            },
        )
        return True

    # 6. Handle member daily limit reached (15 queries)
    if not allowed and reason == "member_daily_limit_reached":
        member_limit_msg = (
            f"⚠️ <b>عفواً يا {html.escape(user_name)}:</b> لقد وصلت للحد الأقصى المسموح للعضو الواحد اليوم (15 استفساراً) "
            "لإتاحة الرصيد اليومي لباقي أعضاء المجموعة."
        )
        _call_telegram_api(
            bot_token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": member_limit_msg,
                "parse_mode": "HTML",
                "reply_to_message_id": msg_id,
                "message_thread_id": thread_id,
            },
        )
        return True

    if not allowed:
        return True

    # 7. Allowed! Process the query
    custom_signature = str(result.get("custom_signature") or "⚡ تحليلات خاصة بقناتنا بالتعاون مع EGX BOTS").strip()
    daily_used = result.get("daily_used", 1)
    daily_limit = result.get("daily_limit", 50)

    # If the user didn't write a question (e.g. just said @egxbots_bot or /start /help)
    if not clean_query:
        help_text = (
            f"🤖 <b>أهلاً بك يا {html.escape(user_name)} في بوت التحليل الذكي للبورصة المصرية!</b>\n\n"
            "<b>كيف تسأل البوت؟</b>\n"
            "• <code>@egxbots_bot حلل سهم فوري</code>\n"
            "• <code>/ask رأيك في طلعت مصطفى ودعومه ومقاوماته</code>\n"
            "• <code>/ask مقارنة بين السويدي وحديد عز</code>\n"
            "• <code>/ask ملخص السوق وأقوى أسهم التجميع اليوم</code>\n\n"
            f"📊 <i>رصيد المجموعة اليوم: استُهلك {daily_used} من {daily_limit} استفساراً.</i>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{html.escape(custom_signature)}"
        )
        _call_telegram_api(
            bot_token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": help_text,
                "parse_mode": "HTML",
                "reply_to_message_id": msg_id,
                "message_thread_id": thread_id,
            },
        )
        return True

    # Send temporary typing action
    _call_telegram_api(
        bot_token,
        "sendChatAction",
        {"chat_id": chat_id, "action": "typing", "message_thread_id": thread_id},
        timeout=3,
    )

    # Spawn background thread to query agentic pipeline and reply
    threading.Thread(
        target=_process_and_send_b2b_reply,
        args=(bot_token, chat_id, thread_id, msg_id, user_id, user_name, clean_query, custom_signature, daily_used, daily_limit),
        daemon=True,
    ).start()

    return True


def _process_and_send_b2b_reply(
    bot_token: str,
    chat_id: int,
    thread_id: Optional[int],
    reply_to_msg_id: int,
    user_id: int,
    user_name: str,
    query_text: str,
    custom_signature: str,
    daily_used: int,
    daily_limit: int,
) -> None:
    """Execute AI pipeline and post formatted answer with custom signature footer."""
    acquired = _B2B_SEMAPHORE.acquire(timeout=60)
    try:
        from api.telegram_vip_chat import call_web_vip_chat_api, format_pipeline_reply_for_telegram

        api_res = call_web_vip_chat_api(
            {
                "action": "chat",
                "message": query_text,
                "telegram_user_id": user_id,
                "telegram_username": user_name,
                "chat_source": "telegram_b2b",
                "bypass_quota": True,
            },
            timeout=70,
        )

        reply_raw = str(api_res.get("reply") or "").strip()
        if not reply_raw:
            reply_raw = "عذراً، حدث خطأ أثناء تحليل السهم. يرجى إعادة المحاولة."

        # Format tables and markdown for Telegram HTML
        formatted = format_pipeline_reply_for_telegram(
            reply_text=reply_raw,
            tables=api_res.get("tables") or [],
            user_name=user_name,
            tg_user_id=user_id,
            is_pro=True,
            used=daily_used,
            limit=daily_limit,
            remaining=max(0, daily_limit - daily_used),
            period="daily",
        )

        # Append custom signature branding footer
        signature_footer = (
            f"\n\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ <b>{html.escape(custom_signature)}</b>\n"
            f"🤖 <i>مدعوم بالذكاء الاصطناعي من EGX BOTS (<a href=\"https://egxbots.com\">egxbots.com</a>)</i>"
        )
        final_message = formatted + signature_footer

        _call_telegram_api(
            bot_token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": final_message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_to_message_id": reply_to_msg_id,
                "message_thread_id": thread_id,
            },
        )
    except Exception as exc:
        print(f"[TELEGRAM_B2B] Failed to process and reply: {exc}")
        _call_telegram_api(
            bot_token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": f"⚠️ عذراً يا {html.escape(user_name)}، تعذر إتمام التحليل الفني حالياً. يرجى المحاولة لاحقاً.",
                "parse_mode": "HTML",
                "reply_to_message_id": reply_to_msg_id,
                "message_thread_id": thread_id,
            },
        )
    finally:
        if acquired:
            _B2B_SEMAPHORE.release()
