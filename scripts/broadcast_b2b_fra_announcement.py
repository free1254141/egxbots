"""
Broadcast FRA-compliant B2B SaaS & Affiliate (25%) announcement to:
1) Telegram-linked registered users via @egxbots_bot private messages (with tailored affiliate highlight for registered partners).
2) Non-Telegram active affiliate partners via Resend email (respecting 24h cooldown).

Strictly adheres to FRA SaaS software-tool wording (no buy/sell advisory or promises of return).
"""

import argparse
import datetime
import html
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from supabase import create_client

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv(".env")
load_dotenv("web/.env.local", override=True)

BOT_TOKEN = (os.getenv("ARTORO_AI_BOT") or "").strip()
RELAY_URL = (os.getenv("TELEGRAM_RELAY_URL") or "").strip().rstrip("/")
RESEND_KEY = (os.getenv("RESEND_API_KEY") or "").strip()
FROM_EMAIL = (os.getenv("MARKETING_EMAIL_FROM") or "EGX BOTS <support@egxbots.com>").strip()
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

FRA_DISCLAIMER_HTML = (
    "⚠️ <b>تنويه تنظيمي:</b> المنصة وأدواتها البرمجية (SaaS) توفر بيانات ومؤشرات إحصائية وتقنية "
    "لأغراض البحث والدراسة فقط، ولا تقدم توصيات أو استشارات مالية أو أوامر بيع وشراء. "
    "قرارات الاستثمار مسؤوليتك الشخصية عبر شركات السمسرة المرخصة."
)


def call_telegram_api(method: str, payload: Dict[str, Any], timeout: int = 15) -> Dict[str, Any]:
    """Call Telegram Bot API via direct endpoint or TELEGRAM_RELAY_URL fallback."""
    bases = ["https://api.telegram.org"]
    if RELAY_URL and RELAY_URL != "https://api.telegram.org":
        bases.append(RELAY_URL)

    last_err = "unknown"
    for base in bases:
        try:
            url = f"{base}/bot{BOT_TOKEN}/{method}"
            resp = requests.post(url, json=payload, timeout=timeout)
            data = resp.json()
            if data.get("ok") or resp.status_code in (400, 403):
                return data
            last_err = f"HTTP {resp.status_code}: {str(data)[:160]}"
        except Exception as exc:
            last_err = str(exc)
            continue
    return {"ok": False, "description": last_err}


def build_telegram_message(name: str, affiliate_code: Optional[str]) -> str:
    """Build FRA-aligned SaaS announcement for Telegram private chat."""
    safe_name = html.escape((name or "المستثمر").strip())
    if affiliate_code:
        safe_code = html.escape(affiliate_code)
        aff_block = (
            f"🤝 <b>فرصة إضافية لك كشريك نجاح (كودك: <code>{safe_code}</code>):</b>\n"
            "• أي صاحب جروب أو متدرب أو قناة متابعة فنية يسجل عبر رابطك أو يشترك في باقات الأعمال "
            "تحصل معه على <b>عمولة 25% كاش متكررة شهرياً</b> على كل تجديد.\n"
            '🔗 لوحة الشركاء: <a href="https://egxbots.com/affiliate">https://egxbots.com/affiliate</a>\n\n'
        )
    else:
        aff_block = (
            "🤝 <b>وهل تعرف صاحب جروب أو أكاديمية؟</b>\n"
            "• يمكنك مشاركة الخدمة من خلال برنامج الشركاء والحصول على <b>عمولة 25% كاش متكررة شهرياً</b> "
            'عند اشتراك أي عميل عن طريقك: <a href="https://egxbots.com/affiliate">egxbots.com/affiliate</a>\n\n'
        )

    return (
        f"أهلاً بك يا <b>{safe_name}</b> في عائلة EGX BOTS 👋\n\n"
        "📊 <b>هل تدير مجتمع مستثمرين أو أكاديمية تعليمية في البورصة المصرية أو السعودية؟</b>\n\n"
        "أطلقنا بوابة الأعمال (<b>B2B SaaS</b>) لتشغيل أداة قراءة البيانات والمؤشرات <b>ARTORO</b> "
        "مباشرة داخل جروبات التليجرام تحت اسم وتوقيع مجموعتك الخاص:\n"
        "• عرض فوري للأسعار الرسمية المسجلة، ومؤشرات السيولة (RSI / MACD)، ونقاط الدعم والمقاومة الحسابية.\n"
        "• التحقق الآلي من التوافق الشرعي (EGX33 / تاسي) وحاسبة القيمة العادلة.\n"
        "• توقيع تعريفي خاص باسم مجموعتك أسفل كل رد، مع نظام منع سبام (90 ثانية).\n\n"
        "🎁 <b>متاح الآن تجربة برمجية مجانية لمدة 3 أيام بدون بطاقة بنكية وربط آلي في 60 ثانية:</b>\n"
        '👉 <a href="https://egxbots.com/b2b">https://egxbots.com/b2b</a>\n\n'
        f"{aff_block}"
        f"{FRA_DISCLAIMER_HTML}"
    )


def build_email_html(name: str, affiliate_code: str) -> str:
    """Build FRA-aligned SaaS announcement HTML email for non-Telegram affiliates."""
    safe_name = html.escape((name or "شريكنا العزيز").strip())
    safe_code = html.escape(affiliate_code)
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8" /></head>
<body style="font-family: 'Segoe UI', Tahoma, Arial, sans-serif; background-color: #f4f4f5; padding: 24px; color: #18181b; line-height: 1.7;">
  <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border: 2px solid #18181b; padding: 28px;">
    <div style="background: #10b981; color: #000000; display: inline-block; padding: 4px 12px; font-weight: 800; font-size: 12px; margin-bottom: 12px;">
      EGX BOTS &amp; TASI BOTS · بوابة الأعمال (B2B SaaS)
    </div>
    <h2 style="margin: 0 0 12px 0; font-size: 20px;">أهلاً بك يا {safe_name}، إطلاق باقات الجروبات والأكاديميات (عمولة 25%)</h2>
    <p style="font-size: 14px; color: #3f3f46;">
      أطلقنا بوابة حلول الأعمال الجديدة (<strong>egxbots.com/b2b</strong>) لتمكين أصحاب مجتمعات المستثمرين وأكاديميات التدريب المالي من تشغيل أداة قراءة البيانات والمؤشرات <strong>ARTORO</strong> داخل جروبات التليجرام بتوقيعهم الخاص.
    </p>
    <div style="background: #f4f4f5; border-right: 4px solid #10b981; padding: 14px; margin: 16px 0; font-size: 13px;">
      <strong>ما الذي تقدمه الأداة لأعضاء أي جروب؟</strong><br/>
      • قراءة فورية للأسعار التاريخية المسجلة ومؤشرات السيولة (RSI / MACD) ونقاط الدعم والمقاومة الحسابية.<br/>
      • فحص التوافق الشرعي (EGX33 / تاسي) ومحدد القيمة العادلة للأسهم المصرية والسعودية.<br/>
      • توقيع خاص باسم القناة أو الأكاديمية أسفل كل رد، مع حماية ضد السبام (90 ثانية).
    </div>
    <p style="font-size: 14px; color: #18181b;">
      🤝 <strong>فرصة الشريك (كودك: <code>{safe_code}</code>):</strong><br/>
      يمكنك تجربة الأداة مجاناً لمدة 3 أيام إن كنت تدير جروباً، أو دعوتها لأصحاب القنوات والأكاديميات لتربح <strong>25% عمولة كاش متكررة شهرياً</strong> عن كل مشترك عبر لوحة الشركاء.
    </p>
    <div style="margin: 22px 0;">
      <a href="https://egxbots.com/b2b" style="background: #18181b; color: #ffffff; text-decoration: none; padding: 12px 22px; font-weight: 800; font-size: 14px; display: inline-block;">
        استعراض بوابة الأعمال والتجربة المجانية (3 أيام) ←
      </a>
    </div>
    <hr style="border: none; border-top: 1px solid #e4e4e7; margin: 20px 0;" />
    <p style="font-size: 11px; color: #71717a;">
      ⚠️ <strong>تنويه تنظيمي:</strong> المنصة وأدواتها البرمجية (SaaS) توفر بيانات ومؤشرات إحصائية وتقنية لأغراض البحث والدراسة فقط، ولا تقدم توصيات أو استشارات مالية أو أوامر بيع وشراء. قرارات الاستثمار مسؤوليتك الشخصية عبر شركات السمسرة المرخصة.
    </p>
  </div>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Broadcast FRA-compliant B2B SaaS announcement.")
    parser.add_argument("--send", action="store_true", help="Actually dispatch messages (default is dry-run).")
    args = parser.parse_args()

    if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
        print("Missing required env vars (ARTORO_AI_BOT, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY).")
        sys.exit(1)

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    me = call_telegram_api("getMe", {})
    if not me.get("ok"):
        print(f"Telegram getMe failed: {me}")
        sys.exit(1)
    print(f"Bot verified: @{me['result'].get('username')}")

    profs = (
        sb.table("profiles")
        .select("id, display_name, username, telegram_chat_id")
        .not_.is_("telegram_chat_id", "null")
        .execute()
        .data
        or []
    )

    affs = (
        sb.table("affiliates")
        .select("id, user_id, code, name, is_active")
        .eq("is_active", True)
        .execute()
        .data
        or []
    )
    aff_by_uid = {a["user_id"]: a for a in affs if a.get("user_id")}

    # Distinct Telegram chat_id targets
    tg_targets: List[Dict[str, Any]] = []
    seen_chats = set()
    tg_user_ids = set()
    for p in profs:
        chat_id = str(p.get("telegram_chat_id") or "").strip()
        if not chat_id or chat_id in seen_chats:
            continue
        seen_chats.add(chat_id)
        uid = p["id"]
        tg_user_ids.add(uid)
        aff = aff_by_uid.get(uid)
        tg_targets.append(
            {
                "user_id": uid,
                "chat_id": chat_id,
                "name": p.get("display_name") or p.get("username") or (aff.get("name") if aff else None) or "المستثمر",
                "affiliate_code": aff.get("code") if aff else None,
            }
        )

    # Non-Telegram active human affiliates who haven't received an email today
    today_start = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
    today_logs = (
        sb.table("marketing_message_log")
        .select("user_id")
        .gte("sent_at", today_start)
        .execute()
        .data
        or []
    )
    emailed_today_uids = {l.get("user_id") for l in today_logs if l.get("user_id")}

    email_targets: List[Dict[str, Any]] = []
    skipped_email_affs: List[str] = []
    for uid, aff in aff_by_uid.items():
        if uid in tg_user_ids:
            continue
        if uid in emailed_today_uids:
            skipped_email_affs.append(f"{aff.get('code')} (emailed today)")
            continue
        try:
            u = sb.auth.admin.get_user_by_id(uid)
            email = getattr(getattr(u, "user", None), "email", None)
            if email and "@" in email:
                email_targets.append(
                    {
                        "user_id": uid,
                        "email": email.strip().lower(),
                        "name": aff.get("name") or "شريكنا العزيز",
                        "code": aff.get("code"),
                    }
                )
        except Exception as exc:
            skipped_email_affs.append(f"{aff.get('code')} ({exc})")

    print(
        f"Targets ready -> Telegram: {len(tg_targets)} distinct chats "
        f"(incl. {sum(1 for t in tg_targets if t['affiliate_code'])} affiliates) | "
        f"Affiliate Emails (non-TG): {len(email_targets)} | Skipped email affiliates: {skipped_email_affs}"
    )

    if not args.send:
        print("DRY RUN complete. Pass --send to dispatch live.")
        return

    tg_sent = 0
    tg_blocked = 0
    tg_failed = 0
    tg_errors: List[str] = []

    for idx, t in enumerate(tg_targets, 1):
        text_html = build_telegram_message(t["name"], t["affiliate_code"])
        res = call_telegram_api(
            "sendMessage",
            {
                "chat_id": t["chat_id"],
                "text": text_html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
        if res.get("ok"):
            tg_sent += 1
        else:
            desc = str(res.get("description") or "unknown")
            if "blocked" in desc.lower() or "chat not found" in desc.lower() or "deactivated" in desc.lower():
                tg_blocked += 1
            else:
                tg_failed += 1
            tg_errors.append(f"{t['chat_id']}: {desc}")
        if idx % 15 == 0:
            print(f"  Telegram progress: {idx}/{len(tg_targets)} (sent={tg_sent}, blocked={tg_blocked}, failed={tg_failed})")
        time.sleep(0.15)

    email_sent = 0
    email_failed = 0
    if email_targets and RESEND_KEY:
        for et in email_targets:
            payload = {
                "from": FROM_EMAIL,
                "to": [et["email"]],
                "subject": f"بوابة الأعمال الجديدة (B2B SaaS) وعمولة الشركاء 25% — كودك {et['code']}",
                "html": build_email_html(et["name"], et["code"]),
                "tags": [{"name": "campaign", "value": "b2b_affiliate_launch_2026"}],
            }
            try:
                r = requests.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {RESEND_KEY}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=15,
                )
                r_data = r.json() if r.content else {}
                if r.status_code in (200, 201) and r_data.get("id"):
                    email_sent += 1
                    sb.table("marketing_message_log").insert(
                        {
                            "user_id": et["user_id"],
                            "email": et["email"],
                            "message_type": "b2b_affiliate_launch_2026",
                            "channel": "email",
                            "status": "sent",
                            "provider_message_id": r_data.get("id"),
                            "sent_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            "metadata": {"affiliate_code": et["code"], "campaign": "b2b_affiliate_launch_2026"},
                        }
                    ).execute()
                else:
                    email_failed += 1
                    print(f"  Email failed for {et['email']}: {r.status_code} {r_data}")
            except Exception as exc:
                email_failed += 1
                print(f"  Email exception for {et['email']}: {exc}")
            time.sleep(0.3)

    print("\n=== DISPATCH SUMMARY ===")
    print(f"Telegram: sent={tg_sent}, blocked_or_not_found={tg_blocked}, failed={tg_failed} / total={len(tg_targets)}")
    print(f"Emails (non-TG affiliates): sent={email_sent}, failed={email_failed}, skipped={len(skipped_email_affs)}")
    if tg_errors:
        print("Sample Telegram errors (up to 10):", tg_errors[:10])


if __name__ == "__main__":
    main()
