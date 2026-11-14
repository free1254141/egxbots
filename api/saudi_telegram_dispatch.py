"""
Saudi Market (TASI / Tadawul) Telegram VIP Channel Dispatcher.
Formats and sends active Saudi recommendations (System 1 Medium-Term, System 2 Short Swings,
and System 3 Fast Scanner) in SAR (ر.س) to the Saudi VIP Telegram group (-1004397045436).
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from supabase import Client, create_client

RIYADH_TZ = ZoneInfo("Asia/Riyadh")


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
            "🌐 <a href=\"https://egxbots.com/scanner/backtests?market=tasi\">فتح لوحة توصيات السوق السعودي (TASI)</a>",
        ]
    )
    return "\n".join(lines)


def dispatch_saudi_open_recommendations(chat_id: Optional[str] = None) -> Dict[str, Any]:
    sb = get_saudi_supabase()
    target_chat_id = (chat_id or get_saudi_vip_chat_id()).strip()
    token = get_telegram_bot_token()

    res = (
        sb.table("scan_results")
        .select("symbol,name,status,signal,entry_price,last_close,target_price,stop_loss,precision,created_at")
        .eq("status", "open")
        .eq("is_public", True)
        .order("precision", desc=True)
        .limit(20)
        .execute()
    )
    open_rows = res.data or []
    text = build_saudi_open_recommendations_message(open_rows)

    candidate_ids = [target_chat_id]
    if target_chat_id.startswith("-100"):
        candidate_ids.append("-" + target_chat_id[4:])

    last_resp: Dict[str, Any] = {}
    for cid in candidate_ids:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": cid,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        data = resp.json()
        last_resp = data
        if data.get("ok"):
            return {
                "ok": True,
                "chat_id": cid,
                "sent_count": len(open_rows),
                "message_id": data.get("result", {}).get("message_id"),
            }

    return {
        "ok": False,
        "chat_id": target_chat_id,
        "sent_count": len(open_rows),
        "error": last_resp.get("description") or "Telegram send failed",
    }


if __name__ == "__main__":
    out = dispatch_saudi_open_recommendations()
    print(out)
