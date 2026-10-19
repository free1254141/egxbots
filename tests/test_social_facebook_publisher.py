import json
from unittest.mock import MagicMock
from api.social_facebook_publisher import (
    get_facebook_credentials,
    select_primary_daily_report,
    publish_photo_to_facebook_page,
    auto_publish_daily_report_to_facebook,
)


def test_select_primary_daily_report_prefers_market_then_stock():
    reports = {
        "stock": {"status": "ready", "symbol": "COMI"},
        "market": {"status": "ready", "kind": "market"},
    }
    kind, report = select_primary_daily_report(reports)
    assert kind == "market"
    assert report["kind"] == "market"

    # Only stock ready
    kind, report = select_primary_daily_report({"stock": {"status": "ready", "symbol": "POUL"}})
    assert kind == "stock"
    assert report["symbol"] == "POUL"


def test_auto_publish_skips_when_no_token(monkeypatch):
    monkeypatch.delenv("FACEBOOK_PAGE_ACCESS_TOKEN", raising=False)
    client = MagicMock()
    # market_cache returns no payload
    client.table().select().eq().maybe_single().execute.return_value = MagicMock(data=None)

    result = auto_publish_daily_report_to_facebook(client, "2026-10-19")
    assert result == {"status": "skipped", "reason": "Token not configured"}


def test_auto_publish_skips_if_already_published(monkeypatch):
    monkeypatch.setenv("FACEBOOK_PAGE_ACCESS_TOKEN", "TEST_TOKEN")
    monkeypatch.setenv("FACEBOOK_PAGE_ID", "egxbots")

    client = MagicMock()
    client.table().select().eq().eq().maybe_single().execute.return_value = MagicMock(
        data={"state": "published", "post_id": "123_456", "kind": "market"}
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
