import os
import sys
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import requests
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv('C:/Users/MR__CODER__/Desktop/stokscan_AI/.env')
url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
key = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

headers = {
    'apikey': key,
    'Authorization': f'Bearer {key}',
    'Content-Type': 'application/json'
}

# 1. Fetch Users
users_res = requests.get(f'{url}/auth/v1/admin/users?per_page=1000', headers=headers)
users = users_res.json().get('users', []) if users_res.status_code == 200 else []
user_map = {u['id']: u.get('email', u['id']) for u in users}

# 2. Fetch Subscriptions
subs_res = requests.get(f'{url}/rest/v1/subscriptions?select=*', headers=headers)
subs = subs_res.json() if subs_res.status_code == 200 else []
pro_users = {s['user_id']: s for s in subs if s.get('status') == 'active'}

# 3. Fetch ai_chatbot_limits for 17 and 18 Oct
limits_res = requests.get(f'{url}/rest/v1/ai_chatbot_limits?date=in.(2026-10-17,2026-10-18)&select=*', headers=headers)
limits = limits_res.json() if limits_res.status_code == 200 else []

# 4. Fetch all messages for 17 and 18 Oct
# Note: Egypt is UTC+2 or UTC+3. In UTC: 2026-10-16T21:00:00Z to 2026-10-18T23:59:59Z
msgs_res = requests.get(f'{url}/rest/v1/ai_chat_messages?created_at=gte.2026-10-16T21:00:00Z&order=created_at.asc&select=*', headers=headers)
msgs = msgs_res.json() if msgs_res.status_code == 200 else []

print(f"Total messages fetched in time range: {len(msgs)}")

def categorize_date(ts_str):
    # convert UTC timestamp to Egypt Time (UTC+3)
    dt_utc = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    dt_egypt = dt_utc + timedelta(hours=3)
    return dt_egypt.strftime('%Y-%m-%d'), dt_egypt.strftime('%H:%M:%S')

days_data = {
    '2026-10-17': {'users': defaultdict(list), 'user_msgs': 0, 'bot_msgs': 0},
    '2026-10-18': {'users': defaultdict(list), 'user_msgs': 0, 'bot_msgs': 0}
}

for m in msgs:
    d, t = categorize_date(m.get('created_at'))
    if d in days_data:
        uid = m.get('user_id') or 'Anonymous/Guest'
        role = m.get('role')
        content = m.get('content', '')
        if role == 'user':
            days_data[d]['user_msgs'] += 1
            days_data[d]['users'][uid].append({'time': t, 'text': content})
        elif role == 'assistant':
            days_data[d]['bot_msgs'] += 1

for target_date, date_label in [('2026-10-17', 'أمس (السبت 17 أكتوبر 2026)'), ('2026-10-18', 'اليوم (الأحد 18 أكتوبر 2026)')]:
    print("\n" + "="*70)
    print(f"📅 {date_label}")
    print("="*70)
    d_info = days_data[target_date]
    user_dict = d_info['users']
    print(f"🔹 إجمالي رسائل المستخدمين: {d_info['user_msgs']} سؤال")
    print(f"🔹 إجمالي ردود الشات بوت: {d_info['bot_msgs']} إجابة")
    print(f"🔹 عدد المستخدمين الفريدين: {len(user_dict)} مستخدم")
    
    # Check limit rows for this date
    date_limits = {r['user_id']: r['chat_count'] for r in limits if r['date'] == target_date}
    
    print("\n👥 تفاصيل المستخدمين واستهلاكهم:")
    for uid, history in user_dict.items():
        email = user_map.get(uid, uid)
        plan = "PRO 💎" if uid in pro_users else ("FREE 🆓" if '@' in email else "GUEST 👤")
        recorded_limit = date_limits.get(uid, len(history))
        print(f"\n👤 [{plan}] {email}")
        print(f"   الاستهلاك المسجل: {recorded_limit} رسالة (عدد الأسئلة الفعلية: {len(history)})")
        print("   الأسئلة التي طرحها:")
        for idx, q in enumerate(history, 1):
            txt = q['text'].replace('\n', ' ')
            if len(txt) > 80:
                txt = txt[:80] + '...'
            print(f"     {idx}. [{q['time']}] {txt}")

