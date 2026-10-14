import sys, os
sys.path.append(os.getcwd())
sys.stdout.reconfigure(encoding='utf-8')
import requests, json
from dotenv import dotenv_values
from datetime import datetime, timezone, timedelta

v = dotenv_values('.env')
url = v['SUPABASE_URL']
key = v['SUPABASE_SERVICE_ROLE_KEY']
headers = {'apikey': key, 'Authorization': f'Bearer {key}'}

target_uids = ['c634fe18-9e6f-4f35-b2aa-1fa7a22ad78d', '65f8472d-b19e-46d2-966e-5590c2668080']
egypt_tz = timezone(timedelta(hours=3))

for uid in target_uids:
    print(f"==================================================")
    print(f"ANALYZING USER: {uid}")
    print(f"==================================================")
    
    # 1. Auth User
    r_u = requests.get(f"{url}/auth/v1/admin/users/{uid}", headers=headers)
    u_data = r_u.json() if r_u.status_code == 200 else {}
    print(f"Email: {u_data.get('email')}")
    created_raw = u_data.get('created_at')
    if created_raw:
        c_eg = datetime.fromisoformat(created_raw.replace('Z', '+00:00')).astimezone(egypt_tz)
        print(f"Created (Egypt Time): {c_eg.strftime('%Y-%m-%d %I:%M:%S %p')}")
    last_in_raw = u_data.get('last_sign_in_at')
    if last_in_raw:
        li_eg = datetime.fromisoformat(last_in_raw.replace('Z', '+00:00')).astimezone(egypt_tz)
        print(f"Last Sign In (Egypt Time): {li_eg.strftime('%Y-%m-%d %I:%M:%S %p')}")
    print(f"Metadata: {json.dumps(u_data.get('user_metadata'), ensure_ascii=False)}")
    
    # 2. Profile
    r_prof = requests.get(f"{url}/rest/v1/profiles?id=eq.{uid}", headers=headers)
    prof = r_prof.json()
    print(f"Profile: {json.dumps(prof, indent=2, ensure_ascii=False)}")
    
    # 3. Orders & Subscriptions
    r_ord = requests.get(f"{url}/rest/v1/local_payment_orders?user_id=eq.{uid}&order=created_at.desc", headers=headers)
    orders = r_ord.json()
    print(f"\nOrders ({len(orders)}):")
    for o in orders:
        print(f"  ID: {o.get('id')} | Plan: {o.get('plan_id')} | Amount: {o.get('amount_egp')} EGP | Status: {o.get('status')} | Customer Note: {o.get('customer_note')}")
        if o.get('telegram_invite_link'):
            print(f"  Telegram Link: {o.get('telegram_invite_link')}")
            
    r_sub = requests.get(f"{url}/rest/v1/subscriptions?user_id=eq.{uid}&order=created_at.desc", headers=headers)
    subs = r_sub.json()
    print(f"\nSubscriptions ({len(subs)}):")
    for s in subs:
        print(f"  Plan: {s.get('plan_id')} | Status: {s.get('status')} | Start: {s.get('current_period_start')} | End: {s.get('current_period_end')} | Provider: {s.get('provider')}")

    # Check pro telegram invite record
    r_ti = requests.get(f"{url}/rest/v1/pro_telegram_invites?user_id=eq.{uid}", headers=headers)
    tis = r_ti.json()
    print(f"\nPro Telegram Invites:")
    for ti in tis:
        print(f"  VIP User ID: {ti.get('vip_telegram_user_id')} | Link: {ti.get('invite_link')} | Updated: {ti.get('updated_at')}")

    # 4. Portfolio
    r_pos = requests.get(f"{url}/rest/v1/positions?user_id=eq.{uid}", headers=headers)
    positions = r_pos.json()
    print(f"\nPortfolio Positions ({len(positions)}):")
    for p in positions:
        print(f"  {p.get('symbol')} ({p.get('name')}) | Entry: {p.get('entry_price')} | Target: {p.get('target_price')} | Stop: {p.get('stop_price')}")

    # 5. Activity Events (Traffic)
    r_act = requests.get(f"{url}/rest/v1/user_activity_events?user_id=eq.{uid}&order=created_at.asc", headers=headers)
    acts = r_act.json()
    print(f"\nActivity Events ({len(acts)}):")
    for a in acts:
        c_at = a.get('created_at')
        if c_at:
            t_eg = datetime.fromisoformat(c_at.replace('Z', '+00:00')).astimezone(egypt_tz).strftime('%I:%M:%S %p')
        else:
            t_eg = '??'
        meta = json.dumps(a.get('metadata'), ensure_ascii=False) if a.get('metadata') else ''
        print(f"  {t_eg} | {a.get('event_name')} | {a.get('path')} | {meta}")

    # 6. Chat Messages
    r_sess = requests.get(f"{url}/rest/v1/ai_chat_sessions?user_id=eq.{uid}&order=created_at.asc", headers=headers)
    sessions = r_sess.json()
    print(f"\nChat Sessions ({len(sessions)}):")
    for s in sessions:
        sid = s.get('id')
        r_msg = requests.get(f"{url}/rest/v1/ai_chat_messages?session_id=eq.{sid}&order=created_at.asc", headers=headers)
        msgs = r_msg.json()
        print(f"-- Session {sid} ({len(msgs)} msgs) --")
        for m in msgs:
            role = m.get('role')
            clean_c = (m.get('content') or '').replace('\n', ' ')[:200]
            print(f"  [{role}]: {clean_c}")
    print("\n")
