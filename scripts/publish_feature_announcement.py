#!/usr/bin/env python3
"""
Publish new feature announcement to Telegram and Facebook Page.
Feature: Autonomous AI Recommendations Mode + Chat Wallpapers & Mobile UI.
"""
import os
import sys
import json
import logging
import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("feature_announcement")

# Load environment
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

load_dotenv(os.path.join(base_dir, ".env"))
load_dotenv(os.path.join(base_dir, "web", ".env.local"), override=True)

from api.short_swings_daily import _get_supabase_client
from api.social_facebook_publisher import get_facebook_credentials

TELEGRAM_BOT_TOKEN = os.getenv("ARTORO_AI_BOT", "").strip()
TELEGRAM_FREE_CHAT_ID = "-1002083067817"
TELEGRAM_FREE_THREAD_ID = 153
TELEGRAM_VIP_CHAT_ID = os.getenv("TELEGRAM_PRO_CHAT_ID", "-1003906516349").strip()

# Image banner path
BANNER_PATH = os.path.join(base_dir, "egx_bots_facebook_banner.jpg")

TELEGRAM_CAPTION_HTML = """🚀 <b>تحديث جديد في EGX Bots AI: الذكاء الاصطناعي يقترح عليك أفضل الصفقات!</b> 🤖📈

لكل متداولي البورصة المصرية 🇪🇬.. شات الذكاء الاصطناعي أصبح أكثر ذكاءً بميزات جديدة:

🌟 <b>1. وضع التوصيات الحرة المستقلة (Autonomous AI):</b>
• اسأل الذكاء الاصطناعي مباشرة حسب خطتك وظروفك:
💬 <i>«معايا 10 آلاف لأسبوعين، اقترح عليا أفضل الأسهم؟»</i>
• يمسح السيولة والتجميع والمؤشرات الفنية ويعطيك:
  ✅ مناطق الدخول الآمنة والدعوم.
  ✅ المستهدفات السعرية وجني الأرباح.
  ✅ نقاط وقف الخسارة الصارمة لحماية رأس مالك.

🛡️ <b>2. تحكم كامل وإلغاء فوري بالمحادثة:</b>
• الميزة اختيارية وبإخلاء مسؤولية صريح.
• أوقفها بأي وقت بالمحادثة؛ فقط قل له: <b>«اقفله»</b> أو <b>«عطله»</b> وسيعود فوراً للوضع القياسي!

🎨 <b>3. خلفيات وتخصيص الشات (Wallpapers):</b>
• خلفيات مريحة مثل واتساب، ودعم للوضع الليلي والفاتح والموبايل.

💡 <b>جرّب الميزة الجديدة الآن مجاناً:</b>
👉 <a href="https://egxbots.com/chat">اضغط هنا لبدء محادثة مع الذكاء الاصطناعي</a>

#البورصة_المصرية #EGX30 #الذكاء_الاصطناعي #EGXBots"""

FACEBOOK_CAPTION = """🚀 تحديث ثوري جديد في EGX Bots AI: الذكاء الاصطناعي يقترح عليك أفضل الصفقات بحرية تامة وبطلبك! 🤖📈

لكل مستثمري ومتداولي البورصة المصرية 🇪🇬.. شات الذكاء الاصطناعي في منصة EGX Bots أصبح الآن أكثر قوة وذكاءً مع باقة من الميزات الحصرية الجديدة كلياً:

🌟 1. وضع التوصيات الحرة المستقلة (Autonomous AI Mode):
• مش محتاج تدور بنفسك أو تحتار! تقدر تسأل الذكاء الاصطناعي مباشرة حسب خطتك وظروفك:
💬 «معايا 10 آلاف جنيه وعايز أسيبهم أسبوعين في السوق، اقترح عليا أفضل الأسهم وفرص الدخول؟»
• الذكاء الاصطناعي هيمسح بيانات ومؤشرات الجلسة، السيولة الذكية، ومراحل التجميع المؤسسي، ويرتبلك خطة واضحة ومحسوبة بالمليم:
  ✅ مناطق الدخول الآمنة والدعوم الفنية.
  ✅ المستهدفات السعرية وفرص جني الأرباح.
  ✅ نقاط وقف الخسارة الصارمة لحماية رأس مالك.
  ✅ توزيع المحفظة وإدارة المخاطر.

🛡️ 2. تحكم كامل وإخلاء مسؤولية فوري وشفاف:
• الميزة اختيارية بالكامل وبموافقتك، مع إخلاء مسؤولية واضح.
• والأجمل: تقدر تتحكم فيها بالمحادثة المباشرة! لو حبيت توقفها في أي وقت، بس قوله في الشات: «اقفله» أو «عطله»، وهيطفي الوضع فورياً ويرجع للوضع القياسي المعتمد!

🎨 3. تخصيص كامل لواجهة الشات والخلفيات (Chat Wallpapers):
• تجربة استخدام راقية شبيهة بواتساب؛ تقدر تختار خلفيات أنيقة ومريحة للعين أو ترفع خلفيتك الخاصة.
• دعم كامل ومتناسق مع الوضعين الليلي (Dark Mode) والفاتح (Light Mode) وسلاسة تامة على شاشات الموبايل.

💡 جرّب الميزة الجديدة الآن مجاناً وشاركنا تجربتك:
🔗 رابط الشات المباشر: https://egxbots.com/chat
🌐 رابط المنصة: https://egxbots.com

#البورصة_المصرية #EGX30 #EGX70 #الذكاء_الاصطناعي #تداول #استثمار #EGXBots #تحليل_فني #أسهم_مصر"""


def send_to_telegram(chat_id: str, message_thread_id: int = None, channel_name: str = "Telegram"):
    """Send announcement photo with caption to Telegram channel."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error(f"❌ Telegram bot token missing for {channel_name}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    
    try:
        if os.path.exists(BANNER_PATH):
            with open(BANNER_PATH, "rb") as photo_file:
                data = {
                    "chat_id": chat_id,
                    "caption": TELEGRAM_CAPTION_HTML,
                    "parse_mode": "HTML",
                }
                if message_thread_id:
                    data["message_thread_id"] = message_thread_id
                
                logger.info(f"📤 Sending photo announcement to {channel_name} (Chat ID: {chat_id}, Thread: {message_thread_id})...")
                resp = requests.post(url, data=data, files={"photo": photo_file}, timeout=45)
        else:
            # Fallback to sendMessage if banner is missing
            url_msg = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": TELEGRAM_CAPTION_HTML,
                "parse_mode": "HTML",
            }
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id
            resp = requests.post(url_msg, json=payload, timeout=30)

        result = resp.json()
        if resp.status_code == 200 and result.get("ok"):
            msg_id = result.get("result", {}).get("message_id")
            logger.info(f"✅ Successfully posted to {channel_name}! Message ID: {msg_id}")
            return True
        else:
            logger.warning(f"⚠️ Photo send failed ({result}), falling back to sendMessage...")
            url_msg = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": TELEGRAM_CAPTION_HTML,
                "parse_mode": "HTML",
            }
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id
            resp2 = requests.post(url_msg, json=payload, timeout=30)
            res2 = resp2.json()
            if resp2.status_code == 200 and res2.get("ok"):
                msg_id = res2.get("result", {}).get("message_id")
                logger.info(f"✅ Successfully posted to {channel_name} via sendMessage! Message ID: {msg_id}")
                return True
            logger.error(f"❌ Failed to post to {channel_name}: {res2}")
            return False
    except Exception as e:
        logger.error(f"❌ Exception posting to {channel_name}: {e}")
        return False


def send_to_facebook():
    """Publish photo announcement to Facebook Page."""
    try:
        supabase = _get_supabase_client()
        creds = get_facebook_credentials(supabase)
        if not creds or not creds.get("token"):
            logger.error("❌ Facebook credentials not found")
            return False

        page_id = creds["page_id"]
        token = creds["token"]

        url = f"https://graph.facebook.com/v19.0/{page_id}/photos"

        if os.path.exists(BANNER_PATH):
            with open(BANNER_PATH, "rb") as photo_file:
                logger.info(f"📤 Uploading photo announcement to Facebook Page {page_id}...")
                resp = requests.post(
                    url,
                    data={
                        "caption": FACEBOOK_CAPTION,
                        "access_token": token,
                    },
                    files={"source": photo_file},
                    timeout=60,
                )
        else:
            # Fallback to public URL or feed
            logger.info("Banner file not found, publishing to Facebook feed...")
            feed_url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
            resp = requests.post(
                feed_url,
                data={
                    "message": FACEBOOK_CAPTION,
                    "link": "https://egxbots.com/chat",
                    "access_token": token,
                },
                timeout=30,
            )

        result = resp.json()
        if resp.status_code == 200 and ("id" in result or "post_id" in result):
            post_id = result.get("id") or result.get("post_id")
            logger.info(f"✅ Successfully published to Facebook Page! Post ID: {post_id}")
            return post_id
        else:
            logger.error(f"❌ Failed to publish to Facebook Page: {result}")
            return False
    except Exception as e:
        logger.error(f"❌ Exception publishing to Facebook: {e}")
        return False


def main():
    logger.info("========================================")
    logger.info("🚀 Starting Multi-Channel Feature Announcement")
    logger.info("========================================")

    # 1. Telegram Free Channel (with thread 153)
    tg_free_ok = send_to_telegram(
        chat_id=TELEGRAM_FREE_CHAT_ID,
        message_thread_id=TELEGRAM_FREE_THREAD_ID,
        channel_name="Telegram Public Channel (Thread 153)"
    )

    # 2. Telegram VIP / Pro Channel
    tg_vip_ok = send_to_telegram(
        chat_id=TELEGRAM_VIP_CHAT_ID,
        channel_name="Telegram VIP Pro Channel"
    )

    # 3. Facebook Page
    # fb_post_id was already successfully published: 122142984957385797
    fb_post_id = "122142984957385797 (Already Published)"

    logger.info("========================================")
    logger.info("📢 Announcement Dispatch Summary:")
    logger.info(f"• Telegram Public Channel: {'✅ Success' if tg_free_ok else '❌ Failed'}")
    logger.info(f"• Telegram VIP Channel:    {'✅ Success' if tg_vip_ok else '❌ Failed'}")
    logger.info(f"• Facebook Page:           {'✅ Success (Post ID: ' + str(fb_post_id) + ')' if fb_post_id else '❌ Failed'}")
    logger.info("========================================")


if __name__ == "__main__":
    main()
