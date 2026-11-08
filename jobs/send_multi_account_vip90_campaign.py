#!/usr/bin/env python3
"""
jobs/send_multi_account_vip90_campaign.py
Dispatches the smart conversion email to high-intent multi-account users,
showcasing:
- Last week's top recommendations & verified win stats (from campaign_targets_and_copy.md)
- New features, AI Chat & Quota (350 messages/month vs 10 free, 10 portfolio stocks, 0-day signal delay, Telegram VIP)
- The new EGX Disclosures section (/disclosures)
- Direct links to all platform tools (/chat, /disclosures, /scanner/technical, /fair-value, /scanner/ai, /chart, /sharia, /news)
- Special 90 EGP offer with code VIP90 (valid until Tuesday midnight)
"""
import os
import sys
import time
import json
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List

sys.stdout.reconfigure(encoding="utf-8")
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))
load_dotenv(os.path.join(ROOT_DIR, "web", ".env.local"), override=True)

from api.stock_ai import _init_supabase, supabase
_init_supabase()

from api.marketing_lifecycle import (
    send_resend_email,
    record_marketing_message,
    is_user_unsubscribed,
    generate_unsub_token,
    APP_URL,
)
from jobs.analyze_email_campaign import analyze_campaign

MESSAGE_TYPE = "campaign_multi_account_vip90_2026_11_08"
SUBJECT = "👑 [عرض خاص لحسابك + المميزات الجديدة] 350 رسالة شات AI وقسم الإفصاحات وتوصيات الأسبوع بـ 90 ج فقط! 🇪🇬"


def build_smart_vip90_email_html(user_id: str, email: str, name: str) -> str:
    unsub_token = generate_unsub_token(user_id, email)
    unsub_url = f"{APP_URL}/api/marketing/unsubscribe?uid={user_id}&email={email}&token={unsub_token}"
    checkout_url = f"{APP_URL}/pricing?ref=VIP90"
    display_name = (name or "المتداول العزيز").strip()

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>المميزات الجديدة + توصيات الأسبوع وعرض 90 ج.م | EGX BOTS</title>
</head>
<body style="margin:0;padding:0;background-color:#07090e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#f3f4f6;text-align:right;">
<div style="max-width:640px;margin:0 auto;padding:24px 16px;">

  <!-- Header -->
  <div style="text-align:center;padding-bottom:20px;border-bottom:2px solid #1f2937;">
    <a href="{APP_URL}" style="text-decoration:none;color:#fff;font-size:26px;font-weight:900;">EGX <span style="color:#10b981;">BOTS</span> ⚡</a>
    <div style="margin-top:8px;">
      <span style="display:inline-block;background:rgba(16,185,129,.15);border:1px solid rgba(16,185,129,.4);color:#10b981;font-size:12px;font-weight:bold;padding:5px 16px;border-radius:9999px;">
        👑 دعوة خاصة لأكثر المتداولين نشاطاً على المنصة
      </span>
    </div>
  </div>

  <!-- Smart Hook & Greeting -->
  <div style="padding:22px 0 16px 0;">
    <h1 style="margin:0 0 10px 0;font-size:21px;color:#ffffff;line-height:1.4;">
      مرحباً {display_name} 👋،
    </h1>
    <p style="margin:0 0 12px 0;font-size:15px;color:#d1d5db;line-height:1.8;">
      لاحظنا شغفك ومتابعتك المستمرة لرادار وأدوات <strong>EGX BOTS</strong>! ولأن المتداول المحترف يحتاج إلى <strong>حساب Pro رسمي واحد مستقر</strong> يجمع محفظته، سجل محادثاته الذكية، وتنبيهاته اللحظية دون انقطاع، جهزنا لك اليوم ملخص أقوى توصيات الأسبوع، مع جولة كاملة في <strong>المميزات الجديدة وكوتا الشات الضخمة</strong> وهدية استثنائية لتفعيل حسابك بـ <strong>90 ج.م فقط</strong> (3 جنيهات يومياً!).
    </p>
  </div>

  <!-- Section 1: Last Week's Top Recommendations -->
  <div style="background:#0d1117;border:2px solid #10b981;border-radius:16px;padding:20px;margin-bottom:20px;">
    <h2 style="margin:0 0 12px 0;font-size:17px;color:#10b981;">
      🚀 أولاً: ماذا فعلت إشارات وتوصيات الأسبوع الماضي؟
    </h2>
    <div style="font-size:14px;color:#d1d5db;line-height:1.9;">
      • <strong>سهم ليسيكو مصر (LCSW) [إشارة اليوم]:</strong> إشارة شراء حول <strong>39.47 ج</strong> بنسبة نجاح <span style="color:#10b981;font-weight:bold;">70%</span> نحو مستهدف أول <strong>47.36 ج (+20%)</strong> ومستهدف ثانٍ <strong>52.10 ج (+32%)</strong>! ⚡<br>
      • <strong>سهم تايكون (TYCN):</strong> إشارة دخول حول <strong>13.33 ج</strong> بنسبة نجاح تاريخية <span style="color:#10b981;font-weight:bold;">81%</span> — صعد بالحد الأقصى في الجلسة (+20%) متجهاً نحو مستهدفاته (16.40 ج ثم <strong>18.04 ج بفرصة ربح +35.3%</strong>)! 🔥<br>
      • <strong>سهم كفر الزيات (KZPC):</strong> إشارة شراء حول <strong>13.56 ج</strong> بمستهدف أول <strong>18.24 ج (+34.5%)</strong> ومستهدف ثانٍ <strong>20.06 ج (+47.9%)</strong> بنسبة نجاح 65%.<br>
      • <strong>سهم الملتقى العربي (AMIA):</strong> إشارة شراء <strong>18.11 ج</strong> بمستهدفات <strong>21.73 ج (+20%)</strong> و <strong>23.90 ج (+32%)</strong>.<br>
      • <strong>سهم القاهرة للأدوية (CPCI):</strong> إشارة دخول <strong>601.50 ج</strong> نحو <strong>673.68 ج (+12%)</strong> و <strong>741.05 ج (+23.2%)</strong>.<br>
      • <strong>سهم الدولية للاستثمار (ICID):</strong> إشارة شراء <strong>17.98 ج</strong> بمستهدف أول <strong>23.37 ج (+30%)</strong> وثانٍ <strong>25.71 ج (+43%)</strong>.<br>
      • <strong>سهم جهينة (JUFO):</strong> إشارة شراء حول <strong>23.00 ج</strong> بمستهدف <strong>28.79 ج (+25.2%)</strong>.
    </div>
  </div>

  <!-- Section 2: Proven Stats -->
  <div style="background:#0d1117;border:1px solid #1f2937;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 10px 0;font-size:16px;color:#f59e0b;">
      📊 إحصائيات شفافة وموثقة من الجلسات السابقة:
    </h2>
    <div style="font-size:13.5px;color:#d1d5db;line-height:1.85;">
      ✅ <strong>دقة إشارات استثنائية:</strong> حققت إشارات المنصة نسبة فوز بين <strong>14 رابح من 15</strong> و <strong>15 رابح من 15</strong> في الجلسات السابقة.<br>
      ✅ <strong>كاشف القيمة العادلة:</strong> رصد أكثر من <strong>83 سهماً</strong> يتداولون حالياً بأقل من قيمتهم العادلة بفوارق ربحية تتجاوز <strong>+65%</strong>.<br>
      ✅ <strong>كاشف المصائد اللحظية:</strong> تنبيهات مباشرة لمصائد الارتداد الحقيقي (Spring) ومصائد الاختراق الكاذب (Upthrust) لتجنب التعليقة في القمم.
    </div>
  </div>

  <!-- Section 3: New Features, AI Chat, Quota & Disclosures -->
  <div style="background:#0d1117;border:2px solid #3b82f6;border-radius:16px;padding:20px;margin-bottom:20px;">
    <h2 style="margin:0 0 14px 0;font-size:17px;color:#60a5fa;">
      ⚡ ثانياً: المميزات الجديدة وحصة الشات والكوتا في باقة PRO
    </h2>
    <div style="font-size:14px;color:#e5e7eb;line-height:1.9;">
      🤖 <strong>1. شات الذكاء الاصطناعي الوكيل (AI Chat) — كوتا 350 رسالة شهرياً!</strong><br>
      <span style="color:#9ca3af;font-size:13px;">بدلاً من 10 رسائل فقط في الحساب المجاني، تحصل على <strong>350 رسالة شهرياً</strong>! اسأل الشات بالعامية المصرية عن أي سهم، دعومه ومقاوماته، تقييم محفظتك، مقارنة الأسهم، أو الأسهم التي تشهد تجميعاً مؤسسياً الآن.</span><br><br>

      📋 <strong>2. قسم إفصاحات البورصة المصرية الجوهرية (ميزة جديدة كلياً!):</strong><br>
      <span style="color:#9ca3af;font-size:13px;">متابعة لحظية لكافة إفصاحات الشركات المدرجة، نتائج الأعمال المالية، الكوبونات والتوزيعات، وقرارات مجالس الإدارة مع تلخيص ذكي لتأثير الإفصاح على السهم.</span><br><br>

      ⚡ <strong>3. إشارات فورية بلا تأخير + قناة تليجرام VIP:</strong><br>
      <span style="color:#9ca3af;font-size:13px;">استلم توصيات الصفقات القصيرة والمتوسطة لحظة صدورها (بدون تأخير الـ 15 يوماً في المجاني)، وانضم فوراً لقناة <strong>Telegram VIP</strong> الخاصة بالمشتركين.</span><br><br>

      💼 <strong>4. كوتا محفظة مضاعفة ومعمل شارت احترافي:</strong><br>
      <span style="color:#9ca3af;font-size:13px;">إدارة ومتابعة حتى <strong>10 أسهم في محفظتك</strong> مع أداة إعادة التوازن الذكي، ومعمل شارت يدعم حتى <strong>8 نوافذ</strong> وتحليل الشارت بالـ AI مباشرة.</span>
    </div>
  </div>

  <!-- Section 4: Direct Links to Platform Tools -->
  <div style="background:#0d1117;border:1px solid #1f2937;border-radius:16px;padding:20px;margin-bottom:22px;">
    <h2 style="margin:0 0 14px 0;font-size:16px;color:#10b981;">
      🔗 روابط سريعة لجميع أدوات المنصة (اضغط للتجربة المباشرة):
    </h2>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:13.5px;line-height:2.1;">
      <tr>
        <td style="padding:4px 0;border-bottom:1px solid #1f2937;">
          🤖 <a href="{APP_URL}/chat" style="color:#10b981;text-decoration:none;font-weight:bold;">شات الذكاء الاصطناعي للبورصة (AI Chat) ↗</a>
          <span style="color:#9ca3af;font-size:12px;"> — 350 رسالة/شهر في Pro</span>
        </td>
      </tr>
      <tr>
        <td style="padding:4px 0;border-bottom:1px solid #1f2937;">
          📋 <a href="{APP_URL}/disclosures" style="color:#60a5fa;text-decoration:none;font-weight:bold;">قسم إفصاحات الشركات والبيانات الجوهرية (جديد) ↗</a>
          <span style="color:#9ca3af;font-size:12px;"> — متابعة لحظية للإفصاحات</span>
        </td>
      </tr>
      <tr>
        <td style="padding:4px 0;border-bottom:1px solid #1f2937;">
          🪤 <a href="{APP_URL}/scanner/technical" style="color:#f59e0b;text-decoration:none;font-weight:bold;">كاشف المصائد والنشاط غير الطبيعي (Traps Scanner) ↗</a>
          <span style="color:#9ca3af;font-size:12px;"> — ارتداد واختراق كاذب</span>
        </td>
      </tr>
      <tr>
        <td style="padding:4px 0;border-bottom:1px solid #1f2937;">
          💎 <a href="{APP_URL}/fair-value" style="color:#10b981;text-decoration:none;font-weight:bold;">رادار وحاسبة القيمة العادلة لـ 254 سهماً ↗</a>
          <span style="color:#9ca3af;font-size:12px;"> — اكتشف الأسهم الرخيصة</span>
        </td>
      </tr>
      <tr>
        <td style="padding:4px 0;border-bottom:1px solid #1f2937;">
          🚀 <a href="{APP_URL}/scanner/ai" style="color:#a78bfa;text-decoration:none;font-weight:bold;">رادار توصيات وإشارات الذكاء الاصطناعي (AI Signals) ↗</a>
          <span style="color:#9ca3af;font-size:12px;"> — صفقات قصيرة ومتوسطة</span>
        </td>
      </tr>
      <tr>
        <td style="padding:4px 0;border-bottom:1px solid #1f2937;">
          📈 <a href="{APP_URL}/chart" style="color:#38bdf8;text-decoration:none;font-weight:bold;">معمل الشارت الاحترافي وتحليل الشارت بالـ AI ↗</a>
          <span style="color:#9ca3af;font-size:12px;"> — حتى 8 شارتات ومؤشرات</span>
        </td>
      </tr>
      <tr>
        <td style="padding:4px 0;border-bottom:1px solid #1f2937;">
          🌙 <a href="{APP_URL}/sharia" style="color:#34d399;text-decoration:none;font-weight:bold;">فلتر الأسهم الشرعية وحاسبة التطهير ↗</a>
          <span style="color:#9ca3af;font-size:12px;"> — فحص التوافق الشرعي</span>
        </td>
      </tr>
      <tr>
        <td style="padding:4px 0;">
          📰 <a href="{APP_URL}/news" style="color:#f472b6;text-decoration:none;font-weight:bold;">رادار أخبار البورصة والسوق اللحظي ↗</a>
          <span style="color:#9ca3af;font-size:12px;"> — تغطية إخبارية فورية</span>
        </td>
      </tr>
    </table>
  </div>

  <!-- Section 5: Special 90 EGP Offer Box -->
  <div style="background:linear-gradient(135deg, rgba(16,185,129,0.14), rgba(245,158,11,0.10));border:2px solid #f59e0b;border-radius:16px;padding:22px;text-align:center;margin-bottom:24px;">
    <span style="background:#f59e0b;color:#000;font-weight:900;font-size:11px;padding:4px 12px;border-radius:9999px;">
      🎁 كود خصم خاص لتثبيت حسابك الرسمي
    </span>
    <h2 style="margin:12px 0 8px 0;font-size:21px;color:#fff;">
      وفر 10 ج.م إضافية — وادفع <span style="color:#10b981;font-size:25px;font-weight:900;">90 ج.م فقط!</span>
    </h2>
    <p style="margin:0 0 16px 0;font-size:14px;color:#d1d5db;line-height:1.6;">
      فعّل باقة Pro الكاملة لشهر كامل بـ 90 ج.م بدلاً من 100 ج.م باستخدام الكود:<br>
      <strong style="display:inline-block;margin-top:6px;color:#ffe600;font-size:19px;letter-spacing:1.5px;background:#000;padding:5px 14px;border-radius:8px;border:1px dashed #ffe600;">VIP90</strong>
    </p>
    <div style="background:#07090e;border-radius:10px;padding:12px;margin:0 auto 18px auto;max-width:400px;font-size:13px;color:#e5e7eb;line-height:1.8;">
      ⏳ <strong>صلاحية الكود:</strong> متاح حتى منتصف ليل الثلاثاء 10 نوفمبر فقط.<br>
      💳 <strong>طرق الدفع الفورية:</strong> فودافون كاش / انستاباي / فيزا وماستركارد / المحافظ الإلكترونية.
    </div>
    <a href="{checkout_url}" style="display:inline-block;background:#10b981;color:#000000;font-weight:900;font-size:16px;padding:14px 32px;border-radius:12px;text-decoration:none;box-shadow:0 4px 14px rgba(16,185,129,0.4);">
      👈 اضغط هنا لتفعيل الخصم والدفع بـ 90 ج.م مباشرة
    </a>
  </div>

  <!-- FRA Regulatory Disclaimer -->
  <div style="border-top:1px solid #1f2937;padding-top:16px;font-size:11px;color:#6b7280;text-align:justify;line-height:1.6;">
    <p style="margin:0 0 8px 0;">
      <strong>⚠️ تنبيه قانوني وإخلاء مسؤولية (FRA):</strong> مخرجات النماذج الكمية وشات بوت الذكاء الاصطناعي هي مؤشرات وأدوات فنية وإحصائية لأغراض البحث والتحليل والتعليم الشخصي فقط، ولا تمثل توصية استثمارية أو دعوة لشراء أو بيع أي ورقة مالية أو إدارة محافظ. قرارات التداول مسؤوليتك المستقلة عبر شركة سمسرة مرخصة من الهيئة العامة للرقابة المالية (FRA).
    </p>
    <p style="margin:0;text-align:center;">
      تصلك هذه الرسالة لحسابك المسجل في EGX BOTS. <a href="{unsub_url}" style="color:#9ca3af;text-decoration:underline;">إلغاء الاشتراك بنقرة واحدة</a>
    </p>
  </div>

</div>
</body>
</html>"""


def load_multi_account_targets() -> List[Dict[str, Any]]:
    target_path = "C:/Users/MR__CODER__/.gemini/antigravity/brain/4f7d6beb-f26c-4ee9-90e6-60b99bd6260b/scratch/multi_account_targets.json"
    with open(target_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Send Smart VIP90 Email to Multi-Account Users")
    parser.add_argument("--dry-run", action="store_true", help="Preview recipients only")
    args = parser.parse_args()

    targets = load_multi_account_targets()
    print("=== SMART MULTI-ACCOUNT VIP90 CAMPAIGN ===")
    print(f"Total target accounts loaded: {len(targets)}")

    valid_recipients = []
    for i, t in enumerate(targets, 1):
        if is_user_unsubscribed(t["id"], t["email"]):
            print(f"  [SKIP - Unsubscribed] {t['email']}")
            continue
        valid_recipients.append(t)
        print(f"  {i}. [{t['group']}] {t['email']} ({t['name']})")

    if args.dry_run:
        print(f"\n[DRY RUN] Ready to send to {len(valid_recipients)} accounts.")
        return

    sent_count = 0
    failed_count = 0
    print(f"\nDispatching live emails to {len(valid_recipients)} accounts...")

    for i, r in enumerate(valid_recipients, 1):
        html_body = build_smart_vip90_email_html(r["id"], r["email"], r["name"])
        out_data = {}
        ok = send_resend_email(r["email"], SUBJECT, html_body, out=out_data)
        if ok:
            sent_count += 1
            record_marketing_message(
                user_id=r["id"],
                email=r["email"],
                message_type=MESSAGE_TYPE,
                metadata={
                    "campaign": "multi_account_vip90",
                    "group": r["group"],
                    "promo_code": "VIP90",
                    "discount_percent": 10.0,
                },
                provider_message_id=out_data.get("provider_message_id"),
            )
            print(f"[{i}/{len(valid_recipients)}] ✅ Sent to {r['email']} (ID: {out_data.get('provider_message_id')})")
        else:
            failed_count += 1
            print(f"[{i}/{len(valid_recipients)}] ❌ Failed to send to {r['email']}")

        time.sleep(0.6)

    print(f"\n=== DISPATCH SUMMARY ===")
    print(f"Sent: {sent_count} | Failed: {failed_count}")

    print("\n" + "=" * 50)
    print("MANDATORY POST-DISPATCH LIVE ANALYTICS BREAKDOWN")
    print("=" * 50)
    time.sleep(2)
    analyze_campaign()


if __name__ == "__main__":
    main()
