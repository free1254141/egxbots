#!/usr/bin/env python3
"""
scripts/dispatch_conversion_boost_2026_11_18.py
Targeted conversion & B2B group activation campaign (Nov 18, 2026):
1. B2B Unlinked Trial Owners (2 users) -> 1-click Telegram group activation link + /activate code.
2. Churned Pro Subscribers (10 users) -> Pro renewal win-back via official /pricing checkout.
3. Abandoned Checkout Users (6 users) -> Complete official /pricing checkout or start 3-day trial.
4. Active Free Power Users with No Trial (15 users) -> Claim 3-day free Pro trial on /pricing.
"""
from __future__ import annotations

import os
import sys
import time
import requests
from typing import Any, Dict, List, Tuple

sys.stdout.reconfigure(encoding="utf-8")
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))
load_dotenv(os.path.join(ROOT_DIR, "web", ".env.local"), override=True)

from api.marketing_lifecycle import (
    send_resend_email,
    record_marketing_message,
    is_user_unsubscribed,
    generate_unsub_token,
    APP_URL,
)
from jobs.analyze_email_campaign import analyze_campaign

BOT_TOKEN = (os.environ.get("ARTORO_AI_BOT") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def send_telegram(chat_id: str, text: str, reply_markup: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not BOT_TOKEN or not chat_id:
        return {"ok": False, "error": "Missing token or chat_id"}
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload: Dict[str, Any] = {
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
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def build_email_html(
    *,
    user_id: str,
    email: str,
    badge: str,
    headline: str,
    body_html: str,
    cta_text: str,
    cta_url: str,
    secondary_text: str = "",
    secondary_url: str = "",
) -> str:
    unsub_token = generate_unsub_token(user_id, email)
    unsub_url = f"{APP_URL}/unsubscribe?uid={user_id}&token={unsub_token}&email={email}"
    secondary_block = ""
    if secondary_text and secondary_url:
        secondary_block = f"""
        <div style="margin-top: 14px; text-align: center;">
          <a href="{secondary_url}" style="color: #10b981; font-size: 13px; font-weight: 700; text-decoration: underline;">
            {secondary_text}
          </a>
        </div>
        """

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:24px 12px;background:#09090b;font-family:'Segoe UI',Tahoma,Arial,sans-serif;color:#f4f4f5;direction:rtl;text-align:right;">
  <div style="max-width:580px;margin:0 auto;background:#18181b;border:2px solid #27272a;border-radius:12px;overflow:hidden;">
    <div style="background:linear-gradient(135deg,#059669,#10b981);padding:18px 24px;color:#000;font-weight:900;font-size:14px;">
      {badge}
    </div>
    <div style="padding:26px 24px;">
      <h1 style="margin:0 0 14px;font-size:20px;line-height:1.5;color:#ffffff;">{headline}</h1>
      <div style="font-size:15px;line-height:1.8;color:#d4d4d8;">
        {body_html}
      </div>
      <div style="margin-top:26px;text-align:center;">
        <a href="{cta_url}" style="display:inline-block;background:#10b981;color:#000000;font-weight:900;font-size:15px;padding:14px 28px;border-radius:8px;text-decoration:none;border:2px solid #000;">
          {cta_text}
        </a>
      </div>
      {secondary_block}
    </div>
    <div style="padding:14px 24px;background:#09090b;border-top:1px solid #27272a;font-size:11px;color:#71717a;text-align:center;">
      منصة EGX BOTS للتحليل الذكي • <a href="{unsub_url}" style="color:#71717a;">إلغاء الاشتراك من الرسائل الترويجية</a>
    </div>
  </div>
</body>
</html>"""


def main() -> None:
    # 1. B2B Unlinked Trial Owners
    b2b_targets = [
        {
            "user_id": "391a820b-5642-4dfc-b06e-460e9443bf70",
            "email": "sayedyehia1994@gmail.com",
            "name": "أستاذ سيد",
            "telegram_chat_id": "1306633168",
            "short_code": "9af81f17",
            "order_id": "B2B-TRIAL-4OTBEP",
        },
        {
            "user_id": "86c79da2-d185-41c2-9ddd-5f097ba08e01",
            "email": "khalifakhaled883@gmail.com",
            "name": "أستاذ خالد",
            "telegram_chat_id": None,
            "short_code": "d64c94f7",
            "order_id": "B2B-TRIAL-CD04FB",
        },
    ]

    # 2. Churned Pro Subscribers (10 real users)
    churned_pro_targets = [
        {"user_id": "10e61c50-aedf-44e3-b885-32d3c3b4d224", "email": "amrosami94@gmail.com", "telegram_chat_id": "8991028165"},
        {"user_id": "282fddc5-a5c2-4c31-803b-a3b8015ac3ea", "email": "eng.elwelely@gmail.com", "telegram_chat_id": "1104030746"},
        {"user_id": "2974d0db-711a-408b-8ef4-9f0853561e64", "email": "mohamedkani10@gmail.com", "telegram_chat_id": "1143988365"},
        {"user_id": "30478844-fef3-48d2-b512-d34b11488a78", "email": "mahmoudelmorshedy94@gmail.com", "telegram_chat_id": "5950650613"},
        {"user_id": "60e5fb92-7b5e-46b7-bb81-c6ebab3692aa", "email": "dralaagaber@gmail.com", "telegram_chat_id": "5635227755"},
        {"user_id": "632ad712-8e28-43fe-969b-9d9330beee5d", "email": "mohamed.m.abdellatif@gmail.com", "telegram_chat_id": "6777125447"},
        {"user_id": "65f8472d-b19e-46d2-966e-5590c2668080", "email": "saied.abdelfatah90@gmail.com", "telegram_chat_id": "1303952732"},
        {"user_id": "6620f1c9-3822-4e1e-b798-2cbe0ea9141d", "email": "amraly2010@gmail.com", "telegram_chat_id": None},
        {"user_id": "8010a163-6d2f-40df-834f-6ad9cbd1faa5", "email": "ramzyalomda115@gmail.com", "telegram_chat_id": "8651357614"},
        {"user_id": "c634fe18-9e6f-4f35-b2aa-1fa7a22ad78d", "email": "trobicola3@gmail.com", "telegram_chat_id": "8893903002"},
    ]

    # 3. Abandoned Official Checkout Users (6 unique non-churned users)
    abandoned_targets = [
        {"user_id": "49c0564d-8d13-4b69-bfa7-905099fcbcd5", "email": "mostafadev2@gmail.com", "telegram_chat_id": None, "plan_id": "pro"},
        {"user_id": "01ab2b3a-2434-4992-b87e-95dce10f6807", "email": "lawyermoshehata@gmail.com", "telegram_chat_id": None, "plan_id": "pro"},
        {"user_id": "3424d6a8-e62c-4e0a-a1de-0567f62ba73b", "email": "aboamara55556@gmail.com", "telegram_chat_id": None, "plan_id": "lifetime"},
        {"user_id": "32f97883-a9c6-44d1-a6d0-317236ea363d", "email": "mohamed12faisa@gmail.com", "telegram_chat_id": None, "plan_id": "pro"},
        {"user_id": "66af5e3c-68fc-402b-82ed-38988b2ff12a", "email": "civilengmohamed2012@gmail.com", "telegram_chat_id": None, "plan_id": "pro"},
        {"user_id": "136f9e02-c12b-4924-bcbf-16baaac287e5", "email": "shhabm3@gmail.com", "telegram_chat_id": None, "plan_id": "pro"},
    ]

    # 4. Active Free Power Users (>= 5 chat questions in 30d, never claimed 3-day trial)
    power_free_targets = [
        {"user_id": "bd4db4e2-f551-4c47-9d7c-c65e21be44fa", "email": "amrmkamel2@gmail.com", "telegram_chat_id": "7452952384", "q_count": 17},
        {"user_id": "c619052a-bd90-4b41-a567-150c5b932043", "email": "bmohamedrefaat@gmail.com", "telegram_chat_id": None, "q_count": 16},
        {"user_id": "14515187-1052-43f0-ab16-9ebfaafcf2fa", "email": "moataz.survey@gmail.com", "telegram_chat_id": "1568951778", "q_count": 15},
        {"user_id": "3d0d8f9b-fc10-46f3-8f8b-1cba579a9ea2", "email": "algnralmohammed6@gmail.com", "telegram_chat_id": "1454957376", "q_count": 10},
        {"user_id": "5d6ab6bf-7986-4698-ab88-9872226c07cf", "email": "mhmdmhmdslah503@gmail.com", "telegram_chat_id": "9097864371", "q_count": 10},
        {"user_id": "c890fb75-9976-4020-950d-8749bdde9d45", "email": "drmadhatahmedaziz@gmail.com", "telegram_chat_id": "8444913631", "q_count": 10},
        {"user_id": "757a9c0f-dee4-4dbb-a23e-2313834b6295", "email": "petertharwat15@yahoo.com", "telegram_chat_id": None, "q_count": 9},
        {"user_id": "8f5613c2-6b68-4532-91ac-18a3ac755ac3", "email": "babaelmgal1@gmail.com", "telegram_chat_id": "7880942450", "q_count": 8},
        {"user_id": "d1bd8dd3-96f0-447f-9be0-a147aa994928", "email": "w99512@gmail.com", "telegram_chat_id": None, "q_count": 8},
        {"user_id": "90e8c48e-d001-4ea2-8ad8-5b93f273eea4", "email": "hatemfam@gmail.com", "telegram_chat_id": None, "q_count": 6},
        {"user_id": "f3b581d0-351d-450e-a255-8511cab256e6", "email": "eyad19912@gmail.com", "telegram_chat_id": "1230788471", "q_count": 6},
        {"user_id": "3eee8fe8-d9e9-48ee-a09a-6e8d1e356ffa", "email": "tarek2011999@gmail.com", "telegram_chat_id": None, "q_count": 6},
        {"user_id": "8496a09a-28f1-430b-8426-601255b6b513", "email": "hanyawny7777@gmail.com", "telegram_chat_id": "1405714794", "q_count": 5},
        {"user_id": "83ebd3d2-9380-4d8d-8c58-f752efe6b348", "email": "ronaldoboyka20@gmail.com", "telegram_chat_id": "1799538430", "q_count": 5},
        {"user_id": "70921780-8b3a-46f2-a194-91f5ca699137", "email": "mahmoud.dosouki458@gmail.com", "telegram_chat_id": None, "q_count": 5},
    ]

    email_sent = 0
    email_failed = 0
    tg_sent = 0
    tg_failed = 0

    print("=== 1. DISPATCHING B2B GROUP ACTIVATION FOLLOW-UP (2 USERS) ===")
    for b in b2b_targets:
        uid = b["user_id"]
        email = b["email"]
        code = b["short_code"]
        connect_url = f"https://t.me/egxbots_bot?startgroup=activate_{code}&admin=delete_messages+pin_messages"
        dashboard_url = f"{APP_URL}/b2b/dashboard"

        if b["telegram_chat_id"]:
            tg_msg = (
                f"أهلاً بك {b['name']} 👋\n\n"
                "لاحظنا أنك قمت بتفعيل <b>الرخصة التجريبية لبوت الجروبات (B2B)</b> على منصة EGX BOTS، ولكن لم يتم ربط البوت داخل مجموعتك على تليجرام بعد!\n\n"
                "🎁 <b>قمنا بتمديد صلاحية تجربتك المجانية لمدة 3 أيام كاملة تبدأ من اليوم!</b>\n\n"
                "⚡ <b>طريقة التفعيل في 10 ثوانٍ فقط:</b>\n"
                "1️⃣ اضغط الزر بالأسفل لاختيار مجموعتك وإضافة البوت مشرفاً (Admin).\n"
                f"2️⃣ أو اكتب داخل الجروب هذا الأمر مباشرة:\n<code>/activate {code}</code>\n\n"
                "بمجرد التفعيل، سيرد البوت آلياً على استفسارات أعضاء جروبك عن أسهم البورصة المصرية والسعودية بتوقيع قناتك الخاص!"
            )
            tg_kb = {
                "inline_keyboard": [
                    [{"text": "🚀 ربط وتفعيل البوت في جروبي بضغطة واحدة", "url": connect_url}],
                    [{"text": "⚙️ لوحة تحكم جروبي (B2B Dashboard)", "url": dashboard_url}],
                ]
            }
            res = send_telegram(b["telegram_chat_id"], tg_msg, reply_markup=tg_kb)
            if res.get("ok"):
                tg_sent += 1
                print(f"  [B2B TG] ✅ Sent to {email}")
            else:
                tg_failed += 1
                print(f"  [B2B TG] ❌ Failed to {email}: {res}")

        subject = f"🚀 خطوة واحدة لتشغيل بوت EGX BOTS داخل جروبك (كود التفعيل: {code})"
        body_html = f"""
        <p>أهلاً بك <strong>{b['name']}</strong>،</p>
        <p>لاحظنا أنك أنشأت رخصة <strong>بوت الجروبات التجريبية (B2B Pro)</strong>، ولكن لم يتم ربط البوت بمجموعتك على تليجرام حتى الآن.</p>
        <p>🎁 <strong>خبر سار:</strong> قمنا بتجديد فترة التجربة المجانية لحسابك لمدة <strong>3 أيام كاملة تبدأ من اليوم</strong> حتى تتمكن من تجربته مع أعضائك.</p>
        <div style="background:#27272a;padding:16px;border-radius:8px;margin:16px 0;border-right:4px solid #10b981;">
          <div style="font-weight:900;color:#10b981;margin-bottom:8px;">خطوات التشغيل في 10 ثوانٍ:</div>
          <div>1. اضغط على الزر الأخضر بالأسفل لاختيار جروبك على تليجرام وإضافة البوت <code>@egxbots_bot</code> كمشرف (Admin).</div>
          <div style="margin-top:6px;">2. سيتفعل البوت تلقائياً، أو يمكنك كتابة هذا الأمر داخل الجروب:</div>
          <div style="margin-top:8px;font-family:monospace;font-size:16px;background:#09090b;padding:8px 12px;border-radius:6px;color:#fbbf24;text-align:center;" dir="ltr">/activate {code}</div>
        </div>
        """
        html = build_email_html(
            user_id=uid,
            email=email,
            badge="🤖 تفعيل رخصة جروب التليجرام (B2B)",
            headline="فعّل البوت داخل مجموعتك الآن بضغطة واحدة!",
            body_html=body_html,
            cta_text="🚀 ربط وتفعيل البوت في جروبي الآن",
            cta_url=connect_url,
            secondary_text="فتح لوحة تحكم B2B وتعديل توقيع القناة",
            secondary_url=dashboard_url,
        )
        meta: Dict[str, Any] = {}
        if send_resend_email(email, subject, html, out=meta):
            email_sent += 1
            record_marketing_message(
                user_id=uid,
                email=email,
                message_type="b2b_unlinked_group_activation_2026_11_18",
                metadata={"short_code": code, "resend_id": meta.get("id")},
                provider_message_id=meta.get("id"),
            )
            print(f"  [B2B EMAIL] ✅ Sent to {email} ({meta.get('id')})")
        else:
            email_failed += 1
            print(f"  [B2B EMAIL] ❌ Failed to {email}")
        time.sleep(0.35)

    print("\n=== 2. DISPATCHING CHURNED PRO RENEWAL WIN-BACK (10 USERS) ===")
    for u in churned_pro_targets:
        uid = u["user_id"]
        email = u["email"]
        tg_id = u["telegram_chat_id"]
        pricing_url = f"{APP_URL}/pricing?plan=pro"

        if tg_id:
            tg_msg = (
                "أهلاً بك في <b>EGX BOTS</b> 👋\n\n"
                "بصفتك من مشتركينا السابقين في باقة <b>PRO</b>، يسعدنا إبلاغك بإضافة تحديثات قوية للمنصة تشمل:\n"
                "• شارتات لحظية وتاريخية تفاعلية ومستويات دعوم ومقاومات دقيقة.\n"
                "• كاشف التجميع والمصائد السعرية والتنبيهات الآلية.\n"
                "• 350 استفسار شهرياً في الشات الذكي بدون تأخير الإشارات.\n\n"
                "👇 يمكنك تجديد اشتراكك الآن بسهولة وأمان عبر صفحة الاشتراكات الرسمية:"
            )
            tg_kb = {
                "inline_keyboard": [
                    [{"text": "💎 تجديد اشتراك PRO الآن", "url": pricing_url}],
                ]
            }
            res = send_telegram(tg_id, tg_msg, reply_markup=tg_kb)
            if res.get("ok"):
                tg_sent += 1
            else:
                tg_failed += 1

        if not is_user_unsubscribed(uid, email):
            subject = "💎 دعوة خاصة لمشتركي PRO السابقين: تحديثات جديدة بانتظارك على EGX BOTS"
            body_html = """
            <p>أهلاً بك يا صديقي،</p>
            <p>شكراً لثقتك السابقة في باقة <strong>PRO</strong> على منصة EGX BOTS. منذ انتهاء اشتراكك الأخير، أضفنا مجموعة من أقوى أدوات التحليل اللحظي لمساعدتك في اقتناص الفرص بدقة:</p>
            <ul style="padding-right:18px;line-height:1.9;">
              <li><strong>الشارتات ومستويات التداول اللحظية:</strong> نقاط الدخول، وقف الخسارة، والأهداف السعرية بدون تأخير الـ 15 يوماً.</li>
              <li><strong>رادار التجميع والمصائد السعرية:</strong> كشف السيولة الذكية قبل التحرك.</li>
              <li><strong>كوتة شات PRO (350 سؤال شهرياً):</strong> متابعة مستمرة لأسهم محفظتك والقيمة العادلة.</li>
            </ul>
            <p>يمكنك استعادة كافة صلاحيات حسابك PRO فوراً عبر بوابة الدفع الرسمية على الموقع:</p>
            """
            html = build_email_html(
                user_id=uid,
                email=email,
                badge="💎 عرض تجديد باقة PRO",
                headline="استعد صلاحيات حسابك PRO الكاملة اليوم",
                body_html=body_html,
                cta_text="⚡ تجديد اشتراك PRO الآن",
                cta_url=pricing_url,
            )
            meta = {}
            if send_resend_email(email, subject, html, out=meta):
                email_sent += 1
                record_marketing_message(
                    user_id=uid,
                    email=email,
                    message_type="pro_winback_renewal_2026_11_18",
                    metadata={"resend_id": meta.get("id")},
                    provider_message_id=meta.get("id"),
                )
                print(f"  [WINBACK EMAIL] ✅ Sent to {email}")
            else:
                email_failed += 1
            time.sleep(0.35)

    print("\n=== 3. DISPATCHING ABANDONED CHECKOUT RECOVERY (6 USERS) ===")
    for u in abandoned_targets:
        uid = u["user_id"]
        email = u["email"]
        plan_id = u["plan_id"]
        pricing_url = f"{APP_URL}/pricing?plan={plan_id}"
        if not is_user_unsubscribed(uid, email):
            subject = "🔓 خطوتك الأخيرة لإتمام تفعيل باقة PRO على EGX BOTS"
            body_html = """
            <p>أهلاً بك،</p>
            <p>لاحظنا أنك بدأت خطوة الترقية إلى باقة <strong>PRO</strong> على منصة EGX BOTS ولكن لم تكتمل عملية الدفع النهائية.</p>
            <p>سواء كنت ترغب في إتمام تفعيل الباقة عبر بوابة الدفع الرسمية (بطاقات بنكية أو محافظ إلكترونية عبر EasyKash)، أو رغبت في <strong>تفعيل تجربة الـ 3 أيام المجانية</strong> أولاً بدون بطاقة، يمكنك المتابعة مباشرة من الرابط التالي:</p>
            """
            html = build_email_html(
                user_id=uid,
                email=email,
                badge="🔓 استكمال تفعيل حسابك",
                headline="أكمل تفعيل باقة PRO أو ابدأ تجربتك المجانية",
                body_html=body_html,
                cta_text="🚀 استكمال التفعيل من صفحة الأسعار",
                cta_url=pricing_url,
            )
            meta = {}
            if send_resend_email(email, subject, html, out=meta):
                email_sent += 1
                record_marketing_message(
                    user_id=uid,
                    email=email,
                    message_type="abandoned_checkout_recovery_2026_11_18",
                    metadata={"plan_id": plan_id, "resend_id": meta.get("id")},
                    provider_message_id=meta.get("id"),
                )
                print(f"  [ABANDONED EMAIL] ✅ Sent to {email}")
            else:
                email_failed += 1
            time.sleep(0.35)

    print("\n=== 4. DISPATCHING 3-DAY FREE TRIAL INVITE TO POWER FREE USERS (15 USERS) ===")
    for u in power_free_targets:
        uid = u["user_id"]
        email = u["email"]
        tg_id = u["telegram_chat_id"]
        q_count = u["q_count"]
        trial_url = f"{APP_URL}/pricing"

        if tg_id:
            tg_msg = (
                f"أهلاً بك في <b>EGX BOTS</b> 👋\n\n"
                f"لاحظنا تفاعلك القوي مع المساعد الذكي ({q_count} استفسارات مؤخراً)، ولكنك لم تفعّل بعد <b>هدية التجربة المجانية لباقة PRO لمدة 3 أيام</b> المتاحة لحسابك!\n\n"
                "🎁 <b>مزايا التجربة المجانية (بدون بطاقة بنكية):</b>\n"
                "• فتح التوصيات والإشارات اليومية بدون تأخير 15 يوماً.\n"
                "• فتح كوتة الشات الذكي وكاشف التجميع والمصائد.\n"
                "• متابعة حتى 15 سهماً في محفظتك.\n\n"
                "👇 فعّل تجربتك المجانية الآن بضغطة واحدة:"
            )
            tg_kb = {
                "inline_keyboard": [
                    [{"text": "🎁 تفعيل تجربة PRO المجانية (3 أيام)", "url": trial_url}],
                ]
            }
            res = send_telegram(tg_id, tg_msg, reply_markup=tg_kb)
            if res.get("ok"):
                tg_sent += 1
            else:
                tg_failed += 1

        if not is_user_unsubscribed(uid, email):
            subject = "🎁 لديك تجربة PRO مجانية (3 أيام) غير مفعّلة في حسابك على EGX BOTS!"
            body_html = f"""
            <p>أهلاً بك،</p>
            <p>يسعدنا تواجدك النشط على <strong>EGX BOTS</strong> وطرحك <strong>{q_count} استفسارات</strong> في الشات الذكي مؤخراً.</p>
            <p>هل تعلم أن حسابك مؤهل لتفعيل <strong>تجربة باقة PRO مجاناً لمدة 3 أيام كاملة (بدون أي بطاقة بنكية)</strong>؟</p>
            <ul style="padding-right:18px;line-height:1.9;">
              <li>فتح الإشارات والتوصيات اليومية اللحظية (إلغاء تأخير الـ 15 يوماً).</li>
              <li>فتح كوتة إضافية في الشات الذكي لتحليل أسهمك ومستويات الدخول.</li>
              <li>الوصول الكامل لرادار التجميع وحاسبة القيمة العادلة.</li>
            </ul>
            """
            html = build_email_html(
                user_id=uid,
                email=email,
                badge="🎁 هدية مفعّلة لحسابك (3 أيام مجاناً)",
                headline="فعّل تجربة PRO المجانية بضغطة واحدة الآن",
                body_html=body_html,
                cta_text="🎁 تفعيل تجربة 3 أيام مجاناً الآن",
                cta_url=trial_url,
            )
            meta = {}
            if send_resend_email(email, subject, html, out=meta):
                email_sent += 1
                record_marketing_message(
                    user_id=uid,
                    email=email,
                    message_type="power_free_trial_invite_2026_11_18",
                    metadata={"q_count": q_count, "resend_id": meta.get("id")},
                    provider_message_id=meta.get("id"),
                )
                print(f"  [POWER FREE EMAIL] ✅ Sent to {email}")
            else:
                email_failed += 1
            time.sleep(0.35)

    print("\n" + "=" * 60)
    print(f"SUMMARY: Emails sent={email_sent} (failed={email_failed}) | Telegram DMs sent={tg_sent} (failed={tg_failed})")
    print("=" * 60)
    time.sleep(2)
    analyze_campaign()


if __name__ == "__main__":
    main()
