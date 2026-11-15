"""Marketing & email campaign tracking endpoints hosted on the Python HF backend.

Handles Resend Svix webhooks, signed click redirects, and one-click unsubscribe
so email campaign traffic never consumes Vercel Serverless Function / Active CPU quota.
"""

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import html
import json
import math
import os
import re
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import api.stock_ai as stock_ai
from api.marketing_lifecycle import _click_sig, verify_unsub_token
from api.web_origin import get_web_origin

router = APIRouter()

_EVENT_MAP: Dict[str, str] = {
    "email.delivered": "delivered",
    "email.opened": "opened",
    "email.clicked": "clicked",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.delivery_delayed": "delivery_delayed",
}
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_CAMPAIGN_RE = re.compile(r"^[a-z0-9_:-]{1,40}$")
_ALLOWED_EXTERNAL_HOSTS = {"t.me"}


def _get_supabase():
    """Return initialized Supabase service client or None if unavailable."""
    if not stock_ai.supabase:
        stock_ai._init_supabase()
    return stock_ai.supabase if stock_ai.supabase else None


def _verify_svix(body: str, svix_id: str, timestamp: str, signature_header: str, secret: str) -> bool:
    """Verify Svix HMAC-SHA256 webhook signature within a 5-minute replay window."""
    try:
        ts = float(timestamp)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(ts) or abs(time.time() - ts) > 5 * 60:
        return False

    raw_secret = secret[6:] if secret.startswith("whsec_") else secret
    try:
        key = base64.b64decode(raw_secret, validate=True)
    except Exception:
        return False

    signed_payload = f"{svix_id}.{timestamp}.{body}".encode("utf-8")
    expected = base64.b64encode(hmac.new(key, signed_payload, hashlib.sha256).digest()).decode("ascii")

    for part in signature_header.split(" "):
        if "," not in part:
            continue
        version, sig = part.split(",", 1)
        if version == "v1" and sig and hmac.compare_digest(sig, expected):
            return True
    return False


def _is_duplicate_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code == "23505":
        return True
    text = str(exc)
    return "23505" in text or "duplicate key" in text.lower()


def _is_internal_path(target: str) -> bool:
    return target.startswith("/") and not target.startswith("//") and "\\" not in target


@router.get("/marketing/resend-webhook")
@router.get("/api/marketing/resend-webhook")
async def resend_webhook_status():
    """Health/configuration status for the Resend webhook endpoint."""
    configured = bool(os.getenv("RESEND_WEBHOOK_SECRET", "").strip())
    return {
        "ok": True,
        "service": "resend-webhook",
        "backend": "huggingface",
        "configured": configured,
        "events_tracked": list(_EVENT_MAP.values()),
        "instructions": (
            "Webhook secret configured. Register https://weeasdwee-ai-bot.hf.space/marketing/resend-webhook in Resend Dashboard -> Webhooks."
            if configured
            else "RESEND_WEBHOOK_SECRET is missing on Hugging Face Space secrets."
        ),
    }


@router.post("/marketing/resend-webhook")
@router.post("/api/marketing/resend-webhook")
async def resend_webhook_ingest(request: Request):
    """Ingest signed Resend Svix webhook events into Supabase marketing_events."""
    secret = os.getenv("RESEND_WEBHOOK_SECRET", "").strip()
    if not secret:
        return JSONResponse({"error": "webhook_not_configured"}, status_code=503)

    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8", errors="replace")
    svix_id = request.headers.get("svix-id", "")
    svix_ts = request.headers.get("svix-timestamp", "")
    svix_sig = request.headers.get("svix-signature", "")

    if not svix_id or not svix_ts or not svix_sig or not _verify_svix(body_str, svix_id, svix_ts, svix_sig, secret):
        return JSONResponse({"error": "invalid_signature"}, status_code=401)

    try:
        payload: Dict[str, Any] = json.loads(body_str)
    except Exception:
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    if not isinstance(payload, dict):
        return JSONResponse({"error": "invalid_json"}, status_code=400)

    event_type = _EVENT_MAP.get(str(payload.get("type") or ""))
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    provider_id = data.get("email_id") or data.get("id") or svix_id
    if not event_type or not provider_id:
        return {"ok": True, "ignored": True}

    client = _get_supabase()
    if client is None:
        return JSONResponse({"error": "server_error"}, status_code=503)

    try:
        msg_res = (
            client.table("marketing_message_log")
            .select("id,user_id,message_type")
            .eq("provider_message_id", provider_id)
            .limit(1)
            .execute()
        )
        rows = getattr(msg_res, "data", None) or []
        msg = rows[0] if rows else None

        matched_user_id = msg.get("user_id") if msg else None
        campaign = (msg.get("message_type") if msg else None) or "email_campaign"
        message_id = msg.get("id") if msg else None

        to_list = data.get("to") if isinstance(data.get("to"), list) else []
        if not msg and to_list:
            recipient = str(to_list[0]).strip().lower()
            recent_res = (
                client.table("marketing_message_log")
                .select("id,user_id,message_type")
                .eq("email", recipient)
                .order("sent_at", desc=True)
                .limit(1)
                .execute()
            )
            recent_rows = getattr(recent_res, "data", None) or []
            if recent_rows:
                recent = recent_rows[0]
                matched_user_id = recent.get("user_id")
                campaign = recent.get("message_type") or campaign
                message_id = recent.get("id")

        client.table("marketing_events").insert({
            "event_type": event_type,
            "channel": "email",
            "campaign": campaign,
            "message_id": message_id,
            "provider_message_id": provider_id,
            "user_id": matched_user_id,
            "target": ", ".join(str(item) for item in to_list) if to_list else None,
            "svix_id": svix_id,
        }).execute()
    except Exception as exc:
        if _is_duplicate_error(exc):
            return {"ok": True, "tracked": event_type}
        print(f"[marketing/resend-webhook] error: {exc}")
        return JSONResponse({"error": "db_error"}, status_code=500)

    return {"ok": True, "tracked": event_type}


@router.get("/marketing/click")
@router.get("/api/marketing/click")
async def marketing_click_redirect(
    ch: str = Query(default="email"),
    c: str = Query(default=""),
    m: str = Query(default=""),
    to: str = Query(default="/"),
    sig: str = Query(default=""),
):
    """Record a marketing link click and safely redirect to the target URL."""
    channel = "telegram" if ch == "telegram" else "email"
    origin = get_web_origin().rstrip("/")
    fallback_url = f"{origin}/"

    signed = False
    if sig:
        expected = _click_sig(channel, c, m, to)
        signed = hmac.compare_digest(sig, expected)
        if not signed:
            return RedirectResponse(url=fallback_url, status_code=302)

    destination: Optional[str] = None
    if _is_internal_path(to):
        destination = f"{origin}{to}"
    elif signed:
        try:
            parsed = urlparse(to)
            if parsed.scheme == "https" and parsed.hostname in _ALLOWED_EXTERNAL_HOSTS:
                destination = to
        except Exception:
            destination = None

    if not destination:
        return RedirectResponse(url=fallback_url, status_code=302)

    if _CAMPAIGN_RE.match(c) and (signed or channel == "telegram"):
        client = _get_supabase()
        if client is not None:
            try:
                msg_id = m if _UUID_RE.match(m) else None
                user_id = None
                if msg_id:
                    res = (
                        client.table("marketing_message_log")
                        .select("user_id")
                        .eq("id", msg_id)
                        .limit(1)
                        .execute()
                    )
                    rows = getattr(res, "data", None) or []
                    if rows:
                        user_id = rows[0].get("user_id")

                client.table("marketing_events").insert({
                    "event_type": "clicked",
                    "channel": channel,
                    "campaign": c,
                    "message_id": msg_id,
                    "user_id": user_id,
                    "target": to[:200],
                }).execute()
            except Exception as exc:
                print(f"[marketing/click] could not record click: {exc}")

    return RedirectResponse(
        url=destination,
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/marketing/unsubscribe")
@router.get("/api/marketing/unsubscribe")
async def marketing_unsubscribe(
    uid: str = Query(default=""),
    email: str = Query(default=""),
    token: str = Query(default=""),
):
    """Handle signed one-click email unsubscribe links."""
    if not uid or not email or not token:
        return HTMLResponse(content="رابط غير صالح", status_code=400)

    try:
        is_valid = verify_unsub_token(uid, email, token)
    except Exception:
        is_valid = False

    if not is_valid:
        return HTMLResponse(content="رمز التحقق غير صالح أو منتهي الصلاحية", status_code=403)

    client = _get_supabase()
    if client is None:
        return HTMLResponse(content="حدث خطأ أثناء معالجة الطلب", status_code=503)

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        client.table("marketing_preferences").upsert(
            {
                "user_id": uid,
                "email": email.lower().strip(),
                "unsubscribed_all": True,
                "unsubscribed_at": now_iso,
                "updated_at": now_iso,
            },
            on_conflict="user_id",
        ).execute()
    except Exception as exc:
        print(f"[marketing/unsubscribe] error: {exc}")
        return HTMLResponse(content="حدث خطأ أثناء معالجة الطلب", status_code=500)

    safe_email = html.escape(email)
    body = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
  <meta charset="utf-8">
  <title>تم إلغاء الاشتراك بنجاح | EGX BOTS</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 40px 16px; background-color: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; direction: rtl; text-align: right;">
  <div style="max-width: 500px; margin: 40px auto; background: #fff; border: 3px solid #000; box-shadow: 6px 6px 0px #000; padding: 32px 24px; text-align: center;">
    <h1 style="margin: 0 0 16px; font-size: 22px; font-weight: 900; color: #111;">تم إلغاء الاشتراك بنجاح ✅</h1>
    <p style="font-size: 14px; line-height: 1.7; color: #4b5563; margin-bottom: 24px;">
      لن تتلقى أي رسائل تسويقية أو تذكيرات عروض على بريدك الإلكتروني (<strong>{safe_email}</strong>) بعد الآن.
      ستظل تتلقى الإشعارات الهامة المتعلقة بحسابك أو معاملاتك المالية.
    </p>
    <a href="https://egxbots.com" style="display: inline-block; padding: 12px 24px; background: #FFE600; color: #000; text-decoration: none; font-weight: 900; font-size: 14px; border: 2px solid #000; box-shadow: 3px 3px 0px #000;">
      العودة للمنصة الرئيسية ←
    </a>
  </div>
</body>
</html>"""
    return HTMLResponse(content=body, status_code=200)
