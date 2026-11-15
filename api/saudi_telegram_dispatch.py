"""
Saudi Market (TASI / Tadawul) Telegram VIP Channel Dispatcher.
Formats and sends active Saudi recommendations, Short Swings (System 2) alerts,
and Daily TASI Market Outlook in SAR (ر.س) strictly to the Saudi VIP Telegram group
(`SAUDI_TELEGRAM_PRO_CHAT_ID` / `-1004397045436`).

There is intentionally NO Free channel dispatch for the Saudi market.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from supabase import Client, create_client

from api.web_origin import get_web_origin

RIYADH_TZ = ZoneInfo("Asia/Riyadh")
SAUDI_COUNTRY = "Saudi Arabia"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


def _load_env() -> None:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(repo_root, "web", ".env.local"))
    load_dotenv(os.path.join(repo_root, ".env"))


def get_saudi_supabase() -> Client:
    _load_env()
    url = (os.getenv("SAUDI_SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SAUDI_SUPABASE_URL") or "").strip()
    key = (os.getenv("SAUDI_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("SAUDI_SUPABASE_URL / SAUDI_SUPABASE_SERVICE_ROLE_KEY missing")
    return create_client(url, key)


def get_saudi_vip_chat_id() -> str:
    _load_env()
    return (os.getenv("SAUDI_TELEGRAM_PRO_CHAT_ID") or "-1004397045436").strip()


def get_telegram_bot_token() -> str:
    _load_env()
    token = (os.getenv("ARTORO_AI_BOT") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("ARTORO_AI_BOT / TELEGRAM_BOT_TOKEN missing")
    return token


def _fmt_price(val: Any) -> str:
    try:
        num = float(val)
        return f"{num:,.2f}"
    except (TypeError, ValueError):
        return "—"


def _pct_diff(entry: Any, target: Any) -> str:
    try:
        e = float(entry)
        t = float(target)
        if e <= 0:
            return ""
        pct = ((t - e) / e) * 100.0
        sign = "+" if pct >= 0 else ""
        return f" ({sign}{pct:.1f}%)"
    except (TypeError, ValueError):
        return ""


def _send_telegram_message(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: Optional[str] = "HTML",
    dry_run: bool = False,
) -> Dict[str, Any]:
    target_chat_id = (chat_id or get_saudi_vip_chat_id()).strip()
    if dry_run:
        return {"ok": True, "dry_run": True, "chat_id": target_chat_id, "message_id": None}

    token = get_telegram_bot_token()
    candidate_ids = [target_chat_id]
    if target_chat_id.startswith("-100"):
        candidate_ids.append("-" + target_chat_id[4:])

    last_resp: Dict[str, Any] = {}
    for cid in candidate_ids:
        payload: Dict[str, Any] = {
            "chat_id": cid,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=15,
        )
        data = resp.json()
        last_resp = data
        if data.get("ok"):
            return {
                "ok": True,
                "chat_id": cid,
                "message_id": data.get("result", {}).get("message_id"),
            }

    return {
        "ok": False,
        "chat_id": target_chat_id,
        "error": last_resp.get("description") or "Telegram send failed",
    }


def _read_market_cache(sb: Client, cache_key: str) -> Dict[str, Any]:
    try:
        res = (
            sb.table("market_cache")
            .select("payload")
            .eq("cache_key", cache_key)
            .eq("country", SAUDI_COUNTRY)
            .maybe_single()
            .execute()
        )
        row = getattr(res, "data", None)
        if isinstance(row, dict) and isinstance(row.get("payload"), dict):
            return dict(row["payload"])
    except Exception:
        pass
    return {}


def _write_market_cache(sb: Client, cache_key: str, payload: Dict[str, Any]) -> None:
    try:
        sb.table("market_cache").upsert(
            {
                "cache_key": cache_key,
                "country": SAUDI_COUNTRY,
                "payload": payload,
                "computed_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="cache_key,country",
        ).execute()
    except Exception as exc:
        print(f"[SAUDI-TG] Failed to persist cache {cache_key}: {exc}")


def build_saudi_open_recommendations_message(open_rows: List[Dict[str, Any]]) -> str:
    now_str = datetime.now(RIYADH_TZ).strftime("%Y-%m-%d | %I:%M %p بتوقيت الرياض")
    lines: List[str] = [
        "🇸🇦 <b>TASI BOTS VIP — التوصيات المفتوحة للسوق السعودي (تداول)</b>",
        f"📅 <b>التاريخ:</b> {now_str}",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if not open_rows:
        lines.append("ℹ️ لا توجد صفقات مفتوحة حالياً مستوفية لشروط الدخول وحماية رأس المال.")
    else:
        for idx, row in enumerate(open_rows[:12], start=1):
            sym = str(row.get("symbol") or "").strip()
            name = str(row.get("name") or sym).strip()
            entry = row.get("entry_price") or row.get("last_close")
            last_close = row.get("last_close") or entry
            target = row.get("target_price")
            stop = row.get("stop_loss")
            prec = row.get("precision")
            prec_str = ""
            try:
                p_val = float(prec)
                if p_val <= 1.0:
                    p_val *= 100.0
                prec_str = f" | 🧠 الثقة: <b>{p_val:.0f}%</b>"
            except (TypeError, ValueError):
                pass

            lines.extend(
                [
                    f"\n{idx}️⃣ <b>{name} ({sym})</b>{prec_str}",
                    f"   💵 <b>الدخول:</b> {_fmt_price(entry)} ر.س | <b>الإغلاق الحالي:</b> {_fmt_price(last_close)} ر.س",
                    f"   🎯 <b>الهدف:</b> {_fmt_price(target)} ر.س{_pct_diff(entry, target)} | 🛑 <b>الوقف:</b> {_fmt_price(stop)} ر.س{_pct_diff(entry, stop)}",
                ]
            )

    lines.extend(
        [
            "\n━━━━━━━━━━━━━━━━━━━━",
            "🛡️ <i>إدارة المخاطر: الالتزام الصارم بوقف الخسارة وتفعيل تأمين التعادل الآلي. ليست نصيحة مالية.</i>",
            "🌐 <a href=\"https://egxbots.com/scanner/backtests?market=sa\">فتح لوحة توصيات السوق السعودي (TASI)</a>",
        ]
    )
    return "\n".join(lines)


def dispatch_saudi_open_recommendations(
    chat_id: Optional[str] = None,
    dedup_date: Optional[str] = None,
    sb: Optional[Client] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    client = sb or get_saudi_supabase()
    if dedup_date:
        state = _read_market_cache(client, "telegram_saudi_recs_sent")
        if dedup_date in set(state.get("dates") or []):
            return {"ok": True, "skipped": True, "reason": "already_sent_today", "date": dedup_date}

    res = (
        client.table("scan_results")
        .select("symbol,name,status,signal,entry_price,last_close,target_price,stop_loss,precision,created_at")
        .eq("status", "open")
        .eq("is_public", True)
        .order("precision", desc=True)
        .limit(20)
        .execute()
    )
    open_rows = res.data or []
    text = build_saudi_open_recommendations_message(open_rows)
    send_res = _send_telegram_message(text=text, chat_id=chat_id, parse_mode="HTML", dry_run=dry_run)
    send_res["sent_count"] = len(open_rows)

    if send_res.get("ok") and dedup_date and not dry_run:
        state = _read_market_cache(client, "telegram_saudi_recs_sent")
        dates = list(dict.fromkeys([*(state.get("dates") or []), dedup_date]))[-14:]
        _write_market_cache(
            client,
            "telegram_saudi_recs_sent",
            {"dates": dates, "last_date": dedup_date, "last_count": len(open_rows)},
        )
    return send_res


def build_saudi_short_swings_vip_entry_message(
    trades: List[Dict[str, Any]],
    as_of_date: str,
    web_origin: Optional[str] = None,
) -> str:
    origin = web_origin or get_web_origin()
    if trades and all(t.get("entry_kind") == "intraday_observed" for t in trades):
        lines = [
            "🇸🇦 ⚡ *دخول مضاربة قصيرة أثناء الجلسة (السوق السعودي — VIP)*",
            f"📅 `{as_of_date}`",
            "━━━━━━━━━━━━━━━━━━━━",
        ]
        for trade in trades:
            name = trade.get("name_ar") or trade.get("name") or trade["symbol"]
            lines.extend(
                [
                    f"🔹 *{name}* (`{trade['symbol']}`)",
                    f"• سعر الدخول المرصود: `{float(trade['entry_price']):.2f}` ر.س",
                    f"• وقت الرصد: `{trade.get('observed_at', as_of_date)}`",
                    f"• الوقف المبدئي (-4%): `{float(trade.get('stop_loss') or 0):.2f}` ر.س",
                    "• المتابعة تبدأ من وقت الرصد بدقة تنفيذ لحظية.",
                    "",
                ]
            )
        lines.append(f"🔗 {origin}/scanner/backtests?market=sa&tab=short_swings")
        return "\n".join(lines)

    lines = [
        "🇸🇦 ⚡ *إشارات مضاربة قصيرة جديدة — تداول VIP*",
        f"📅 رُصدت بنهاية جلسة: `{as_of_date}` | 🎯 *التنفيذ: مع افتتاح جلسة الغد*",
        "━━━━━━━━━━━━━━━━━━━━",
        "تم رصد اختراق قواعد سعرية مع انفجار سيولة (>140%) في السوق السعودي جاهزة للمتابعة غداً:",
        "",
    ]
    for t in trades:
        sym = t.get("symbol", "")
        name = t.get("name_ar") or t.get("name") or sym
        close_ref = float(t.get("reference_close") or t.get("entry_price") or t.get("current_price") or 0.0)
        sl_price = float(t.get("trailing_stop") or t.get("stop_loss") or (close_ref * 0.96))
        sl_pct = ((sl_price / close_ref) - 1.0) * 100.0 if close_ref > 0 else -4.0
        sig_type = t.get("trigger_type", "اختراق قمة مع انفجار سيولة")
        sector = t.get("sector", "عام")
        lines.extend(
            [
                f"🔹 *{name}* (`{sym}`) — قطاع {sector}",
                f"  • *سعر الإغلاق المرجعي:* `{close_ref:.2f}` ر.س",
                "  • *نقطة الدخول المقترحة:* مع افتتاح جلسة الغد (شرط عدم الافتتاح بفجوة > 2.0%)",
                f"  • *الوقف الحالي:* `{sl_price:.2f}` ر.س (`{sl_pct:.1f}%`) | الوقف المبدئي -4%",
                f"  • *تأمين الصفقة (Breakeven):* عند الوصول إلى `{close_ref * 1.05:.2f}` ر.س (+5.0%) يُرفع الوقف لحجز +0.8%.",
                f"  • *النموذج الفني:* {sig_type}",
                "",
            ]
        )
    lines.extend(
        [
            "━━━━━━━━━━━━━━━━━━━━",
            f"🔗 *لوحة المضاربة القصيرة (TASI):* {origin}/scanner/backtests?market=sa&tab=short_swings",
            "⚠️ *إدارة المخاطر:* التزم بنسبة مخاطرة 1-2% من المحفظة لكل صفقة.",
        ]
    )
    return "\n".join(lines)


def build_saudi_short_swings_vip_exit_message(
    exits: List[Dict[str, Any]],
    as_of_date: str,
    web_origin: Optional[str] = None,
) -> str:
    origin = web_origin or get_web_origin()
    lines = [
        "🇸🇦 🏁 *إغلاق صفقات مضاربة قصيرة — تداول VIP*",
        f"📅 جلسة: `{as_of_date}`",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    for e in exits:
        sym = e.get("symbol", "")
        name = e.get("name_ar") or e.get("name") or sym
        ret = float(e.get("return_pct") or 0.0)
        entry = float(e.get("entry_price") or 0.0)
        exit_p = float(e.get("exit_price") or 0.0)
        days = e.get("sessions") or e.get("holding_days") or 1
        reason = e.get("exit_reason") or e.get("reason") or "إغلاق حسب الخطة"
        sign = "+" if ret >= 0 else ""
        icon = "🟢" if ret > 0 else "🔴"
        lines.extend(
            [
                f"{icon} *{name}* (`{sym}`):",
                f"  • *النتيجة:* `{sign}{ret:.2f}%`",
                f"  • *الدخول:* `{entry:.2f}` ر.س | *الخروج:* `{exit_p:.2f}` ر.س",
                f"  • *مدة الاحتفاظ:* `{days}` جلسات | *السبب:* {reason}",
                "",
            ]
        )
    lines.extend(
        [
            "━━━━━━━━━━━━━━━━━━━━",
            f"🔗 *سجل الصفقات:* {origin}/scanner/backtests?market=sa&tab=short_swings",
        ]
    )
    return "\n".join(lines)


def dispatch_saudi_short_swings_vip(
    swings_payload: Dict[str, Any],
    phase: str = "close",
    chat_id: Optional[str] = None,
    sb: Optional[Client] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Send Saudi Short Swings entries & exits exclusively to Saudi VIP Telegram."""
    client = sb or get_saudi_supabase()
    as_of_date = str(swings_payload.get("as_of_date") or datetime.now(RIYADH_TZ).date().isoformat())[:10]
    cache_key = f"saudi_short_swings_sent_{as_of_date}"
    sent_state = _read_market_cache(client, cache_key)
    sent_entries = dict(sent_state.get("sent_entries") or {})
    sent_exits = dict(sent_state.get("sent_exits") or {})

    raw_entries = list(swings_payload.get("new_entries") or [])
    if not raw_entries and phase in {"morning", "midday"}:
        raw_entries = [
            t for t in (swings_payload.get("active_trades") or [])
            if str(t.get("entry_date") or t.get("signal_date") or "")[:10] == as_of_date
        ]
    raw_exits = list(swings_payload.get("new_exits") or [])
    if not raw_exits:
        raw_exits = [
            t for t in (swings_payload.get("closed_trades") or [])
            if str(t.get("exit_date") or "")[:10] == as_of_date
        ]

    entries_to_send = [t for t in raw_entries if t.get("symbol") and not sent_entries.get(t["symbol"])]
    exits_to_send: List[Dict[str, Any]] = []
    for ex in raw_exits:
        sym = ex.get("symbol")
        if not sym:
            continue
        exit_key = f"{sym}_{ex.get('entry_date') or ex.get('exit_date') or as_of_date}"
        if not sent_exits.get(exit_key):
            exits_to_send.append({**ex, "_exit_key": exit_key})

    entries_sent = 0
    exits_sent = 0
    errors: List[str] = []

    if entries_to_send:
        msg = build_saudi_short_swings_vip_entry_message(entries_to_send, as_of_date)
        res = _send_telegram_message(text=msg, chat_id=chat_id, parse_mode="Markdown", dry_run=dry_run)
        if res.get("ok"):
            entries_sent = len(entries_to_send)
            for t in entries_to_send:
                sent_entries[t["symbol"]] = True
        else:
            errors.append(str(res.get("error") or "entry_send_failed"))

    if exits_to_send:
        msg = build_saudi_short_swings_vip_exit_message(exits_to_send, as_of_date)
        res = _send_telegram_message(text=msg, chat_id=chat_id, parse_mode="Markdown", dry_run=dry_run)
        if res.get("ok"):
            exits_sent = len(exits_to_send)
            for ex in exits_to_send:
                sent_exits[ex["_exit_key"]] = True
        else:
            errors.append(str(res.get("error") or "exit_send_failed"))

    if (entries_sent or exits_sent) and not dry_run:
        _write_market_cache(
            client,
            cache_key,
            {
                "sent_entries": sent_entries,
                "sent_exits": sent_exits,
                "last_phase": phase,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            },
        )

    return {
        "ok": len(errors) == 0,
        "vip_only": True,
        "as_of_date": as_of_date,
        "entries_sent": entries_sent,
        "exits_sent": exits_sent,
        "skipped_duplicates": max(0, (len(raw_entries) - len(entries_to_send)) + (len(raw_exits) - len(exits_to_send))),
        "errors": errors,
    }


def compose_saudi_market_outlook(
    market_date: str,
    market_status: Dict[str, Any],
    ind_rows: List[Dict[str, Any]],
    recommendations_count: int = 0,
) -> str:
    """Compose Arabic daily Tadawul / TASI VIP outlook via DeepSeek with deterministic fallback."""
    breadth = market_status.get("breadth") or {}
    tasi_metrics = market_status.get("tasi_metrics") or {}
    regime = market_status.get("regime", "neutral")
    reject_buys = bool(market_status.get("reject_buys"))

    pos_count = int(breadth.get("advancers") or sum(1 for r in ind_rows if float(r.get("change_pct") or 0) > 0.1))
    neg_count = int(breadth.get("decliners") or sum(1 for r in ind_rows if float(r.get("change_pct") or 0) < -0.1))
    unch_count = int(breadth.get("unchanged") or max(0, len(ind_rows) - pos_count - neg_count))
    ret_1d = tasi_metrics.get("return_1d_pct")
    ret_5d = tasi_metrics.get("return_5d_pct")

    sorted_gainers = sorted(ind_rows, key=lambda x: float(x.get("change_pct") or 0), reverse=True)[:5]
    gainers_summary = ", ".join(
        f"{g.get('symbol')} (+{float(g.get('change_pct') or 0):.1f}% | {float(g.get('close') or 0):.2f} ر.س)"
        for g in sorted_gainers
        if g.get("symbol")
    )

    deepseek_key = (os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_OFFICIAL_API_KEY") or "").strip()
    if deepseek_key:
        evidence = (
            f"تاريخ جلسة تداول: {market_date}\n"
            f"اتجاه السوق العام (Regime): {regime} | تعليق التوصيات الجديدة: {'نعم' if reject_buys else 'لا'}\n"
            f"تغير مؤشر تاسي المتساوي الأوزان: يومي {ret_1d or 0:.2f}% | 5 جلسات {ret_5d or 0:.2f}%\n"
            f"اتساع السوق: الصاعد {pos_count} | الهابط {neg_count} | الثابت {unch_count}\n"
            f"أبرز الأسهم صعوداً: {gainers_summary or 'لا يوجد'}\n"
            f"عدد التوصيات المفتوحة المتابعة: {recommendations_count}"
        )
        req = urllib.request.Request(
            DEEPSEEK_API_URL,
            data=json.dumps(
                {
                    "model": "deepseek-chat",
                    "temperature": 0.2,
                    "max_tokens": 700,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "أنت محرر التحليل الفني للسوق السعودي (تداول / تاسي) في منصة EGX BOTS VIP. "
                                "اكتب رسالة تليجرام عربية موجزة ورشيقة بعنوان 'نظرة السوق السعودي اليومية'. "
                                "استخدم الأرقام المرفقة فقط بالريال السعودي (ر.س) ولا تختلق أرقاماً. "
                                "وضّح اتجاه الجلسة واتساع السوق وأبرز الأسهم الصاعدة وحالة فلتر المخاطر بدون تقديم نصيحة استثمارية ملزمة."
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"أنشئ تقرير تليجرام VIP لجلسة تداول {market_date} من البيانات التالية:\n{evidence}",
                        },
                    ],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {deepseek_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if content:
                    return content
        except Exception as exc:
            print(f"[SAUDI-OUTLOOK] DeepSeek unavailable, using structured fallback: {exc}")

    regime_map = {
        "bull": "زخم شرائي إيجابي",
        "neutral": "توازن وتدوير سيولة انتقائي",
        "bear": "ضغط بيعي وتصحيح",
        "panic": "تراجع حاد — حماية السيولة أولوية",
    }
    lines = [
        f"🇸🇦 📊 <b>نظرة السوق السعودي اليومية — TASI VIP</b> ({market_date})",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🏛️ <b>حالة السوق:</b> {regime_map.get(regime, regime)}",
        f"📈 <b>اتساع التداولات:</b> صاعد <b>{pos_count}</b> | هابط <b>{neg_count}</b> | ثابت <b>{unch_count}</b>",
    ]
    if ret_1d is not None:
        sign = "+" if float(ret_1d) >= 0 else ""
        lines.append(f"📌 <b>أداء الجلسة (متساوي الأوزان):</b> <b>{sign}{float(ret_1d):.2f}%</b>")
    if gainers_summary:
        lines.append(f"🚀 <b>أبرز الأسهم صعوداً:</b> {gainers_summary}")
    lines.extend(
        [
            "",
            "⚖️ <b>فلتر المخاطر والفرص:</b>",
            "• الفرص الجديدة مقيدة مؤقتاً لحماية رأس المال حتى تحسن الاتجاه." if reject_buys else f"• الوضع نشط — {recommendations_count} فرصة مفتوحة قيد المتابعة بالريال السعودي (ر.س).",
            "━━━━━━━━━━━━━━━━━━━━",
            "💡 <i>تحليل فني آلي للبيانات ولا يمثل توصية بيع أو شراء مباشرة.</i>",
        ]
    )
    return "\n".join(lines)


def dispatch_saudi_market_outlook_vip(
    market_status: Dict[str, Any],
    ind_rows: List[Dict[str, Any]],
    recommendations_count: int = 0,
    market_date: Optional[str] = None,
    chat_id: Optional[str] = None,
    sb: Optional[Client] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    client = sb or get_saudi_supabase()
    target_date = str(market_date or market_status.get("latest_date") or datetime.now(RIYADH_TZ).date().isoformat())[:10]
    state = _read_market_cache(client, "telegram_saudi_market_outlook_sent")
    if target_date in set(state.get("dates") or []):
        return {"ok": True, "skipped": True, "reason": "already_sent_today", "date": target_date}

    text = compose_saudi_market_outlook(target_date, market_status, ind_rows, recommendations_count)
    # Note: DeepSeek output can be plain text / Markdown-lite, so send HTML only for deterministic template
    use_html = "<b>" in text
    res = _send_telegram_message(text=text, chat_id=chat_id, parse_mode="HTML" if use_html else None, dry_run=dry_run)
    res["date"] = target_date

    if res.get("ok") and not dry_run:
        dates = list(dict.fromkeys([*(state.get("dates") or []), target_date]))[-14:]
        _write_market_cache(client, "telegram_saudi_market_outlook_sent", {"dates": dates, "last_date": target_date})
    return res


if __name__ == "__main__":
    out = dispatch_saudi_open_recommendations()
    print(out)
