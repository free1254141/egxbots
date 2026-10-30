"""
jobs/founders_campaign.py — Broadcast & Direct Campaign Engine for 100 Founders Offer.

Features:
- Targets active users who haven't subscribed to Pro yet.
- Scarcity-focused copy for Founders Plan (50 EGP/month lifetime).
- Direct Telegram DM via egxbots_bot with interactive inline keyboard buttons.
- Public/Free channel broadcast option.
- Idempotency and cooldown tracking via `marketing_message_log`.
- Safe dry-run mode by default.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from api.stock_ai import supabase

APP_URL = os.getenv("NEXT_PUBLIC_APP_URL", "https://egxbots.com").rstrip("/")
API_TIMEOUT = 20


def get_telegram_token() -> str:
    token = (
        os.getenv("ARTORO_AI_BOT")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or os.getenv("SUBSCRIPTION_REMINDER_BOT_TOKEN")
        or ""
    ).strip()
    if not token:
        raise RuntimeError("Missing required secret: ARTORO_AI_BOT or TELEGRAM_BOT_TOKEN")
    return token


def build_founders_announcement_text(user_name: Optional[str] = None) -> str:
    greeting = f"أهلاً بك يا {user_name} 👋" if user_name and user_name != "N/A" else "أهلاً بك صديقنا العزيز 👋"
    return (
        "⚡ <b>عرض المؤسسين لفترة محدودة (15 يوماً فقط) | EGX BOTS PRO</b>\n\n"
        f"{greeting}\n\n"
        "نود تذكيرك بأن <b>عرض باقة المؤسسين (100 ج.م شهرياً مدى الحياة بدلاً من 200 ج.م)</b> متاح حالياً لمدة 15 يوماً فقط! ويثبت هذا السعر لحسابك مدى الحياة طالما تجدد مع مهلة 72 ساعة لتثبيت السعر عند كل تجديد.\n\n"
        "🎯 <b>أدوات ومزايا باقة Pro الرقمية:</b>\n"
        "• <b>مساعد الشات بوت الذكي (AI Chatbot):</b> شات بوت متطور لتحليل أي سهم، فحص الدعوم والمقاومات، مقارنة الأسهم ومراجعة المحفظة لحظياً عبر الموقع وتليجرام (350 استفساراً شهرياً).\n"
        "• <b>إشارات ونماذج السوينج الفنية:</b> رصد مؤتمت لنقاط المراقبة والمستويات السعرية المستهدفة ومستويات إدارة المخاطر.\n"
        "• <b>ماسح التجميع والسيولة الذكية:</b> فحص كمي وإحصائي لحظي لحركة التداول والسيولة بالبورصة المصرية.\n"
        "• <b>قناة التنبيهات الفنية VIP:</b> إشعارات رقمية فورية لاكتمال النماذج الفنية الفورية.\n"
        "• <b>تثبيت السعر مدى الحياة:</b> اشتراكك البرمجي يثبت بـ 100 ج.م شهرياً دائماً ما دمت مجدداً لاشتراكك دون أي زيادة.\n\n"
        "💡 <i>يمكنك تجربة كافة أدوات Pro البرمجية مجاناً لمدة 3 أيام بضغطة زر واحدة!</i>\n\n"
        "⚠️ <i>تنبيه قانوني وإخلاء مسؤولية: المنصة برمجية للتحليل الفني والكمي ولا تقدم توصيات استثمارية أو استشارات مالية أو إدارة محافظ. قرارات التداول مسؤوليتك المستقلة عبر شركة سمسرة مرخصة من الهيئة العامة للرقابة المالية (FRA).</i>"
    )


def get_founders_inline_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "⚡ اشترك بـ 100 ج.م شهرياً (تثبيت مدى الحياة)", "url": f"{APP_URL}/pricing?plan=pro"}],
            [{"text": "🎁 تفعيل التجربة المجانية (3 أيام)", "url": f"{APP_URL}/pricing"}],
        ]
    }


def send_telegram_campaign_message(
    chat_id: int | str,
    text: str,
    reply_markup: Optional[dict] = None,
    token: Optional[str] = None,
) -> bool:
    token = token or get_telegram_token()
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    relay = (os.getenv("TELEGRAM_RELAY_URL") or "https://api.telegram.org").strip().rstrip("/")
    bases = [relay] if relay != "https://api.telegram.org" else []
    bases.append("https://api.telegram.org")

    for base in bases:
        try:
            resp = requests.post(f"{base}/bot{token}/sendMessage", json=payload, timeout=API_TIMEOUT)
            if resp.status_code == 200 and resp.json().get("ok"):
                return True
            time.sleep(0.5)
        except Exception as e:
            print(f"[CAMPAIGN] Telegram send error to {chat_id} via {base}: {e}")
            continue

    return False


def get_active_target_users(cooldown_days: int = 7) -> List[Dict[str, Any]]:
    """
    Fetches active free users who have connected telegram_chat_id,
    excluding users with active Pro subscriptions and those messaged within cooldown.
    """
    if not supabase:
        return []

    # 1. Active Pro subscriptions
    active_subs = (
        supabase.table("subscriptions")
        .select("user_id")
        .eq("status", "active")
        .execute()
        .data or []
    )
    active_uids = {s["user_id"] for s in active_subs}

    # 2. Profiles with telegram_chat_id
    profiles = (
        supabase.table("profiles")
        .select("id, username, display_name, telegram_chat_id, updated_at")
        .not_.is_("telegram_chat_id", "null")
        .order("updated_at", desc=True)
        .limit(100)
        .execute()
        .data or []
    )

    cutoff = (datetime.now(timezone.utc) - timedelta(days=cooldown_days)).isoformat()
    candidates = []

    for p in profiles:
        uid = p.get("id")
        chat_id = p.get("telegram_chat_id")
        if not uid or not chat_id or uid in active_uids:
            continue

        # Check cooldown
        try:
            recent_log = (
                supabase.table("marketing_message_log")
                .select("id")
                .eq("user_id", uid)
                .eq("message_type", "founders_offer")
                .gte("sent_at", cutoff)
                .limit(1)
                .execute()
                .data or []
            )
            if recent_log:
                continue
        except Exception:
            pass

        candidates.append({
            "user_id": uid,
            "display_name": p.get("display_name") or p.get("username") or "صديقنا المستثمر",
            "telegram_chat_id": chat_id,
            "updated_at": p.get("updated_at"),
        })

    return candidates


def run_campaign(
    send_telegram: bool = False,
    preview_admin: bool = False,
    broadcast_free_channel: bool = False,
) -> Dict[str, Any]:
    token = get_telegram_token()
    admin_chat = os.getenv("SUPPORT_ADMIN_CHAT_ID", "5149631436")
    free_channel = os.getenv("TELEGRAM_FREE_CHAT_ID")

    results: Dict[str, Any] = {
        "preview_sent": False,
        "channel_sent": False,
        "direct_sent_count": 0,
        "candidates_count": 0,
        "dry_run": not (send_telegram or preview_admin or broadcast_free_channel),
    }

    # 1. Admin Preview
    if preview_admin:
        preview_text = build_founders_announcement_text("أدمن EGX BOTS")
        ok = send_telegram_campaign_message(
            chat_id=admin_chat,
            text=preview_text,
            reply_markup=get_founders_inline_keyboard(),
            token=token,
        )
        results["preview_sent"] = ok
        print(f"[CAMPAIGN] Admin preview sent to {admin_chat}: {ok}")

    # 2. Channel Broadcast
    if broadcast_free_channel and free_channel:
        channel_text = build_founders_announcement_text()
        ok = send_telegram_campaign_message(
            chat_id=free_channel,
            text=channel_text,
            reply_markup=get_founders_inline_keyboard(),
            token=token,
        )
        results["channel_sent"] = ok
        print(f"[CAMPAIGN] Free channel broadcast sent to {free_channel}: {ok}")

    # 3. Direct Telegram DMs to Active Candidates
    candidates = get_active_target_users(cooldown_days=7)
    results["candidates_count"] = len(candidates)
    print(f"[CAMPAIGN] Found {len(candidates)} eligible active candidates for direct DM.")

    if send_telegram:
        for user in candidates:
            uid = user["user_id"]
            cid = user["telegram_chat_id"]
            name = user["display_name"]
            msg = build_founders_announcement_text(name)
            success = send_telegram_campaign_message(
                chat_id=cid,
                text=msg,
                reply_markup=get_founders_inline_keyboard(),
                token=token,
            )
            if success:
                results["direct_sent_count"] += 1
                try:
                    supabase.table("marketing_message_log").insert({
                        "user_id": uid,
                        "email": f"telegram:{cid}",
                        "message_type": "founders_offer",
                        "channel": "telegram",
                        "status": "sent",
                        "metadata": {"chat_id": cid, "name": name},
                    }).execute()
                except Exception as log_err:
                    print(f"[CAMPAIGN] Warning: could not log to marketing_message_log: {log_err}")
                print(f"[CAMPAIGN] Direct DM sent to {name} (chat_id: {cid})")
            time.sleep(1.0)  # Safe rate limit between messages

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EGX BOTS 100 Founders Campaign")
    parser.add_argument("--preview-admin", action="store_true", help="Send preview to admin Telegram")
    parser.add_argument("--broadcast-channel", action="store_true", help="Broadcast to public/free Telegram channel")
    parser.add_argument("--send-telegram", action="store_true", help="Send direct DM to active free users")
    args = parser.parse_args()

    res = run_campaign(
        send_telegram=args.send_telegram,
        preview_admin=args.preview_admin,
        broadcast_free_channel=args.broadcast_channel,
    )
    print(f"[CAMPAIGN] Execution finished: {res}")
