import os
import sys
import time
import requests
from dotenv import load_dotenv
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api.stock_ai as sai

load_dotenv('.env')
load_dotenv('web/.env.local', override=True)

api_key = os.getenv('RESEND_API_KEY', '').strip()
from_email = os.getenv('MARKETING_EMAIL_FROM', 'EGX BOTS <support@egxbots.com>').strip()

if not api_key:
    print("ERROR: RESEND_API_KEY is not configured.")
    sys.exit(1)

sai._init_supabase()
sb = sai.supabase

print("1. Fetching user logs and candidates...")

# 1. Paging logs to map history
all_logs = []
start = 0
step = 1000
while True:
    r = sb.table('marketing_message_log').select('email, message_type, channel, status, sent_at').range(start, start + step - 1).execute()
    data = r.data or []
    all_logs.extend(data)
    if len(data) < step:
        break
    start += step

email_history = {}
for r in all_logs:
    em = (r.get('email') or '').lower().strip()
    if '@' in em:
        email_history.setdefault(em, []).append(r)

# 2. Auth Users
all_auth = []
page = 1
while True:
    res = sb.auth.admin.list_users(page=page, per_page=100)
    if not res:
        break
    all_auth.extend(res)
    if len(res) < 100:
        break
    page += 1

# 3. Subscriptions, Trials, Approved Orders
sres = sb.table('subscriptions').select('user_id, plan_id, status').execute()
active_sub_users = set(s['user_id'] for s in sres.data or [] if s.get('status') in ['active', 'trialing'])

tres = sb.table('subscription_trials').select('user_id').execute()
trial_users = set(t['user_id'] for t in tres.data or [])

ores = sb.table('local_payment_orders').select('user_id').eq('status', 'approved').execute()
paid_users = set(o['user_id'] for o in ores.data or [])

cutoff_48h = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=48)).isoformat()

# 4. Filter candidates (never tried pro, no email in 48h)
candidates = []
for u in all_auth:
    uid = u.id
    email = (u.email or '').lower().strip()
    if not email or '@' not in email:
        continue
    if uid in active_sub_users or uid in trial_users or uid in paid_users:
        continue

    logs = email_history.get(email, [])
    # Guard: no email in last 48h
    if any(l.get('sent_at', '') >= cutoff_48h for l in logs):
        continue

    candidates.append({
        'user_id': uid,
        'email': email,
        'history_count': len(logs)
    })

# Prioritize users with 0 previous emails (fresh leads), then 1 previous email
candidates.sort(key=lambda x: x['history_count'])

# Target batch size: exactly 60
batch_size = 60
batch = candidates[:batch_size]

print(f"Total eligible candidates: {len(candidates)}")
print(f"Batch selected for dispatch: {len(batch)} users")
if not batch:
    print("No candidates available for dispatch.")
    sys.exit(0)

# Email Template
subject = "🎁 تم فتح رادار وتوصيات Pro لحسابك مجاناً لمدة 3 أيام (بدون بطاقة بنكية)"

html_template = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>هدية ترحيبية: 3 أيام Pro مجاناً</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #09090b; color: #ffffff; margin: 0; padding: 20px; text-align: right;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; margin: 0 auto; background-color: #121215; border: 2px solid #27272a; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
    <!-- Header -->
    <tr>
      <td style="padding: 28px 24px; text-align: center; background-color: #18181b; border-bottom: 2px solid #27272a;">
        <span style="display: inline-block; padding: 5px 14px; background-color: #10b981; color: #000000; font-weight: 900; font-size: 11px; border-radius: 9999px; text-transform: uppercase; letter-spacing: 0.05em;">هدية ترحيبية خاصة 🎁</span>
        <h1 style="color: #ffffff; font-size: 22px; font-weight: 900; margin: 14px 0 0 0; line-height: 1.4;">تم فتح رادار وتوصيات PRO لحسابك مجاناً 🚀</h1>
        <p style="color: #a1a1aa; font-size: 13px; margin: 6px 0 0 0; font-weight: 600;">3 أيام كاملة بدون أي بطاقة بنكية أو شروط</p>
      </td>
    </tr>

    <!-- Content -->
    <tr>
      <td style="padding: 26px 24px; line-height: 1.8; font-size: 14px; color: #d4d4d8;">
        <p style="margin-top: 0; font-size: 15px;">أهلاً بك صديقنا المستثمر،</p>
        <p>نود إبلاغك أن حسابك على منصة <strong>EGX BOTS</strong> أصبح مؤهلاً رسمياً لفتح <strong>باقة المحترفين (PRO) بالكامل لمدة 3 أيام مجاناً</strong> كهدية ترحيبية لتجربة القوة الحقيقية لتحليلات البورصة بالذكاء الاصطناعي.</p>
        
        <div style="background-color: #18181b; border-right: 4px solid #10b981; padding: 16px 20px; border-radius: 10px; margin: 22px 0;">
          <h3 style="color: #ffffff; margin: 0 0 8px 0; font-size: 15px; font-weight: 900;">ماذا ستحصل عليه فور التفعيل؟</h3>
          <ul style="padding-right: 20px; margin: 0; color: #e4e4e7; font-size: 13px;">
            <li style="margin-bottom: 8px;"><strong>⚡ صفقات وتوصيات فورية:</strong> دخول قناة VIP على تليجرام واستلام تنبيهات الشراء والأهداف والوقف لحظة بلحظة.</li>
            <li style="margin-bottom: 8px;"><strong>🎯 رادار الأسهم والسيولة الذكية:</strong> رصد اختراقات الأسهم وتجميع وايكوف ومصائد صانع السوق فور حدوثها.</li>
            <li style="margin-bottom: 8px;"><strong>🤖 شات بوت المستشار المالي ARTORO:</strong> 350 استشارة شهرياً لتحليل أي سهم، وقراءة محفظتك من صورة (Vision AI).</li>
          </ul>
        </div>

        <!-- Primary CTA Button -->
        <div style="text-align: center; margin: 32px 0 16px 0;">
          <a href="https://egxbots.com/profile?activate_trial=1" style="display: inline-block; background-color: #10b981; color: #000000; font-weight: 900; font-size: 15px; padding: 15px 32px; border-radius: 12px; text-decoration: none; box-shadow: 0 6px 20px rgba(16, 185, 129, 0.45); border: 2px solid #059669;">⚡ تفعيل باقة PRO التجريبية بضغطة زر واحدة</a>
        </div>
        <p style="text-align: center; font-size: 12px; color: #71717a; margin-top: 6px;">التفعيل فوري ولا يتطلب إدخال أي فيزا أو وسيلة دفع.</p>

        <!-- Telegram CTA Step -->
        <div style="background-color: #18181b; border: 1px solid #3f3f46; padding: 16px; border-radius: 10px; margin-top: 24px; text-align: center;">
          <p style="margin: 0 0 10px 0; font-size: 13px; font-weight: bold; color: #ffffff;">📲 الخطوة التالية: لتصلك إشارات جلسة اليوم على هاتفك</p>
          <a href="https://t.me/egxbots_bot" style="display: inline-block; background-color: #22c55e; color: #000000; font-weight: 800; font-size: 13px; padding: 10px 22px; border-radius: 8px; text-decoration: none;">ربط التليجرام واستلام إشارات الجلسة 💬</a>
        </div>
      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="padding: 18px 24px; text-align: center; background-color: #18181b; border-top: 1px solid #27272a; font-size: 11px; color: #71717a;">
        منصة EGX BOTS لتحليل أسهم البورصة المصرية والسعودية بالذكاء الاصطناعي · <a href="https://egxbots.com" style="color: #a1a1aa; text-decoration: underline;">egxbots.com</a>
        <br>
        <span style="display: inline-block; margin-top: 6px;">إذا كنت لا ترغب في استلام هذه الرسائل، يمكنك تجاهلها أو التواصل معنا عبر <a href="mailto:support@egxbots.com" style="color: #a1a1aa;">support@egxbots.com</a>.</span>
      </td>
    </tr>
  </table>
</body>
</html>
"""

sent_count = 0
failed_count = 0
sent_emails = []

print(f"\n2. Dispatching batch of {len(batch)} emails via Resend...")

for idx, c in enumerate(batch, 1):
    to_email = c['email']
    user_id = c['user_id']
    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_template,
    }
    try:
        res = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=15
        )
        if res.status_code in [200, 201]:
            resp_data = res.json()
            msg_id = resp_data.get('id')
            sent_count += 1
            sent_emails.append(to_email)
            # Log to marketing_message_log
            sb.table('marketing_message_log').insert({
                'user_id': user_id,
                'email': to_email,
                'message_type': 'winback_free_trial_3d',
                'channel': 'email',
                'status': 'sent',
                'provider_message_id': msg_id,
                'metadata': {'campaign': 'winback_free_trial_3d_batch1', 'history_count': c['history_count']}
            }).execute()
            print(f"[{idx}/{len(batch)}] OK: {to_email}")
        else:
            failed_count += 1
            print(f"[{idx}/{len(batch)}] FAILED {to_email}: {res.status_code} - {res.text}")
    except Exception as e:
        failed_count += 1
        print(f"[{idx}/{len(batch)}] EXCEPTION {to_email}: {e}")
    time.sleep(0.4)

print("\n" + "=" * 50)
print("BATCH DISPATCH COMPLETE")
print(f"Successfully Sent: {sent_count}")
print(f"Failed: {failed_count}")
print("=" * 50)
