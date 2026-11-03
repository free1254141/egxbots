"""
inspect_mohamedkani10.py
"""
import os
import sys
import json
from supabase import create_client
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv('web/.env.local')
supabase = create_client(os.getenv('NEXT_PUBLIC_SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))

users_res = supabase.auth.admin.list_users(page=1, per_page=1000)
user = next((u for u in users_res if u.email == 'mohamedkani10@gmail.com'), None)

if not user:
    print('User not found')
    sys.exit()

uid = user.id
print('==============================================')
print('User ID:', uid)
print('Email:', user.email)
print('Auth Created At:', user.created_at)
print('Last Sign In At:', user.last_sign_in_at)
print('User Metadata:', user.user_metadata)
print('App Metadata:', user.app_metadata)

# Check subscriptions
subs = supabase.table('subscriptions').select('*').eq('user_id', uid).execute().data
print('\n--- Subscriptions ---')
print(json.dumps(subs, indent=2, ensure_ascii=False))

# Check payment entitlement events or payments
try:
    events = supabase.table('payment_entitlement_events').select('*').eq('user_id', uid).execute().data
    print('\n--- Payment Entitlement Events ---')
    print(json.dumps(events, indent=2, ensure_ascii=False))
except Exception as e:
    print('Error entitlement events:', e)

try:
    kashier = supabase.table('kashier_payments').select('*').eq('user_id', uid).execute().data
    print('\n--- Kashier Payments ---')
    print(json.dumps(kashier, indent=2, ensure_ascii=False))
except Exception as e:
    print('Error kashier:', e)

# Check profile
prof = supabase.table('profiles').select('*').eq('id', uid).execute().data
print('\n--- Profile ---')
print(json.dumps(prof, indent=2, ensure_ascii=False))

# Check all chat messages ordered by created_at desc
chats = supabase.table('ai_chat_messages').select('*').eq('user_id', uid).order('created_at', desc=True).limit(20).execute().data
print(f'\n--- Latest Chat Messages ({len(chats)}) ---')
for c in chats:
    t = c.get('created_at', '')[:19]
    r = c.get('role', '')
    txt = c.get('content', '').replace('\n', ' ').strip()
    print(f'  [{t}] ({r}): {txt[:120]}...')

# Check marketing logs
try:
    m_logs = supabase.table('marketing_message_log').select('*').eq('user_id', uid).order('created_at', desc=True).limit(10).execute().data
    print('\n--- Marketing message logs ---')
    print(json.dumps(m_logs, indent=2, ensure_ascii=False))
except Exception as e:
    print('Error marketing logs:', e)

# Check if there are any other logs or references
print('==============================================')
