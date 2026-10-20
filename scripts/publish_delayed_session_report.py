"""Publish delayed report for session 2026-10-20 to official Facebook Page using the new permanent token."""
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.short_swings_daily import _get_supabase_client
from api.social_facebook_publisher import get_facebook_credentials, publish_photo_to_facebook_page

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("publish_delayed")

def main():
    client = _get_supabase_client()
    creds = get_facebook_credentials(client)
    if not creds or not creds.get("token"):
        logger.error("No Facebook credentials found")
        return

    logger.info(f"Using Facebook Page ID: {creds['page_id']}")
    
    # Fetch 2026-10-20 market report
    rep = client.table("daily_social_reports").select("*").eq("session_date", "2026-10-20").eq("kind", "market").maybe_single().execute()
    r = rep.data if rep else None
    if not r or not r.get("image_url"):
        logger.error("No ready market report found for 2026-10-20")
        return

    image_url = r["image_url"]
    caption = r["social_caption"]
    logger.info(f"Publishing image {image_url} to Facebook...")
    res = publish_photo_to_facebook_page(image_url, caption, creds["page_id"], creds["token"])
    logger.info(f"Published successfully! Result: {res}")
    
    post_id = res.get("post_id")
    post_url = f"https://www.facebook.com/{post_id}"
    print(f"LIVE_POST_URL: {post_url}")

    # Record into daily_social_publications
    client.table("daily_social_publications").upsert({
        "session_date": "2026-10-20",
        "platform": "facebook",
        "kind": "market",
        "state": "published",
        "post_id": post_id,
        "error": None,
        "publication_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, on_conflict="session_date,platform,kind").execute()
    logger.info("Recorded state into daily_social_publications as published.")

if __name__ == "__main__":
    main()
