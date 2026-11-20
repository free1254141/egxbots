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
LINK_DIVIDENDS = "https://egxbots.com/dividends"
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


def _load_upcoming_dividends_with_financials(client, limit: int = 8) -> List[Dict[str, Any]]:
    """Load upcoming/pending EGX dividends from market_cache and attach deterministic financial health."""
    try:
        rows = (
            client.table("market_cache")
            .select("payload")
            .eq("cache_key", "dividends_calendar_egx")
            .order("computed_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        payload = (rows[0].get("payload") if rows else {}) or {}
        all_divs = [
            d for d in (payload.get("dividends") or [])
            if isinstance(d, dict) and d.get("status") in ("upcoming", "pending_pay")
        ]
        if not all_divs:
            return []
        picked = all_divs[:limit]
        syms = [str(d.get("symbol") or "").upper() for d in picked if d.get("symbol")]
        fund_map: Dict[str, Dict[str, Any]] = {}
        if syms:
            f_rows = (
                client.table("stock_fundamentals")
                .select("symbol,data,fund_score")
                .eq("exchange", "EGX")
                .in_("symbol", syms)
                .limit(len(syms) + 5)
                .execute()
                .data
                or []
            )
            for fr in f_rows:
                if fr.get("symbol"):
                    fund_map[str(fr["symbol"]).upper()] = fr

        from api.agentic_chat.tools_execution import _extract_rich_fundamentals

        enriched: List[Dict[str, Any]] = []
        for d in picked:
            sym = str(d.get("symbol") or "").upper()
            fr = fund_map.get(sym) or {}
            rich = _extract_rich_fundamentals(
                fr.get("data") or {},
                fund_score=fr.get("fund_score"),
                close_price=d.get("close_price"),
                name=d.get("name_en") or d.get("name_ar") or sym,
            )
            diag = rich.get("fundamental_diagnosis") if isinstance(rich.get("fundamental_diagnosis"), dict) else {}
            enriched.append({
                **d,
                "verdict_ar": diag.get("verdict_ar") or "🟡 بيانات مالية قيد الاستكمال",
                "pe_ratio": rich.get("pe_ratio"),
                "roe_pct": rich.get("roe_pct"),
                "net_margin_pct": rich.get("net_margin_pct"),
                "debt_to_equity": rich.get("debt_to_equity"),
                "fund_score": rich.get("fund_score"),
            })
        return enriched
    except Exception as e:
        print(f"[REPORT_DISPATCH] Failed to load upcoming dividends: {e}")
        return []


def _dividends_lines(s: Dict[str, Any], limit: int = 6, detailed: bool = True) -> str:
    divs = s.get("dividends") or []
    if not divs:
        return "• لا توجد توزيعات كوبونات قادمة مسجلة حالياً."
    lines: List[str] = []
    for d in divs[:limit]:
        sym = d.get("symbol") or ""
        name_ar = d.get("name_ar") or sym
        amt = float(d.get("amount") or 0)
        amt_str = f"{amt:.3f}" if amt < 1 else f"{amt:.2f}"
        curr = d.get("currency_ar") or "ج.م"
        yld = d.get("yield_pct")
        yld_txt = f" (عائد <b>{float(yld):.2f}%</b>)" if yld is not None else ""
        ex_dt = d.get("ex_date") or "-"
        pay_dt = d.get("pay_date") or "يُعلن قريباً"
        verdict = str(d.get("verdict_ar") or "🟡 متوازن")
        short_verdict = verdict.split("—")[0].strip()

        if detailed:
            metrics_parts: List[str] = []
            if d.get("pe_ratio") is not None:
                metrics_parts.append(f"P/E: {float(d['pe_ratio']):.1f}x")
            if d.get("roe_pct") is not None:
                metrics_parts.append(f"ROE: {float(d['roe_pct']):.1f}%")
            if d.get("fund_score") is not None:
                metrics_parts.append(f"تقييم مالي: {int(round(float(d['fund_score'])))}/100")
            m_str = f" ({' | '.join(metrics_parts)})" if metrics_parts else ""
            lines.append(
                f"• <b>{sym}</b> ({name_ar}): كوبون <b>{amt_str} {curr}</b>{yld_txt}\n"
                f"  📅 بدون كوبون: <code>{ex_dt}</code> | الصرف: <code>{pay_dt}</code>\n"
                f"  💼 <i>{verdict}{m_str}</i>"
            )
        else:
            lines.append(
                f"• <b>{sym}</b> ({name_ar}): <b>{amt_str} {curr}</b>{yld_txt} | Ex: <code>{ex_dt}</code> — {short_verdict}"
            )
    return "\n".join(lines)


def build_stats(
    perf: Dict[str, Any],
    traps: Dict[str, Any],
    disclosures: Optional[List[Dict[str, Any]]] = None,
    dividends: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
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
        "dividends": dividends or [],
    }


def _top_block(s: Dict[str, Any]) -> str:
    t = s["top"]
    if not t.get("symbol"):
        return ""
    return (
        f"⭐ <b>نجم الجلسة: {t['symbol']}</b>\n"
        f"• سعر الإشارة: <b>{_f(t.get('signalClose'))} ج.م</b> | القمة: <b>{_f(t.get('nextHigh'))} ج (+{_f(t.get('intradayHighPct'))}%)</b>\n"
        f"• الإغلاق: <b>{_f(t.get('nextClose'))} ج (+{_f(t.get('retPct'))}%)</b> | حجم {_f(t.get('relativeVolume'), 1)}x\n"
    )


def _movers_lines(s: Dict[str, Any], limit: int = 4) -> str:
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


def _bear_lines(s: Dict[str, Any], limit: int = 4) -> str:
    return "\n".join(
        f"{i}. <b>{t.get('symbol')}</b> | إغلاق {_f(t.get('close'))} | دعم {_f(t.get('keyLevel'))} | "
        f"ثقة {_f(t.get('conviction'), 0)}% | حجم {_f(t.get('relativeVolume'), 1)}x"
        for i, t in enumerate(s["bear"][:limit], 1)
    ) or "• لا توجد نماذج ارتداد مؤكدة اليوم."


def _bull_lines(s: Dict[str, Any], limit: int = 3) -> str:
    return "\n".join(
        f"{i}. <b>{t.get('symbol')}</b> | إغلاق {_f(t.get('close'))} | مقاومة {_f(t.get('keyLevel'))} | "
        f"ثقة {_f(t.get('conviction'), 0)}%"
        for i, t in enumerate(s["bull"][:limit], 1)
    ) or "• لا توجد مصائد قمم نشطة اليوم."


def _disclosures_lines(s: Dict[str, Any], limit: int = 4) -> str:
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
        title_snippet = (d.get("title") or "")[:45]
        lines.append(f"• {icon} <b>{sym}</b>: {act_ar}{shares_txt} — <i>{title_snippet}...</i>")
    return "\n".join(lines)


def _record_line(s: Dict[str, Any]) -> str:
    if s["total"] <= 0:
        return ""
    return f"🚀 <b>{s['winners']} رابح من أصل {s['total']} إشارة ({s['winners'] / s['total'] * 100:.0f}%)</b>\n\n"


def _offer_html() -> str:
    from api.payment_common import current_pro_offer_copy

    price, is_open = current_pro_offer_copy()
    if is_open:
        headline = f"👑 <b>عرض المؤسسين: الباقة الشاملة Pro بـ {price} ج.م شهرياً (وتبدأ الباقات المنفصلة من 100 ج.م)!</b>\n"
    else:
        headline = "👑 <b>باقات EGX BOTS تبدأ من 100 ج.م شهرياً!</b>\n"
    return (
        headline
        + "🤖 <b>الشات الذكي فقط:</b> 100 ج.م/شهر (350 رسالة تحليلية + Vision AI + محفظة 15 سهماً)\n"
        + "📡 <b>تليجرام VIP فقط:</b> 100 ج.م/شهر (تنبيهات EGX + TASI اللحظية)\n"
        + f"👑 <b>الباقة الشاملة Pro:</b> {price} ج.م/شهر (الشات الذكي + قنوات VIP معاً بتوفير 50 ج.م)\n"
        + "💳 <i>الدفع عبر بوابة EasyKash المعتمدة (بطاقات بنكية محلية ودولية / محافظ إلكترونية / فوري)</i>"
    )


_OFFER_HTML = _offer_html()


def build_vip_html(s: Dict[str, Any]) -> str:
    from jobs.send_vip_telegram_daily_report import build_consensus_section
    us, sp, up = s["unusual_stat"], s["springs_stat"], s["upthrusts_stat"]
    consensus = build_consensus_section(
        s["as_of"],
        s.get("bear") or [],
        s.get("movers") or [],
        s.get("disclosures") or []
    )
    consensus_block = f"\n━━━━━━━━━━━━━━━━━━━\n\n{consensus}\n" if consensus else ""

    return (
        f"👑 <b>تقرير VIP الحصري | حصيلة الإشارات ومصائد الجلسة القادمة</b> 🇪🇬\n"
        f"📅 <b>جلسة التداول:</b> {s['as_of']}\n━━━━━━━━━━━━━━━━━━━\n\n"
        f"{_record_line(s)}{_top_block(s)}\n"
        f"📈 <b>أبرز الصاعدين من إشارات الرادار:</b>\n{_movers_lines(s, 4)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n🟢 <b>مصائد الدببة (Spring) — ارتداد تجميعي:</b>\n{_bear_lines(s, 4)}\n\n"
        f"🔴 <b>مصائد الثيران (Upthrust) — تجنب الشراء عند القمم:</b>\n{_bull_lines(s, 3)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n💎 <b>ثالثاً: فرص الأسهم بأقل من قيمتها العادلة:</b>\n"
        f"• <b>HRHO:</b> خصم 39% (+65% صعود متوقع).\n"
        f"• <b>OCPH:</b> خصم 28% مع تدفقات نقدية قوية.\n"
        f"• <b>AUTO:</b> خصم 38% ومضاعف ربحية منخفض.\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n📑 <b>رابعاً: رادار إفصاحات الشركات وتعاملات الداخليين:</b>\n"
        f"{_disclosures_lines(s, 4)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n💰 <b>خامساً: نشرة الكوبونات القادمة والحالة المالية لكل سهم:</b>\n"
        f"{_dividends_lines(s, 6, detailed=True)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n🎯 <b>السجل الموثق (40 جلسة):</b>\n"
        f"• انفجار 3 أيام: <b>{us.get('hitRate3d', '-')}%</b> ({us.get('events', '-')} إشارة)\n"
        f"• دقة Spring: <b>{sp.get('hitRate3d', '-')}%</b> | دقة Upthrust: <b>{up.get('winRate', '-')}%</b>\n\n"
        f"{consensus_block}"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>روابط الأدوات على المنصة:</b>\n"
        f"• تقويم الكوبونات (4 أسواق): {LINK_DIVIDENDS}\n"
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
        f"💰 <b>نشرة الكوبونات القريبة والحالة المالية:</b>\n{_dividends_lines(s, 4, detailed=False)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n{_offer_html()}\n\n"
        f"🔗 <b>استكشف الأدوات مجاناً:</b>\n"
        f"• تقويم الكوبونات القادمة: {LINK_DIVIDENDS}\n"
        f"• رادار الإفصاحات: {LINK_DISCLOSURES}\n"
        f"• كاشف المصائد: {LINK_TECHNICAL}"
    )


def build_email_html(s: Dict[str, Any], unsub_url: str, app_url: str) -> str:
    from api.payment_common import current_pro_offer_copy

    price, is_open = current_pro_offer_copy()
    email_offer_title = (
        f"عرض المؤسسين: الباقة الشاملة Pro بـ {price} ج.م/شهر (أو باقات منفصلة من 100 ج.م)"
        if is_open
        else f"باقات EGX BOTS: 100 ج.م للشات أو VIP — والباقة الشاملة بـ {price} ج.م"
    )

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
<div style="font-size:18px;font-weight:900;color:#fff;margin-bottom:10px;">{email_offer_title}</div>
<div style="font-size:13px;color:#d1d5db;margin-bottom:14px;line-height:1.8;">
🤖 <strong>الشات الذكي فقط:</strong> 100 ج.م/شهر (350 رسالة تحليلية + Vision AI + محفظة 15 سهماً)<br>
📡 <strong>تليجرام VIP فقط:</strong> 100 ج.م/شهر (تنبيهات EGX + TASI اللحظية + إشارات فورية)<br>
👑 <strong>الباقة الشاملة Pro:</strong> {price} ج.م/شهر (أو 750 ج.م/6 شهور • 1,350 ج.م/سنة — مع حفظ 50 / 100 ج.م للمؤسسين)<br>
💳 الدفع الآمن عبر بوابة EasyKash (بطاقات بنكية محلية ودولية مع 3D Secure / محافظ إلكترونية / فوري)</div>
<a href="{LINK_PRICING}" style="display:inline-block;background:#10b981;color:#000;font-weight:900;font-size:15px;padding:14px 30px;border-radius:12px;text-decoration:none;">⚡ استعراض الباقات والتفعيل عبر EasyKash ↗</a></div>
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
    token = (
        os.getenv("ARTORO_AI_BOT")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or os.getenv("TELEGRAM_TOKEN")
        or os.getenv("SUPPORT_BOT_TOKEN")
        or ""
    ).strip().strip('"').strip("'")
    if not token or not chat_raw:
        print(f"[REPORT_DISPATCH] Skipped Telegram send: token_found={bool(token)}, chat_raw={bool(chat_raw)}")
        return False, None
    chat_id, _, thread = chat_raw.partition("_")

    relay_url = (os.getenv("TELEGRAM_RELAY_URL") or "https://api.telegram.org").rstrip("/")
    bases = [relay_url] if relay_url != "https://api.telegram.org" else ["https://api.telegram.org"]
    if "https://api.telegram.org" not in bases:
        bases.append("https://api.telegram.org")

    split_marker = "🎯 <b>سادساً: رادار الإجماع الخوارزمي"

    # If within Telegram limit (4096 chars), send in one single complete message!
    if len(html) <= 4000 or split_marker not in html:
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": html[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": {"inline_keyboard": buttons},
        }
        if thread.isdigit():
            payload["message_thread_id"] = int(thread)

        for attempt in range(3):
            for base in bases:
                try:
                    resp = requests.post(f"{base}/bot{token}/sendMessage", json=payload, timeout=55)
                    data = resp.json()
                    if data.get("ok"):
                        msg_id = (data.get("result") or {}).get("message_id")
                        print(f"[REPORT_DISPATCH] Sent single message to {chat_id} via {base} (msg_id: {msg_id})")
                        return True, msg_id
                    else:
                        print(f"[REPORT_DISPATCH] Telegram API error via {base} on attempt {attempt+1}: {data}")
                except Exception as exc:
                    print(f"[REPORT_DISPATCH] Exception via {base} on attempt {attempt+1}: {exc}")
            time.sleep(2)
        return False, None

    # Multi-part fallback if ever exceeding 4000 characters
    parts = html.split(split_marker)
    part1 = parts[0].strip()
    part2 = (split_marker + parts[1]).strip()

    p1_payload: Dict[str, Any] = {
        "chat_id": chat_id, "text": part1, "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if thread.isdigit():
        p1_payload["message_thread_id"] = int(thread)

    p1_sent = False
    for attempt in range(3):
        try:
            r1 = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=p1_payload, timeout=55)
            d1 = r1.json()
            if d1.get("ok"):
                p1_sent = True
                break
            time.sleep(2)
        except Exception as e:
            print(f"[REPORT_DISPATCH] Part 1 dispatch error (attempt {attempt+1}): {e}")
            time.sleep(3)

    p2_payload: Dict[str, Any] = {
        "chat_id": chat_id, "text": part2, "parse_mode": "HTML",
        "disable_web_page_preview": True, "reply_markup": {"inline_keyboard": buttons},
    }
    if thread.isdigit():
        p2_payload["message_thread_id"] = int(thread)

    for attempt in range(3):
        try:
            resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=p2_payload, timeout=55)
            data = resp.json()
            if data.get("ok"):
                msg_id = (data.get("result") or {}).get("message_id")
                print(f"[REPORT_DISPATCH] Sent multi-part message to {chat_id} (msg_id: {msg_id})")
                return True, msg_id
            time.sleep(2)
        except Exception as e:
            print(f"[REPORT_DISPATCH] Part 2 dispatch error (attempt {attempt+1}): {e}")
            time.sleep(3)
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
    dividends = _load_upcoming_dividends_with_financials(client, limit=8)
    s = build_stats(perf, traps, disclosures, dividends)
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
            {"text": "💰 تقويم الكوبونات ↗", "url": LINK_DIVIDENDS},
        ],
    ]
    from api.payment_common import current_pro_offer_copy

    pro_price, _ = current_pro_offer_copy()
    free_buttons = [
        [{"text": f"⚡ الباقات تبدأ من 100 ج.م (والشاملة {pro_price} ج.م) ↗", "url": LINK_PRICING}],
        [
            {"text": "💰 تقويم الكوبونات ↗", "url": LINK_DIVIDENDS},
            {"text": "📑 رادار الإفصاحات ↗", "url": LINK_DISCLOSURES},
        ],
    ]
    free_chat = os.getenv("TELEGRAM_FREE_CHAT_ID", "-1002083067817_153").strip()

    plan = [
        ("vip_telegram", lambda: _telegram_send(VIP_CHAT_ID, build_vip_html(s), vip_buttons)),
        ("free_telegram", lambda: _telegram_send(free_chat, build_free_telegram_html(s), free_buttons)),
    ]
    if os.getenv("DAILY_PROMO_EMAILS_ENABLED", "").strip().lower() in ("1", "true", "yes"):
        plan.append(("active_free_email", lambda: (True, _send_promo_emails(client, s, today))))
    else:
        result["channels"]["active_free_email"] = "disabled"
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


def send_upcoming_dividends_bulletin(client, dry_run: bool = False) -> Dict[str, Any]:
    """Send a dedicated Upcoming Cash Dividends + Financial Health bulletin to VIP & Free Telegram channels."""
    today = _cairo_today()
    divs = _load_upcoming_dividends_with_financials(client, limit=10)
    if not divs:
        return {"ok": False, "reason": "no_upcoming_dividends"}

    s = {"as_of": today, "dividends": divs}
    vip_html = (
        f"👑 <b>نشرة VIP | الكوبونات النقدية القريبة والحالة المالية لكل سهم</b> 🇪🇬\n"
        f"📅 <b>التحديث:</b> {today}\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"{_dividends_lines(s, limit=10, detailed=True)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>تنويه: تخضع توزيعات البورصة المصرية لضريبة توزيعات 5% عند الصرف. "
        f"تُضاف الكوبونات تلقائياً وتظهر تنبيهاتها في محفظتك على المنصة.</i>\n"
        f"🔗 تقويم الكوبونات الكامل (مصر + السعودية + قطر + الإمارات): {LINK_DIVIDENDS}\n"
        f"⚠️ <i>بيانات إحصائية وتحليلية لأغراض البحث والتعليم فقط وليست توصية استثمارية.</i>"
    )
    free_html = (
        f"💰 <b>نشرة الكوبونات النقدية القريبة في البورصة المصرية والحالة المالية</b> 🇪🇬\n"
        f"📅 <b>التحديث:</b> {today}\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"{_dividends_lines(s, limit=8, detailed=True)}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"{_offer_html()}\n\n"
        f"🔗 <b>تقويم الكوبونات وحاسبة أرباحك مجاناً (4 أسواق):</b> {LINK_DIVIDENDS}\n"
        f"⚠️ <i>بيانات إحصائية وتحليلية لأغراض البحث والتعليم فقط وليست توصية استثمارية.</i>"
    )
    from api.payment_common import current_pro_offer_copy
    pro_price, _ = current_pro_offer_copy()
    vip_buttons = [
        [
            {"text": "💰 تقويم الكوبونات (4 أسواق) ↗", "url": LINK_DIVIDENDS},
            {"text": "💼 محفظتي وكوبوناتي ↗", "url": "https://egxbots.com/profile#portfolio"},
        ]
    ]
    free_buttons = [
        [{"text": "💰 تقويم الكوبونات وحاسبة أرباحك (4 أسواق) ↗", "url": LINK_DIVIDENDS}],
        [{"text": f"⚡ الباقات تبدأ من 100 ج.م (والشاملة {pro_price} ج.م) ↗", "url": LINK_PRICING}],
    ]
    free_chat = os.getenv("TELEGRAM_FREE_CHAT_ID", "-1002083067817_153").strip()

    if dry_run:
        return {"ok": True, "dry_run": True, "count": len(divs), "vip_preview": vip_html[:400]}

    vip_ok, vip_info = _telegram_send(VIP_CHAT_ID, vip_html, vip_buttons)
    free_ok, free_info = _telegram_send(free_chat, free_html, free_buttons)
    return {
        "ok": bool(vip_ok and free_ok),
        "count": len(divs),
        "vip": {"ok": vip_ok, "chat_id": VIP_CHAT_ID, "msg_id": vip_info},
        "free": {"ok": free_ok, "chat_id": free_chat, "msg_id": free_info},
    }
