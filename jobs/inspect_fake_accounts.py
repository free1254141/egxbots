"""
jobs/inspect_fake_accounts.py — Analyzes all 529 registered users to detect fake/test/disposable accounts.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding="utf-8")

from api.stock_ai import supabase

DISPOSABLE_DOMAINS = {
    "tempmail.com", "guerrillamail.com", "10minutemail.com", "mailinator.com",
    "throwawaymail.com", "yopmail.com", "sharklasers.com", "trashmail.com",
    "getairmail.com", "mohmal.com", "fakemailgenerator.com", "temp-mail.org",
    "burnermail.io", "dispostable.com", "mytemp.email", "crazymailing.com",
    "duck.com", "inboxkitten.com", "maildrop.cc", "tempail.com", "tempmail.net",
    "emailondeck.com", "10minutemail.net", "dropmail.me"
}

MAJOR_PROVIDERS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
    "live.com", "msn.com", "aol.com", "protonmail.com", "proton.me"
}


def is_gibberish(local_part: str) -> bool:
    """Detects random keyboard mash like ghgfhgfh, asdfgh, etc."""
    s = local_part.lower().split("+")[0]
    # Strip numbers at end
    s_chars = re.sub(r"\d+", "", s)
    if len(s_chars) >= 6:
        # Same 3-4 chars repeated randomly e.g. ghgfhgfh, asdfasd
        unique_chars = len(set(s_chars))
        if unique_chars <= 4:
            return True
        # Typical keyboard rows mashes
        mashes = ["asdf", "hjkl", "ghgf", "zxcv", "qwer", "poiuy", "12345"]
        for m in mashes:
            if m in s_chars and len(s_chars) <= 10:
                return True
    return False


def run_analysis():
    # 1. Fetch all auth users
    page = 1
    per_page = 100
    all_users = []
    while True:
        resp = supabase.auth.admin.list_users(page=page, per_page=per_page)
        users = resp.users if hasattr(resp, "users") else (resp if isinstance(resp, list) else [])
        if not users:
            break
        all_users.extend(users)
        if len(users) < per_page:
            break
        page += 1

    total = len(all_users)
    print(f"Total accounts analyzed: {total}")

    # Fetch all profiles for display names and chat_ids
    prof_res = supabase.table("profiles").select("id, display_name, username, telegram_chat_id, whatsapp_number, cash_balance").execute()
    prof_map = {p["id"]: p for p in (prof_res.data or [])}

    # Categories
    disposable_users = []
    gibberish_users = []
    never_logged_in = []
    unconfirmed_emails = []
    active_users = []
    providers_counter = Counter()

    for u in all_users:
        uid = str(getattr(u, "id", None) or (u.get("id") if isinstance(u, dict) else None))
        email = str(getattr(u, "email", None) or (u.get("email") if isinstance(u, dict) else "") or "").strip().lower()
        confirmed_at = getattr(u, "email_confirmed_at", None) or (u.get("email_confirmed_at") if isinstance(u, dict) else None)
        last_sign_in = getattr(u, "last_sign_in_at", None) or (u.get("last_sign_in_at") if isinstance(u, dict) else None)
        created_at = str(getattr(u, "created_at", None) or (u.get("created_at") if isinstance(u, dict) else "") or "")

        prof = prof_map.get(uid, {})
        dname = prof.get("display_name") or prof.get("username") or ""
        tg_id = prof.get("telegram_chat_id")
        wa = prof.get("whatsapp_number")

        domain = email.split("@")[1] if "@" in email else "unknown"
        local_part = email.split("@")[0] if "@" in email else email
        providers_counter[domain] += 1

        is_fake = False
        reasons = []

        # Check disposable domain
        if domain in DISPOSABLE_DOMAINS:
            is_fake = True
            reasons.append(f"بريد مؤقت ({domain})")
            disposable_users.append((email, uid, reasons, created_at))

        # Check gibberish
        if is_gibberish(local_part):
            is_fake = True
            reasons.append("اسم عشوائي كيبورد (Gibberish)")
            gibberish_users.append((email, uid, reasons, created_at))

        # Check never confirmed or never signed in
        if not last_sign_in:
            never_logged_in.append((email, uid, created_at))

        if not confirmed_at:
            unconfirmed_emails.append((email, uid, created_at))

        # If has telegram or phone or logged in, they are definitely real
        if tg_id or wa or (last_sign_in and confirmed_at and not is_fake):
            active_users.append((email, uid, dname, tg_id, wa, last_sign_in))

    print("\n=======================================================")
    print(" 📊 تصنيف وتحليل جودة حسابات المستخدمين (529 مستخدم)")
    print("=======================================================")
    print(f"🔹 إجمالي الحسابات المسجلة: {total}")
    print(f"✅ حسابات حقيقية مؤكدة وتفاعلت: {len(active_users)} ({len(active_users)/total*100:.1f}%)")
    print(f"⚠️ حسابات بإيميلات مؤقتة (Disposable): {len(disposable_users)}")
    print(f"⚠️ حسابات بحروف كيبورد عشوائية (Gibberish): {len(gibberish_users)}")
    print(f"💤 حسابات سجلت ولم تسجل دخول مطلقاً (Never Logged In): {len(never_logged_in)}")
    print(f"📩 حسابات لم تؤكد بريدها (Unconfirmed): {len(unconfirmed_emails)}")
    print("-------------------------------------------------------")

    print("\n🏢 توزيع مزودي البريد الإلكتروني (Top Providers):")
    for prov, count in providers_counter.most_common(10):
        print(f"   • {prov}: {count} مستخدم ({count/total*100:.1f}%)")

    print("\n🚨 تفاصيل الحسابات الوهمية أو المؤقتة المكتشفة:")
    all_flagged = {}
    for em, uid, r, cr in disposable_users + gibberish_users:
        all_flagged[em] = {"reasons": r, "created_at": cr[:10]}

    print(f"إجمالي الحسابات المشبوهة/الوهمية: {len(all_flagged)} حساب")
    for em, info in all_flagged.items():
        print(f"   • {em} | الأسباب: {', '.join(info['reasons'])} | تاريخ التسجيل: {info['created_at']}")

    print("=======================================================")


if __name__ == "__main__":
    run_analysis()
