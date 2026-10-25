from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, patch
import pytest

from api.social_scheduler import (
    SCHEDULED_SLOTS,
    _completed_slots_today,
    _completed_slots_lock,
    is_egx_trading_day,
    resolve_session_date_for_slot,
    is_slot_due,
    execute_publication_slot,
)
from api.social_facebook_publisher import is_report_publishable_with_content

CAIRO_TZ = ZoneInfo("Africa/Cairo")


def test_is_egx_trading_day():
    sun = datetime(2026, 10, 18, 12, 0, tzinfo=CAIRO_TZ)  # Sunday
    mon = datetime(2026, 10, 19, 12, 0, tzinfo=CAIRO_TZ)  # Monday
    thu = datetime(2026, 10, 22, 12, 0, tzinfo=CAIRO_TZ)  # Thursday
    fri = datetime(2026, 10, 23, 12, 0, tzinfo=CAIRO_TZ)  # Friday (weekend)
    sat = datetime(2026, 10, 24, 12, 0, tzinfo=CAIRO_TZ)  # Saturday (weekend)

    assert is_egx_trading_day(sun) is True
    assert is_egx_trading_day(mon) is True
    assert is_egx_trading_day(thu) is True
    assert is_egx_trading_day(fri) is False
    assert is_egx_trading_day(sat) is False


def test_resolve_session_date_for_slot():
    evening_slot = SCHEDULED_SLOTS[0]  # market_evening, target: current_session
    morning_slot = SCHEDULED_SLOTS[2]  # accumulation_morning, target: latest_closed_session

    mon_19 = datetime(2026, 10, 19, 18, 45, tzinfo=CAIRO_TZ)  # Monday
    sun_18 = datetime(2026, 10, 18, 8, 45, tzinfo=CAIRO_TZ)   # Sunday morning

    assert resolve_session_date_for_slot(evening_slot, mon_19) == "2026-10-19"
    assert resolve_session_date_for_slot(morning_slot, sun_18) == "2026-10-15"
    assert resolve_session_date_for_slot(morning_slot, mon_19) == "2026-10-18"


def test_is_slot_due():
    slot = {"time": "18:45"}
    at_time = datetime(2026, 10, 19, 18, 45, tzinfo=CAIRO_TZ)
    within_window = datetime(2026, 10, 19, 18, 52, tzinfo=CAIRO_TZ)
    too_early = datetime(2026, 10, 19, 18, 30, tzinfo=CAIRO_TZ)
    too_late = datetime(2026, 10, 19, 19, 10, tzinfo=CAIRO_TZ)
    catch_up_later = datetime(2026, 10, 19, 22, 30, tzinfo=CAIRO_TZ)
    next_day = datetime(2026, 10, 20, 0, 5, tzinfo=CAIRO_TZ)

    assert is_slot_due(slot, at_time) is True
    assert is_slot_due(slot, within_window) is True
    assert is_slot_due(slot, too_early) is False
    assert is_slot_due(slot, too_late) is False
    assert is_slot_due(slot, too_late, window_minutes=900) is True
    assert is_slot_due(slot, catch_up_later, window_minutes=900) is True
    assert is_slot_due(slot, next_day, window_minutes=900) is False


def test_execute_publication_slot_skips_if_already_published():
    mock_client = MagicMock()
    mock_client.table().select().eq().eq().eq().limit().execute.return_value = MagicMock(
        data=[{"state": "published", "post_id": "123_456"}]
    )

    slot = SCHEDULED_SLOTS[0]
    now_dt = datetime(2026, 10, 19, 18, 45, tzinfo=CAIRO_TZ)

    with _completed_slots_lock:
        _completed_slots_today.clear()

    res = execute_publication_slot(mock_client, slot, now_dt)
    assert res["status"] == "already_published"
    assert res["post_id"] == "123_456"


def test_execute_publication_slot_successful_publish():
    mock_client = MagicMock()
    mock_client.table().select().eq().eq().eq().limit().execute.return_value = MagicMock(data=[])

    mock_client.table().select().eq().eq().maybe_single().execute.return_value = MagicMock(
        data={
            "kind": "market",
            "image_url": "https://supabase.co/market.png",
            "image_status": "ready",
            "social_caption": "وضع السوق المصري ممتاز وإشارات السيولة قوية",
            "social_title": "تقرير السوق",
            "evidence": [{"tool": "get_market", "data": {"egx30": 30000}}],
        }
    )

    mock_client.table().upsert().execute.return_value = MagicMock(data=[{"id": 1}])

    slot = SCHEDULED_SLOTS[0]
    now_dt = datetime(2026, 10, 19, 18, 45, tzinfo=CAIRO_TZ)

    with _completed_slots_lock:
        _completed_slots_today.clear()

    with patch("api.social_scheduler.get_facebook_credentials", return_value={"token": "EAAG_TEST", "page_id": "1107903499083226"}):
        with patch("api.social_scheduler.publish_photo_to_facebook_page", return_value={"success": True, "post_id": "fb_post_999"}):
            res = execute_publication_slot(mock_client, slot, now_dt, force=True)

            assert res["status"] == "published"
            assert res["post_id"] == "fb_post_999"
            assert res["kind"] == "market"
            assert res["session_date"] == "2026-10-19"


def test_execute_publication_slot_skips_when_no_token():
    mock_client = MagicMock()
    mock_client.table().select().eq().eq().eq().limit().execute.return_value = MagicMock(data=[])

    slot = SCHEDULED_SLOTS[0]
    now_dt = datetime(2026, 10, 19, 18, 45, tzinfo=CAIRO_TZ)

    with _completed_slots_lock:
        _completed_slots_today.clear()

    with patch("api.social_scheduler.get_facebook_credentials", return_value=None):
        res = execute_publication_slot(mock_client, slot, now_dt, force=True)
        assert res["status"] == "skipped"
        assert res["reason"] == "Token not configured"


def test_execute_publication_slot_falls_back_when_accumulation_empty():
    mock_client = MagicMock()
    mock_client.table().select().eq().eq().eq().limit().execute.return_value = MagicMock(data=[])

    # Accumulation has empty stocks; market fallback has real data
    def mock_table_select(kind):
        if kind == "accumulation":
            return MagicMock(
                data={
                    "kind": "accumulation",
                    "image_url": "https://supabase.co/acc.png",
                    "image_status": "ready",
                    "social_caption": "لا توجد نتائج مطابقة في العينة",
                    "evidence": [{"tool": "get_accumulation_stocks", "data": {"stocks": []}}],
                }
            )
        elif kind == "stock":
            return MagicMock(data=None)
        elif kind == "market":
            return MagicMock(
                data={
                    "kind": "market",
                    "image_url": "https://supabase.co/market.png",
                    "image_status": "ready",
                    "social_caption": "مؤشرات السوق تسجل ارتفاعاً",
                    "evidence": [{"tool": "get_market", "data": {"egx30": 30500}}],
                }
            )
        return MagicMock(data=None)

    def select_side_effect(*args, **kwargs):
        eq_mock = MagicMock()
        def eq_date(col, val):
            eq_kind_mock = MagicMock()
            def eq_kind_val(col2, kind_val):
                res_mock = MagicMock()
                res_mock.maybe_single.return_value.execute.return_value = mock_table_select(kind_val)
                return res_mock
            eq_kind_mock.eq.side_effect = eq_kind_val
            return eq_kind_mock
        eq_mock.eq.side_effect = eq_date
        return eq_mock

    # Slot 3 is accumulation_morning (preferred: accumulation, fallbacks: follow_up, stock, market)
    morning_slot = SCHEDULED_SLOTS[2]
    now_dt = datetime(2026, 10, 19, 8, 45, tzinfo=CAIRO_TZ)  # Monday morning -> target Sunday 2026-10-18

    mock_client.table("daily_social_reports").select.side_effect = select_side_effect
    mock_client.table("daily_social_publications").upsert().execute.return_value = MagicMock(data=[{"id": 1}])

    with _completed_slots_lock:
        _completed_slots_today.clear()

    with patch("api.social_scheduler.get_facebook_credentials", return_value={"token": "EAAG_TEST", "page_id": "1107903499083226"}):
        with patch("api.social_scheduler.publish_photo_to_facebook_page", return_value={"success": True, "post_id": "fb_fallback_123"}):
            res = execute_publication_slot(mock_client, morning_slot, now_dt, force=True)

            assert res["status"] == "published"
            assert res["kind"] == "market"
            assert res["post_id"] == "fb_fallback_123"


def test_execute_publication_slot_preclaims_slot_memory():
    mock_client = MagicMock()
    mock_client.table().select().eq().eq().eq().limit().execute.return_value = MagicMock(data=[])

    slot = SCHEDULED_SLOTS[0]
    now_dt = datetime(2026, 10, 19, 18, 45, tzinfo=CAIRO_TZ)

    slot_key = "2026-10-19:market_evening"
    with _completed_slots_lock:
        _completed_slots_today.clear()
        _completed_slots_today.add(slot_key)

    # Calling without force should immediately skip due to in-memory pre-claim
    res = execute_publication_slot(mock_client, slot, now_dt, force=False)
    assert res["status"] == "skipped"
    assert "already published in memory" in res["reason"]
