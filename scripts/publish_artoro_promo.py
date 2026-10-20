"""Publish Artoro AI promotional announcement to official Facebook Page."""
import json
import logging
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.short_swings_daily import _get_supabase_client
from api.social_facebook_publisher import get_facebook_credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("publish_artoro_promo")

def main():
    client = _get_supabase_client()
    creds = get_facebook_credentials(client)
    if not creds or not creds.get("token"):
        logger.error("Missing Facebook credentials in market_cache / environment")
        sys.exit(1)

    page_id = creds["page_id"]
    token = creds["token"]

    photo_urls = [
        "https://gfcmaxbtscmizsakarvc.supabase.co/storage/v1/object/public/social-reports/promos/artoro/artoro_banner_3d.png",
        "https://gfcmaxbtscmizsakarvc.supabase.co/storage/v1/object/public/social-reports/promos/artoro/artoro_portfolio_overview.png",
        "https://gfcmaxbtscmizsakarvc.supabase.co/storage/v1/object/public/social-reports/promos/artoro/artoro_portfolio_stocks.png",
    ]

    logger.info(f"Uploading {len(photo_urls)} unpublished photos to Facebook Page {page_id}...")
    media_ids = []
    for idx, p_url in enumerate(photo_urls, 1):
        upload_url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
        payload = json.dumps({
            "url": p_url,
            "published": False,
            "access_token": token,
        }).encode("utf-8")
        req = urllib.request.Request(
            upload_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            media_id = res_data.get("id")
            logger.info(f"Photo {idx} uploaded successfully! Media FBID: {media_id}")
            media_ids.append({"media_fbid": media_id})

    caption = (
        "🚀 روبوت الذكاء الاصطناعي الأقوى في البورصة المصرية: أرتورو (ARTORO AI) وصل رسمياً! 🤖📈\n\n"
        "محتار في أسهمك؟ مش عارف توزع محفظتك صح ولا إمتى تخرج وإمتى تزود؟\n"
        "دلوقتي مش محتاج تقعد بالساعات تحسب نسب أو تقرأ شارتات معقدة.. \"أرتورو\" بقى معاك في كل خطوة!\n\n"
        "📸 ميزة ثورية: صور محفظتك وسيب الباقي على أرتورو!\n"
        "سواء محفظتك على ثندر (Thndr) أو هيرميس أو أي شركة سمسرة، كل اللي عليك تاخد سكرين شوت وترفعها في الشات:\n"
        "✅ يقرأ جميع أسهمك، أوزانها، وأسعار الشراء تلقائياً بدقة متناهية.\n"
        "✅ يحلل مخاطر محفظتك ونسب توزيع السيولة بين القطاعات.\n"
        "✅ يقترح عليك خطة إعادة توازن ذكية (Portfolio Rebalancing) لتقليل المخاطر وزيادة فرص الربح.\n\n"
        "💬 محلل فني لحظي في جيبك 24/7 (بالعامية المصرية):\n"
        "اسأل أرتورو كأنك بتكلم خبيرك المالي الموثوق:\n"
        "🔹 «سهم طلعت مصطفى وضعه إيه ومكمل ولا هيصحح؟»\n"
        "🔹 «إيه أفضل نقطة دخول ووقف خسارة في السويدي إليكتريك؟»\n"
        "🔹 «مقارنة سريعة بين أرقام حديد عز ومصر للألومنيوم؟»\n"
        "🔹 يديك الدعم والمقاومة، مناطق السيولة المؤسسية، وإشارات المؤشرات الفنية (RSI, MACD, تجميع السيولة) بلغة سهلة ومباشرة بدون تعقيد!\n\n"
        "📱 متاح الآن بين إيديك على كل المنصات:\n"
        "1️⃣ تطبيق أندرويد متوفر للتحميل المباشر (APK):\n"
        "👉 https://egxbots.com/artoro.apk\n"
        "2️⃣ جرب الشات الذكي مجاناً الآن على موقعنا:\n"
        "👉 https://egxbots.com/chat\n"
        "3️⃣ انضم لقناة ومجتمع EGX BOTS الرسمي على تيليجرام للتنبيهات الفورية:\n"
        "👉 https://t.me/egxbots\n"
        "🤖 شات البوت المباشر على تيليجرام: @egxbots_bot\n\n"
        "ابدأ جلستك القادمة وأنت مسنود بأقوى ذكاء اصطناعي مالي في مصر! 🚀📊\n\n"
        "#البورصة_المصرية #EGX #EGX30 #EGX70 #Artoro #ذكاء_اصطناعي #تداول #استثمار #ثندر #اسهم_مصر #EGX_BOTS"
    )

    feed_url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
    feed_payload = json.dumps({
        "message": caption,
        "attached_media": media_ids,
        "access_token": token,
    }).encode("utf-8")

    feed_req = urllib.request.Request(
        feed_url,
        data=feed_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    logger.info("Publishing multi-photo post to Facebook Page feed...")
    with urllib.request.urlopen(feed_req, timeout=30) as resp:
        feed_res = json.loads(resp.read().decode("utf-8"))
        post_id = feed_res.get("id")
        logger.info(f"SUCCESS: Published post to Facebook feed! Post ID: {post_id}")
        print(f"LIVE_POST_URL: https://www.facebook.com/{post_id}")
        return post_id

if __name__ == "__main__":
    main()
