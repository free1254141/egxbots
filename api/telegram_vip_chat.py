"""
Telegram VIP Chat Room & ARTORO Interactive Hub (https://t.me/egxbots/1652).

Connects the public/VIP Telegram chat topic directly to the website's Agentic AI
Pipeline (/api/telegram/vip-chat), enforcing per-user Free (5/day) and Pro (350/month)
quotas, preserving multi-turn session state & memory, providing 1-click quick tools
and interactive prompts (ForceReply + state), and displaying private modal alert
dialogs + pricing upgrade cards when a user reaches their plan limit.
"""
from __future__ import annotations

import html
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from api.web_origin import get_web_origin

# Default Group & Topic from https://t.me/egxbots/1652 -> -1002083067817_1652
DEFAULT_VIP_GROUP_ID = "-1002083067817"
DEFAULT_VIP_TOPIC_ID = 1652

# In-memory deduplication & pending prompt state (backed by Supabase telegram_vip_chat_state)
_DEDUP_LOCK = threading.Lock()
_PROCESSED_EVENTS: Dict[str, float] = {}
_PENDING_PROMPTS: Dict[Tuple[str, int], Dict[str, Any]] = {}


def get_vip_group_id() -> str:
    raw = os.getenv("TELEGRAM_VIP_CHAT_ID", DEFAULT_VIP_GROUP_ID).strip()
    if "_" in raw:
        raw = raw.split("_", 1)[0]
    return raw or DEFAULT_VIP_GROUP_ID


def get_vip_topic_id() -> Optional[int]:
    raw_env = os.getenv("TELEGRAM_VIP_CHAT_THREAD_ID", "").strip()
    if raw_env.isdigit():
        return int(raw_env)
    raw_group = os.getenv("TELEGRAM_VIP_CHAT_ID", "").strip()
    if "_" in raw_group:
        _, thread_part = raw_group.split("_", 1)
        if thread_part.isdigit():
            return int(thread_part)
    return DEFAULT_VIP_TOPIC_ID


def _pricing_url() -> str:
    origin = (get_web_origin() or "https://egxbots.com").rstrip("/")
    if "localhost" in origin or "127.0.0.1" in origin:
        origin = "https://egxbots.com"
    return f"{origin}/pricing"


def _profile_url() -> str:
    origin = (get_web_origin() or "https://egxbots.com").rstrip("/")
    if "localhost" in origin or "127.0.0.1" in origin:
        origin = "https://egxbots.com"
    return f"{origin}/profile"


def _private_bot_url() -> str:
    bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "egxbots_bot").strip().lstrip("@") or "egxbots_bot"
    return f"https://t.me/{bot_username}?start=artoro_chat"


def _topic_url() -> str:
    return "https://t.me/egxbots/1652"


def build_vip_chat_keyboard(is_private: bool = False) -> Dict[str, Any]:
    """Sleek interactive Inline Keyboard for summoning ARTORO and running quick tools."""
    rows: List[List[Dict[str, Any]]] = [
        [
            {"text": "🤖 اسأل أرتورو", "callback_data": "vip_ask_free"},
            {"text": "🔍 حلل سهم", "callback_data": "vip_ask_stock"},
            {"text": "⚖️ قارن سهمين", "callback_data": "vip_ask_compare"},
        ],
        [
            {"text": "📈 ملخص السوق وأقوى الأسهم", "callback_data": "vip_tool_market"},
            {"text": "🧲 أسهم التجميع والسيولة", "callback_data": "vip_tool_accum"},
        ],
        [
            {"text": "⚡ المسح الفني", "callback_data": "vip_tool_scan"},
            {"text": "🎯 التوصيات المفتوحة (PRO)", "callback_data": "vip_tool_recs"},
            {"text": "📰 أخبار السوق", "callback_data": "vip_tool_news"},
        ],
        [
            {"text": "💼 تحليل محفظتي", "callback_data": "vip_tool_portfolio"},
            {"text": "📊 رصيدي وخطتي", "callback_data": "vip_my_quota"},
            {"text": "💎 مميزات PRO", "callback_data": "vip_pricing_dialog"},
        ],
    ]
    if is_private:
        rows.append(
            [
                {"text": "💬 غرفة أرتورو العامة", "url": _topic_url()},
                {"text": "🔗 ربط حساب الموقع", "url": _profile_url()},
            ]
        )
    else:
        rows.append(
            [
                {
                    "text": "🔒 تحدث مع أرتورو في شات خاص (@egxbots_bot)",
                    "url": _private_bot_url(),
                }
            ]
        )
    return {"inline_keyboard": rows}


def build_pricing_upgrade_keyboard(is_private: bool = False) -> Dict[str, Any]:
    """Inline keyboard for the Limit Reached / Pro Upgrade dialog card."""
    rows: List[List[Dict[str, Any]]] = [
        [
            {
                "text": "👑 اشترك في PRO الآن — صفحة التسعير (50 ج.م)",
                "url": _pricing_url(),
            }
        ],
        [
            {
                "text": "💎 عرض مميزات PRO في نافذة خاصة",
                "callback_data": "vip_pricing_alert",
            },
            {
                "text": "🔗 ربط حساب الموقع",
                "url": _profile_url(),
            },
        ],
    ]
    if not is_private:
        rows.append(
            [
                {
                    "text": "🔒 فتح شات خاص مع أرتورو (@egxbots_bot)",
                    "url": _private_bot_url(),
                }
            ]
        )
    rows.append(
        [
            {
                "text": "🤖 العودة للوحة أدوات أرتورو",
                "callback_data": "vip_show_panel",
            }
        ]
    )
    return {"inline_keyboard": rows}


# Native Telegram modal popup dialog text (max 200 characters for show_alert=True)
LIMIT_REACHED_ALERT_TEXT = (
    "⚠️ انتهى رصيدك المجاني اليوم (5/5 أسئلة)!\n"
    "💎 اشترك في باقة PRO (50 ج.م للمؤسسين بدلاً من 200):\n"
    "• 350 سؤال ذكي/شهر\n"
    "• توصيات شراء فورية + قناة VIP\n"
    "• متابعة 10 أسهم بمحفظتك\n"
    "👇 اضغط زر التسعير للاشتراك"
)

PRO_ONLY_TOOL_ALERT_TEXT = (
    "🔒 التوصيات المفتوحة اللحظية متاحة لمشتركي PRO فقط!\n"
    "💎 باقة PRO (50 ج.م/شهر للمؤسسين):\n"
    "• إشارات شراء فورية بدون تأخير 15 يوم\n"
    "• 350 سؤال ذكي شهرياً لأرتورو\n"
    "• متابعة 10 أسهم بمحفظتك\n"
    "👇 اشترك الآن من صفحة التسعير"
)

PRICING_FEATURES_ALERT_TEXT = (
    "👑 مميزات باقة EGX Bots PRO:\n"
    "✅ 350 سؤال وتحليل شهرياً مع أرتورو\n"
    "✅ توصيات شراء فورية بدون تأخير 15 يوم\n"
    "✅ دخول قناة توصيات VIP الخاصة\n"
    "✅ محفظة ذكية لمتابعة 10 أسهم\n"
    "🔥 خصم المؤسسين: 50 ج.م/شهر فقط!"
)

ACCOUNT_LINK_ALERT_TEXT = (
    "🔗 لتحليل محفظتك الاستثمارية أو مزامنة اشتراكك:\n"
    "١. افتح صفحة البروفايل في الموقع (egxbots.com/profile)\n"
    "٢. اضغط على زر ربط التليجرام (Connect Telegram Bot)\n"
    "٣. ستتم مزامنة محفظتك وباقتك تلقائياً!"
)


def build_welcome_panel_html(is_private: bool = False, chat_id: Optional[Any] = None) -> str:
    """Build the main ARTORO VIP Chat Hub message (for public topic or private @egxbots_bot DM)."""
    if is_private:
        chat_id_line = f"\n🆔 <b>معرف تليجرام الخاص بك (Chat ID):</b> <code>{chat_id}</code>" if chat_id else ""
        return (
            "🤖 <b>الشات الخاص مع أرتورو — @egxbots_bot</b> 👑\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "أهلاً بك في المحادثة الخاصة المباشرة مع المساعد الذكي <b>ARTORO</b> للبورصة المصرية (EGX)!\n"
            "🔒 <b>خصوصية تامة 100%:</b> جميع أسئلتك، تحليلات أسهمك، ومحفظتك الاستثمارية هنا خاصة بك وحدك ولا يراها أي عضو آخر.\n\n"
            "💬 <b>كيف تستخدم البوت هنا؟</b>\n"
            "• <b>اكتب مباشرةً:</b> يمكنك كتابة سؤالك أو اسم أي سهم مباشرة في الرسائل (مثل: <code>حلل فوري</code> أو <code>قارن بين التجاري الدولي وطلعت مصطفى</code>).\n"
            "• <b>أو استخدم الأزرار السريعة بالأسفل:</b> لتحليل سهم، مقارنة سهمين، ملخص السوق، أسهم التجميع، المسح الفني، التوصيات المفتوحة، وتحليل محفظتك بضغطة واحدة!\n\n"
            "🎫 <b>نظام الباقات والرصيد:</b>\n"
            "• <b>الباقة المجانية:</b> <code>5 أسئلة يومياً</code>.\n"
            "• <b>باقة PRO VIP:</b> <code>350 سؤالاً شهرياً</code> + التوصيات المفتوحة اللحظية + متابعة 10 أسهم بمحفظتك."
            f"{chat_id_line}\n\n"
            "👇 <b>اكتب سؤالك الآن أو اختر الأداة المطلوبة من الأزرار بالأسفل:</b>"
        )

    return (
        "🤖 <b>غرفة أرتورو الذكية — EGX Bots VIP Chat</b> 👑\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "أهلاً بك في الغرفة التفاعلية المباشرة لمساعد الذكاء الاصطناعي <b>ARTORO</b> للبورصة المصرية (EGX)!\n"
        "يعمل أرتورو هنا بنفس محرك الموقع الذكي مع حفظ سياق محادثتك وأدوات التحليل اللحظية.\n\n"
        "💬 <b>نظام الغرفة (دردشة حرة + استدعاء بالأزرار فقط):</b>\n"
        "• يمكنك التحدث والدردشة مع الأعضاء في الغرفة بحرية تامة دون أن يتدخل البوت أو يخصم من رصيدك.\n"
        "• <b>لكي يرد عليك أرتورو هنا:</b> اضغط أولاً على أحد أزرار القائمة بالأسفل (مثل <code>🔍 حلل سهم</code> أو <code>🤖 اسأل أرتورو</code> أو أدوات الضغطة الواحدة).\n\n"
        "🔒 <b>تفضل الخصوصية الكاملة؟ (شات خاص 1-on-1):</b>\n"
        "• إذا كنت لا ترغب في كتابة أسهمك أو محفظتك في الشات العام، اضغط على زر <b>«🔒 تحدث مع أرتورو في شات خاص (@egxbots_bot)»</b> بالأسفل أو راسل البوت <a href=\"https://t.me/egxbots_bot?start=artoro_chat\">@egxbots_bot</a> مباشرة للتحدث معه على انفراد وبخصوصية تامة!\n\n"
        "🎫 <b>نظام الباقات والرصيد:</b>\n"
        "• <b>الباقة المجانية:</b> <code>5 أسئلة يومياً</code>.\n"
        "• <b>باقة PRO VIP:</b> <code>350 سؤالاً شهرياً</code> + التوصيات المفتوحة اللحظية + متابعة 10 أسهم بمحفظتك.\n\n"
        "👇 <b>اختر الأداة المطلوبة من الأزرار بالأسفل أو افتح الشات الخاص:</b>"
    )


def build_pricing_dialog_html(
    user_name: str,
    tg_user_id: int,
    reason: str = "limit_reached",
    used: int = 5,
    limit: int = 5,
) -> str:
    """Build the rich Pricing & Upgrade Dialog card with direct link to /pricing."""
    safe_name = html.escape(user_name or "المستثمر")
    user_mention = f'<a href="tg://user?id={tg_user_id}">{safe_name}</a>'

    if reason == "pro_required":
        header = (
            f"🔒 <b>ميزة حصرية لمشتركي PRO — أهلاً {user_mention}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"أداة <b>التوصيات المفتوحة وإشارات الشراء اللحظية</b> متاحة حصرياً لأعضاء <b>باقة PRO VIP</b>."
        )
    elif reason == "account_link":
        header = (
            f"🔗 <b>ربط حساب الموقع مطلوب — أهلاً {user_mention}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"لقراءة وتحليل أسهم محفظتك الاستثمارية أو تفعيل اشتراكك على التليجرام، يرجى ربط حسابك من صفحة البروفايل في الموقع بضغطة واحدة."
        )
    elif reason == "pricing_info":
        header = (
            f"💎 <b>باقات ومميزات EGX Bots PRO — أهلاً {user_mention}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"ارتقِ بقراراتك الاستثمارية في البورصة المصرية مع التغطية الكاملة واللحظية:"
        )
    else:
        header = (
            f"⚠️ <b>وصلت للحد الأقصى لرصيدك اليومي ({used}/{limit}) — أهلاً {user_mention}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"لقد استهلكت كامل رصيدك المجاني اليوم في سؤال <b>أرتورو AI</b>. "
            f"للاستمرار في التحليل الفوري والوصول الكامل لجميع الأدوات، قم بالترقية إلى <b>باقة PRO VIP</b>:"
        )

    return (
        f"{header}\n\n"
        "👑 <b>مميزات الاشتراك في باقة PRO VIP:</b>\n"
        "1️⃣ <b>350 سؤال وتحليل ذكي شهرياً</b> مع أرتورو في الموقع والتليجرام (بدلاً من 5 يومياً).\n"
        "2️⃣ <b>توصيات وإشارات الشراء اللحظية</b> فور صدورها (بدون تأخير 15 يوماً في الباقة المجانية).\n"
        "3️⃣ <b>دخول قناة التليجرام VIP الخاصة</b> لإشارات الدخول والأهداف ووقف الخسارة.\n"
        "4️⃣ <b>محفظة استثمارية ذكية لمتابعة حتى 10 أسهم</b> مع تحليل مستمر لمراكزك.\n"
        "5️⃣ <b>دعم فني مباشر VIP</b> وأولوية قصوى في الخوادم.\n\n"
        "🔥 <b>عرض المؤسسين الحصري (لأول 100 مشترك):</b>\n"
        "💰 <b>50 ج.م فقط شهرياً</b> (بدلاً من <s>200 ج.م</s>) — الدفع فوري عبر فودافون كاش / إنستاباي / فوري / البطاقات البنكية.\n\n"
        "👇 <b>اضغط على الزر بالأسفل للانتقال إلى صفحة التسعير وتفعيل اشتراكك فوراً:</b>"
    )


def _mark_event_processed(event_key: str) -> bool:
    """Return True if this event has NOT been processed yet, False if duplicate."""
    now = time.time()
    with _DEDUP_LOCK:
        # Clean expired keys older than 120s
        expired = [k for k, ts in _PROCESSED_EVENTS.items() if now - ts > 120]
        for k in expired:
            _PROCESSED_EVENTS.pop(k, None)
        if event_key in _PROCESSED_EVENTS:
            return False
        _PROCESSED_EVENTS[event_key] = now
        return True


def set_local_pending_prompt(chat_id: Any, tg_user_id: int, mode: Optional[str]) -> None:
    key = (str(chat_id), int(tg_user_id))
    with _DEDUP_LOCK:
        if not mode:
            _PENDING_PROMPTS.pop(key, None)
        else:
            _PENDING_PROMPTS[key] = {
                "mode": mode,
                "expires_at": time.time() + 300,
            }


def get_local_pending_prompt(chat_id: Any, tg_user_id: int) -> Optional[str]:
    key = (str(chat_id), int(tg_user_id))
    with _DEDUP_LOCK:
        entry = _PENDING_PROMPTS.get(key)
        if not entry:
            return None
        if time.time() > entry.get("expires_at", 0):
            _PENDING_PROMPTS.pop(key, None)
            return None
        return str(entry.get("mode") or "")


def _call_telegram_api(bot_token: str, method: str, payload: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING") == "true" or os.getenv("TELEGRAM_TEST_MODE") == "true":
        return {
            "ok": True,
            "result": {
                "message_id": 777777,
                "chat": {"id": payload.get("chat_id", 0)},
                "text": payload.get("text", ""),
            },
        }
    relay = os.getenv("TELEGRAM_RELAY_URL", "https://api.telegram.org").strip().rstrip("/")
    bases = [relay, "https://api.telegram.org"] if relay != "https://api.telegram.org" else ["https://api.telegram.org"]
    last_err: Dict[str, Any] = {"ok": False, "description": "No endpoint tried"}
    for base in bases:
        try:
            url = f"{base}/bot{bot_token}/{method}"
            resp = requests.post(url, json=payload, timeout=timeout)
            data = resp.json()
            if data.get("ok"):
                return data
            last_err = data
            # If 4xx error from Telegram (like parse error or user blocked), don't retry on other base
            if 400 <= int(data.get("error_code") or 0) < 500:
                return data
        except Exception as exc:
            last_err = {"ok": False, "description": str(exc)}
    return last_err


def send_vip_message(
    bot_token: str,
    chat_id: Any,
    text: str,
    message_thread_id: Optional[int] = None,
    reply_to_message_id: Optional[int] = None,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """Send an HTML-formatted message (splitting if >3900 chars) and return the last message_id."""
    chunks = _split_html_chunks(text, max_len=3850)
    last_msg_id: Optional[int] = None
    for idx, chunk in enumerate(chunks):
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if message_thread_id is not None:
            payload["message_thread_id"] = int(message_thread_id)
        if idx == 0 and reply_to_message_id is not None:
            payload["reply_to_message_id"] = int(reply_to_message_id)
            payload["allow_sending_without_reply"] = True
        if idx == len(chunks) - 1 and reply_markup is not None:
            payload["reply_markup"] = reply_markup

        res = _call_telegram_api(bot_token, "sendMessage", payload)
        if not res.get("ok"):
            # Fallback without HTML parse_mode if entities failed
            plain_payload = dict(payload)
            plain_payload.pop("parse_mode", None)
            plain_payload["text"] = re.sub(r"<[^>]+>", "", chunk)
            res = _call_telegram_api(bot_token, "sendMessage", plain_payload)
        if res.get("ok") and isinstance(res.get("result"), dict):
            last_msg_id = res["result"].get("message_id")
    return last_msg_id


def _split_html_chunks(text: str, max_len: int = 3850) -> List[str]:
    if len(text) <= max_len:
        return [text]
    chunks: List[str] = []
    remaining = text
    while len(remaining) > max_len:
        cut = remaining.rfind("\n", 0, max_len)
        if cut < 800:
            cut = max_len
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def answer_vip_callback(
    bot_token: str,
    callback_query_id: str,
    text: str,
    show_alert: bool = False,
) -> None:
    payload: Dict[str, Any] = {
        "callback_query_id": callback_query_id,
        "text": text[:199],
        "show_alert": bool(show_alert),
    }
    _call_telegram_api(bot_token, "answerCallbackQuery", payload, timeout=8)


def _web_vip_chat_endpoints() -> List[str]:
    urls: List[str] = []
    local_port = os.getenv("PORT_WEB", "3000")
    urls.append(f"http://127.0.0.1:{local_port}/api/telegram/vip-chat")
    origin = (get_web_origin() or "https://egxbots.com").rstrip("/")
    if origin and "127.0.0.1" not in origin and "localhost" not in origin:
        urls.append(f"{origin}/api/telegram/vip-chat")
    elif "https://egxbots.com/api/telegram/vip-chat" not in urls:
        urls.append("https://egxbots.com/api/telegram/vip-chat")
    return urls


def call_web_vip_chat_api(payload: Dict[str, Any], timeout: int = 75) -> Dict[str, Any]:
    """Call Next.js /api/telegram/vip-chat endpoint with automatic local->production fallback."""
    admin_key = os.getenv("ADMIN_SECRET_KEY", "").strip()
    headers = {
        "Content-Type": "application/json",
        "x-admin-key": admin_key,
    }
    last_error = "Unreachable"
    for url in _web_vip_chat_endpoints():
        try:
            connect_timeout = 2.0 if "127.0.0.1" in url else 8.0
            resp = requests.post(url, json=payload, headers=headers, timeout=(connect_timeout, timeout))
            if resp.status_code in (200, 400, 403, 429):
                return resp.json()
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:
            last_error = str(exc)
            continue
    return {"ok": False, "error": last_error}


def _format_table_for_telegram(table: Dict[str, Any]) -> str:
    """Render an ExcelTable object into sleek, mobile-readable Telegram HTML."""
    title = str(table.get("title") or "").strip()
    headers = [str(h).strip() for h in (table.get("headers") or [])]
    rows = table.get("rows") or []
    if not rows:
        return ""

    lines: List[str] = []
    if title:
        lines.append(f"\n📊 <b>{html.escape(title)}</b>")

    for row in rows[:10]:
        if not isinstance(row, list) or not row:
            continue
        cells = [str(c).strip() for c in row]
        # Format first column as bullet header, and remaining columns as key: value pairs
        head_label = html.escape(cells[0])
        details: List[str] = []
        for idx in range(1, len(cells)):
            val = html.escape(cells[idx])
            if not val or val == "—":
                continue
            col_name = html.escape(headers[idx]) if idx < len(headers) else ""
            if col_name:
                details.append(f"{col_name}: <code>{val}</code>")
            else:
                details.append(f"<code>{val}</code>")
        if details:
            lines.append(f"• <b>{head_label}</b> — " + " | ".join(details))
        else:
            lines.append(f"• <b>{head_label}</b>")
    return "\n".join(lines)


def _convert_markdown_tables_to_bullets(md_text: str) -> str:
    """Convert raw Markdown pipe tables in LLM text into clean Telegram bullet lists."""
    lines = md_text.split("\n")
    out: List[str] = []
    table_buffer: List[str] = []

    def _flush_table(buf: List[str]) -> None:
        if len(buf) < 2:
            out.extend(buf)
            return
        parsed_rows: List[List[str]] = []
        for r in buf:
            stripped = r.strip().strip("|")
            if re.match(r"^[\s:\-|]+$", stripped):
                continue
            cells = [c.strip() for c in stripped.split("|")]
            if any(cells):
                parsed_rows.append(cells)
        if len(parsed_rows) < 2:
            out.extend(buf)
            return
        headers = parsed_rows[0]
        for row in parsed_rows[1:]:
            first = row[0] if row else ""
            parts: List[str] = []
            for idx in range(1, len(row)):
                val = row[idx]
                if not val:
                    continue
                col = headers[idx] if idx < len(headers) else ""
                parts.append(f"{col}: `{val}`" if col else f"`{val}`")
            if parts:
                out.append(f"• **{first}** — " + " | ".join(parts))
            else:
                out.append(f"• **{first}**")

    for line in lines:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            table_buffer.append(line)
        else:
            if table_buffer:
                _flush_table(table_buffer)
                table_buffer = []
            out.append(line)
    if table_buffer:
        _flush_table(table_buffer)
    return "\n".join(out)


def format_pipeline_reply_for_telegram(
    reply_text: str,
    tables: List[Dict[str, Any]],
    user_name: str,
    tg_user_id: int,
    is_pro: bool,
    used: int,
    limit: int,
    remaining: int,
    period: str,
) -> str:
    """Convert pipeline markdown response + tables into rich Telegram HTML."""
    cleaned = (reply_text or "").strip()
    has_md_table = bool(re.search(r"^\|.+\|$", cleaned, flags=re.MULTILINE))
    cleaned = _convert_markdown_tables_to_bullets(cleaned)

    # Escape HTML first
    escaped = html.escape(cleaned)

    # Convert Markdown links [text](url) -> <a href="url">text</a>
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s\)]+)\)",
        r'<a href="\2">\1</a>',
        escaped,
    )
    # Convert Markdown headers ### Title -> \n<b>🔹 Title</b>
    escaped = re.sub(
        r"^\s*#{1,4}\s+(.+)$",
        r"\n<b>🔹 \1</b>",
        escaped,
        flags=re.MULTILINE,
    )
    # Convert **bold** -> <b>bold</b>
    escaped = re.sub(r"\*\*([^\*\n]+)\*\*", r"<b>\1</b>", escaped)
    # Convert `code` -> <code>code</code>
    escaped = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", escaped)

    # If structured tables were returned and not already in the markdown text, append them
    if tables and not has_md_table:
        rendered_tables = [_format_table_for_telegram(t) for t in tables[:3]]
        rendered_tables = [t for t in rendered_tables if t]
        if rendered_tables:
            escaped += "\n" + "\n".join(rendered_tables)

    safe_user = html.escape(user_name or "المستثمر")
    user_link = f'<a href="tg://user?id={tg_user_id}">{safe_user}</a>'
    plan_badge = "👑 PRO VIP" if is_pro else "🎫 مجاني (Free)"
    period_label = "شهرياً" if period == "monthly" else "اليوم"

    footer = (
        f"\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 المستثمر: <b>{user_link}</b> | الباقة: <b>{plan_badge}</b>\n"
        f"📊 الرصيد المتبقي ({period_label}): <code>{remaining}</code> من <code>{limit}</code> سؤال"
    )
    if not is_pro and remaining <= 2:
        footer += f'\n💎 <a href="{_pricing_url()}">اشترك في باقة PRO (50 ج.م) للحصول على 350 سؤال شهرياً وتوصيات لحظية</a>'

    return f"🤖 <b>رد أرتورو الذكي لـ {user_link}:</b>\n\n{escaped}{footer}"


def is_vip_chat_update(data: Dict[str, Any]) -> bool:
    """Return True if this Telegram update belongs to the VIP Chat room / topic or uses vip_ callbacks."""
    if data.get("callback_query"):
        cb_data = str(data["callback_query"].get("data") or "")
        if cb_data.startswith("vip_"):
            return True

    msg = data.get("message") or {}
    chat = msg.get("chat") or {}
    chat_id_str = str(chat.get("id") or "")
    chat_type = str(chat.get("type") or "")
    thread_id = msg.get("message_thread_id")
    text = str(msg.get("text") or "").strip()

    target_group = get_vip_group_id()
    target_topic = get_vip_topic_id()

    # Check if inside the configured group + topic (e.g., -1002083067817 thread 1652)
    if chat_id_str == target_group:
        if target_topic is not None and thread_id == target_topic:
            return True
        # Also allow admin command /vippanel or /artoro_panel to initialize topic
        if text.lower().startswith(("/vippanel", "/artoro_panel")):
            return True
        return False

    # Also support standalone VIP Chat groups if chat_type is group/supergroup and explicitly addressed
    if chat_type in ("group", "supergroup"):
        if text.lower().startswith(("/vippanel", "/artoro_panel", "/ask")):
            return True
        reply_to = msg.get("reply_to_message") or {}
        reply_text = str(reply_to.get("text") or "")
        if "تحليل سهم فوري —" in reply_text or "مقارنة الأسهم —" in reply_text or "اسأل أرتورو —" in reply_text:
            return True

    return False


def _extract_user_info(from_obj: Dict[str, Any]) -> Tuple[int, str]:
    tg_user_id = int(from_obj.get("id") or 0)
    first = str(from_obj.get("first_name") or "").strip()
    last = str(from_obj.get("last_name") or "").strip()
    username = str(from_obj.get("username") or "").strip()
    full_name = f"{first} {last}".strip() or username or "المستثمر"
    return tg_user_id, full_name


def _show_limit_or_upgrade_dialog(
    bot_token: str,
    chat_id: Any,
    thread_id: Optional[int],
    tg_user_id: int,
    user_name: str,
    reason: str = "limit_reached",
    used: int = 5,
    limit: int = 5,
    callback_query_id: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
) -> None:
    """
    1. If triggered from a button click (callback_query_id), pop up a native modal
       Alert Dialog (show_alert=True) visible ONLY to that user!
    2. Also send the rich Pricing & Upgrade Dialog Card (with direct link to /pricing)
       to the user's Private DM (and/or in the topic if DM isn't open or triggered by text).
    """
    if callback_query_id:
        if reason == "pro_required":
            alert_text = PRO_ONLY_TOOL_ALERT_TEXT
        elif reason == "account_link":
            alert_text = ACCOUNT_LINK_ALERT_TEXT
        elif reason == "pricing_info":
            alert_text = PRICING_FEATURES_ALERT_TEXT
        else:
            alert_text = LIMIT_REACHED_ALERT_TEXT
        answer_vip_callback(bot_token, callback_query_id, alert_text, show_alert=True)

    dialog_html = build_pricing_dialog_html(
        user_name=user_name,
        tg_user_id=tg_user_id,
        reason=reason,
        used=used,
        limit=limit,
    )
    keyboard = build_pricing_upgrade_keyboard()

    # Try sending to the user's Private DM first so it's 100% private to them
    dm_sent = False
    if tg_user_id and str(chat_id) != str(tg_user_id):
        dm_res = _call_telegram_api(
            bot_token,
            "sendMessage",
            {
                "chat_id": tg_user_id,
                "text": dialog_html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": keyboard,
            },
        )
        dm_sent = bool(dm_res.get("ok"))

    # Also post the upgrade card in the topic if DM wasn't reachable, or if user clicked Pricing / hit limit via text
    if not dm_sent or not callback_query_id or reason == "pricing_info":
        send_vip_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=dialog_html,
            message_thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
            reply_markup=keyboard,
        )


def _execute_and_reply_vip_chat(
    bot_token: str,
    chat_id: Any,
    thread_id: Optional[int],
    tg_user_id: int,
    user_name: str,
    query_text: str,
    reply_to_message_id: Optional[int] = None,
    callback_query_id: Optional[str] = None,
) -> None:
    """Run the query through the website's Agentic Pipeline (/api/telegram/vip-chat) and post the formatted answer."""
    # Send typing indicator in the topic
    action_payload: Dict[str, Any] = {"chat_id": chat_id, "action": "typing"}
    if thread_id is not None:
        action_payload["message_thread_id"] = int(thread_id)
    _call_telegram_api(bot_token, "sendChatAction", action_payload, timeout=5)

    # Send temporary "جاري التحليل..." status message so user sees instant feedback
    safe_user = html.escape(user_name or "المستثمر")
    safe_query = html.escape(query_text[:120])
    wait_msg_id = send_vip_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=(
            f"⏳ <b>جاري تحليل طلبك يا <a href=\"tg://user?id={tg_user_id}\">{safe_user}</a>...</b>\n"
            f"💬 الطلب: <code>{safe_query}</code>"
        ),
        message_thread_id=thread_id,
        reply_to_message_id=reply_to_message_id,
    )

    api_res = call_web_vip_chat_api(
        {
            "action": "chat",
            "telegram_user_id": tg_user_id,
            "telegram_username": user_name,
            "message": query_text,
        }
    )

    # Delete temporary waiting message
    if wait_msg_id:
        _call_telegram_api(
            bot_token,
            "deleteMessage",
            {"chat_id": chat_id, "message_id": wait_msg_id},
            timeout=5,
        )

    if not api_res.get("ok"):
        err_code = str(api_res.get("error_code") or "")
        used = int(api_res.get("used") or 5)
        limit = int(api_res.get("limit") or 5)
        if err_code == "LIMIT_REACHED":
            _show_limit_or_upgrade_dialog(
                bot_token=bot_token,
                chat_id=chat_id,
                thread_id=thread_id,
                tg_user_id=tg_user_id,
                user_name=user_name,
                reason="limit_reached",
                used=used,
                limit=limit,
                callback_query_id=callback_query_id,
                reply_to_message_id=reply_to_message_id,
            )
            return
        if err_code == "PRO_REQUIRED":
            _show_limit_or_upgrade_dialog(
                bot_token=bot_token,
                chat_id=chat_id,
                thread_id=thread_id,
                tg_user_id=tg_user_id,
                user_name=user_name,
                reason="pro_required",
                used=used,
                limit=limit,
                callback_query_id=callback_query_id,
                reply_to_message_id=reply_to_message_id,
            )
            return
        if err_code == "ACCOUNT_LINK_REQUIRED":
            _show_limit_or_upgrade_dialog(
                bot_token=bot_token,
                chat_id=chat_id,
                thread_id=thread_id,
                tg_user_id=tg_user_id,
                user_name=user_name,
                reason="account_link",
                used=used,
                limit=limit,
                callback_query_id=callback_query_id,
                reply_to_message_id=reply_to_message_id,
            )
            return

        err_detail = html.escape(str(api_res.get("detail") or api_res.get("error") or "تعذر إكمال التحليل حالياً"))
        is_priv = str(chat_id) == str(tg_user_id)
        send_vip_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=f"⚠️ <b>عذراً يا {safe_user}، تعذر إتمام الطلب حالياً:</b>\n<code>{err_detail}</code>",
            message_thread_id=thread_id,
            reply_to_message_id=reply_to_message_id,
            reply_markup=build_vip_chat_keyboard(is_private=is_priv),
        )
        return

    formatted_html = format_pipeline_reply_for_telegram(
        reply_text=str(api_res.get("reply") or ""),
        tables=api_res.get("tables") or [],
        user_name=str(api_res.get("display_name") or user_name),
        tg_user_id=tg_user_id,
        is_pro=bool(api_res.get("is_pro")),
        used=int(api_res.get("used") or 1),
        limit=int(api_res.get("limit") or 5),
        remaining=int(api_res.get("remaining") or 0),
        period=str(api_res.get("period") or "daily"),
    )

    is_priv = str(chat_id) == str(tg_user_id)
    send_vip_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=formatted_html,
        message_thread_id=thread_id,
        reply_to_message_id=reply_to_message_id,
        reply_markup=build_vip_chat_keyboard(is_private=is_priv),
    )


def handle_vip_chat_update(data: Dict[str, Any], bot_token: str) -> bool:
    """
    Process a Telegram update (callback_query or message) for the VIP Chat room or @egxbots_bot private chat.
    Returns True if handled.
    """
    if not bot_token:
        return False

    # 1. Handle Inline Button Callbacks (vip_*)
    if data.get("callback_query"):
        cb = data["callback_query"]
        cb_id = str(cb.get("id") or "")
        cb_data = str(cb.get("data") or "")
        if not cb_data.startswith("vip_"):
            return False

        if cb_id and not _mark_event_processed(f"cb:{cb_id}"):
            return True

        msg = cb.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        chat_type = str(chat.get("type") or "")
        is_private = chat_type == "private" or (chat_id is not None and str(chat_id) == str((cb.get("from") or {}).get("id")))
        thread_id = msg.get("message_thread_id")
        from_obj = cb.get("from") or {}
        tg_user_id, user_name = _extract_user_info(from_obj)

        if not chat_id or not tg_user_id:
            return True

        # A) Pure Pricing Alert Popup Dialog
        if cb_data == "vip_pricing_alert":
            answer_vip_callback(bot_token, cb_id, PRICING_FEATURES_ALERT_TEXT, show_alert=True)
            return True

        # B) Show Pricing Dialog + Card
        if cb_data == "vip_pricing_dialog":
            _show_limit_or_upgrade_dialog(
                bot_token=bot_token,
                chat_id=chat_id,
                thread_id=thread_id,
                tg_user_id=tg_user_id,
                user_name=user_name,
                reason="pricing_info",
                callback_query_id=cb_id,
            )
            return True

        # C) Show Control Panel
        if cb_data == "vip_show_panel":
            answer_vip_callback(bot_token, cb_id, "🤖 لوحة أدوات أرتورو الذكية جاهزة!")
            send_vip_message(
                bot_token=bot_token,
                chat_id=chat_id,
                text=build_welcome_panel_html(is_private=is_private, chat_id=chat_id),
                message_thread_id=thread_id,
                reply_markup=build_vip_chat_keyboard(is_private=is_private),
            )
            return True

        # D) Check Quota Status (📊 رصيدي وخطتي)
        if cb_data == "vip_my_quota":
            q_res = call_web_vip_chat_api(
                {
                    "action": "check_quota",
                    "telegram_user_id": tg_user_id,
                    "telegram_username": user_name,
                },
                timeout=15,
            )
            is_pro = bool(q_res.get("is_pro"))
            linked = bool(q_res.get("linked"))
            used = int(q_res.get("used") or 0)
            limit = int(q_res.get("limit") or (350 if is_pro else 5))
            remaining = int(q_res.get("remaining") if q_res.get("remaining") is not None else max(0, limit - used))
            plan_txt = "👑 باقة PRO VIP" if is_pro else "🎫 الباقة المجانية (Free)"
            link_txt = "مربوط بالموقع ✅" if linked else "غير مربوط (اربطه من البروفايل)"
            period_txt = "شهرياً" if is_pro else "اليوم"

            quota_alert = (
                f"📊 حالة حسابك يا {user_name[:22]}:\n"
                f"• الباقة: {plan_txt}\n"
                f"• الحساب: {link_txt}\n"
                f"• المستهلك ({period_txt}): {used} من {limit}\n"
                f"• المتبقي لك: {remaining} سؤال"
            )
            answer_vip_callback(bot_token, cb_id, quota_alert, show_alert=True)
            return True

        # E) Interactive Input Prompts: vip_ask_stock, vip_ask_compare, vip_ask_free
        if cb_data in ("vip_ask_stock", "vip_ask_compare", "vip_ask_free"):
            mode_map = {
                "vip_ask_stock": "stock",
                "vip_ask_compare": "compare",
                "vip_ask_free": "free",
            }
            mode = mode_map[cb_data]

            # Check quota first & persist pending prompt
            q_res = call_web_vip_chat_api(
                {
                    "action": "set_pending_prompt",
                    "telegram_user_id": tg_user_id,
                    "telegram_username": user_name,
                    "prompt_mode": mode,
                },
                timeout=15,
            )
            remaining = int(q_res.get("remaining") if q_res.get("remaining") is not None else 5)
            used = int(q_res.get("used") or 0)
            limit = int(q_res.get("limit") or 5)

            if q_res.get("ok") and remaining <= 0:
                set_local_pending_prompt(chat_id, tg_user_id, None)
                _show_limit_or_upgrade_dialog(
                    bot_token=bot_token,
                    chat_id=chat_id,
                    thread_id=thread_id,
                    tg_user_id=tg_user_id,
                    user_name=user_name,
                    reason="limit_reached",
                    used=used,
                    limit=limit,
                    callback_query_id=cb_id,
                )
                return True

            set_local_pending_prompt(chat_id, tg_user_id, mode)
            safe_user = html.escape(user_name)
            user_mention = f'<a href="tg://user?id={tg_user_id}">{safe_user}</a>'

            if mode == "stock":
                answer_vip_callback(bot_token, cb_id, "🔍 اكتب اسم السهم بالعربي أو الكود الآن...")
                prompt_html = (
                    f"🔍 <b>تحليل سهم فوري — {user_mention}</b>\n"
                    f"✍️ اكتب الآن <b>اسم السهم بالعربي أو رمزه</b> في رسالتك القادمة "
                    f"(مثال: <code>فوري</code> أو <code>COMI</code> أو <code>طلعت مصطفى</code> أو <code>أبوقير</code>):"
                )
                placeholder = "اكتب اسم السهم أو رمزه (مثال: فوري أو COMI)..."
            elif mode == "compare":
                answer_vip_callback(bot_token, cb_id, "⚖️ اكتب اسم السهمين للمقارنة الآن...")
                prompt_html = (
                    f"⚖️ <b>مقارنة الأسهم — {user_mention}</b>\n"
                    f"✍️ اكتب الآن <b>اسم السهمين بالعربي أو الرمز</b> في رسالتك القادمة "
                    f"(مثال: <code>التجاري الدولي وفوري</code> أو <code>COMI و HRHO</code>):"
                )
                placeholder = "مثال: التجاري الدولي وفوري..."
            else:
                answer_vip_callback(bot_token, cb_id, "🤖 اكتب سؤالك لأرتورو الآن...")
                prompt_html = (
                    f"🤖 <b>اسأل أرتورو — {user_mention}</b>\n"
                    f"✍️ اكتب الآن سؤالك أو استفسارك عن السوق أو أي سهم في رسالتك القادمة:"
                )
                placeholder = "اكتب سؤالك لأرتورو هنا..."

            send_vip_message(
                bot_token=bot_token,
                chat_id=chat_id,
                text=prompt_html,
                message_thread_id=thread_id,
                reply_markup={
                    "force_reply": True,
                    "selective": True,
                    "input_field_placeholder": placeholder,
                },
            )
            return True

        # F) 1-Click Instant Tools (vip_tool_*)
        tool_queries = {
            "vip_tool_market": "أقوى الأسهم النهارده وملخص السوق",
            "vip_tool_accum": "أقوى أسهم التجميع والسيولة الذكية اليوم",
            "vip_tool_scan": "أفضل الأسهم فنياً اليوم حسب المسح الفني والمؤشرات",
            "vip_tool_recs": "هات كل التوصيات المفتوحة حالياً",
            "vip_tool_news": "أهم أخبار وإفصاحات البورصة المصرية اليوم",
            "vip_tool_portfolio": "حلل محفظتي الاستثمارية بالتفصيل",
        }
        if cb_data in tool_queries:
            query_text = tool_queries[cb_data]
            # First pre-check quota / Pro gate so we can show native show_alert modal if blocked!
            q_res = call_web_vip_chat_api(
                {
                    "action": "check_quota",
                    "telegram_user_id": tg_user_id,
                    "telegram_username": user_name,
                },
                timeout=12,
            )
            if q_res.get("ok"):
                is_pro = bool(q_res.get("is_pro"))
                linked = bool(q_res.get("linked"))
                remaining = int(q_res.get("remaining") if q_res.get("remaining") is not None else 5)
                used = int(q_res.get("used") or 0)
                limit = int(q_res.get("limit") or 5)

                if cb_data == "vip_tool_recs" and not is_pro:
                    _show_limit_or_upgrade_dialog(
                        bot_token=bot_token,
                        chat_id=chat_id,
                        thread_id=thread_id,
                        tg_user_id=tg_user_id,
                        user_name=user_name,
                        reason="pro_required",
                        used=used,
                        limit=limit,
                        callback_query_id=cb_id,
                    )
                    return True

                if cb_data == "vip_tool_portfolio" and not linked:
                    _show_limit_or_upgrade_dialog(
                        bot_token=bot_token,
                        chat_id=chat_id,
                        thread_id=thread_id,
                        tg_user_id=tg_user_id,
                        user_name=user_name,
                        reason="account_link",
                        used=used,
                        limit=limit,
                        callback_query_id=cb_id,
                    )
                    return True

                if remaining <= 0:
                    _show_limit_or_upgrade_dialog(
                        bot_token=bot_token,
                        chat_id=chat_id,
                        thread_id=thread_id,
                        tg_user_id=tg_user_id,
                        user_name=user_name,
                        reason="limit_reached",
                        used=used,
                        limit=limit,
                        callback_query_id=cb_id,
                    )
                    return True

            answer_vip_callback(bot_token, cb_id, "⏳ جاري تجهيز التحليل من أرتورو...")
            threading.Thread(
                target=_execute_and_reply_vip_chat,
                kwargs={
                    "bot_token": bot_token,
                    "chat_id": chat_id,
                    "thread_id": thread_id,
                    "tg_user_id": tg_user_id,
                    "user_name": user_name,
                    "query_text": query_text,
                    "callback_query_id": None,
                },
                daemon=True,
            ).start()
            return True

        return False

    # 2. Handle Regular Messages in the VIP Chat Topic or Private Chat with @egxbots_bot
    msg = data.get("message") or {}
    if not msg:
        return False

    # Ignore messages sent by bots
    from_obj = msg.get("from") or {}
    if from_obj.get("is_bot"):
        return False

    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = str(chat.get("type") or "")
    thread_id = msg.get("message_thread_id")
    msg_id = msg.get("message_id")
    text = str(msg.get("text") or "").strip()

    if not chat_id or not text:
        return False

    tg_user_id, user_name = _extract_user_info(from_obj)
    if not tg_user_id:
        return False

    is_private = chat_type == "private" or str(chat_id) == str(tg_user_id)

    if msg_id and not _mark_event_processed(f"msg:{chat_id}:{msg_id}"):
        return True

    clean_lower = text.lower().split("@")[0].split()[0]

    # Quick Quota Simulation Commands for Testing (/test_limit, /test_free, /test_normal)
    if clean_lower in ("/test_limit", "/test_free", "/test_normal"):
        mode_arg = {
            "/test_limit": "limit_reached",
            "/test_free": "free_plan",
            "/test_normal": "normal",
        }[clean_lower]
        res = call_web_vip_chat_api(
            {
                "action": "set_test_mode",
                "telegram_user_id": tg_user_id,
                "telegram_username": user_name,
                "test_mode": mode_arg,
            },
            timeout=15,
        )
        if mode_arg == "limit_reached":
            msg_txt = (
                "🧪 <b>تم تفعيل وضع اختبار انتهاء الكوتا (Limit Reached 5/5):</b>\n"
                "اضغط الآن على أي زر في اللوحة بالأسفل (مثل <code>🔍 حلل سهم</code> أو <code>📈 ملخص السوق</code>) "
                "لترى كيف تظهر <b>النافذة المنبثقة الخاصة (Dialog)</b> وكارت التسعير للمستخدم حين ينتهي رصيده!\n"
                "• للعودة لحسابك الطبيعي اكتب: <code>/test_normal</code>"
            )
        elif mode_arg == "free_plan":
            msg_txt = (
                "🧪 <b>تم تفعيل وضع اختبار الباقة المجانية (Free Plan):</b>\n"
                "يمكنك الآن الضغط على زر <code>🎯 التوصيات المفتوحة (PRO)</code> لاختبار قفل الميزة، أو اختبار خصم الـ 5 رسائل اليومية.\n"
                "• للعودة لباقتك الطبيعية اكتب: <code>/test_normal</code>"
            )
        else:
            used_val = res.get("used", 0)
            limit_val = res.get("limit", 350)
            rem_val = res.get("remaining", 350)
            msg_txt = (
                f"✅ <b>تمت استعادة وضع حسابك الطبيعي (PRO VIP):</b>\n"
                f"• المستهلك الفعلي: <code>{used_val} / {limit_val}</code>\n"
                f"• المتبقي لك: <code>{rem_val}</code> سؤال."
            )
        send_vip_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=msg_txt,
            message_thread_id=thread_id,
            reply_to_message_id=msg_id,
            reply_markup=build_vip_chat_keyboard(is_private=is_private),
        )
        return True

    # Command to show/pin the interactive ARTORO Control Panel (or /start in private DM)
    if clean_lower in (
        "/start",
        "/panel",
        "/vippanel",
        "/artoro",
        "/artoro_panel",
        "/menu",
    ):
        panel_msg_id = send_vip_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=build_welcome_panel_html(is_private=is_private, chat_id=chat_id),
            message_thread_id=thread_id,
            reply_to_message_id=msg_id,
            reply_markup=build_vip_chat_keyboard(is_private=is_private),
        )
        if not is_private and panel_msg_id and clean_lower in ("/vippanel", "/artoro_panel", "/panel"):
            _call_telegram_api(
                bot_token,
                "pinChatMessage",
                {"chat_id": chat_id, "message_id": panel_msg_id, "disable_notification": True},
                timeout=5,
            )
        return True

    # Check if user has an active pending prompt mode (from clicking 🔍 حلل سهم, ⚖️ قارن سهمين, or 🤖 اسأل أرتورو)
    pending_mode = get_local_pending_prompt(chat_id, tg_user_id)
    reply_to = msg.get("reply_to_message") or {}
    reply_to_text = str(reply_to.get("text") or "")

    if not pending_mode and reply_to_text:
        if "تحليل سهم فوري —" in reply_to_text:
            pending_mode = "stock"
        elif "مقارنة الأسهم —" in reply_to_text:
            pending_mode = "compare"
        elif "اسأل أرتورو —" in reply_to_text:
            pending_mode = "free"

    # In Private 1-on-1 Chat with @egxbots_bot, users can type directly OR use the buttons!
    # In the Public Group Topic (1652), users must click a button first so member-to-member chat is ignored.
    if not pending_mode:
        if is_private:
            pending_mode = "free"
        else:
            return True

    set_local_pending_prompt(chat_id, tg_user_id, None)

    cleaned_input = text.strip()
    if pending_mode == "stock":
        if not re.search(r"(?:حلل|تحليل|سعر|رايك|رأيك|مستويات|اخبار|أخبار)", cleaned_input):
            query_text = f"حلل سهم {cleaned_input}"
        else:
            query_text = cleaned_input
    elif pending_mode == "compare":
        if not re.search(r"(?:قارن|مقارن|مقارنة|ايهم|أيهما)", cleaned_input):
            query_text = f"قارن بين {cleaned_input}"
        else:
            query_text = cleaned_input
    else:
        query_text = cleaned_input

    threading.Thread(
        target=_execute_and_reply_vip_chat,
        kwargs={
            "bot_token": bot_token,
            "chat_id": chat_id,
            "thread_id": thread_id,
            "tg_user_id": tg_user_id,
            "user_name": user_name,
            "query_text": query_text,
            "reply_to_message_id": msg_id,
            "callback_query_id": None,
        },
        daemon=True,
    ).start()
    return True


def post_initial_vip_panel(bot_token: Optional[str] = None) -> Dict[str, Any]:
    """Post and attempt to pin the welcome control panel in https://t.me/egxbots/1652."""
    token = (bot_token or os.getenv("ARTORO_AI_BOT") or os.getenv("SUPPORT_BOT_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "error": "No bot token configured"}
    chat_id = get_vip_group_id()
    thread_id = get_vip_topic_id()
    msg_id = send_vip_message(
        bot_token=token,
        chat_id=chat_id,
        text=build_welcome_panel_html(),
        message_thread_id=thread_id,
        reply_markup=build_vip_chat_keyboard(),
    )
    if msg_id:
        _call_telegram_api(
            token,
            "pinChatMessage",
            {"chat_id": chat_id, "message_id": msg_id, "disable_notification": True},
            timeout=5,
        )
        return {"ok": True, "chat_id": chat_id, "thread_id": thread_id, "message_id": msg_id}
    return {"ok": False, "error": "Failed to send panel message"}
