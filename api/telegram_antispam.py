"""
Telegram Anti-Spam & Auto-Ban Shield for EGX Bots Community.
Detects and deletes spam (e.g. Cyrillic/Russian job scams, unauthorized promo bots)
and permanently bans the offenders.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional
import requests

logger = logging.getLogger("telegram_antispam")


def is_spam_message(text: str, caption: str = "") -> bool:
    """Check if the text or caption contains spam signatures (Cyrillic or known scams)."""
    full_text = f"{text or ''} {caption or ''}".strip()
    if not full_text:
        return False

    # 1. Cyrillic detection (Egyptian stock community is Arabic/English/numbers only)
    has_cyrillic = any("\u0400" <= ch <= "\u04ff" for ch in full_text)
    if has_cyrillic:
        return True

    # 2. Known scam keywords in non-Arabic
    lower = full_text.lower()
    spam_patterns = [
        r"завод[а-я]* кирпич",
        r"подработк[а-я]*",
        r"курьер[а-я]*",
        r"водительск[а-я]*",
        r"пишите в личку",
    ]
    for pat in spam_patterns:
        if re.search(pat, lower):
            return True

    return False


def check_and_handle_spam(msg: Optional[Dict[str, Any]], bot_token: str) -> bool:
    """
    Checks if an incoming message in a group/supergroup is spam.
    If spam:
      1. Calls deleteMessage to remove it immediately.
      2. Calls banChatMember to ban the spammer permanently.
      3. Sends a notification to the admin chat.
    Returns True if spam was detected and handled, False otherwise.
    """
    if not msg or not isinstance(msg, dict) or not bot_token:
        return False

    chat = msg.get("chat") or {}
    chat_type = str(chat.get("type") or "")
    chat_id = chat.get("id")

    # Only inspect group/supergroup messages
    if chat_type not in ("group", "supergroup"):
        return False

    text = str(msg.get("text") or "")
    caption = str(msg.get("caption") or "")

    if not is_spam_message(text, caption):
        return False

    msg_id = msg.get("message_id")
    from_user = msg.get("from") or {}
    user_id = from_user.get("id")
    first_name = str(from_user.get("first_name") or "")
    last_name = str(from_user.get("last_name") or "")
    user_name = f"{first_name} {last_name}".strip() or str(from_user.get("username") or "مستخدم مجهول")
    username = str(from_user.get("username") or "")

    # Don't ban admins / bots
    if from_user.get("is_bot") and str(user_id) == str(bot_token.split(":")[0]):
        return False

    logger.warning(f"[ANTI-SPAM] Cyrillic spam detected from user {user_id} ({user_name}) in chat {chat_id}, msg {msg_id}")

    # 1. Delete message immediately
    if msg_id and chat_id:
        try:
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/deleteMessage",
                json={"chat_id": chat_id, "message_id": msg_id},
                timeout=10,
            )
        except Exception as e:
            logger.error(f"[ANTI-SPAM] Failed to delete spam message {msg_id}: {e}")

    # 2. Ban spammer permanently from the group
    if user_id and chat_id:
        try:
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/banChatMember",
                json={"chat_id": chat_id, "user_id": user_id},
                timeout=10,
            )
        except Exception as e:
            logger.error(f"[ANTI-SPAM] Failed to ban spam user {user_id}: {e}")

    # 3. Notify Admin
    admin_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID") or "5149631436"
    try:
        sample_txt = (text or caption)[:120].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        admin_alert = (
            f"🛡️ <b>[درع الحماية من السبام]</b>\n"
            f"تم رصد وحظر سبام روسي تلقائياً ومسح رسالته فوراً من المجموعة!\n\n"
            f"👤 <b>المرسل:</b> {user_name} (@{username if username else 'بدون معرف'})\n"
            f"🆔 <b>المعرف:</b> <code>{user_id}</code>\n"
            f"💬 <b>نص الرسالة:</b>\n<i>{sample_txt}</i>"
        )
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": admin_id, "text": admin_alert, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        logger.error(f"[ANTI-SPAM] Failed to notify admin: {e}")

    return True
