"""
jobs/analyze_email_campaign.py — Real-time Resend Email Analytics & Engagement Tracker.
Fetches live event metrics (delivered, opened, clicked, bounced) directly from Resend API.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding="utf-8")

from api.marketing_lifecycle import RESEND_API_KEY


def fetch_resend_emails(limit: int = 100) -> List[Dict[str, Any]]:
    """Fetches recently sent emails with their real-time last_event from Resend."""
    if not RESEND_API_KEY:
        print("[ERROR] Missing RESEND_API_KEY")
        return []

    url = f"https://api.resend.com/emails?limit={limit}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "User-Agent": "EGXBots-Marketing/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("data", [])
    except Exception as e:
        print(f"[ERROR] Failed to fetch emails from Resend: {e}")
        return []


def analyze_campaign() -> Dict[str, Any]:
    """Analyzes email engagement status and prints formatted breakdown."""
    emails = fetch_resend_emails(limit=100)
    total = len(emails)

    counter = Counter(e.get("last_event", "unknown") for e in emails)
    opened = [e for e in emails if e.get("last_event") in ["opened", "clicked"]]
    clicked = [e for e in emails if e.get("last_event") == "clicked"]
    bounced = [e for e in emails if e.get("last_event") in ["bounced", "complained"]]
    delivered = [e for e in emails if e.get("last_event") == "delivered"]

    open_rate = (len(opened) / total * 100) if total > 0 else 0
    click_rate = (len(clicked) / total * 100) if total > 0 else 0

    print("==================================================")
    print(" 📊 تقرير التحليل اللحظي لحملات البريد الإلكتروني (Resend)")
    print("==================================================")
    print(f"🔹 إجمالي الرسائل المسجلة: {total}")
    for event, count in counter.items():
        pct = (count / total * 100) if total > 0 else 0
        print(f"   • {event}: {count} ({pct:.1f}%)")
    print("--------------------------------------------------")
    print(f"📈 نسبة الفتح (Open Rate):  {open_rate:.1f}% ({len(opened)} مستخدم)")
    print(f"🎯 نسبة النقر (Click Rate): {click_rate:.1f}% ({len(clicked)} مستخدم)")
    print("--------------------------------------------------")

    if opened:
        print("👀 المستخدمون الذين فتحوا الإيميل:")
        for e in opened:
            to_addr = e.get("to", ["N/A"])[0]
            created = e.get("created_at", "")[:19]
            print(f"   ✓ {to_addr} | الحالة: {e.get('last_event')} | التوقيت: {created}")
    else:
        print("ℹ️ لم يتم تسجيل فتح أي إيميل حتى اللحظة (طبيعي لأن الدفعة أُرسلت قبل دقائق قليلة).")

    if clicked:
        print("\n⚡ المستخدمون الذين نقروا على الروابط:")
        for e in clicked:
            to_addr = e.get("to", ["N/A"])[0]
            print(f"   ★ {to_addr} | نقر على رابط الاشتراك!")

    print("==================================================")

    return {
        "total": total,
        "counts": dict(counter),
        "open_rate": round(open_rate, 2),
        "click_rate": round(click_rate, 2),
        "opened_recipients": [e.get("to", [""])[0] for e in opened],
        "clicked_recipients": [e.get("to", [""])[0] for e in clicked],
    }


if __name__ == "__main__":
    analyze_campaign()
