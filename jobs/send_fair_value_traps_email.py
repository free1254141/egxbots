#!/usr/bin/env python3
"""
jobs/send_fair_value_traps_email.py
Dispatches the session-close report (traps, fair value, unusual activity and
yesterday's verified signal outcomes) to ACTIVE PRO subscribers only via Resend,
followed by the mandatory live analytics breakdown.

Usage:
  python jobs/send_fair_value_traps_email.py --dry-run   # list recipients only
  python jobs/send_fair_value_traps_email.py             # send
"""
import os
import sys
import time
import argparse
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

client = create_client(os.environ['NEXT_PUBLIC_SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])

PRO_PLAN_IDS = ["pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime"]
MESSAGE_TYPE = "pro_session_report_2026_11_02"
SUBJECT = "👑 [تقرير Pro] نتائج إشارات الأمس + كاشف مصائد جلسة 02-11 وأرخص أسهم القيمة العادلة | EGX BOTS"

ROW = 'style="padding: 8px 0; border-bottom: 1px solid #1f2937;"'


def build_email_html(user_id: str, email: str) -> str:
    unsub_token = generate_unsub_token(user_id, email)
    unsub_url = f"{APP_URL}/unsubscribe?uid={user_id}&token={unsub_token}&email={email}"
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>تقرير Pro | EGX BOTS</title></head>
<body style="margin:0;padding:0;background-color:#07090e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#f3f4f6;text-align:right;">
<div style="max-width:620px;margin:0 auto;padding:24px 16px;">

  <div style="text-align:center;padding-bottom:20px;border-bottom:2px solid #1f2937;">
    <a href="{APP_URL}" style="text-decoration:none;color:#fff;font-size:24px;font-weight:900;">EGX <span style="color:#10b981;">BOTS</span> | ARTORO AI</a>
    <div style="margin-top:8px;"><span style="display:inline-block;background:rgba(16,185,129,.15);border:1px solid rgba(16,185,129,.4);color:#10b981;font-size:12px;font-weight:bold;padding:4px 12px;border-radius:9999px;">👑 تقرير المشتركين المميزين (Pro Exclusive)</span></div>
  </div>

  <div style="padding:20px 0 12px 0;">
    <h1 style="margin:0 0 8px 0;font-size:20px;color:#fff;line-height:1.4;">📊 تقرير إغلاق جلسة 02-11-2026</h1>
    <p style="margin:0;font-size:14px;color:#9ca3af;line-height:1.6;">مراجعة شفافة لنتائج إشارات الأمس، ثم مصائد اليوم، وأرخص الأسهم مقابل القيمة العادلة، وأسهم النشاط غير الطبيعي.</p>
  </div>

  <div style="background:#0d1117;border:2px solid #10b981;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 10px 0;font-size:16px;color:#10b981;">🎯 أولاً: ماذا حدث لإشارات الأمس (مصائد الارتداد 01-11)؟</h2>
    <div style="font-size:13px;color:#d1d5db;line-height:1.8;">
      • <strong>SEIG:</strong> من 223.68 ج إلى <strong>247.50 ج (+10.65%)</strong>، ولامس أثناء الجلسة <strong>268.41 ج (+20%)</strong> 🔥<br>
      • <strong>CRST:</strong> صعد لحظياً حتى 2.81 ج (+4.07%) ثم أغلق 2.68 ج (-0.74%).<br>
      • <strong>SAIB:</strong> ثبات عند 3.03 ج دون كسر الدعم.<br>
      • <strong>CANA / ADIB / LUTS / GMCI:</strong> تراجعات بين -3.4% و-5.5% مع ضغط بيعي عام.<br>
      <span style="color:#9ca3af;font-size:12px;">الحصيلة بأمانة: سهم واحد من 7 أغلق صاعداً في اليوم التالي، لكنه حقق أقوى حركة في السوق. المصائد إشارة احتمالية وليست ضماناً؛ استخدم وقف الخسارة أسفل مستوى الدعم المذكور.</span>
    </div>
  </div>

  <div style="background:#0d1117;border:2px solid #1f2937;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 12px 0;font-size:16px;color:#f59e0b;">🪤 ثانياً: كاشف المصائد لجلسة 02-11</h2>
    <div style="color:#10b981;font-weight:bold;font-size:14px;margin-bottom:6px;">🟢 مصائد الارتداد (Spring) — الإغلاق | الدعم | قوة الإشارة</div>
    <div style="font-size:13px;color:#d1d5db;line-height:1.8;margin-bottom:14px;">
      • <strong>EOSB</strong> العروبة للسمسرة: 1.69 ج | 1.64 ج | 88% (حجم 2.1x)<br>
      • <strong>SAIB</strong> بنك saib: 3.03 ج | 2.73 ج | 82%<br>
      • <strong>AMPI</strong> المؤشر باي: 2.33 ج | 2.22 ج | 74%<br>
      • <strong>COMI</strong> التجاري الدولي: 121.40 ج | 117.85 ج | 69% (حجم 1.4x)<br>
      • <strong>ADRI</strong>: 12.51 ج | 12.06 ج | 59%<br>
      • <strong>ORWE</strong> النساجون الشرقيون: 24.20 ج | 22.37 ج | 51%
    </div>
    <div style="color:#ef4444;font-weight:bold;font-size:14px;margin-bottom:6px;">🔴 مصائد الاختراق الكاذب (Upthrust) — الإغلاق | المقاومة | قوة الإشارة</div>
    <div style="font-size:13px;color:#d1d5db;line-height:1.8;">
      • <strong>ADCI</strong> العربية للأدوية: 251.56 ج | 263.02 ج | 72%<br>
      • <strong>SCTS</strong> قناة السويس لتوطين التكنولوجيا: 482.16 ج | 505.58 ج | 71%<br>
      • <strong>MPCI</strong> ممفيس للأدوية: 299.99 ج | 312.91 ج | 63%<br>
      • <strong>NIPH</strong> النيل للأدوية: 263.03 ج | 280.37 ج | 60%<br>
      <span style="color:#9ca3af;font-size:12px;">3 مصائد اختراق كاذب في قطاع الدواء في نفس الجلسة — إشارة لضغط جني أرباح على القطاع.</span>
    </div>
  </div>

  <div style="background:#0d1117;border:2px solid #1f2937;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 12px 0;font-size:16px;color:#10b981;">💎 ثالثاً: أسهم بأقل من قيمتها العادلة (من 254 سهماً: 83 رخيص، 54 عادل، 117 متضخم)</h2>
    <div style="font-size:13px;line-height:1.7;color:#e5e7eb;">
      <div {ROW}><strong>EGBE</strong> المصري الخليجي: 0.49 ج ← العادل 0.81 ج <span style="color:#10b981;font-weight:bold;">(+65.3%)</span></div>
      <div {ROW}><strong>PRMH</strong> برايم القابضة: 1.81 ج ← العادل 2.99 ج <span style="color:#10b981;font-weight:bold;">(+65.2%)</span></div>
      <div {ROW}><strong>RACC</strong> راية لمراكز الاتصالات: 7.27 ج ← العادل 12.00 ج <span style="color:#10b981;font-weight:bold;">(+65.1%)</span></div>
      <div style="padding:8px 0;"><strong>ASPI</strong> أسباير كابيتال: 0.29 ج ← العادل 0.48 ج <span style="color:#10b981;font-weight:bold;">(+65.5%)</span></div>
      <span style="color:#9ca3af;font-size:12px;">القيمة العادلة نموذج كمي (جراهام/مضاعفات القطاع/VWAP) يعتمد على آخر بيانات مالية متاحة، ويُحدّث يومياً مع سعر الإغلاق.</span>
    </div>
  </div>

  <div style="background:#0d1117;border:2px solid #1f2937;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 12px 0;font-size:16px;color:#3b82f6;">⚡ رابعاً: النشاط غير الطبيعي (حجم ≥ 2x متوسط 20 جلسة)</h2>
    <div style="font-size:13px;color:#d1d5db;line-height:1.8;">
      • <strong>ELWA</strong>: حجم 7.9x | تغير -4.67%<br>
      • <strong>SEIG</strong>: حجم 6.7x | تغير +10.65%<br>
      • <strong>PRCL</strong>: حجم 5.3x | تغير +5.36%<br>
      • <strong>EPCO</strong>: حجم 4.9x | تغير +1.63%<br>
      • <strong>GTWL</strong>: حجم 3.6x | تغير +5.31%<br>
      <span style="color:#9ca3af;font-size:12px;">اختبار تاريخي مبدئي على 52 حالة لأسهم قيادية: 61.5% حققت إغلاقاً صاعداً أو صعوداً لحظياً ≥2% في الجلسة التالية، بمتوسط أقصى صعود +5% خلال 3 جلسات. الحجم المرتفع مع هبوط السعر قد يعني تصريفاً لا تجميعاً.</span>
    </div>
  </div>

  <div style="text-align:center;margin:28px 0 20px 0;">
    <a href="{APP_URL}/scanner/technical" style="display:block;background:#10b981;color:#000;font-weight:900;font-size:15px;padding:14px 24px;border-radius:12px;text-decoration:none;margin-bottom:10px;">🪤 افتح كاشف المصائد والنشاط غير الطبيعي ↗</a>
    <a href="{APP_URL}/fair-value" style="display:block;background:#1f2937;color:#fff;font-weight:bold;font-size:14px;padding:12px 24px;border-radius:12px;text-decoration:none;">💎 القيمة العادلة لكل أسهم السوق ↗</a>
  </div>

  <div style="border-top:1px solid #1f2937;padding-top:18px;font-size:11px;color:#6b7280;text-align:center;line-height:1.6;">
    <p style="margin:0 0 8px 0;">⚠️ إخلاء مسؤولية: EGX BOTS أداة تحليل فني وكمي ولا تقدم توصيات استثمارية. النتائج السابقة لا تضمن النتائج المستقبلية، وقرارات البيع والشراء مسؤوليتك.</p>
    <p style="margin:0;">تصلك هذه الرسالة كمشترك Pro في EGX BOTS. <a href="{unsub_url}" style="color:#9ca3af;text-decoration:underline;">إلغاء الاشتراك</a></p>
  </div>
</div>
</body>
</html>"""


def active_pro_user_ids() -> set:
    now = datetime.now(timezone.utc)
    rows = (client.table('subscriptions').select('user_id,plan_id,status,current_period_end')
            .in_('plan_id', PRO_PLAN_IDS).in_('status', ['active', 'trialing']).limit(1000).execute().data or [])
    ids = set()
    for r in rows:
        end = r.get('current_period_end')
        if end:
            try:
                if datetime.fromisoformat(str(end).replace('Z', '+00:00')) < now:
                    continue
            except ValueError:
                pass
        ids.add(r['user_id'])
    return ids


def already_sent_emails() -> set:
    rows = (client.table('marketing_message_log').select('email')
            .eq('message_type', MESSAGE_TYPE).limit(1000).execute().data or [])
    return {str(r.get('email') or '').lower() for r in rows}


def main(dry_run: bool):
    print("=== Pro Session Report Campaign (02-11-2026) ===")
    pro_ids = active_pro_user_ids()
    users_resp = client.auth.admin.list_users(page=1, per_page=1000)
    auth_users = users_resp if isinstance(users_resp, list) else getattr(users_resp, 'users', [])
    sent_before = already_sent_emails()

    candidates, seen = [], set()
    for u in auth_users:
        email = (getattr(u, 'email', None) or '').strip().lower()
        if u.id not in pro_ids or '@' not in email or email in seen:
            continue
        local = email.split('@')[0]
        if local in ('user', 'test', 'admin') or 'fake' in email or 'test' in local:
            continue  # placeholder / test accounts
        seen.add(email)
        candidates.append({'user_id': u.id, 'email': email})

    print(f"Active Pro subscribers with email: {len(candidates)} (already sent this report: {len(sent_before)})")
    if dry_run:
        for c in candidates:
            print("  -", c['email'], "(already sent)" if c['email'] in sent_before else "")
        return

    ok_count = fail_count = skip_count = 0
    for i, c in enumerate(candidates, 1):
        uid, email = c['user_id'], c['email']
        if email in sent_before or is_user_unsubscribed(uid, email):
            skip_count += 1
            print(f"[{i}/{len(candidates)}] skip {email}")
            continue
        meta = {}
        if send_resend_email(email, SUBJECT, build_email_html(uid, email), out=meta):
            ok_count += 1
            record_marketing_message(user_id=uid, email=email, message_type=MESSAGE_TYPE,
                                     metadata={"is_pro": True, "resend_id": meta.get("id")},
                                     provider_message_id=meta.get("id"))
            print(f"[{i}/{len(candidates)}] ✅ {email} ({meta.get('id')})")
        else:
            fail_count += 1
            print(f"[{i}/{len(candidates)}] ❌ {email}")
        time.sleep(0.4)

    print(f"\nSent {ok_count} | failed {fail_count} | skipped {skip_count}")
    print("\n" + "=" * 50 + "\nLive Post-Dispatch Analytics\n" + "=" * 50)
    time.sleep(2)
    analyze_campaign()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--dry-run', action='store_true')
    main(p.parse_args().dry_run)
