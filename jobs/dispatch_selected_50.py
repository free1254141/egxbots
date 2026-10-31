import sys, os, time, json
sys.path.insert(0, r'c:\Users\MR__CODER__\Desktop\stokscan_AI')
sys.stdout.reconfigure(encoding='utf-8')
from datetime import datetime, timezone
from api.stock_ai import supabase
from api.marketing_lifecycle import (
    send_resend_email,
    record_marketing_message,
    is_user_unsubscribed,
    _build_email_html,
    APP_URL,
)
from jobs.send_founders_emails import send_founders_offer_email

def send_abandoned_cart_reminder(user_id: str, email: str, display_name: str) -> bool:
    """Sends an urgent, high-intent reminder to users who clicked previously but didn't pay."""
    if is_user_unsubscribed(user_id, email):
        return False

    subject = "⏳ تذكير قبل افتتاح جلسة الأحد: ثبت باقة Pro بسعر المؤسسين (100 ج.م فقط)"
    greeting = f"أهلاً {display_name} 👋"
    paragraphs = [
        "لاحظنا اهتمامك الأخير بالانضمام إلى <strong>باقة EGX BOTS PRO</strong> وتصفحك لعرض المؤسسين.",
        "مع اقتراب انطلاق <strong>جلسة افتتاح الأسبوع غداً الأحد بالبورصة المصرية</strong>، نود تذكيرك بأن مقعدك في <strong>عرض المؤسسين المخفض (100 ج.م شهرياً مدى الحياة بدلاً من 200 ج.م)</strong> ما زال متاحاً ومحفوظاً لحسابك.",
        "🚀 <strong>ما ستحصل عليه فور تفعيل باقتك:</strong><br/>"
        "• <strong>قناة التنبيهات الفنية VIP على تليجرام:</strong> إشعارات لحظية لنماذج السوينج والسيولة الذكية ومستويات المراقبة الحية أثناء الجلسة.<br/>"
        "• <strong>مساعد الشات بوت الذكي ARTORO بدون حدود:</strong> فحص فني ومالي دقيق لأي سهم في محفظتك وتحليل فوري لفرص التجميع.<br/>"
        "• <strong>تثبيت السعر مدى الحياة:</strong> يظل اشتراكك دائماً بـ 100 ج.م شهرياً طول ما بتجدد بدون أي زيادة مستقبلية.",
    ]
    cta_text = "⚡ إتمام الاشتراك بسعر العرض (100 ج.م)"
    cta_url = f"{APP_URL}/pricing?plan=pro"

    html = _build_email_html(subject, greeting, paragraphs, cta_text, cta_url, user_id, email)
    send_meta = {}
    if send_resend_email(email, subject, html, out=send_meta):
        record_marketing_message(
            user_id,
            email,
            "abandoned_checkout",
            {"channel": "email", "campaign": "sunday_prep_reminder"},
            provider_message_id=send_meta.get("provider_message_id")
        )
        return True
    return False

def build_target_lists():
    # Load all eligible users from scratch/eligible_users.json
    json_path = r'C:\Users\MR__CODER__\.gemini\antigravity\brain\4f44c13e-1a12-41ea-bcf3-561da28b931e\scratch\eligible_users.json'
    with open(json_path, 'r', encoding='utf-8') as f:
        all_eligible = json.load(f)

    clean_fresh = []
    for u in all_eligible:
        em = u['email']
        if 'example.' in em or 'test' in em or 'fake' in em or em.endswith('.cim') or 'bgugvbhchj' in em:
            continue
        clean_fresh.append(u)

    # Category 1: October fresh users (active in October 2026)
    cat1 = [u for u in clean_fresh if u['last_active'] >= '2026-10-01']
    
    # Category 2: Next 25 fresh users sorted by activity
    cat2_candidates = [u for u in clean_fresh if u['last_active'] < '2026-10-01']
    cat2 = cat2_candidates[:25]

    # Category 3: The 16 hot clickers
    click_events = supabase.table('marketing_events').select('message_id,created_at').eq('event_type', 'clicked').execute().data
    mids = list({e['message_id'] for e in click_events if e.get('message_id')})
    
    cat3_emails = {}
    if mids:
        for i in range(0, len(mids), 50):
            chunk = mids[i:i+50]
            logs = supabase.table('marketing_message_log').select('id,email,user_id').in_('id', chunk).execute().data
            for l in logs:
                em = (l.get('email') or '').lower().strip()
                uid = l.get('user_id')
                if em and '@' in em and em not in cat3_emails:
                    cat3_emails[em] = uid

    # Exclude active paid subscribers from Cat 3
    active_subs = supabase.table('subscriptions').select('user_id').eq('status', 'active').execute().data
    active_uids = {s['user_id'] for s in active_subs}
    
    cat3 = []
    for em, uid in cat3_emails.items():
        if uid in active_uids or em in ['weeeessd57@gmail.com', 'acursour@gmail.com']:
            continue
        cat3.append({'user_id': uid, 'email': em, 'category': 'cat3_clickers'})

    return cat1, cat2, cat3

def run_dispatch():
    cat1, cat2, cat3 = build_target_lists()
    total = len(cat1) + len(cat2) + len(cat3)
    print(f"🚀 Starting dispatch for {total} selected recipients...")
    print(f"  • Category 1 (Fresh October): {len(cat1)} emails")
    print(f"  • Category 2 (Fresh Top 25): {len(cat2)} emails")
    print(f"  • Category 3 (Hot Clickers): {len(cat3)} emails\n")

    sent_count = 0
    failed_count = 0

    # 1. Dispatch Category 1
    print("--- Dispatching Category 1 (Fresh October) ---")
    for u in cat1:
        uid = u['user_id']
        email = u['email']
        prof = supabase.table("profiles").select("display_name, username").eq("id", uid).maybe_single().execute().data or {}
        dname = prof.get("display_name") or prof.get("username") or "المستثمر العزيز"
        ok = send_founders_offer_email(uid, email, dname)
        if ok:
            sent_count += 1
            print(f"  ✅ [Cat 1 SENT] {email} ({dname})", flush=True)
        else:
            failed_count += 1
            print(f"  ❌ [Cat 1 FAILED/SKIPPED] {email}", flush=True)
        time.sleep(0.6)

    # 2. Dispatch Category 2
    print("\n--- Dispatching Category 2 (Fresh Top 25) ---")
    for u in cat2:
        uid = u['user_id']
        email = u['email']
        prof = supabase.table("profiles").select("display_name, username").eq("id", uid).maybe_single().execute().data or {}
        dname = prof.get("display_name") or prof.get("username") or "المستثمر العزيز"
        ok = send_founders_offer_email(uid, email, dname)
        if ok:
            sent_count += 1
            print(f"  ✅ [Cat 2 SENT] {email} ({dname})", flush=True)
        else:
            failed_count += 1
            print(f"  ❌ [Cat 2 FAILED/SKIPPED] {email}", flush=True)
        time.sleep(0.6)

    # 3. Dispatch Category 3
    print("\n--- Dispatching Category 3 (Hot Clickers - Sunday Reminder) ---")
    for u in cat3:
        uid = u['user_id']
        email = u['email']
        prof = supabase.table("profiles").select("display_name, username").eq("id", uid).maybe_single().execute().data or {}
        dname = prof.get("display_name") or prof.get("username") or "المستثمر العزيز"
        ok = send_abandoned_cart_reminder(uid, email, dname)
        if ok:
            sent_count += 1
            print(f"  ✅ [Cat 3 SENT] {email} ({dname})", flush=True)
        else:
            failed_count += 1
            print(f"  ❌ [Cat 3 FAILED/SKIPPED] {email}", flush=True)
        time.sleep(0.6)

    print(f"\n🎉 Dispatch Completed! Sent: {sent_count} | Failed/Skipped: {failed_count}")

if __name__ == '__main__':
    run_dispatch()
