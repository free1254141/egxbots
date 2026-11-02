#!/usr/bin/env python3
"""
jobs/send_fair_value_traps_email.py
Dispatches Fair Value & Wyckoff Traps Report to Pro & Active Users via Resend.
Followed by automatic live analytics reporting.
"""
import os
import sys
import time
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
client = create_client(url, key)

def build_email_html(user_id: str, email: str, is_pro: bool) -> str:
    unsub_token = generate_unsub_token(user_id, email)
    unsub_url = f"{APP_URL}/unsubscribe?uid={user_id}&token={unsub_token}&email={email}"
    
    badge_text = "👑 تقرير المشتركين المميزين (Pro Exclusive)" if is_pro else "📊 تقرير خاص للمتداولين النشطين"
    pro_perk = ""
    if not is_pro:
        pro_perk = f"""
        <div style="background: rgba(245, 158, 11, 0.1); border: 2px solid #f59e0b; border-radius: 12px; padding: 16px; margin: 24px 0; text-align: right;">
          <h4 style="margin: 0 0 8px 0; color: #f59e0b; font-size: 15px;">⚡ فك تشفير باقي مصائد السوق وتشغيل إعادة تدوير المحفظة:</h4>
          <p style="margin: 0; color: #d1d5db; font-size: 13px; line-height: 1.6;">
            في باقة Pro، يمكنك فك تشفير كافة مصائد السوق الحية يومياً، واستخدام أداة <strong>«إعادة تدوير المحفظة بالذكاء الاصطناعي»</strong> لفحص أسهمك الراكدة وتدوير السيولة الميتة.
          </p>
          <div style="margin-top: 12px;">
            <a href="{APP_URL}/pricing?plan=pro" style="display: inline-block; background: #10b981; color: #000; font-weight: bold; font-size: 13px; padding: 8px 16px; border-radius: 8px; text-decoration: none;">الترقية لباقة Pro وتثبيت سعر العرض ↗</a>
          </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>تقرير إغلاق البورصة المصرية | EGX BOTS</title>
</head>
<body style="margin: 0; padding: 0; background-color: #07090e; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; color: #f3f4f6; text-align: right;">
  <div style="max-width: 620px; margin: 0 auto; padding: 24px 16px;">
    
    <!-- Header -->
    <div style="text-align: center; padding-bottom: 24px; border-bottom: 2px solid #1f2937;">
      <a href="{APP_URL}" style="text-decoration: none; color: #ffffff; font-size: 24px; font-weight: 900; letter-spacing: -0.5px;">
        EGX <span style="color: #10b981;">BOTS</span> | ARTORO AI
      </a>
      <div style="margin-top: 8px;">
        <span style="display: inline-block; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); color: #10b981; font-size: 12px; font-weight: bold; padding: 4px 12px; border-radius: 9999px;">
          {badge_text}
        </span>
      </div>
    </div>

    <!-- Main Title -->
    <div style="padding: 24px 0 16px 0;">
      <h1 style="margin: 0 0 8px 0; font-size: 20px; color: #ffffff; line-height: 1.4;">
        📊 تقرير إغلاق البورصة المصرية (جلسة 01-11-2026)
      </h1>
      <p style="margin: 0; font-size: 14px; color: #9ca3af; line-height: 1.6;">
        ملخص مؤسسي دقيق لأرخص 5 أسهم متداولة بأقل من قيمتها العادلة، مع رصد مصائد القيعان والقمم الحية (Wyckoff Traps).
      </p>
    </div>

    <!-- Section 1: Fair Value -->
    <div style="background: #0d1117; border: 2px solid #1f2937; border-radius: 16px; padding: 20px; margin-bottom: 20px;">
      <h2 style="margin: 0 0 16px 0; font-size: 16px; color: #10b981; display: flex; align-items: center; gap: 8px;">
        💎 أولاً: أبرز الأسهم المتداولة بأقل من قيمتها العادلة:
      </h2>
      <div style="font-size: 13px; line-height: 1.7; color: #e5e7eb;">
        <div style="padding: 10px 0; border-bottom: 1px solid #1f2937;">
          <strong style="color: #ffffff;">1. البنك التجاري الدولي (COMI):</strong> الحالي <strong>85.00 ج</strong> | العادل <strong>103.40 ج</strong> <span style="color: #10b981; font-weight: bold;">(+21.6%)</span><br>
          <span style="color: #9ca3af; font-size: 12px;">• تقييم مالي: مكرر ربحية 5.7x ومضاعف دفترية 1.68x مع قوة ملاءة تشغيلية.</span>
        </div>
        <div style="padding: 10px 0; border-bottom: 1px solid #1f2937;">
          <strong style="color: #ffffff;">2. بنك فيصل الإسلامي (FAIT):</strong> الحالي <strong>43.20 ج</strong> | العادل <strong>52.80 ج</strong> <span style="color: #10b981; font-weight: bold;">(+22.2%)</span><br>
          <span style="color: #9ca3af; font-size: 12px;">• تقييم مالي: ربحية سهم 11.34 ج وتداول بخصم عن قيمته الدفترية (0.59x).</span>
        </div>
        <div style="padding: 10px 0; border-bottom: 1px solid #1f2937;">
          <strong style="color: #ffffff;">3. بنك الكويت الوطني (NBKE):</strong> الحالي <strong>31.00 ج</strong> | العادل <strong>51.15 ج</strong> <span style="color: #10b981; font-weight: bold;">(+65.0%)</span><br>
          <span style="color: #9ca3af; font-size: 12px;">• تقييم مالي: مكرر ربحية منخفض جداً (2.4x) وفرصة استثمارية متحفظة.</span>
        </div>
        <div style="padding: 10px 0; border-bottom: 1px solid #1f2937;">
          <strong style="color: #ffffff;">4. كيما (EGCH):</strong> الحالي <strong>10.20 ج</strong> | العادل <strong>16.80 ج</strong> <span style="color: #10b981; font-weight: bold;">(+64.7%)</span><br>
          <span style="color: #9ca3af; font-size: 12px;">• تقييم مالي: قيمة دفترية تفوق 21.6 ج للسهم مع بدء ارتداد هوامش التشغيل.</span>
        </div>
        <div style="padding: 10px 0;">
          <strong style="color: #ffffff;">5. دايس للملابس (DEIN):</strong> الحالي <strong>10.36 ج</strong> | العادل <strong>14.50 ج</strong> <span style="color: #10b981; font-weight: bold;">(+39.9%)</span><br>
          <span style="color: #9ca3af; font-size: 12px;">• تقييم مالي: نمو تصديري متسارع وربحية سنوية 5.3 ج تدعم التوسع.</span>
        </div>
      </div>
    </div>

    <!-- Section 2: Wyckoff Traps -->
    <div style="background: #0d1117; border: 2px solid #1f2937; border-radius: 16px; padding: 20px; margin-bottom: 20px;">
      <h2 style="margin: 0 0 16px 0; font-size: 16px; color: #f59e0b;">
        🪤 ثانياً: كاشف المصائد والانعكاسات الحية (Wyckoff Traps):
      </h2>
      
      <div style="margin-bottom: 14px;">
        <div style="color: #10b981; font-weight: bold; font-size: 14px; margin-bottom: 6px;">
          🟢 مصائد القيعان والارتداد الشرائي (Spring):
        </div>
        <div style="font-size: 13px; color: #d1d5db; line-height: 1.6;">
          • <strong>ADIB (أبوظبي الإسلامي):</strong> كسر وهمي عند 46.43 ج ثم ارتداد قوي للإغلاق عند 47.90 ج بذيل 94.6% (قوة 73/100).<br>
          • <strong>CANA (قناة السويس):</strong> ارتداد بنسبة 82.6% فوق مستوى 43.74 ج للإغلاق عند 47.63 ج.<br>
          • <strong>CRST (كريست مارك):</strong> شمعة ارتداد 100% فوق 2.64 ج للإغلاق عند 2.70 ج.
        </div>
      </div>

      <div>
        <div style="color: #ef4444; font-weight: bold; font-size: 14px; margin-bottom: 6px;">
          🔴 مصائد القمم والتصريف الوهمي (Upthrust):
        </div>
        <div style="font-size: 13px; color: #d1d5db; line-height: 1.6;">
          • <strong>AMOC (أموك):</strong> اختراق وهمي لمقاومة 14.54 ج ثم إغلاق هابط عند 14.31 ج بذيل تصريفي 73% (يُنصح بتفعيل وقف الخسارة).<br>
          • <strong>CIEB (كريدي أجريكول):</strong> ذيل تصريفي 88% بعد ملامسة 23.25 ج والإغلاق عند 22.64 ج.
        </div>
      </div>
    </div>

    {pro_perk}

    <!-- Call to Actions -->
    <div style="text-align: center; margin: 32px 0 24px 0;">
      <a href="{APP_URL}/scanner/technical" style="display: block; background: #10b981; color: #000000; font-weight: 900; font-size: 15px; padding: 14px 24px; border-radius: 12px; text-decoration: none; margin-bottom: 10px;">
        🪤 فتح كاشف المصائد بالكامل في المنصة ↗
      </a>
      <a href="{APP_URL}/fair-value" style="display: block; background: #1f2937; color: #ffffff; font-weight: bold; font-size: 14px; padding: 12px 24px; border-radius: 12px; text-decoration: none;">
        💎 فحص القيمة العادلة لأي سهم بالبورصة ↗
      </a>
    </div>

    <!-- Footer & Disclaimer -->
    <div style="border-top: 1px solid #1f2937; padding-top: 20px; font-size: 11px; color: #6b7280; text-align: center; line-height: 1.6;">
      <p style="margin: 0 0 8px 0;">
        ⚠️ إخلاء مسؤولية: منصة EGX BOTS هي أداة برمجية للتحليل الفني والكمي وقراءة حركة السوق ولا تقدم أي توصيات استثمارية أو إدارة محافظ. قرارات البيع والشراء مسؤوليتك المستقلة.
      </p>
      <p style="margin: 0;">
        تصلك هذه الرسالة لأنك مسجل في منصة EGX BOTS. 
        <a href="{unsub_url}" style="color: #9ca3af; text-decoration: underline;">إلغاء الاشتراك بنقرة واحدة</a>
      </p>
    </div>

  </div>
</body>
</html>"""
    return html

def main():
    print("=== Launching Email Campaign: Fair Value & Wyckoff Traps Report ===")
    
    # 1. Gather Pro and Active Users
    users_resp = client.auth.admin.list_users()
    auth_users = users_resp if isinstance(users_resp, list) else getattr(users_resp, 'users', [])
    user_map = {u.id: u.email for u in auth_users if getattr(u, 'email', None)}

    subs_res = client.table('subscriptions').select('user_id, plan_id, status').in_('status', ['active', 'trialing']).execute()
    pro_ids = set(s['user_id'] for s in (subs_res.data or []))

    pos_res = client.table('positions').select('user_id').eq('status', 'open').execute()
    pos_ids = set(p['user_id'] for p in (pos_res.data or []))

    active_log_res = client.table('marketing_message_log').select('user_id, email').execute()
    active_log_emails = set(r['email'].lower() for r in (active_log_res.data or []) if r.get('email'))

    candidates = []
    seen = set()

    for uid, email in user_map.items():
        clean_email = email.strip().lower()
        if clean_email in seen:
            continue
        if 'fake' in clean_email or 'test' in clean_email or clean_email.endswith('.cim') or '@' not in clean_email:
            continue
        if clean_email.startswith('dnd.n.gz'):
            continue
        
        is_pro = uid in pro_ids
        has_pos = uid in pos_ids
        is_active_log = clean_email in active_log_emails

        if is_pro or has_pos or is_active_log:
            seen.add(clean_email)
            candidates.append({
                'user_id': uid,
                'email': clean_email,
                'is_pro': is_pro,
            })

    print(f"Targeting {len(candidates)} qualified Pro & Active users.")

    sent_success = 0
    sent_failed = 0

    for i, c in enumerate(candidates, 1):
        uid = c['user_id']
        email = c['email']
        is_pro = c['is_pro']

        if is_user_unsubscribed(uid, email):
            print(f"[{i}/{len(candidates)}] Skipping unsubscribed: {email}")
            continue

        subject = (
            "👑 [تقرير Pro الحصري] القيمة العادلة وكاشف مصائد السيولة لجلسة اليوم | EGX BOTS"
            if is_pro else
            "📊 [تقرير عاجل] كاشف مصائد البورصة المصرية وأرخص 5 أسهم تحت قيمتها العادلة"
        )
        html = build_email_html(uid, email, is_pro)
        send_meta = {}

        ok = send_resend_email(email, subject, html, out=send_meta)
        if ok:
            sent_success += 1
            resend_id = send_meta.get("id")
            record_marketing_message(
                user_id=uid,
                email=email,
                message_type="daily_fair_value_traps_nov02",
                metadata={"is_pro": is_pro, "resend_id": resend_id},
                provider_message_id=resend_id,
            )
            print(f"[{i}/{len(candidates)}] ✅ Sent to {email} (Resend ID: {resend_id})")
        else:
            sent_failed += 1
            print(f"[{i}/{len(candidates)}] ❌ Failed to send to {email}")
        
        time.sleep(0.4)

    print(f"\nDispatched {sent_success} emails successfully ({sent_failed} failed).")

    print("\n" + "="*50)
    print("Generating Live Post-Dispatch Analytics Breakdown...")
    print("="*50)
    time.sleep(2)
    analyze_campaign()

if __name__ == '__main__':
    main()
