#!/usr/bin/env python3
"""
jobs/send_active_free_promo_report_2026_11_04.py
Dispatches a high-converting announcement report to ACTIVE NON-PRO users for 2026-11-04.
Showcases today's verified success (15/15 winning signals 100% accuracy, TYCN +19.98% limit-up),
previews tomorrow's 8 Wyckoff Spring traps and 6 Bull Traps, and includes the 100 EGP Pro upgrade offer.
"""
import os
import sys
import time
import argparse

sys.stdout.reconfigure(encoding="utf-8")
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))
load_dotenv(os.path.join(ROOT_DIR, "web", ".env.local"), override=True)

from supabase import create_client
from api.marketing_lifecycle import (
    send_resend_email,
    record_marketing_message,
    is_user_unsubscribed,
    generate_unsub_token,
    APP_URL,
)
from jobs.analyze_email_campaign import analyze_campaign

client = create_client(os.environ["NEXT_PUBLIC_SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

MESSAGE_TYPE = "active_free_promo_report_2026_11_04"
SUBJECT = "🔥 دقة 100% في إشارات اليوم (15 رابح من 15)! سهم TYCN بالحد الأقصى +20% ومصائد الغد 🇪🇬"

LINK_PRICING = "https://egxbots.com/pricing?plan=pro"
LINK_TECHNICAL = "https://egxbots.com/scanner/technical"
LINK_FAIR_VALUE = "https://egxbots.com/fair-value"


def build_email_html(user_id: str, email: str) -> str:
    unsub_token = generate_unsub_token(user_id, email)
    unsub_url = f"{APP_URL}/unsubscribe?uid={user_id}&token={unsub_token}&email={email}"

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>تقرير حصيلة السوق وعرض Pro | EGX BOTS</title>
</head>
<body style="margin:0;padding:0;background-color:#07090e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#f3f4f6;text-align:right;">
<div style="max-width:620px;margin:0 auto;padding:24px 16px;">

  <!-- Header -->
  <div style="text-align:center;padding-bottom:20px;border-bottom:2px solid #1f2937;">
    <a href="{APP_URL}" style="text-decoration:none;color:#fff;font-size:24px;font-weight:900;">EGX <span style="color:#10b981;">BOTS</span> | ARTORO AI</a>
    <div style="margin-top:8px;">
      <span style="display:inline-block;background:rgba(245,158,11,.15);border:1px solid rgba(245,158,11,.4);color:#f59e0b;font-size:12px;font-weight:bold;padding:4px 12px;border-radius:9999px;">⚡ تقرير خاص للمتداولين النشطين</span>
    </div>
  </div>

  <!-- Intro -->
  <div style="padding:20px 0 12px 0;">
    <h1 style="margin:0 0 8px 0;font-size:20px;color:#fff;line-height:1.4;">📈 أرقام استثنائية: نسبة نجاح 100% في إشارات اليوم!</h1>
    <p style="margin:0;font-size:14px;color:#9ca3af;line-height:1.6;">نشاركك نتائج رادار الذكاء الاصطناعي وكاشف المصائد بشفافية مطلقة، مع نظرة استباقية لما يجهزه كبار السوق لجلسة الغد.</p>
  </div>

  <!-- 1. Real Results / Social Proof -->
  <div style="background:#0d1117;border:2px solid #10b981;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 10px 0;font-size:16px;color:#10b981;">🚀 15 سهماً رابحاً من أصل 15 (100% نسبة نجاح إشارات الرادار اليوم!):</h2>
    <div style="font-size:13px;color:#d1d5db;line-height:1.8;">
      <div style="background:rgba(16,185,129,0.12);padding:12px;border-radius:8px;margin-bottom:12px;border-right:3px solid #10b981;">
        ⭐ <strong>سهم TYCN (التعمير والاستشارات) — نجم الجلسة الأول:</strong><br>
        أصدر الرادار إشارة الدخول عند 11.11 ج.م .. اليوم طار السهم ليسجل <strong>13.33 ج.م (+19.98% بالحد الأقصى Limit Up!)</strong> وأغلق عند 13.33 ج.م بحجم تداول قياسي <strong>9.3 أضعاف</strong> المعدل الطبيعي!<br>
      </div>
      <strong>نماذج قياسية أخرى صعدت مباشرة اليوم من إشارات الرادار ومصائد الأمس:</strong><br>
      • <strong>EGREF:</strong> من 20.66 ج ➔ قمة <strong>24.49 ج (+18.54%)</strong> وإغلاق 24.04 ج (+16.36%) بحجم 4.8x<br>
      • <strong>KWIN:</strong> صعد للحد الأقصى <strong>+20.0%</strong> وأغلق +14.65% بحجم 8.65x<br>
      • <strong>GRCA:</strong> قمة <strong>+19.07%</strong> وإغلاق +13.44% بحجم 5.4x<br>
      • <strong>WKOL:</strong> قمة <strong>+17.95%</strong> وإغلاق +12.72%<br>
      • <strong>UTOP:</strong> صعود بالحد الأقصى <strong>+10.00%</strong> إغلاقاً<br>
      • <strong>CAED (من مصائد الأمس):</strong> طار من 99.24 ج ➔ قمة <strong>111.99 ج (+12.85%)</strong> بحجم 7.4x<br>
      • <strong>BIOC (من مصائد الأمس):</strong> صعد لـ <strong>332.00 ج (+8.85%)</strong><br>
      • <strong>NHPS:</strong> قمة <strong>+11.30%</strong> | <strong>AFMC:</strong> قمة <strong>+7.17%</strong> | <strong>UEFM:</strong> +5.2%
    </div>
  </div>

  <!-- 2. Preview for Tomorrow -->
  <div style="background:#0d1117;border:2px solid #374151;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 12px 0;font-size:16px;color:#f59e0b;">🪤 ماذا يخبئ السوق لجلسة الغد؟ (كاشف المصائد الحية)</h2>
    <p style="font-size:13px;color:#d1d5db;margin-bottom:10px;line-height:1.6;">
      رصد خوارزمي وايكوف (Wyckoff Trap Detector) مع إغلاق اليوم نماذج ارتداد تجميعية حادة بجانب تحذيرات صارمة من مصائد القمم:
    </p>
    <div style="font-size:13px;color:#9ca3af;line-height:1.8;background:#111827;padding:12px;border-radius:8px;margin-bottom:12px;">
      <div style="color:#10b981;font-weight:bold;margin-bottom:6px;">🟢 مصائد الارتداد الشرائي (Spring):</div>
      • <strong>KASABF:</strong> إغلاق 7.32 ج (+20.0%) | ارتداد 100% فوق 6.70 ج | ثقة 98% وحجم 3.7x<br>
      • <strong>UTOP:</strong> إغلاق 90.53 ج (+10.0%) | ارتداد 100% فوق 85.56 ج | ثقة 92.5%<br>
      • <strong>RMDA:</strong> إغلاق 5.48 ج (+7.0%) | ارتداد 100% فوق 5.10 ج | ثقة 89.6% وحجم 2.2x<br>
      • <strong>AALR:</strong> إغلاق 251.99 ج (+16.1%) | ارتداد 85.3% فوق 224.31 ج | حجم قياسي 8.85x!<br>
      • <strong>VLMRA / CCRS / ELSH / MFPC</strong> (موبكو - ارتداد كامل 100% فوق 40.39 ج)
    </div>
    <div style="font-size:13px;color:#9ca3af;line-height:1.8;background:#111827;padding:12px;border-radius:8px;">
      <div style="color:#ef4444;font-weight:bold;margin-bottom:6px;">🔴 مصائد القمم والاختراق الكاذب (Upthrust) — احذر الشراء:</div>
      • <strong>ORHD (أوراسكوم للتنمية):</strong> رفض مقاومة 10.38 ج بذيل 100% وإغلاق 10.10 ج<br>
      • <strong>PHTV:</strong> رفض مقاومة 332.74 ج مع هبوط إلى 320.00 ج بحجم 3.17x<br>
      • <strong>EASB / GTEX / ADCI / AMOC</strong> (تصريف علوي أسفل المقاومات)
    </div>
  </div>

  <!-- 3. Fair Value Preview -->
  <div style="background:#0d1117;border:2px solid #374151;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 10px 0;font-size:16px;color:#60a5fa;">💎 80 سهماً يتداولون تحت قيمتهم الاستثمارية الحقيقية</h2>
    <p style="font-size:13px;color:#d1d5db;margin:0;line-height:1.6;">
      كاشف القيمة العادلة المحدث لـ 254 شركة مسجلة بالبورصة أظهر أن أسهماً قيادية مثل <strong>هيرميس القابضة (HRHO)</strong> تتداول حالياً عند 22.50 ج بينما قيمتها العادلة المحسوبة علمياً هي <strong>37.13 ج</strong> (فرصة صعود متوقعة تتجاوز <strong>+65%</strong>).
    </p>
  </div>

  <!-- 4. Special Pro Offer Box -->
  <div style="background:linear-gradient(135deg, rgba(16,185,129,0.15) 0%, rgba(59,130,246,0.15) 100%);border:2px solid #10b981;border-radius:16px;padding:24px;text-align:center;margin-bottom:24px;">
    <span style="background:#10b981;color:#000;font-size:11px;font-weight:900;padding:3px 10px;border-radius:9999px;text-transform:uppercase;">عرض المؤسسين المحدود</span>
    <h3 style="margin:12px 0 8px 0;font-size:20px;color:#fff;">ثبّت باقة EGX BOTS Pro بـ 100 ج.م شهرياً فقط مدى الحياة!</h3>
    <p style="margin:0 0 16px 0;font-size:13px;color:#d1d5db;line-height:1.6;">
      احصل على الوصول الكامل والفوري لكافة إشارات الرادار اللحظية، كاشف المصائد اليومي، قناة التنبيهات VIP الفورية على تليجرام، ومساعدك الذكي ARTORO بدون قيود.
    </p>
    <a href="{LINK_PRICING}" style="display:inline-block;background:#10b981;color:#000;font-weight:900;font-size:15px;padding:16px 32px;border-radius:12px;text-decoration:none;box-shadow:0 4px 15px rgba(16,185,129,0.35);">
      ⚡ تفعيل باقة Pro بـ 100 ج.م الآن ↗
    </a>
    <div style="margin-top:10px;font-size:11px;color:#9ca3af;">
      💳 دفع فوري وآمن عبر: فودافون كاش / انستاباي / فوري / بطاقات بنكية وميزة.
    </div>
  </div>

  <!-- Quick Explore Links -->
  <div style="text-align:center;margin:16px 0;">
    <a href="{LINK_TECHNICAL}" style="color:#10b981;text-decoration:underline;font-size:13px;margin:0 8px;">تصفح الماسح الفني</a> | 
    <a href="{LINK_FAIR_VALUE}" style="color:#10b981;text-decoration:underline;font-size:13px;margin:0 8px;">فحص القيمة العادلة للأسهم</a>
  </div>

  <!-- Footer -->
  <div style="border-top:1px solid #1f2937;padding-top:20px;font-size:11px;color:#6b7280;text-align:center;line-height:1.6;">
    <p style="margin:0 0 8px 0;">⚠️ إخلاء مسؤولية: منصة EGX BOTS أداة برمجية للتحليل الفني والكمي ولا تقدم توصيات استثمارية أو إدارة محافظ.</p>
    <a href="{unsub_url}" style="color:#9ca3af;text-decoration:underline;">إلغاء الاشتراك بنقرة واحدة</a>
  </div>

</div>
</body>
</html>"""


def main(dry_run: bool):
    print("=== Active Free Promo Campaign (04-11-2026) ===")

    # 1. Pro IDs to exclude
    pro_subs = client.table("subscriptions").select("user_id").in_("status", ["active", "trialing"]).execute()
    pro_ids = set(s["user_id"] for s in pro_subs.data)

    # 2. Get engaged free users from marketing events & message logs
    events = client.table("marketing_events").select("message_id").in_("event_type", ["opened", "clicked"]).execute()
    engaged_mids = list(set(e["message_id"] for e in events.data if e.get("message_id")))

    engaged_emails = set()
    if engaged_mids:
        for i in range(0, len(engaged_mids), 100):
            chunk = engaged_mids[i:i+100]
            logs = client.table("marketing_message_log").select("user_id, email").in_("id", chunk).execute().data or []
            for l in logs:
                em = (l.get("email") or "").strip().lower()
                uid = l.get("user_id")
                if em and "@" in em and uid not in pro_ids:
                    engaged_emails.add((uid, em))

    # Also include users who received recent campaigns
    recent_logs = client.table("marketing_message_log").select("user_id, email").order("sent_at", desc=True).limit(200).execute().data or []
    for l in recent_logs:
        em = (l.get("email") or "").strip().lower()
        uid = l.get("user_id")
        if em and "@" in em and uid not in pro_ids:
            engaged_emails.add((uid, em))

    recipients = list(engaged_emails)
    print(f"Targeting {len(recipients)} engaged active free users.")

    if dry_run:
        print("\n[DRY RUN] Would send to first 10 recipients:")
        for uid, em in recipients[:10]:
            print(f"  - {em} ({uid})")
        print("\nSubject:", SUBJECT)
        print("HTML length:", len(build_email_html("test_uid", "test@example.com")))
        return

    # Sending
    # Check already sent in this campaign
    already_sent_rows = client.table("marketing_message_log").select("email").eq("message_type", MESSAGE_TYPE).execute().data or []
    already_sent_emails = set((r.get("email") or "").strip().lower() for r in already_sent_rows)

    success = len(already_sent_emails)
    failed = 0
    skipped = 0

    for i, (uid, email) in enumerate(recipients, 1):
        clean_email = email.strip().lower()
        if clean_email in already_sent_emails:
            continue

        if is_user_unsubscribed(uid, email):
            skipped += 1
            continue

        html_body = build_email_html(uid, email)
        meta: dict = {}
        if send_resend_email(email, SUBJECT, html_body, out=meta):
            success += 1
            record_marketing_message(
                user_id=uid,
                email=email,
                message_type=MESSAGE_TYPE,
                metadata={"is_pro": False, "is_promo": True, "resend_id": meta.get("provider_message_id")},
                provider_message_id=meta.get("provider_message_id"),
            )
            print(f"[{i}/{len(recipients)}] ✅ {email} (ID: {meta.get('provider_message_id')})")
        else:
            failed += 1
            print(f"[{i}/{len(recipients)}] ❌ {email}")

        already_sent_emails.add(clean_email)
        time.sleep(0.4)

    print(f"\n✅ Finished! Success: {success}, Failed: {failed}, Skipped: {skipped}")

    print("\n--- Mandatory Live Email Analytics ---")
    analyze_campaign()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(args.dry_run)
