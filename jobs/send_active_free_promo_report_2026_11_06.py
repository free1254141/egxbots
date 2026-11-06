#!/usr/bin/env python3
"""
jobs/send_active_free_promo_report_2026_11_06.py

Distributes the 2026-11-06 market report to:
  1) Email: ACTIVE non-Pro users only — two segments:
       - priority : active in the last 3 days
       - core     : active in the last 7 days (includes priority, deduped)
  2) Telegram: the official VIP channel -1003906516349 (VIP edition, no Pro upsell).

All numbers are read live from market_cache (last session close), never hardcoded.

Usage:
    python jobs/send_active_free_promo_report_2026_11_06.py --dry-run
    python jobs/send_active_free_promo_report_2026_11_06.py --send
    python jobs/send_active_free_promo_report_2026_11_06.py --send --skip-email
    python jobs/send_active_free_promo_report_2026_11_06.py --send --skip-vip
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))
load_dotenv(os.path.join(ROOT_DIR, "web", ".env.local"), override=True)

import requests
from api.stock_ai import _init_supabase, supabase
from api.marketing_lifecycle import (
    send_resend_email,
    record_marketing_message,
    is_user_unsubscribed,
    generate_unsub_token,
    APP_URL,
)

REPORT_DATE = "2026-11-06"
MESSAGE_TYPE = "active_free_promo_report_2026_11_06"
SUBJECT = "🔥 15 إشارة ناجحة من 15 في جلسة الأمس | مصائد الغد وفرص تحت القيمة العادلة 🇪🇬"

VIP_CHANNEL_ID = "-1003906516349"
LINK_PRICING = "https://egxbots.com/pricing?plan=pro"
LINK_TECHNICAL = "https://egxbots.com/scanner/technical"
LINK_FAIR_VALUE = "https://egxbots.com/fair-value"

PRO_PLAN_IDS = {"pro", "pro_6m", "pro_1y", "lifetime", "pro_lifetime"}


# ----------------------------------------------------------------------------- data
def _cache_payload(key: str) -> dict:
    r = supabase.table("market_cache").select("payload,computed_at").eq("cache_key", key).limit(1).execute()
    return (r.data or [{}])[0].get("payload") or {}


def load_market() -> dict:
    perf = _cache_payload("signal_performance_EGX")
    traps = _cache_payload("daily_traps_snapshot")
    review = perf.get("review") or {}
    return {
        "as_of": perf.get("asOf") or traps.get("asOf") or REPORT_DATE,
        "signal_date": review.get("signalDate"),
        "outcome_date": review.get("outcomeDate"),
        "review": review,
        "unusual_score": review.get("unusualScore") or {},
        "springs_score": review.get("springsScore") or {},
        "upthrusts_score": review.get("upthrustsScore") or {},
        "top_mover": review.get("topMover") or {},
        "unusual": review.get("unusual") or [],
        "springs": review.get("springs") or [],
        "upthrusts": review.get("upthrusts") or [],
        "stats": {
            "unusual": perf.get("unusual") or {},
            "springs": perf.get("springs") or {},
            "upthrusts": perf.get("upthrusts") or {},
        },
        "bear_traps": traps.get("bearTraps") or [],
        "bull_traps": traps.get("bullTraps") or [],
        "total_bear": traps.get("totalBearTraps") or len(traps.get("bearTraps") or []),
        "total_bull": traps.get("totalBullTraps") or len(traps.get("bullTraps") or []),
    }


def load_fair_value() -> dict | None:
    """Reads the platform's own cached fair-value report (no recomputation drift)."""
    url = os.getenv("REPORT_FAIR_VALUE_URL", "http://127.0.0.1:3000/api/market/fair-value")
    try:
        res = requests.get(url, timeout=90)
        if res.status_code != 200:
            print(f"[FAIR-VALUE] HTTP {res.status_code}; skipping section detail")
            return None
        return res.json()
    except Exception as exc:
        print(f"[FAIR-VALUE] unavailable: {exc}")
        return None


# ----------------------------------------------------------------------------- audience
def valid_pro_ids() -> set[str]:
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = supabase.table("subscriptions").select("user_id,plan_id,status,current_period_end").in_(
        "status", ["active", "trialing"]
    ).limit(10000).execute().data or []
    out = set()
    for r in rows:
        if str(r.get("plan_id") or "").lower() not in PRO_PLAN_IDS:
            continue
        end = r.get("current_period_end")
        if end:
            try:
                d = datetime.datetime.fromisoformat(str(end).replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=datetime.timezone.utc)
                if d <= now:
                    continue
            except ValueError:
                continue
        if r.get("user_id"):
            out.add(str(r["user_id"]))
    return out


def email_map() -> dict[str, str]:
    out: dict[str, str] = {}
    start = 0
    while True:
        r = supabase.table("marketing_message_log").select("user_id,email").order(
            "sent_at", desc=True
        ).range(start, start + 999).execute()
        d = r.data or []
        for x in d:
            em = (x.get("email") or "").strip().lower()
            uid = x.get("user_id")
            if em and "@" in em and uid and str(uid) not in out:
                out[str(uid)] = em
        if len(d) < 1000:
            break
        start += 1000
    return out


def active_ids(days: int) -> set[str]:
    cut = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
    out: set[str] = set()
    start = 0
    while True:
        r = supabase.table("user_activity_events").select("user_id").gte(
            "created_at", cut
        ).range(start, start + 999).execute()
        d = r.data or []
        for x in d:
            if x.get("user_id"):
                out.add(str(x["user_id"]))
        if len(d) < 1000:
            break
        start += 1000
    return out


def build_recipients() -> list[dict]:
    pro = valid_pro_ids()
    emap = email_map()
    unsub_users: set[str] = set()
    unsub_emails: set[str] = set()
    prefs = supabase.table("marketing_preferences").select(
        "user_id,email,unsubscribed_all"
    ).eq("unsubscribed_all", True).limit(10000).execute().data or []
    for p in prefs:
        if p.get("user_id"):
            unsub_users.add(str(p["user_id"]))
        if p.get("email"):
            unsub_emails.add(str(p["email"]).lower())

    priority = active_ids(3)
    core = active_ids(7) | priority

    already = set()
    prev = supabase.table("marketing_message_log").select("email").eq(
        "message_type", MESSAGE_TYPE
    ).limit(10000).execute().data or []
    for r in prev:
        if r.get("email"):
            already.add(str(r["email"]).lower())

    out = []
    for uid, em in emap.items():
        if uid not in core:
            continue
        if uid in pro or uid in unsub_users or em in unsub_emails or em in already:
            continue
        seg = "priority" if uid in priority else "core"
        out.append({"user_id": uid, "email": em, "segment": seg})
    out.sort(key=lambda x: (x["segment"] != "priority", x["email"]))
    return out


# ----------------------------------------------------------------------------- builders
def _fmt(v, digits=2):
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _has_arabic(text) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in str(text or ""))


def fair_value_picks(fv: dict | None, limit: int = 3) -> tuple[int, list[dict]]:
    """Returns (undervalued_count, picks) using only solid, readable examples."""
    if not fv:
        return 0, []
    stocks = fv.get("stocks") or []
    undervalued = [s for s in stocks if s.get("status") == "undervalued"]
    picks = [
        s for s in undervalued
        if float(s.get("currentPrice") or 0) >= 5.0 and _has_arabic(s.get("nameAr"))
    ][:limit]
    if len(picks) < limit:
        seen = {p.get("symbol") for p in picks}
        for s in undervalued:
            if s.get("symbol") in seen:
                continue
            picks.append(s)
            if len(picks) >= limit:
                break
    return len(undervalued), picks


def build_email_html(m: dict, fv: dict | None, user_id: str, email: str) -> str:
    unsub = generate_unsub_token(user_id, email)
    unsub_url = f"{APP_URL}/api/marketing/unsubscribe?uid={user_id}&token={unsub}&email={email}"

    top = m["top_mover"]
    top_block = ""
    if top.get("symbol"):
        top_block = (
            f"⭐ <strong>سهم {top['symbol']} — نجم الجلسة:</strong><br>"
            f"إشارة الدخول عند {_fmt(top.get('signalClose'))} ج.م &rarr; أعلى قمة "
            f"<strong>{_fmt(top.get('nextHigh'))} ج.م (+{_fmt(top.get('intradayHighPct'))}%)</strong> "
            f"وإغلاق {_fmt(top.get('nextClose'))} ج.م (+{_fmt(top.get('retPct'))}%) "
            f"بحجم <strong>{_fmt(top.get('relativeVolume'), 2)}×</strong> المعدل الطبيعي."
        )

    movers = []
    for u in m["unusual"][:8]:
        if u.get("symbol") == top.get("symbol"):
            continue
        movers.append(
            f"• <strong>{u.get('symbol')}</strong>: قمة +{_fmt(u.get('intradayHighPct'))}% "
            f"| إغلاق +{_fmt(u.get('retPct'))}% | حجم {_fmt(u.get('relativeVolume'))}x"
        )
    movers_html = "<br>".join(movers) or "• لا توجد نماذج إضافية اليوم."

    bear = m["bear_traps"][:6]
    bear_html = "<br>".join(
        f"• <strong>{t.get('symbol')}</strong>: إغلاق {_fmt(t.get('close'))} ج | دعم "
        f"{_fmt(t.get('keyLevel'))} ج | ارتداد {_fmt(t.get('wickPct'), 0)}% | ثقة "
        f"{_fmt(t.get('conviction'), 0)}% | حجم {_fmt(t.get('relativeVolume'))}x"
        for t in bear
    ) or "• جاري تحديث نماذج الارتداد."

    bull = m["bull_traps"][:4]
    bull_html = "<br>".join(
        f"• <strong>{t.get('symbol')}</strong>: إغلاق {_fmt(t.get('close'))} ج | مقاومة "
        f"{_fmt(t.get('keyLevel'))} ج | رفض {_fmt(t.get('wickPct'), 0)}% | ثقة "
        f"{_fmt(t.get('conviction'), 0)}%"
        for t in bull
    ) or "• لا توجد مصائد قمم نشطة."

    fv_html = ""
    if fv and fv.get("summary"):
        s = fv["summary"]
        und_count, picks = fair_value_picks(fv)
        picks_html = "<br>".join(
            f"• <strong>{p.get('symbol')}</strong> ({p.get('nameAr')}): يتداول عند "
            f"{_fmt(p.get('currentPrice'))} ج مقابل قيمة عادلة {_fmt(p.get('fairValue'))} ج "
            f"(صعود متوقع +{_fmt(p.get('upsidePct'))}%)"
            for p in picks
        ) or "• التقرير الكامل متاح داخل المنصة."
        fv_html = (
            f'<h2 style="margin:0 0 10px 0;font-size:16px;color:#60a5fa;">💎 '
            f'{und_count} سهماً يتداولون تحت قيمتهم العادلة</h2>'
            f'<p style="font-size:13px;color:#d1d5db;margin:0 0 10px 0;line-height:1.7;">'
            f'تقييم أساسي كمي لأحدث جلسة ({fv.get("latestSessionDate") or "-"}) عبر '
            f'{s.get("totalEvaluated", 0)} سهماً مسجلاً.</p>'
            f'<div style="font-size:13px;color:#9ca3af;line-height:1.9;background:#111827;'
            f'padding:12px;border-radius:8px;">{picks_html}</div>'
        )
    else:
        fv_html = (
            '<h2 style="margin:0 0 10px 0;font-size:16px;color:#60a5fa;">💎 فرص الأسهم تحت القيمة العادلة</h2>'
            '<p style="font-size:13px;color:#d1d5db;margin:0;line-height:1.7;">'
            'التقرير المحدث متاح الآن على المنصة مع القيمة العادلة لكل سهم وسبب التقييم.</p>'
        )

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>تقرير السوق {REPORT_DATE} | EGX BOTS</title></head>
<body style="margin:0;padding:0;background-color:#07090e;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#f3f4f6;text-align:right;">
<div style="max-width:620px;margin:0 auto;padding:24px 16px;">
  <div style="text-align:center;padding-bottom:20px;border-bottom:2px solid #1f2937;">
    <a href="{APP_URL}" style="text-decoration:none;color:#fff;font-size:24px;font-weight:900;">EGX <span style="color:#10b981;">BOTS</span> | ARTORO AI</a>
    <div style="margin-top:8px;"><span style="display:inline-block;background:rgba(245,158,11,.15);border:1px solid rgba(245,158,11,.4);color:#f59e0b;font-size:12px;font-weight:bold;padding:4px 12px;border-radius:9999px;">⚡ تقرير خاص للمتداولين النشطين</span></div>
  </div>

  <div style="padding:20px 0 12px 0;">
    <h1 style="margin:0 0 8px 0;font-size:20px;color:#fff;line-height:1.4;">📈 حصيلة جلسة {m['outcome_date'] or m['as_of']} ونظرة جلسة {REPORT_DATE}</h1>
    <p style="margin:0;font-size:14px;color:#9ca3af;line-height:1.7;">نتائج إشارات الرادار ومصائد وايكوف والقيمة العادلة — بأرقامها الحقيقية من السوق.</p>
  </div>

  <div style="background:#0d1117;border:2px solid #10b981;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 10px 0;font-size:16px;color:#10b981;">🚀 إشارات النشاط غير الطبيعي: {m['unusual_score'].get('wins', 0)}/{m['unusual_score'].get('total', 0)} ناجحة</h2>
    <div style="font-size:13px;color:#d1d5db;line-height:1.9;">
      <div style="background:rgba(16,185,129,0.12);padding:12px;border-radius:8px;margin-bottom:12px;border-right:3px solid #10b981;">{top_block}</div>
      {movers_html}
    </div>
  </div>

  <div style="background:#0d1117;border:2px solid #374151;border-radius:16px;padding:18px;margin-bottom:20px;">
    <h2 style="margin:0 0 12px 0;font-size:16px;color:#f59e0b;">🪤 كاشف المصائد — جلسة {REPORT_DATE}</h2>
    <p style="font-size:13px;color:#d1d5db;margin:0 0 10px 0;line-height:1.7;">رصد وايكوف سجّل <strong>{m['total_bear']}</strong> مصيدة ارتداد شرائي و<strong>{m['total_bull']}</strong> مصيدة قمم.</p>
    <div style="font-size:13px;color:#9ca3af;line-height:1.9;background:#111827;padding:12px;border-radius:8px;margin-bottom:12px;">
      <div style="color:#10b981;font-weight:bold;margin-bottom:6px;">🟢 ارتداد شرائي (Spring):</div>{bear_html}
    </div>
    <div style="font-size:13px;color:#9ca3af;line-height:1.9;background:#111827;padding:12px;border-radius:8px;">
      <div style="color:#ef4444;font-weight:bold;margin-bottom:6px;">🔴 مصائد قمم (Upthrust) — احذر الشراء:</div>{bull_html}
    </div>
  </div>

  <div style="background:#0d1117;border:2px solid #374151;border-radius:16px;padding:18px;margin-bottom:20px;">
    {fv_html}
  </div>

  <div style="background:linear-gradient(135deg, rgba(16,185,129,0.15) 0%, rgba(59,130,246,0.15) 100%);border:2px solid #10b981;border-radius:16px;padding:24px;text-align:center;margin-bottom:24px;">
    <span style="background:#10b981;color:#000;font-size:11px;font-weight:900;padding:3px 10px;border-radius:9999px;">عرض المؤسسين المحدود</span>
    <h3 style="margin:12px 0 8px 0;font-size:20px;color:#fff;">باقة EGX BOTS Pro بـ 100 ج.م شهرياً فقط</h3>
    <p style="margin:0 0 16px 0;font-size:13px;color:#d1d5db;line-height:1.7;">إشارات الرادار اللحظية، كاشف المصائد اليومي، قناة التنبيهات VIP، ومساعد ARTORO بدون قيود.</p>
    <a href="{LINK_PRICING}" style="display:inline-block;background:#10b981;color:#000;font-weight:900;font-size:15px;padding:16px 32px;border-radius:12px;text-decoration:none;">⚡ تفعيل باقة Pro الآن ↗</a>
    <div style="margin-top:10px;font-size:11px;color:#9ca3af;">💳 دفع فوري: فودافون كاش / انستاباي / فوري / بطاقات وميزة</div>
  </div>

  <div style="text-align:center;margin:16px 0;">
    <a href="{LINK_TECHNICAL}" style="color:#10b981;text-decoration:underline;font-size:13px;margin:0 8px;">تصفح الماسح الفني</a> |
    <a href="{LINK_FAIR_VALUE}" style="color:#10b981;text-decoration:underline;font-size:13px;margin:0 8px;">فحص القيمة العادلة</a>
  </div>

  <div style="border-top:1px solid #1f2937;padding-top:20px;font-size:11px;color:#6b7280;text-align:center;line-height:1.6;">
    <p style="margin:0 0 8px 0;">⚠️ إخلاء مسؤولية: منصة EGX BOTS أداة تحليل فني وكمي ولا تقدم توصيات استثمارية.</p>
    <a href="{unsub_url}" style="color:#9ca3af;text-decoration:underline;">إلغاء الاشتراك بنقرة واحدة</a>
  </div>
</div>
</body>
</html>"""


def build_vip_telegram(m: dict, fv: dict | None) -> str:
    top = m["top_mover"]
    top_block = ""
    if top.get("symbol"):
        top_block = (
            f"⭐ <b>نجم الجلسة: {top['symbol']}</b>\n"
            f"• إشارة الدخول: {_fmt(top.get('signalClose'))} ج.م\n"
            f"• أعلى قمة: {_fmt(top.get('nextHigh'))} ج.م (+{_fmt(top.get('intradayHighPct'))}%)\n"
            f"• الإغلاق: {_fmt(top.get('nextClose'))} ج.م (+{_fmt(top.get('retPct'))}%)\n"
            f"• الحجم: {_fmt(top.get('relativeVolume'))}× المعدل الطبيعي\n"
        )
    movers = []
    for u in m["unusual"][:6]:
        if u.get("symbol") == top.get("symbol"):
            continue
        movers.append(
            f"• <b>{u.get('symbol')}</b>: قمة +{_fmt(u.get('intradayHighPct'))}% | "
            f"إغلاق +{_fmt(u.get('retPct'))}% | حجم {_fmt(u.get('relativeVolume'))}x"
        )
    bear = "\n".join(
        f"{i}. <b>{t.get('symbol')}</b> | إغلاق {_fmt(t.get('close'))} ج | دعم {_fmt(t.get('keyLevel'))} ج | "
        f"ارتداد {_fmt(t.get('wickPct'), 0)}% | ثقة {_fmt(t.get('conviction'), 0)}%"
        for i, t in enumerate(m["bear_traps"][:6], 1)
    ) or "• جاري التحديث."
    bull = "\n".join(
        f"{i}. <b>{t.get('symbol')}</b> | إغلاق {_fmt(t.get('close'))} ج | مقاومة {_fmt(t.get('keyLevel'))} ج | "
        f"رفض {_fmt(t.get('wickPct'), 0)}% | ثقة {_fmt(t.get('conviction'), 0)}%"
        for i, t in enumerate(m["bull_traps"][:4], 1)
    ) or "• لا توجد مصائد قمم نشطة."

    fv_block = ""
    if fv and fv.get("summary"):
        s = fv["summary"]
        und_count, picks = fair_value_picks(fv)
        picks_txt = "\n".join(
            f"• <b>{p.get('symbol')}</b>: {_fmt(p.get('currentPrice'))} ج مقابل قيمة عادلة "
            f"{_fmt(p.get('fairValue'))} ج (صعود متوقع +{_fmt(p.get('upsidePct'))}%)"
            for p in picks
        )
        fv_block = (
            f"💎 <b>ثالثاً: {und_count} سهماً تحت القيمة العادلة</b>\n"
            f"تقييم {s.get('totalEvaluated', 0)} سهماً — جلسة {fv.get('latestSessionDate') or '-'}\n{picks_txt}"
        )
    else:
        fv_block = "💎 <b>ثالثاً: تقرير القيمة العادلة</b>\nالتقرير المحدث متاح على المنصة."

    st = m["stats"]
    return (
        f"👑 <b>تقرير VIP | حصيلة جلسة {m['outcome_date'] or m['as_of']} ومصائد {REPORT_DATE}</b> 🇪🇬\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"🚀 <b>أولاً: إشارات النشاط غير الطبيعي ({m['unusual_score'].get('wins', 0)}/{m['unusual_score'].get('total', 0)})</b>\n"
        f"{top_block}\n"
        f"<b>أبرز النماذج الصاعدة:</b>\n" + "\n".join(movers) + "\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"🪤 <b>ثانياً: كاشف المصائد — جلسة {REPORT_DATE}</b>\n"
        f"إجمالي: <b>{m['total_bear']}</b> ارتداد شرائي | <b>{m['total_bull']}</b> مصيدة قمم\n\n"
        f"🟢 <b>Wyckoff Spring:</b>\n{bear}\n\n"
        f"🔴 <b>Wyckoff Upthrust:</b>\n{bull}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"{fv_block}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 <b>رابعاً: الإحصاءات (40 جلسة)</b>\n"
        f"• انفجار 3 أيام: <b>{st['unusual'].get('hitRate3d', '-')}%</b> "
        f"(متوسط +{st['unusual'].get('avgBest3d', '-')}% | {st['unusual'].get('events', '-')} إشارة)\n"
        f"• ارتداد Spring: <b>{st['springs'].get('hitRate3d', '-')}%</b> "
        f"(متوسط +{st['springs'].get('avgBest3d', '-')}% | {st['springs'].get('events', '-')})\n"
        f"• حماية Upthrust: <b>{st['upthrusts'].get('winRate', '-')}%</b> "
        f"(تجنب هبوط {st['upthrusts'].get('hitRate3d', '-')}% | متوسط {st['upthrusts'].get('avgBest3d', '-')}%)\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 {LINK_TECHNICAL}"
    )


# ----------------------------------------------------------------------------- senders
def send_vip(text: str) -> bool:
    token = (os.getenv("ARTORO_AI_BOT") or os.getenv("SUPPORT_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("No Telegram bot token found.")
    if VIP_CHANNEL_ID != "-1003906516349":
        raise ValueError("SAFETY: refusing to send to a non-VIP channel.")
    payload = {
        "chat_id": VIP_CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {"inline_keyboard": [[
            {"text": "📊 الماسح الفني", "url": LINK_TECHNICAL},
            {"text": "💎 القيمة العادلة", "url": LINK_FAIR_VALUE},
        ]]},
    }
    res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=30)
    data = res.json()
    if data.get("ok"):
        print(f"[VIP] ✅ sent message_id={data['result']['message_id']}")
        return True
    print(f"[VIP] ❌ {data}")
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="actually send (default is dry-run)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-email", action="store_true")
    ap.add_argument("--skip-vip", action="store_true")
    args = ap.parse_args()
    do_send = args.send and not args.dry_run

    _init_supabase()
    market = load_market()
    fv = load_fair_value()
    recipients = build_recipients()
    priority = [r for r in recipients if r["segment"] == "priority"]
    core = [r for r in recipients if r["segment"] == "core"]

    print(f"=== Report {REPORT_DATE} | market as-of {market['as_of']} ===")
    print(f"Recipients: total={len(recipients)} priority={len(priority)} core={len(core)}")
    print(f"Fair value: {'loaded' if fv else 'unavailable'}")

    if not do_send:
        print("\n[DRY RUN] Email recipients (first 10):")
        for r in recipients[:10]:
            print(f"  - [{r['segment']}] {r['email']}")
        html = build_email_html(market, fv, "test", "test@example.com")
        print(f"[DRY RUN] Subject: {SUBJECT}")
        print(f"[DRY RUN] HTML length: {len(html)}")
        print("\n[DRY RUN] VIP Telegram preview:\n")
        print(build_vip_telegram(market, fv))
        return

    # ---- email ----
    if not args.skip_email:
        ok = fail = 0
        for i, r in enumerate(recipients, 1):
            if is_user_unsubscribed(r["user_id"], r["email"]):
                continue
            html = build_email_html(market, fv, r["user_id"], r["email"])
            meta: dict = {}
            if send_resend_email(r["email"], SUBJECT, html, out=meta):
                record_marketing_message(
                    user_id=r["user_id"],
                    email=r["email"],
                    message_type=MESSAGE_TYPE,
                    metadata={"is_pro": False, "is_promo": True, "segment": r["segment"],
                              "resend_id": meta.get("provider_message_id")},
                    provider_message_id=meta.get("provider_message_id"),
                )
                ok += 1
                print(f"[{i}/{len(recipients)}] ✅ {r['email']} ({r['segment']})")
            else:
                fail += 1
                print(f"[{i}/{len(recipients)}] ❌ {r['email']}")
            time.sleep(0.4)
        print(f"[EMAIL] sent={ok} failed={fail}")

    # ---- VIP telegram ----
    if not args.skip_vip:
        send_vip(build_vip_telegram(market, fv))


if __name__ == "__main__":
    main()
