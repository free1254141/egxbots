"""
inspect_first_subscriber.py
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
email_to_user = {u.email: u for u in users_res}

candidates = [
    'weeessd57@gmail.com',
    'weeeenew@gmail.com',
    'mohamedkani10@gmail.com',
    'mahmoudelmorshedy94@gmail.com',
    'amrosami94@gmail.com',
    'amraly2010@gmail.com'
]

for em in candidates:
    u = email_to_user.get(em)
    if not u:
        continue
    uid = u.id
    prof = supabase.table('profiles').select('*').eq('id', uid).execute().data
    p = prof[0] if prof else {}
    subs = supabase.table('subscriptions').select('*').eq('user_id', uid).execute().data
    positions = supabase.table('positions').select('*').eq('user_id', uid).execute().data or []
    chats = supabase.table('ai_chat_messages').select('id, role, content, created_at').eq('user_id', uid).order('created_at', desc=False).execute().data or []
    
    print('========================================================')
    print(f'Email: {em}')
    print(f'User ID: {uid}')
    print(f'Auth Created At: {u.created_at}')
    print(f'Display Name: {p.get("display_name")}')
    print(f'Telegram Chat ID: {p.get("telegram_chat_id")}')
    print(f'WhatsApp: {p.get("whatsapp_number")}')
    print(f'Cash Balance: {p.get("cash_balance")}')
    print(f'Subscriptions: {json.dumps(subs, indent=2, ensure_ascii=False)}')
    print(f'Positions Count: {len(positions)}')
    if positions:
        print('Sample positions:', positions[:5])
    print(f'Chat Messages Count: {len(chats)}')
    if chats:
        print('First 3 chats:')
        for c in chats[:3]:
            print(f'  [{c["created_at"]}] ({c["role"]}): {c["content"][:100]}...')
        print('Last chat:')
        print(f'  [{chats[-1]["created_at"]}] ({chats[-1]["role"]}): {chats[-1]["content"][:100]}...')
