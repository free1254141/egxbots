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


def fetch_resend_emails(max_emails: int = 500) -> List[Dict[str, Any]]:
    """Fetches all sent emails with real-time events from Resend using pagination."""
    if not RESEND_API_KEY:
        print("[ERROR] Missing RESEND_API_KEY")
        return []

    all_emails: List[Dict[str, Any]] = []
    after: str | None = None

    while len(all_emails) < max_emails:
        url = "https://api.resend.com/emails?limit=100" + (f"&after={after}" if after else "")
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
                items = data.get("data", [])
                if not items:
                    break
                all_emails.extend(items)
                if not data.get("has_more") or len(items) < 100:
                    break
                after = items[-1]["id"]
        except Exception as e:
            print(f"[ERROR] Failed to fetch emails from Resend: {e}")
            break

    return all_emails


def analyze_campaign() -> Dict[str, Any]:
    """Analyzes email engagement status and prints formatted breakdown."""
    emails = fetch_resend_emails(max_emails=500)
    total = len(emails)

    counter = Counter(e.get("last_event", "unknown") for e in emails)
    opened = [e for e in emails if e.get("last_event") in ["opened", "clicked"]]
    clicked = [e for e in emails if e.get("last_event") == "clicked"]
    bounced = [e for e in emails if e.get("last_event") in ["bounced", "complained"]]
    delivered = [e for e in emails if e.get("last_event") == "delivered"]

    open_rate = (len(opened) / total * 100) if total > 0 else 0
    click_rate = (len(clicked) / total * 100) if total > 0 else 0

    # Today's vs Previous days breakdown (UTC date)
    now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_emails = [e for e in emails if (e.get("created_at") or "").startswith(now_utc_str)]
    today_opened = [e for e in today_emails if e.get("last_event") in ["opened", "clicked"]]

    print("==================================================")
    print(" 📊 تقرير التحليل الشامل والتراكمي لحملات البريد الإلكتروني")
    print("==================================================")
    print(f"🔹 إجمالي الرسائل التراكمية في Resend: {total}")
    for event, count in counter.items():
        pct = (count / total * 100) if total > 0 else 0
        print(f"   • {event}: {count} ({pct:.1f}%)")
    print("--------------------------------------------------")
    print(f"📈 نسبة الفتح الكلية (Overall Open Rate):  {open_rate:.1f}% ({len(opened)} مستخدم)")
    print(f"🎯 نسبة النقر الكلية (Overall Click Rate): {click_rate:.1f}% ({len(clicked)} مستخدم)")
    print("--------------------------------------------------")
    print(f"📅 إحصائيات دفعة اليوم ({now_utc_str}):")
    print(f"   • عدد المرسل اليوم: {len(today_emails)} إيميل")
    print(f"   • فتحوا رسائل اليوم حتى اللحظة: {len(today_opened)} مستخدم ({((len(today_opened)/len(today_emails)*100) if today_emails else 0):.1f}%)")
    print("--------------------------------------------------")

    if opened:
        print(f"👀 قائمة المستخدمين الذين فتحوا الإيميل ({len(opened)} مستخدم):")
        for e in opened:
            to_addr = e.get("to", ["N/A"])[0]
            created = e.get("created_at", "")[:19].replace("T", " ")
            is_today = " [دفعة اليوم⚡]" if created.startswith(now_utc_str) else ""
            print(f"   ✓ {to_addr}{is_today} | الحالة: {e.get('last_event')} | وقت الإرسال: {created}")
    else:
        print("ℹ️ لم يتم تسجيل فتح أي إيميل حتى اللحظة.")

    if clicked:
        print("\n⚡ المستخدمون الذين نقروا على الروابط:")
        for e in clicked:
            to_addr = e.get("to", ["N/A"])[0]
            print(f"   ★ {to_addr} | نقر على رابط الاشتراك وقام بالدفع!")

    print("==================================================")

    return {
        "total": total,
        "counts": dict(counter),
        "open_rate": round(open_rate, 2),
        "click_rate": round(click_rate, 2),
        "today_total": len(today_emails),
        "today_opened": len(today_opened),
        "opened_recipients": [e.get("to", [""])[0] for e in opened],
        "clicked_recipients": [e.get("to", [""])[0] for e in clicked],
    }


if __name__ == "__main__":
    analyze_campaign()
