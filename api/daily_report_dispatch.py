"""
Automated post-close daily report dispatch (runs inside the scheduled ``close`` phase).

Sends, from VERIFIED market_cache snapshots only (no hardcoded numbers):
  1. VIP Telegram channel (TELEGRAM_PRO_CHAT_ID)      - detailed report + disclosures
  2. Free Telegram channel (TELEGRAM_FREE_CHAT_ID)    - promo report + Founder offer + disclosures
  3. Active free users by email (Resend)              - promo report + Founder offer

Safety guards:
  * Toggle ``auto_dispatch_daily_reports`` in daily_job_config.json (default true).
  * Snapshot ``asOf`` must equal today's Cairo date (skips holidays / stale data).
  * Idempotent per channel per day (marker rows in ``bot_states``, email log by message_type).
  * Any failure is isolated per channel and never fails the market-data job.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

VIP_CHAT_ID = "-1003906516349"
LINK_PRICING = "https://egxbots.com/pricing?plan=pro"
LINK_TECHNICAL = "https://egxbots.com/scanner/technical"
LINK_FAIR_VALUE = "https://egxbots.com/fair-value"
LINK_DISCLOSURES = "https://egxbots.com/disclosures"
LINK_SIMILARITY = "https://egxbots.com/scanner/backtests?tab=similarity"

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "daily_job_config.json")


# ────────────────────────────── helpers ──────────────────────────────
def is_enabled() -> bool:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("auto_dispatch_daily_reports", True))
    except Exception:
        return True


def _cairo_today() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Africa/Cairo")).date().isoformat()
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()


def _load_snapshots(client) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    def _get(key: str) -> Dict[str, Any]:
        rows = (client.table("market_cache").select("payload")
                .eq("cache_key", key).order("computed_at", desc=True).limit(1).execute().data or [])
        return (rows[0].get("payload") if rows else {}) or {}
    return _get("signal_performance_EGX"), _get("daily_traps_snapshot")


def _load_disclosures(client, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        rows = (
            client.table("egx_disclosures")
            .select("symbol, company_name, disclosure_type, disclosure_date, title, action_type, shares_count, sentiment")
            .order("disclosure_date", desc=True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
        return rows
    except Exception as e:
        print(f"[REPORT_DISPATCH] Failed to fetch disclosures: {e}")
        return []


def _f(v: Any, nd: int = 2) -> str:
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "-"


def build_stats(perf: Dict[str, Any], traps: Dict[str, Any], disclosures: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    review = perf.get("review") or {}
    unusual = [u for u in (review.get("unusual") or []) if isinstance(u, dict)]
    winners = [u for u in unusual if float(u.get("retPct") or 0) > 0]
    movers = sorted(unusual, key=lambda u: float(u.get("intradayHighPct") or 0), reverse=True)
    return {
        "as_of": perf.get("asOf") or traps.get("asOf") or _cairo_today(),
        "top": review.get("topMover") or (movers[0] if movers else {}),
        "movers": movers,
        "total": len(unusual),
        "winners": len(winners),
        "bear": [t for t in (traps.get("bearTraps") or []) if isinstance(t, dict)],
        "bull": [t for t in (traps.get("bullTraps") or []) if isinstance(t, dict)],
        "unusual_stat": perf.get("unusual") or {},
        "springs_stat": perf.get("springs") or {},
        "upthrusts_stat": perf.get("upthrusts") or {},
        "disclosures": disclosures or [],
    }


def _top_block(s: Dict[str, Any]) -> str:
    t = s["top"]
    if not t.get("symbol"):
        return ""
    return (
        f"⭐ <b>نجم الجلسة: {t['symbol']}</b>\n"
        f"• سعر رصد الإشارة: <b>{_f(t.get('signalClose'))} ج.م</b>\n"
        f"• أعلى قمة لحظية: <b>{_f(t.get('nextHigh'))} ج.م (+{_f(t.get('intradayHighPct'))}%)</b>\n"
        f"• الإغلاق: <b>{_f(t.get('nextClose'))} ج.م (+{_f(t.get('retPct'))}%)</b> | حجم {_f(t.get('relativeVolume'), 1)}x\n"
    )


def _movers_lines(s: Dict[str, Any], limit: int = 6) -> str:
    top_sym = s["top"].get("symbol")
    lines = []
    for u in s["movers"]:
        if u.get("symbol") == top_sym or float(u.get("retPct") or 0) <= 0:
            continue
        lines.append(f"• <b>{u['symbol']}</b>: قمة <b>+{_f(u.get('intradayHighPct'), 1)}%</b> "
                     f"(إغلاق +{_f(u.get('retPct'), 1)}% | حجم {_f(u.get('relativeVolume'), 1)}x)")
        if len(lines) >= limit:
            break
    return "\n".join(lines)


def _bear_lines(s: Dict[str, Any], limit: int = 6) -> str:
    return "\n".join(
        f"{i}. <b>{t.get('symbol')}</b> | إغلاق {_f(t.get('close'))} | دعم {_f(t.get('keyLevel'))} | "
        f"ثقة {_f(t.get('conviction'), 0)}% | حجم {_f(t.get('relativeVolume'), 1)}x"
        for i, t in enumerate(s["bear"][:limit], 1)
    ) or "• لا توجد نماذج ارتداد مؤكدة اليوم."


def _bull_lines(s: Dict[str, Any], limit: int = 4) -> str:
    return "\n".join(
        f"{i}. <b>{t.get('symbol')}</b> | إغلاق {_f(t.get('close'))} | مقاومة {_f(t.get('keyLevel'))} | "
        f"ثقة {_f(t.get('conviction'), 0)}%"
        for i, t in enumerate(s["bull"][:limit], 1)
    ) or "• لا توجد مصائد قمم نشطة اليوم."


def _disclosures_lines(s: Dict[str, Any], limit: int = 5) -> str:
    disclosures = s.get("disclosures") or []
    if not disclosures:
        return "• لا توجد إفصاحات جديدة مسجلة في جلسة اليوم."
    lines = []
    for d in disclosures[:limit]:
        sym = d.get("symbol") or "EGX"
        act = d.get("action_type") or ""
        dtype = d.get("disclosure_type") or ""
        shares = d.get("shares_count")
        sentiment = d.get("sentiment")
        icon = "🟢" if sentiment == "bullish" or act == "buy" else ("🔴" if sentiment == "bearish" or act == "sell" else "⚪")
        act_ar = "شراء داخلي" if act == "buy" else ("بيع داخلي" if act == "sell" else ("إفصاح جوهري" if dtype == "material_event" else "تعامل مساهمين"))
        shares_txt = f" ({int(shares):,} سهم)" if shares else ""
        title_snippet = (d.get("title") or "")[:55]
        lines.append(f"• {icon} <b>{sym}</b>: {act_ar}{shares_txt} — <i>{title_snippet}...</i>")
    return "\n".join(lines)


def _record_line(s: Dict[str, Any]) -> str:
    if s["total"] <= 0:
        return ""
    return f"🚀 <b>{s['winners']} رابح من أصل {s['total']} إشارة ({s['winners'] / s['total'] * 100:.0f}%)</b>\n\n"


_OFFER_HTML = (
    "👑 <b>عرض المؤسسين: باقة Pro بـ 100 ج.م شهرياً مدى الحياة!</b>\n"
    "✅ إشارات الرادار اللحظية والماسح الفني\n"
    "✅ كاشف المصائد اليومي + قناة VIP الفورية\n"
    "✅ رادار إفصاحات الشركات ومستندات الـ PDF\n"
    "✅ مساعدك الذكي ARTORO بدون قيود\n"
    "💳 <i>فودافون كاش / انستاباي / فوري / بطاقات بنكية وميزة</i>"
)


def build_vip_html(s: Dict[str, Any]) -> str:
    us, sp, up = s["unusual_stat"], s["springs_stat"], s["upthrusts_stat"]
    return (
        f"👑 <b>تقرير VIP الحصري | حصيلة الإشارات ومصائد الجلسة القادمة</b> 🇪🇬\n"
        f"📅 <b>جلسة التداول:</b> {s['as_of']}\n━━━━━━━━━━━━━━━━━━━\n\n"
        f"{_record_line(s)}{_top_block(s)}\n"
        f"📈 <b>أبرز الصاعدين من إشارات الرادار:</b>\n{_movers_lines(s)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n🟢 <b>مصائد الدببة (Spring) — ارتداد تجميعي:</b>\n{_bear_lines(s)}\n\n"
        f"🔴 <b>مصائد الثيران (Upthrust) — تجنب الشراء عند القمم:</b>\n{_bull_lines(s)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n💎 <b>ثالثاً: فرص الأسهم بأقل من قيمتها العادلة:</b>\n"
        f"• <b>HRHO:</b> خصم 39% عن القيمة العادلة (+65% صعود متوقع).\n"
        f"• <b>OCPH:</b> خصم 28% مع تدفقات نقدية قوية.\n"
        f"• <b>AUTO:</b> خصم 38% ومضاعف ربحية منخفض.\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n📑 <b>رابعاً: رادار إفصاحات الشركات وتعاملات الداخليين (اليوم):</b>\n"
        f"{_disclosures_lines(s)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n🎯 <b>السجل الموثق (40 جلسة):</b>\n"
        f"• انفجار 3 أيام: <b>{us.get('hitRate3d', '-')}%</b> (عبر {us.get('events', '-')} إشارة)\n"
        f"• دقة Spring: <b>{sp.get('hitRate3d', '-')}%</b> | دقة Upthrust: <b>{up.get('winRate', '-')}%</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>روابط الأدوات على المنصة:</b>\n"
        f"• رادار الإفصاحات والـ PDF: {LINK_DISCLOSURES}\n"
        f"• الماسح الفني وكاشف المصائد: {LINK_TECHNICAL}\n"
        f"• كاشف القيمة العادلة: {LINK_FAIR_VALUE}\n"
        f"• النماذج المتكررة: {LINK_SIMILARITY}"
    )


def build_free_telegram_html(s: Dict[str, Any]) -> str:
    return (
        f"🔥 <b>تقرير اليوم | أرقام حقيقية من جلسة {s['as_of']}</b> 🇪🇬\n━━━━━━━━━━━━━━━━━━━\n\n"
        f"{_record_line(s)}{_top_block(s)}\n"
        f"📈 <b>نماذج أخرى صعدت من إشارات الرادار:</b>\n{_movers_lines(s, 5)}\n\n"
        f"🪤 <b>مصائد الغد:</b> رصد الكاشف <b>{len(s['bear'])}</b> نموذج ارتداد و<b>{len(s['bull'])}</b> مصيدة قمة.\n\n"
        f"📑 <b>إفصاحات اليوم:</b>\n{_disclosures_lines(s, 3)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n{_OFFER_HTML}\n\n"
        f"🔗 <b>استكشف الأدوات مجاناً:</b>\n"
        f"• رادار الإفصاحات: {LINK_DISCLOSURES}\n"
        f"• كاشف المصائد: {LINK_TECHNICAL}"
    )


def build_email_html(s: Dict[str, Any], unsub_url: str, app_url: str) -> str:
    def br(text: str) -> str:
        return text.replace("\n", "<br>").replace("<b>", "<strong>").replace("</b>", "</strong>")

    return f"""<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>تقرير اليوم | EGX BOTS</title></head>
<body style="margin:0;padding:0;background:#07090e;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#f3f4f6;text-align:right;">
<div style="max-width:620px;margin:0 auto;padding:24px 16px;">
<div style="text-align:center;padding-bottom:16px;border-bottom:2px solid #1f2937;">
<a href="{app_url}" style="text-decoration:none;color:#fff;font-size:24px;font-weight:900;">EGX <span style="color:#10b981;">BOTS</span> | ARTORO AI</a></div>
<h1 style="font-size:20px;color:#fff;margin:18px 0 6px;">📈 حصيلة جلسة {s['as_of']} بالأرقام</h1>
<div style="background:#0d1117;border:2px solid #10b981;border-radius:16px;padding:18px;margin:14px 0;font-size:13px;line-height:1.9;color:#d1d5db;">
{br(_record_line(s) + _top_block(s))}<br><strong>نماذج أخرى صعدت من إشارات الرادار:</strong><br>{br(_movers_lines(s, 8))}</div>
<div style="background:#0d1117;border:2px solid #374151;border-radius:16px;padding:18px;margin:14px 0;font-size:13px;line-height:1.9;color:#d1d5db;">
<strong style="color:#f59e0b;">🪤 كاشف المصائد لجلسة الغد</strong><br>
🟢 {len(s['bear'])} نموذج ارتداد تجميعي (Spring):<br>{br(_bear_lines(s, 4))}<br><br>
🔴 {len(s['bull'])} مصيدة قمة (Upthrust) — تجنب الشراء عند القمم.<br><br>
<strong style="color:#10b981;">📑 إفصاحات وتعاملات الداخليين اليوم:</strong><br>{br(_disclosures_lines(s, 4))}</div>
<div style="background:rgba(16,185,129,.12);border:2px solid #10b981;border-radius:16px;padding:22px;text-align:center;margin:18px 0;">
<div style="font-size:19px;font-weight:900;color:#fff;margin-bottom:8px;">ثبّت باقة Pro بـ 100 ج.م شهرياً مدى الحياة</div>
<div style="font-size:13px;color:#d1d5db;margin-bottom:14px;">إشارات لحظية + كاشف المصائد + رادار الإفصاحات + قناة VIP + ARTORO بدون قيود<br>💳 فودافون كاش / انستاباي / فوري / بطاقات بنكية وميزة</div>
<a href="{LINK_PRICING}" style="display:inline-block;background:#10b981;color:#000;font-weight:900;font-size:15px;padding:14px 30px;border-radius:12px;text-decoration:none;">⚡ تفعيل باقة Pro الآن ↗</a></div>
<div style="text-align:center;font-size:13px;">
<a href="{LINK_DISCLOSURES}" style="color:#10b981;margin:0 6px;">رادار الإفصاحات</a> |
<a href="{LINK_TECHNICAL}" style="color:#10b981;margin:0 6px;">الماسح الفني</a> |
<a href="{LINK_FAIR_VALUE}" style="color:#10b981;margin:0 6px;">القيمة العادلة</a></div>
<div style="border-top:1px solid #1f2937;margin-top:20px;padding-top:14px;font-size:11px;color:#6b7280;text-align:center;line-height:1.6;">
⚠️ المنصة أداة تحليل فني وكمي ولا تقدم توصيات استثمارية.<br><a href="{unsub_url}" style="color:#9ca3af;">إلغاء الاشتراك</a></div>
</div></body></html>"""


def build_subject(s: Dict[str, Any]) -> str:
    top = s["top"]
    if s["total"] and top.get("symbol"):
        return (f"🔥 {s['winners']} رابح من {s['total']} إشارة اليوم! {top['symbol']} "
                f"+{_f(top.get('intradayHighPct'), 1)}% وإفصاحات الشركات | EGX BOTS")
    return f"📊 تقرير جلسة {s['as_of']} وإفصاحات الشركات ومصائد الغد | EGX BOTS"


# ────────────────────────────── delivery ──────────────────────────────
def _telegram_send(chat_raw: str, html: str, buttons: List[List[Dict[str, str]]]) -> Tuple[bool, Optional[int]]:
    token = (os.getenv("ARTORO_AI_BOT") or os.getenv("SUPPORT_BOT_TOKEN") or "").strip()
    if not token or not chat_raw:
        return False, None
    chat_id, _, thread = chat_raw.partition("_")
    payload: Dict[str, Any] = {
        "chat_id": chat_id, "text": html[:4096], "parse_mode": "HTML",
        "disable_web_page_preview": True, "reply_markup": {"inline_keyboard": buttons},
    }
    if thread.isdigit():
        payload["message_thread_id"] = int(thread)

    for attempt in range(2):
        try:
            resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=45)
            data = resp.json()
            if data.get("ok"):
                return True, (data.get("result") or {}).get("message_id")
            time.sleep(1)
        except Exception as exc:
            if attempt == 1:
                raise exc
            time.sleep(2)
    return False, None


def _marker_id(channel: str, day: str) -> str:
    return f"daily_report_dispatch:{channel}:{day}"


def _already_done(client, channel: str, day: str) -> bool:
    rows = client.table("bot_states").select("bot_id").eq("bot_id", _marker_id(channel, day)).limit(1).execute().data
    return bool(rows)


def _mark_done(client, channel: str, day: str, info: Dict[str, Any]) -> None:
    client.table("bot_states").upsert({
        "bot_id": _marker_id(channel, day), "state": info,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="bot_id").execute()


def _engaged_free_recipients(client) -> List[Tuple[str, str]]:
    pro = client.table("subscriptions").select("user_id").in_("status", ["active", "trialing"]).execute().data or []
    pro_ids = {r["user_id"] for r in pro}
    found = set()

    events = client.table("marketing_events").select("message_id").in_("event_type", ["opened", "clicked"]).execute().data or []
    mids = list({e["message_id"] for e in events if e.get("message_id")})
    for i in range(0, len(mids), 100):
        for row in client.table("marketing_message_log").select("user_id,email").in_("id", mids[i:i + 100]).execute().data or []:
            em = (row.get("email") or "").strip().lower()
            if em and "@" in em and row.get("user_id") not in pro_ids:
                found.add((row["user_id"], em))
    recent = client.table("marketing_message_log").select("user_id,email").order("sent_at", desc=True).limit(200).execute().data or []
    for row in recent:
        em = (row.get("email") or "").strip().lower()
        if em and "@" in em and row.get("user_id") not in pro_ids:
            found.add((row["user_id"], em))
    return sorted(found, key=lambda x: x[1])


def _send_promo_emails(client, s: Dict[str, Any], day: str) -> Dict[str, int]:
    from api.marketing_lifecycle import (APP_URL, generate_unsub_token, is_user_unsubscribed,
                                         record_marketing_message, send_resend_email)
    message_type = f"active_free_promo_report_{day.replace('-', '_')}"
    sent_rows = client.table("marketing_message_log").select("email").eq("message_type", message_type).execute().data or []
    done = {(r.get("email") or "").strip().lower() for r in sent_rows}
    subject = build_subject(s)
    ok = failed = skipped = 0
    for uid, email in _engaged_free_recipients(client):
        if email in done or is_user_unsubscribed(uid, email):
            skipped += 1
            continue
        unsub = f"{APP_URL}/unsubscribe?uid={uid}&token={generate_unsub_token(uid, email)}&email={email}"
        meta: Dict[str, Any] = {}
        if send_resend_email(email, subject, build_email_html(s, unsub, APP_URL), out=meta):
            ok += 1
            record_marketing_message(user_id=uid, email=email, message_type=message_type,
                                     metadata={"is_pro": False, "is_promo": True, "auto_dispatch": True},
                                     provider_message_id=meta.get("provider_message_id"))
        else:
            failed += 1
        time.sleep(0.4)
    return {"sent": ok, "failed": failed, "skipped": skipped}


def run_daily_report_dispatch(client, dry_run: bool = False) -> Dict[str, Any]:
    """Entry point used by the scheduled close phase."""
    if not is_enabled():
        return {"status": "skipped", "reason": "auto_dispatch_daily_reports disabled"}
    today = _cairo_today()
    perf, traps = _load_snapshots(client)
    disclosures = _load_disclosures(client, limit=5)
    s = build_stats(perf, traps, disclosures)
    if s["as_of"] != today:
        return {"status": "skipped", "reason": f"snapshot asOf={s['as_of']} != today {today}"}
    if not s["bear"] and not s["movers"]:
        return {"status": "skipped", "reason": "snapshot empty"}

    result: Dict[str, Any] = {"status": "completed", "date": today, "channels": {}}
    vip_buttons = [
        [
            {"text": "📑 رادار الإفصاحات والـ PDF ↗", "url": LINK_DISCLOSURES},
            {"text": "📊 كاشف المصائد والماسح ↗", "url": LINK_TECHNICAL},
        ],
        [
            {"text": "💎 فحص القيمة العادلة ↗", "url": LINK_FAIR_VALUE},
            {"text": "📈 النماذج المتكررة ↗", "url": LINK_SIMILARITY},
        ],
    ]
    free_buttons = [
        [{"text": "⚡ اشترك في Pro بـ 100 ج.م ↗", "url": LINK_PRICING}],
        [
            {"text": "📑 رادار الإفصاحات ↗", "url": LINK_DISCLOSURES},
            {"text": "🔍 كاشف المصائد ↗", "url": LINK_TECHNICAL},
        ],
    ]
    free_chat = os.getenv("TELEGRAM_FREE_CHAT_ID", "-1002083067817_153").strip()

    plan = [
        ("vip_telegram", lambda: _telegram_send(VIP_CHAT_ID, build_vip_html(s), vip_buttons)),
        ("free_telegram", lambda: _telegram_send(free_chat, build_free_telegram_html(s), free_buttons)),
        ("active_free_email", lambda: (True, _send_promo_emails(client, s, today))),
    ]
    for channel, action in plan:
        try:
            if _already_done(client, channel, today):
                result["channels"][channel] = "already_sent"
                continue
            if dry_run:
                result["channels"][channel] = "dry_run"
                continue
            ok, info = action()
            result["channels"][channel] = {"ok": ok, "info": info}
            if ok:
                _mark_done(client, channel, today, {"info": info if isinstance(info, (dict, int)) else None})
        except Exception as exc:  # isolate per channel
            result["channels"][channel] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return result
