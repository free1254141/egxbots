"""
Native Python Telegram VIP Chat Engine for EGX BOTS.
Executes directly on Hugging Face Spaces / Python Backend without invoking Vercel Serverless Functions.
Handles quota verification, pending prompts, and AI chat analysis via direct DeepSeek integration.
"""
import os
import re
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional

logger = logging.getLogger("native_telegram_vip_chat")
logger.setLevel(logging.INFO)

CAIRO_TZ = ZoneInfo("Africa/Cairo")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
ADMIN_TG_IDS = {"5149631436"}


def get_cairo_date_str() -> str:
    return datetime.now(CAIRO_TZ).strftime("%Y-%m-%d")


def _get_supabase_config():
    url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or ""
    return url, key


def _supabase_request(endpoint: str, method: str = "GET", payload: Optional[Dict[str, Any]] = None, timeout: int = 10) -> Optional[Any]:
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
        sub_rows = _supabase_request(f"subscriptions?user_id=eq.{linked_user_id}&status=in.(active,trialing)&select=plan_id,status,current_period_end&order=current_period_end.desc&limit=1") or []
        if sub_rows:
            is_pro = True
            limit = 350
        else:
            limit = 10
            period = "daily"

        # Check quota usage
        quota_rows = _supabase_request(f"ai_chatbot_limits?user_id=eq.{linked_user_id}&date=gte.{today[:7]}-01&select=chat_count") or []
        used = sum(int(r.get("chat_count") or 0) for r in quota_rows)
    else:
        # Unlinked user
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


def _extract_stock_symbol(text: str) -> Optional[str]:
    # Match symbols like #COMI, COMI, فورى, التجاري الدولي, etc.
    words = re.findall(r"[A-Za-z]{2,8}", text)
    if words:
        for w in words:
            w_upper = w.upper()
            if w_upper not in {"THE", "AND", "FOR", "BUY", "SELL", "VIP", "BOT", "EGX"}:
                return w_upper
    return None


def handle_native_vip_chat(payload: Dict[str, Any]) -> Dict[str, Any]:
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
        pending_payload = {"mode": prompt_mode, "expires_at": int(datetime.now().timestamp() * 1000) + 300000} if prompt_mode else None
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

    # Detect symbol
    symbol = _extract_stock_symbol(query)
    stock_context = ""
    evidence_data = []

    if symbol:
        ind_rows = _supabase_request(f"stock_technical_indicators?exchange=eq.EGX&symbol=eq.{symbol}&select=symbol,date,close,change_pct,volume,vol_sma20,r_vol,rsi_14,macd,bb_upper,bb_lower,ema_20,ema_50&order=date.desc&limit=5") or []
        if ind_rows:
            latest = ind_rows[0]
            stock_context = (
                f"بيانات سهم #{symbol} لجلسة {latest.get('date')}:\n"
                f"• الإغلاق: {latest.get('close')} ج.م ({float(latest.get('change_pct') or 0):+.2f}%)\n"
                f"• حجم التداول: {int(latest.get('volume') or 0):,} سهم (الحجم النسبي: {float(latest.get('r_vol') or 1.0):.2f}x)\n"
                f"• مؤشر RSI(14): {float(latest.get('rsi_14') or 50):.1f}\n"
                f"• المتوسطات: EMA20={latest.get('ema_20')}, EMA50={latest.get('ema_50')}\n"
                f"• حدود بولينجر: العلوي={latest.get('bb_upper')}, السفلي={latest.get('bb_lower')}\n"
            )
            evidence_data.append(latest)

    # General market context if no stock found
    if not stock_context:
        market_rows = _supabase_request(f"stock_technical_indicators?exchange=eq.EGX&date=eq.{today}&select=symbol,close,change_pct,volume&limit=50") or []
        pos = sum(1 for r in market_rows if float(r.get("change_pct") or 0) > 0.1)
        neg = sum(1 for r in market_rows if float(r.get("change_pct") or 0) < -0.1)
        stock_context = f"بيانات السوق العام: صاعد {pos} سهم، هابط {neg} سهم."

    deepseek_key = (os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_OFFICIAL_API_KEY") or "").strip()
    reply_text = ""

    if deepseek_key:
        sys_prompt = (
            "أنت المساعد المالي والتقني الذكي (ARTORO AI) الخاص بمنصة EGX BOTS المعتمد لتحليل البورصة المصرية.\n"
            "مهمتك: الإجابة على استفسار المستثمر بدقة فنية ومالية عالية، بأسلوب عربي فصيح، راقٍ ومهني.\n"
            "قواعد التحليل:\n"
            "1. استند حصرياً إلى البيانات والأرقام المرفقة ولا تخترع أسعاراً أو أرقاماً غير موجودة.\n"
            "2. وضح مستويات الدعم والمقاومة، وقف الخسارة، والاتجاه والزخم بناءً على المؤشرات الفنية المتاحة.\n"
            "3. رتّب الإجابة في نقاط واضحة برؤوس أقلام بارزة تناسب شاشة تليجرام على الموبايل.\n"
            "4. اذكر دائماً أن التحليل فني وقراءة للأدلة الرقمية ولا يمثل دعوة شراء أو بيع ملزمة."
        )
        usr_prompt = f"استفسار المستثمر: {query}\n\nالبيانات الرقمية الموثقة من السوق:\n{stock_context}"

        req = urllib.request.Request(
            DEEPSEEK_API_URL,
            data=json.dumps({
                "model": "deepseek-chat",
                "temperature": 0.2,
                "max_tokens": 900,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": usr_prompt},
                ]
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

    if not reply_text:
        # Fallback response
        if symbol and evidence_data:
            latest = evidence_data[0]
            reply_text = (
                f"📊 **التحليل الفني السريع لسهم #{symbol}:**\n\n"
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

    # Increment quota & save state
    state_row = user_info["state_row"] or {}
    new_daily_count = (int(state_row.get("daily_count") or 0) + 1) if state_row.get("quota_date") == today else 1

    chat_history = state_row.get("chat_history") or []
    chat_history.append({"role": "user", "content": query, "created_at": datetime.now(timezone.utc).isoformat()})
    chat_history.append({"role": "assistant", "content": reply_text[:1200], "created_at": datetime.now(timezone.utc).isoformat()})

    _supabase_request(
        "telegram_vip_chat_state?on_conflict=telegram_user_id",
        method="POST",
        payload={
            "telegram_user_id": tg_user_id,
            "telegram_username": user_name,
            "linked_user_id": user_info["linked_user_id"],
            "quota_date": today,
            "daily_count": new_daily_count,
            "chat_history": chat_history[-14:],
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
