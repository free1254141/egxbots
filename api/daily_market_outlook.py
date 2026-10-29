"""
Native Python Daily Market Outlook Generator.
Executes directly on Hugging Face Spaces / Python Backend without invoking Vercel Serverless Functions.
Queries market data from Supabase and prompts DeepSeek directly.
"""
import os
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

logger = logging.getLogger("daily_market_outlook")
logger.setLevel(logging.INFO)

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


def _get_supabase_config():
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or ""
    return url, key


def _supabase_get(endpoint: str, timeout: int = 10) -> Optional[Any]:
    url, key = _get_supabase_config()
    if not url or not key:
        return None
    full_url = f"{url}/rest/v1/{endpoint}"
    req = urllib.request.Request(
        full_url,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"[DAILY_OUTLOOK_PY] GET {endpoint} failed: {e}")
        return None


def compose_daily_market_outlook_native(
    market_date: str,
    gate: Dict[str, Any],
    recommendations_created: int = 0
) -> Optional[str]:
    """
    Composes the daily market outlook natively in Python using DeepSeek API directly.
    Eliminates the HTTP call to Vercel and prevents Serverless Function timeouts.
    """
    # 1. Fetch market indicators for date
    market_rows = _supabase_get(f"stock_technical_indicators?exchange=eq.EGX&date=eq.{market_date}&select=symbol,close,change_pct,volume,r_vol,rsi_14&limit=300") or []

    pos_count = sum(1 for r in market_rows if float(r.get("change_pct") or 0) > 0.1)
    neg_count = sum(1 for r in market_rows if float(r.get("change_pct") or 0) < -0.1)
    unch_count = len(market_rows) - pos_count - neg_count

    # Try to find EGX30 index or proxy
    egx30_close = gate.get("latest_close") or gate.get("latestClose")
    sma50 = gate.get("sma50")
    pct_vs_sma50 = gate.get("percent_vs_sma50") or gate.get("percentVsSma50")
    regime = gate.get("regime", "neutral")
    is_blocked = bool(gate.get("blocked"))
    gate_reason = gate.get("reason", "")

    # Top gainers
    sorted_gainers = sorted(market_rows, key=lambda x: float(x.get("change_pct") or 0), reverse=True)[:5]
    gainers_summary = ", ".join(f"#{g['symbol']} (+{float(g['change_pct']):.1f}%)" for g in sorted_gainers if g.get("symbol"))

    evidence_summary = (
        f"تاريخ الجلسة: {market_date}\n"
        f"حالة السوق العام: {regime} (مغلق أمام التوصيات الجديدة: {'نعم' if is_blocked else 'لا'})\n"
        f"سبب حالة السوق: {gate_reason}\n"
        f"المؤشر الرئيسي EGX30: {egx30_close if egx30_close else 'غير محدد'} (مقارنة بمتوسط 50 يوم: {pct_vs_sma50 or 0:.1f}%)\n"
        f"اتساع السوق: الصاعد {pos_count} | الهابط {neg_count} | الثابت {unch_count}\n"
        f"أبرز الأسهم صعوداً: {gainers_summary}\n"
        f"عدد التوصيات الصادرة اليوم: {recommendations_created}"
    )

    deepseek_key = (os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_OFFICIAL_API_KEY") or "").strip()

    if deepseek_key:
        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "أنت محرر التحليل الفني لأسواق المال في منصة EGX BOTS. "
                    "اكتب رسالة تيليجرام عربية موجزة ورشيقة بعنوان 'نظرة السوق اليومية'. "
                    "استخدم الأدلة والأرقام المرفقة فقط بدون اختلاق أرقام غير موجودة. "
                    "وضح اتجاه الجلسة، اتساع الصعود والهبوط، وأبرز الأسهم الرابحة، وقرار فلتر التوصيات. "
                    "لا تقدم نصائح استثمارية ملزمة بل قراءة تحليلية واضحة للمشتركين. "
                    "أخرج نص الرسالة منسقاً برموز تعبيرية راقية تناسب تليجرام."
                )
            },
            {
                "role": "user",
                "content": f"أنشئ ملخص نظرة السوق لجلسة {market_date} بناءً على هذه البيانات الحقيقية:\n{evidence_summary}"
            }
        ]

        req = urllib.request.Request(
            DEEPSEEK_API_URL,
            data=json.dumps({
                "model": "deepseek-chat",
                "temperature": 0.2,
                "max_tokens": 800,
                "messages": prompt_messages,
            }).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {deepseek_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if content:
                    logger.info("[DAILY_OUTLOOK_PY] Composed successfully via DeepSeek direct API.")
                    return content
        except Exception as e:
            logger.warning(f"[DAILY_OUTLOOK_PY] DeepSeek direct call failed: {e}. Using structured template fallback.")

    # High-quality deterministic analytical fallback if DeepSeek is offline or unconfigured
    regime_ar = "سيطرة شرائية إيجابية" if pos_count > neg_count else ("تصحيح وضغط بيعي" if neg_count > pos_count else "توازن وتدوير سيولة")
    lines = [
        f"📊 <b>نظرة السوق اليومية — EGX BOTS</b> ({market_date})",
        "━━━━━━━━━━━━━━━━━━━━",
        f"🏛️ <b>حالة المؤشر العام:</b> {regime_ar}",
        f"📈 اتساع حركة السوق: الصاعد <b>{pos_count}</b> سهم | الهابط <b>{neg_count}</b> سهم | الثابت <b>{unch_count}</b> سهم",
    ]
    if egx30_close:
        lines.append(f"📌 إغلاق EGX30: <b>{egx30_close:.2f}</b> نقطة")
    if gainers_summary:
        lines.append(f"🚀 أبرز أسهم الجلسة: {gainers_summary}")
    lines.append("")
    lines.append("⚖️ <b>إدارة المخاطر والفرص:</b>")
    if is_blocked:
        lines.append(f"• فلتر السوق الآلي: التوصيات الجديدة معلقة لحماية السيولة ({gate_reason or 'انتظار استقرار المؤشر'}).")
    else:
        lines.append(f"• فلتر السوق الآلي: وضع إيجابي نشط — تم رصد {recommendations_created} فرصة فنية اليوم.")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 <i>ملاحظة: هذا التقرير تحليلي مبني على خوارزميات رصد السيولة والبيانات الفنية ولا يمثل نصيحة بيع أو شراء مباشرة.</i>")
    return "\n".join(lines)
