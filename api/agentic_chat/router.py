"""
api/agentic_chat/router.py
FastAPI router for the parallel Python Agentic Chatbot backend.
Supports streaming SSE (text/event-stream), authenticated quota checks,
session persistence, and non-blocking async execution.
"""

import asyncio
import json
import logging
import os
import time
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Request, Header
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from api.agentic_chat.pipeline import run_agentic_chat_stream
from api.agentic_chat.auth_guard import (
    get_authenticated_user,
    check_and_consume_quota,
    get_user_chat_quota,
    sanitize_user_input,
)
from api.stock_ai import _init_supabase, supabase
from api.plan_limits import is_pro_user

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


@router.get("/health")
async def health_check():
    """Health check endpoint for the agentic chat service."""
    return {
        "status": "healthy",
        "service": "agentic_chat",
        "engine": "deepseek-v3",
        "mode": "async-streaming",
    }


def _persist_message_background(
    session_id: str,
    user_id: Optional[str],
    user_msg: str,
    reply: str,
    latency_ms: int = 0,
):
    """Save user and assistant messages to ai_chat_messages in background."""
    if user_id == "00000000-0000-0000-0000-000000000000" or not session_id:
        return
    try:
        _init_supabase()
        now_iso = datetime.now(timezone.utc).isoformat()
        title = (user_msg or "محادثة جديدة")[:45].strip()

        # 1. MUST UPSERT SESSION FIRST TO SATISFY FOREIGN KEY CONSTRAINT
        session_payload = {
            "id": session_id,
            "title": title,
            "updated_at": now_iso,
        }
        if user_id:
            session_payload["user_id"] = user_id

        supabase.from_("ai_chat_sessions").upsert(session_payload).execute()

        # 2. NOW INSERT MESSAGES INTO ai_chat_messages
        rows = [
            {
                "session_id": session_id,
                "user_id": user_id,
                "role": "user",
                "content": user_msg,
            },
            {
                "session_id": session_id,
                "user_id": user_id,
                "role": "assistant",
                "content": reply,
                "latency_ms": latency_ms,
            },
        ]
        supabase.from_("ai_chat_messages").insert(rows).execute()
        logger.info(f"[agentic_chat] Successfully persisted session {session_id} and messages.")
    except Exception as e:
        logger.warning(f"[agentic_chat] Message persistence warning: {e}")


@router.get("")
@router.get("/")
async def get_chat_root(
    request: Request,
    action: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """
    Handle GET /api/ai-chat requests:
    - ?action=sessions
    - ?action=settings
    - ?session_id=...
    """
    try:
        _init_supabase()
    except Exception:
        pass

    auth_user = get_authenticated_user(request)
    user_id = auth_user.get("id") if auth_user else None
    user_is_pro = is_pro_user(user_id, supabase) if user_id else False

    if action == "sessions":
        sessions_list = []
        if user_id:
            try:
                res = (
                    supabase.from_("ai_chat_sessions")
                    .select("id, title, created_at, updated_at")
                    .eq("user_id", user_id)
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
        return JSONResponse({
            "status": "ok",
            "remaining_quota": remaining,
            "quota_limit": limit,
            "is_pro": user_is_pro,
            "unlimited": user_is_pro,
        })

    if session_id:
        messages = []
        if user_id:
            try:
                res = (
                    supabase.from_("ai_chat_messages")
                    .select("id, role, content, image_url, created_at, latency_ms, metadata")
                    .eq("session_id", session_id)
                    .eq("user_id", user_id)
                    .order("created_at", desc=False)
                    .limit(50)
                    .execute()
                )
                for m in (res.data or []):
                    messages.append({
                        "id": m.get("id"),
                        "role": m.get("role"),
                        "content": m.get("content", ""),
                        "timestamp": m.get("created_at"),
                        "imageUrl": m.get("image_url"),
                        "latencyMs": m.get("latency_ms"),
                    })
            except Exception:
                messages = []
        return JSONResponse({"messages": messages})

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
    """Update session title: PUT /api/ai-chat { session_id, title } (authenticated user only)"""
    try:
        body = await request.json()
        sid = body.get("session_id") or body.get("sessionId")
        new_title = (body.get("title") or "").strip()
        if sid and new_title:
            _init_supabase()
            auth_user = get_authenticated_user(request)
            uid = auth_user.get("id") if auth_user else None
            if not uid:
                return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)
            supabase.from_("ai_chat_sessions").update({"title": new_title}).eq("id", sid).eq("user_id", uid).execute()
            return {"status": "ok", "updated": sid, "title": new_title}
    except Exception as e:
        logger.warning(f"[agentic_chat] Failed to update session title: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
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

        supabase.from_("ai_chat_messages").delete().eq("session_id", sid).eq("user_id", uid).execute()
        supabase.from_("ai_chat_sessions").delete().eq("id", sid).eq("user_id", uid).execute()
        return {"status": "ok", "deleted": sid}
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

    # Allow local development fallback only if explicitly local/dev or body userId provided in non-production
    if not verified_user_id:
        dev_override = body.user_id or body.userId
        if dev_override and os.getenv("NODE_ENV") != "production":
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
        user_is_pro = is_pro_user(verified_user_id, supabase) if verified_user_id else False

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

    accept_header = accept or request.headers.get("accept", "")
    wants_streaming = body.stream is not False or "text/event-stream" in accept_header

    if wants_streaming:
        # Wrap generator to intercept final reply and persist messages in background
        async def streaming_wrapper():
            final_reply = ""
            async for sse_chunk in run_agentic_chat_stream(
                message=user_msg,
                history=body.history,
                session_id=session_id,
                user_id=verified_user_id,
                model=model,
                autonomous_recommendations=auto_recs,
                is_pro=user_is_pro,
                remaining_quota=remaining_quota,
                quota_limit=quota_limit,
            ):
                line = sse_chunk.strip()
                if line.startswith("data:"):
                    data_part = line[5:].strip()
                    if data_part != "[DONE]":
                        try:
                            event = json.loads(data_part)
                            if event.get("type") == "done":
                                final_reply = event.get("reply", "")
                        except Exception:
                            pass
                yield sse_chunk

            # Persist after stream completes (skip for benchmark load tests)
            if final_reply and session_id and verified_user_id != "00000000-0000-0000-0000-000000000000":
                asyncio.create_task(
                    asyncio.to_thread(
                        _persist_message_background,
                        session_id,
                        verified_user_id,
                        user_msg,
                        final_reply,
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
        async for sse_chunk in run_agentic_chat_stream(
            message=user_msg,
            history=body.history,
            session_id=session_id,
            user_id=verified_user_id,
            model=model,
            autonomous_recommendations=auto_recs,
            is_pro=user_is_pro,
            remaining_quota=remaining_quota,
            quota_limit=quota_limit,
        ):
            line = sse_chunk.strip()
            if line.startswith("data:"):
                data_part = line[5:].strip()
                if data_part != "[DONE]":
                    try:
                        event = json.loads(data_part)
                        if event.get("type") == "token":
                            full_reply += event.get("token", "")
                        elif event.get("type") == "done":
                            full_reply = event.get("reply", full_reply)
                            tables = event.get("tables", [])
                    except Exception:
                        pass

        if full_reply and session_id and verified_user_id != "00000000-0000-0000-0000-000000000000":
            asyncio.create_task(
                asyncio.to_thread(
                    _persist_message_background,
                    session_id,
                    verified_user_id,
                    user_msg,
                    full_reply,
                )
            )

        return JSONResponse({
            "reply": full_reply,
            "session_id": session_id,
            "tables": tables,
            "is_pro": user_is_pro,
            "remaining_quota": remaining_quota,
            "quota_limit": quota_limit,
        })
