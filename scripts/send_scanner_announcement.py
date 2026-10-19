import os
import sys
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

token = os.getenv("ARTORO_AI_BOT", "").strip()
if not token:
    print("Error: ARTORO_AI_BOT token not found in environment")
    sys.exit(1)

chat_id = "-1002083067817"
message_thread_id = 1
image_path = os.path.abspath(r"C:/Users/MR__CODER__/.gemini/antigravity/brain/0dfb0046-156e-44da-9df3-72fc3ae17bd8/.user_uploaded/media_1792444484349_fc25cb67.png")

caption = (
    "🚀 <b>تحديث هام وكبير في EGX BOTS | شارت الـ 15 دقيقة اللحظي ورادار الإسكانر!</b> ⚡\n\n"
    "يسعدنا إطلاق أقوى أدوات التداول اللحظي ومتابعة صفقات الإسكانر بالبورصة المصرية:\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🔥 <b>رادار لحظي أثناء الجلسة:</b>\n"
    "• رصد انفجارات وتجميع السيولة (Volume Surge 2.5x+)\n"
    "• رصد الاختراقات الفنية اللحظية (Breakouts)\n"
    "• رصد ارتدادات القاع والتشبع البيعي (RSI Bounce)\n\n"
    "📊 <b>شارت شموع 15 دقيقة تفاعلي وفوري:</b>\n"
    "• فتح شارت الجلسة اللحظي لأي فرصة مرصودة فوراً (&lt;5ms).\n"
    "• تحديد نقطة وسعر ووقت الدخول بدقة على الشارت.\n"
    "• تتبع أقصى قمة ربح محققة لحظياً بعد التنبيه (Peak Gain Tracker).\n\n"
    "🎯 <b>تتبع الصفقات والأهداف بدقة:</b>\n"
    "• أهداف واضحة (Target 1) ومستوى وقف خسارة صارم لحماية رأس المال.\n"
    "• متابعة حية لجميع الإشارات المفتوحة والنتائج المحققة جلسة بجلسة.\n\n"
    "🔗 <b>شاهد وتتبع كافة الإشارات المفتوحة والشارتات الآن عبر بروفايلك:</b>\n"
    '👉 <a href="https://egxbots.com/profile#scanner-signals">https://egxbots.com/profile#scanner-signals</a>\n\n'
    "<i>EGX BOTS — استثمار ذكي بالأرقام والذكاء الاصطناعي</i> 🇪🇬"
)

print(f"Connecting to Telegram for chat_id={chat_id}, thread={message_thread_id}...")

if not os.path.isfile(image_path):
    print(f"Error: Image not found at {image_path}")
    sys.exit(1)

with open(image_path, "rb") as photo_file:
    data = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "HTML",
    }
    files = {
        "photo": ("scanner_15m_chart_modal.png", photo_file, "image/png")
    }
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        data=data,
        files=files,
        timeout=35,
    )
    print("HTTP Status:", resp.status_code)
    try:
        body = resp.json()
        print("Telegram Response OK:", body.get("ok"))
        if body.get("ok"):
            msg_id = body.get("result", {}).get("message_id")
            print(f"✅ Success! Sent to thread {message_thread_id}, Message ID: {msg_id}")
        else:
            print("Telegram Error Description:", body.get("description"))
    except Exception as e:
        print("Parsing response failed:", e, resp.text)
