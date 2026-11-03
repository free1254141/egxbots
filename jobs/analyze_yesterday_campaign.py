"""
jobs/analyze_yesterday_campaign.py — In-depth analytics for emails sent yesterday (2026-11-02).
"""
import os
import sys
import json
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding='utf-8')

# Read env
RESEND_API_KEY = None
with open('web/.env.local', 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('RESEND_API_KEY='):
            RESEND_API_KEY = line.strip().split('=', 1)[1].strip('"\'')
            break

if not RESEND_API_KEY:
    print('[ERROR] RESEND_API_KEY not found')
    sys.exit(1)

all_emails = []
after = None
while len(all_emails) < 1000:
    url = 'https://api.resend.com/emails?limit=100' + (f'&after={after}' if after else '')
    req = urllib.request.Request(
        url,
        headers={
            'Authorization': f'Bearer {RESEND_API_KEY}',
            'User-Agent': 'EGXBots-Marketing/1.0',
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            items = data.get('data', [])
            if not items:
                break
            all_emails.extend(items)
            if not data.get('has_more') or len(items) < 100:
                break
            after = items[-1]['id']
    except Exception as e:
        print(f'[ERROR] Resend fetch failed: {e}')
        break

CAIRO_TZ = timezone(timedelta(hours=2))

print(f'Total cumulative emails in Resend: {len(all_emails)}')

# Breakdown by day
by_day = {}
for e in all_emails:
    created_str = e.get('created_at', '')
    if created_str:
        dt = datetime.fromisoformat(created_str.replace('Z', '+00:00')).astimezone(CAIRO_TZ)
        d_str = dt.strftime('%Y-%m-%d')
        if d_str not in by_day:
            by_day[d_str] = []
        by_day[d_str].append((dt, e))

print('\nEmails sent per day (Cairo timezone):')
for d in sorted(by_day.keys(), reverse=True):
    print(f'  {d}: {len(by_day[d])} emails')

yesterday_list = by_day.get('2026-11-02', [])
today_list = by_day.get('2026-11-03', [])

print(f'\n======================================================')
print(f'📊 تفاصيل إيميلات أمس (2026-11-02) — إجمالي: {len(yesterday_list)}')
print(f'======================================================')

# Campaigns breakdown yesterday
campaigns = {}
for dt, e in yesterday_list:
    subj = e.get('subject', 'No Subject')
    if subj not in campaigns:
        campaigns[subj] = []
    campaigns[subj].append((dt, e))

print(f'الحملات التي تم إرسالها أمس ({len(campaigns)} حملات):')
for subj, items in campaigns.items():
    c_events = Counter(e.get('last_event') for _, e in items)
    c_opened = [e for _, e in items if e.get('last_event') in ['opened', 'clicked']]
    c_clicked = [e for _, e in items if e.get('last_event') == 'clicked']
    c_open_rate = len(c_opened) / len(items) * 100 if items else 0
    c_click_rate = len(c_clicked) / len(items) * 100 if items else 0
    print(f'\n📌 حملة: "{subj}"')
    print(f'   - إجمالي المرسل: {len(items)}')
    print(f'   - تم الفتح: {len(c_opened)} ({c_open_rate:.1f}%)')
    print(f'   - نقر الروابط: {len(c_clicked)} ({c_click_rate:.1f}%)')
    print(f'   - توزيع الحالات: {dict(c_events)}')

# Cumulative yesterday metrics
y_events = Counter(e.get('last_event') for _, e in yesterday_list)
y_opened = [(dt, e) for dt, e in yesterday_list if e.get('last_event') in ['opened', 'clicked']]
y_clicked = [(dt, e) for dt, e in yesterday_list if e.get('last_event') == 'clicked']
y_bounced = [(dt, e) for dt, e in yesterday_list if e.get('last_event') in ['bounced', 'complained']]
y_delivered = [(dt, e) for dt, e in yesterday_list if e.get('last_event') == 'delivered']

y_open_rate = (len(y_opened) / len(yesterday_list) * 100) if yesterday_list else 0
y_click_rate = (len(y_clicked) / len(yesterday_list) * 100) if yesterday_list else 0

print(f'\n======================================================')
print(f'🎯 ملخص إجمالي إيميلات أمس (2026-11-02):')
print(f'   • إجمالي الإيميلات المرسلة: {len(yesterday_list)}')
print(f'   • تم الفتح (Openers): {len(y_opened)} مستخدم ({y_open_rate:.1f}%)')
print(f'   • نقروا على الروابط (Clickers): {len(y_clicked)} مستخدم ({y_click_rate:.1f}%)')
print(f'   • تم التسليم وفي انتظار الفتح: {len(y_delivered)} مستخدم')
print(f'   • مرتد / ارتداد (Bounced): {len(y_bounced)} مستخدم')
print(f'======================================================')

print('\n👥 قائمة المستخدمين الذين فتحوا إيميلات أمس بالتفصيل:')
# Sort by time
for dt, e in sorted(y_opened, key=lambda x: x[0], reverse=True):
    to_addr = e.get('to', ['N/A'])[0]
    subj = e.get('subject', '')
    status = e.get('last_event')
    star = '⭐ [نقر على الرابط!]' if status == 'clicked' else '✓ [فتح الإيميل]'
    print(f'   {star} {to_addr} | الوقت: {dt.strftime("%I:%M %p")} | الحملة: {subj[:35]}...')

print(f'\n======================================================')
print(f'📊 تفاصيل إيميلات اليوم (2026-11-03) — إجمالي: {len(today_list)}')
print(f'======================================================')

campaigns_today = {}
for dt, e in today_list:
    subj = e.get('subject', 'No Subject')
    if subj not in campaigns_today:
        campaigns_today[subj] = []
    campaigns_today[subj].append((dt, e))

for subj, items in campaigns_today.items():
    c_events = Counter(e.get('last_event') for _, e in items)
    c_opened = [e for _, e in items if e.get('last_event') in ['opened', 'clicked']]
    c_clicked = [e for _, e in items if e.get('last_event') == 'clicked']
    c_open_rate = len(c_opened) / len(items) * 100 if items else 0
    c_click_rate = len(c_clicked) / len(items) * 100 if items else 0
    print(f'\n📌 حملة: "{subj}"')
    print(f'   - إجمالي المرسل: {len(items)}')
    print(f'   - تم الفتح: {len(c_opened)} ({c_open_rate:.1f}%)')
    print(f'   - نقر الروابط: {len(c_clicked)} ({c_click_rate:.1f}%)')
    print(f'   - توزيع الحالات: {dict(c_events)}')
    if c_opened:
        print('   - قائمة من فتحوا:')
        for o in c_opened:
            print(f'     * {o.get("to", [""])[0]} ({o.get("last_event")})')

