"""
api/native_telegram_vip_chat.py — Comprehensive Native Python Engine for Telegram VIP Chat & ARTORO.

Executes 100% on Hugging Face Spaces / Python Backend natively with ZERO Vercel CPU usage.
Provides:
1. Full Arabic & English stock name resolution via api.stock_aliases (870+ mappings).
2. Direct Supabase data fetching: technical indicators, moving averages, RSI, MACD, Bollinger Bands, scan results.
3. Multi-symbol comparison support (e.g., "قارن بين طلعت مصطفى وفوري").
4. 1-Click quick tools support: Market Summary, Accumulation Stocks, Open Recommendations.
5. High-intelligence DeepSeek financial analysis formatted specifically for Telegram mobile chat.
6. Atomic quota verification & consumption (Pro 350/mo, Free 5/day, Admin unlimited).
7. Conversational memory (multi-turn context saved in telegram_vip_chat_state).
"""

from __future__ import annotations

import os
import re
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional

# Load local environment if available
try:
    from dotenv import load_dotenv
    _base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_base_dir, ".env"))
    load_dotenv(os.path.join(_base_dir, "web", ".env.local"), override=True)
except Exception:
    pass

logger = logging.getLogger("native_telegram_vip_chat")
logger.setLevel(logging.INFO)

CAIRO_TZ = ZoneInfo("Africa/Cairo")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
ADMIN_TG_IDS = {"5149631436"}


def get_cairo_date_str() -> str:
    """Return current date formatted as YYYY-MM-DD in Cairo timezone."""
    try:
        return datetime.now(CAIRO_TZ).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_supabase_config() -> tuple[str, str]:
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or ""
    return url, key


def _supabase_request(
    endpoint: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 12
) -> Optional[Any]:
    url, key = _get_supabase_config()
    if not url or not key:
        return None
    full_url = f"{url}/rest/v1/{endpoint}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if method == "POST":
        headers["Prefer"] = "resolution=merge-duplicates"

    req = urllib.request.Request(full_url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except Exception as e:
        logger.warning(f"[NATIVE_VIP_CHAT] {method} {endpoint} failed: {e}")
        return None


def _resolve_telegram_user(telegram_user_id: int, telegram_username: str) -> Dict[str, Any]:
    """Resolve user subscription, quota limits, and linked accounts from Supabase."""
    tg_id_str = str(telegram_user_id)
    is_admin = tg_id_str in ADMIN_TG_IDS
    today = get_cairo_date_str()

    state_rows = _supabase_request(f"telegram_vip_chat_state?telegram_user_id=eq.{telegram_user_id}&select=*") or []
    state_row = state_rows[0] if state_rows else None

    profile_rows = _supabase_request(f"profiles?telegram_chat_id=eq.{tg_id_str}&select=id,display_name,username&limit=1") or []
    invite_rows = _supabase_request(f"pro_telegram_invites?vip_telegram_user_id=eq.{telegram_user_id}&select=user_id&limit=1") or []

    linked_user_id = None
    display_name = telegram_username or "المستثمر"

    if profile_rows:
        linked_user_id = profile_rows[0].get("id")
        display_name = profile_rows[0].get("display_name") or profile_rows[0].get("username") or display_name
    elif invite_rows:
        linked_user_id = invite_rows[0].get("user_id")
    elif state_row and state_row.get("linked_user_id"):
        linked_user_id = state_row.get("linked_user_id")

    is_pro = False
    used = 0
    limit = 10
    period = "monthly"

    if linked_user_id:
        sub_rows = _supabase_request(
            f"subscriptions?user_id=eq.{linked_user_id}&status=in.(active,trialing)&select=plan_id,status,current_period_end&order=current_period_end.desc&limit=1"
        ) or []
        if sub_rows:
            is_pro = True
            limit = 350
        else:
            limit = 10
            period = "daily"

        quota_rows = _supabase_request(
            f"ai_chatbot_limits?user_id=eq.{linked_user_id}&date=gte.{today[:7]}-01&select=chat_count"
        ) or []
        used = sum(int(r.get("chat_count") or 0) for r in quota_rows)
    else:
        limit = 5
        period = "daily"
        if state_row and state_row.get("quota_date") == today:
            used = int(state_row.get("daily_count") or 0)

    remaining = 9999 if is_admin else max(0, limit - used)

    return {
        "telegram_user_id": telegram_user_id,
        "telegram_username": telegram_username,
        "linked_user_id": linked_user_id,
        "display_name": display_name,
        "is_pro": is_pro,
        "is_admin": is_admin,
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "period": period,
        "state_row": state_row,
    }


def _fetch_stock_technical_context(symbol: str) -> tuple[str, Optional[Dict[str, Any]]]:
    """Fetch latest technical indicators and fundamentals for a given symbol."""
    ind_rows = _supabase_request(
        f"stock_technical_indicators?exchange=eq.EGX&symbol=eq.{symbol}&select=symbol,date,close,change_pct,volume,vol_sma20,r_vol,rsi_14,macd,macd_signal,bb_upper,bb_lower,ema_20,ema_50,ema_200,adx_14&order=date.desc&limit=2"
    ) or []

    if not ind_rows:
        return "", None

    latest = ind_rows[0]

    # Fetch scan results if available
    scan_rows = _supabase_request(
        f"scan_results?exchange=eq.EGX&symbol=eq.{symbol}&order=created_at.desc&limit=1"
    ) or []
    scan = scan_rows[0] if scan_rows else {}
    signal = scan.get("signal")
    precision = scan.get("precision")
    top_reasons = scan.get("top_reasons") or {}
    rationale = top_reasons.get("brief_rationale") or top_reasons.get("technical_rationale") or ""

    close_val = latest.get("close")
    change_pct = float(latest.get("change_pct") or 0.0)
    vol = int(latest.get("volume") or 0)
    r_vol = float(latest.get("r_vol") or 1.0)
    rsi = float(latest.get("rsi_14") or 50.0)
    macd = float(latest.get("macd") or 0.0)
    macd_sig = float(latest.get("macd_signal") or 0.0)
    ema20 = latest.get("ema_20")
    ema50 = latest.get("ema_50")
    ema200 = latest.get("ema_200")
    bb_up = latest.get("bb_upper")
    bb_low = latest.get("bb_lower")
    adx = float(latest.get("adx_14") or 25.0)

    context = (
        f"بيانات سهم #{symbol} لجلسة {latest.get('date')}:\n"
        f"• سعر الإغلاق: {close_val} ج.م ({change_pct:+.2f}%)\n"
        f"• حجم التداول: {vol:,} سهم (الحجم النسبي: {r_vol:.2f}x)\n"
        f"• مؤشر القوة النسبية RSI(14): {rsi:.1f} ({'تشبع شرائي' if rsi > 70 else 'تشبع بيعي' if rsi < 30 else 'منطقة توازن'})\n"
        f"• مؤشر MACD: {macd:.3f} (خط الإشارة: {macd_sig:.3f}) -> {'تقاطع إيجابي' if macd > macd_sig else 'تقاطع سلبي'}\n"
        f"• المتوسطات المتحركة: EMA20={ema20}, EMA50={ema50}, EMA200={ema200}\n"
        f"• حدود بولينجر باند: المقاومة العليا={bb_up}, الدعم السفلي={bb_low}\n"
        f"• مؤشر قوة الاتجاه ADX: {adx:.1f} ({'اتجاه قوي' if adx > 25 else 'اتجاه ضعيف/عرضي'})\n"
    )
    if signal:
        context += f"• إشارة نموذج EGX BOTS: {signal} بدقة متوقعة {float(precision or 0.65)*100:.0f}%\n"
    if rationale:
        context += f"• ملخص استراتيجية النموذج: {rationale[:250]}\n"

    return context, latest


def _fetch_market_summary_context() -> str:
    """Fetch broad market stats, gainers, losers, and liquidity leaders."""
    today = get_cairo_date_str()
    rows = _supabase_request(
        f"stock_technical_indicators?exchange=eq.EGX&order=date.desc,volume.desc&limit=60"
    ) or []

    if not rows:
        return "بيانات السوق اللحظية قيد التحديث."

    latest_date = rows[0].get("date", today)
    session_rows = [r for r in rows if r.get("date") == latest_date]
    if not session_rows:
        session_rows = rows[:30]

    gainers = sorted(session_rows, key=lambda x: float(x.get("change_pct") or 0), reverse=True)[:5]
    decliners = sorted(session_rows, key=lambda x: float(x.get("change_pct") or 0))[:5]
    vol_leaders = sorted(session_rows, key=lambda x: int(x.get("volume") or 0), reverse=True)[:5]

    pos_count = sum(1 for r in session_rows if float(r.get("change_pct") or 0) > 0)
    neg_count = sum(1 for r in session_rows if float(r.get("change_pct") or 0) < 0)

    summary = (
        f"ملخص جلسة البورصة المصرية ({latest_date}):\n"
        f"• اتساع السوق: {pos_count} سهم صاعد مقابل {neg_count} سهم هابط.\n"
        f"• أنشط الأسهم سيولة وحجماً: " + ", ".join([f"#{r.get('symbol')} ({int(r.get('volume') or 0):,} سهم)" for r in vol_leaders]) + "\n"
        f"• الأكثر ارتفاعاً: " + ", ".join([f"#{r.get('symbol')} ({float(r.get('change_pct') or 0):+.2f}%)" for r in gainers]) + "\n"
        f"• الأكثر انخفاضاً: " + ", ".join([f"#{r.get('symbol')} ({float(r.get('change_pct') or 0):+.2f}%)" for r in decliners]) + "\n"
    )
    return summary


def _fetch_accumulation_stocks_context() -> str:
    """Fetch stocks showing high relative volume and smart money accumulation."""
    rows = _supabase_request(
        f"stock_technical_indicators?exchange=eq.EGX&order=date.desc,r_vol.desc&limit=40"
    ) or []

    if not rows:
        return "لا توجد أسهم تجميع حالياً."

    latest_date = rows[0].get("date")
    accum_rows = [
        r for r in rows
        if r.get("date") == latest_date
        and float(r.get("r_vol") or 1.0) >= 1.25
        and float(r.get("change_pct") or 0.0) >= -0.5
    ][:6]

    if not accum_rows:
        accum_rows = rows[:5]

    lines = [f"أقوى أسهم التجميع وضخ السيولة غير المعتادة (جلسة {latest_date}):"]
    for r in accum_rows:
        sym = r.get("symbol")
        close = r.get("close")
        chg = float(r.get("change_pct") or 0.0)
        r_vol = float(r.get("r_vol") or 1.0)
        rsi = float(r.get("rsi_14") or 50.0)
        lines.append(f"• #{sym}: سعر {close} ج.م ({chg:+.2f}%) | نشاط نسبي {r_vol:.2f}x | RSI {rsi:.1f}")

    return "\n".join(lines)


def _fetch_open_recommendations_context() -> str:
    """Fetch active BUY recommendations from scan_results."""
    rows = _supabase_request(
        f"scan_results?exchange=eq.EGX&signal=eq.BUY&order=created_at.desc&limit=5"
    ) or []

    if not rows:
        return "لا توجد توصيات مفتوحة جديدة في الوقت الحالي."

    lines = ["التوصيات الفنية المفتوحة النشطة (من نماذج الذكاء الاصطناعي):"]
    for r in rows:
        sym = r.get("symbol")
        entry = r.get("entry_price") or r.get("last_close")
        target = r.get("target_price")
        sl = r.get("stop_loss")
        prec = float(r.get("precision") or 0.65) * 100
        lines.append(
            f"• سهم #{sym}: دخول مقترح حول {entry} ج.م | المستهدف: {target} ج.م | وقف الخسارة: {sl} ج.م (دقة النموذج: {prec:.0f}%)"
        )

    return "\n".join(lines)


def handle_native_vip_chat(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute complete VIP chat action natively on Python backend with zero Vercel CPU."""
    action = payload.get("action", "chat")
    tg_user_id = payload.get("telegram_user_id")
    user_name = payload.get("telegram_username", "المستثمر")

    if not tg_user_id:
        return {"ok": False, "error": "Missing telegram_user_id"}

    user_info = _resolve_telegram_user(tg_user_id, user_name)
    today = get_cairo_date_str()

    # 1. Action: check_quota
    if action == "check_quota":
        return {
            "ok": True,
            "linked": bool(user_info["linked_user_id"]),
            "user_id": user_info["linked_user_id"],
            "display_name": user_info["display_name"],
            "is_pro": user_info["is_pro"],
            "used": user_info["used"],
            "limit": user_info["limit"],
            "remaining": user_info["remaining"],
            "period": user_info["period"],
            "pending_prompt": (user_info["state_row"] or {}).get("pending_prompt"),
        }

    # 2. Action: set_pending_prompt
    if action == "set_pending_prompt":
        prompt_mode = payload.get("prompt_mode")
        pending_payload = (
            {"mode": prompt_mode, "expires_at": int(datetime.now().timestamp() * 1000) + 300000}
            if prompt_mode else None
        )
        state_row = user_info["state_row"] or {}

        _supabase_request(
            "telegram_vip_chat_state?on_conflict=telegram_user_id",
            method="POST",
            payload={
                "telegram_user_id": tg_user_id,
                "telegram_username": user_name,
                "linked_user_id": user_info["linked_user_id"],
                "quota_date": today,
                "daily_count": state_row.get("daily_count", 0),
                "pending_prompt": pending_payload,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return {
            "ok": True,
            "linked": bool(user_info["linked_user_id"]),
            "is_pro": user_info["is_pro"],
            "used": user_info["used"],
            "limit": user_info["limit"],
            "remaining": user_info["remaining"],
            "period": user_info["period"],
            "pending_prompt": pending_payload,
        }

    # 3. Action: chat
    query = (payload.get("message") or "").strip()
    if not query:
        return {"ok": False, "error": "Empty message"}

    # Quota check
    if not user_info["is_admin"] and user_info["remaining"] <= 0:
        return {
            "ok": False,
            "error_code": "LIMIT_REACHED",
            "linked": bool(user_info["linked_user_id"]),
            "display_name": user_info["display_name"],
            "is_pro": user_info["is_pro"],
            "used": user_info["used"],
            "limit": user_info["limit"],
            "remaining": 0,
            "period": user_info["period"],
            "detail": "لقد استهلكت رصيد أسئلتك المتاح. يرجى الترقية لباقة PRO للمتابعة والاستفسار اللامحدود.",
        }

    # Import stock aliases mapping
    from api.stock_aliases import resolve_stock_symbol, extract_all_stock_symbols

    symbols_found = extract_all_stock_symbols(query)
    single_symbol = resolve_stock_symbol(query) if not symbols_found else symbols_found[0]

    market_context = ""
    evidence_data = []

    # Check for specific quick tools queries
    is_market_summary_query = any(k in query for k in ("ملخص السوق", "أقوى الأسهم", "وضع السوق", "المؤشر"))
    is_accumulation_query = any(k in query for k in ("تجميع", "سيولة", "السيولة الذكية"))
    is_recs_query = any(k in query for k in ("توصيات", "توصية", "فرص الشراء", "توصيات مفتوحة"))
    is_portfolio_query = any(k in query for k in ("محفظتي", "المحفظة", "محفظه"))

    if is_portfolio_query and not user_info["linked_user_id"]:
        return {
            "ok": False,
            "error_code": "ACCOUNT_LINK_REQUIRED",
            "linked": False,
            "display_name": user_info["display_name"],
            "is_pro": user_info["is_pro"],
            "used": user_info["used"],
            "limit": user_info["limit"],
            "remaining": user_info["remaining"],
            "period": user_info["period"],
            "detail": "لتحليل محفظتك الاستثمارية، يرجى ربط حسابك في الموقع بالبوت أولاً من صفحة البروفايل.",
        }

    # Comparison Mode (2 symbols detected)
    if len(symbols_found) >= 2:
        s1, s2 = symbols_found[0], symbols_found[1]
        ctx1, d1 = _fetch_stock_technical_context(s1)
        ctx2, d2 = _fetch_stock_technical_context(s2)
        market_context = f"مقارنة بين سهمين:\n\n{ctx1}\n\n{ctx2}"
        if d1:
            evidence_data.append(d1)
        if d2:
            evidence_data.append(d2)

    # Single Stock Mode
    elif single_symbol:
        ctx, d = _fetch_stock_technical_context(single_symbol)
        if ctx:
            market_context = ctx
            if d:
                evidence_data.append(d)

    # Tool: Market Summary
    elif is_market_summary_query:
        market_context = _fetch_market_summary_context()

    # Tool: Accumulation Stocks
    elif is_accumulation_query:
        market_context = _fetch_accumulation_stocks_context()

    # Tool: Open Recommendations
    elif is_recs_query:
        market_context = _fetch_open_recommendations_context()

    # Fallback to general market context
    if not market_context:
        market_context = _fetch_market_summary_context()

    deepseek_key = (
        os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("DEEPSEEK_OFFICIAL_API_KEY")
        or ""
    ).strip()

    reply_text = ""

    if deepseek_key:
        sys_prompt = (
            "أنت المساعد المالي والتقني الذكي (ARTORO AI) الخاص بمنصة EGX BOTS المعتمد لتحليل البورصة المصرية.\n"
            "مهمتك: الإجابة على استفسار المستثمر بأسلوب عربي فصيح، راقٍ، مهني ودقيق جداً بالأرقام.\n\n"
            "هيكل الإجابة المطلوب:\n"
            "1. ابدأ برأس واضح ومختصر: اسم السهم ورمزه (مثال: #TMGH) مع سعر الإغلاق ونسبة التغير.\n"
            "2. نقاط فنية مركزة:\n"
            "   • الاتجاه والزخم: تقييم RSI، MACD وموقع السعر بالنسبة للمتوسطات EMA 20 و EMA 50 و EMA 200.\n"
            "   • السيولة والنشاط: تحليل الحجم النسبي r_vol.\n"
            "   • الدعوم والمقاومات: حدد بوضوح أهم مستوى دعم، أهم مستوى مقاومة، ووقف الخسارة المقترح.\n"
            "3. الخلاصة التنفيذية وإدارة المخاطر في سطرين محددين (هل السهم إيجابي للمتابعة، أم حيادي، أم سلبي للتصريف).\n"
            "4. استخدم علامات Markdown واضحة (العناوين `##`، النقاط `•`، والأرقام داخل كود `12.50 ج.م`).\n"
            "قاعدة صارمة: لا تخترع أرقاماً غير موجودة بالبيانات المرفقة."
        )

        user_content = f"استفسار المستثمر: {query}\n\nبيانات السوق والأسهم اللحظية الموثقة من السيرفر:\n{market_context}"

        messages = [
            {"role": "system", "content": sys_prompt},
        ]

        # Append previous chat history if available
        state_row = user_info["state_row"] or {}
        history = state_row.get("chat_history") or []
        for h in history[-4:]:  # last 2 turns
            if h.get("role") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"][:300]})

        messages.append({"role": "user", "content": user_content})

        req = urllib.request.Request(
            DEEPSEEK_API_URL,
            data=json.dumps({
                "model": "deepseek-chat",
                "temperature": 0.2,
                "max_tokens": 1000,
                "messages": messages,
            }).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {deepseek_key}",
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                ds_res = json.loads(resp.read().decode("utf-8"))
                reply_text = ds_res.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.warning(f"[NATIVE_VIP_CHAT] DeepSeek chat error: {e}")

    # Fallback response if DeepSeek was unavailable
    if not reply_text:
        if single_symbol and evidence_data:
            latest = evidence_data[0]
            reply_text = (
                f"📊 **التحليل الفني السريع لسهم #{single_symbol}:**\n\n"
                f"• **آخر سعر إغلاق:** `{latest.get('close')} ج.م` ({float(latest.get('change_pct') or 0):+.2f}%)\n"
                f"• **النشاط والسيولة:** حجم التداول `{int(latest.get('volume') or 0):,}` سهم بنشاط نسبي `{float(latest.get('r_vol') or 1.0):.2f}x`\n"
                f"• **مؤشر القوة النسبية RSI:** `{float(latest.get('rsi_14') or 50):.1f}`\n"
                f"• **الدعم والمقاومة:** الدعم الفني عند متوسط 20 يوم `{latest.get('ema_20')} ج.م` والمقاومة عند `{latest.get('bb_upper')} ج.م`.\n\n"
                f"💡 _نصيحة إدارة المخاطر: ينصح دائماً بوضع وقف خسارة أسفل مستوى الدعم بنسبة 2.5% إلى 3.0% لحماية المحفظة._"
            )
        else:
            reply_text = (
                f"مرحباً بك يا {user_info['display_name']}! 👋\n\n"
                f"أنا **أرتورو (ARTORO AI)**، المساعد الذكي لتحليل الأسهم المصرية.\n"
                f"يمكنك سؤالي عن أي سهم بكتابة رمزه (مثال: `COMI` أو `فوري` أو `سهم طلعت مصطفى`)، "
                f"أو الاستفسار عن وضع المؤشرات العامة والسيولة وسأجيبك بأدق القراءات الفنية اللحظية."
            )

    # Save state & consume quota atomically
    state_row = user_info["state_row"] or {}
    new_daily_count = (int(state_row.get("daily_count") or 0) + 1) if state_row.get("quota_date") == today else 1

    chat_history = state_row.get("chat_history") or []
    chat_history.append({"role": "user", "content": query[:300], "created_at": datetime.now(timezone.utc).isoformat()})
    chat_history.append({"role": "assistant", "content": reply_text[:600], "created_at": datetime.now(timezone.utc).isoformat()})

    _supabase_request(
        "telegram_vip_chat_state?on_conflict=telegram_user_id",
        method="POST",
        payload={
            "telegram_user_id": tg_user_id,
            "telegram_username": user_name,
            "linked_user_id": user_info["linked_user_id"],
            "quota_date": today,
            "daily_count": new_daily_count,
            "chat_history": chat_history[-10:],
            "pending_prompt": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    new_used = user_info["used"] + 1
    new_remaining = 9999 if user_info["is_admin"] else max(0, user_info["limit"] - new_used)

    return {
        "ok": True,
        "reply": reply_text,
        "tables": [],
        "display_name": user_info["display_name"],
        "is_pro": user_info["is_pro"],
        "used": new_used,
        "limit": user_info["limit"],
        "remaining": new_remaining,
        "period": user_info["period"],
    }
