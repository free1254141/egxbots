#!/usr/bin/env python3
"""
jobs/execute_paywall_recovery_campaign.py
Executes targeted paywall recovery campaign for users who exhausted their 10 free messages
and users on the verge of exhaustion (9/10 messages).
Includes Telegram DMs + Resend Emails + Mandatory Live Post-Dispatch Analytics Breakdown.
"""
import os
import sys
import time
import requests
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

BOT_TOKEN = os.environ.get('ARTORO_AI_BOT', '').strip()

# --- Telegram Sender ---
def send_telegram(chat_id: str, text: str, reply_markup=None):
    if not BOT_TOKEN or not chat_id:
        return {"ok": False, "error": "No token or chat_id"}
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = requests.post(api_url, json=payload, timeout=15)
        return res.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

# --- HTML Email Builder ---
def build_recovery_email(user_id: str, email: str, tier: str) -> tuple[str, str]:
    unsub_token = generate_unsub_token(user_id, email)
    unsub_url = f"{APP_URL}/unsubscribe?uid={user_id}&token={unsub_token}&email={email}"

    if tier == "HOT_LEAD":
        subject = "🔓 نأسف لتوقف استشارتك! هدية فك حظر كوتا الشات بـ 100 ج.م شهرياً مدى الحياة"
        headline = "عارفين إنك كنت بتحلل ومحتاج تكمل استشارتك بدون توقف..."
        lead_p = "أثناء تحليلك للأسهم في البورصة المصرية بالأمس، واجهت رسالة اكتمال كوتا الشات المجانية (10 رسائل). لأن قرارات التداول لا تحتمل التأجيل، نقدم لك اليوم <strong>عرض فك الحظر الحصري</strong> لتستمر في تحليل صفقاتك واقتناص الفرص فوراً."
        badge = "🔥 عرض فك الحظر الحصري (24 ساعة فقط)"
    elif tier == "EDGE_WALKER":
        subject = "⚠️ تنبيه استباقي: باقي لك رسالة واحدة فقط على توقف مساعدك الذكي!"
        headline = "تنبيه هام قبل بدء جلسة التداول..."
        lead_p = "رصيدك الحالي هو <strong>(9 من 10 رسائل مجانية)</strong>، مما يعني أن استشارتك القادمة هي آخر رسالة مجانية قبل قفل الشات بالكامل. حتى لا يتوقف تحليلك فجأة في وسط تحركات السوق، وفّرنا لك إمكانية الترقية الآن مع تثبيت السعر."
        badge = "⚠️ تنبيه استباقي قبل نفاد الكوتا"
    else:  # DORMANT_HEAVY
        subject = "🚀 حدثنا المنصة بالكامل! 4 محركات ذكية جديدة تنتظرك في EGX BOTS"
        headline = "افتقدنا وجودك معنا.. وأضفنا أضخم ترقية في تاريخ المنصة!"
        lead_p = "نعلم أنك كنت من أكثر المتداولين تفاعلاً مع ذكاء EGX BOTS سابقاً. يسعدنا إخبارك أننا أطلقنا 4 أدوات كمية ومؤسسية جديدة ستنقل تداولاتك لمستوى آخر: <strong>كاشف المصائد والانعكاسات الحية، محدد القيمة العادلة لجميع أسهم السوق، حاسبة التوافق الشرعي والزكاة، وتشخيص وإعادة تدوير المحفظة بالذكاء الاصطناعي</strong>."
        badge = "💎 دعوة عودة خاصة لكبار المستخدمين"

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #07090e; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; color: #f3f4f6; text-align: right;">
  <div style="max-width: 620px; margin: 0 auto; padding: 24px 16px;">
    
    <!-- Header -->
    <div style="text-align: center; padding-bottom: 24px; border-bottom: 2px solid #1f2937;">
      <a href="{APP_URL}" style="text-decoration: none; color: #ffffff; font-size: 24px; font-weight: 900; letter-spacing: -0.5px;">
        EGX <span style="color: #10b981;">BOTS</span> | ARTORO AI
      </a>
      <div style="margin-top: 8px;">
        <span style="display: inline-block; background: rgba(245, 158, 11, 0.15); border: 1px solid rgba(245, 158, 11, 0.4); color: #f59e0b; font-size: 12px; font-weight: bold; padding: 4px 12px; border-radius: 9999px;">
          {badge}
        </span>
      </div>
    </div>

    <!-- Main Title -->
    <div style="padding: 24px 0 16px 0;">
      <h1 style="margin: 0 0 10px 0; font-size: 20px; color: #ffffff; line-height: 1.4;">
        {headline}
      </h1>
      <p style="margin: 0; font-size: 14px; color: #d1d5db; line-height: 1.7;">
        {lead_p}
      </p>
    </div>

    <!-- The Offer Box -->
    <div style="background: #0d1117; border: 2px solid #10b981; border-radius: 16px; padding: 22px; margin-bottom: 24px; box-shadow: 0 4px 20px rgba(16, 185, 129, 0.15);">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1f2937; padding-bottom: 12px; margin-bottom: 16px;">
        <span style="color: #10b981; font-weight: 900; font-size: 18px;">⭐ عرض باقة المؤسسين (EGX BOTS PRO):</span>
        <span style="background: #10b981; color: #000; font-weight: 900; font-size: 13px; padding: 3px 10px; border-radius: 6px;">100 ج.م / شهرياً</span>
      </div>
      
      <p style="margin: 0 0 14px 0; font-size: 13px; color: #9ca3af;">
        بدلاً من <strike>200 ج.م</strike>، ويثبت هذا السعر لحسابك <strong>مدى الحياة</strong> دون أي زيادة مستقبلية ما دمت مجدداً لاشتراكك!
      </p>

      <ul style="margin: 0 0 18px 0; padding-right: 20px; color: #f3f4f6; font-size: 13px; line-height: 1.8;">
        <li><strong>350 استشارة ورسالة شهرياً:</strong> اسأل عن أي سهم، فحص الدعوم والمقاومات والوقف والأهداف لحظياً.</li>
        <li><strong>كاشف المصائد السعرية الحية (Wyckoff Traps):</strong> رصد يومي لمصائد القيعان (Spring) والقمم (Upthrust).</li>
        <li><strong>أداة إعادة تدوير المحفظة بالذكاء الاصطناعي:</strong> تشخيص الأسهم الراكدة وتدوير السيولة الميتة.</li>
        <li><strong>حاسبة القيمة العادلة ومؤشر الرخص:</strong> معرفة السعر الاستثماري الحقيقي لجميع أسهم EGX30.</li>
        <li><strong>قناة إشعارات VIP الفورية على تليجرام:</strong> تنبيهات حية فور اكتمال النماذج الفنية.</li>
      </ul>

      <div style="background: rgba(31, 41, 55, 0.6); border-radius: 8px; padding: 10px 14px; font-size: 12px; color: #9ca3af; text-align: center;">
        💳 الدفع فوري وآمن بجميع الطرق: <strong>فودافون كاش / انستاباي / فوري / بطاقات ميزة والفيزا البنكية</strong>.
      </div>
    </div>

    <!-- CTA Button -->
    <div style="text-align: center; margin: 28px 0;">
      <a href="{APP_URL}/pricing?plan=pro" style="display: block; background: #10b981; color: #000000; font-weight: 900; font-size: 16px; padding: 16px 24px; border-radius: 12px; text-decoration: none; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);">
        🚀 اشترك الآن بـ 100 ج.م وثبّت السعر مدى الحياة ↗
      </a>
      <div style="margin-top: 10px; font-size: 12px; color: #9ca3af;">
        🔒 تفعيل فوري لحظي لحسابك بمجرد إتمام الدفع
      </div>
    </div>

    <!-- Footer -->
    <div style="border-top: 1px solid #1f2937; padding-top: 20px; font-size: 11px; color: #6b7280; text-align: center; line-height: 1.6;">
      <p style="margin: 0 0 8px 0;">
        ⚠️ إخلاء مسؤولية: منصة EGX BOTS أداة برمجية للتحليل الفني والكمي وقراءة حركة السوق ولا تقدم توصيات استثمارية أو إدارة محافظ. قرارات التداول مسؤوليتك المستقلة.
      </p>
      <p style="margin: 0;">
        تصلك هذه الرسالة لحسابك المسجل في EGX BOTS. 
        <a href="{unsub_url}" style="color: #9ca3af; text-decoration: underline;">إلغاء الاشتراك بنقرة واحدة</a>
      </p>
    </div>

  </div>
</body>
</html>"""
    return subject, html

def main():
    print("="*60)
    print("🚀 EXECUTING TARGETED PAYWALL RECOVERY CAMPAIGN")
    print("="*60)

    # 1. Fetch all users from Supabase Auth
    users_resp = client.auth.admin.list_users(page=1, per_page=1000)
    all_users = users_resp if isinstance(users_resp, list) else getattr(users_resp, 'users', [])
    user_map = {u.id: getattr(u, 'email', '').strip().lower() for u in all_users if getattr(u, 'email', None)}

    # 2. Active Pro subscriptions (exclude existing Pro)
    subs_res = client.table('subscriptions').select('user_id, status').in_('status', ['active', 'trialing']).execute()
    pro_ids = set(s['user_id'] for s in (subs_res.data or []))

    # 3. Profiles mapping (telegram_chat_id, display_name)
    profiles_res = client.table('profiles').select('id, telegram_chat_id, display_name').execute()
    profile_map = {p['id']: p for p in (profiles_res.data or [])}

    # 4. Check limits table
    limits_res = client.table('ai_chatbot_limits').select('user_id, date, chat_count').execute()
    user_counts = {}
    user_last_date = {}

    for r in (limits_res.data or []):
        uid = r['user_id']
        cnt = int(r.get('chat_count') or 0)
        d = str(r.get('date') or '')
        user_counts[uid] = user_counts.get(uid, 0) + cnt
        if d > user_last_date.get(uid, ''):
            user_last_date[uid] = d

    # 5. Classify Users into Tiers
    hot_leads = []
    edge_walkers = []
    dormant_heavy = []

    # Explicit Hot Leads based on recent logs (last 48h to Oct 31)
    hot_emails = {
        'amrdiesel11@gmail.com',
        'bmohamedrefaat@gmail.com',
        'aw2006a4@gmail.com',
        'janaconda323@gmail.com',
        'ahmedfahmy049@duck.com',
        'memoo1286@gmail.com',
    }

    edge_emails = {
        'dr.shehab1@gmail.com',
        'moham.rashwan@gmail.com',
        'selim_morad@yahoo.com',
        'generalzizo0@gmail.com',
        'egyman017@gmail.com',
        'petertharwat15@yahoo.com',
    }

    processed_uids = set()

    for uid, total in user_counts.items():
        if uid in pro_ids:
            continue
        email = user_map.get(uid, '')
        if not email or '@' not in email:
            continue
        if 'fake' in email or 'test' in email or email.endswith('.cim') or email.startswith('dnd.n.gz'):
            continue

        last_d = user_last_date.get(uid, '')
        tg = profile_map.get(uid, {}).get('telegram_chat_id')
        name = profile_map.get(uid, {}).get('display_name') or 'صديقنا'

        record = {
            'uid': uid,
            'email': email,
            'total_msgs': total,
            'last_date': last_d,
            'telegram_chat_id': tg,
            'name': name,
        }

        if email in hot_emails or (total >= 10 and last_d >= '2026-10-31'):
            hot_leads.append(record)
            processed_uids.add(uid)
        elif email in edge_emails or total == 9:
            edge_walkers.append(record)
            processed_uids.add(uid)
        elif total >= 10 and uid not in processed_uids:
            dormant_heavy.append(record)
            processed_uids.add(uid)

    print(f"\nTarget Cohorts Identified:")
    print(f"  🔥 Hot Leads (Last 48h/Oct 31): {len(hot_leads)} users")
    print(f"  ⚠️ Edge Walkers (9/10 msgs): {len(edge_walkers)} users")
    print(f"  💎 Dormant Heavy Users (10-67 msgs): {len(dormant_heavy)} users")
    print(f"  Total Users to be Recovered: {len(hot_leads) + len(edge_walkers) + len(dormant_heavy)} users\n")

    telegram_sent = 0
    telegram_failed = 0
    email_sent = 0
    email_failed = 0

    all_targets = [
        ("HOT_LEAD", hot_leads),
        ("EDGE_WALKER", edge_walkers),
        ("DORMANT_HEAVY", dormant_heavy),
    ]

    # --- DISPATCH LOOP ---
    for tier_name, user_list in all_targets:
        print(f"\n--- Processing Cohort: {tier_name} ({len(user_list)} users) ---")
        for u in user_list:
            uid = u['uid']
            email = u['email']
            tg_id = u['telegram_chat_id']
            msgs = u['total_msgs']

            # A. Telegram DM Dispatch (if connected)
            if tg_id:
                if tier_name == "HOT_LEAD":
                    tg_text = (
                        "أهلاً بك يا صديقي 👋\n\n"
                        "لاحظنا أنك كنت تحلل أسهمك أمس وتوقفت بسبب اكتمال كوتا الـ 10 رسائل المجانية 🔒.. ونعلم تماماً أن السوق لا ينتظر أحداً.\n\n"
                        "🎁 <b>عرض فك الحظر الحصري لحسابك (صالح لـ 24 ساعة):</b>\n"
                        "يمكنك ترقية حسابك إلى <b>باقة PRO بـ 100 ج.م فقط شهرياً مدى الحياة</b> (بدلاً من 200 ج.م).\n\n"
                        "🚀 <b>مزاياك فور الترقية:</b>\n"
                        "• 350 رسالة شهرياً للاستشارة دون توقف.\n"
                        "• كاشف المصائد السعرية الحية (Springs & Upthrusts).\n"
                        "• أداة إعادة تدوير المحفظة بالذكاء الاصطناعي.\n"
                        "• تثبيت السعر بـ 100 ج.م مدى الحياة.\n\n"
                        "👇 اضغط للترقية وفك الحظر فوراً (متاح فودافون كاش / انستاباي / فيزا):"
                    )
                elif tier_name == "EDGE_WALKER":
                    tg_text = (
                        "⚠️ <b>تنبيه استباقي هام من EGX BOTS:</b>\n\n"
                        "رصيدك الحالي هو (9 من 10 رسائل مجانية)، مما يعني أن استشارتك القادمة هي آخر رسالة مجانية قبل قفل الشات بالكامل.\n\n"
                        "حتى لا يتوقف تحليلك فجأة في وسط جلسة التداول: احصل الآن على باقة PRO بـ 100 ج.م شهرياً مدى الحياة وارفع رصيدك فوراً إلى 350 رسالة شهرياً مع كافة أدوات كشف المصائد وإعادة تدوير المحفظة!\n\n"
                        "👇 اضغط للترقية قبل انتهاء رسالتك الأخيرة:"
                    )
                else:
                    tg_text = (
                        "🚀 <b>حدثنا منصة EGX BOTS بالكامل!</b>\n\n"
                        "نعلم أنك كنت من أوائل وأكثر المتداولين استخداماً لذكاء المنصة في تحليلاتك السابقة. أطلقنا اليوم أضخم ترقية:\n"
                        "• كاشف المصائد السعرية (Wyckoff Traps).\n"
                        "• محدد القيمة العادلة لجميع أسهم السوق.\n"
                        "• تشخيص وإعادة تدوير المحفظة بالذكاء الاصطناعي.\n\n"
                        "ولأنك من مستخدمينا الأوفياء، حسابك مؤهل اليوم للاشتراك في باقة المؤسسين المخفضة بـ 100 ج.م فقط شهرياً مدى الحياة.\n\n"
                        "👇 جرب المنصة ورَقّ حسابك الآن:"
                    )

                tg_keyboard = {
                    "inline_keyboard": [
                        [{"text": "⚡ فك الحظر والترقية بـ 100 ج.م (تثبيت مدى الحياة)", "url": f"{APP_URL}/pricing?plan=pro"}],
                        [{"text": "🪤 استعراض كاشف المصائد الحية", "url": f"{APP_URL}/scanner/technical"}],
                    ]
                }

                tg_res = send_telegram(tg_id, tg_text, reply_markup=tg_keyboard)
                if tg_res.get("ok"):
                    telegram_sent += 1
                    print(f"  [TG-DM] ✅ Sent to {email} (Chat ID: {tg_id})")
                else:
                    telegram_failed += 1
                    print(f"  [TG-DM] ❌ Failed to {email}: {tg_res.get('description')}")
                time.sleep(0.3)

            # B. Resend Email Dispatch
            if not is_user_unsubscribed(uid, email):
                subject, html = build_recovery_email(uid, email, tier_name)
                send_meta = {}
                ok = send_resend_email(email, subject, html, out=send_meta)
                if ok:
                    email_sent += 1
                    resend_id = send_meta.get("id")
                    record_marketing_message(
                        user_id=uid,
                        email=email,
                        message_type=f"paywall_recovery_{tier_name.lower()}",
                        metadata={"tier": tier_name, "total_msgs": msgs, "resend_id": resend_id},
                        provider_message_id=resend_id,
                    )
                    print(f"  [EMAIL] ✅ Sent to {email} (Resend ID: {resend_id})")
                else:
                    email_failed += 1
                    print(f"  [EMAIL] ❌ Failed to {email}")
                time.sleep(0.4)

    print("\n" + "="*60)
    print(f"DISPATCH COMPLETED:")
    print(f"  • Telegram DMs: {telegram_sent} sent, {telegram_failed} failed.")
    print(f"  • Emails: {email_sent} sent, {email_failed} failed.")
    print("="*60)

    # Mandatory Live Post-Dispatch Analytics Report
    print("\n" + "="*60)
    print("📊 GENERATING MANDATORY POST-DISPATCH ANALYTICS BREAKDOWN...")
    print("="*60)
    time.sleep(2)
    analyze_campaign()

if __name__ == '__main__':
    main()
