#!/usr/bin/env python3
"""
scripts/activate_trials_and_vip_invites_2026_11_18.py
1. Repairs missing VIP Telegram group invite links for currently active trial users (e.g. ronaldoboyka20, ahmedharhash983) and sends their VIP invite button on Telegram & Email.
2. Auto-activates the 3-day Pro Trial for all eligible users who already linked their Telegram account (tg_linked_eligible_for_trial), provisions their personal VIP Telegram group invite link, and dispatches the VIP group join button via Telegram DM + Email.
3. Outputs the mandatory post-dispatch Resend live analytics report.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

sys.stdout.reconfigure(encoding="utf-8")
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))
load_dotenv(os.path.join(ROOT_DIR, "web", ".env.local"), override=True)

from api.stock_ai import _init_supabase, supabase
from api.telegram_pro_invites import ensure_pro_invite, send_pro_welcome_to_user_telegram
from api.marketing_lifecycle import (
    send_resend_email,
    record_marketing_message,
    is_user_unsubscribed,
    generate_unsub_token,
    APP_URL,
)
from jobs.analyze_email_campaign import analyze_campaign


def build_vip_trial_email(user_id: str, email: str, invite_link: str) -> str:
    unsub_token = generate_unsub_token(user_id, email)
    unsub_url = f"{APP_URL}/unsubscribe?uid={user_id}&token={unsub_token}&email={email}"
    cta_url = invite_link or f"{APP_URL}/reports"
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:24px 12px;background:#09090b;font-family:'Segoe UI',Tahoma,Arial,sans-serif;color:#f4f4f5;direction:rtl;text-align:right;">
  <div style="max-width:580px;margin:0 auto;background:#18181b;border:2px solid #10b981;border-radius:12px;overflow:hidden;">
    <div style="background:linear-gradient(135deg,#059669,#10b981);padding:18px 24px;color:#000;font-weight:900;font-size:14px;">
      🎉 تم تفعيل تجربة PRO المجانية (3 أيام) + دعوة قناة VIP الخاصة
    </div>
    <div style="padding:26px 24px;">
      <h1 style="margin:0 0 14px;font-size:20px;line-height:1.5;color:#ffffff;">أهلاً بك في مجتمع المشتركين VIP على EGX BOTS 🚀</h1>
      <div style="font-size:15px;line-height:1.8;color:#d4d4d8;">
        <p>تم تفعيل <strong>تجربة باقة PRO المجانية لمدة 3 أيام كاملة</strong> على حسابك بنجاح!</p>
        <p>💎 <strong>خطوتك الأهم الآن:</strong> أصدرنا لك رابط دعوة شخصي ومباشر للانضمام إلى <strong>الجروب والقناة الخاصة بعملاء VIP على تليجرام</strong> لمتابعة إشارات الدخول، الأهداف، ووقف الخسارة لحظة بلحظة:</p>
      </div>
      <div style="margin-top:24px;text-align:center;">
        <a href="{cta_url}" style="display:inline-block;background:#229ED9;color:#ffffff;font-weight:900;font-size:15px;padding:14px 28px;border-radius:8px;text-decoration:none;border:2px solid #000;">
          💎 الانضمام للجروب الخاص VIP على تليجرام الآن
        </a>
      </div>
      <div style="margin-top:16px;text-align:center;">
        <a href="{APP_URL}/scanner/technical" style="color:#10b981;font-size:13px;font-weight:700;text-decoration:underline;">
          فتح الماسح الفني والشات الذكي على الموقع ←
        </a>
      </div>
    </div>
    <div style="padding:14px 24px;background:#09090b;border-top:1px solid #27272a;font-size:11px;color:#71717a;text-align:center;">
      منصة EGX BOTS للتحليل الذكي • <a href="{unsub_url}" style="color:#71717a;">إلغاء الاشتراك من الرسائل الترويجية</a>
    </div>
  </div>
</body>
</html>"""


def main() -> None:
    _init_supabase()
    if not supabase:
        print("[ERROR] Supabase not initialized")
        return

    # 1. Active trial users missing invite_link (already repaired in run 1)
    active_missing: List[Dict[str, str]] = []

    # 2. Eligible users who already linked Telegram but never had their 3-day trial activated
    tg_linked_eligible = [
        {"user_id": "35282ae8-3ae9-4a98-aca5-fa40dbb96c2a", "email": "sr7an.it@gmail.com", "tg_id": "7300751219"},
        {"user_id": "cc20cfd3-f253-4680-b445-3bf8076f2c95", "email": "kokomagdy75@gmail.com", "tg_id": "536575948"},
        {"user_id": "14515187-1052-43f0-ab16-9ebfaafcf2fa", "email": "moataz.survey@gmail.com", "tg_id": "1568951778"},
        {"user_id": "1b2a702c-bc10-4610-8dce-7970502969ba", "email": "asser.a.abadi@gmail.com", "tg_id": "8600368359"},
        {"user_id": "5d6ab6bf-7986-4698-ab88-9872226c07cf", "email": "mhmdmhmdslah503@gmail.com", "tg_id": "9097864371"},
        {"user_id": "d0fb2257-4212-4b8c-82df-837beb2f7811", "email": "mostafaelalfy009@gmail.com", "tg_id": "160013663"},
        {"user_id": "98135830-bdaf-42c3-80cf-fa63ce9effef", "email": "omarsoffar87@gmail.com", "tg_id": "1165398825"},
        {"user_id": "b881dead-2984-4d9c-8a2e-c3c6362a2c1f", "email": "mostafaabosofian79@gmail.com", "tg_id": "8716075001"},
        {"user_id": "bd4db4e2-f551-4c47-9d7c-c65e21be44fa", "email": "amrmkamel2@gmail.com", "tg_id": "7452952384"},
        {"user_id": "606e6232-8ac4-43f3-a238-18d9b439abb4", "email": "mohamed345789126@gmail.com", "tg_id": "1492592730"},
        {"user_id": "cecd9453-9603-486d-827c-9d52f4d18279", "email": "a91084453@gmail.com", "tg_id": "8177956451"},
        {"user_id": "f744e336-91f9-4a95-b964-c908429271dc", "email": "hosamsat2830@gmail.com", "tg_id": "1842154343"},
        {"user_id": "2efd00c0-bd8e-469a-b3ee-60451004b943", "email": "mohmedselman2010@gmail.com", "tg_id": "840533489"},
        {"user_id": "c890fb75-9976-4020-950d-8749bdde9d45", "email": "drmadhatahmedaziz@gmail.com", "tg_id": "8444913631"},
        {"user_id": "78e08e20-23ab-445b-ba25-8531089b4185", "email": "koko22toto33@gmail.com", "tg_id": "1009630868"},
        {"user_id": "f3b581d0-351d-450e-a255-8511cab256e6", "email": "eyad19912@gmail.com", "tg_id": "1230788471"},
        {"user_id": "e5a85084-4ffe-4881-bf8b-f2419e1e3954", "email": "remon_edwar2000@yahoo.com", "tg_id": "1598337071"},
        {"user_id": "26a28742-6beb-49da-9a6b-830bef9c0efc", "email": "123456789pspp@gmail.com", "tg_id": "730553158"},
        {"user_id": "8496a09a-28f1-430b-8426-601255b6b513", "email": "hanyawny7777@gmail.com", "tg_id": "1405714794"},
        {"user_id": "b9e499fc-7ecf-4b20-b4f4-e1eb4637b1d9", "email": "mmix1887@gmail.com", "tg_id": "5353164143"},
        {"user_id": "4784557d-5a13-459d-b6ec-56c8dbb30429", "email": "bgugvbhchj@gmail.com", "tg_id": "8648527741"},
        {"user_id": "8f5613c2-6b68-4532-91ac-18a3ac755ac3", "email": "babaelmgal1@gmail.com", "tg_id": "7880942450"},
        {"user_id": "20e36ae5-5704-4b77-bfc8-9bff14d0a689", "email": "adelabdelsalam20@gmail.com", "tg_id": "7833601159"},
        {"user_id": "3d0d8f9b-fc10-46f3-8f8b-1cba579a9ea2", "email": "algnralmohammed6@gmail.com", "tg_id": "1454957376"},
        {"user_id": "85a0a0d2-f16e-4512-81a1-dbc7d49186a0", "email": "dr.shehab1@gmail.com", "tg_id": "8588174034"},
        {"user_id": "59f03345-cede-4c88-a7b7-e0d963230004", "email": "ahmedrh05@gmail.com", "tg_id": "8866854557"},
        {"user_id": "573c7e12-4247-4b39-8fae-52fa762d3f12", "email": "ahmed.abdelaziz.01@gmail.com", "tg_id": "1053521947"},
        {"user_id": "cfb3ceb3-d958-4645-bf1e-6a1c846b88db", "email": "mohamed.rifaey.91@gmail.com", "tg_id": "6971565028"},
        {"user_id": "41878c10-0dba-4e4f-9a48-9163db2e6c67", "email": "hes4amahmed@gmail.com", "tg_id": "7309292564"},
    ]

    already_emailed_today = {
        "moataz.survey@gmail.com",
        "mhmdmhmdslah503@gmail.com",
        "amrmkamel2@gmail.com",
        "drmadhatahmedaziz@gmail.com",
        "eyad19912@gmail.com",
        "hanyawny7777@gmail.com",
        "babaelmgal1@gmail.com",
        "algnralmohammed6@gmail.com",
    }

    trials_activated = 0
    invites_generated = 0
    tg_sent = 0
    emails_sent = 0

    print("=== STEP 1: REPAIRING VIP INVITE LINKS FOR ACTIVE TRIAL USERS ===")
    for u in active_missing:
        uid = u["user_id"]
        email = u["email"]
        exp = u["expires_at"]
        inv = ensure_pro_invite(uid, exp) or {}
        link = str(inv.get("invite_link") or "").strip()
        if link:
            invites_generated += 1
            sent = send_pro_welcome_to_user_telegram(
                user_id=uid,
                invite_link=link,
                plan_name="تجربة Pro المجانية (3 أيام)",
                subscription_end=exp,
            )
            if sent:
                tg_sent += 1
            print(f"  [REPAIRED] {email} -> {link} (TG sent={sent})")
            if not is_user_unsubscribed(uid, email):
                subject = "💎 رابط انضمامك الخاص لجروب VIP على تليجرام جاهز الآن!"
                html = build_vip_trial_email(uid, email, link)
                meta: Dict[str, Any] = {}
                if send_resend_email(email, subject, html, out=meta):
                    emails_sent += 1
                    record_marketing_message(
                        user_id=uid,
                        email=email,
                        message_type="vip_group_invite_active_trial_2026_11_18",
                        metadata={"invite_link": link, "resend_id": meta.get("id")},
                        provider_message_id=meta.get("id"),
                    )
        time.sleep(0.35)

    print("\n=== STEP 2: PROVISIONING VIP GROUP INVITES & DISPATCHING TO 29 NEW TRIAL USERS ===")
    for u in tg_linked_eligible:
        uid = u["user_id"]
        email = u["email"]
        tg_id = u["tg_id"]
        try:
            # Check if trial was already created in subscription_trials (or create now)
            tr_row = supabase.table("subscription_trials").select("expires_at").eq("user_id", uid).limit(1).execute()
            exp = ""
            if tr_row and tr_row.data:
                exp = str(tr_row.data[0].get("expires_at") or "")
            else:
                rpc_data: Dict[str, Any] = {}
                try:
                    rpc_res = supabase.rpc("start_pro_trial", {
                        "p_user_id": uid,
                        "p_canonical_email": email.lower(),
                        "p_ip_hash": None,
                        "p_device_hash": None,
                        "p_telegram_chat_id": tg_id,
                    }).execute()
                    rpc_data = getattr(rpc_res, "data", None) or {}
                except Exception as rpc_exc:
                    arg0 = rpc_exc.args[0] if getattr(rpc_exc, "args", None) else None
                    if isinstance(arg0, dict) and "success" in arg0:
                        rpc_data = arg0
                if not isinstance(rpc_data, dict) or not rpc_data.get("success"):
                    print(f"  [SKIP] {email}: {rpc_data}")
                    continue
                exp = str(rpc_data.get("expires_at") or "")

            if not exp:
                continue

            trials_activated += 1
            try:
                supabase.table("user_activity_events").insert({
                    "user_id": uid,
                    "event_name": "trial_started",
                    "path": "/telegram-bot",
                    "metadata": {"source": "tg_linked_auto_activation_campaign", "telegram_chat_id": tg_id},
                }).execute()
            except Exception:
                pass

            inv = ensure_pro_invite(uid, exp) or {}
            link = str(inv.get("invite_link") or "").strip()
            if link:
                invites_generated += 1

            sent = send_pro_welcome_to_user_telegram(
                user_id=uid,
                invite_link=link,
                plan_name="تجربة Pro المجانية (3 أيام)",
                subscription_end=exp,
            )
            if sent:
                tg_sent += 1
            print(f"  [TRIAL+VIP] ✅ {email} | link={link} | TG={sent}")

            # Send email with the personal VIP invite link if they weren't already emailed in the earlier batch
            if email not in already_emailed_today and not is_user_unsubscribed(uid, email):
                subject = "🎁 تم تفعيل تجربتك المجانية (3 أيام PRO) + رابط دخول جروب VIP الخاص!"
                html = build_vip_trial_email(uid, email, link)
                meta = {}
                if send_resend_email(email, subject, html, out=meta):
                    emails_sent += 1
                    record_marketing_message(
                        user_id=uid,
                        email=email,
                        message_type="tg_linked_trial_vip_invite_2026_11_18",
                        metadata={"invite_link": link, "resend_id": meta.get("id")},
                        provider_message_id=meta.get("id"),
                    )
            time.sleep(0.35)
        except Exception as exc:
            print(f"  [ERR] {email}: {exc}")

    print("\n" + "=" * 60)
    print(f"DONE: New Trials Activated={trials_activated} | Personal VIP Invites Generated={invites_generated} | TG VIP Invites Sent={tg_sent} | Emails Sent={emails_sent}")
    print("=" * 60)
    time.sleep(2)
    analyze_campaign()


if __name__ == "__main__":
    main()
