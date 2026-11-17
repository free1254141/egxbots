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

    # Extract EGX30 & EGX100 numbers and daily/5d % changes
    mkt_ctx = gate.get("market_context") or {}
    if not isinstance(mkt_ctx, dict) or not mkt_ctx.get("egx30"):
        mc_rows = _supabase_get("market_cache?cache_key=eq.market_status_Egypt&select=payload&limit=1") or []
        if mc_rows and isinstance(mc_rows[0], dict):
            mc_payload = mc_rows[0].get("payload") or {}
            if isinstance(mc_payload, dict):
                mkt_ctx = mc_payload.get("market_context") or mkt_ctx

    egx30 = mkt_ctx.get("egx30") if isinstance(mkt_ctx.get("egx30"), dict) else {}
    egx100 = mkt_ctx.get("egx100") if isinstance(mkt_ctx.get("egx100"), dict) else {}

    egx30_close = egx30.get("close") or gate.get("latest_close") or gate.get("latestClose")
    egx30_1d = egx30.get("return_1d_pct")
    egx30_5d = egx30.get("return_5d_pct")
    egx100_close = egx100.get("close")
    egx100_1d = egx100.get("return_1d_pct")
    egx100_5d = egx100.get("return_5d_pct")
    pct_vs_sma50 = gate.get("percent_vs_sma50") or gate.get("percentVsSma50")
    if pct_vs_sma50 is None and egx30_close and egx30.get("sma50"):
        pct_vs_sma50 = ((float(egx30_close) / float(egx30["sma50"])) - 1.0) * 100.0
    regime = gate.get("regime", "neutral")
    is_blocked = bool(gate.get("blocked"))
    gate_reason = gate.get("reason", "")

    def _fmt_idx_line(label: str, close_val: Any, ret1d: Any, ret5d: Any) -> str:
        if close_val is None:
            return f"{label}: غير متاح"
        parts = [f"{float(close_val):,.2f} نقطة"]
        if ret1d is not None:
            r1 = float(ret1d)
            parts.append(f"يومي: {'+' if r1 >= 0 else ''}{r1:.2f}%")
        if ret5d is not None:
            r5 = float(ret5d)
            parts.append(f"5 جلسات: {'+' if r5 >= 0 else ''}{r5:.2f}%")
        return f"{label}: {' | '.join(parts)}"

    egx30_line = _fmt_idx_line("EGX30", egx30_close, egx30_1d, egx30_5d)
    egx100_line = _fmt_idx_line("EGX100", egx100_close, egx100_1d, egx100_5d)

    # Top gainers
    sorted_gainers = sorted(market_rows, key=lambda x: float(x.get("change_pct") or 0), reverse=True)[:5]
    gainers_summary = ", ".join(f"#{g['symbol']} (+{float(g['change_pct']):.1f}%)" for g in sorted_gainers if g.get("symbol"))

    evidence_summary = (
        f"تاريخ الجلسة: {market_date}\n"
        f"حالة السوق العام: {regime} (مغلق أمام التوصيات الجديدة: {'نعم' if is_blocked else 'لا'})\n"
        f"سبب حالة السوق: {gate_reason}\n"
        f"أداء المؤشرات:\n- {egx30_line} (مقارنة بمتوسط 50 يوم: {float(pct_vs_sma50 or 0):.1f}%)\n- {egx100_line}\n"
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
                    "يجب أن تتضمن الرسالة قسم 'أداء المؤشرات' بأرقام إغلاق EGX30 وEGX100 ونسب التغير المرفقة بوضوح، "
                    "واتجاه الجلسة، واتساع الصعود والهبوط، وأبرز الأسهم الرابحة، وقرار فلتر التوصيات. "
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
                    if ("EGX30" not in content or (egx100_close is not None and "EGX100" not in content)) and (egx30_close is not None or egx100_close is not None):
                        idx_block = f"📌 أداء المؤشرات:\n• {egx30_line}\n• {egx100_line}"
                        content = f"{idx_block}\n\n{content}"
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
    ]
    if egx30_close is not None:
        lines.append(f"📌 <b>{egx30_line}</b>")
    if egx100_close is not None:
        lines.append(f"📌 <b>{egx100_line}</b>")
    lines.append(f"📈 اتساع حركة السوق: الصاعد <b>{pos_count}</b> سهم | الهابط <b>{neg_count}</b> سهم | الثابت <b>{unch_count}</b> سهم")
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
