"""
Native Python Telegram VIP Chat Engine for EGX BOTS.
Executes directly on Hugging Face Spaces / Python Backend without invoking Vercel Serverless Functions.
Handles quota verification, pending prompts, and AI chat analysis via direct DeepSeek integration.
"""
import os
import sys
import re
import json
import logging
import hashlib
import time
import asyncio
import threading
import concurrent.futures
import requests
from requests.adapters import HTTPAdapter
try:
    from dotenv import load_dotenv
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_repo_root, "web", ".env.local"))
    load_dotenv(os.path.join(_repo_root, ".env"))
except ImportError:
    pass
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional

logger = logging.getLogger("native_telegram_vip_chat")
logger.setLevel(logging.INFO)

CAIRO_TZ = ZoneInfo("Africa/Cairo")
ADMIN_TG_IDS = {"5149631436"}

# Persistent HTTP Session for Supabase REST calls (eliminates repeated TLS handshakes)
_SUPABASE_HTTP_SESSION = requests.Session()
_adapter = HTTPAdapter(pool_connections=16, pool_maxsize=32)
_SUPABASE_HTTP_SESSION.mount("https://", _adapter)
_SUPABASE_HTTP_SESSION.mount("http://", _adapter)

# Bounded ThreadPoolExecutor for async execution & background admin logging
_VIP_CHAT_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=12, thread_name_prefix="vip_chat")

# Short-lived in-memory cache for _resolve_telegram_user (reduces 5 Supabase calls per message to 0 on repeat turns)
_USER_RESOLVE_CACHE: Dict[int, Dict[str, Any]] = {}
_USER_RESOLVE_LOCK = threading.Lock()
_USER_CACHE_TTL_SECONDS = 90.0


def _is_pytest() -> bool:
    return bool("pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"))


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
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if method == "POST":
        headers["Prefer"] = "resolution=merge-duplicates"

    try:
        resp = _SUPABASE_HTTP_SESSION.request(
            method=method,
            url=full_url,
            json=payload if payload is not None else None,
            headers=headers,
            timeout=timeout,
        )
        if resp.status_code >= 400:
            logger.warning(f"[NATIVE_VIP_CHAT] {method} {endpoint} HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json() if resp.text and resp.text.strip() else {}
    except Exception as e:
        logger.warning(f"[NATIVE_VIP_CHAT] {method} {endpoint} failed: {e}")
        return None


def _resolve_telegram_user(telegram_user_id: int, telegram_username: str) -> Dict[str, Any]:
    now_ts = time.time()
    if not _is_pytest():
        with _USER_RESOLVE_LOCK:
            cached = _USER_RESOLVE_CACHE.get(int(telegram_user_id))
            if cached and (now_ts - cached.get("_cached_at", 0.0)) < _USER_CACHE_TTL_SECONDS:
                res_copy = dict(cached)
                res_copy.pop("_cached_at", None)
                return res_copy

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

    resolved = {
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

    if not _is_pytest():
        with _USER_RESOLVE_LOCK:
            if len(_USER_RESOLVE_CACHE) > 1000:
                _USER_RESOLVE_CACHE.clear()
            cache_entry = dict(resolved)
            cache_entry["_cached_at"] = now_ts
            _USER_RESOLVE_CACHE[int(telegram_user_id)] = cache_entry

    return resolved


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
    chat_source = payload.get("chat_source") or "telegram_topic"
    bypass_quota = bool(payload.get("bypass_quota")) or (chat_source == "telegram_b2b" and action == "chat")

    if not tg_user_id:
        return {"ok": False, "error": "Missing telegram_user_id"}

    today = get_cairo_date_str()
    if bypass_quota and action == "chat":
        # B2B group requests have already verified and deducted group quota via RPC.
        # Skip the 5 sequential Supabase REST queries for personal user resolution!
        user_info = {
            "telegram_user_id": tg_user_id,
            "telegram_username": user_name,
            "linked_user_id": None,
            "display_name": user_name or "عضو المجموعة",
            "is_pro": True,
            "is_admin": False,
            "used": 0,
            "limit": 999,
            "remaining": 999,
            "period": "daily",
            "state_row": None,
        }
    else:
        user_info = _resolve_telegram_user(tg_user_id, user_name)

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
        with _USER_RESOLVE_LOCK:
            _USER_RESOLVE_CACHE.pop(int(tg_user_id), None)
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
    raw_images = payload.get("images") or []
    if isinstance(raw_images, str):
        raw_images = [raw_images]
    images = [img for img in raw_images if img and isinstance(img, str) and img.strip()]
    image_storage_url = payload.get("image_storage_url") or (images[0] if images else None)

    if not query and not images:
        return {"ok": False, "error": "Empty message"}
    if not query and images:
        query = "حلل محفظتي الاستثمارية بناءً على الصورة المرفقة واستخرج الأسهم والأسعار والكميات وقدم خطة دعم ومقاومة وهدف ووقف خسارة لكل سهم"

    audit_user_id = user_info["linked_user_id"] or deterministic_session_uuid(f"tg-user-{tg_user_id}")
    session_id = deterministic_session_uuid(f"tg-{chat_source}-{audit_user_id}")
    if chat_source == "telegram_private":
        room_prefix = "🔒 [بوت تليجرام الخاص]"
    elif chat_source == "telegram_b2b":
        room_prefix = "🏢 [مجموعة B2B]"
    else:
        room_prefix = "📢 [تليجرام التوبيك العام]"
    img_tag = "📸 [صورة] " if images else ""
    session_title = f"{room_prefix} {img_tag}{query[:24]}"

    if not bypass_quota and not user_info["is_admin"] and user_info["remaining"] <= 0:
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

    # Consume quota if linked account exists (unless bypassed by B2B group quota)
    if not bypass_quota and user_info["linked_user_id"] and not user_info["is_admin"]:
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

    user_created_dt = datetime.now(timezone.utc)
    start_time = time.time()
    reply_text = ""
    tables: List[Dict[str, Any]] = []

    # Fast-Path + Single-Flight Coalescing via Two-Tier Analysis Cache
    # Avoids spinning up an asyncio loop or firing duplicate DeepSeek requests when multiple users ask the same stock question
    early_cache_key: Optional[str] = None
    inflight_lock: Optional[threading.Lock] = None
    if not images:
        try:
            from api.agentic_chat.analysis_cache import (
                build_analysis_cache_key,
                get_vip_analysis_cache,
                get_inflight_cache_lock,
            )
            early_cache_key = build_analysis_cache_key(query)
            if early_cache_key:
                cached_hit = get_vip_analysis_cache(early_cache_key, user_id=user_info.get("linked_user_id"))
                if cached_hit and cached_hit.get("reply"):
                    reply_text = cached_hit["reply"]
                    tables = cached_hit.get("tables") or []
                    logger.info(f"[NATIVE_VIP_CHAT] Instant Fast-Path Cache Hit for {early_cache_key} (0 DeepSeek tokens)")
                else:
                    inflight_lock = get_inflight_cache_lock(early_cache_key)
        except Exception as cache_init_err:
            logger.warning(f"[NATIVE_VIP_CHAT] Fast-path cache check warning: {cache_init_err}")

    # Run the full Agentic Chat Pipeline with all 9 tools (DeepSeek-V3) if not already served by fast-path cache
    if not reply_text:
        acquired_inflight = False
        try:
            if inflight_lock is not None:
                acquired_inflight = inflight_lock.acquire(timeout=55)
                # Double-check cache after acquiring single-flight lock (another concurrent worker may have just populated it!)
                if early_cache_key:
                    from api.agentic_chat.analysis_cache import get_vip_analysis_cache
                    cached_after_wait = get_vip_analysis_cache(early_cache_key, user_id=user_info.get("linked_user_id"))
                    if cached_after_wait and cached_after_wait.get("reply"):
                        reply_text = cached_after_wait["reply"]
                        tables = cached_after_wait.get("tables") or []
                        logger.info(f"[NATIVE_VIP_CHAT] Coalesced Single-Flight Cache Hit for {early_cache_key}")

            if not reply_text:
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
                        images=images,
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
                        reply_text, tables = _VIP_CHAT_EXECUTOR.submit(lambda: asyncio.run(_run_agentic())).result(timeout=65)
                    else:
                        reply_text, tables = loop.run_until_complete(_run_agentic())
                except RuntimeError:
                    reply_text, tables = asyncio.run(_run_agentic())
        except Exception as exc:
            logger.warning(f"[NATIVE_VIP_CHAT] Agentic pipeline error: {exc}")
        finally:
            if acquired_inflight and inflight_lock is not None:
                try:
                    inflight_lock.release()
                except Exception:
                    pass

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
    assistant_created_dt = datetime.now(timezone.utc)
    if assistant_created_dt <= user_created_dt:
        assistant_created_dt = user_created_dt + timedelta(milliseconds=1)
    user_now_iso = user_created_dt.isoformat()
    assistant_now_iso = assistant_created_dt.isoformat()
    now_iso = assistant_now_iso
    common_meta = {
        "chat_source": chat_source,
        "telegram_user_id": tg_user_id,
        "telegram_username": user_name,
        "display_name": user_info["display_name"],
        "linked_user_id": user_info["linked_user_id"],
        "tables": tables,
    }

    # Record session & messages in Supabase for Admin Control Panel visibility (Support & AI tab)
    def _persist_admin_audit():
        try:
            from api.stock_ai import _init_supabase, supabase
            _init_supabase()
            supabase.from_("ai_chat_sessions").upsert({
                "id": session_id,
                "user_id": audit_user_id,
                "title": session_title,
                "is_deleted_by_user": False,
                "updated_at": assistant_now_iso,
            }, on_conflict="id").execute()

            supabase.from_("ai_chat_messages").insert([
                {
                    "session_id": session_id,
                    "user_id": audit_user_id,
                    "role": "user",
                    "content": query,
                    "image_url": image_storage_url,
                    "metadata": common_meta,
                    "created_at": user_now_iso,
                },
                {
                    "session_id": session_id,
                    "user_id": audit_user_id,
                    "role": "assistant",
                    "content": reply_text,
                    "latency_ms": latency_ms,
                    "metadata": common_meta,
                    "created_at": assistant_now_iso,
                }
            ]).execute()
        except Exception as err:
            logger.warning(f"[NATIVE_VIP_CHAT] Admin message persistence error: {err}")

    if _is_pytest():
        _persist_admin_audit()
    else:
        _VIP_CHAT_EXECUTOR.submit(_persist_admin_audit)

    # Increment quota & save Telegram state (skip for B2B group messages since group quota is tracked in b2b_group_licenses)
    if not bypass_quota:
        state_row = user_info["state_row"] or {}
        new_daily_count = (int(state_row.get("daily_count") or 0) + 1) if state_row.get("quota_date") == today else 1

        chat_history = list(state_row.get("chat_history") or [])
        chat_history.append({"role": "user", "content": query, "created_at": user_now_iso})
        chat_history.append({"role": "assistant", "content": reply_text[:1600], "created_at": now_iso})

        def _persist_tg_state():
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
            with _USER_RESOLVE_LOCK:
                _USER_RESOLVE_CACHE.pop(int(tg_user_id), None)

        if _is_pytest():
            _persist_tg_state()
        else:
            _VIP_CHAT_EXECUTOR.submit(_persist_tg_state)

    new_used = user_info["used"] + (0 if bypass_quota else 1)
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
