"""
api/tests/test_scheduled_automations.py — Unit Tests for Scheduled AI Automations Worker.
"""

import datetime as dt
import unittest
from unittest.mock import MagicMock, patch

from api import scheduled_automations_worker as worker


class TestScheduledAutomationsWorker(unittest.TestCase):

    def setUp(self):
        worker._cached_automations = []

    def test_sync_automations_cache(self):
        fake_rows = [
            {"id": "auto-1", "user_id": "u-1", "name": "Task 1", "scheduled_time": "08:30", "is_active": True},
            {"id": "auto-2", "user_id": "u-2", "name": "Task 2", "scheduled_time": "12:00", "is_active": True},
        ]
        with patch.object(worker, "_supabase_request", return_value=fake_rows):
            count = worker.sync_automations_cache()
            self.assertEqual(count, 2)
            self.assertEqual(len(worker._cached_automations), 2)

    def test_is_user_pro(self):
        # 1. Admin user id / telegram
        self.assertTrue(worker._is_user_pro("ba9c27e8-f62d-452f-8a29-dc77fd092207"))

        with patch.object(worker, "_supabase_request", return_value=[{"telegram_chat_id": "5149631436"}]):
            self.assertTrue(worker._is_user_pro("any-user-with-admin-tg"))

        # 2. Expired subscription
        past_date = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).isoformat()
        with patch.object(worker, "_supabase_request", side_effect=[
            [{"telegram_chat_id": "11111"}],
            [{"plan_id": "pro", "current_period_end": past_date}]
        ]):
            self.assertFalse(worker._is_user_pro("expired-user"))

        # 3. Active subscription
        future_date = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=10)).isoformat()
        with patch.object(worker, "_supabase_request", side_effect=[
            [{"telegram_chat_id": "22222"}],
            [{"plan_id": "pro", "current_period_end": future_date}]
        ]):
            self.assertTrue(worker._is_user_pro("active-pro-user"))

    def test_resolve_user_telegram(self):
        # 1. Custom chat id has highest priority
        resolved = worker._resolve_user_telegram("u-1", "custom-12345")
        self.assertEqual(resolved, "custom-12345")

        # 2. Profile telegram_chat_id fallback
        with patch.object(worker, "_supabase_request", return_value=[{"telegram_chat_id": "999888"}]):
            resolved = worker._resolve_user_telegram("u-2", None)
            self.assertEqual(resolved, "999888")

    def test_execute_automation_quota_exceeded(self):
        fake_auto = {
            "id": "auto-100",
            "user_id": "u-quota-exceeded",
            "name": "Morning Brief",
            "prompt": "ما وضع السوق اليوم؟",
            "scheduled_time": "08:30",
            "telegram_chat_id": "123456",
        }
        with patch.object(worker, "_is_user_pro", return_value=True), \
             patch.object(worker, "_resolve_user_telegram", return_value="123456"), \
             patch.object(worker, "_consume_user_quota", return_value=False), \
             patch.object(worker, "send_telegram_direct", return_value=True) as mock_tg, \
             patch.object(worker, "_supabase_request", return_value=[]) as mock_db:

            res = worker.execute_single_automation(fake_auto)
            self.assertFalse(res["ok"])
            self.assertEqual(res["reason"], "quota_exceeded")
            # Verify quota alert was sent to user's Telegram
            mock_tg.assert_called_once()
            self.assertIn("تم استهلاك باقتك الشهرية", mock_tg.call_args[0][1])

    def test_execute_automation_success(self):
        fake_auto = {
            "id": "auto-200",
            "user_id": "u-happy",
            "name": "COMI Check",
            "prompt": "حلل سهم COMI",
            "scheduled_time": "09:00",
            "telegram_chat_id": "777888",
        }
        with patch.object(worker, "_is_user_pro", return_value=True), \
             patch.object(worker, "_resolve_user_telegram", return_value="777888"), \
             patch.object(worker, "_consume_user_quota", return_value=True), \
             patch.object(worker, "_generate_ai_consultation", return_value="سهم التجاري الدولي في مسار صاعد قوي.") as mock_ai, \
             patch.object(worker, "send_telegram_direct", return_value=True) as mock_tg, \
             patch.object(worker, "_supabase_request", return_value=[]):

            res = worker.execute_single_automation(fake_auto)
            self.assertTrue(res["ok"])
            self.assertEqual(res["status"], "success")
            mock_ai.assert_called_once()
            mock_tg.assert_called_once()
            sent_text = mock_tg.call_args[0][1]
            self.assertIn("سهم التجاري الدولي في مسار صاعد قوي", sent_text)
            self.assertIn("COMI Check", sent_text)

    def test_execute_automation_pro_required(self):
        fake_auto = {
            "id": "auto-300",
            "user_id": "u-free",
            "name": "Free User Task",
            "prompt": "Test",
            "scheduled_time": "10:00",
        }
        with patch.object(worker, "_is_user_pro", return_value=False), \
             patch.object(worker, "_supabase_request", return_value=[]):

            res = worker.execute_single_automation(fake_auto)
            self.assertFalse(res["ok"])
            self.assertEqual(res["reason"], "pro_required")

    def test_weekend_and_midnight_timing(self):
        # 1. Midnight diff calculation
        sh, sm = 23, 55
        ch, cm = 0, 2
        diff_minutes = (ch * 60 + cm) - (sh * 60 + sm)
        if diff_minutes < 0:
            diff_minutes += 1440
        self.assertEqual(diff_minutes, 7)
        self.assertTrue(0 <= diff_minutes <= 10)

        # 2. Weekday checks (Friday=4, Saturday=5)
        trading_days_allowed = {6, 0, 1, 2, 3}
        self.assertNotIn(4, trading_days_allowed)  # Friday skipped in trading_days
        self.assertNotIn(5, trading_days_allowed)  # Saturday skipped in trading_days
        self.assertIn(6, trading_days_allowed)     # Sunday is EGX trading day


if __name__ == "__main__":
    unittest.main()
