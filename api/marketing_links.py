"""Tracked links for Telegram promo messages (clicks are recorded by /api/marketing/click)."""
import re
import urllib.parse

from api.web_origin import get_web_origin

_CAMPAIGN_RE = re.compile(r"^[a-z0-9_:-]{1,40}$")


def telegram_tracked_url(path: str, campaign: str) -> str:
    """Return a short redirect URL that records a Telegram click for `campaign`, then opens `path`.

    Falls back to the plain destination if the campaign name is not a safe slug.
    """
    origin = get_web_origin()
    if not path.startswith("/") or path.startswith("//") or not _CAMPAIGN_RE.match(campaign):
        return f"{origin}{path if path.startswith('/') else '/'}"
    qs = urllib.parse.urlencode({"ch": "telegram", "c": campaign, "to": path}, safe="/:")
    return f"{origin}/api/marketing/click?{qs}"
