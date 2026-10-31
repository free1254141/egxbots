#!/usr/bin/env python3
"""
Publish Affiliate Program Announcement to Telegram channel/topic.
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(base_dir, ".env"))
load_dotenv(os.path.join(base_dir, "web", ".env.local"), override=True)

bot_token = os.getenv("ARTORO_AI_BOT", "").strip()
if not bot_token:
    print("❌ ARTORO_AI_BOT token missing!")
    sys.exit(1)

raw_target = os.getenv("TELEGRAM_FREE_CHAT_ID", "-1002083067817_153").strip()
if "_" in raw_target:
    chat_id, thread_id_str = raw_target.split("_", 1)
    thread_id = int(thread_id_str)
else:
    chat_id = raw_target
    thread_id = None

banner_path = os.path.join(base_dir, "egx_bots_facebook_banner.jpg")

caption = (
    "🚀 <b>فرصة دخل إضافي لكل متداول وصانع محتوى في البورصة المصرية! 💰📈</b>\n\n"
    "عندك أصدقاء بيتداولوا في البورصة، أو عندك قناة / جروب مهتم بالأسهم؟\n"
    "دلوقتي تقدر تشارك رابط أو كود الخصم الخاص بك في منصة <b>EGX BOTS</b> وتربح <b>25% عمولة كاش فوري</b> على كل اشتراك! 💸\n\n"
    "🔹 <b>مميزات برنامج شركاء النجاح:</b>\n"
    "1️⃣ <b>هدية لصديقك:</b> بيحصل على خصم فوري 10% عند استخدام كودك.\n"
    "2️⃣ <b>عمولتك 25% كاش:</b> بتتحول مباشرة على رقم محفظتك الإلكترونية (فودافون كاش / اتصالات كاش / أورنج كاش / وي باي).\n"
    "3️⃣ <b>أرباح فورية:</b> بتوصل لـ 506 ج.م على عملية الاشتراك الواحدة!\n"
    "4️⃣ <b>لوحة تحكم حية:</b> بتتابع الزيارات، المشتركين، والرصيد لحظة بلحظة.\n\n"
    "⚡ <b>ابدأ في 10 ثواني:</b> أدخل رقم محفظتك واستلم رابطك وكود الخصم فوراً 👇"
)

inline_keyboard = {
    "inline_keyboard": [
        [
            {"text": "💰 استلم رابط الإحالة الخاص بك (اربح 25% كاش)", "url": "https://egxbots.com/affiliate"}
        ],
        [
            {"text": "📊 باقات الاشتراك", "url": "https://egxbots.com/pricing"},
            {"text": "🌐 منصة EGX BOTS", "url": "https://egxbots.com"}
        ]
    ]
}

print(f"Target chat_id: {chat_id}, thread_id: {thread_id}")
print(f"Caption length: {len(caption)} chars")

success = False
if os.path.exists(banner_path):
    print("Sending with banner photo...")
    url_photo = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    data = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(inline_keyboard),
    }
    if thread_id:
        data["message_thread_id"] = thread_id

    try:
        with open(banner_path, "rb") as f:
            resp = requests.post(url_photo, data=data, files={"photo": f}, timeout=45)
        res = resp.json()
        if resp.status_code == 200 and res.get("ok"):
            success = True
            msg_id = res['result']['message_id']
            print(f"✅ Successfully posted banner message to Telegram! Message ID: {msg_id}")
        else:
            print("Photo send response error:", res)
    except Exception as e:
        print("Error sending photo:", e)

if not success:
    print("Sending text message...")
    url_msg = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": caption,
        "parse_mode": "HTML",
        "reply_markup": inline_keyboard,
    }
    if thread_id:
        payload["message_thread_id"] = thread_id
    resp = requests.post(url_msg, json=payload, timeout=30)
    res = resp.json()
    if resp.status_code == 200 and res.get("ok"):
        msg_id = res['result']['message_id']
        print(f"✅ Successfully posted text message to Telegram! Message ID: {msg_id}")
    else:
        print("❌ Failed to send text message:", res)
        sys.exit(1)
