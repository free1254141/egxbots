#!/usr/bin/env python3
"""
jobs/send_active_free_promo_report_2026_11_03.py
Dispatches a high-converting announcement report to ACTIVE NON-PRO users.
Showcases today's verified success (SEIG +13.13%, 14/15 winning signals),
previews tomorrow's 19 Wyckoff Spring traps, and includes the 100 EGP Pro upgrade offer.
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

MESSAGE_TYPE = "active_free_promo_report_2026_11_03"
SUBJECT = "🔥 كيف حققت إشاراتنا +13.1% اليوم في SEIG (و14 رابح من 15)! مصائد الغد + عرض Pro"

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
    <h1 style="margin:0 0 8px 0;font-size:20px;color:#fff;line-height:1.4;">📈 أرقام حقيقية لا تكذب: ماذا حدث في جلسة اليوم؟</h1>
    <p style="margin:0;font-size:14px;color:#9ca3af;line-height:1.6;">نشاركك نتائج رادار الذكاء الاصطناعي وكاشف المصائد بشفافية مطلقة، مع نظرة استباقية لما يجهزه كبار السوق لجلسة الغد.</p>
  </div>

  <!-- 1. Real Results / Social Proof -->
  <div style="background:#0d1117;border:2px solid #10b981;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 10px 0;font-size:16px;color:#10b981;">🚀 14 سهماً رابحاً من أصل 15 (93.3% نسبة دقة اليوم!):</h2>
    <div style="font-size:13px;color:#d1d5db;line-height:1.8;">
      <div style="background:rgba(16,185,129,0.12);padding:12px;border-radius:8px;margin-bottom:12px;border-right:3px solid #10b981;">
        ⭐ <strong>سهم SEIG (إيكون) — نجم الجلسات الثلاث بلا منازع:</strong><br>
        أصدر الرادار إشارة دخول أمس عند 247.50 ج .. اليوم طار السهم ليسجل <strong>280.00 ج (+13.13% صعود لحظي)</strong> وأغلق عند 266.15 ج (+7.54%) بحجم تداول قياسي <strong>9.9 أضعاف</strong> المعدل الطبيعي!<br>
        <span style="color:#10b981;font-weight:bold;">النتيجة: مكسب تراكمي تخطى +50.2% في 3 جلسات فقط لمن التزم بالإشارة!</span>
      </div>
      <strong>نماذج أخرى صعدت مباشرة اليوم من إشارات الأمس:</strong><br>
      • <strong>PRMH:</strong> من 1.81 ج ➔ قمة 1.95 ج (+7.73%) بحجم 4.0x<br>
      • <strong>QNBE:</strong> من 50.50 ج ➔ قمة 52.80 ج (+4.55%) بحجم 2.4x<br>
      • <strong>AMES:</strong> من 32.50 ج ➔ قمة 34.00 ج (+4.62%) بحجم 2.1x<br>
      • <strong>EPCO:</strong> من 8.11 ج ➔ قمة 8.45 ج (+4.19%) بحجم 6.3x<br>
      • <strong>GTWL:</strong> من 125.00 ج ➔ قمة 132.80 ج (+6.24%)<br>
      • <strong>ORWE (مصيدة القاع):</strong> صعد لـ 24.99 ج (+3.26%) وأغلق صاعداً.
    </div>
  </div>

  <!-- 2. Preview for Tomorrow -->
  <div style="background:#0d1117;border:2px solid #374151;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 12px 0;font-size:16px;color:#f59e0b;">🪤 ماذا يخبئ السوق لجلسة الغد؟ (19 مصيدة ارتداد تجميعية)</h2>
    <p style="font-size:13px;color:#d1d5db;margin-bottom:10px;line-height:1.6;">
      رصد خوارزمي وايكوف (Wyckoff Trap Detector) مع إغلاق اليوم <strong>19 سهماً</strong> أنهت اختبارات قيعان وهمية (Spring) بذيول شرائية قوية تدل على تجميع ذكي استعداداً لارتداد فوري، من بينها:
    </p>
    <div style="font-size:13px;color:#9ca3af;line-height:1.8;background:#111827;padding:12px;border-radius:8px;">
      • <strong>CAED:</strong> ارتداد كامل 100% فوق دعم 94.88 ج (ثقة 98% وحجم 5.6x)<br>
      • <strong>FIRE:</strong> ارتداد 100% فوق دعم 3.81 ج (ثقة 98%)<br>
      • <strong>EMFD (إعمار مصر):</strong> إغلاق 12.21 ج فوق دعم 12.00 ج بحجم 4.7x<br>
      • <strong>EGREF / AFMC / BIOC / CICH / CRST</strong> وغيرها 14 سهماً آخرين..
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
    print("=== Active Free Promo Campaign (03-11-2026) ===")

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

    # Filter out fake / test accounts
    candidates = []
    seen = set()
    for uid, em in engaged_emails:
        if em in seen:
            continue
        local = em.split("@")[0]
        if local in ("user", "test", "admin") or "fake" in em or "test" in local or "example." in em:
            continue
        seen.add(em)
        candidates.append({"user_id": uid, "email": em})

    # Check already sent for this campaign
    sent_rows = client.table("marketing_message_log").select("email").eq("message_type", MESSAGE_TYPE).limit(1000).execute().data or []
    sent_before = {str(r.get("email") or "").lower() for r in sent_rows}

    print(f"Total Eligible Active Free Candidates: {len(candidates)} (Already sent: {len(sent_before)})")
    if dry_run:
        for c in candidates:
            status = "ALREADY_SENT" if c["email"] in sent_before else "READY_TO_SEND"
            print(f"  [{status}] {c['email']}")
        return

    ok_count = fail_count = skip_count = 0
    for i, c in enumerate(candidates, 1):
        uid, email = c["user_id"], c["email"]
        if email in sent_before or is_user_unsubscribed(uid, email):
            skip_count += 1
            print(f"[{i}/{len(candidates)}] Skip {email}")
            continue

        meta = {}
        html = build_email_html(uid, email)
        if send_resend_email(email, SUBJECT, html, out=meta):
            ok_count += 1
            record_marketing_message(
                user_id=uid,
                email=email,
                message_type=MESSAGE_TYPE,
                metadata={"is_pro": False, "is_promo": True, "resend_id": meta.get("id")},
                provider_message_id=meta.get("id"),
            )
            print(f"[{i}/{len(candidates)}] ✅ {email} (ID: {meta.get('id')})")
        else:
            fail_count += 1
            print(f"[{i}/{len(candidates)}] ❌ {email}")
        time.sleep(0.4)

    print(f"\nFinished Active Free Promo Dispatch: Sent={ok_count}, Failed={fail_count}, Skipped={skip_count}")
    print("\n" + "=" * 50 + "\nLive Post-Dispatch Analytics\n" + "=" * 50)
    time.sleep(2)
    analyze_campaign()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    main(parser.parse_args().dry_run)
