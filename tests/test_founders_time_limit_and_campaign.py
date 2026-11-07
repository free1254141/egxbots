from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest

from api.payment_common import (
    founders_offer_ends_at,
    founders_offer_is_open,
    plan_amount_egp,
    is_user_eligible_for_100_egp_renewal,
)
from jobs.send_founders_final_48h_emails import (
    get_offer_hours_remaining,
    is_within_final_48h_window,
    DEFAULT_ENDS_AT,
)


def test_founders_offer_is_open_and_expired():
    future_time = datetime.now(timezone.utc) + timedelta(days=5)
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)

    with patch("api.payment_common.founders_offer_ends_at", return_value=future_time):
        assert founders_offer_is_open() is True

    with patch("api.payment_common.founders_offer_ends_at", return_value=past_time):
        assert founders_offer_is_open() is False

    with patch("api.payment_common.founders_offer_ends_at", return_value=None):
        assert founders_offer_is_open() is True


def test_plan_amount_egp_with_founders_offer_open_vs_expired():
    settings = {
        "founders_offer_enabled": True,
        "founders_price_egp": 100.0,
        "founders_regular_price_egp": 200.0,
        "pro_price_egp": 100.0,
    }

    # Open offer: returns 100.0
    with patch("api.payment_common.billing_settings", return_value=settings), \
         patch("api.payment_common.founders_offer_is_open", return_value=True), \
         patch("api.payment_common.pro_discount", return_value={"active": False}):
        assert plan_amount_egp("pro", user_id=None) == 100.0

    # Expired offer: returns 200.0
    with patch("api.payment_common.billing_settings", return_value=settings), \
         patch("api.payment_common.founders_offer_is_open", return_value=False), \
         patch("api.payment_common.pro_discount", return_value={"active": False}):
        assert plan_amount_egp("pro", user_id=None) == 200.0


def test_plan_amount_egp_grandfathering_precedence():
    settings = {
        "founders_offer_enabled": True,
        "founders_price_egp": 100.0,
        "founders_regular_price_egp": 200.0,
    }

    # User grandfathered at 50 EGP gets 50 even when offer is open or expired
    with patch("api.payment_common.billing_settings", return_value=settings), \
         patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=True), \
         patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=False):
        assert plan_amount_egp("pro", user_id="u_50") == 50.0

    # User grandfathered at 100 EGP gets 100 even when offer is expired
    with patch("api.payment_common.billing_settings", return_value=settings), \
         patch("api.payment_common.is_user_eligible_for_50_egp_renewal", return_value=False), \
         patch("api.payment_common.is_user_eligible_for_100_egp_renewal", return_value=True), \
         patch("api.payment_common.founders_offer_is_open", return_value=False):
        assert plan_amount_egp("pro", user_id="u_100") == 100.0


def test_final_48h_window_guard():
    ends_at = datetime(2026, 11, 14, 1, 0, 0, tzinfo=timezone.utc)

    # 10 days before: hours_remaining ~240 -> Outside 48h window
    now_far = ends_at - timedelta(days=10)
    with patch("jobs.send_founders_final_48h_emails.founders_offer_ends_at", return_value=ends_at):
        assert is_within_final_48h_window(now=now_far) is False

    # 36 hours before: Inside 48h window
    now_36h = ends_at - timedelta(hours=36)
    with patch("jobs.send_founders_final_48h_emails.founders_offer_ends_at", return_value=ends_at):
        assert is_within_final_48h_window(now=now_36h) is True

    # 2 hours before: Inside window
    now_2h = ends_at - timedelta(hours=2)
    with patch("jobs.send_founders_final_48h_emails.founders_offer_ends_at", return_value=ends_at):
        assert is_within_final_48h_window(now=now_2h) is True

    # 1 hour after expiry: hours_remaining < 0 -> Expired
    now_expired = ends_at + timedelta(hours=1)
    with patch("jobs.send_founders_final_48h_emails.founders_offer_ends_at", return_value=ends_at):
        assert is_within_final_48h_window(now=now_expired) is False
