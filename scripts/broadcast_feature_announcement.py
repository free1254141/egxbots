import os
import sys
import time
import requests
from dotenv import load_dotenv
from supabase import create_client

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

token = os.getenv("ARTORO_AI_BOT", "").strip()
if not token:
    print("Error: ARTORO_AI_BOT token not found in environment")
    sys.exit(1)

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(supabase_url, supabase_key)

# 1. Fetch Pro User IDs
sub_res = supabase.table("subscriptions").select("user_id").eq("status", "active").execute()
pro_uids = set(s["user_id"] for s in (sub_res.data or []))

# 2. Fetch Profiles with Telegram
profile_res = supabase.table("profiles").select("id, username, display_name, telegram_chat_id").not_.is_("telegram_chat_id", "null").execute()
profiles = profile_res.data or []

# Build distinct recipient list
recipients = []
seen_chats = set()

for p in profiles:
    chat_id = str(p.get("telegram_chat_id") or "").strip()
    if not chat_id or chat_id in seen_chats:
        continue
    seen_chats.add(chat_id)
    is_pro = p["id"] in pro_uids
    recipients.append({
        "chat_id": chat_id,
        "user_id": p["id"],
        "name": p.get("display_name") or p.get("username") or "مشترك EGX BOTS",
        "is_pro": is_pro
    })

print(f"Total distinct recipients found: {len(recipients)} (Pro: {sum(1 for r in recipients if r['is_pro'])})")

# Image to send: 15m candlestick chart modal
image_path = os.path.abspath(r"C:\Users\MR__CODER__\.gemini\antigravity\brain\0dfb0046-156e-44da-9df3-72fc3ae17bd8\.user_uploaded\media_1792444484349_fc25cb67.png")
if not os.path.isfile(image_path):
    print(f"Error: Image not found at {image_path}")
    sys.exit(1)

caption = (
    "🚀 <b>تحديث حصري في EGX BOTS | إطلاق شارت الـ 15 دقيقة ورادار تتبع الإشارات المباشر!</b> ⚡\n\n"
    "يسعدنا إطلاق أحدث وأقوى ميزة لمتابعة فرص وتنبيهات الإسكانر الفورية في البورصة المصرية:\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "📊 <b>شارت شموع 15 دقيقة تفاعلي وفوري:</b>\n"
    "• فتح شارت الجلسة اللحظي لأي فرصة مرصودة فوراً وبسرعة فائقة (&lt;5ms).\n"
    "• توضيح نقطة الدخول وسعر التنبيه والوقت بدقة على الشارت.\n"
    "• تتبع أقصى قمة ربح محققة لحظياً بعد التنبيه (Peak Gain Tracker).\n\n"
    "🎯 <b>تتبع الصفقات والأهداف بدقة لحظة بلحظة:</b>\n"
    "• أهداف فنية واضحة ومستوى وقف خسارة صارم لحماية رأس المال.\n"
    "• تاب مخصص للإشارات المفتوحة والصفقات المغلقة لمتابعة النتائج خطوة بخطوة.\n"
    "• فلترة الصفقات حسب الأيام وإحصائيات تفصيلية لنسبة النجاح والأرباح.\n\n"
    "🔗 <b>تابع وحلل كافة الإشارات المفتوحة والشارتات الآن عبر بروفايلك:</b>\n"
    '👉 <a href="https://egxbots.com/profile#scanner-signals">https://egxbots.com/profile#scanner-signals</a>\n\n'
    "<i>EGX BOTS — استثمار ذكي بالأرقام والذكاء الاصطناعي</i> 🇪🇬"
)

success_count = 0
failed_count = 0

for r in recipients:
    chat_id = r["chat_id"]
    is_pro = r["is_pro"]
    role_str = "PRO VIP ⭐" if is_pro else "Member"
    print(f"Sending to {chat_id} ({role_str})...", end=" ")

    try:
        with open(image_path, "rb") as photo_file:
            data = {
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
            }
            files = {
                "photo": ("scanner_15m_chart.png", photo_file, "image/png")
            }
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data=data,
                files=files,
                timeout=30,
            )
            body = resp.json()
            if body.get("ok"):
                print("✅ Delivered!")
                success_count += 1
            else:
                print(f"❌ Failed: {body.get('description')}")
                failed_count += 1
    except Exception as e:
        print(f"❌ Exception: {e}")
        failed_count += 1

    time.sleep(0.5)  # Telegram rate limit safety

# Also send to public channel/group
group_chat_id = "-1002083067817"
print(f"Sending to supergroup/channel {group_chat_id}...", end=" ")
try:
    with open(image_path, "rb") as photo_file:
        data = {
            "chat_id": group_chat_id,
            "caption": caption,
            "parse_mode": "HTML",
        }
        files = {
            "photo": ("scanner_15m_chart.png", photo_file, "image/png")
        }
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data=data,
            files=files,
            timeout=30,
        )
        body = resp.json()
        if body.get("ok"):
            print("✅ Group Delivered!")
        else:
            print(f"❌ Group Failed: {body.get('description')}")
except Exception as e:
    print(f"❌ Group Exception: {e}")

print(f"\nBroadcast Summary: {success_count} succeeded, {failed_count} failed out of {len(recipients)} total users.")
