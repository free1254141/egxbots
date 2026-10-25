import json
from unittest.mock import MagicMock, patch

from api.social_facebook_publisher import (
    get_facebook_credentials,
    select_primary_daily_report,
    publish_photo_to_facebook_page,
    auto_publish_daily_report_to_facebook,
    is_report_publishable_with_content,
)


def test_get_facebook_credentials_from_env(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "TEST_ENV_TOKEN")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "987654321")

    creds = get_facebook_credentials()
    assert creds == {"page_id": "987654321", "token": "TEST_ENV_TOKEN"}


def test_get_facebook_credentials_from_market_cache(monkeypatch):
    monkeypatch.delenv("FACEBOOK_PAGE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FACEBOOK_PAGE_ID", raising=False)

    mock_client = MagicMock()
    mock_client.table().select().eq().maybe_single().execute.return_value = MagicMock(
        data={"payload": {"token": "MARKET_CACHE_TOKEN", "page_id": "112233"}}
    )

    creds = get_facebook_credentials(mock_client)
    assert creds == {"page_id": "112233", "token": "MARKET_CACHE_TOKEN"}


def test_auto_publish_skips_when_no_token(monkeypatch):
    monkeypatch.delenv("FACEBOOK_PAGE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FACEBOOK_PAGE_ID", raising=False)

    client = MagicMock()
    client.table().select().eq().maybe_single().execute.return_value = MagicMock(data=None)

    result = auto_publish_daily_report_to_facebook(client, "2026-10-19")
    assert result == {"status": "skipped", "reason": "Token not configured"}


def test_auto_publish_skips_if_already_published(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "TEST_TOKEN")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "egxbots")

    client = MagicMock()
    client.table().select().eq().eq().limit().execute.return_value = MagicMock(
        data=[{"state": "published", "post_id": "123_456", "kind": "market"}]
    )

    result = auto_publish_daily_report_to_facebook(client, "2026-10-19")
    assert result == {"status": "cached", "post_id": "123_456", "kind": "market"}


def test_publish_photo_to_facebook_page_calls_graph_api():
    mock_opener = MagicMock()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"id": "fb_post_789"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_opener.return_value = mock_resp

    res = publish_photo_to_facebook_page(
        image_url="https://test.com/photo.png",
        caption="EGX Market Report",
        page_id="egxbots",
        token="EAAG_TEST",
        opener=mock_opener,
    )

    assert res["success"] is True
    assert res["post_id"] == "fb_post_789"


def test_is_report_publishable_with_content():
    # Empty accumulation report with 0 stocks in evidence
    empty_acc = {
        "kind": "accumulation",
        "image_status": "ready",
        "image_url": "https://test.com/acc.png",
        "social_caption": "لا توجد نتائج مطابقة في العينة",
        "evidence": [{"tool": "get_accumulation_stocks", "data": {"stocks": []}}],
    }
    assert is_report_publishable_with_content(empty_acc) is False

    # Empty caption phrase
    caption_empty = {
        "kind": "stock",
        "symbol": "COMI",
        "image_status": "ready",
        "image_url": "https://test.com/comi.png",
        "social_caption": "صفر نتائج في الجلسة",
    }
    assert is_report_publishable_with_content(caption_empty) is False

    # Valid accumulation report with stocks
    valid_acc = {
        "kind": "accumulation",
        "image_status": "ready",
        "image_url": "https://test.com/acc.png",
        "social_caption": "تقرير إشارات التجميع لأسهم البورصة المصرية اليوم",
        "evidence": [{"tool": "get_accumulation_stocks", "data": {"stocks": [{"symbol": "COMI", "acc_score": 85}]}}],
    }
    assert is_report_publishable_with_content(valid_acc) is True

    # Valid market report
    valid_market = {
        "kind": "market",
        "image_status": "ready",
        "image_url": "https://test.com/market.png",
        "social_caption": "أداء المؤشرات الرئيسية في البورصة المصرية",
    }
    assert is_report_publishable_with_content(valid_market) is True
