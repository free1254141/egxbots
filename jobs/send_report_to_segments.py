"""
jobs/send_report_to_segments.py — sends the same market report to the three
non-converting segments (expired trial / active free / dormant-but-used).

Reuses the report builder from the 2026-11-06 campaign so the content stays
identical to what was sent last week. Dry run by default.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

ROOT_DIR = r"C:/Users/MR__CODER__/Desktop/stokscan_AI"
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))
os.environ.setdefault("REPORT_FAIR_VALUE_URL", "https://egxbots.com/api/market/fair-value")

SPEC = importlib.util.spec_from_file_location(
    "promo_report_20261106",
    os.path.join(ROOT_DIR, "jobs", "send_active_free_promo_report_2026_11_06.py"),
)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)

from api.stock_ai import supabase
from api.marketing_lifecycle import (
    MARKETING_DAILY_EMAIL_CAP,
    get_daily_sent_count,
    get_user_email,
    is_user_unsubscribed,
    record_marketing_message,
    send_resend_email,
)

CAMPAIGN = "weekly_report_segments_2026_11_06"
PAID_PLANS = {"pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime"}
BAD_MARKERS = ("example.", "example.invalid", "test", "fake", "bgugvbhchj")
SEGMENT_ORDER = {"expired_trial": 0, "active_free": 1, "dormant_engaged": 2}
LABELS = {
    "expired_trial": "تجربة منتهية",
    "active_free": "نشط Free",
    "dormant_engaged": "خامل لكن استخدم قبل كده",
}


def build_segments() -> list[dict]:
    now = datetime.now(timezone.utc)
    week = (now - timedelta(days=7)).isoformat()
    h48 = (now - timedelta(hours=48)).isoformat()
    cutoff14 = (now - timedelta(days=14)).isoformat()
    cutoff90 = (now - timedelta(days=90)).isoformat()

    profiles = (supabase.table("profiles").select("id,created_at").limit(2000).execute().data or [])
    subs = (supabase.table("subscriptions").select("user_id,plan_id,status").limit(5000).execute().data or [])
    trials = (supabase.table("subscription_trials").select("user_id,expires_at").limit(5000).execute().data or [])
    prefs = (supabase.table("marketing_preferences").select("user_id,unsubscribed_all").limit(5000).execute().data or [])
    logs48 = (supabase.table("marketing_message_log").select("user_id")
              .gte("sent_at", h48).limit(5000).execute().data or [])
    logs7 = (supabase.table("marketing_message_log").select("user_id")
             .gte("sent_at", week).limit(5000).execute().data or [])
    sent_before = (supabase.table("marketing_message_log").select("user_id")
                   .eq("message_type", CAMPAIGN).limit(5000).execute().data or [])
    chats = (supabase.table("ai_chat_messages").select("user_id,created_at")
             .eq("role", "user").gte("created_at", cutoff90).limit(10000).execute().data or [])
    events = (supabase.table("user_activity_events").select("user_id,created_at")
              .gte("created_at", cutoff90).limit(10000).execute().data or [])

    paid = {s["user_id"] for s in subs
            if s.get("status") == "active" and s.get("plan_id") in PAID_PLANS}
    unsub = {p["user_id"] for p in prefs if p.get("unsubscribed_all")}
    emailed48 = {r["user_id"] for r in logs48}
    emailed7 = {r["user_id"] for r in logs7}
    already = {r["user_id"] for r in sent_before}
    expired = {t["user_id"] for t in trials if str(t.get("expires_at")) <= now.isoformat()}

    last = defaultdict(str)
    for row in chats + events:
        uid, at = row.get("user_id"), str(row.get("created_at") or "")
        if uid and at > last[uid]:
            last[uid] = at

    eligible = {p["id"] for p in profiles} - paid - unsub - already
    created = {p["id"]: str(p.get("created_at") or "") for p in profiles}

    # Decide the segment by id first, then resolve emails only for the chosen
    # users (avoids hundreds of per-user RPC calls).
    picked = []
    for uid in eligible:
        if uid in expired:
            if uid not in emailed48:
                picked.append((uid, "expired_trial"))
            continue
        if last.get(uid, "") >= cutoff14:
            if uid not in emailed7:
                picked.append((uid, "active_free"))
            continue
        if created.get(uid, "") < cutoff14 and last.get(uid, "") and last[uid] < cutoff14 and uid not in emailed7:
            picked.append((uid, "dormant_engaged"))

    chosen = []
    seen_emails = set()
    for uid, segment in sorted(picked, key=lambda item: SEGMENT_ORDER.get(item[1], 9)):
        email = get_user_email(uid)
        if not email or "@" not in email:
            continue
        lowered = email.lower()
        if lowered in seen_emails or any(marker in lowered for marker in BAD_MARKERS):
            continue
        if is_user_unsubscribed(uid, email):
            continue
        seen_emails.add(lowered)
        chosen.append({"user_id": uid, "email": email, "segment": segment})
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--max", type=int, default=60)
    args = ap.parse_args()

    market = report.load_market()
    fair_value = report.load_fair_value()
    sent_today = get_daily_sent_count()
    remaining = max(0, MARKETING_DAILY_EMAIL_CAP - sent_today)
    targets = build_segments()
    recipients = targets[: min(args.max, remaining)] if remaining else []
    counts = defaultdict(int)
    for r in recipients:
        counts[r["segment"]] += 1

    print(f"=== Weekly report -> segments | as-of {market.get('as_of')} ===")
    print("eligible:", len(targets), dict(Counter(r["segment"] for r in targets)),
          "| sending:", len(recipients), dict(counts),
          "| fair_value:", "loaded" if fair_value else "unavailable")
    print("subject:", report.SUBJECT)
    print("sent_today:", sent_today, "/", MARKETING_DAILY_EMAIL_CAP, "| remaining:", remaining)

    sent = failed = 0
    for index, recipient in enumerate(recipients, 1):
        html = report.build_email_html(market, fair_value, recipient["user_id"], recipient["email"])
        print(f"{index:02d}. [{LABELS[recipient['segment']]}] {recipient['email']}")
        if not args.send:
            continue
        meta: dict = {}
        if send_resend_email(recipient["email"], report.SUBJECT, html, out=meta):
            record_marketing_message(
                recipient["user_id"], recipient["email"], CAMPAIGN,
                {"segment": recipient["segment"], "source": "weekly_report"},
                provider_message_id=meta.get("provider_message_id"),
            )
            sent += 1
        else:
            failed += 1

    print(f"\n{'DISPATCHED' if args.send else 'DRY RUN'}: sent={sent} failed={failed} targets={len(recipients)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
