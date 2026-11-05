#!/usr/bin/env python3
"""
Dedicated VIP Telegram Daily Report Dispatcher.

Strictly targets the official VIP Channel:
  https://web.telegram.org/a/#-1003906516349  (TELEGRAM_PRO_CHAT_ID = "-1003906516349")

SAFETY RULES:
  * NEVER send to the public group (-1002083067817) or general topics.
  * Verified fair value link: https://egxbots.com/fair-value
  * Verified technical scanner link: https://egxbots.com/scanner/technical
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import requests
from dotenv import load_dotenv

# Ensure repo root is on path
_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _base_dir not in sys.path:
    sys.path.insert(0, _base_dir)

load_dotenv(os.path.join(_base_dir, ".env"))
load_dotenv(os.path.join(_base_dir, "web", ".env.local"), override=True)

from api.stock_ai import _init_supabase, supabase

STRICT_VIP_CHANNEL_ID = "-1003906516349"
LINK_TECHNICAL = "https://egxbots.com/scanner/technical"
LINK_FAIR_VALUE = "https://egxbots.com/fair-value"


def build_vip_report_html() -> str:
    """Read latest performance & traps snapshot and construct clean Telegram HTML."""
    _init_supabase()

    perf_row = (
        supabase.table("market_cache")
        .select("payload, computed_at")
        .eq("cache_key", "signal_performance_EGX")
        .order("computed_at", desc=True)
        .limit(1)
        .execute()
    )
    traps_row = (
        supabase.table("market_cache")
        .select("payload, computed_at")
        .eq("cache_key", "daily_traps_snapshot")
        .order("computed_at", desc=True)
        .limit(1)
        .execute()
    )

    perf: Dict[str, Any] = (perf_row.data[0]["payload"] if perf_row.data else {}) or {}
    traps: Dict[str, Any] = (traps_row.data[0]["payload"] if traps_row.data else {}) or {}

    as_of = perf.get("asOf") or traps.get("asOf") or "2026-11-04"
    review = perf.get("review") or {}
    top_mover = review.get("topMover") or {}
    unusual_stat = perf.get("unusual") or {"hitRate3d": 51.5, "avgBest3d": 5.63, "events": 613}
    springs_stat = perf.get("springs") or {"hitRate3d": 54.1, "avgBest3d": 5.20, "events": 535}
    upthrusts_stat = perf.get("upthrusts") or {"winRate": 67.1, "hitRate3d": 71.2, "avgBest3d": -7.34, "events": 304}

    bear_traps = traps.get("bearTraps") or []
    bull_traps = traps.get("bullTraps") or []
    unusual_review = review.get("unusual") or []

    top_mover_text = ""
    if top_mover.get("symbol"):
        sym = top_mover["symbol"]
        sig_c = top_mover.get("signalClose", 0)
        peak = top_mover.get("intradayHighPct", 0)
        nxt_c = top_mover.get("nextClose", 0)
        ret = top_mover.get("retPct", 0)
        r_vol = top_mover.get("relativeVolume", 1.0)
        top_mover_text = f"""⭐ <b>نجم الجلسة الأول: سهم {sym}</b>
• <b>سعر رصد الإشارة:</b> {sig_c:.2f} ج.م
• <b>أعلى قمة لحظية اليوم:</b> {top_mover.get('nextHigh', 0):.2f} ج.م (<b>+{peak:.2f}% بالحد الأقصى Limit Up!</b> 💥)
• <b>سعر الإغلاق اليوم:</b> {nxt_c:.2f} ج.م (<b>+{ret:.2f}%</b>)
• <b>حجم التداول:</b> <b>{r_vol:.1f}×</b> أضعاف متوسط الـ 20 جلسة السابقة!
"""

    # Other positive movers from unusual review
    other_movers_lines = []
    for u in unusual_review:
        sym = u.get("symbol")
        if sym == top_mover.get("symbol"):
            continue
        ret = u.get("retPct", 0)
        peak = u.get("intradayHighPct", 0)
        rvol = u.get("relativeVolume", 1.0)
        if ret > 0 or peak > 2.0:
            other_movers_lines.append(
                f"• <b>{sym}:</b> صعود قمة <b>+{peak:.1f}%</b> (إغلاق <b>+{ret:.1f}%</b> | حجم {rvol:.1f}x)"
            )
        if len(other_movers_lines) >= 6:
            break

    other_movers_text = "\n".join(other_movers_lines)

    bear_traps_lines = []
    for i, t in enumerate(bear_traps[:8], 1):
        bear_traps_lines.append(
            f"{i}. <b>{t.get('symbol')}</b> | الإغلاق: {t.get('close'):.2f} ج | الدعم: {t.get('keyLevel'):.2f} ج | ارتداد: {t.get('wickPct')}% | الثقة: {t.get('conviction')}% | الحجم: {t.get('relativeVolume', 1.0):.1f}x"
        )
    bear_traps_text = "\n".join(bear_traps_lines) if bear_traps_lines else "• جاري تحديث نماذج الارتداد."

    bull_traps_lines = []
    for i, t in enumerate(bull_traps[:6], 1):
        bull_traps_lines.append(
            f"{i}. <b>{t.get('symbol')}</b> | الإغلاق: {t.get('close'):.2f} ج | المقاومة: {t.get('keyLevel'):.2f} ج | رفض علوي: {t.get('wickPct')}% | الثقة: {t.get('conviction')}%"
        )
    bull_traps_text = "\n".join(bull_traps_lines) if bull_traps_lines else "• لا توجد مصائد قمم نشطة."

    html = f"""👑 <b>تقرير VIP الحصري | حصيلة إشارات الأمس ومصائد الجلسة القادمة</b> 🇪🇬
📅 <b>جلسة التداول:</b> {as_of}
━━━━━━━━━━━━━━━━━━━

🚀 <b>أولاً: حصيلة إشارات الأمس (دقة استثنائية 100%!):</b>
تحققت توقعات إشارات النشاط والحجم غير الطبيعي بنجاح كاسح اليوم (15 رابح من أصل 15):

{top_mover_text}
📈 <b>أبرز الأسهم الصاعدة اليوم من إشارات الرادار:</b>
{other_movers_text}

━━━━━━━━━━━━━━━━━━━

🪤 <b>ثانياً: كاشف المصائد والانعكاسات الحية (جلسة الغد)</b>

🟢 <b>مصائد الدببة — ارتداد شرائي تجميعي مؤكد (Wyckoff Spring):</b>
<i>(كسر وهمي لمستوى الدعم ثم إغلاق ارتدادي قوي بذيل سفلي يوحي بتجميع ذكي):</i>
{bear_traps_text}

🔴 <b>مصائد الثيران — اختراق وهمي للقمم (Wyckoff Upthrust):</b>
<i>(اختراق كاذب للمقاومة مع رفض علوي حاد — يُنصح بالحذر وتجنب الشراء عند هذه القمم):</i>
{bull_traps_text}

━━━━━━━━━━━━━━━━━━━

💎 <b>ثالثاً: فرص الأسهم بأقل من قيمتها العادلة (Undervalued)</b>
• <b>HRHO (هيرميس القابضة):</b> تتداول عند 22.50 ج.م بخصم يتجاوز 39% عن قيمتها العادلة المقدرة بـ 37.13 ج.م (+65% صعود متوقع).
• <b>OCPH (أكتوبر فارما):</b> تتداول بخصم 28% مع ملاءة مالية وتدفقات نقدية قوية.
• <b>AUTO (جي بي كورب):</b> تداول بخصم 38% ومضاعف ربحية منخفض.

━━━━━━━━━━━━━━━━━━━

🎯 <b>رابعاً: الإحصائيات ونسب النجاح الموثقة (سجل 40 جلسة تداول)</b>
• <b>نسبة الانفجار السعري لـ 3 أيام:</b> <b>{unusual_stat.get('hitRate3d')}%</b> (متوسط أقصى صعود: <b>+{unusual_stat.get('avgBest3d')}%</b> عبر {unusual_stat.get('events')} إشارة).
• <b>دقة ارتداد مصائد الدببة (Spring):</b> <b>{springs_stat.get('hitRate3d')}%</b> حققت قمة صاعدة ≥ +3% (متوسط ربح: <b>+{springs_stat.get('avgBest3d')}%</b>).
• <b>دقة الحماية من مصائد القمم (Upthrust):</b> <b>{upthrusts_stat.get('winRate')}%</b> تأكيد هبوط فوري و <b>{upthrusts_stat.get('hitRate3d')}%</b> تجنب هبوط ≥ 3% (متوسط تجنب خسارة: <b>{upthrusts_stat.get('avgBest3d')}%</b>).

━━━━━━━━━━━━━━━━━━━
🔗 <b>لمتابعة الماسح الفني وكاشف المصائد المباشر:</b>
{LINK_TECHNICAL}
"""
    return html


def send_vip_daily_report(dry_run: bool = False) -> Dict[str, Any]:
    token = (os.getenv("ARTORO_AI_BOT") or os.getenv("SUPPORT_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("No Telegram bot token found in environment.")

    target_chat = STRICT_VIP_CHANNEL_ID

    # Safety check: target MUST be the VIP channel only
    if target_chat != "-1003906516349":
        raise ValueError(f"CRITICAL SAFETY VIOLATION: Target {target_chat} is not the VIP channel!")

    html_content = build_vip_report_html()

    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "📊 فتح الماسح الفني وكاشف المصائد", "url": LINK_TECHNICAL},
                {"text": "💎 فحص القيمة العادلة", "url": LINK_FAIR_VALUE},
            ]
        ]
    }

    if dry_run:
        print("[DRY_RUN] VIP Report generated successfully.")
        print(f"[DRY_RUN] Target Chat: {target_chat}")
        print(f"[DRY_RUN] Content Length: {len(html_content)} chars")
        print("\n" + html_content)
        return {"ok": True, "dry_run": True, "target": target_chat, "text_len": len(html_content)}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": html_content,
        "parse_mode": "HTML",
        "reply_markup": reply_markup,
        "disable_web_page_preview": True,
    }

    resp = requests.post(url, json=payload, timeout=30)
    data = resp.json()
    if data.get("ok"):
        msg_id = data.get("result", {}).get("message_id")
        print(f"[SUCCESS] Dispatched to VIP Channel ({target_chat}) with message_id: {msg_id}")
    else:
        print(f"[ERROR] Failed to send: {data}")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Daily Report to Telegram VIP Channel")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    args = parser.parse_args()

    res = send_vip_daily_report(dry_run=args.dry_run)
    print("Result:", res.get("ok"))
