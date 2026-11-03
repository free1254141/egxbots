#!/usr/bin/env python3
"""
jobs/send_pro_daily_report_2026_11_03.py
Dispatches the verified Pro Session Report for 2026-11-03 to ACTIVE PRO subscribers via Resend.
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

PRO_PLAN_IDS = ["pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime"]
MESSAGE_TYPE = "pro_session_report_2026_11_03_close"
SUBJECT = "👑 [تقرير Pro] نتائج إشارات الأمس (14 رابح من 15) + 19 مصيدة ارتداد لجلسة الغد | EGX BOTS"

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
  <title>تقرير Pro الحصري | EGX BOTS</title>
</head>
<body style="margin:0;padding:0;background-color:#07090e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#f3f4f6;text-align:right;">
<div style="max-width:620px;margin:0 auto;padding:24px 16px;">

  <!-- Header -->
  <div style="text-align:center;padding-bottom:20px;border-bottom:2px solid #1f2937;">
    <a href="{APP_URL}" style="text-decoration:none;color:#fff;font-size:24px;font-weight:900;">EGX <span style="color:#10b981;">BOTS</span> | ARTORO AI</a>
    <div style="margin-top:8px;">
      <span style="display:inline-block;background:rgba(16,185,129,.15);border:1px solid rgba(16,185,129,.4);color:#10b981;font-size:12px;font-weight:bold;padding:4px 12px;border-radius:9999px;">👑 التقرير الحصري لمشتركي Pro (جلسة 03-11-2026)</span>
    </div>
  </div>

  <!-- Intro -->
  <div style="padding:20px 0 12px 0;">
    <h1 style="margin:0 0 8px 0;font-size:20px;color:#fff;line-height:1.4;">📊 حصيلة تداول اليوم ونتائج الإشارات السابقة</h1>
    <p style="margin:0;font-size:14px;color:#9ca3af;line-height:1.6;">تقرير يومي يدمج نتائج إشارات الأمس في تداول اليوم بشفافية كاملة، مع رصد مصائد جلسة الغد وأسهم القيمة العادلة.</p>
  </div>

  <!-- 1. Review of Yesterday Signals -->
  <div style="background:#0d1117;border:2px solid #10b981;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 10px 0;font-size:16px;color:#10b981;">🎯 أولاً: ماذا حققت إشارات أمس في جلسة اليوم؟</h2>
    <div style="font-size:13px;color:#d1d5db;line-height:1.8;">
      <div style="background:rgba(16,185,129,0.1);padding:10px;border-radius:8px;margin-bottom:12px;border-right:3px solid #10b981;">
        🔥 <strong>سهم الجلسة الأقوى (SEIG - إيكون):</strong><br>
        سعر إشارة أمس: 247.50 ج ➔ سجل اليوم قمة عند <strong>280.00 ج (+13.13%)</strong> وأغلق عند <strong>266.15 ج (+7.54%)</strong> بحجم تداول ضخم <strong>9.9x</strong> المتوسط! (مكسب إجمالي +50.2% خلال 3 جلسات فقط).
      </div>
      <strong>📈 نشاط غير طبيعي وانفجار سعري (14 رابح من أصل 15 سهم = 93.3% نسبة نجاح):</strong><br>
      • <strong>PRMH:</strong> من 1.81 ج ➔ قمة 1.95 ج (+7.73%) | إغلاق 1.93 ج (+6.63%) [حجم 4.0x]<br>
      • <strong>QNBE:</strong> من 50.50 ج ➔ قمة 52.80 ج (+4.55%) | إغلاق 52.47 ج (+3.90%)<br>
      • <strong>AMES:</strong> من 32.50 ج ➔ قمة 34.00 ج (+4.62%) | إغلاق 33.74 ج (+3.82%)<br>
      • <strong>EPCO:</strong> من 8.11 ج ➔ قمة 8.45 ج (+4.19%) | إغلاق 8.37 ج (+3.21%) [حجم 6.3x]<br>
      • <strong>ISMA:</strong> من 18.53 ج ➔ قمة 19.23 ج (+3.78%) | إغلاق 19.05 ج (+2.81%)<br>
      • <strong>GTWL:</strong> من 125.00 ج ➔ قمة 132.80 ج (+6.24%) | إغلاق 127.50 ج (+2.00%)<br>
      • <strong>ORWE (مصيدة Spring):</strong> صعد إلى 24.99 ج (+3.26%) وأغلق 24.80 ج (+2.48%)<br>
      • <strong>COMI:</strong> حافظ على الدعم وصعد إلى 123.50 ج (+1.73%)
    </div>
  </div>

  <!-- 2. Wyckoff Traps for Tomorrow -->
  <div style="background:#0d1117;border:2px solid #1f2937;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 12px 0;font-size:16px;color:#f59e0b;">🪤 ثانياً: كاشف المصائد لجلسة الغد (إغلاق 03-11)</h2>
    <div style="color:#10b981;font-weight:bold;font-size:14px;margin-bottom:6px;">🟢 مصائد الارتداد الشرائي (Spring) — رصد 19 سهماً:</div>
    <div style="font-size:13px;color:#d1d5db;line-height:1.8;margin-bottom:14px;">
      • <strong>CAED:</strong> إغلاق 99.24 ج | دعم 94.88 ج | ذيل ارتدادي 100% | ثقة 98% (حجم 5.6x) ⭐<br>
      • <strong>FIRE:</strong> إغلاق 4.13 ج | دعم 3.81 ج | ذيل ارتدادي 100% | ثقة 98% ⭐<br>
      • <strong>EGREF:</strong> إغلاق 20.66 ج | دعم 19.11 ج | ذيل 84.4% | ثقة 87.9%<br>
      • <strong>AFMC:</strong> إغلاق 132.00 ج | دعم 126.99 ج | ذيل 84.3% | ثقة 87.8%<br>
      • <strong>BIOC:</strong> إغلاق 305.00 ج | دعم 283.61 ج | ذيل 100% | ثقة 85.2%<br>
      • <strong>EMFD (إعمار مصر):</strong> إغلاق 12.21 ج | دعم 12.00 ج | ذيل 78.1% | ثقة 83.8% (حجم 4.7x)<br>
      • <strong>RREI:</strong> إغلاق 0.81 ج | دعم 0.79 ج | ذيل 85.2% | ثقة 80.4%<br>
      • <strong>EDFM:</strong> إغلاق 1.09 ج | دعم 1.07 ج | ذيل 65.0% | ثقة 77.0%<br>
      • <strong>CICH (سي آي كابيتال):</strong> إغلاق 7.70 ج | دعم 7.55 ج | ذيل 66.7% | ثقة 73.0%<br>
      • <strong>CRST:</strong> إغلاق 1.70 ج | دعم 1.67 ج | ذيل 61.5% | ثقة 70.0%
    </div>
    <div style="color:#9ca3af;font-size:12px;">
      ℹ️ قاعدة التداول: الشراء بالقرب من الإغلاق مع وضع وقف خسارة حازم بإغلاق تحت الدعم المذكور.
    </div>
  </div>

  <!-- 3. Fair Value Gems -->
  <div style="background:#0d1117;border:2px solid #1f2937;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 12px 0;font-size:16px;color:#10b981;">💎 ثالثاً: أسهم بأقل من قيمتها العادلة (80 سهماً رخيصاً في السوق)</h2>
    <div style="font-size:13px;line-height:1.8;color:#e5e7eb;">
      • <strong>HRHO (هيرميس القابضة):</strong> السعر 22.50 ج | القيمة العادلة <strong>37.13 ج</strong> | صعود متوقع <strong>+65.0%</strong> (مضاعفات القطاع المالي)<br>
      • <strong>SAIB (بنك الشركة المصرفية):</strong> السعر 3.03 ج | القيمة العادلة <strong>5.00 ج</strong> | صعود متوقع <strong>+65.0%</strong><br>
      • <strong>RACC (راية لمراكز الاتصالات):</strong> السعر 7.55 ج | القيمة العادلة <strong>12.46 ج</strong> | صعود متوقع <strong>+65.0%</strong><br>
      • <strong>EGBE (المصري الخليجي):</strong> السعر 0.49 ج | القيمة العادلة <strong>0.81 ج</strong> | صعود متوقع <strong>+65.6%</strong><br>
      • <strong>ELKA (القاهرة للإسكان):</strong> السعر 1.41 ج | القيمة العادلة <strong>2.33 ج</strong> | صعود متوقع <strong>+65.3%</strong><br>
      • <strong>DEIN (دايس للملابس):</strong> السعر 10.35 ج | القيمة العادلة <strong>17.08 ج</strong> | صعود متوقع <strong>+65.0%</strong>
    </div>
  </div>

  <!-- Action Buttons -->
  <div style="text-align:center;margin:28px 0;">
    <a href="{LINK_TECHNICAL}" style="display:inline-block;background:#10b981;color:#000;font-weight:900;font-size:14px;padding:14px 24px;border-radius:10px;text-decoration:none;margin:4px;">
      🔍 فتح الماسح الفني وكاشف المصائد ↗
    </a>
    <a href="{LINK_FAIR_VALUE}" style="display:inline-block;background:#1f2937;color:#fff;font-weight:bold;font-size:14px;padding:14px 24px;border-radius:10px;text-decoration:none;margin:4px;border:1px solid #374151;">
      ⚖️ فحص القيمة العادلة لـ 254 سهماً ↗
    </a>
  </div>

  <!-- Footer -->
  <div style="border-top:1px solid #1f2937;padding-top:20px;font-size:11px;color:#6b7280;text-align:center;line-height:1.6;">
    <p style="margin:0 0 8px 0;">تصلك هذه الرسالة بصفتك مشتركاً متميزاً في باقة EGX BOTS Pro.</p>
    <a href="{unsub_url}" style="color:#9ca3af;text-decoration:underline;">إلغاء الاشتراك بنقرة واحدة</a>
  </div>

</div>
</body>
</html>"""


def main(dry_run: bool):
    print("=== Pro Session Report Campaign (03-11-2026) ===")
    
    # Get active pro IDs
    pro_subs = client.table("subscriptions").select("user_id").in_("status", ["active", "trialing"]).execute()
    pro_ids = set(s["user_id"] for s in pro_subs.data)

    users_resp = client.auth.admin.list_users(page=1, per_page=1000)
    auth_users = users_resp if isinstance(users_resp, list) else getattr(users_resp, "users", [])

    # Check already sent
    sent_rows = client.table("marketing_message_log").select("email").eq("message_type", MESSAGE_TYPE).limit(1000).execute().data or []
    sent_before = {str(r.get("email") or "").lower() for r in sent_rows}

    candidates = []
    seen = set()
    for u in auth_users:
        em = (getattr(u, "email", None) or "").strip().lower()
        if u.id not in pro_ids or "@" not in em or em in seen:
            continue
        local = em.split("@")[0]
        if local in ("user", "test", "admin") or "fake" in em or "test" in local:
            continue
        seen.add(em)
        candidates.append({"user_id": u.id, "email": em})

    print(f"Active Pro subscribers with valid email: {len(candidates)} (Already sent: {len(sent_before)})")
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
                metadata={"is_pro": True, "resend_id": meta.get("id")},
                provider_message_id=meta.get("id"),
            )
            print(f"[{i}/{len(candidates)}] ✅ {email} (ID: {meta.get('id')})")
        else:
            fail_count += 1
            print(f"[{i}/{len(candidates)}] ❌ {email}")
        time.sleep(0.4)

    print(f"\nFinished Pro Dispatch: Sent={ok_count}, Failed={fail_count}, Skipped={skip_count}")
    print("\n" + "=" * 50 + "\nLive Post-Dispatch Analytics\n" + "=" * 50)
    time.sleep(2)
    analyze_campaign()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    main(parser.parse_args().dry_run)
