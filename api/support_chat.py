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
        [{"text": "⚡ تفعيل PRO سريع"}],
        [{"text": "👥 المسجلين (اليوم وأمس)"}, {"text": "💬 مستخدمين الشات"}],
        [{"text": "⚡ نشاط المستخدمين"}, {"text": "📊 تقرير شامل"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

ADMIN_INLINE_KEYBOARD = {
    "inline_keyboard": [
        [
            {"text": "⚡ تفعيل PRO سريع", "callback_data": "cmd_activate_prompt"}
        ],
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

_ADMIN_AWAITING_ACTIVATION: Dict[int, Dict[str, Any]] = {}
_EMAIL_USER_CACHE: Dict[str, dict] = {}

EMAIL_ACTIVATION_CMD_REGEX = re.compile(
    r'^(?:/activate|/pro|تفعيل|تفعيل_برو)\s+([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)(?:\s+(\d+))?',
    re.IGNORECASE
)
EMAIL_FINDER_REGEX = re.compile(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', re.IGNORECASE)

def find_user_by_email(email: str) -> Optional[dict]:
    _init_supabase()
    if not _supabase:
        return None
    clean = email.strip().lower()
    if clean in _EMAIL_USER_CACHE:
        return _EMAIL_USER_CACHE[clean]

    page = 1
    while page <= 15:
        try:
            users = _supabase.auth.admin.list_users(page=page, per_page=100)
        except Exception as e:
            print(f"[SUPPORT_CHAT] list_users error: {e}")
            break
        if not users:
            break
        for u in users:
            u_email = (getattr(u, "email", "") or "").strip().lower()
            if u_email:
                meta = getattr(u, "user_metadata", {}) or {}
                user_info = {
                    "id": str(u.id),
                    "email": u_email,
                    "name": meta.get("full_name") or meta.get("name") or meta.get("display_name") or "",
                    "created_at": str(getattr(u, "created_at", "") or "")
                }
                _EMAIL_USER_CACHE[u_email] = user_info
                if u_email == clean:
                    return user_info
        if len(users) < 100:
            break
        page += 1
    return None

def quick_activate_pro(chat_id: int, target_email: str, duration_days: int = 30) -> None:
    _init_supabase()
    if not _supabase:
        send_telegram_message(chat_id, "⚠️ خطأ: قاعدة البيانات غير متصلة حالياً.")
        return

    clean_email = target_email.strip().lower()
    user = find_user_by_email(clean_email)
    if not user:
        send_telegram_message(
            chat_id,
            f"❌ <b>لم يتم العثور على حساب مسجل بهذا الإيميل:</b>\n<code>{clean_email}</code>\n\n"
            f"⚠️ <b>يجب على العميل تسجيل الدخول أولاً:</b>\n"
            f"اطلب من العميل الدخول لموقع <a href='https://egxbots.com'>egxbots.com</a> والضغط على 'تسجيل الدخول بحساب جوجل' لإنشاء حسابه.\n"
            f"بمجرد تسجيله يمكنك تفعيله فوراً من هنا بضغطة زر 🚀",
            reply_markup=ADMIN_REPLY_KEYBOARD
        )
        return

    user_id = user["id"]
    user_name = user.get("name") or "عميل EGX Bots"

    send_telegram_message(
        chat_id,
        f"⏳ <b>جاري تفعيل باقة PRO لحساب:</b>\n<code>{clean_email}</code>\n"
        f"📅 <b>المدة:</b> {duration_days} يوماً..."
    )

    import uuid
    from datetime import datetime, timezone
    from api.payment_common import activate_subscription
    from api.telegram_pro_invites import ensure_pro_invite, send_pro_welcome_to_user_telegram

    order_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        # Check if user has an existing pending order to update
        existing = (
            _supabase.table("local_payment_orders")
            .select("id")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if existing and existing.data:
            order_id = existing.data[0]["id"]
            _supabase.table("local_payment_orders").update({
                "provider": "admin_telegram",
                "customer_note": f"Activated via Telegram Support Bot by admin {chat_id}",
                "payment_reviewed_by": f"tg_admin_{chat_id}",
                "payment_review_status": "reviewed",
                "payment_reviewed_at": now_iso,
                "updated_at": now_iso
            }).eq("id", order_id).execute()
        else:
            _supabase.table("local_payment_orders").insert({
                "id": order_id,
                "user_id": user_id,
                "plan_id": "pro",
                "amount_egp": 100.0,
                "provider": "admin_telegram",
                "status": "pending",
                "customer_note": f"Activated via Telegram Support Bot by admin {chat_id}",
                "payment_reviewed_by": f"tg_admin_{chat_id}",
                "payment_review_status": "reviewed",
                "payment_reviewed_at": now_iso,
                "created_at": now_iso,
                "updated_at": now_iso
            }).execute()

        # Call activate_subscription with duration_days
        activate_subscription(
            user_id,
            "pro",
            provider="admin_telegram",
            payment_order_id=order_id,
            duration_days=duration_days
        )

        # Mark order approved
        _supabase.table("local_payment_orders").update({
            "status": "approved",
            "updated_at": now_iso
        }).eq("id", order_id).execute()

        # Fetch updated subscription period end
        sub_res = (
            _supabase.table("subscriptions")
            .select("current_period_end")
            .eq("user_id", user_id)
            .eq("status", "active")
            .order("current_period_end", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        sub_end = (sub_res.data or {}).get("current_period_end") if sub_res and sub_res.data else None
        sub_end_str = str(sub_end)[:10] if sub_end else f"{duration_days} يوم"

        # Generate unique VIP channel invite link
        invite_link = ""
        try:
            inv = ensure_pro_invite(user_id, str(sub_end or ""))
            invite_link = str((inv or {}).get("invite_link") or "").strip()
        except Exception as inv_err:
            print(f"[SUPPORT_CHAT] ensure_pro_invite warning: {inv_err}")

        # Send Pro welcome to user on Telegram if connected
        welcomed = False
        try:
            welcomed = send_pro_welcome_to_user_telegram(
                user_id,
                invite_link=invite_link,
                plan_name="Pro VIP",
                subscription_end=str(sub_end or "")
            )
        except Exception as w_err:
            print(f"[SUPPORT_CHAT] send_pro_welcome warning: {w_err}")

        # Send automated confirmation message to user's web support chat session
        web_support_sent = False
        try:
            web_support_msg = (
                f"أهلاً بك يا فندم! 👑 تم مراجعة طلبك وتفعيل اشتراكك في باقة Pro بنجاح.\n\n"
                f"📅 مدة الاشتراك: {duration_days} يوماً (ساري حتى {sub_end_str}).\n"
                f"💎 رابط قناة VIP الحصري على تليجرام:\n"
                f"{invite_link or 'https://t.me/EGX_Bots'}\n\n"
                f"نتمنى لك دائماً تداولات ناجحة وموفقة، وتحت أمرك في أي وقت! 🚀"
            )
            _supabase.table("support_messages").insert({
                "session_id": user_id,
                "sender": "admin",
                "content": web_support_msg,
                "user_name": "إدارة EGX BOTS",
                "user_id": user_id,
                "image_url": None,
            }).execute()
            web_support_sent = True
        except Exception as s_err:
            print(f"[SUPPORT_CHAT] web support notification warning: {s_err}")

        tg_status_note = (
            "📲 <b>تم إرسال رسالة ترحيبية ورابط قناة VIP للعميل على تليجرامه مباشرة!</b>"
            if welcomed else
            "ℹ️ <i>العميل لم يربط حسابه بتليجرام بعد — يمكنك نسخ رابط قناة VIP أدناه وإرساله له يدوياً.</i>"
        )
        web_status_note = (
            "💬 <b>تم إرسال رسالة تأكيد فورية في شات الدعم الفني على الموقع للعميل!</b>"
            if web_support_sent else ""
        )

        success_msg = (
            "👑 <b>تم تفعيل اشتراك PRO بنجاح! 🚀</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>العميل:</b> <code>{clean_email}</code>\n"
            f"📛 <b>الاسم:</b> {user_name}\n"
            f"📅 <b>صلاحية الباقة:</b> <code>{duration_days}</code> يوماً\n"
            f"⏳ <b>ساري حتى:</b> <code>{sub_end_str}</code>\n"
            f"💎 <b>رابط قناة VIP الخاص بالعميل:</b>\n"
            f"{invite_link or 'https://t.me/EGX_Bots'}\n\n"
            f"{tg_status_note}\n"
            f"{web_status_note}\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        send_telegram_message(chat_id, success_msg, reply_markup=ADMIN_REPLY_KEYBOARD)

    except Exception as exc:
        print(f"[SUPPORT_CHAT] quick_activate_pro failed: {exc}")
        send_telegram_message(
            chat_id,
            f"❌ <b>حدث خطأ أثناء التفعيل:</b>\n<code>{exc}</code>",
            reply_markup=ADMIN_REPLY_KEYBOARD
        )

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

    # Process with DeepSeek Support AI Agent in background
    def _run_ai_agent():
        try:
            from api.support_ai_agent import process_support_message_with_deepseek, is_support_ai_enabled
            if is_support_ai_enabled():
                reply = process_support_message_with_deepseek(session_id, content, user_name)
                if reply:
                    _init_supabase()
                    if _supabase:
                        _supabase.table("support_messages").insert({
                            "session_id": session_id,
                            "user_id": session_id,
                            "sender": "admin",
                            "content": reply,
                            "user_name": "المساعد الذكي (DeepSeek)"
                        }).execute()
        except Exception as ai_e:
            print(f"[SUPPORT_CHAT] AI Agent background error: {ai_e}")

    threading.Thread(target=_run_ai_agent, daemon=True).start()

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
        if cb_data == "cmd_activate_prompt":
            _ADMIN_AWAITING_ACTIVATION[chat_id] = {"time": time.time()}
            prompt_text = (
                "⚡ <b>تفعيل باقة PRO السريع للمستخدم</b> 👑\n\n"
                "أرسل الآن إيميل المستخدم (Gmail) لتفعيل حسابه فوراً 🚀\n\n"
                "أو اكتب:\n"
                "<code>/activate email@gmail.com 30</code>\n\n"
                "💡 <i>(إذا كتبت الإيميل فقط سيتم تفعيله لمدة 30 يوماً تلقائياً)</i>\n"
                "<i>للإلغاء أرسل: إلغاء</i>"
            )
            send_telegram_message(chat_id, prompt_text)
            return
        elif cb_data == "cmd_users":
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
            "القائمة", "مساعدة", "اوامر", "الأوامر", "أوامر",
            "⚡ تفعيل pro سريع", "تفعيل pro", "تفعيل برو", "تفعيل",
            "الغاء", "إلغاء", "خروج"
        )
        or EMAIL_ACTIVATION_CMD_REGEX.match(clean_cmd) is not None
        or (chat_id in _ADMIN_AWAITING_ACTIVATION and EMAIL_FINDER_REGEX.search(text) is not None)
        or (chat_id not in _ADMIN_ACTIVE_SESSIONS and EMAIL_FINDER_REGEX.search(text) is not None)
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

    # A. Check explicit command: /activate email [days] or تفعيل email [days]
    act_match = EMAIL_ACTIVATION_CMD_REGEX.match(text.strip())
    if act_match:
        target_email = act_match.group(1)
        days = int(act_match.group(2)) if act_match.group(2) else 30
        _ADMIN_AWAITING_ACTIVATION.pop(chat_id, None)
        quick_activate_pro(chat_id, target_email, days)
        return

    # B. Check prompt click or command without email
    if clean_cmd in ("⚡ تفعيل pro سريع", "تفعيل pro", "تفعيل برو", "تفعيل", "/activate", "/pro", "⚡ تفعيل pro"):
        _ADMIN_AWAITING_ACTIVATION[chat_id] = {"time": time.time()}
        prompt_text = (
            "⚡ <b>تفعيل باقة PRO السريع للمستخدم</b> 👑\n\n"
            "أرسل الآن إيميل المستخدم (Gmail) لتفعيل حسابه فوراً 🚀\n\n"
            "أو اكتب:\n"
            "<code>/activate email@gmail.com 30</code>\n\n"
            "💡 <i>(إذا كتبت الإيميل فقط سيتم تفعيله لمدة 30 يوماً تلقائياً)</i>\n"
            "<i>للإلغاء أرسل: إلغاء</i>"
        )
        send_telegram_message(chat_id, prompt_text)
        return

    # C. If awaiting activation input
    if chat_id in _ADMIN_AWAITING_ACTIVATION:
        active_prompt = _ADMIN_AWAITING_ACTIVATION[chat_id]
        if time.time() - active_prompt.get("time", 0) < 600:  # 10 min window
            if clean_cmd in ("الغاء", "إلغاء", "cancel", "/cancel", "خروج"):
                _ADMIN_AWAITING_ACTIVATION.pop(chat_id, None)
                send_telegram_message(chat_id, "تم إلغاء عملية التفعيل.", reply_markup=ADMIN_REPLY_KEYBOARD)
                return

            email_match = EMAIL_FINDER_REGEX.search(text)
            if email_match:
                target_email = email_match.group(1)
                days = 30
                for p in text.split():
                    if p.isdigit():
                        days = int(p)
                        break
                _ADMIN_AWAITING_ACTIVATION.pop(chat_id, None)
                quick_activate_pro(chat_id, target_email, days)
                return

    # D. If admin pasted an email directly without prompt (and not inside customer support session)
    if not session_id and chat_id not in _ADMIN_ACTIVE_SESSIONS:
        standalone_email = EMAIL_FINDER_REGEX.search(text)
        if standalone_email:
            target_email = standalone_email.group(1)
            days = 30
            for p in text.split():
                if p.isdigit():
                    days = int(p)
                    break
            quick_activate_pro(chat_id, target_email, days)
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

    # If admin explicitly addresses AI with /ai or ذكاء or مساعد or asks AI assistant
    if clean_cmd.startswith(("/ai", "ai ", "ذكاء", "مساعد", "بوت")):
        try:
            from api.support_ai_agent import process_support_message_with_deepseek, is_support_ai_enabled
            if is_support_ai_enabled():
                ai_query = re.sub(r'^(?:/ai|ai|ذكاء|مساعد|بوت)\s*', '', text, flags=re.IGNORECASE).strip()
                ai_reply = process_support_message_with_deepseek(
                    session_id=f"admin_{chat_id}",
                    user_message=ai_query or text,
                    user_name="Admin"
                )
                if ai_reply:
                    send_telegram_message(chat_id, ai_reply, reply_markup=ADMIN_REPLY_KEYBOARD)
                    return
        except Exception as ai_err:
            print(f"[SUPPORT_CHAT] Admin AI fallback warning: {ai_err}")

    # Fallback for arbitrary messages when no active customer session exists
    guide_text = (
        "ℹ️ <b>لم يتم إرسال الرسالة لعدم وجود جلسة دعم فني نشطة حالياً.</b>\n\n"
        "للرد على عميل:\n"
        "• اضغط <b>Reply (رد)</b> على رسالة طلب الدعم الخاصة بالعميل.\n\n"
        "📊 أو استخدم الأزرار أدناه لعرض التقارير والإحصائيات اللحظية."
    )
    send_telegram_message(chat_id, guide_text, reply_markup=ADMIN_REPLY_KEYBOARD)
