"""
Native Python Telegram VIP Chat Engine for EGX BOTS.
Executes directly on Hugging Face Spaces / Python Backend without invoking Vercel Serverless Functions.
Handles quota verification, pending prompts, and AI chat analysis via direct DeepSeek integration.
"""
import os
import re
import json
import logging
import hashlib
import time
import asyncio
import concurrent.futures
try:
    from dotenv import load_dotenv
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_repo_root, "web", ".env.local"))
    load_dotenv(os.path.join(_repo_root, ".env"))
except ImportError:
    pass
import urllib.request
import urllib.error
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional

logger = logging.getLogger("native_telegram_vip_chat")
logger.setLevel(logging.INFO)

CAIRO_TZ = ZoneInfo("Africa/Cairo")
ADMIN_TG_IDS = {"5149631436"}


def deterministic_session_uuid(seed: str) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"


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

    profile_rows = _supabase_request(f"profiles?telegram_chat_id=eq.{tg_id_str}&select=id,display_name,username&limit=10") or []
    invite_rows = _supabase_request(f"pro_telegram_invites?vip_telegram_user_id=eq.{telegram_user_id}&select=user_id&limit=10") or []

    candidate_ids = []
    for r in profile_rows:
        if r.get("id") and r["id"] not in candidate_ids:
            candidate_ids.append(r["id"])
    for r in invite_rows:
        if r.get("user_id") and r["user_id"] not in candidate_ids:
            candidate_ids.append(r["user_id"])
    if state_row and state_row.get("linked_user_id") and state_row["linked_user_id"] not in candidate_ids:
        candidate_ids.append(state_row["linked_user_id"])

    linked_user_id = candidate_ids[0] if candidate_ids else None
    display_name = telegram_username or "المستثمر"
    if profile_rows:
        display_name = profile_rows[0].get("display_name") or profile_rows[0].get("username") or display_name
    is_pro = is_admin

    if candidate_ids:
        id_filter = ",".join(candidate_ids)
        sub_rows = _supabase_request(f"subscriptions?user_id=in.({id_filter})&status=in.(active,trialing)&select=user_id,plan_id,status,current_period_end&order=current_period_end.desc&limit=5") or []
        if sub_rows:
            active_sub = sub_rows[0]
            linked_user_id = active_sub.get("user_id") or linked_user_id
            is_pro = True

    limit = 350 if is_pro else 10
    period = "monthly"
    used = 0

    if linked_user_id:
        quota_rows = _supabase_request(f"ai_chatbot_limits?user_id=eq.{linked_user_id}&date=gte.{today[:7]}-01&select=chat_count") or []
        used = sum(int(r.get("chat_count") or 0) for r in quota_rows)
    else:
        limit = 350 if is_pro else 10
        period = "monthly" if is_pro else "daily"
        if state_row and state_row.get("quota_date") == today:
            used = int(state_row.get("daily_count") or 0)

    remaining = max(0, limit - used)

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

    chat_source = payload.get("chat_source") or "telegram_topic"
    audit_user_id = user_info["linked_user_id"] or deterministic_session_uuid(f"tg-user-{tg_user_id}")
    session_id = deterministic_session_uuid(f"tg-{chat_source}-{audit_user_id}")
    room_prefix = "🔒 [بوت تليجرام الخاص]" if chat_source == "telegram_private" else "📢 [تليجرام التوبيك العام]"
    session_title = f"{room_prefix} {query[:28]}"

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

    # Consume quota if linked account exists
    if user_info["linked_user_id"] and not user_info["is_admin"]:
        try:
            from api.agentic_chat.auth_guard import check_and_consume_quota
            allowed, rem, lim, err = check_and_consume_quota(user_info["linked_user_id"], user_info["is_pro"])
            if not allowed:
                return {
                    "ok": False,
                    "error_code": "LIMIT_REACHED",
                    "linked": True,
                    "display_name": user_info["display_name"],
                    "is_pro": user_info["is_pro"],
                    "used": lim,
                    "limit": lim,
                    "remaining": 0,
                    "period": user_info["period"],
                    "detail": err or "لقد استهلكت رصيدك المتاح.",
                }
        except Exception as e:
            logger.warning(f"[NATIVE_VIP_CHAT] Quota check warning: {e}")

    start_time = time.time()
    reply_text = ""
    tables: List[Dict[str, Any]] = []

    # Run the full Agentic Chat Pipeline with all 9 tools (DeepSeek-V3)
    try:
        from api.agentic_chat.pipeline import run_agentic_chat_stream

        chat_history = (user_info.get("state_row") or {}).get("chat_history") or []
        formatted_history = [
            {"role": h.get("role", "user"), "content": h.get("content", "")}
            for h in chat_history[-10:]
        ]

        async def _run_agentic():
            full = ""
            tbls = []
            async for sse_chunk in run_agentic_chat_stream(
                message=query,
                history=formatted_history,
                session_id=session_id,
                user_id=audit_user_id,
                model="deepseek-chat",
                is_pro=user_info["is_pro"],
                remaining_quota=user_info["remaining"],
                quota_limit=user_info["limit"],
            ):
                line = sse_chunk.strip()
                if line.startswith("data:"):
                    dp = line[5:].strip()
                    if dp != "[DONE]":
                        try:
                            ev = json.loads(dp)
                            if ev.get("type") == "token":
                                full += ev.get("token", "")
                            elif ev.get("type") == "done":
                                full = ev.get("reply", full)
                                tbls = ev.get("tables", [])
                        except Exception:
                            pass
            return full, tbls

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    reply_text, tables = pool.submit(lambda: asyncio.run(_run_agentic())).result(timeout=65)
            else:
                reply_text, tables = loop.run_until_complete(_run_agentic())
        except RuntimeError:
            reply_text, tables = asyncio.run(_run_agentic())
    except Exception as exc:
        logger.warning(f"[NATIVE_VIP_CHAT] Agentic pipeline error: {exc}")

    # Fallback to direct technical indicators if agentic call failed
    if not reply_text:
        symbol = _extract_stock_symbol(query)
        if symbol:
            ind_rows = _supabase_request(f"stock_technical_indicators?exchange=eq.EGX&symbol=eq.{symbol}&select=symbol,date,close,change_pct,volume,vol_sma20,r_vol,rsi_14,macd,bb_upper,bb_lower,ema_20,ema_50&order=date.desc&limit=5") or []
            if ind_rows:
                latest = ind_rows[0]
                reply_text = (
                    f"📊 **التحليل الفني السريع لسهم #{symbol}:**\n\n"
                    f"• **آخر سعر إغلاق:** `{latest.get('close')} ج.م` ({float(latest.get('change_pct') or 0):+.2f}%)\n"
                    f"• **النشاط والسيولة:** حجم التداول `{int(latest.get('volume') or 0):,}` سهم بنشاط نسبي `{float(latest.get('r_vol') or 1.0):.2f}x`\n"
                    f"• **مؤشر القوة النسبية RSI:** `{float(latest.get('rsi_14') or 50):.1f}`\n"
                    f"• **الدعم والمقاومة:** الدعم الفني عند متوسط 20 يوم `{latest.get('ema_20')} ج.م` والمقاومة عند `{latest.get('bb_upper')} ج.م`.\n\n"
                    f"💡 _نصيحة إدارة المخاطر: ينصح دائماً بوضع وقف خسارة أسفل مستوى الدعم بنسبة 2.5% إلى 3.0% لحماية المحفظة._"
                )

        if not reply_text:
            reply_text = (
                f"مرحباً بك يا {user_info['display_name']}! 👋\n\n"
                f"أنا **أرتورو (ARTORO AI)**، المساعد الذكي لتحليل الأسهم المصرية.\n"
                f"يمكنك سؤالي عن أي سهم بكتابة رمزه (مثال: `COMI` أو `فوري` أو `سهم طلعت مصطفى`)، "
                f"أو الاستفسار عن وضع المؤشرات العامة والسيولة وسأجيبك بأدق القراءات الفنية اللحظية."
            )

    latency_ms = int((time.time() - start_time) * 1000)
    now_iso = datetime.now(timezone.utc).isoformat()
    common_meta = {
        "chat_source": chat_source,
        "telegram_user_id": tg_user_id,
        "telegram_username": user_name,
        "display_name": user_info["display_name"],
        "linked_user_id": user_info["linked_user_id"],
        "tables": tables,
    }

    # Record session & messages in Supabase for Admin Control Panel visibility (Support & AI tab)
    try:
        from api.stock_ai import _init_supabase, supabase
        _init_supabase()
        # 1. Upsert session so Admin sees the user's room
        supabase.from_("ai_chat_sessions").upsert({
            "id": session_id,
            "user_id": audit_user_id,
            "title": session_title,
            "is_deleted_by_user": False,
            "updated_at": now_iso,
        }, on_conflict="id").execute()

        # 2. Insert messages so Admin sees the full prompt and answer
        supabase.from_("ai_chat_messages").insert([
            {
                "session_id": session_id,
                "user_id": audit_user_id,
                "role": "user",
                "content": query,
                "metadata": common_meta,
                "created_at": now_iso,
            },
            {
                "session_id": session_id,
                "user_id": audit_user_id,
                "role": "assistant",
                "content": reply_text,
                "latency_ms": latency_ms,
                "metadata": common_meta,
                "created_at": now_iso,
            }
        ]).execute()
        logger.info(f"[NATIVE_VIP_CHAT] Successfully persisted session {session_id} to ai_chat_sessions & ai_chat_messages for admin.")
    except Exception as err:
        logger.warning(f"[NATIVE_VIP_CHAT] Admin message persistence error: {err}")

    # Increment quota & save Telegram state
    state_row = user_info["state_row"] or {}
    new_daily_count = (int(state_row.get("daily_count") or 0) + 1) if state_row.get("quota_date") == today else 1

    chat_history = state_row.get("chat_history") or []
    chat_history.append({"role": "user", "content": query, "created_at": now_iso})
    chat_history.append({"role": "assistant", "content": reply_text[:1600], "created_at": now_iso})

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
            "updated_at": now_iso,
        }
    )

    new_used = user_info["used"] + 1
    new_remaining = max(0, user_info["limit"] - new_used)

    return {
        "ok": True,
        "reply": reply_text,
        "tables": tables,
        "display_name": user_info["display_name"],
        "is_pro": user_info["is_pro"],
        "used": new_used,
        "limit": user_info["limit"],
        "remaining": new_remaining,
        "period": user_info["period"],
    }
