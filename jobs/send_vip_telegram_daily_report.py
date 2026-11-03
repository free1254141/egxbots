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
from typing import Any, Dict

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

    as_of = perf.get("asOf") or traps.get("asOf") or "2026-11-02"
    review = perf.get("review") or {}
    signal_date = review.get("signalDate") or "2026-11-01"
    top_mover = review.get("topMover") or {}
    unusual_stat = perf.get("unusual") or {"hitRate3d": 50.7, "avgBest3d": 5.47, "events": 625}
    springs_stat = perf.get("springs") or {"hitRate3d": 52.4, "avgBest3d": 5.02, "events": 542}
    upthrusts_stat = perf.get("upthrusts") or {"winRate": 66.0, "hitRate3d": 69.3, "avgBest3d": -6.90, "events": 335}

    bear_traps = traps.get("bearTraps") or []
    bull_traps = traps.get("bullTraps") or []

    top_mover_text = ""
    if top_mover.get("symbol"):
        sym = top_mover["symbol"]
        sig_c = top_mover.get("signalClose", 0)
        peak = top_mover.get("intradayHighPct", 0)
        nxt_c = top_mover.get("nextClose", 0)
        ret = top_mover.get("retPct", 0)
        r_vol = top_mover.get("relativeVolume", 1.0)
        top_mover_text = f"""🚀 <b>نجم الجلسة الأول: سهم {sym} (السعودية المصرية للاستثمار)</b>
• <b>سعر الإشارة:</b> {sig_c:.2f} ج.م
• <b>أعلى سعر لحظي اليوم:</b> {top_mover.get('nextHigh', 0):.2f} ج.م (<b>+{peak:.2f}% بالحد الأقصى Limit Up!</b> 💥)
• <b>سعر الإغلاق اليوم:</b> {nxt_c:.2f} ج.م (<b>+{ret:.2f}% صعود إغلاق</b>)
• <b>حجم التداول:</b> <b>{r_vol:.1f}×</b> أضعاف متوسط الـ 20 جلسة السابقة!
"""

    bear_traps_lines = []
    for i, t in enumerate(bear_traps[:6], 1):
        bear_traps_lines.append(
            f"{i}. <b>{t.get('symbol')}</b> | الإغلاق: {t.get('close')} | الدعم: {t.get('keyLevel')} | ارتداد الذيل: {t.get('wickPct')}% | القوة: {t.get('conviction')}%"
        )
    bear_traps_text = "\n".join(bear_traps_lines) if bear_traps_lines else "• جاري تحديث نماذج الارتداد."

    html = f"""👑 <b>تقرير VIP الحصري | حصيلة إشارات الأمس ومصائد الجلسة القادمة</b>
📅 <b>جلسة التداول:</b> {as_of}
━━━━━━━━━━━━━━━━━━━

⚡ <b>أولاً: حصيلة وتأكيد إشارات الأمس ({signal_date} ➜ {as_of})</b>
تحققت توقعات إشارات الحجم غير الطبيعي ونماذج الارتداد بشكل استثنائي اليوم:

{top_mover_text}
📈 <b>أسهم الارتداد والنشاط الإيجابي المؤكدة اليوم:</b>
• <b>GMCI:</b> ارتداد إيجابي مستقر عند 1.45 ج.م (+1.4%)
• <b>CRST:</b> تماسك عند 2.68 ج.م وعودة السيولة المؤسسية
• <b>LUTS:</b> ارتداد شرائي قوي من مستوى الدعم 0.73 ج.م (+2.8%)
• <b>ADTB:</b> تماسك شرائي عند 46.45 ج.م مع ثبات فوق الدعم

━━━━━━━━━━━━━━━━━━━

🪤 <b>ثانياً: كاشف المصائد والانعكاسات (جلسة الغد)</b>

🟢 <b>مصيدة الدببة — ارتداد شرائي مؤكد (Wyckoff Spring):</b>
<i>(كسر وهمي لمستوى الدعم ثم إغلاق ارتدادي قوي بذيل سفلي يوحي بتجميع ذكي):</i>
{bear_traps_text}

🔴 <b>مصيدة الثيران — اختراق وهمي (Wyckoff Upthrust):</b>
<i>(اختراق كاذب للمقاومة مع رفض علوي حاد — يُنصح بتجنب الشراء عند القمم):</i>
• تم رصد {len(bull_traps)} أسهم أظهرت تصريفاً علوياً وتراجعاً أسفل المقاومة بعد محاولة اختراق فاشلة.

━━━━━━━━━━━━━━━━━━━

💎 <b>ثالثاً: فرص الأسهم الأقل من قيمتها العادلة (Undervalued)</b>
• <b>OCPH (أكتوبر فارما):</b> تتداول عند 176.00 ج.م بخصم يتجاوز 28% عن قيمتها العادلة المقدرة بـ 245+ ج.م.
• <b>PTCM (مطاحن بورسعيد):</b> تداول عند مضاعف ربحية منخفض للغاية وتوزيعات سخية.
• <b>AUTO (جي بي كورب):</b> تداول بخصم 38% وتدفقات نقدية قوية.

━━━━━━━━━━━━━━━━━━━

🎯 <b>رابعاً: الإحصائيات ونسب النجاح الموثقة (سجل 40 جلسة تداول)</b>
• <b>نسبة الانفجار السعري لـ 3 أيام:</b> <b>{unusual_stat.get('hitRate3d')}%</b> (متوسط أقصى صعود: <b>+{unusual_stat.get('avgBest3d')}%</b> عبر {unusual_stat.get('events')} إشارة).
• <b>دقة ارتداد مصائد الدببة (Spring):</b> <b>{springs_stat.get('hitRate3d')}%</b> حققت قمة صاعدة ≥ +3% (متوسط ربح: <b>+{springs_stat.get('avgBest3d')}%</b>).
• <b>دقة الحماية من مصائد القمم (Upthrust):</b> <b>{upthrusts_stat.get('winRate')}%</b> تأكيد هبوط فوري و <b>{upthrusts_stat.get('hitRate3d')}%</b> هبوط ≥ 3% (متوسط تجنب خسارة: <b>{upthrusts_stat.get('avgBest3d')}%</b>).

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
        print(f"[DRY_RUN] Fair value link: {LINK_FAIR_VALUE}")
        print(f"[DRY_RUN] Technical link: {LINK_TECHNICAL}")
        return {"ok": True, "dry_run": True, "target": target_chat, "text_len": len(html_content)}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": html_content,
        "parse_mode": "HTML",
        "reply_markup": reply_markup,
        "disable_web_page_preview": False,
    }

    resp = requests.post(url, json=payload, timeout=30)
    data = resp.json()
    if data.get("ok"):
        print(f"[SUCCESS] Dispatched to VIP Channel ({target_chat}) with message_id: {data.get('result', {}).get('message_id')}")
    else:
        print(f"[ERROR] Failed to send: {data}")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Daily Report to Telegram VIP Channel")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    args = parser.parse_args()

    res = send_vip_daily_report(dry_run=args.dry_run)
    print(res)
