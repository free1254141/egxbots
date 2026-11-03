"""
jobs/inspect_first_users_activity.py
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

users_to_check = [
    ('mohamedkani10@gmail.com', 'أول مشترك حقيقي (فودافون كاش - 23 سبتمبر)'),
    ('mahmoudelmorshedy94@gmail.com', 'أول مشترك دفع عبر بوابة الدفع الإلكترونية EasyKash (26 سبتمبر)'),
    ('amrosami94@gmail.com', 'ثاني مشترك EasyKash (26 سبتمبر) — مستثمر نشط بمحفظة فعلية'),
    ('amraly2010@gmail.com', 'أول مشترك Pro لا يزال مستمراً ونشطاً حتى اليوم (27 سبتمبر وحتى 6 نوفمبر)')
]

for em, title in users_to_check:
    u = email_to_user.get(em)
    if not u:
        continue
    uid = u.id
    prof = supabase.table('profiles').select('*').eq('id', uid).execute().data
    p = prof[0] if prof else {}
    subs = supabase.table('subscriptions').select('*').eq('user_id', uid).execute().data
    positions = supabase.table('positions').select('*').eq('user_id', uid).execute().data or []
    chats = supabase.table('ai_chat_messages').select('*').eq('user_id', uid).order('created_at', desc=False).execute().data or []
    
    print('========================================================')
    print(f'📌 {title}')
    print(f'  • البريد الإلكتروني: {em}')
    print(f'  • تاريخ التسجيل الأولي: {u.created_at}')
    print(f'  • آخر تسجيل دخول: {u.last_sign_in_at}')
    print(f'  • تليجرام: {p.get("telegram_chat_id")}')
    print(f'  • تفاصيل الاشتراك: {subs}')
    print(f'  • المحفظة والأسهم المسجلة: {len(positions)} أسهم')
    for pos in positions:
        print(f'      - سهم: {pos.get("symbol")} | الكمية: {pos.get("quantity")} | سعر الشراء: {pos.get("entry_price")} | الحالة: {pos.get("status")}')
    print(f'  • نشاط الشات بوت: {len(chats)} رسالة')
    user_queries = [c for c in chats if c.get('role') == 'user']
    print(f'      - إجمالي الأسئلة الموجهة للمساعد الذكي: {len(user_queries)}')
    for q in user_queries[:8]:
        t = q.get('created_at', '')[:19]
        txt = q.get('content', '').replace('\n', ' ').strip()
        print(f'      * [{t}] {txt}')
