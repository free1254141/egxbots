"""
api/agentic_chat/router.py
FastAPI router for the parallel Python Agentic Chatbot backend.
Supports streaming SSE (text/event-stream), authenticated quota checks,
session persistence, and non-blocking async execution.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import json
import logging
import os
import time
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Request, Header
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from api.agentic_chat.pipeline import run_agentic_chat_stream, _build_tools_stage_label
from api.agentic_chat.tools_execution import _normalize_market_code, _ui_market_label
from api.agentic_chat.auth_guard import (
    get_authenticated_user,
    check_and_consume_quota,
    get_user_chat_quota,
    sanitize_user_input,
)
from api.stock_ai import _init_supabase, supabase
from api.plan_limits import has_chat_pro_user, is_pro_user

logger = logging.getLogger("agentic_chat")
router = APIRouter(prefix="", tags=["agentic_chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: Optional[str] = ""
    history: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    images: Optional[List[str]] = Field(default_factory=list)
    model: Optional[str] = "deepseek-chat"
    sessionId: Optional[str] = None
    session_id: Optional[str] = None
    userId: Optional[str] = None
    user_id: Optional[str] = None
    clientMessageId: Optional[str] = None
    autonomousRecommendations: Optional[bool] = False
    autonomous_recommendations: Optional[bool] = False
    action: Optional[str] = None
    title: Optional[str] = None
    stream: Optional[bool] = True
    market: Optional[str] = None


@router.get("/health")
async def health_check():
    """Health check endpoint for the agentic chat service."""
    return {
        "status": "healthy",
        "service": "agentic_chat",
        "engine": "deepseek-v3",
        "mode": "async-streaming",
        "markets": ["EGX", "TASI"],
    }


_VALID_STAGE_IDS = ("understand", "fetch_data", "quant_verify", "synthesize")
_RAW_STAGE_STATUS_CODES = frozenset({
    "thinking", "vision", "executing_tools", "quant_engine", "generating", "cached",
})


def _default_answer_stages(*, has_images: bool = False) -> List[Dict[str, str]]:
    return [
        {
            "id": "understand",
            "label": "قراءة الصورة وفهم سياق السؤال" if has_images else "فهم السؤال وتحديد السهم والسوق",
            "status": "in_progress",
        },
        {"id": "fetch_data", "label": "جلب البيانات الحية من أدوات السوق", "status": "pending"},
        {"id": "quant_verify", "label": "التحليل الكمي ومحاكاة مونت كارلو وحسم التعارض", "status": "pending"},
        {"id": "synthesize", "label": "صياغة التقرير النهائي ومراجعة الحارس الآلي", "status": "pending"},
    ]


def _resolve_stage_id_from_event(event: Dict[str, Any]) -> Optional[str]:
    sid = event.get("step_id")
    if sid in _VALID_STAGE_IDS:
        return sid
    st = str(event.get("status") or "").strip()
    if st in ("thinking", "vision"):
        return "understand"
    if st in ("executing_tools", "cached"):
        return "fetch_data"
    if st == "quant_engine":
        return "quant_verify"
    if st == "generating":
        return "synthesize"
    return None


def _build_persisted_answer_stages(
    status_events: List[Dict[str, Any]],
    *,
    has_images: bool = False,
    tools_used: Optional[List[str]] = None,
    cached: bool = False,
) -> List[Dict[str, str]]:
    """Replay SSE status events into finalized compact answerStages matching ChatContext.tsx."""
    stages = _default_answer_stages(has_images=has_images)
    for ev in status_events or []:
        if not isinstance(ev, dict):
            continue
        raw_msg = str(ev.get("message") or ev.get("content") or "").strip()
        human_label = raw_msg if (raw_msg and raw_msg not in _RAW_STAGE_STATUS_CODES) else ""
        if str(ev.get("status") or "").strip() == "cached":
            by_id = {s["id"]: s for s in stages}
            defaults = {s["id"]: s for s in _default_answer_stages(has_images=has_images)}
            u = dict(by_id.get("understand") or defaults["understand"])
            f = dict(by_id.get("fetch_data") or defaults["fetch_data"])
            sy = dict(by_id.get("synthesize") or defaults["synthesize"])
            u["status"] = "done"
            f["label"] = human_label or "تم استرجاع التحليل الموثق من الذاكرة"
            f["status"] = "done"
            sy["status"] = "in_progress"
            stages = [u, f, sy]
            continue

        target_id = _resolve_stage_id_from_event(ev)
        if not target_id:
            continue
        target_idx = next((i for i, s in enumerate(stages) if s["id"] == target_id), -1)
        if target_idx < 0:
            prev_map = {s["id"]: s for s in stages}
            stages = [dict(prev_map.get(s["id"], s)) for s in _default_answer_stages(has_images=has_images)]
            target_idx = next((i for i, s in enumerate(stages) if s["id"] == target_id), -1)
        if target_idx < 0:
            continue

        next_stages: List[Dict[str, str]] = []
        for idx, stage in enumerate(stages):
            item = dict(stage)
            if idx < target_idx:
                item["status"] = "done"
            elif idx == target_idx:
                if human_label:
                    item["label"] = human_label
                item["status"] = "in_progress"
            else:
                item["status"] = "pending"
            next_stages.append(item)
        stages = next_stages

    has_tools = isinstance(tools_used, list) and len(tools_used) > 0
    finalized: List[Dict[str, str]] = []
    for s in stages:
        sid = s.get("id")
        if (
            sid in ("understand", "synthesize")
            or s.get("status") in ("done", "in_progress")
            or (has_tools and not cached)
        ):
            label = str(s.get("label") or "").strip()[:180]
            if sid in _VALID_STAGE_IDS and label:
                finalized.append({"id": str(sid), "label": label, "status": "done"})
    return finalized


def _normalize_persisted_answer_stages(raw: Any) -> Optional[List[Dict[str, str]]]:
    if not isinstance(raw, list) or not raw:
        return None
    out: List[Dict[str, str]] = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()[:180]
        if sid in _VALID_STAGE_IDS and label and sid not in seen:
            seen.add(sid)
            out.append({"id": sid, "label": label, "status": "done"})
    return out or None


def _extract_message_answer_stages(role: Optional[str], meta: Dict[str, Any]) -> Optional[List[Dict[str, str]]]:
    """Return stored answer_stages from metadata, or reconstruct accurately for historical assistant rows."""
    if role != "assistant" or not isinstance(meta, dict):
        return None
    stored = _normalize_persisted_answer_stages(meta.get("answer_stages") or meta.get("answerStages"))
    if stored:
        return stored
    if not (meta.get("engine") or meta.get("usage") or meta.get("cached") is True or meta.get("latency_ms")):
        return None
    if meta.get("cached") is True:
        return [
            {"id": "understand", "label": "فهم السؤال وتحديد السهم والسوق", "status": "done"},
            {"id": "fetch_data", "label": "تم استرجاع التحليل الموثق من الذاكرة", "status": "done"},
            {"id": "synthesize", "label": "صياغة التقرير النهائي ومراجعة الحارس الآلي", "status": "done"},
        ]
    usage = meta.get("usage") if isinstance(meta.get("usage"), dict) else {}
    tools_used = usage.get("tools_used") if isinstance(usage.get("tools_used"), list) else []
    has_tables = isinstance(meta.get("tables"), list) and len(meta.get("tables")) > 0
    if tools_used or has_tables:
        fetch_label = _build_tools_stage_label(tools_used) if tools_used else "جلب البيانات الحية من أدوات السوق"
        return [
            {"id": "understand", "label": "فهم السؤال وتحديد السهم والسوق", "status": "done"},
            {"id": "fetch_data", "label": fetch_label, "status": "done"},
            {"id": "quant_verify", "label": "تدقيق ومطابقة البيانات المالية والفنية المستخرجة", "status": "done"},
            {"id": "synthesize", "label": "صياغة التقرير النهائي ومراجعة الحارس الآلي", "status": "done"},
        ]
    return [
        {"id": "understand", "label": "فهم السؤال وتحديد السهم والسوق", "status": "done"},
        {"id": "synthesize", "label": "صياغة التقرير النهائي ومراجعة الحارس الآلي", "status": "done"},
    ]


def _persist_message_background(
    session_id: str,
    user_id: Optional[str],
    user_msg: str,
    reply: str,
    latency_ms: int = 0,
    image_url: Optional[str] = None,
    market: str = "EGX",
    cached: bool = False,
    cache_key: Optional[str] = None,
    tables: Optional[List[Any]] = None,
    usage: Optional[Dict[str, Any]] = None,
    guard_warnings: Optional[List[str]] = None,
    answer_stages: Optional[List[Dict[str, Any]]] = None,
):
    """Save user and assistant messages to ai_chat_messages in background."""
    if user_id == "00000000-0000-0000-0000-000000000000" or not session_id:
        return
    try:
        _init_supabase()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        safe_latency = max(int(latency_ms or 0), 0)
        time_diff = safe_latency if safe_latency > 0 else 1000
        user_created_at_iso = (now - timedelta(milliseconds=time_diff)).isoformat()
        title = (user_msg or "محادثة جديدة")[:45].strip()

        # 1. MUST UPSERT SESSION FIRST TO SATISFY FOREIGN KEY CONSTRAINT
        session_payload = {
            "id": session_id,
            "title": title,
            "updated_at": now_iso,
        }
        if user_id:
            session_payload["user_id"] = user_id

        supabase.from_("ai_chat_sessions").upsert(session_payload, on_conflict="id").execute()

        # 2. NOW INSERT MESSAGES INTO ai_chat_messages
        meta: Dict[str, Any] = {
            "latency_ms": safe_latency,
            "engine": "deepseek-v3",
            "chat_source": "web_chat",
            "market": market,
            "cached": bool(cached),
        }
        if cache_key:
            meta["cache_key"] = cache_key
        if isinstance(tables, list) and tables:
            meta["tables"] = tables
        if isinstance(usage, dict) and usage:
            meta["usage"] = usage
        if isinstance(guard_warnings, list) and guard_warnings:
            meta["guard_warnings"] = guard_warnings
        clean_stages = _normalize_persisted_answer_stages(answer_stages)
        if clean_stages:
            meta["answer_stages"] = clean_stages
        user_row = {
            "session_id": session_id,
            "user_id": user_id,
            "role": "user",
            "content": user_msg,
            "created_at": user_created_at_iso,
        }
        if image_url:
            user_row["image_url"] = image_url

        rows = [
            user_row,
            {
                "session_id": session_id,
                "user_id": user_id,
                "role": "assistant",
                "content": reply,
                "latency_ms": safe_latency,
                "metadata": meta,
                "created_at": now_iso,
            },
        ]
        supabase.from_("ai_chat_messages").insert(rows).execute()
        logger.info(f"[agentic_chat] Successfully persisted session {session_id} and messages with latency_ms={safe_latency}.")
    except Exception as e:
        logger.warning(f"[agentic_chat] Message persistence warning: {e}")


@router.get("")
@router.get("/")
async def get_chat_root(
    request: Request,
    action: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: Optional[int] = None,
    before: Optional[str] = None,
):
    """
    Handle GET /api/ai-chat requests:
    - ?action=sessions
    - ?action=settings
    - ?session_id=...&limit=...&before=...
    """
    try:
        _init_supabase()
    except Exception:
        pass

    auth_user = get_authenticated_user(request)
    user_id = auth_user.get("id") if auth_user else None
    user_is_pro = has_chat_pro_user(user_id, supabase) if user_id else False

    if action == "sessions":
        sessions_list = []
        if user_id:
            try:
                res = (
                    supabase.from_("ai_chat_sessions")
                    .select("id, title, created_at, updated_at")
                    .eq("user_id", user_id)
                    .or_("is_deleted_by_user.is.null,is_deleted_by_user.eq.false")
                    .order("updated_at", desc=True)
                    .limit(20)
                    .execute()
                )
                sessions_list = res.data or []
            except Exception as e:
                logger.warning(f"[agentic_chat] Error fetching sessions: {e}")
                sessions_list = []

        _used, remaining, limit = get_user_chat_quota(user_id, user_is_pro)
        return JSONResponse({
            "sessions": sessions_list,
            "remaining_quota": remaining,
            "quota_limit": limit,
            "is_pro": user_is_pro,
            "autonomous_recommendations": False,
        })

    if action == "settings":
        _used, remaining, limit = get_user_chat_quota(user_id, user_is_pro)
        custom_rules = None
        if user_id:
            try:
                p_res = supabase.table("profiles").select("custom_ai_rules").eq("id", user_id).limit(1).execute()
                if p_res and p_res.data:
                    custom_rules = p_res.data[0].get("custom_ai_rules")
            except Exception:
                pass
        return JSONResponse({
            "status": "ok",
            "remaining_quota": remaining,
            "quota_limit": limit,
            "is_pro": user_is_pro,
            "unlimited": user_is_pro,
            "custom_ai_rules": custom_rules,
        })

    target_sid = session_id or request.query_params.get("session_id") or request.query_params.get("sessionId")
    if target_sid:
        raw_limit = limit if limit is not None else request.query_params.get("limit")
        page_limit = 50
        if raw_limit is not None:
            try:
                page_limit = max(1, min(int(raw_limit), 50))
            except (TypeError, ValueError):
                page_limit = 50

        raw_before = before if before is not None else request.query_params.get("before")
        before_cursor: Optional[str] = None
        if isinstance(raw_before, str):
            stripped_before = raw_before.strip()
            if stripped_before:
                if stripped_before.isdigit():
                    try:
                        before_cursor = datetime.fromtimestamp(
                            int(stripped_before) / 1000.0, tz=timezone.utc
                        ).isoformat()
                    except Exception:
                        before_cursor = None
                elif "T" in stripped_before or "-" in stripped_before:
                    before_cursor = stripped_before

        messages = []
        has_more = False
        next_before: Optional[str] = None
        if user_id:
            try:
                query = (
                    supabase.from_("ai_chat_messages")
                    .select("id, role, content, image_url, created_at, latency_ms, metadata")
                    .eq("session_id", target_sid)
                    .eq("user_id", user_id)
                )
                if before_cursor:
                    query = query.lt("created_at", before_cursor)
                res = (
                    query
                    .order("created_at", desc=True)
                    .limit(page_limit + 1)
                    .execute()
                )
                raw_rows = res.data or []
                has_more = len(raw_rows) > page_limit
                page_rows = list(reversed(raw_rows[:page_limit]))
                if has_more and page_rows:
                    next_before = page_rows[0].get("created_at")

                for m in page_rows:
                    created_at_val = m.get("created_at")
                    ts = int(time.time() * 1000)
                    if created_at_val:
                        try:
                            ts = int(datetime.fromisoformat(created_at_val.replace("Z", "+00:00")).timestamp() * 1000)
                        except Exception:
                            pass
                    meta = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
                    msg_tables = meta.get("tables") if isinstance(meta.get("tables"), list) else None
                    msg_answer_stages = _extract_message_answer_stages(m.get("role"), meta)
                    msg_item: Dict[str, Any] = {
                        "id": m.get("id"),
                        "role": m.get("role"),
                        "content": m.get("content", ""),
                        "timestamp": ts,
                        "imageUrl": m.get("image_url"),
                        "latencyMs": m.get("latency_ms"),
                    }
                    if created_at_val:
                        msg_item["createdAt"] = created_at_val
                    if msg_tables:
                        msg_item["tables"] = msg_tables
                    if msg_answer_stages:
                        msg_item["answerStages"] = msg_answer_stages
                    messages.append(msg_item)
            except Exception as e:
                logger.warning(f"[agentic_chat] Error fetching session messages: {e}")
                messages = []
                has_more = False
                next_before = None
        return JSONResponse({
            "history": messages,
            "messages": messages,
            "has_more": has_more,
            "next_before": next_before,
        })

    return JSONResponse({
        "status": "healthy",
        "service": "agentic_chat",
        "engine": "deepseek-v3",
        "mode": "async-streaming",
        "is_pro": user_is_pro,
    })


@router.put("")
@router.put("/")
async def update_session(request: Request):
    """Update session title or custom AI rules: PUT /api/ai-chat (authenticated user only)"""
    try:
        body = await request.json()
        _init_supabase()
        auth_user = get_authenticated_user(request)
        uid = auth_user.get("id") if auth_user else None
        if not uid:
            return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

        if "custom_ai_rules" in body:
            new_rules = body.get("custom_ai_rules")
            supabase.from_("profiles").update({"custom_ai_rules": new_rules or None}).eq("id", uid).execute()
            return {"status": "ok", "custom_ai_rules": new_rules}

        sid = body.get("session_id") or body.get("sessionId")
        new_title = (body.get("title") or "").strip()
        if sid and new_title:
            supabase.from_("ai_chat_sessions").update({"title": new_title}).eq("id", sid).eq("user_id", uid).execute()
            return {"status": "ok", "updated": sid, "title": new_title}
    except Exception as e:
        logger.warning(f"[agentic_chat] Failed to update session or custom rules: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
    return {"status": "ok"}
    return {"status": "ok"}


@router.delete("")
@router.delete("/")
async def delete_session(request: Request, session_id: Optional[str] = None):
    """Delete a chat session (authenticated user only)."""
    try:
        sid = session_id or request.query_params.get("session_id")
        if not sid:
            return JSONResponse({"status": "error", "message": "Missing session_id"}, status_code=400)

        _init_supabase()
        auth_user = get_authenticated_user(request)
        uid = auth_user.get("id") if auth_user else None
        if not uid:
            return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

        now_iso = datetime.now(timezone.utc).isoformat()
        supabase.from_("ai_chat_sessions").update({
            "is_deleted_by_user": True,
            "deleted_at": now_iso
        }).eq("id", sid).eq("user_id", uid).execute()
        return {"status": "ok", "deleted": sid, "success": True}
    except Exception as e:
        logger.warning(f"[agentic_chat] Session delete error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@router.post("")
@router.post("/")
@router.post("/stream")
async def chat_stream_endpoint(
    request: Request,
    body: Optional[ChatRequest] = None,
    accept: Optional[str] = Header(None),
):
    """
    Main Chatbot endpoint.
    Streams Server-Sent Events (SSE) directly to the client.
    Handles settings updates, input sanitization, JWT auth, and quota reservation.
    """
    # Parse request body safely
    if body is None:
        try:
            raw_body = await request.json()
            body = ChatRequest(**raw_body)
        except Exception:
            body = ChatRequest()

    # Handle settings action
    action = request.query_params.get("action") or body.action
    if action == "settings" or body.action == "update_settings":
        auto_enabled = bool(body.autonomous_recommendations or body.autonomousRecommendations)
        auth_user = get_authenticated_user(request)
        if auth_user and auth_user.get("id"):
            try:
                _init_supabase()
                supabase.from_("user_settings").upsert({
                    "user_id": auth_user["id"],
                    "app_state": {"chat": {"autonomous_recommendations": auto_enabled}},
                }).execute()
            except Exception:
                pass
        return JSONResponse({"ok": True, "autonomous_recommendations": auto_enabled})

    # Validate and sanitize input
    raw_user_msg = (body.message or "").strip()
    is_valid, sanitized_msg_or_err = sanitize_user_input(raw_user_msg)
    if not is_valid:
        return JSONResponse(
            status_code=400,
            content={"detail": sanitized_msg_or_err},
        )
    user_msg = sanitized_msg_or_err

    # Extract authenticated user (never blindly trust client body userId in production)
    auth_user = get_authenticated_user(request)
    verified_user_id = auth_user.get("id") if auth_user else None

    # Allow explicit local dev override only when opted in (never trust raw body.user_id in production containers)
    if not verified_user_id:
        dev_override = body.user_id or body.userId
        if dev_override and os.getenv("ALLOW_DEV_USER_ID_OVERRIDE", "").strip().lower() == "true":
            verified_user_id = dev_override

    # If still unauthenticated, return 401 Unauthorized (matching frontend login modal)
    if not verified_user_id:
        return JSONResponse(
            status_code=401,
            content={"detail": "تحتاج إلى تسجيل الدخول لاستخدام المساعد الذكي. سجّل دخولك من زر الحساب أعلى الصفحة ثم أعد إرسال سؤالك."},
        )

    # Check Pro status
    if verified_user_id == "00000000-0000-0000-0000-000000000000":
        user_is_pro = True
    else:
        _init_supabase()
        user_is_pro = has_chat_pro_user(verified_user_id, supabase) if verified_user_id else False

    has_attached_images = any(
        isinstance(img, str) and bool(img.strip())
        for img in (body.images or [])
    )
    if has_attached_images and not user_is_pro:
        return JSONResponse(
            status_code=403,
            content={
                "error": "PRO_REQUIRED",
                "detail": "تحليل صور المحفظة والشارت (Vision AI) متاح لمشتركي باقة الشات الذكي (100 ج.م) أو الباقة الشاملة Pro (150 ج.م).",
            },
        )

    # Check and consume quota
    allowed, remaining_quota, quota_limit, quota_err = check_and_consume_quota(
        verified_user_id,
        user_is_pro,
    )
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "LIMIT_REACHED",
                "limit_type": "monthly",
                "daily_limit": quota_limit,
                "detail": quota_err,
            },
        )

    session_id = body.session_id or body.sessionId or f"sess_{int(time.time() * 1000)}"
    model = body.model or "deepseek-chat"
    auto_recs = (body.autonomous_recommendations or body.autonomousRecommendations or False) and user_is_pro
    raw_market = (
        body.market
        or request.headers.get("x-egxbots-market")
        or request.query_params.get("market")
    )
    active_market = _ui_market_label(_normalize_market_code(raw_market))

    accept_header = accept if isinstance(accept, str) else (request.headers.get("accept", "") or "")
    wants_streaming = body.stream is not False or "text/event-stream" in accept_header

    primary_image_url = body.images[0] if (body.images and len(body.images) > 0 and body.images[0]) else None

    if wants_streaming:
        # Wrap generator to intercept final reply and persist messages in background
        async def streaming_wrapper():
            final_reply = ""
            final_tables: List[Any] = []
            latency_ms = 0
            was_cached = False
            used_cache_key: Optional[str] = None
            usage_stats: Optional[Dict[str, Any]] = None
            guard_warnings: Optional[List[str]] = None
            status_events: List[Dict[str, Any]] = []
            t_req_start = time.time()
            async for sse_chunk in run_agentic_chat_stream(
                message=user_msg,
                history=body.history,
                images=body.images,
                session_id=session_id,
                user_id=verified_user_id,
                model=model,
                autonomous_recommendations=auto_recs,
                is_pro=user_is_pro,
                remaining_quota=remaining_quota,
                quota_limit=quota_limit,
                market=active_market,
            ):
                line = sse_chunk.strip()
                if line.startswith("data:"):
                    data_part = line[5:].strip()
                    if data_part != "[DONE]":
                        try:
                            event = json.loads(data_part)
                            if event.get("type") == "status":
                                status_events.append(event)
                            elif event.get("type") == "done":
                                final_reply = event.get("reply", "")
                                if isinstance(event.get("tables"), list):
                                    final_tables = event.get("tables") or []
                                latency_ms = event.get("latency_ms") or int((time.time() - t_req_start) * 1000)
                                was_cached = bool(event.get("cached", False))
                                used_cache_key = event.get("cache_key")
                                if isinstance(event.get("usage"), dict):
                                    usage_stats = event.get("usage")
                                if isinstance(event.get("guard_warnings"), list):
                                    guard_warnings = event.get("guard_warnings")
                        except Exception:
                            pass
                yield sse_chunk

            if not latency_ms:
                latency_ms = int((time.time() - t_req_start) * 1000)

            usage_tools = (
                usage_stats.get("tools_used")
                if isinstance(usage_stats, dict) and isinstance(usage_stats.get("tools_used"), list)
                else None
            )
            final_answer_stages = _build_persisted_answer_stages(
                status_events,
                has_images=has_attached_images,
                tools_used=usage_tools,
                cached=was_cached,
            )

            # Persist after stream completes (skip for benchmark load tests)
            if final_reply and session_id and verified_user_id != "00000000-0000-0000-0000-000000000000":
                asyncio.create_task(
                    asyncio.to_thread(
                        _persist_message_background,
                        session_id=session_id,
                        user_id=verified_user_id,
                        user_msg=user_msg,
                        reply=final_reply,
                        latency_ms=latency_ms,
                        image_url=primary_image_url,
                        market=active_market,
                        cached=was_cached,
                        cache_key=used_cache_key,
                        tables=final_tables or None,
                        usage=usage_stats,
                        guard_warnings=guard_warnings,
                        answer_stages=final_answer_stages or None,
                    )
                )

        return StreamingResponse(
            streaming_wrapper(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
            },
        )
    else:
        # Non-streaming JSON fallback
        full_reply = ""
        tables = []
        latency_ms = 0
        was_cached = False
        used_cache_key: Optional[str] = None
        usage_stats: Optional[Dict[str, Any]] = None
        guard_warnings: Optional[List[str]] = None
        status_events: List[Dict[str, Any]] = []
        t_req_start = time.time()
        async for sse_chunk in run_agentic_chat_stream(
            message=user_msg,
            history=body.history,
            images=body.images,
            session_id=session_id,
            user_id=verified_user_id,
            model=model,
            autonomous_recommendations=auto_recs,
            is_pro=user_is_pro,
            remaining_quota=remaining_quota,
            quota_limit=quota_limit,
            market=active_market,
        ):
            line = sse_chunk.strip()
            if line.startswith("data:"):
                data_part = line[5:].strip()
                if data_part != "[DONE]":
                    try:
                        event = json.loads(data_part)
                        if event.get("type") == "status":
                            status_events.append(event)
                        elif event.get("type") == "token":
                            full_reply += event.get("token", "")
                        elif event.get("type") == "done":
                            full_reply = event.get("reply", full_reply)
                            tables = event.get("tables", [])
                            latency_ms = event.get("latency_ms") or int((time.time() - t_req_start) * 1000)
                            was_cached = bool(event.get("cached", False))
                            used_cache_key = event.get("cache_key")
                            if isinstance(event.get("usage"), dict):
                                usage_stats = event.get("usage")
                            if isinstance(event.get("guard_warnings"), list):
                                guard_warnings = event.get("guard_warnings")
                    except Exception:
                        pass

        if not latency_ms:
            latency_ms = int((time.time() - t_req_start) * 1000)

        usage_tools = (
            usage_stats.get("tools_used")
            if isinstance(usage_stats, dict) and isinstance(usage_stats.get("tools_used"), list)
            else None
        )
        final_answer_stages = _build_persisted_answer_stages(
            status_events,
            has_images=has_attached_images,
            tools_used=usage_tools,
            cached=was_cached,
        )

        if full_reply and session_id and verified_user_id != "00000000-0000-0000-0000-000000000000":
            asyncio.create_task(
                asyncio.to_thread(
                    _persist_message_background,
                    session_id=session_id,
                    user_id=verified_user_id,
                    user_msg=user_msg,
                    reply=full_reply,
                    latency_ms=latency_ms,
                    image_url=primary_image_url,
                    market=active_market,
                    cached=was_cached,
                    cache_key=used_cache_key,
                    tables=tables or None,
                    usage=usage_stats,
                    guard_warnings=guard_warnings,
                    answer_stages=final_answer_stages or None,
                )
            )

        return JSONResponse({
            "reply": full_reply,
            "session_id": session_id,
            "market": active_market,
            "tables": tables,
            "answer_stages": final_answer_stages,
            "latency_ms": latency_ms,
            "is_pro": user_is_pro,
            "remaining_quota": remaining_quota,
            "quota_limit": quota_limit,
            "cached": was_cached,
            "cache_key": used_cache_key,
            "usage": usage_stats,
        })
