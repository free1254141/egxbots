import os
import sys
import time
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api.stock_ai as sai
import datetime

load_dotenv('.env')
load_dotenv('web/.env.local', override=True)

api_key = os.getenv('RESEND_API_KEY', '').strip()
from_email = os.getenv('MARKETING_EMAIL_FROM', 'EGX BOTS <support@egxbots.com>').strip()

sai._init_supabase()
sb = sai.supabase

# Paging logs
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

# Auth Users
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

# Subscriptions
sres = sb.table('subscriptions').select('user_id, plan_id, status').execute()
active_sub_users = set(s['user_id'] for s in sres.data or [] if s.get('status') == 'active')

# Approved orders
ores = sb.table('local_payment_orders').select('user_id').eq('status', 'approved').execute()
paid_users = set(o['user_id'] for o in ores.data or [])

cutoff_7d = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)).isoformat()
cutoff_48h = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=48)).isoformat()

# Filter candidates: prioritize those with 0 emails, then 1 email, never spamming
candidates = []
for u in all_auth:
    uid = u.id
    email = (u.email or '').lower().strip()
    if not email or '@' not in email:
        continue
    if uid in active_sub_users or uid in paid_users:
        continue
    
    logs = email_history.get(email, [])
    # No email in last 48h
    if any(l.get('sent_at', '') >= cutoff_48h for l in logs):
        continue
    # Never received founders email in last 7 days
    if any(('founder' in (l.get('message_type') or '')) and l.get('sent_at', '') >= cutoff_7d for l in logs):
        continue

    candidates.append({
        'user_id': uid,
        'email': email,
        'history_count': len(logs)
    })

# Sort by history count ascending (0 emails first)
candidates.sort(key=lambda x: x['history_count'])

# Safe batch size of 50 recipients (to stay safely within 100/day free limit)
batch = candidates[:50]
print(f'Total candidates selected: {len(batch)} (all 0-1 previous emails, 0 in last 48h)')

subject = "⏳ باقي 24 ساعة فقط: آخر فرصة لتثبيت اشتراك EGX BOTS PRO بـ 100 ج.م مدى الحياة!"

html_template = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <title>فرصة أخيرة لتثبيت اشتراك 100 ج.م</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #09090b; color: #ffffff; margin: 0; padding: 20px; text-align: right;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; margin: 0 auto; background-color: #121215; border: 2px solid #27272a; border-radius: 16px; overflow: hidden;">
    <!-- Header -->
    <tr>
      <td style="padding: 24px; text-align: center; background-color: #18181b; border-bottom: 2px solid #27272a;">
        <span style="display: inline-block; padding: 4px 12px; background-color: #f59e0b; color: #000000; font-weight: 900; font-size: 11px; border-radius: 9999px; text-transform: uppercase;">تنبيه نهائي · انتهاء العرض</span>
        <h1 style="color: #ffffff; font-size: 22px; font-weight: 900; margin: 12px 0 0 0;">باقي 24 ساعة فقط على انتهاء عرض المؤسسين 👑</h1>
      </td>
    </tr>

    <!-- Content -->
    <tr>
      <td style="padding: 24px; line-height: 1.7; font-size: 14px; color: #d4d4d8;">
        <p style="margin-top: 0;">أهلاً بك صديقنا المستثمر،</p>
        <p>نود تذكيرك بأن <strong>عرض المؤسسين الاستثنائي</strong> لاشتراك منصة <strong>EGX BOTS PRO</strong> بـ <strong style="color: #10b981; font-size: 16px;">100 ج.م فقط شهرياً</strong> (بدلاً من 200 ج.م) سينتهي رسمياً خلال <strong>24 ساعة</strong>.</p>
        
        <div style="background-color: #18181b; border-right: 4px solid #10b981; padding: 14px 18px; border-radius: 8px; margin: 20px 0;">
          <h3 style="color: #ffffff; margin: 0 0 6px 0; font-size: 14px;">🔒 ميزة تثبيت السعر مدى الحياة (مهلة 72 ساعة):</h3>
          <p style="margin: 0; font-size: 13px; color: #a1a1aa;">
            باشتراكك الآن، يُثبّت سعر حسابك عند <strong>100 ج.م شهرياً مدى الحياة</strong> عند كل تجديد مستقبلي، مع مهلة سماح 72 ساعة للحفاظ على سعرك المخفض حتى بعد عودة السعر الأصلي.
          </p>
        </div>

        <h3 style="color: #ffffff; font-size: 15px; margin-bottom: 10px;">ماذا ستحصل عليه فور تفعيل باقة PRO؟</h3>
        <ul style="padding-right: 20px; margin: 0 0 20px 0; color: #e4e4e7;">
          <li style="margin-bottom: 8px;"><strong>الصفقات القصيرة ⚡ PRO:</strong> إشارات الزخم السريعة ومتابعة الأرباح ووقف الخسارة الصارم (4%).</li>
          <li style="margin-bottom: 8px;"><strong>رادار وتنبيهات الإسكانر الفورية:</strong> اختراقات السيولة الذكية، تجميع وايكوف، وصفقات المطلعين.</li>
          <li style="margin-bottom: 8px;"><strong>شات بوت المستشار الذكي 24/7:</strong> 350 استشارة شهرياً لتحليل أي سهم مصري وتحليل المحفظة من صورة (Vision AI).</li>
        </ul>

        <!-- CTA Button -->
        <div style="text-align: center; margin: 30px 0 10px 0;">
          <a href="https://egxbots.com/pricing?plan=pro" style="display: inline-block; background-color: #10b981; color: #000000; font-weight: 900; font-size: 15px; padding: 14px 28px; border-radius: 12px; text-decoration: none; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.4);">⚡ اشترك الآن بـ 100 ج.م وثبّت سعرك مدى الحياة</a>
        </div>
        <p style="text-align: center; font-size: 11px; color: #71717a; margin-top: 8px;">الدفع فوري ومتاح عبر فودافون كاش / إنستاباي / البطاقات البنكية.</p>
      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="padding: 16px 24px; text-align: center; background-color: #18181b; border-top: 1px solid #27272a; font-size: 11px; color: #71717a;">
        منصة EGX BOTS لتحليل أسهم البورصة المصرية بالذكاء الاصطناعي · <a href="https://egxbots.com" style="color: #a1a1aa; text-decoration: underline;">egxbots.com</a>
      </td>
    </tr>
  </table>
</body>
</html>
"""

sent_count = 0
failed_count = 0
sent_recipients = []

print("Starting dispatch via Resend...")
for c in batch:
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
            sent_recipients.append(to_email)
            # Log to marketing_message_log
            sb.table('marketing_message_log').insert({
                'user_id': user_id,
                'email': to_email,
                'message_type': 'founders_final_24h',
                'channel': 'email',
                'status': 'sent',
                'provider_message_id': msg_id,
                'metadata': {'campaign': 'founders_final_24h_filtered', 'previous_emails': c['history_count']}
            }).execute()
            print(f"[{sent_count}] Sent to {to_email}")
        else:
            failed_count += 1
            print(f"Failed for {to_email}: {res.status_code} - {res.text}")
    except Exception as e:
        failed_count += 1
        print(f"Exception for {to_email}: {e}")
    time.sleep(0.3)

print("\n--- DISPATCH SUMMARY ---")
print(f"Successfully Sent: {sent_count}")
print(f"Failed: {failed_count}")
