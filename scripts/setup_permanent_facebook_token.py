"""Exchange short-lived user token for permanent Never-Expiring Page Token and persist to database."""
import json
import logging
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("setup_fb_token")

APP_ID = "1603642448173628"
APP_SECRET = "7a100e933d81448bddf4c11e2b3d4adb"
USER_TOKEN = "EAAWygRp4WjwBS8aSZBZC28FDSdgOi254FVxZCSBm9pitrhPrE8ie10yfZAwzTeSxwsnhgP5m9beGgr9TdvwgmRjeGZBsKSXDz4BcqshHI8ztxoEEbXoum6KsSxFG7ZCcehrVHD9YSgHutVZCR2lWd3ZC2ML14eKSyZCRV0OuSEjJE0eAShp050yTCauN9xwAUtoxRBlIl3tLZCYweF96cVBw6DFwlrfyON5WLUdeyCwAZDZD"
PAGE_ID = "1107903499083226"

def main():
    logger.info("Step 1: Exchanging short-lived user token for 60-day Long-Lived User Token...")
    params = urllib.parse.urlencode({
        "grant_type": "fb_exchange_token",
        "client_id": APP_ID,
        "client_secret": APP_SECRET,
        "fb_exchange_token": USER_TOKEN,
    })
    url = f"https://graph.facebook.com/v19.0/oauth/access_token?{params}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        res1 = json.loads(resp.read().decode("utf-8"))
        long_user_token = res1.get("access_token")
        expires_in = res1.get("expires_in", 0)
        logger.info(f"Obtained Long-Lived User Token! Valid for: {expires_in // 86400} days")

    logger.info(f"Step 2: Fetching Never-Expiring Page Token for Page {PAGE_ID}...")
    url2 = f"https://graph.facebook.com/v19.0/{PAGE_ID}?fields=access_token,name,id&access_token={long_user_token}"
    with urllib.request.urlopen(url2, timeout=15) as resp:
        res2 = json.loads(resp.read().decode("utf-8"))
        page_token = res2.get("access_token")
        page_name = res2.get("name")
        logger.info(f"Obtained Page Access Token for '{page_name}' (ID: {PAGE_ID})")

    logger.info("Step 3: Verifying token expiration via debug_token endpoint...")
    debug_params = urllib.parse.urlencode({
        "input_token": page_token,
        "access_token": f"{APP_ID}|{APP_SECRET}",
    })
    debug_url = f"https://graph.facebook.com/debug_token?{debug_params}"
    with urllib.request.urlopen(debug_url, timeout=15) as resp:
        dbg = json.loads(resp.read().decode("utf-8")).get("data", {})
        is_valid = dbg.get("is_valid")
        expires_at = dbg.get("expires_at")
        scopes = dbg.get("scopes", [])
        logger.info(f"Token is_valid: {is_valid}")
        logger.info(f"Token expires_at: {expires_at} (0 = NEVER EXPIRES / PERMANENT)")
        logger.info(f"Token scopes: {scopes}")

    logger.info("Step 4: Persisting permanent token to Supabase market_cache...")
    from api.short_swings_daily import _get_supabase_client
    client = _get_supabase_client()
    payload = {
        "page_id": PAGE_ID,
        "pageId": PAGE_ID,
        "page_name": page_name,
        "pageName": page_name,
        "token": page_token,
        "never_expires": (expires_at == 0),
        "app_id": APP_ID,
    }
    client.table("market_cache").upsert({
        "cache_key": "facebook_page_credentials",
        "payload": payload,
        "country": "EG",
    }, on_conflict="cache_key,country").execute()
    logger.info("SUCCESS: Permanent Page Token saved in database!")

    return page_token

if __name__ == "__main__":
    main()
