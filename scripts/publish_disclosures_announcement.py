#!/usr/bin/env python3
"""
Publish new feature announcement for EGX Disclosures Radar & Official PDF Viewer to:
1. Telegram Public Channel (Thread 153)
2. Telegram VIP Pro Channel
3. Facebook Official Page
"""
import os
import sys
import json
import logging
import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("disclosures_announcement")

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

VIDEO_PATH = "C:/Users/MR__CODER__/.gemini/antigravity/brain/4f44c13e-1a12-41ea-bcf3-561da28b931e/.user_uploaded/media_1794137865667_5b45326d.mp4"
PHOTO_LIST_PATH = "C:/Users/MR__CODER__/.gemini/antigravity/brain/4f44c13e-1a12-41ea-bcf3-561da28b931e/.user_uploaded/media_1794137865982_7605f9e2.png"
PHOTO_ZOOM_PATH = "C:/Users/MR__CODER__/.gemini/antigravity/brain/4f44c13e-1a12-41ea-bcf3-561da28b931e/.user_uploaded/media_1794137866030_0579c8b0.jpg"

TELEGRAM_FREE_CAPTION = (
    "🔥 <b>رادار إفصاحات البورصة ومستندات الـ PDF الأصلية بالذكاء الاصطناعي! 📄🤖</b>\n\n"
    "لكل متداولي البورصة المصرية 🇪🇬.. تابع كواليس السوق لحظة بلحظة:\n\n"
    "✨ <b>أبرز مميزات الرادار:</b>\n"
    "📑 <b>1. مستندات PDF أصلية معتمدة:</b>\n"
    "تصفح وحمل ملف الـ PDF الرسمي الصادر من البورصة المصرية لكل إفصاح مباشرة داخل المنصة.\n\n"
    "🧠 <b>2. تحليل فوري بالذكاء الاصطناعي:</b>\n"
    "يشرح لك مغزى كل عملية (شراء/بيع داخلي، تغيير حصص، أحداث جوهرية) وأثرها المالي المتوقع على حركة السهم.\n\n"
    "💬 <b>3. ناقش الإفصاح في الشات:</b>\n"
    "بنقرة واحدة ينتقل الإفصاح لشات الذكاء الاصطناعي لربطه بمستويات الدعم والمقاومة، مع عرض مستند الـ PDF الأصلي بالشات!\n\n"
    "🎛️ <b>4. عرض أفقي وشبكي:</b>\n"
    "اختر بين القائمة الأفقية أو شبكة الكروت المتجاوبة لتصفح فائق السلاسة على الموبايل والكمبيوتر.\n\n"
    "🔗 <b>جرّب الرادار مجاناً الآن:</b>\n"
    "👉 <a href=\"https://egxbots.com/disclosures\">https://egxbots.com/disclosures</a>\n\n"
    "#البورصة_المصرية #EGX30 #إفصاحات #EGXBots #ذكاء_اصطناعي"
)

TELEGRAM_VIP_CAPTION = (
    "👑 <b>تحديث خاص لـ EGX Bots PRO: رادار تعاملات الداخليين والـ PDF المعتمد 📄🔍</b>\n\n"
    "أعضاءنا الكرام.. رصد تحركات المطلعين وكبار المساهمين أصبح بين يديك:\n\n"
    "🎯 <b>كيف تستفيد في صفقاتك؟</b>\n"
    "🔍 <b>1. كشف التجميع المؤسسي والداخلي:</b>\n"
    "راقب صفقات شراء المطلعين ومجموعاتهم المرتبطة (مثل شراء 273 ألف سهم بالعربية للصناعات الهندسية، أو قرارات إمدادات الغاز لموبكو). الذكاء الاصطناعي يحلل هل الشراء تجميع حقيقي أم تصريف.\n\n"
    "📑 <b>2. مستند الـ PDF الأصلي بلمسة زر:</b>\n"
    "معاينة المستند الرسمي للبورصة داخل كل بطاقة دون مغادرة الصفحة مع تحميل فوري.\n\n"
    "🤖 <b>3. ربط فوري بالشات وبوتات التداول:</b>\n"
    "ناقش أثر أي إفصاح مع الشات المالي ليقارنه مع إشارات بوتات التداول ومستويات السيولة.\n\n"
    "📊 <b>تصفح الرادار الآن في حسابك:</b>\n"
    "👉 <a href=\"https://egxbots.com/disclosures\">https://egxbots.com/disclosures</a>\n\n"
    "#EGXBots #VIP #البورصة_المصرية #تداول_احترافي"
)

FACEBOOK_CAPTION = (
    "🚀 إطلاق رسمي جديد في منصة EGX Bots: رادار إفصاحات البورصة المصرية وتعاملات الداخليين بمستندات الـ PDF الأصلية وتحليل الذكاء الاصطناعي! 📄🤖📈\n\n"
    "لكل مستثمري ومتداولي البورصة المصرية 🇪🇬.. خطوة جديدة تجعل بين يديك أقوى ميزة لمتابعة نبض السوق وما يدور خلف الكواليس:\n\n"
    "🌟 مميزات رادار الإفصاحات الجديد كلياً:\n\n"
    "📑 1. استعراض ملفات الـ PDF الأصلية المعتمدة من البورصة:\n"
    "مش مجرد أرقام مجردة! تقدر الآن تشوف وتتصفح مستند الإفصاح الرسمي (PDF) المعتمد من البورصة المصرية مباشرة داخل المنصة، مع إمكانية فتحه بالحجم الكامل أو تحميله على جهازك بضغطة زر واحدة.\n\n"
    "🧠 2. تحليل مالي وفني فوري بالذكاء الاصطناعي:\n"
    "الذكاء الاصطناعي بيلخص ويفسر كل إفصاح باللغة العربية الواضحة:\n"
    "✅ هل العملية شراء داخلي يعكس ثقة الإدارة بالقيمة العادلة؟\n"
    "✅ تفاصيل نسب الحصص قبل وبعد التعامل للمساهمين الرئيسيين.\n"
    "✅ الأثر المتوقع للحدث الجوهري على ربحية الشركة وأسعار التداول.\n\n"
    "💬 3. مناقشة تفاعلية في الشات المالي المباشر:\n"
    "بضغطة واحدة على زر \"ناقش هذا الإفصاح في الشات\"، بينتقل الإفصاح مباشرة لشات الذكاء الاصطناعي، يربطه بمستويات الدعم والمقاومة ومؤشرات الزخم، ويعرضلك مستند الـ PDF الأصلي التفاعلي مباشرة داخل المحادثة!\n\n"
    "🎛️ 4. طريقتين للعرض وسرعة فائقة:\n"
    "اختار طريقة العرض المناسبة ليك سواء العرض الأفقي الشامل (قائمة) أو العرض الشبكي (جريد كروت) المصمم خصيصاً لتجربة تصفح مريحة على الموبايل والديسكتوب.\n\n"
    "💡 ادخل دلوقتي واكتشف أحدث إفصاحات وتحركات الداخليين في السوق:\n"
    "🔗 رابط صفحة الإفصاحات: https://egxbots.com/disclosures\n"
    "🌐 رابط المنصة: https://egxbots.com\n\n"
    "#البورصة_المصرية #EGX30 #EGX70 #إفصاحات #تعاملات_الداخليين #الذكاء_الاصطناعي #EGXBots #تداول #استثمار #أسهم_مصر"
)


def send_video_to_telegram(chat_id: str, caption: str, message_thread_id: int = None, channel_name: str = "Telegram"):
    """Send announcement video with caption to Telegram channel."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error(f"❌ Telegram bot token missing for {channel_name}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    
    try:
        if os.path.exists(VIDEO_PATH):
            logger.info(f"📤 Uploading video ({os.path.getsize(VIDEO_PATH)} bytes) to {channel_name}...")
            with open(VIDEO_PATH, "rb") as video_file:
                data = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "supports_streaming": True,
                }
                if message_thread_id:
                    data["message_thread_id"] = message_thread_id

                resp = requests.post(
                    url,
                    data=data,
                    files={"video": video_file},
                    timeout=180,
                )
        elif os.path.exists(PHOTO_LIST_PATH):
            logger.info(f"Video not found, fallback to photo upload for {channel_name}...")
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            with open(PHOTO_LIST_PATH, "rb") as photo_file:
                data = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                }
                if message_thread_id:
                    data["message_thread_id"] = message_thread_id
                resp = requests.post(url, data=data, files={"photo": photo_file}, timeout=60)
        else:
            logger.error(f"❌ Neither video nor photo found for {channel_name}")
            return False

        res_json = resp.json()
        if res_json.get("ok"):
            logger.info(f"✅ Successfully sent video announcement to {channel_name}!")
            return True
        else:
            logger.error(f"❌ Telegram API Error for {channel_name}: {res_json}")
            return False
    except Exception as e:
        logger.error(f"❌ Exception sending to {channel_name}: {e}")
        return False


def publish_to_facebook():
    """Publish announcement video / photo to Facebook Page via Meta Graph API."""
    try:
        supabase = _get_supabase_client()
        creds = get_facebook_credentials(supabase)
        if not creds or not creds.get("token"):
            logger.error("❌ Facebook credentials not found")
            return False

        page_id = creds["page_id"]
        token = creds["token"]

        # 1. Try uploading video to Facebook Page
        if os.path.exists(VIDEO_PATH):
            logger.info(f"📤 Uploading video announcement to Facebook Page {page_id}...")
            video_url = f"https://graph-video.facebook.com/v19.0/{page_id}/videos"
            with open(VIDEO_PATH, "rb") as video_file:
                resp = requests.post(
                    video_url,
                    data={
                        "description": FACEBOOK_CAPTION,
                        "title": "رادار إفصاحات البورصة المصرية ومستندات الـ PDF الأصلية بالذكاء الاصطناعي 📄🤖",
                        "access_token": token,
                    },
                    files={"source": video_file},
                    timeout=240,
                )
                res = resp.json()
                if resp.status_code == 200 and "id" in res:
                    logger.info(f"✅ Successfully published video to Facebook Page! Video ID: {res['id']}")
                    return res["id"]
                else:
                    logger.warning(f"Video upload returned {resp.status_code}: {res}. Trying photo fallback...")

        # 2. Fallback to Photo upload
        if os.path.exists(PHOTO_LIST_PATH):
            logger.info(f"📤 Uploading photo announcement to Facebook Page {page_id}...")
            photo_url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
            with open(PHOTO_LIST_PATH, "rb") as photo_file:
                resp = requests.post(
                    photo_url,
                    data={
                        "caption": FACEBOOK_CAPTION,
                        "access_token": token,
                    },
                    files={"source": photo_file},
                    timeout=60,
                )
                res = resp.json()
                if resp.status_code == 200 and ("id" in res or "post_id" in res):
                    post_id = res.get("id") or res.get("post_id")
                    logger.info(f"✅ Successfully published photo to Facebook Page! Post ID: {post_id}")
                    return post_id
                else:
                    logger.error(f"❌ Facebook photo upload failed: {res}")
                    return False

        return False
    except Exception as e:
        logger.error(f"❌ Exception publishing to Facebook: {e}")
        return False


def main():
    logger.info("========================================")
    logger.info("🚀 Starting Multi-Channel Announcement for Disclosures Radar")
    logger.info(f"• Telegram Free Caption length: {len(TELEGRAM_FREE_CAPTION)} / 1024")
    logger.info(f"• Telegram VIP Caption length:  {len(TELEGRAM_VIP_CAPTION)} / 1024")
    logger.info("========================================")

    # 1. Telegram Public Channel (Thread 153)
    tg_free_ok = send_video_to_telegram(
        chat_id=TELEGRAM_FREE_CHAT_ID,
        caption=TELEGRAM_FREE_CAPTION,
        message_thread_id=TELEGRAM_FREE_THREAD_ID,
        channel_name="Telegram Public Channel (Thread 153)"
    )

    # 2. Telegram VIP / Pro Channel
    tg_vip_ok = send_video_to_telegram(
        chat_id=TELEGRAM_VIP_CHAT_ID,
        caption=TELEGRAM_VIP_CAPTION,
        channel_name="Telegram VIP Pro Channel"
    )

    # 3. Facebook Page
    fb_post_id = publish_to_facebook()

    logger.info("========================================")
    logger.info("📢 Announcement Dispatch Summary:")
    logger.info(f"• Telegram Public Channel: {'✅ Success' if tg_free_ok else '❌ Failed'}")
    logger.info(f"• Telegram VIP Channel:    {'✅ Success' if tg_vip_ok else '❌ Failed'}")
    logger.info(f"• Facebook Page:           {'✅ Success (Post ID: ' + str(fb_post_id) + ')' if fb_post_id else '❌ Failed'}")
    logger.info("========================================")


if __name__ == "__main__":
    main()
