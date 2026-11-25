"""
scripts/dispatch_trial_reengagement_nov25.py

Dispatches a personalized Arabic re-engagement email via Resend to users who registered
in the last 14 days without completing Telegram linking or ever claiming a Pro trial / subscription.
Includes direct personalized Telegram deep link, website fallback, and manual /start <uid> fallback.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
import time
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api.stock_ai as sai  # noqa: E402


SUBJECT = "🔧 تم إصلاح تفعيل البوت والتجربة المجانية — جرّب EGX BOTS Pro لمدة 3 أيام مجاناً"


def build_email_html(user_id: str, display_name: str | None) -> str:
    tg_url = f"https://t.me/egxbots_bot?start={user_id}"
    profile_url = "https://egxbots.com/profile?activate_trial=1"
    start_cmd = f"/start {user_id}"
    greeting = f"أهلاً بك {display_name}،" if display_name else "أهلاً بك صديقنا،"

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>تم إصلاح ربط تليجرام وتفعيل التجربة المجانية</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #09090b; color: #ffffff; margin: 0; padding: 20px; text-align: right;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; margin: 0 auto; background-color: #121215; border: 2px solid #27272a; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
    <tr>
      <td style="padding: 28px 24px; text-align: center; background-color: #18181b; border-bottom: 2px solid #27272a;">
        <span style="display: inline-block; padding: 5px 14px; background-color: #ffe600; color: #000000; font-weight: 900; font-size: 11px; border-radius: 9999px;">تحديث وإصلاح فوري 🛠️</span>
        <h1 style="color: #ffffff; font-size: 21px; font-weight: 900; margin: 14px 0 0 0; line-height: 1.4;">حسابك جاهز الآن لتفعيل 3 أيام Pro مجاناً 🚀</h1>
        <p style="color: #a1a1aa; font-size: 13px; margin: 6px 0 0 0; font-weight: 600;">بدون بطاقة بنكية وبدون أي التزام</p>
      </td>
    </tr>

    <tr>
      <td style="padding: 26px 24px; line-height: 1.8; font-size: 14px; color: #d4d4d8;">
        <p style="margin-top: 0; font-size: 15px;">{greeting}</p>
        <p>لاحظنا أنك أنشأت حساباً على <strong>EGX BOTS</strong> مؤخراً ولم تكتمل خطوة ربط التليجرام أو تفعيل التجربة المجانية <strong>(Pro لمدة 3 أيام)</strong>. نعتذر لك عن أي عطل أو تأخير حدث أثناء الربط — لقد قمنا بإصلاح المشكلة بالكامل، وأصبح بإمكانك التفعيل الآن في ثانية واحدة.</p>

        <div style="background-color: #18181b; border-right: 4px solid #10b981; padding: 16px 20px; border-radius: 10px; margin: 20px 0;">
          <h3 style="color: #ffffff; margin: 0 0 8px 0; font-size: 15px; font-weight: 900;">ماذا يُفتح لك فوراً خلال الـ 3 أيام المجانية؟</h3>
          <ul style="padding-right: 20px; margin: 0; color: #e4e4e7; font-size: 13px;">
            <li style="margin-bottom: 8px;"><strong>🤖 شات ARTORO الذكي (350 رسالة/شهر):</strong> تحليل فني وكمي لأي سهم في مصر والسعودية والإمارات وقطر والذهب، وقراءة الشارت والمحفظة بالصورة.</li>
            <li style="margin-bottom: 8px;"><strong>📡 قنوات وتنبيهات تليجرام VIP:</strong> إشارات لحظية للسيولة والاختراقات وتنبيهات أسهم محفظتك (حتى 15 سهماً).</li>
            <li><strong>📊 رادار القيمة العادلة والتجميع والماسح الفني:</strong> مؤشرات إحصائية محدثة يومياً بعد كل جلسة.</li>
          </ul>
        </div>

        <div style="text-align: center; margin: 28px 0 14px 0;">
          <a href="{tg_url}" style="display: inline-block; background-color: #10b981; color: #000000; font-weight: 900; font-size: 15px; padding: 14px 28px; border-radius: 12px; text-decoration: none; border: 2px solid #059669;">🚀 ربط التليجرام وتفعيل 3 أيام Pro فوراً</a>
        </div>

        <div style="text-align: center; margin: 12px 0 22px 0;">
          <a href="{profile_url}" style="display: inline-block; background-color: #ffe600; color: #000000; font-weight: 900; font-size: 13px; padding: 11px 22px; border-radius: 10px; text-decoration: none; border: 2px solid #000000;">🌐 أو التفعيل مباشرة من حسابك في الموقع</a>
        </div>

        <div style="background-color: #18181b; border: 1px dashed #52525b; padding: 14px 16px; border-radius: 10px; text-align: center;">
          <p style="margin: 0 0 8px 0; font-size: 12px; color: #e4e4e7; font-weight: 700;">💡 لو لم يفتح الرابط تلقائياً: افتح البوت <strong>@egxbots_bot</strong> على تليجرام وأرسل له هذا الأمر:</p>
          <div dir="ltr" style="background-color: #09090b; border: 1px solid #3f3f46; padding: 8px 12px; border-radius: 6px; font-family: monospace; font-size: 12px; color: #ffe600; word-break: break-all;">{start_cmd}</div>
        </div>

        <p style="font-size: 12px; color: #a1a1aa; margin-top: 18px;">
          بعد انتهاء الـ 3 أيام المجانية، يمكنك الترقية في أي وقت عبر بوابة <strong>EasyKash</strong> المعتمدة (من 100 ج.م للشات أو VIP، أو 150 ج.م للباقة الشاملة).
        </p>
      </td>
    </tr>

    <tr>
      <td style="padding: 12px 24px; background-color: #18181b; border-top: 1px solid #27272a; font-size: 11px; color: #a1a1aa; text-align: justify; line-height: 1.6;">
        ⚠️ <strong>تنبيه قانوني وإخلاء مسؤولية (FRA):</strong> المنصة وأدواتها البرمجية (SaaS) توفر مؤشرات وقراءات فنية وإحصائية لأغراض البحث الشخصي والتعليم فقط، ولا تقدم توصية استثمارية أو استشارة مالية أو إدارة محافظ. قرار التداول مسؤوليتك الشخصية.
      </td>
    </tr>

    <tr>
      <td style="padding: 18px 24px; text-align: center; background-color: #18181b; border-top: 1px solid #27272a; font-size: 11px; color: #71717a;">
        منصة EGX BOTS للتحليل الكمي والذكاء الاصطناعي · <a href="https://egxbots.com" style="color: #a1a1aa; text-decoration: underline;">egxbots.com</a>
        <br>
        <span style="display: inline-block; margin-top: 6px;">للتواصل والدعم: <a href="mailto:support@egxbots.com" style="color: #a1a1aa;">support@egxbots.com</a></span>
      </td>
    </tr>
  </table>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch re-engagement emails to eligible never-Pro unlinked users.")
    parser.add_argument("--dry-run", action="store_true", help="Print eligible candidates without sending emails.")
    parser.add_argument("--days", type=int, default=14, help="Lookback window in days (default: 14).")
    args = parser.parse_args()

    load_dotenv(".env")
    load_dotenv("web/.env.local", override=True)

    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = os.getenv("MARKETING_EMAIL_FROM", "EGX BOTS <support@egxbots.com>").strip()
    if not args.dry_run and (not api_key or api_key.startswith("re_placeholder")):
        print("ERROR: RESEND_API_KEY is missing or placeholder.")
        return 1

    sai._init_supabase()
    sb = sai.supabase
    if sb is None:
        print("ERROR: Supabase unavailable.")
        return 1

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    since_iso = (now_utc - datetime.timedelta(days=args.days)).isoformat()
    cutoff_48h = (now_utc - datetime.timedelta(hours=48)).isoformat()

    # 1. Fetch unlinked profiles in the lookback window
    unlinked_profs = (
        sb.table("profiles")
        .select("id, created_at, display_name, username, telegram_chat_id")
        .gte("created_at", since_iso)
        .is_("telegram_chat_id", "null")
        .order("created_at", desc=True)
        .limit(500)
        .execute()
        .data
        or []
    )
    uids = [str(p["id"]) for p in unlinked_profs if p.get("id")]
    if not uids:
        print("No unlinked profiles found in window.")
        return 0

    # 2. Exclude ANY user with a trial, any subscription (any status), approved order, or founder row
    trials = {r["user_id"] for r in (sb.table("subscription_trials").select("user_id").in_("user_id", uids).limit(500).execute().data or [])}
    subs = {r["user_id"] for r in (sb.table("subscriptions").select("user_id").in_("user_id", uids).limit(500).execute().data or [])}
    orders = {r["user_id"] for r in (sb.table("local_payment_orders").select("user_id").in_("user_id", uids).eq("status", "approved").limit(500).execute().data or [])}
    founders = {r["user_id"] for r in (sb.table("founders_offer_members").select("user_id").in_("user_id", uids).limit(500).execute().data or [])}
    excluded = trials | subs | orders | founders

    # 3. Exclude anyone emailed within last 48h or already sent this campaign
    recent_logs = (
        sb.table("marketing_message_log")
        .select("user_id, email, message_type, sent_at")
        .gte("sent_at", cutoff_48h)
        .limit(2000)
        .execute()
        .data
        or []
    )
    already_campaign = (
        sb.table("marketing_message_log")
        .select("user_id, email")
        .eq("message_type", "trial_reengagement_fix_nov25")
        .limit(2000)
        .execute()
        .data
        or []
    )
    recent_uids = {str(r.get("user_id") or "") for r in recent_logs if r.get("user_id")} | {str(r.get("user_id") or "") for r in already_campaign if r.get("user_id")}
    recent_emails = {str(r.get("email") or "").lower().strip() for r in recent_logs if r.get("email")} | {str(r.get("email") or "").lower().strip() for r in already_campaign if r.get("email")}

    # 4. Paginate auth users to resolve verified emails
    email_map: dict[str, str] = {}
    page = 1
    while True:
        res = sb.auth.admin.list_users(page=page, per_page=200)
        if not res:
            break
        for u in res:
            em = (getattr(u, "email", None) or "").lower().strip()
            if em and "@" in em:
                email_map[str(u.id)] = em
        if len(res) < 200:
            break
        page += 1

    candidates = []
    for p in unlinked_profs:
        uid = str(p["id"])
        if uid in excluded or uid in recent_uids:
            continue
        em = email_map.get(uid, "")
        if not em or em in recent_emails:
            continue
        disp = (p.get("display_name") or p.get("username") or "").strip() or None
        candidates.append({"user_id": uid, "email": em, "display_name": disp, "created_at": str(p.get("created_at") or "")[:10]})

    print(f"Unlinked profiles ({args.days}d): {len(unlinked_profs)} | Excluded ever-Pro/trial: {len(excluded)} | Eligible final: {len(candidates)}")
    if args.dry_run:
        for idx, c in enumerate(candidates, 1):
            print(f"  [{idx}] {c['email']} | {c['created_at']} | {c['user_id']}")
        return 0

    sent_count = 0
    failed_count = 0
    for idx, c in enumerate(candidates, 1):
        to_email = c["email"]
        uid = c["user_id"]
        html = build_email_html(uid, c["display_name"])
        payload = {"from": from_email, "to": [to_email], "subject": SUBJECT, "html": html}
        try:
            res = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=15,
            )
            if res.status_code in (200, 201):
                msg_id = (res.json() or {}).get("id")
                sent_count += 1
                sb.table("marketing_message_log").insert({
                    "user_id": uid,
                    "email": to_email,
                    "message_type": "trial_reengagement_fix_nov25",
                    "channel": "email",
                    "status": "sent",
                    "provider_message_id": msg_id,
                    "metadata": {"campaign": "trial_reengagement_fix_nov25", "signup_date": c["created_at"]},
                }).execute()
                print(f"[{idx}/{len(candidates)}] OK: {to_email}")
            else:
                failed_count += 1
                print(f"[{idx}/{len(candidates)}] FAILED {to_email}: {res.status_code} - {res.text}")
        except Exception as exc:
            failed_count += 1
            print(f"[{idx}/{len(candidates)}] EXCEPTION {to_email}: {exc}")
        time.sleep(0.55)  # stay comfortably under Resend 2 req/s rate limit

    print(f"\nDISPATCH COMPLETE -> Sent: {sent_count} | Failed: {failed_count}")
    return 0 if failed_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
