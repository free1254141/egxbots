import os
import re
import requests
import threading
import time
from typing import Optional, List, Dict, Any
from api.stock_ai import _init_supabase, supabase as _supabase
from api.support_analytics import (
    get_registrations_summary,
    get_activity_summary,
    get_chat_summary,
    get_comprehensive_report
)

def get_token() -> str:
    return os.getenv("SUPPORT_BOT_TOKEN", "").strip()

def __getattr__(name: str):
    if name == "SUPPORT_BOT_TOKEN":
        token = get_token()
        print("[SUPPORT_CHAT] SUPPORT_BOT_TOKEN is configured")
        return token
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

CHAT_ID_FILE = os.path.join(os.path.dirname(__file__), "support_admin_chat_id.txt")
TELEGRAM_RELAY_URL = os.getenv("TELEGRAM_RELAY_URL", "https://api.telegram.org").rstrip("/")

_ADMIN_ACTIVE_SESSIONS: Dict[int, Dict[str, Any]] = {}
SESSION_REGEX = re.compile(
    r'(?:Session|جلسة|session_id)(?:</?[a-zA-Z0-9]+>|[\s:=-])*([a-zA-Z0-9\-_\.]{6,})',
    re.IGNORECASE
)
ACTIVE_SESSION_TTL_SECONDS = 20 * 60  # 20 minutes of inactivity

ADMIN_REPLY_KEYBOARD = {
    "keyboard": [
        [{"text": "👥 المسجلين (اليوم وأمس)"}, {"text": "💬 مستخدمين الشات"}],
        [{"text": "⚡ نشاط المستخدمين"}, {"text": "📊 تقرير شامل"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

ADMIN_INLINE_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "👥 المسجلين", "callback_data": "cmd_users"},
            {"text": "💬 الشات", "callback_data": "cmd_chats"}
        ],
        [
            {"text": "⚡ النشاط", "callback_data": "cmd_activity"},
            {"text": "📊 تقرير شامل", "callback_data": "cmd_stats"}
        ],
        [
            {"text": "🔄 تحديث الأرقام الآن", "callback_data": "cmd_refresh"}
        ]
    ]
}

def load_admin_chat_id() -> Optional[int]:
    env_chat = os.getenv("SUPPORT_ADMIN_CHAT_ID") or os.getenv("ADMIN_CHAT_ID")
    if env_chat and env_chat.strip().lstrip("-").isdigit():
        return int(env_chat.strip())
    if os.path.exists(CHAT_ID_FILE):
        try:
            with open(CHAT_ID_FILE, "r") as f:
                return int(f.read().strip())
        except Exception:
            pass
    # Default fallback admin chat ID
    return 5149631436

def save_admin_chat_id(chat_id: int):
    # Never overwrite admin chat ID with a group/channel ID (negative in Telegram)
    if not chat_id or int(chat_id) < 0:
        return
    try:
        with open(CHAT_ID_FILE, "w") as f:
            f.write(str(chat_id))
        print(f"[SUPPORT_CHAT] Saved admin chat ID: {chat_id}")
    except Exception as e:
        print(f"[SUPPORT_CHAT] Error saving admin chat ID: {e}")

def send_telegram_message(chat_id: int, text: str, reply_markup: Optional[dict] = None) -> bool:
    url = f"{TELEGRAM_RELAY_URL}/bot{get_token()}/sendMessage"
    # Chunk text if exceeds Telegram's limit (4096 chars)
    chunks = [text[i:i + 4000] for i in range(0, max(1, len(text)), 4000)]
    success = True
    for idx, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "HTML"
        }
        if idx == len(chunks) - 1 and reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            resp = requests.post(url, json=payload, timeout=12)
            res_json = resp.json()
            if not res_json.get("ok"):
                # If HTML parse error or rejected, retry without parse_mode
                payload.pop("parse_mode", None)
                resp2 = requests.post(url, json=payload, timeout=12)
                if not resp2.json().get("ok"):
                    success = False
        except Exception as e:
            print(f"[SUPPORT_CHAT] Telegram send error: {e}")
            success = False
    return success

def set_telegram_reaction(chat_id: int, message_id: Optional[int], emoji: str = "👍") -> bool:
    if not message_id:
        return False
    url = f"{TELEGRAM_RELAY_URL}/bot{get_token()}/setMessageReaction"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reaction": [{"type": "emoji", "emoji": emoji}]
    }
    try:
        resp = requests.post(url, json=payload, timeout=5)
        return resp.json().get("ok", False)
    except Exception:
        return False

def answer_callback_query(callback_query_id: str, text: Optional[str] = None):
    url = f"{TELEGRAM_RELAY_URL}/bot{get_token()}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[SUPPORT_CHAT] Error answering callback: {e}")

def edit_telegram_message(chat_id: int, message_id: int, text: str, reply_markup: Optional[dict] = None) -> bool:
    url = f"{TELEGRAM_RELAY_URL}/bot{get_token()}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.json().get("ok", False)
    except Exception as e:
        print(f"[SUPPORT_CHAT] Telegram edit error: {e}")
        return False

def handle_customer_message(session_id: str, content: str, user_name: Optional[str] = None):
    _init_supabase()
    if not _supabase:
        print("[SUPPORT_CHAT] Supabase client not initialized")
        return None
        
    msg_data = {
        "session_id": session_id,
        "sender": "user",
        "content": content,
        "user_name": user_name or "Guest"
    }
    
    try:
        res = _supabase.table("support_messages").insert(msg_data).execute()
        saved_msg = res.data[0] if res.data else None
    except Exception as e:
        print(f"[SUPPORT_CHAT] DB insert error: {e}")
        saved_msg = None
        
    # Forward to admin on Telegram
    admin_chat_id = load_admin_chat_id()
    if admin_chat_id:
        _ADMIN_ACTIVE_SESSIONS[admin_chat_id] = {
            "session_id": session_id,
            "user_name": user_name or "Guest",
            "time": time.time(),
        }
        tg_text = (
            f"💬 <b>[طلب دعم فني جديد]</b>\n"
            f"<b>Session:</b> <code>{session_id}</code>\n"
            f"<b>العميل:</b> {user_name or 'زائر'}\n"
            f"---------------------------------\n"
            f"{content}\n"
            f"---------------------------------\n"
            f"💡 <i>اضغط Reply (رد) على الرسالة لإرسال ردك مباشرة للعميل.</i>"
        )
        send_telegram_message(admin_chat_id, tg_text)
        
    return saved_msg

def handle_telegram_update(data: dict):
    # 1. Handle Callback Query (from Admin Inline Keyboard)
    if data.get("callback_query"):
        cb = data["callback_query"]
        cb_id = cb.get("id")
        cb_data = cb.get("data", "")
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        msg_id = message.get("message_id")
        
        if cb_id:
            answer_callback_query(cb_id, "جاري تحديث البيانات...")
            
        if not chat_id or int(chat_id) < 0:
            return
            
        save_admin_chat_id(chat_id)
        
        report_text = ""
        if cb_data == "cmd_users":
            report_text = get_registrations_summary()
        elif cb_data == "cmd_chats":
            report_text = get_chat_summary()
        elif cb_data == "cmd_activity":
            report_text = get_activity_summary()
        elif cb_data in ("cmd_stats", "cmd_refresh"):
            report_text = get_comprehensive_report()
            
        if report_text:
            if msg_id:
                edited = edit_telegram_message(chat_id, msg_id, report_text, reply_markup=ADMIN_INLINE_KEYBOARD)
                if not edited:
                    send_telegram_message(chat_id, report_text, reply_markup=ADMIN_INLINE_KEYBOARD)
            else:
                send_telegram_message(chat_id, report_text, reply_markup=ADMIN_INLINE_KEYBOARD)
        return

    # 2. Handle Member updates (Pro channel invites)
    if data.get("chat_member") or data.get("my_chat_member"):
        from api.telegram_pro_invites import handle_chat_member_update
        handle_chat_member_update(data)
        return

    # 3. Handle Regular Messages
    message = data.get("message", {})
    if not message:
        return
        
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    
    # Do not run Admin AI assistant in group/channel chats
    if not chat_id or int(chat_id) < 0:
        return
        
    # Always register / update admin chat ID
    save_admin_chat_id(chat_id)

    clean_cmd = text.lower()

    # Manual command to end/close active support session
    if clean_cmd in ("/end", "/done", "/close", "انهاء", "إنهاء", "خلاص", "تم الانتهاء"):
        if chat_id in _ADMIN_ACTIVE_SESSIONS:
            sess = _ADMIN_ACTIVE_SESSIONS.pop(chat_id, None)
            sess_id = sess.get("session_id") if sess else ""
            send_telegram_message(chat_id, f"🔒 تم إغلاق جلسة الدعم الفني (<code>{sess_id}</code>). رسائلك التالية لن تُرسل للعميل.")
        else:
            send_telegram_message(chat_id, "ℹ️ لا توجد جلسة دعم فني نشطة حالياً.")
        return

    is_admin_command = (
        clean_cmd.startswith("/")
        or clean_cmd in (
            "المسجلين", "المستخدمين", "مسجلين", "👥 المسجلين (اليوم وأمس)", "المسجلين اليوم",
            "النشاط", "نشاط", "تفاعل", "التفاعل", "⚡ نشاط المستخدمين",
            "الشات", "شات", "محادثات", "المحادثات", "💬 مستخدمين الشات",
            "تقرير", "إحصائيات", "احصائيات", "التقرير", "الإحصائيات", "📊 تقرير شامل",
            "القائمة", "مساعدة", "اوامر", "الأوامر", "أوامر"
        )
    )

    # 1. Resolve session_id from explicit reply
    session_id = None
    reply_to = message.get("reply_to_message", {})
    if reply_to and text:
        reply_text = reply_to.get("text", "") or reply_to.get("caption", "")
        match = SESSION_REGEX.search(reply_text)
        if match:
            session_id = match.group(1)
        elif chat_id in _ADMIN_ACTIVE_SESSIONS:
            active_info = _ADMIN_ACTIVE_SESSIONS[chat_id]
            if time.time() - active_info.get("time", 0) < ACTIVE_SESSION_TTL_SECONDS:
                session_id = active_info.get("session_id")

    # 2. Or resolve from active session if admin typed directly without reply (and not a command)
    if not session_id and not is_admin_command and chat_id in _ADMIN_ACTIVE_SESSIONS:
        active_info = _ADMIN_ACTIVE_SESSIONS[chat_id]
        if time.time() - active_info.get("time", 0) < ACTIVE_SESSION_TTL_SECONDS:
            session_id = active_info.get("session_id")

    # 3. If routed to customer support session
    if session_id and not is_admin_command:
        _init_supabase()
        if _supabase:
            reply_data = {
                "session_id": session_id,
                "sender": "admin",
                "content": text,
                "user_name": "Admin"
            }
            try:
                _supabase.table("support_messages").insert(reply_data).execute()
                _ADMIN_ACTIVE_SESSIONS[chat_id] = {
                    "session_id": session_id,
                    "time": time.time(),
                }
                reacted = set_telegram_reaction(chat_id, message.get("message_id"), "👍")
                if not reacted:
                    send_telegram_message(
                        chat_id,
                        f"✅ تم إرسال ردك للعميل (Session: <code>{session_id}</code>)"
                    )
                print(f"[SUPPORT_CHAT] Saved admin reply for session {session_id}")
            except Exception as e:
                print(f"[SUPPORT_CHAT] Error saving admin reply: {e}")
                send_telegram_message(chat_id, f"⚠️ خطأ أثناء حفظ الرد: {e}")
        return

    clean_cmd = text.lower()

    # Handle /start or /menu or /help
    if clean_cmd.startswith("/start") or clean_cmd in ("/menu", "/help", "القائمة", "مساعدة", "اوامر", "الأوامر", "أوامر"):
        welcome_text = (
            "👑 <b>أهلاً بك في بوت إدارة ودعم منصة EGX Bots!</b>\n\n"
            "هذا البوت مخصص للمؤسس والإدارة للمتابعة والدعم الفني المباشر:\n"
            "١. 💬 <b>دعم العملاء المباشر:</b> اضغط Reply (رد) على أي تذكرة عميل لإرسال ردك فورياً لشاشته بالموقع.\n"
            "٢. 📊 <b>تقارير لحظية سريعة:</b> استخدم الأزرار الثابتة بالأسفل لعرض إحصائيات اليوم وأمس بضغطة واحدة.\n\n"
            "👇 <b>اختر من الأزرار أدناه أو انتظر إشعارات رسائل العملاء:</b>"
        )
        send_telegram_message(chat_id, welcome_text, reply_markup=ADMIN_REPLY_KEYBOARD)
        send_telegram_message(chat_id, get_comprehensive_report(), reply_markup=ADMIN_INLINE_KEYBOARD)
        return

    # Handle Registered Users (اليوم وأمس)
    if clean_cmd in ("/users", "/registrations", "المسجلين", "المستخدمين", "مسجلين", "👥 المسجلين (اليوم وأمس)", "المسجلين اليوم"):
        send_telegram_message(chat_id, get_registrations_summary(), reply_markup=ADMIN_INLINE_KEYBOARD)
        return

    # Handle Activity (النشاط)
    if clean_cmd in ("/activity", "/active", "النشاط", "نشاط", "تفاعل", "التفاعل", "⚡ نشاط المستخدمين"):
        send_telegram_message(chat_id, get_activity_summary(), reply_markup=ADMIN_INLINE_KEYBOARD)
        return

    # Handle Chat Users & Sessions (مستخدمين الشات)
    if clean_cmd in ("/chat", "/chats", "الشات", "شات", "محادثات", "المحادثات", "💬 مستخدمين الشات"):
        send_telegram_message(chat_id, get_chat_summary(), reply_markup=ADMIN_INLINE_KEYBOARD)
        return

    # Handle Comprehensive Report (التقرير الشامل)
    if clean_cmd in ("/stats", "/report", "تقرير", "إحصائيات", "احصائيات", "التقرير", "الإحصائيات", "📊 تقرير شامل"):
        send_telegram_message(chat_id, get_comprehensive_report(), reply_markup=ADMIN_INLINE_KEYBOARD)
        return

    # Fallback for arbitrary messages when no active customer session exists (NO AI / NO LLM)
    guide_text = (
        "ℹ️ <b>لم يتم إرسال الرسالة لعدم وجود جلسة دعم فني نشطة حالياً.</b>\n\n"
        "للرد على عميل:\n"
        "• اضغط <b>Reply (رد)</b> على رسالة طلب الدعم الخاصة بالعميل.\n\n"
        "📊 أو استخدم الأزرار أدناه لعرض التقارير والإحصائيات اللحظية."
    )
    send_telegram_message(chat_id, guide_text, reply_markup=ADMIN_REPLY_KEYBOARD)
