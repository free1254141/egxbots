"""
jobs/send_mohamed_kani_vip_email.py
Sends hyper-personalized VIP Win-Back email to Mohamed Kani (first Pro subscriber).
Followed by live Resend analytics report as mandated by agent rules.
"""
import os
import sys
import time

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
    generate_unsub_token,
    APP_URL,
)
from jobs.analyze_email_campaign import analyze_campaign

url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
supabase = create_client(url, key)

USER_ID = "2974d0db-711a-408b-8ef4-9f0853561e64"
EMAIL = "mohamedkani10@gmail.com"
NAME = "أستاذ محمد (Mo Kany)"

def build_vip_email():
    unsub_token = generate_unsub_token(USER_ID, EMAIL)
    unsub_url = f"{APP_URL}/unsubscribe?uid={USER_ID}&token={unsub_token}&email={EMAIL}"
    pricing_url = f"{APP_URL}/pricing?ref=mokany_founder_vip"
    portfolio_url = f"{APP_URL}/profile#portfolio"

    subject = "👑 أ/ محمد.. كود خصم خاص لأول شريك نجاح في EGX BOTS + أداة تدوير المحفظة الجديدة"
    
    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #0b0f19; margin: 0; padding: 25px; text-align: right; color: #f8fafc;">
    <div style="max-width: 620px; margin: 0 auto; background: #111827; border-radius: 16px; overflow: hidden; border: 1px solid #1f2937; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);">
        
        <!-- Header Banner -->
        <div style="background: linear-gradient(135deg, #059669 0%, #0f172a 100%); padding: 30px 25px; text-align: center; border-bottom: 2px solid #10b981;">
            <div style="display: inline-block; background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; padding: 4px 14px; border-radius: 20px; font-size: 13px; font-weight: bold; margin-bottom: 10px;">
                ⭐ أول شريك نجاح في EGX BOTS Pro
            </div>
            <h1 style="color: #ffffff; margin: 5px 0 0 0; font-size: 26px; font-weight: 800; letter-spacing: 0.5px;">EGX BOTS VIP</h1>
            <p style="color: #94a3b8; margin: 6px 0 0 0; font-size: 14px;">تقدير خاص لأول من وضع ثقته في منظومتنا الذكية</p>
        </div>

        <!-- Body Content -->
        <div style="padding: 30px 25px; background: #111827;">
            <p style="font-size: 17px; line-height: 1.8; color: #e2e8f0; margin-top: 0;">
                تحية طيبة يا <strong>{NAME}</strong>،
            </p>
            <p style="font-size: 15px; line-height: 1.8; color: #cbd5e1;">
                نحن في فريق <strong>EGX BOTS</strong> لا ننسى أبداً من كان أول من شاركنا الرحلة؛ فأنت مسجل لدينا تاريخياً كـ <strong>أول مشترك في باقة Pro</strong> في تاريخ المنصة، ونعتز بوجودك كشريك نجاح أساسي.
            </p>

            <!-- Portfolio Context Card -->
            <div style="background: #1e293b; border-right: 4px solid #10b981; padding: 20px; border-radius: 10px; margin: 25px 0;">
                <h3 style="color: #38bdf8; margin: 0 0 10px 0; font-size: 16px;">
                    🔄 بخصوص محفظتك وأسهمك التي حللتها معنا (فرتيكا FERC وكفر الزيات HBCO):
                </h3>
                <p style="font-size: 14px; line-height: 1.7; color: #94a3b8; margin: 0;">
                    نعلم أن جلسات الشهر الماضي شهدت ضغوطاً تصحيحية على بعض أسهم محفظتك وخاصة التركز في قطاع البرمجيات، ولأن هدفنا الحقيقي هو تعظيم أرباحك وتفادي احتجاز السيولة، قمنا بتطوير وإطلاق <strong>أحدث ترسانة أدوات ذكية في البورصة المصرية</strong>:
                </p>
            </div>

            <!-- Features Highlights -->
            <ul style="padding-right: 20px; color: #f1f5f9; font-size: 14.5px; line-height: 1.9; margin: 20px 0;">
                <li>
                    <strong>🔄 محرك تشخيص وإعادة تدوير المحفظة (AI Portfolio Rebalancer):</strong> يحلل توزيع السيولة لديك، ويحدد بدائل سريعة التعويض بالذكاء الاصطناعي للخروج الآمن ونقل الأوزان لأسهم رابحة.
                </li>
                <li>
                    <strong>🪤 كاشف مصائد السيولة اللحظي (Wyckoff Traps):</strong> رصد فخاخ صانع السوق (مصائد الدباب Spring ومصائد الثيران Upthrust) عند إغلاق كل جلسة لمنع الشراء عند القمم.
                </li>
                <li>
                    <strong>🎯 محرك القيمة العادلة القطاعي:</strong> مضاعفات ربحية وقيمة دفترية مخصصة للشركات والبنوك المصرية لمعرفة السعر الحقيقي المستهدف لكل سهم.
                </li>
                <li>
                    <strong>⚡ استشارات ذكاء اصطناعي غير محدودة:</strong> لتحليل أي شارت أو سهم أو محفظة فورياً.
                </li>
            </ul>

            <!-- Special Offer Banner -->
            <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(59, 130, 246, 0.15)); border: 1px dashed #10b981; border-radius: 12px; padding: 20px; text-align: center; margin: 30px 0 25px 0;">
                <h4 style="color: #34d399; margin: 0 0 8px 0; font-size: 18px; font-weight: 800;">
                    🎁 هدية العودة الحصرية لأول مشترك Pro:
                </h4>
                <p style="color: #e2e8f0; font-size: 15px; margin: 0 0 15px 0; line-height: 1.6;">
                    تجديد اشتراكك السنوي أو الشهري في باقة Pro بـ <strong style="color: #10b981; font-size: 20px;">100 ج.م فقط شهرياً مدى الحياة</strong> (خصم 50% عن الـ 200 ج.م السابقة)!
                </p>
                <div style="margin: 20px 0 10px 0;">
                    <a href="{pricing_url}" style="display: inline-block; background-color: #10b981; color: #ffffff; padding: 14px 36px; border-radius: 8px; text-decoration: none; font-weight: 800; font-size: 16px; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.4);">
                        👑 استئناف اشتراكي في باقة Pro (100 ج.م)
                    </a>
                </div>
                <p style="color: #94a3b8; font-size: 13px; margin: 12px 0 0 0;">
                    متاح التجديد عبر: <strong>فودافون كاش / InstaPay / البطاقات البنكية</strong>.
                </p>
            </div>

            <p style="font-size: 14px; color: #94a3b8; line-height: 1.7; margin-top: 25px;">
                يمكنك أيضاً فحص محفظتك الحالية مجاناً عبر المنصة عبر <a href="{portfolio_url}" style="color: #38bdf8; text-decoration: underline;">لوحة المحفظة</a> والاطلاع على التحديثات في أي وقت.
            </p>

            <p style="font-size: 14px; color: #cbd5e1; margin-top: 30px;">
                مع خالص التحية والتقدير،<br>
                <strong>فريق عمل EGX BOTS</strong>
            </p>
        </div>

        <!-- Footer -->
        <div style="background: #0f172a; padding: 20px; text-align: center; border-top: 1px solid #1f2937; font-size: 12px; color: #64748b;">
            <p style="margin: 0 0 8px 0;">تصلك هذه الرسالة بصفتك الشريك الأول المسجل في EGX BOTS.</p>
            <p style="margin: 0;"><a href="{unsub_url}" style="color: #94a3b8; text-decoration: underline;">إلغاء الاشتراك من الرسائل البريدية</a></p>
        </div>
    </div>
</body>
</html>"""
    return subject, html

def send_vip_outreach():
    print("==================================================")
    print(f" 🚀 جاري إرسال إيميل VIP لمحمد كاني ({EMAIL})")
    print("==================================================")

    subj, html = build_vip_email()
    res_out = {}
    success = send_resend_email(EMAIL, subj, html, out=res_out)

    if success:
        p_id = res_out.get("id")
        print(f"  ✓ تم إرسال الإيميل بنجاح عبر Resend: {p_id}")
        record_marketing_message(
            user_id=USER_ID,
            email=EMAIL,
            message_type="vip_founder_winback",
            metadata={"subject": subj, "ref": "mokany_vip"},
            provider_message_id=p_id,
        )
    else:
        print("  ❌ فشل إرسال الإيميل عبر Resend")

    print("\nجاري تحديث التحليلات الحية من Resend API...")
    time.sleep(2)
    analyze_campaign()

if __name__ == "__main__":
    send_vip_outreach()
