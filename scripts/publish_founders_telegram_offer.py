#!/usr/bin/env python3
"""
Publish Founders Offer announcement to Telegram channel and group topic.
Feature Highlights: Portfolio Image Analysis (Vision AI) + Live Recommendations + 50 EGP/mo Founders Offer.
"""
import os
import sys
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
    "🔥 <b>عرض المؤسسين الحصري: 100 ج.م فقط شهرياً (لفترة محدودة 15 يوماً فقط)!</b> 👑🇪🇬\n\n"
    "لكل متداولي البورصة المصرية.. أطلقنا باقة من أقوى ميزات <b>ARTORO AI Pro</b>:\n\n"
    "📸 <b>1. تحليل محفظتك من صورة (Vision AI):</b>\n"
    "ارفع سكرين شوت لمحفظتك من (ثندر أو تطبيق وسيطك)، وسيقوم المساعد فوراً بقراءة الأسهم، حساب نسب السيولة، وتحليل المخاطر وتحديد الدعوم والمستهدفات لكل سهم!\n\n"
    "🎯 <b>2. التوصيات اللحظية وصفقات الزخم السريعة (0 تأخير):</b>\n"
    "إشارات دخول يومية مدروسة، مستهدفات جني الأرباح، ووقف خسارة صارم، مع وصول فوري لقناة الـ VIP الخاصة.\n\n"
    "🤖 <b>3. وضع التوصيات الحرة المستقلة:</b>\n"
    "اطلب من المساعد اقتراح أفضل صفقات الجلسة برؤية فنية ورقمية مستقلة.\n\n"
    "🚀 <b>4. شات ذكي 350 استشارة شهرياً + معمل الشارت المتكامل.</b>\n\n"
    "⚡ <b>اشترك الآن بـ 100 ج.م شهرياً (بدلاً من 200 ج.م) مع مهلة 72 ساعة لتثبيت السعر عند التجديد:</b>\n"
    "👉 <a href=\"https://egxbots.com/pricing?plan=pro\">اضغط هنا للاشتراك في عرض المؤسسين 👑</a>\n"
    "💬 <a href=\"https://egxbots.com/chat\">تجربة المساعد الذكي الآن</a>"
)

print(f"Caption length: {len(caption)} chars (limit: 1024)")
print(f"Target chat_id: {chat_id}, thread_id: {thread_id}")

url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
data = {
    "chat_id": chat_id,
    "caption": caption,
    "parse_mode": "HTML",
}
if thread_id:
    data["message_thread_id"] = thread_id

inline_keyboard = {
    "inline_keyboard": [
        [
            {"text": "👑 اشترك بـ 50 ج.م (عرض المؤسسين)", "url": "https://egxbots.com/pricing?plan=pro"},
        ],
        [
            {"text": "💬 جرب الشات الذكي", "url": "https://egxbots.com/chat"},
            {"text": "🌐 زيارة المنصة", "url": "https://egxbots.com"},
        ]
    ]
}
data["reply_markup"] = requests.compat.json.dumps(inline_keyboard)

success = False
if os.path.exists(banner_path):
    print(f"Sending with photo banner {banner_path}...")
    with open(banner_path, "rb") as f:
        resp = requests.post(url, data=data, files={"photo": f}, timeout=45)
    res = resp.json()
    print("Photo send response:", res)
    if resp.status_code == 200 and res.get("ok"):
        success = True
        print(f"✅ Successfully posted photo message to Telegram! Message ID: {res['result']['message_id']}")

if not success:
    print("Falling back to sendMessage...")
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
    print("Text send response:", res)
    if resp.status_code == 200 and res.get("ok"):
        print(f"✅ Successfully posted text message to Telegram! Message ID: {res['result']['message_id']}")
    else:
        print(f"❌ Failed to send message: {res}")
        sys.exit(1)
