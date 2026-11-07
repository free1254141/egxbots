#!/usr/bin/env python3
"""
jobs/send_vip90_campaign.py
Dispatches the VIP90 3-day return campaign (10 EGP discount / 90 EGP Pro)
with last week's top recommendations and verified win rate stats.

Targets:
1. Expired Pro subscribers (canceled/ended)
2. Expired Trial users
3. Top Engaged Free leads who open emails regularly

Usage:
  python jobs/send_vip90_campaign.py --dry-run   # Preview recipients only
  python jobs/send_vip90_campaign.py             # Dispatch live batch
"""
import os
import sys
import time
import json
import argparse
from datetime import datetime, timezone, timedelta
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
    MARKETING_DAILY_EMAIL_CAP,
)
from jobs.analyze_email_campaign import fetch_resend_emails, analyze_campaign

MESSAGE_TYPE = "campaign_vip90_return_2026_11_07"
SUBJECT = "🔥 [توصيات الأسبوع + كود عودة بـ 90 ج] نتائج صعود إشاراتنا حتى +47.9% وهدية لـ 3 أيام فقط! 🇪🇬"


def build_vip90_email_html(user_id: str, email: str, name: str) -> str:
    unsub_token = generate_unsub_token(user_id, email)
    unsub_url = f"{APP_URL}/api/marketing/unsubscribe?uid={user_id}&email={email}&token={unsub_token}"
    checkout_url = f"{APP_URL}/pricing?ref=VIP90"
    display_name = (name or "المتداول العزيز").strip()

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>فرص وتوصيات الأسبوع + كود العودة الحصري | EGX BOTS</title>
</head>
<body style="margin:0;padding:0;background-color:#07090e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#f3f4f6;text-align:right;">
<div style="max-width:620px;margin:0 auto;padding:24px 16px;">

  <!-- Header -->
  <div style="text-align:center;padding-bottom:20px;border-bottom:2px solid #1f2937;">
    <a href="{APP_URL}" style="text-decoration:none;color:#fff;font-size:24px;font-weight:900;">EGX <span style="color:#10b981;">BOTS</span> ⚡</a>
    <div style="margin-top:6px;">
      <span style="display:inline-block;background:rgba(16,185,129,.15);border:1px solid rgba(16,185,129,.4);color:#10b981;font-size:12px;font-weight:bold;padding:4px 14px;border-radius:9999px;">
        🎯 تقرير توصيات الأسبوع + عرض العودة الحصري
      </span>
    </div>
  </div>

  <!-- Greeting -->
  <div style="padding:22px 0 14px 0;">
    <h1 style="margin:0 0 10px 0;font-size:21px;color:#ffffff;line-height:1.4;">
      مرحباً {display_name} 👋،
    </h1>
    <p style="margin:0;font-size:15px;color:#9ca3af;line-height:1.7;">
      <strong>هل تابعت ماذا فعلت إشارات وتوصيات EGX BOTS الأسبوع الماضي؟</strong><br>
      خلال جلسات الأسبوع الماضي فقط، رصدت خوارزميات الذكاء الاصطناعي الكمية صعوداً كبيراً لأسهم مختارة بدقة عالية قبل انطلاقها:
    </p>
  </div>

  <!-- Top Recommendations Box -->
  <div style="background:#0d1117;border:2px solid #10b981;border-radius:16px;padding:20px;margin-bottom:22px;">
    <h2 style="margin:0 0 14px 0;font-size:17px;color:#10b981;">
      🚀 أحدث توصيات وإشارات الأسبوع الماضي (جلسات 3 - 6 نوفمبر):
    </h2>
    <div style="font-size:14px;color:#d1d5db;line-height:1.9;">
      • <strong>سهم تايكون (TYCN):</strong> إشارة شراء حول <strong>13.33 ج</strong> بنسبة نجاح تاريخية <span style="color:#10b981;font-weight:bold;">81%</span> — صعد بالحد الأقصى في الجلسة (+20%) نحو مستهدف أول 16.40 ج ومستهدف ثانٍ <strong>18.04 ج (+35.3%)</strong>! 🔥<br>
      • <strong>سهم كفر الزيات (KZPC):</strong> إشارة دخول <strong>13.56 ج</strong> بمستهدف أول 18.24 ج (+34.5%) ومستهدف ثانٍ <strong>20.06 ج (+47.9%)</strong> بنسبة نجاح 65%.<br>
      • <strong>سهم الملتقى العربي (AMIA):</strong> إشارة شراء <strong>18.11 ج</strong> بمستهدفات <strong>21.73 ج (+20%)</strong> و <strong>23.90 ج (+32%)</strong>.<br>
      • <strong>سهم القاهرة للأدوية (CPCI):</strong> إشارة دخول <strong>601.50 ج</strong> نحو <strong>673.68 ج (+12%)</strong> و <strong>741.05 ج (+23.2%)</strong>.<br>
      • <strong>سهم الدولية للاستثمار (ICID):</strong> إشارة شراء <strong>17.98 ج</strong> بمستهدف أول <strong>23.37 ج (+30%)</strong> وثانٍ <strong>25.71 ج (+43%)</strong>.<br>
      • <strong>سهم جهينة (JUFO):</strong> إشارة شراء حول <strong>23.00 ج</strong> نحو مستهدف <strong>28.79 ج (+25.2%)</strong>.
    </div>
  </div>

  <!-- Transparent Performance Stats -->
  <div style="background:#0d1117;border:1px solid #1f2937;border-radius:16px;padding:18px;margin-bottom:22px;">
    <h2 style="margin:0 0 12px 0;font-size:16px;color:#f59e0b;">
      📊 أرقام وإحصائيات موثقة من أداء المنصة:
    </h2>
    <div style="font-size:13px;color:#d1d5db;line-height:1.8;">
      ✅ <strong>دقة إشارات غير مسبوقة:</strong> حققت إشاراتنا اليومية نسبة نجاح بين <strong>14 رابح من 15</strong> و <strong>15 رابح من 15</strong> بالجلسات السابقة.<br>
      ✅ <strong>كاشف القيمة العادلة:</strong> تم رصد أكثر من <strong>83 سهماً</strong> يتداولون حالياً بأقل من قيمتهم العادلة بفوارق ربحية تصل لأكثر من <strong>+65%</strong>.<br>
      ✅ <strong>كاشف المصائد اللحظية:</strong> رصد فوري لمصائد الارتداد الحقيقي (Spring) ومصائد الاختراق الكاذب (Upthrust) لحماية محفظتك من الهبوط المفاجئ.
    </div>
  </div>

  <!-- Special 90 EGP Offer Box -->
  <div style="background:linear-gradient(135deg, rgba(16,185,129,0.12), rgba(245,158,11,0.08));border:2px solid #f59e0b;border-radius:16px;padding:22px;text-align:center;margin-bottom:24px;">
    <span style="background:#f59e0b;color:#000;font-weight:900;font-size:11px;padding:4px 12px;border-radius:9999px;text-transform:uppercase;">
      هدية عودة حصرية ومحدودة المدة ⏳
    </span>
    <h2 style="margin:12px 0 8px 0;font-size:20px;color:#fff;">
      وفر 10 ج.م إضافية — وادفع <span style="color:#10b981;font-size:24px;font-weight:900;">90 ج.م فقط!</span>
    </h2>
    <p style="margin:0 0 16px 0;font-size:14px;color:#9ca3af;line-height:1.6;">
      تقديراً لتواجدك معنا، قمنا بإنشاء كود خصم خاص جداً:<br>
      كود الخصم: <strong style="color:#ffe600;font-size:18px;letter-spacing:1px;background:#000;padding:4px 10px;border-radius:6px;border:1px dashed #ffe600;">VIP90</strong>
    </p>
    <div style="background:#07090e;border-radius:10px;padding:12px;margin:0 auto 18px auto;max-width:380px;font-size:13px;color:#e5e7eb;line-height:1.7;">
      ⚡ <strong>صلاحية الكود:</strong> 3 أيام فقط (ينتهي منتصف ليل الثلاثاء 10 نوفمبر).<br>
      💳 <strong>طرق الدفع:</strong> فودافون كاش، انستاباي، فيزا / ماستركارد، المحافظ الإلكترونية.
    </div>
    <a href="{checkout_url}" style="display:inline-block;background:#10b981;color:#000000;font-weight:900;font-size:16px;padding:14px 32px;border-radius:12px;text-decoration:none;box-shadow:0 4px 14px rgba(16,185,129,0.4);">
      👈 تفعيل الخصم والاشتراك بـ 90 ج.م الآن
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


def get_recipients(max_batch_size: int = 75) -> List[Dict[str, Any]]:
    # Load targets from classified audit
    audit_file = os.path.join(ROOT_DIR, "scratch", "classified_targets.json")
    if not os.path.exists(audit_file):
        audit_file = "C:/Users/MR__CODER__/.gemini/antigravity/brain/4f7d6beb-f26c-4ee9-90e6-60b99bd6260b/scratch/classified_targets.json"

    with open(audit_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Fetch emails sent today in Resend to enforce 24h cooldown
    resend_today = fetch_resend_emails(max_emails=100)
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    emailed_today = set()
    for em in resend_today:
        if (em.get("created_at") or "").startswith(today_utc):
            for r in (em.get("to") or []):
                emailed_today.add(r.strip().lower())

    recipients: List[Dict[str, Any]] = []
    seen_emails = set()

    # Priority 1: Expired Pro (10 users)
    for u in data.get("expired_pro", []):
        em = u["email"].strip().lower()
        if em in emailed_today or em in seen_emails:
            continue
        recipients.append({**u, "segment": "Expired Pro (مشترك سابق)"})
        seen_emails.add(em)

    # Priority 2: Expired Trials (13 users)
    for u in data.get("expired_trials", []):
        em = u["email"].strip().lower()
        if em in emailed_today or em in seen_emails:
            continue
        recipients.append({**u, "segment": "Expired Trial (تجريبي منتهي)"})
        seen_emails.add(em)

    # Priority 3: Engaged Free leads who open emails (sorted by open count and rate)
    engaged = data.get("engaged_free", [])
    engaged_sorted = sorted(engaged, key=lambda x: (x["open_count"], x["open_rate"]), reverse=True)
    for u in engaged_sorted:
        if len(recipients) >= max_batch_size:
            break
        em = u["email"].strip().lower()
        if em in emailed_today or em in seen_emails:
            continue
        recipients.append({**u, "segment": f"Engaged Free ({u['open_rate']}% Open)"})
        seen_emails.add(em)

    return recipients


def main():
    parser = argparse.ArgumentParser(description="Send VIP90 Email Campaign")
    parser.add_argument("--dry-run", action="store_true", help="Preview recipients without sending")
    parser.add_argument("--limit", type=int, default=70, help="Maximum recipients to send to")
    args = parser.parse_args()

    recipients = get_recipients(max_batch_size=args.limit)
    print(f"=== VIP90 CAMPAIGN DISPATCH ENGINE ===")
    print(f"Target recipients selected: {len(recipients)}")
    print(f"Mode: {'DRY RUN (Preview Only)' if args.dry_run else 'LIVE DISPATCH'}")

    # Check unsubscriptions and print preview
    valid_recipients = []
    for i, r in enumerate(recipients, 1):
        if is_user_unsubscribed(r["id"], r["email"]):
            print(f"  [SKIP - Unsubscribed] {r['email']}")
            continue
        valid_recipients.append(r)
        print(f"  {i}. [{r['segment']}] {r['email']} ({r['name']}) - Opens: {r.get('open_count')}/{r.get('sent_count')} ({r.get('open_rate')}%)")

    print(f"\nTotal ready to send: {len(valid_recipients)}")

    if args.dry_run:
        print("\n[DRY RUN COMPLETE] No emails were sent.")
        return

    # Live dispatch
    sent_count = 0
    failed_count = 0
    print("\nStarting live dispatch via Resend API...")

    for i, r in enumerate(valid_recipients, 1):
        user_id = r["id"]
        email = r["email"]
        name = r["name"]
        html_content = build_vip90_email_html(user_id, email, name)

        out_data = {}
        ok = send_resend_email(email, SUBJECT, html_content, out=out_data)

        if ok:
            sent_count += 1
            record_marketing_message(
                user_id=user_id,
                email=email,
                message_type=MESSAGE_TYPE,
                metadata={
                    "campaign": "vip90_return",
                    "promo_code": "VIP90",
                    "segment": r["segment"],
                    "discount_percent": 10.0,
                },
                provider_message_id=out_data.get("provider_message_id"),
            )
            print(f"[{i}/{len(valid_recipients)}] ✅ Sent to {email} (ID: {out_data.get('provider_message_id')})")
        else:
            failed_count += 1
            print(f"[{i}/{len(valid_recipients)}] ❌ Failed to send to {email}")

        # Sleep 0.6s to respect Resend rate limits
        time.sleep(0.6)

    print(f"\n=== DISPATCH SUMMARY ===")
    print(f"Successfully Sent: {sent_count}")
    print(f"Failed: {failed_count}")

    # Automatically run and display live campaign analytics breakdown
    print("\n" + "="*50)
    print("MANDATORY POST-DISPATCH LIVE ANALYTICS BREAKDOWN")
    print("="*50)
    time.sleep(2)
    analyze_campaign()


if __name__ == "__main__":
    main()
