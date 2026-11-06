"""Autonomous Facebook Page publisher for daily verified session reports.

Publishes directly to the official Facebook Page via Meta Graph API without human intervention.
No groups or third-party web scraping; uses official Graph API photo endpoint.
"""
import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger("social_facebook_publisher")

DEFAULT_PAGE_ID = "egxbots"
GRAPH_API_VERSION = os.getenv("FACEBOOK_GRAPH_API_VERSION", "v19.0")

# Retries are intentionally short: the daily pipeline must never queue behind a
# Facebook hiccup. 3 retries after the first failure, max ~7s of backoff total.
FACEBOOK_PUBLISH_RETRIES = int(os.getenv("FACEBOOK_PUBLISH_RETRIES", "3"))
FACEBOOK_RETRY_BACKOFF_SECONDS = (1, 2, 4)
FACEBOOK_HTTP_TIMEOUT_SECONDS = int(os.getenv("FACEBOOK_API_TIMEOUT_SECONDS", "20"))


def _is_transient_publish_error(exc: BaseException) -> bool:
    """Network/TLS/timeout errors are retryable; Graph API 4xx responses are not."""
    if isinstance(exc, urllib.error.HTTPError):
        return False
    return isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ssl.SSLError))


def get_facebook_credentials(client=None):
    """Retrieve Facebook Page ID and Access Token from environment or market_cache."""
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN")
    page_id = os.getenv("FACEBOOK_PAGE_ID") or DEFAULT_PAGE_ID

    if token:
        return {"page_id": page_id, "token": token}

    if client is not None:
        try:
            res = (
                client.table("market_cache")
                .select("payload")
                .eq("cache_key", "facebook_page_credentials")
                .maybe_single()
                .execute()
            )
            if res and res.data and res.data.get("payload"):
                payload = res.data["payload"]
                if payload.get("token"):
                    return {
                        "page_id": payload.get("page_id") or payload.get("pageId") or page_id,
                        "token": payload["token"],
                    }
        except Exception as e:
            logger.warning(f"[FB_AUTO] Could not read credentials from market_cache: {e}")

    return None


def is_report_publishable_with_content(report):
    """Validate that a daily social report contains non-empty, actionable data.

    Prevents publishing placeholder cards or zero-match scans to official feeds.
    """
    if not report or not isinstance(report, dict):
        return False

    # Image must be ready and present
    if not report.get("image_url") or report.get("image_status") != "ready":
        return False

    kind = report.get("kind")
    caption = report.get("social_caption") or report.get("social_title") or report.get("content") or ""

    # Never publish empty scans that mention zero results
    empty_phrases = (
        "لا توجد نتائج",
        "لا توجد نتائج مطابقة",
        "صفر نتائج",
        "لم تظهر إشارات",
        "لا توجد أي أسهم",
        "لا يوجد أسهم",
        "لا توجد أسهم",
        "0 أسهم",
    )
    if any(phrase in caption for phrase in empty_phrases):
        logger.info(f"[FB_VALIDATOR] Rejected report ({kind}): caption indicates empty results")
        return False

    # Check evidence data if present
    evidence = report.get("evidence")
    if evidence and isinstance(evidence, list):
        if kind == "accumulation":
            for item in evidence:
                if item.get("tool") == "get_accumulation_stocks":
                    stocks = (item.get("data") or {}).get("stocks") or []
                    if len(stocks) == 0:
                        logger.info("[FB_VALIDATOR] Rejected accumulation report: 0 stocks in evidence")
                        return False
        elif kind in ("stock", "follow_up"):
            for item in evidence:
                if item.get("tool") == "get_stock":
                    data = item.get("data") or {}
                    if not data.get("price") or data.get("price") == "—":
                        logger.info("[FB_VALIDATOR] Rejected stock report: missing price in evidence")
                        return False

    # For stock/follow_up, symbol must be defined
    if kind in ("stock", "follow_up") and not report.get("symbol"):
        logger.info(f"[FB_VALIDATOR] Rejected {kind} report: missing symbol")
        return False

    return True


def select_primary_daily_report(reports_dict):
    """Select the best report of the session (stock or market) to publish."""
    # Priority order for social feed
    for kind in ("market", "stock", "accumulation", "follow_up"):
        r = reports_dict.get(kind)
        if r and is_report_publishable_with_content(r):
            return kind, r
    return None, None



def publish_photo_to_facebook_page(image_url, caption, page_id, token, opener=None):
    """Call Meta Graph API to upload photo and publish post to the Page."""
    if not image_url or not token:
        raise ValueError("Missing image_url or access token")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{urllib.parse.quote(page_id)}/photos"
    payload = json.dumps({
        "url": image_url,
        "caption": caption or "",
        "access_token": token,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    call_opener = opener or urllib.request.urlopen
    with call_opener(req, timeout=FACEBOOK_HTTP_TIMEOUT_SECONDS) as response:
        data = json.loads(response.read().decode("utf-8"))
        post_id = data.get("id") or data.get("post_id")
        return {"success": True, "post_id": post_id, "raw": data}


def publish_photo_with_retries(
    image_url,
    caption,
    page_id,
    token,
    opener=None,
    retries: int | None = None,
):
    """Publish a photo, retrying ONLY transient network/TLS/timeout failures.

    The first attempt plus at most `retries` retries (default 3). Backoff is
    deliberately tiny (1s, 2s, 4s) so nothing downstream waits on a failing
    Facebook call. Graph API errors (HTTP 4xx) are raised immediately.
    """
    total_retries = FACEBOOK_PUBLISH_RETRIES if retries is None else max(0, retries)
    max_attempts = total_retries + 1
    last_exc: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            res = publish_photo_to_facebook_page(
                image_url=image_url,
                caption=caption,
                page_id=page_id,
                token=token,
                opener=opener,
            )
            if attempt > 1:
                logger.info(f"[FB_PUBLISH] Succeeded on attempt {attempt}/{max_attempts}")
            return res
        except Exception as exc:  # noqa: BLE001 - classified below
            last_exc = exc
            if not _is_transient_publish_error(exc) or attempt >= max_attempts:
                logger.error(f"[FB_PUBLISH] Failed on attempt {attempt}/{max_attempts}: {exc}")
                raise
            delay = FACEBOOK_RETRY_BACKOFF_SECONDS[min(attempt - 1, len(FACEBOOK_RETRY_BACKOFF_SECONDS) - 1)]
            logger.warning(
                f"[FB_PUBLISH] Transient error on attempt {attempt}/{max_attempts}: {exc}. Retrying in {delay}s"
            )
            time.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Facebook publish failed without an exception")


def auto_publish_daily_report_to_facebook(client, session_date, job_run_id=None, opener=None):
    """Fully automated step called after daily report images are generated.

    1. Checks if Facebook Page Access Token is configured.
    2. Checks if already published for this session_date to avoid duplicates.
    3. Finds ready reports with generated image URLs.
    4. Publishes to Facebook Page via Graph API.
    5. Records state into daily_social_publications.
    """
    if not client:
        return {"status": "skipped", "reason": "No supabase client"}

    creds = get_facebook_credentials(client)
    if not creds or not creds.get("token"):
        logger.info("[FB_AUTO] Auto-publish skipped: FACEBOOK_PAGE_ACCESS_TOKEN not configured")
        return {"status": "skipped", "reason": "Token not configured"}

    # 1. Check if already published for this session_date
    try:
        existing = (
            client.table("daily_social_publications")
            .select("state, post_id, kind")
            .eq("session_date", session_date)
            .eq("platform", "facebook")
            .limit(1)
            .execute()
        )
        existing_row = existing.data[0] if (existing and existing.data and len(existing.data) > 0) else None
        if existing_row and existing_row.get("state") == "published":
            logger.info(f"[FB_AUTO] Session {session_date} already published on Facebook ({existing_row.get('post_id')})")
            return {
                "status": "cached",
                "post_id": existing_row.get("post_id"),
                "kind": existing_row.get("kind"),
            }
    except Exception as e:
        logger.warning(f"[FB_AUTO] Check publication query warning: {e}")

    # 2. Fetch reports for this date
    try:
        query = (
            client.table("daily_social_reports")
            .select("session_date, kind, symbol, image_status, image_url, social_caption, social_title, evidence")
            .eq("session_date", session_date)
            .eq("image_status", "ready")
        )
        if job_run_id:
            query = query.eq("job_run_id", job_run_id)
        reports = query.limit(10).execute().data
    except Exception as e:
        logger.error(f"[FB_AUTO] Failed to query ready reports: {e}")
        return {"status": "failed", "error": str(e)}

    if not reports:
        logger.info(f"[FB_AUTO] No ready report images found for session {session_date}")
        return {"status": "skipped", "reason": "No ready images"}

    # Filter only reports that have genuine content
    valid_reports = [r for r in reports if is_report_publishable_with_content(r)]
    if not valid_reports:
        logger.info(f"[FB_AUTO] No publishable reports with content found for session {session_date}")
        return {"status": "skipped", "reason": "No publishable reports with content"}

    reports_by_kind = {r["kind"]: r for r in valid_reports}
    kind, selected_report = select_primary_daily_report(reports_by_kind)
    if not selected_report:
        selected_report = valid_reports[0]
        kind = selected_report.get("kind", "stock")

    image_url = selected_report.get("image_url")
    caption = selected_report.get("social_caption") or selected_report.get("social_title") or ""

    if not image_url:
        return {"status": "failed", "reason": "Missing image_url"}

    # 3. Publish to Facebook Page
    try:
        result = publish_photo_with_retries(
            image_url=image_url,
            caption=caption,
            page_id=creds["page_id"],
            token=creds["token"],
            opener=opener,
        )
        post_id = result.get("post_id")
        logger.info(f"[FB_AUTO] Successfully published to Facebook Page: {post_id}")

        # 4. Record to daily_social_publications
        client.table("daily_social_publications").upsert({
            "session_date": session_date,
            "platform": "facebook",
            "kind": kind,
            "state": "published",
            "post_id": post_id,
            "error": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        return {
            "status": "published",
            "post_id": post_id,
            "kind": kind,
            "page_id": creds["page_id"],
        }
    except Exception as e:
        logger.error(f"[FB_AUTO] Error publishing to Facebook Page after retries: {e}")
        try:
            client.table("daily_social_publications").upsert({
                "session_date": session_date,
                "platform": "facebook",
                "kind": kind,
                "state": "failed",
                "error": f"after {FACEBOOK_PUBLISH_RETRIES + 1} attempts: {str(e)[:230]}",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception:
            pass
        return {"status": "failed", "error": str(e), "attempts": FACEBOOK_PUBLISH_RETRIES + 1}
