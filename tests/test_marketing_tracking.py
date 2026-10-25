import re
import urllib.parse

import pytest

import api.marketing_lifecycle as ml
from api.marketing_links import telegram_tracked_url


def _qs(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))


def test_build_tracked_url_strips_app_url_and_signs():
    url = ml.build_tracked_url(f"{ml.APP_URL}/pricing?plan=pro", "email", "trial_expiring", "abc")
    q = _qs(url)
    assert url.startswith(f"{ml.APP_URL}/api/marketing/click?")
    assert q["to"] == "/pricing?plan=pro"
    assert q["ch"] == "email" and q["c"] == "trial_expiring" and q["m"] == "abc"
    assert q["sig"] == ml._click_sig("email", "trial_expiring", "abc", "/pricing?plan=pro")


def test_signature_changes_with_target():
    a = ml._click_sig("email", "c", "m", "/pricing")
    b = ml._click_sig("email", "c", "m", "/admin")
    assert a != b


def test_email_html_contains_tracked_links():
    html = ml._build_email_html("h", "g", ["p"], "cta", f"{ml.APP_URL}/pricing", "u1", "a@b.com", "abandoned_checkout", "mid1")
    assert html.count("/api/marketing/click?") == 2
    assert "t.me%2Fegxbots_bot" in html or "t.me/egxbots_bot" in html
    assert 'href="https://t.me/egxbots_bot"' not in html


def test_telegram_tracked_url_unsigned_and_safe():
    url = telegram_tracked_url("/pricing", "tg_exit")
    q = _qs(url)
    assert q == {"ch": "telegram", "c": "tg_exit", "to": "/pricing"}
    # Unsafe campaign or non-internal path falls back to the plain destination.
    assert "/api/marketing/click" not in telegram_tracked_url("/pricing", "Bad Campaign!")
    assert "/api/marketing/click" not in telegram_tracked_url("//evil.com", "tg_exit")
