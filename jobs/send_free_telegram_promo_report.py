#!/usr/bin/env python3
"""
jobs/send_free_telegram_promo_report.py
Dispatches the promotional market report to the FREE Telegram Channel / Group topic.
Highlights:
  - 14/15 winning signals (SEIG +13.13% today, +50.2% in 3 sessions)
  - Tomorrow's 19 Wyckoff Spring traps preview
  - Fair Value preview (80 undervalued stocks, HRHO +65% upside)
  - 100 EGP Founder Pro offer with inline buttons
"""
import os
import sys
import json
import argparse
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT_DIR, ".env"))
load_dotenv(os.path.join(ROOT_DIR, "web", ".env.local"), override=True)

LINK_PRICING = "https://egxbots.com/pricing?plan=pro"
LINK_TECHNICAL = "https://egxbots.com/scanner/technical"
LINK_FAIR_VALUE = "https://egxbots.com/fair-value"


def build_promo_message_html() -> str:
    return (
        "🔥 <b>تقرير خاص: أرقام حقيقية لا تكذب | حصيلة جلسة اليوم ومصائد الغد</b> 🇪🇬\n"
        "📅 <b>جلسة الإثنين: 03-11-2026</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "نشارككم نتائج رادار الذكاء الاصطناعي وكاشف المصائد بشفافية مطلقة، مع نظرة استباقية لما يجهزه كبار السوق لجلسة الغد:\n\n"
        "🚀 <b>أولاً: 14 سهماً رابحاً من أصل 15 (93.3% نسبة دقة اليوم!):</b>\n\n"
        "⭐ <b>سهم SEIG (إيكون / السعودية المصرية للاستثمار) — نجم الجلسات الثلاث:</b>\n"
        "• رصد الرادار إشارة الدخول أمس عند <b>247.50 ج.م</b>\n"
        "• اليوم طار السهم ليسجل <b>280.00 ج.م (+13.13% بالحد الأقصى Limit Up!)</b> 💥\n"
        "• أغلق عند <b>266.15 ج.م (+7.54%)</b> بحجم تداول قياسي <b>9.9 أضعاف</b> المعدل الطبيعي!\n"
        "🏆 <b>النتيجة: مكسب تراكمي تخطى +50.2% في 3 جلسات فقط لمن التزم بالإشارة!</b>\n\n"
        "📈 <b>نماذج أخرى صعدت مباشرة اليوم من إشارات الأمس:</b>\n"
        "• <b>PRMH:</b> من 1.81 ج.م ➔ قمة <b>1.95 ج.م (+7.73%)</b> | حجم 4.0x\n"
        "• <b>GTWL:</b> من 125.00 ج.م ➔ قمة <b>132.80 ج.م (+6.24%)</b>\n"
        "• <b>AMES:</b> من 32.50 ج.م ➔ قمة <b>34.00 ج.م (+4.62%)</b> | حجم 2.1x\n"
        "• <b>QNBE:</b> من 50.50 ج.م ➔ قمة <b>52.80 ج.م (+4.55%)</b> | حجم 2.4x\n"
        "• <b>EPCO:</b> من 8.11 ج.م ➔ قمة <b>8.45 ج.م (+4.19%)</b> | حجم 6.3x\n"
        "• <b>ORWE (مصيدة القاع):</b> صعد لـ <b>24.99 ج.م (+3.26%)</b> وأغلق صاعداً.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🪤 <b>ثانياً: ماذا يخبئ السوق لجلسة الغد؟ (19 مصيدة ارتداد تجميعية)</b>\n\n"
        "رصد خوارزمي وايكوف (Wyckoff Trap Detector) مع إغلاق اليوم <b>19 سهماً</b> أنهت اختبارات قيعان وهمية (Spring) بذيول شرائية قوية تدل على تجميع ذكي واستعداد لارتداد، من بينها:\n"
        "• <b>CAED:</b> ارتداد كامل 100% فوق دعم 94.88 ج.م (ثقة 98% وحجم 5.6x)\n"
        "• <b>FIRE:</b> ارتداد 100% فوق دعم 3.81 ج.م (ثقة 98%)\n"
        "• <b>EMFD (إعمار مصر):</b> إغلاق 12.21 ج.م فوق دعم 12.00 ج.م بحجم 4.7x\n"
        "• <b>EGREF / AFMC / BIOC / CICH / CRST</b> وغيرها 14 سهماً آخرين مرصودة بالكامل داخل المنصة.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💎 <b>ثالثاً: 80 سهماً يتداولون بأقل من قيمتهم الاستثمارية العادلة</b>\n\n"
        "كاشف القيمة العادلة المحدث لـ 254 شركة مسجلة أظهر أن أسهماً قيادية مثل <b>هيرميس القابضة (HRHO)</b> تتداول حالياً عند <b>22.50 ج.م</b> بينما قيمتها العادلة المقدرة علمياً هي <b>37.13 ج.م</b> (فرصة صعود متوقعة تتجاوز <b>+65%</b>).\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👑 <b>عرض المؤسسين الحصري: ثبّت باقة Pro بـ 100 ج.م شهرياً فقط مدى الحياة!</b>\n\n"
        "بدلاً من 200 ج.م شهرياً.. احصل فوراً على:\n"
        "✅ الوصول الكامل لإشارات الرادار اللحظية والماسح الفني.\n"
        "✅ كاشف المصائد والانعكاسات اليومي (Spring & Upthrust).\n"
        "✅ قناة التنبيهات VIP الفورية على تليجرام.\n"
        "✅ مساعدك الذكي ARTORO لتحليل الأسهم والمحافظ بدون قيود.\n\n"
        "💳 <i>طرق دفع فورية وسهلة: فودافون كاش / انستاباي / فوري / بطاقات بنكية وميزة.</i>\n\n"
        "👇 <b>استفد من العرض وتصفح الإشارات عبر الروابط المباشرة:</b>"
    )


def send_promo_report(dry_run: bool = False) -> dict:
    bot_token = os.getenv("ARTORO_AI_BOT", "").strip()
    if not bot_token:
        raise RuntimeError("No Telegram bot token found in environment (ARTORO_AI_BOT).")

    raw_target = os.getenv("TELEGRAM_FREE_CHAT_ID", "-1002083067817_153").strip()
    if "_" in raw_target:
        chat_id, thread_id_str = raw_target.split("_", 1)
        thread_id = int(thread_id_str)
    else:
        chat_id = raw_target
        thread_id = None

    message_text = build_promo_message_html()

    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "⚡ اشترك في باقة Pro بـ 100 ج.م (تثبيت السعر) ↗", "url": LINK_PRICING}
            ],
            [
                {"text": "🔍 فتح الماسح الفني وكاشف المصائد ↗", "url": LINK_TECHNICAL},
                {"text": "💎 فحص القيمة العادلة للأسهم ↗", "url": LINK_FAIR_VALUE}
            ]
        ]
    }

    print(f"Target chat_id: {chat_id}, thread_id: {thread_id}")
    print(f"Message length: {len(message_text)} characters (Telegram limit: 4096)")

    if dry_run:
        print("\n[DRY RUN PREVIEW]:\n")
        print(message_text)
        print("\n[INLINE KEYBOARD]:", json.dumps(inline_keyboard, ensure_ascii=False, indent=2))
        return {"ok": True, "dry_run": True, "target": chat_id, "thread_id": thread_id, "length": len(message_text)}

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "HTML",
        "reply_markup": inline_keyboard,
        "disable_web_page_preview": True,
    }
    if thread_id:
        payload["message_thread_id"] = thread_id

    resp = requests.post(url, json=payload, timeout=30)
    data = resp.json()
    if data.get("ok"):
        msg_id = data.get("result", {}).get("message_id")
        print(f"✅ Successfully dispatched promo report to Free Telegram! Message ID: {msg_id}")
    else:
        print(f"❌ Failed to dispatch: {data}")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Promotional Market Report to Free Telegram Channel")
    parser.add_argument("--dry-run", action="store_true", help="Preview message without sending")
    args = parser.parse_args()

    res = send_promo_report(dry_run=args.dry_run)
    print("Result:", res.get("ok"))
