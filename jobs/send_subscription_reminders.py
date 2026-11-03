"""
jobs/send_subscription_reminders.py
Sends subscription renewal and expiration reminders to active Pro, expiring trial, and recently expired users.
Sends via Telegram DM (where available) and Resend HTML Email.
Then automatically runs the live analytics breakdown.
"""
import os
import sys
import time
import requests
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')
ROOT_DIR = "c:\\Users\\MR__CODER__\\Desktop\\stokscan_AI"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, '.env'))
load_dotenv(os.path.join(ROOT_DIR, 'web', '.env.local'), override=True)

from supabase import create_client
from api.marketing_lifecycle import (
    send_resend_email,
    record_marketing_message,
    is_user_unsubscribed,
    generate_unsub_token,
    APP_URL,
)
from jobs.analyze_email_campaign import analyze_campaign

url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
supabase = create_client(url, key)

BOT_TOKEN = os.environ.get('ARTORO_AI_BOT', '').strip()

def send_telegram(chat_id: str, text: str, reply_markup=None):
    if not BOT_TOKEN or not chat_id:
        return {"ok": False, "error": "No token or chat_id"}
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = requests.post(api_url, json=payload, timeout=15)
        return res.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

# --- Target Users Definition ---
TARGETS = [
    {
        "category": "PRO_EXPIRING_SOON",
        "email": "dralaagaber@gmail.com",
        "name": "د. علاء جابر",
        "tg_id": "5635227755",
        "expires_in": "غداً الأربعاء 04 نوفمبر",
    },
    {
        "category": "PRO_EXPIRING_SOON",
        "email": "ramzyalomda115@gmail.com",
        "name": "أستاذ رمزي العمدة",
        "tg_id": "8651357614",
        "expires_in": "الخميس 05 نوفمبر",
    },
    {
        "category": "PRO_EXPIRING_SOON",
        "email": "eng.elwelely@gmail.com",
        "name": "م. الوليلي",
        "tg_id": "1104030746",
        "expires_in": "الجمعة 06 نوفمبر",
    },
    {
        "category": "PRO_EXPIRING_SOON",
        "email": "amraly2010@gmail.com",
        "name": "أستاذ عمرو علي",
        "tg_id": None,
        "expires_in": "الجمعة 06 نوفمبر",
    },
    {
        "category": "TRIAL_EXPIRING_TONIGHT",
        "email": "arabygalib@gmail.com",
        "name": "أستاذ عربي غالب",
        "tg_id": None,
        "expires_in": "الليلة (خلال دقائق)",
    },
    {
        "category": "TRIAL_EXPIRING_SOON",
        "email": "kkemokawaga@gmail.com",
        "name": "أستاذ كيمو",
        "tg_id": "431963108",
        "expires_in": "غداً الأربعاء 04 نوفمبر",
    },
    {
        "category": "WIN_BACK_EXPIRED_PRO",
        "email": "ahmedfahmy049@duck.com",
        "name": "أستاذ أحمد فهمي",
        "tg_id": "804297689",
        "expires_in": "انتهى في 31 أكتوبر",
    },
    {
        "category": "WIN_BACK_EXPIRED_PRO",
        "email": "mahmoudelmorshedy94@gmail.com",
        "name": "أستاذ محمود المرشدي",
        "tg_id": "5950650613",
        "expires_in": "انتهى في 26 أكتوبر",
    },
]

def build_reminder_email(user_id: str, email: str, target: dict) -> tuple[str, str]:
    unsub_token = generate_unsub_token(user_id, email)
    unsub_url = f"{APP_URL}/unsubscribe?uid={user_id}&token={unsub_token}&email={email}"
    pricing_url = f"{APP_URL}/pricing?ref=renewal_reminder"
    scanner_url = f"{APP_URL}/scanner/technical"

    name = target["name"]
    category = target["category"]
    expires_in = target["expires_in"]

    if category == "PRO_EXPIRING_SOON":
        subject = f"👑 تذكير بتجديد اشتراكك في باقة Pro | EGX BOTS"
        headline = "تذكير بتجديد اشتراك باقة Pro الحصرية"
        badge_text = "تجديد الاشتراك السنوي/الشهري"
        badge_color = "#3b82f6"
        content_html = f"""
        <p style="font-size: 16px; line-height: 1.8; color: #374151;">
            تحية طيبة <strong>{name}</strong>،<br><br>
            نود تذكير سيادتكم بأن اشتراككم في باقة <strong>EGX BOTS Pro</strong> سينتهي في <strong>({expires_in})</strong>.<br>
            نحرص على ألا يفوتك أي من أدوات المنصة المحدثة:
        </p>
        <div style="background: #f8fafc; border-right: 4px solid #10b981; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <ul style="margin: 0; padding-right: 20px; color: #1e293b; font-size: 15px; line-height: 1.8;">
                <li>🪤 <strong>كاشف مصائد وايكوف اللحظي (Wyckoff Traps):</strong> رصد فخاخ الدباب والثيران مع الإغلاق.</li>
                <li>🎯 <strong>محرك القيمة العادلة المحدث:</strong> مضاعفات قطاعية دقيقة للأسهم المصرية والبنوك.</li>
                <li>🔄 <strong>محلل وإعادة تدوير المحفظة بالذكاء الاصطناعي:</strong> تقييم صفقاتك واقتراح بدائل رابحة.</li>
                <li>⚡ <strong>استشارات شات بوت غير محدودة:</strong> إجابات فورية لأي سهم في البورصة المصرية.</li>
            </ul>
        </div>
        <p style="font-size: 15px; color: #4b5563;">
            لتجديد اشتراكك دون انقطاع والحفاظ على سعر اشتراكك الحالي المخفض، يرجى الضغط على زر التجديد أدناه:
        </p>
        """
        cta_text = "👑 تجديد اشتراكي في باقة Pro"
    elif category.startswith("TRIAL"):
        subject = f"⏳ فترتك التجريبية في EGX BOTS تنتهي قريباً — ثبّت خصم المؤسسين (100 ج.م)"
        headline = "فترتك التجريبية تشارف على الانتهاء"
        badge_text = "عرض تثبيت الاشتراك"
        badge_color = "#f59e0b"
        content_html = f"""
        <p style="font-size: 16px; line-height: 1.8; color: #374151;">
            أهلاً بك <strong>{name}</strong>،<br><br>
            نود إعلامك بأن فترتك التجريبية المجانية ستنتهي <strong>({expires_in})</strong>.<br>
            حتى لا يتوقف مساعدك الاستثماري وكاشف الفرص، يمكنك الآن تفعيل اشتراكك وتثبيت <strong>عرض المؤسسين بـ 100 ج.م شهرياً فقط مدى الحياة</strong> بدلاً من 250 ج.م.
        </p>
        <p style="font-size: 15px; color: #4b5563;">
            يشمل الاشتراك فتح كامل إشارات التداول، كاشف المصائد، تقارير القيمة العادلة، والدردشة الذكية بلا حدود.
        </p>
        """
        cta_text = "⚡ تثبيت عرض المؤسسين بـ 100 ج.م"
    else: # WIN_BACK
        subject = f"🎁 نتشرف بعودتك! خصم خاص لتجديد باقة Pro في EGX BOTS"
        headline = "اشتقنا لتواجدك معنا في EGX BOTS Pro"
        badge_text = "عرض عودة خاص"
        badge_color = "#8b5cf6"
        content_html = f"""
        <p style="font-size: 16px; line-height: 1.8; color: #374151;">
            أهلاً بك <strong>{name}</strong>،<br><br>
            لاحظنا انتهاء اشتراكك في باقة Pro مؤخراً <strong>({expires_in})</strong>.<br>
            أطلقنا هذا الأسبوع تحديثات كبرى للمنصة: كاشف مصائد السيولة (Spring & Upthrust)، محرك القيمة العادلة القطاعي، وأداة إعادة تدوير المحفظة.
        </p>
        <p style="font-size: 15px; color: #4b5563;">
            يسعدنا استئناف اشتراكك بنفس سعر عرض المؤسسين (100 ج.م شهرياً) للاستفادة من كل الميزات الجديدة فوراً:
        </p>
        """
        cta_text = "🔄 استئناف اشتراكي في باقة Pro"

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px; text-align: right;">
    <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
        <div style="background: #0f172a; padding: 25px 20px; text-align: center; border-bottom: 3px solid #10b981;">
            <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 800; letter-spacing: 1px;">EGX BOTS</h1>
            <p style="color: #94a3b8; margin: 5px 0 0 0; font-size: 13px;">المنصة الذكية للأسهم المصرية</p>
        </div>
        <div style="padding: 30px 25px;">
            <div style="display: inline-block; background-color: {badge_color}; color: #ffffff; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; margin-bottom: 15px;">
                {badge_text}
            </div>
            <h2 style="color: #0f172a; font-size: 20px; margin: 0 0 15px 0;">{headline}</h2>
            {content_html}
            <div style="text-align: center; margin: 30px 0 20px 0;">
                <a href="{pricing_url}" style="display: inline-block; background-color: #10b981; color: #ffffff; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);">
                    {cta_text}
                </a>
            </div>
            <p style="text-align: center; font-size: 13px; color: #64748b; margin-top: 15px;">
                لأي مساعدة في وسائل الدفع (InstaPay / فودافون كاش / بطاقات بنكية)، تواصل مع الدعم الفني مباشرة.
            </p>
        </div>
        <div style="background: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8;">
            <p style="margin: 0 0 8px 0;">تصلك هذه الرسالة بصفتك مسجلاً في منصة EGX BOTS.</p>
            <p style="margin: 0;"><a href="{unsub_url}" style="color: #64748b; text-decoration: underline;">إلغاء الاشتراك من رسائل التذكير</a></p>
        </div>
    </div>
</body>
</html>"""
    return subject, html

def execute_reminders():
    print("==================================================")
    print(" 🚀 بدء إرسال تذكيرات تجديد الاشتراكات (Telegram + Resend)")
    print("==================================================")
    
    users_res = supabase.auth.admin.list_users(page=1, per_page=1000)
    email_to_uid = {u.email: u.id for u in users_res}
    
    tg_success = 0
    tg_fail = 0
    email_success = 0
    email_fail = 0

    for target in TARGETS:
        em = target["email"]
        uid = email_to_uid.get(em)
        name = target["name"]
        cat = target["category"]
        expires = target["expires_in"]
        tg_id = target.get("tg_id")

        print(f"\n--- جاري المعالجة: {name} ({em}) ---")

        # 1. Telegram DM
        if tg_id:
            if cat == "PRO_EXPIRING_SOON":
                tg_text = (
                    f"👑 <b>أهلاً بك {name} في EGX BOTS Pro</b>\n\n"
                    f"نود تذكير سيادتكم بأن اشتراككم في باقة Pro سينتهي في <b>({expires})</b>.\n\n"
                    f"لتجنب انقطاع التوصيات وإشارات <b>كاشف المصائد (Wyckoff Traps)</b> واستشارات الشات بوت، "
                    f"يمكنك تجديد اشتراكك بسهولة والحفاظ على سعر اشتراكك الحالي عبر الرابط:\n"
                    f"👉 https://eqxbots.com/pricing"
                )
            elif cat.startswith("TRIAL"):
                tg_text = (
                    f"⏳ <b>أهلاً بك {name} في EGX BOTS</b>\n\n"
                    f"نود إعلامك بأن فترتك التجريبية ستنتهي <b>({expires})</b>.\n\n"
                    f"حتى لا تتوقف الاستشارات والتوصيات، يمكنك الآن تثبيت <b>عرض المؤسسين بـ 100 ج.م شهرياً فقط مدى الحياة</b>:\n"
                    f"👉 https://eqxbots.com/pricing"
                )
            else:
                tg_text = (
                    f"🎁 <b>أهلاً بك {name} — نتشرف بعودتك لـ EGX BOTS Pro</b>\n\n"
                    f"أطلقنا مؤخراً تحديثات كبرى للمنصة: كاشف مصائد السيولة اللحظي، ومحرك القيمة العادلة المحدث.\n"
                    f"يسعدنا تجديد اشتراكك بنفس سعر عرض المؤسسين (100 ج.م) عبر الرابط:\n"
                    f"👉 https://eqxbots.com/pricing"
                )

            markup = {
                "inline_keyboard": [
                    [{"text": "👑 تجديد الاشتراك في باقة Pro", "url": "https://eqxbots.com/pricing"}]
                ]
            }
            res_tg = send_telegram(tg_id, tg_text, reply_markup=markup)
            if res_tg.get("ok"):
                print(f"  ✓ تم إرسال تليجرام بنجاح إلى Chat ID: {tg_id}")
                tg_success += 1
            else:
                print(f"  ❌ فشل تليجرام إلى {tg_id}: {res_tg.get('description', res_tg)}")
                tg_fail += 1
        else:
            print("  ℹ️ لا يوجد تليجرام مسجل (سيتم الاعتماد على البريد الإلكتروني)")

        # 2. Resend Email
        if uid:
            subj, html = build_reminder_email(uid, em, target)
            res_out = {}
            success = send_resend_email(em, subj, html, out=res_out)
            if success:
                p_id = res_out.get("id")
                print(f"  ✓ تم إرسال إيميل بنجاح عبر Resend: {p_id}")
                record_marketing_message(
                    user_id=uid,
                    email=em,
                    message_type="subscription_reminder",
                    metadata={"category": cat, "expires_in": expires},
                    provider_message_id=p_id,
                )
                email_success += 1
            else:
                print(f"  ❌ فشل إرسال إيميل عبر Resend")
                email_fail += 1
        else:
            print("  ❌ لم يتم العثور على User ID في Auth")
            email_fail += 1

        time.sleep(1) # respectful rate limit

    print("\n==================================================")
    print(f"📊 نتيجة الإرسال:")
    print(f"  • تليجرام: {tg_success} نجاح | {tg_fail} فشل")
    print(f"  • إيميلات Resend: {email_success} نجاح | {email_fail} فشل")
    print("==================================================")

    # Automatically run live analytics breakdown as mandated by rule
    print("\nجاري استخراج التحليلات الحية من Resend API...")
    time.sleep(2)
    analyze_campaign()

if __name__ == "__main__":
    execute_reminders()
